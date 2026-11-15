"""Read and write the settings stored on the lamp."""

import logging
from datetime import datetime

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt

from . import protocol as p

_LOGGER = logging.getLogger(__name__)
PRAYER_SLOTS = {
    slot: name for slot, name in enumerate(p.PRAYERS, 1) if name != "sunrise"
}
PRAYER_MASK = sum(1 << (slot - 1) for slot in PRAYER_SLOTS)


def decode_schedule(data):
    if len(data) != 13:
        raise HomeAssistantError("The lamp returned an unexpected prayer schedule")
    return {
        prayer: f"{hour:02d}:{minute:02d}"
        for prayer, hour, minute in zip(p.PRAYERS, data[1::2], data[2::2], strict=True)
    }


async def read_enabled(session):
    reply = await session.request(p.frame(p.AZAN_STATUS))
    if reply not in (b"\x00", b"\x01"):
        raise HomeAssistantError("The lamp returned an unexpected azan switch state")
    return reply == b"\x01"


async def read_mask(session):
    reply = await session.request(p.frame(p.AZAN_SLOT_STATUS))
    if len(reply) != 1:
        raise HomeAssistantError("The lamp returned unexpected prayer alarm settings")
    return reply[0]


async def write_mask(session, desired):
    actual = await read_mask(session)
    if actual & 0x3F == desired:
        return
    for slot in range(1, 7):
        bit = 1 << (slot - 1)
        if (actual ^ desired) & bit:
            await session.write(
                p.frame(p.AZAN_SLOT_ENABLE, slot, int(bool(desired & bit)))
            )
    if (await read_mask(session)) & 0x3F != desired:
        raise HomeAssistantError("The lamp did not save the prayer alarm settings")


class LampSettings(DataUpdateCoordinator):
    def __init__(self, hass, entry, lamp):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{entry.title} settings",
        )
        self.lamp = lamp
        self._store = Store[dict[str, int]](
            hass, 1, f"quran_lamp.{entry.entry_id}.alarms"
        )
        self._saved_mask = PRAYER_MASK
        self._sync_store = Store[dict[str, str]](
            hass, 1, f"quran_lamp.{entry.entry_id}.mawaqit_sync"
        )
        self.last_mawaqit_sync: datetime | None = None

    async def async_load_preferences(self):
        if (data := await self._store.async_load()) is not None:
            self._saved_mask = data["mask"] & PRAYER_MASK

        if (data := await self._sync_store.async_load()) is not None:
            self.last_mawaqit_sync = dt.parse_datetime(data["completed_at"])

    async def async_record_mawaqit_sync(self, schedule):
        completed_at = dt.utcnow()
        await self._sync_store.async_save({"completed_at": completed_at.isoformat()})
        self.last_mawaqit_sync = completed_at
        self.async_set_updated_data({**(self.data or {}), "schedule": schedule})

    async def _save_mask(self, mask):
        await self._store.async_save({"mask": mask})
        self._saved_mask = mask

    async def async_read(self, session):
        try:
            enabled = await read_enabled(session)
            data = {
                "enabled": enabled,
                "mask": (await read_mask(session)) & PRAYER_MASK
                if enabled
                else self._saved_mask,
                "schedule": decode_schedule(await session.request(p.frame(p.SCHEDULE))),
                "tones": {
                    slot: await session.read_azan_tone(slot) for slot in PRAYER_SLOTS
                },
            }
        except HomeAssistantError as err:
            self.async_set_update_error(err)
        else:
            self.async_set_updated_data(data)

    async def async_set_enabled(self, enabled):
        async with self.lamp.session() as session:
            was_enabled = await read_enabled(session)
            mask = (
                (await read_mask(session)) & PRAYER_MASK
                if was_enabled
                else self._saved_mask
            )
            if was_enabled and not enabled:
                await self._save_mask(mask)
            if was_enabled != enabled:
                await session.write(p.frame(p.AZAN_ENABLE, int(enabled)))
                if await read_enabled(session) != enabled:
                    raise HomeAssistantError("The lamp did not change its azan switch")
            if enabled:
                # Switching on can re-enable all five prayers in the firmware.
                await write_mask(session, mask)
            self.async_set_updated_data(
                {**(self.data or {}), "enabled": enabled, "mask": mask}
            )

    async def async_set_prayer_sound(self, slot, tone):
        async with self.lamp.session() as session:
            enabled = await read_enabled(session)
            mask = (
                (await read_mask(session)) & PRAYER_MASK
                if enabled
                else self._saved_mask
            )
            bit = 1 << (slot - 1)
            if tone is None:
                mask &= ~bit
            else:
                # The final zero saves the recording without previewing it.
                await session.write(p.frame(p.AZAN_TONE, slot, tone, 0))
                if await session.read_azan_tone(slot) != tone:
                    raise HomeAssistantError(
                        "The lamp did not save the selected azan sound"
                    )
                mask |= bit
            if enabled:
                await write_mask(session, mask)
            await self._save_mask(mask)
            data = self.data or {}
            tones = data.get("tones", {})
            if tone is not None:
                tones = {**tones, slot: tone}
            self.async_set_updated_data(
                {**data, "enabled": enabled, "mask": mask, "tones": tones}
            )
