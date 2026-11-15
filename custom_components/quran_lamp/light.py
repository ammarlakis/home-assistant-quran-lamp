"""Quran lamp light entity."""

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import protocol as p


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([QuranLight(entry.runtime_data)])


class QuranLight(CoordinatorEntity, LightEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_color_mode = ColorMode.RGB
    _attr_assumed_state = True

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_supported_color_modes = {ColorMode.RGB}
        self._attr_unique_id = f"{coordinator.lamp.address}_light"
        self._attr_device_info = coordinator.device_info
        self._last_brightness = 60

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (previous := await self.async_get_last_state()) is None:
            return
        if previous.state in ("on", "off"):
            self._attr_is_on = previous.state == "on"
        if isinstance(level := previous.attributes.get(ATTR_BRIGHTNESS), int):
            self._last_brightness = max(1, round(level * 100 / 255))
            self._attr_brightness = level
        if color := previous.attributes.get(ATTR_RGB_COLOR):
            self._attr_rgb_color = tuple(color)

    async def _write(self, packet):
        async with self.coordinator.lamp.session() as session:
            if await session.request(packet) != b"\x01":
                raise HomeAssistantError("The lamp rejected the light change")

    async def async_turn_on(self, **kwargs):
        level = self._last_brightness
        if ATTR_BRIGHTNESS in kwargs:
            level = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
        if color := kwargs.get(ATTR_RGB_COLOR):
            await self._write(p.frame(p.LIGHT_RGB, level, *color))
            self._attr_rgb_color = color
        else:
            await self._write(p.frame(p.SET_LIGHT_LEVEL, level))
        self._last_brightness = level
        self._attr_brightness = round(level * 255 / 100)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self._write(p.frame(p.SET_LIGHT_LEVEL, 0))
        self._attr_is_on = False
        self.async_write_ha_state()
