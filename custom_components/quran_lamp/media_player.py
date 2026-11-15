"""Playback of audio stored on the lamp."""

import asyncio

import voluptuous as vol
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_platform_entity_service
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import protocol as p
from .recitations import SURAHS

MAX_VOLUME = 30


def register_play_recitation(hass):
    async_register_platform_entity_service(
        hass,
        "quran_lamp",
        "play_recitation",
        entity_domain="media_player",
        func="async_play_recitation",
        schema={
            vol.Required("surah"): vol.All(vol.Coerce(int), vol.Range(min=1, max=114)),
            vol.Optional("reciter"): cv.string,
            vol.Optional("volume"): vol.All(
                vol.Coerce(float), vol.Range(min=0, max=100)
            ),
        },
    )


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([QuranPlayer(entry.runtime_data)])


class QuranPlayer(CoordinatorEntity, MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_name = "Speaker"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.lamp.address}_speaker"
        self._attr_device_info = coordinator.device_info

    @property
    def state(self):
        return (
            MediaPlayerState.PLAYING
            if self.coordinator.data["play"] in (1, 3)
            else MediaPlayerState.PAUSED
        )

    @property
    def volume_level(self):
        return min(MAX_VOLUME, self.coordinator.data["volume"]) / MAX_VOLUME

    @property
    def media_title(self):
        surah = self.coordinator.reported_surah
        return SURAHS[surah - 1] if surah is not None else None

    @property
    def media_artist(self):
        if self.coordinator.reported_surah is None:
            return None
        return next(
            (
                name
                for name, reciter in self.coordinator.reciters.items()
                if reciter == self.coordinator.reported_reciter
            ),
            None,
        )

    @property
    def extra_state_attributes(self):
        if self.coordinator.reported_surah is None:
            return None
        return {
            "surah": self.coordinator.reported_surah,
            "ayah": self.coordinator.reported_ayah,
        }

    async def _set_playing(self, playing):
        lamp = self.coordinator.lamp
        async with lamp.session() as session:
            status = await session.request(p.frame(p.PLAY_STATUS))
            if status not in (b"\x00", b"\x01", b"\x02", b"\x03"):
                raise HomeAssistantError("The lamp reported an unknown playback state")
            if playing and status == b"\x00":
                status = await self._wake_recitation(
                    session, self._resume_packet(), status
                )
            elif (status in (b"\x01", b"\x03")) != playing:
                await session.write(p.frame(p.PLAY_PAUSE))
                expected = (b"\x01", b"\x03") if playing else (b"\x00", b"\x02")
                for _ in range(4):
                    status = await session.request(p.frame(p.PLAY_STATUS))
                    if status in expected:
                        break
                    await asyncio.sleep(0.25)
                else:
                    if not playing or status not in (b"\x00", b"\x02"):
                        raise HomeAssistantError(
                            "The lamp did not change its playback state"
                        )
                    status = await self._wake_recitation(
                        session, self._resume_packet(), status
                    )
            self.coordinator.async_set_updated_data(
                {**self.coordinator.data, "play": status[0]}
            )

    async def async_media_play(self):
        coordinator = self.coordinator
        if coordinator.recitation_pending:
            surah = coordinator.selected_surah
            ayah = coordinator.start_ayah
            reciter = coordinator.selected_reciter
            if surah is not None:
                await self._play_packet(
                    p.surah(surah, ayah), surah=True, reciter=reciter
                )
            else:
                if reciter is not None:
                    await self.async_play_media(MediaType.MUSIC, f"reciter:{reciter}")
                await self._set_playing(True)
            if (surah, ayah, reciter) == (
                coordinator.selected_surah,
                coordinator.start_ayah,
                coordinator.selected_reciter,
            ):
                coordinator.recitation_pending = False
                coordinator.start_ayah = 1
                coordinator.async_update_listeners()
                await coordinator.lamp.send(p.frame(p.GET_CHAPTER))
            return
        await self._set_playing(True)

    async def async_media_pause(self):
        await self._set_playing(False)

    async def async_media_next_track(self):
        await self.coordinator.lamp.send(p.frame(p.NEXT))
        await self.coordinator.async_request_refresh()

    async def async_media_previous_track(self):
        await self.coordinator.lamp.send(p.frame(p.PREVIOUS))
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume):
        level = round(max(0, min(1, volume)) * MAX_VOLUME)
        async with self.coordinator.lamp.session() as session:
            await self._set_volume(session, level)
        self.coordinator.async_set_updated_data(
            {**self.coordinator.data, "volume": level}
        )

    @staticmethod
    async def _set_volume(session, level):
        if await session.request(p.frame(p.SET_VOLUME, level)) != b"\x01":
            raise HomeAssistantError("The lamp rejected the volume change")

    async def async_play_recitation(self, surah, reciter=None, volume=None):
        coordinator = self.coordinator
        reciter_id = None
        if reciter is not None:
            reciter_id = coordinator.reciters.get(reciter)
            if reciter_id is None:
                raise HomeAssistantError("Use a name from the lamp’s Reciter dropdown")
        level = round(volume * MAX_VOLUME / 100) if volume is not None else None
        await self._play_packet(
            p.surah(surah, 1), surah=True, reciter=reciter_id, level=level
        )
        if not coordinator.recitation_pending:
            coordinator.selected_reciter = coordinator.reported_reciter
            coordinator.async_update_listeners()

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        if media_content_id == "recitations":
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id="recitations",
                media_content_type=MediaClass.DIRECTORY,
                title="Quran recitations",
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.MUSIC,
                children=[
                    BrowseMedia(
                        media_class=MediaClass.MUSIC,
                        media_content_id=f"surah:{number}",
                        media_content_type=MediaType.MUSIC,
                        title=f"{number}. {name}",
                        can_play=True,
                        can_expand=False,
                    )
                    for number, name in enumerate(SURAHS, start=1)
                ],
            )

        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id="",
            media_content_type=MediaClass.DIRECTORY,
            title="Quran Lamp",
            can_play=False,
            can_expand=True,
            children=[
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id="recitations",
                    media_content_type=MediaClass.DIRECTORY,
                    title="Quran recitations",
                    can_play=False,
                    can_expand=True,
                ),
                BrowseMedia(
                    media_class=MediaClass.MUSIC,
                    media_content_id="mp3",
                    media_content_type=MediaType.MUSIC,
                    title="Lamp MP3 mode",
                    can_play=True,
                    can_expand=False,
                ),
            ],
        )

    async def async_play_media(self, media_type, media_id, **kwargs):
        if media_id.startswith("reciter:"):
            try:
                reciter = int(media_id.removeprefix("reciter:"))
            except ValueError as err:
                raise HomeAssistantError(
                    "Choose a reciter from the lamp’s list"
                ) from err
            async with self.coordinator.lamp.session() as session:
                ids = await session.request(p.frame(p.GET_RECITER_IDS))
                if not 1 <= reciter <= 254 or reciter not in ids:
                    raise HomeAssistantError("Choose a reciter from the lamp’s list")
                await self._select_reciter(session, reciter)
                status = await session.request(p.frame(p.PLAY_STATUS))
                if status not in (b"\x00", b"\x01", b"\x02", b"\x03"):
                    raise HomeAssistantError(
                        "The lamp returned an invalid speaker status"
                    )
                self.coordinator.async_set_updated_data(
                    {**self.coordinator.data, "play": status[0]}
                )
            return

        if media_id == "playback_mode":
            packet = p.frame(p.PLAYBACK_MODE)
        elif media_id == "mp3":
            packet = p.frame(p.MP3)
        elif media_id.startswith("surah:"):
            try:
                _, number, *verse = media_id.split(":")
                if len(verse) > 1:
                    raise ValueError
                packet = p.surah(int(number), int(verse[0]) if verse else 1)
            except ValueError as err:
                raise HomeAssistantError("Use surah:<1–114>[:ayah]") from err
        else:
            raise HomeAssistantError(
                "Choose playback_mode, mp3, reciter:<id>, or surah:<number>[:ayah]"
            )
        await self._play_packet(packet, surah=media_id.startswith("surah:"))

    async def _select_reciter(self, session, reciter):
        expected = bytes((reciter,))
        if await session.request(p.frame(p.GET_RECITER)) == expected:
            return
        await session.write(p.frame(p.SET_RECITER, reciter))
        for _ in range(4):
            if await session.request(p.frame(p.GET_RECITER)) == expected:
                return
            await asyncio.sleep(0.25)
        raise HomeAssistantError("The lamp did not confirm the selected reciter")

    @staticmethod
    async def _recitation_status(session):
        for attempt in range(4):
            if attempt:
                await asyncio.sleep(0.25)
            status = await session.request(p.frame(p.PLAY_STATUS))
            if status in (b"\x01", b"\x03"):
                break
        return status

    def _resume_packet(self):
        coordinator = self.coordinator
        surah = coordinator.reported_surah or coordinator.selected_surah or 1
        return p.surah(surah, coordinator.reported_ayah or 1)

    async def _wake_recitation(self, session, packet, status):
        if status == b"\x00":
            await session.wake_quran_mode()
        await session.write(packet)
        status = await self._recitation_status(session)
        if status not in (b"\x01", b"\x03"):
            raise HomeAssistantError("The lamp did not start Quran playback")
        await session.write(p.frame(p.GET_CHAPTER))
        return status

    async def _play_packet(self, packet, *, surah, reciter=None, level=None):
        # Keep the connection for the command and its readback while
        # the lamp switches audio modes.
        async with self.coordinator.lamp.session() as session:
            if surah and await session.request(p.frame(p.PLAY_STATUS)) == b"\x00":
                await session.wake_quran_mode()
            if reciter is not None:
                await self._select_reciter(session, reciter)
            if level is not None:
                await self._set_volume(session, level)
            await session.write(packet)
            if surah:
                status = await self._recitation_status(session)
                if status in (b"\x00", b"\x02"):
                    status = await self._wake_recitation(session, packet, status)
            else:
                status = await session.request(p.frame(p.PLAY_STATUS))
            volume = await session.request(p.frame(p.VOLUME))
            if surah and status in (b"\x01", b"\x03"):
                await session.write(p.frame(p.GET_CHAPTER))
            elif not surah and packet[1] == p.MP3:
                self.coordinator.reported_surah = None
                self.coordinator.reported_ayah = None
        if status not in (b"\x00", b"\x01", b"\x02", b"\x03") or len(volume) != 1:
            raise HomeAssistantError("The lamp returned an invalid speaker status")
        self.coordinator.async_set_updated_data(
            {"play": status[0], "volume": volume[0]}
        )
        if surah and status not in (b"\x01", b"\x03"):
            raise HomeAssistantError(
                "The lamp stayed paused after the recitation command"
            )
