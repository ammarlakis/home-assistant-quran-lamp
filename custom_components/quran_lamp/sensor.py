"""Expose prayer times from the lamp."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .protocol import PRAYERS


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    old_entity_id = registry.async_get_entity_id(
        "sensor", entry.domain, f"{coordinator.lamp.address}_current_ayah"
    )
    if old_entity_id is not None:
        registry.async_remove(old_entity_id)

    async_add_entities(
        [StoredPrayerTime(coordinator, prayer) for prayer in PRAYERS]
        + [LastMawaqitSync(coordinator)]
    )


class StoredPrayerTime(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-outline"

    def __init__(self, lamp_coordinator, prayer):
        super().__init__(lamp_coordinator.settings)
        self._prayer = prayer
        label = "Shuruq" if prayer == "sunrise" else prayer.capitalize()
        self._attr_name = f"Stored {label} time"
        self._attr_unique_id = f"{lamp_coordinator.lamp.address}_{prayer}_stored_time"
        self._attr_device_info = lamp_coordinator.device_info

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("schedule", {}).get(self._prayer)


class LastMawaqitSync(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Last sync"

    def __init__(self, lamp_coordinator):
        super().__init__(lamp_coordinator.settings)
        self._attr_unique_id = f"{lamp_coordinator.lamp.address}_last_mawaqit_sync"
        self._attr_device_info = lamp_coordinator.device_info

    @property
    def available(self):
        # The saved timestamp remains useful when the lamp cannot be reached.
        return True

    @property
    def native_value(self):
        return self.coordinator.last_mawaqit_sync
