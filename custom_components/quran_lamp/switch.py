"""Master switch for the Quran lamp's built-in azan."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([AzanSwitch(entry.runtime_data)])


class AzanSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_name = "Built-in azan"

    def __init__(self, lamp_coordinator):
        super().__init__(lamp_coordinator.settings)
        self._attr_device_info = lamp_coordinator.device_info
        self._attr_unique_id = f"{lamp_coordinator.lamp.address}_azan_enabled"

    @property
    def is_on(self):
        return (self.coordinator.data or {}).get("enabled")

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_enabled(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_enabled(False)
