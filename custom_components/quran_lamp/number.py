"""Show the current ayah and select where the next recitation starts."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .recitations import AYAH_COUNTS


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Ayah(entry.runtime_data)])


class Ayah(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Ayah"
    _attr_icon = "mdi:book-open-page-variant-outline"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_step = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.lamp.address}_start_ayah"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self):
        return super().available and self.coordinator.selected_surah is not None

    @property
    def native_max_value(self):
        surah = self.coordinator.selected_surah
        return AYAH_COUNTS[surah - 1] if surah is not None else 1

    @property
    def native_value(self):
        coordinator = self.coordinator
        if (
            not coordinator.recitation_pending
            and coordinator.selected_surah == coordinator.reported_surah
            and coordinator.reported_ayah is not None
        ):
            return coordinator.reported_ayah
        return coordinator.start_ayah

    async def async_set_native_value(self, value):
        if int(value) != value or not 1 <= value <= self.native_max_value:
            raise HomeAssistantError(
                f"Choose a whole ayah from 1 to {self.native_max_value}"
            )
        self.coordinator.start_ayah = int(value)
        self.coordinator.recitation_pending = True
        self.coordinator.async_update_listeners()
