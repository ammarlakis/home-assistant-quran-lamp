"""Play a preview of each prayer's stored azan recording."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .services import preview_prayer
from .settings import PRAYER_SLOTS


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        [
            AzanPreview(coordinator, slot, prayer, position)
            for position, (slot, prayer) in enumerate(PRAYER_SLOTS.items(), start=1)
        ]
    )


class AzanPreview(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:play"

    def __init__(self, coordinator, slot, prayer, position):
        super().__init__(coordinator.settings)
        self._slot = slot
        self._attr_name = f"Preview {position} · {prayer.capitalize()} azan"
        self._attr_unique_id = f"{coordinator.lamp.address}_{prayer}_azan_preview"
        self._attr_device_info = coordinator.device_info

    async def async_press(self):
        await preview_prayer(self.coordinator.lamp, self._slot)
