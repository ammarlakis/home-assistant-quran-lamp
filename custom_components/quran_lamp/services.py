"""Actions for the lamp's schedule and azan preview."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from . import protocol as p
from .prayers import sync_schedule
from .settings import decode_schedule

DOMAIN = "quran_lamp"


async def playback_is_active(session):
    state = await session.request(p.frame(p.PLAY_STATUS))
    if state not in (b"\x00", b"\x01", b"\x02", b"\x03"):
        raise HomeAssistantError("The lamp reported an unknown playback state")
    return state in (b"\x01", b"\x03")


async def preview_prayer(lamp, slot):
    """Play the selected prayer's saved recording on demand."""
    async with lamp.session() as session:
        tone = await session.read_azan_tone(slot)
        was_playing = await playback_is_active(session)
        await session.write(p.frame(p.AZAN_TONE, slot, tone, 1))
        lamp.playing_before_preview = was_playing


def register_services(hass):
    from .media_player import register_play_recitation

    register_play_recitation(hass)

    def coordinator_for(call):
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise HomeAssistantError("Select a loaded Quran Lamp integration entry")
        return entry.runtime_data

    def lamp_for(call):
        return coordinator_for(call).lamp

    async def set_prayer_times(call):
        times = tuple(call.data[key] for key in p.PRAYERS)
        coordinator = coordinator_for(call)
        settings = coordinator.settings
        schedule = await sync_schedule(coordinator.lamp, times)
        settings.async_set_updated_data({**(settings.data or {}), "schedule": schedule})
        if "enable_azan" in call.data:
            await settings.async_set_enabled(call.data["enable_azan"])

    async def preview_azan(call):
        slot = p.PRAYERS.index(call.data["prayer"]) + 1
        await preview_prayer(lamp_for(call), slot)

    async def stop_azan_preview(call):
        lamp = lamp_for(call)
        async with lamp.session() as session:
            if await session.request(p.frame(p.STOP_PREVIEW)) != b"\x01":
                raise HomeAssistantError("The lamp rejected the azan stop command")
            if lamp.playing_before_preview is False and await playback_is_active(
                session
            ):
                # The firmware can start a recitation when the ringtone preview stops.
                await session.write(p.frame(p.PLAY_PAUSE))
                if await playback_is_active(session):
                    raise HomeAssistantError(
                        "Azan stopped, but the lamp did not pause the recitation"
                    )
            lamp.playing_before_preview = None

    async def set_azan_switch(call):
        await coordinator_for(call).settings.async_set_enabled(call.data["enabled"])

    async def get_prayer_times(call):
        async with lamp_for(call).session() as session:
            stored = await session.request(p.frame(p.SCHEDULE))
            displayed = await session.request(p.frame(p.DISPLAY_SCHEDULE))
            enabled = await session.request(p.frame(p.AZAN_STATUS))

        return {
            "stored": decode_schedule(stored),
            "displayed": decode_schedule(displayed),
            "enabled": enabled == b"\x01",
        }

    entry_field = {vol.Required("config_entry_id"): cv.string}
    hass.services.async_register(
        DOMAIN,
        "get_prayer_times",
        get_prayer_times,
        schema=vol.Schema(entry_field),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "set_azan_switch",
        set_azan_switch,
        schema=vol.Schema({**entry_field, vol.Required("enabled"): cv.boolean}),
    )
    hass.services.async_register(
        DOMAIN,
        "set_prayer_times",
        set_prayer_times,
        schema=vol.Schema(
            {
                **entry_field,
                **{vol.Required(key): cv.time for key in p.PRAYERS},
                vol.Optional("enable_azan"): cv.boolean,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "preview_azan",
        preview_azan,
        schema=vol.Schema(
            {
                **entry_field,
                vol.Required("prayer", default="fajr"): vol.In(p.PRAYERS),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "stop_azan_preview",
        stop_azan_preview,
        schema=vol.Schema(entry_field),
    )
