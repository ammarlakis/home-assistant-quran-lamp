"""Home Assistant integration for the SQ953 Quran lamp."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import protocol as p
from .connection import Lamp
from .prayers import start_sync
from .recitations import SURAHS
from .services import register_services
from .settings import LampSettings

DOMAIN = "quran_lamp"
PLATFORMS = [
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.BUTTON,
]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    register_services(hass)
    return True


async def async_setup_entry(hass, entry):
    coordinator = LampCoordinator(hass, entry)
    await coordinator.settings.async_load_preferences()
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.lamp.aclose()
        raise
    if entry.options.get("sync_prayer_times"):
        start_sync(hass, entry, coordinator.lamp, coordinator.settings)
    return True


async def async_unload_entry(hass, entry):
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.lamp.aclose()
    return unloaded


class LampCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            config_entry=entry,
            update_interval=timedelta(minutes=1),
        )
        self.lamp = Lamp(hass, entry.data[CONF_ADDRESS], self._on_notification)
        self.settings = LampSettings(hass, entry, self.lamp)
        self.reciters = {}
        self.translations = {}
        self.translation = None
        self._translation_probed = False
        self.selected_reciter = None
        self.selected_surah = None
        self.start_ayah = 1
        self.reported_surah = None
        self.reported_ayah = None
        self.reported_reciter = None
        self.recitation_pending = False
        self.device_info = {
            "identifiers": {(DOMAIN, self.lamp.address)},
            "name": entry.title,
            "model": "SQ953",
        }

    @callback
    def _on_notification(self, opcode, payload):
        if opcode in (p.GET_RECITER, p.SET_RECITER) and len(payload) == 1:
            self.reported_reciter = payload[0]
            return
        if opcode in (p.GET_TRANSLATION, p.SET_TRANSLATION, p.NEXT_TRANSLATION):
            # Reading the saved language says nothing about Arabic-only playback.
            if opcode == p.GET_TRANSLATION and self.translation == 0:
                return
            if len(payload) == 1 and payload[0] in self.translations.values():
                self.translation = payload[0]
                self.async_update_listeners()
            return
        if opcode not in (p.NEXT, p.PREVIOUS, p.GET_CHAPTER) or len(payload) != 3:
            return
        surah = payload[0] + 1
        if surah > len(SURAHS):
            return
        self.reported_surah = surah
        self.reported_ayah = int.from_bytes(payload[1:], "big") + 1
        if not self.recitation_pending:
            self.set_selected_surah(surah)
        self.async_update_listeners()

    @callback
    def set_selected_surah(self, surah):
        if surah != self.selected_surah:
            self.selected_surah = surah
            self.start_ayah = 1

    async def async_set_translation(self, translation):
        async with self.lamp.session() as session:
            if translation == 0:
                await self._disable_translation(session)
            else:
                expected = bytes((translation,))
                response = await session.request(
                    p.frame(p.SET_TRANSLATION, translation), optional=True
                )
                if response != expected:
                    raise HomeAssistantError(
                        "The lamp did not confirm the selected translation"
                    )
            self.translation = translation
        self.async_update_listeners()

    async def _disable_translation(self, session):
        status = await session.request(p.frame(p.PLAY_STATUS))
        if status not in (b"\x00", b"\x01", b"\x02", b"\x03"):
            raise HomeAssistantError("The lamp reported an unknown playback state")
        was_playing = status in (b"\x01", b"\x03")
        await session.request(p.frame(p.GET_CHAPTER), optional=True)
        surah = self.reported_surah or self.selected_surah or 1
        ayah = self.reported_ayah or 1
        reciter = await session.request(p.frame(p.GET_RECITER))
        if len(reciter) != 1 or reciter[0] in (0, 255):
            raise HomeAssistantError("The lamp did not report its reciter")

        try:
            if status == b"\x00":
                await session.wake_quran_mode()
                status = await session.request(p.frame(p.PLAY_STATUS))
            if status not in (b"\x01", b"\x03"):
                await session.write(p.frame(p.PLAY_PAUSE))
                await self._wait_for_playback(session, playing=True)
            # This firmware treats translation ID zero as English. Leaving recitation
            # mode and explicitly reselecting the reciter starts Arabic-only playback.
            await session.request(p.frame(p.MP3))
            if await session.request(p.frame(p.SET_RECITER, reciter[0])) != reciter:
                raise HomeAssistantError("The lamp did not confirm its reciter")
            await session.write(p.surah(surah, ayah))
            status = await self._wait_for_playback(session, playing=True)
        finally:
            if not was_playing and session.connected:
                status = await session.request(p.frame(p.PLAY_STATUS))
                if status in (b"\x01", b"\x03"):
                    await session.write(p.frame(p.PLAY_PAUSE))
                    status = await self._wait_for_playback(session, playing=False)
        await session.write(p.frame(p.GET_CHAPTER))
        self.async_set_updated_data({**self.data, "play": status[0]})

    @staticmethod
    async def _wait_for_playback(session, *, playing):
        expected = (b"\x01", b"\x03") if playing else (b"\x00", b"\x02")
        for attempt in range(4):
            if attempt:
                await asyncio.sleep(0.25)
            status = await session.request(p.frame(p.PLAY_STATUS))
            if status in expected:
                return status
        raise HomeAssistantError("The lamp did not change its playback state")

    async def _read_translation(self, session):
        ids = await session.request(p.frame(p.GET_TRANSLATION_IDS), optional=True)
        if ids is None:
            raise HomeAssistantError("The lamp did not report its translation catalog")
        ids = ids.partition(b"\xff")[0]
        options = {"Off": 0}
        for language in dict.fromkeys(ids):
            if language in (0, 255):
                continue
            name = p.TRANSLATION_NAMES.get(language)
            if name is None:
                raw = await session.request(
                    p.frame(p.GET_TRANSLATION_NAME, language), optional=True
                )
                name = (raw or b"").rstrip(b"\0 ").decode("utf-8", errors="replace")
            name = name or f"Language {language}"
            if name in options:
                name = f"{name} ({language})"
            options[name] = language
        self.translations = options
        current = await session.request(p.frame(p.GET_TRANSLATION), optional=True)
        if self.translation != 0 and current and len(current) == 1:
            self.translation = current[0]

    async def _async_update_data(self):
        try:
            async with self.lamp.session() as session:
                playback = {
                    "play": (await session.request(p.frame(p.PLAY_STATUS)))[0],
                    "volume": (await session.request(p.frame(p.VOLUME)))[0],
                }
                if not self.reciters:
                    try:
                        ids = await session.request(p.frame(p.GET_RECITER_IDS))
                        names = {}
                        for reciter in dict.fromkeys(ids):
                            if reciter in (0, 255):
                                continue
                            reply = await session.request(
                                p.frame(p.GET_RECITER_NAME, reciter)
                            )
                            name = reply.rstrip(b"\0 ").decode(
                                "utf-8", errors="replace"
                            )
                            names[reciter] = name or f"Reciter {reciter}"
                        current = await session.request(p.frame(p.GET_RECITER))
                    except HomeAssistantError as err:
                        _LOGGER.debug("Could not read the lamp's reciters: %s", err)
                    else:
                        self.reciters = {
                            f"{name} ({reciter})"
                            if list(names.values()).count(name) > 1
                            else name: reciter
                            for reciter, name in names.items()
                        }
                        if self.selected_reciter is None and len(current) == 1:
                            self.selected_reciter = current[0]
                if session.connected:
                    await self.settings.async_read(session)
                if session.connected and playback["play"] in (1, 2, 3):
                    # Some firmware reports chapters only when explicitly queried.
                    await session.request(p.frame(p.GET_RECITER), optional=True)
                    await session.write(p.frame(p.GET_CHAPTER))
                if session.connected and not self._translation_probed:
                    self._translation_probed = True
                    try:
                        await self._read_translation(session)
                    except HomeAssistantError as err:
                        _LOGGER.debug("Could not read the lamp's translation: %s", err)
                return playback
        except (HomeAssistantError, IndexError) as err:
            self.settings.async_set_update_error(err)
            raise UpdateFailed(str(err)) from err
