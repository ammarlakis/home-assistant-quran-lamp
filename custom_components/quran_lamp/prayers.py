"""Write the lamp's daily schedule from local prayer times."""

import logging
from datetime import time, timedelta

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt

from . import protocol as p
from .settings import decode_schedule

_LOGGER = logging.getLogger(__name__)


async def sync_schedule(lamp, times):
    """Update selected times and read back the full schedule."""
    async with lamp.session() as session:
        original = await session.request(p.frame(p.SCHEDULE))
        if len(original) != 13:
            raise HomeAssistantError("The lamp returned an unexpected prayer schedule")
        expected = p.schedule(original, times)
        if await session.request(p.clock(dt.now())) != b"\x01":
            raise HomeAssistantError("The lamp rejected its new clock time")
        if original != expected[2:-2]:
            if await session.request(expected) != b"\x01":
                raise HomeAssistantError("The lamp rejected the prayer schedule")
            if await session.request(p.frame(p.SCHEDULE)) != expected[2:-2]:
                raise HomeAssistantError(
                    "The lamp did not retain the requested prayer times"
                )
        return decode_schedule(expected[2:-2])


def read_sensor(value, now):
    """Map the next prayer onto the lamp’s repeating daily clock."""
    try:
        wall_time = time.fromisoformat(value)
    except ValueError:
        try:
            timestamp = dt.parse_datetime(value)
        except ValueError:
            return None
        if timestamp is None or timestamp.tzinfo is None:
            return None
        local = dt.as_local(timestamp)
        if local.date() == now.date():
            return local.time()
        # A next-day time can replace a past slot only once its wall time
        # has also passed today. Otherwise it could fire a second time today.
        if local.date() == now.date() + timedelta(days=1) and (
            local.hour,
            local.minute,
        ) < (now.hour, now.minute):
            return local.time()
        return None
    return wall_time if wall_time.tzinfo is None else None


def start_sync(hass, entry, lamp, settings):
    sensors = [entry.options.get(key) for key in p.PRAYERS]
    selected_sensors = list(
        dict.fromkeys(entity_id for entity_id in sensors if entity_id)
    )
    if not selected_sensors:
        return
    last_synced = None
    task = None

    async def sync():
        nonlocal last_synced
        now = dt.now()
        times = []
        for entity_id in sensors:
            if not entity_id:
                times.append(None)
                continue
            state = hass.states.get(entity_id)
            value = read_sensor(state.state, now) if state else None
            if value is None:
                _LOGGER.debug("Waiting for a safe prayer time from %s", entity_id)
                return
            times.append(value.replace(second=0, microsecond=0))
        key = now.date(), tuple(times)
        if key != last_synced:
            try:
                schedule = await sync_schedule(lamp, key[1])
                await settings.async_record_sync(schedule)
            except (HomeAssistantError, OSError) as err:
                _LOGGER.warning(
                    "Could not sync prayer times for %s: %s", entry.title, err
                )
            else:
                last_synced = key

    @callback
    def queue_sync(_event=None):
        nonlocal task
        if task is None or task.done():
            task = entry.async_create_background_task(
                hass, sync(), "quran_lamp prayer sync"
            )

    entry.async_on_unload(
        async_track_state_change_event(hass, selected_sensors, queue_sync)
    )
    entry.async_on_unload(
        async_track_time_change(hass, queue_sync, minute=range(0, 60, 5), second=10)
    )
    queue_sync()
