"""Select which built-in azan plays for each prayer."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .recitations import SURAHS
from .settings import PRAYER_SLOTS

TONES = ("Al Aqsa", "Egypt", "Famous azan", "Madina", "Makkah")


async def async_setup_entry(hass, entry, async_add_entities):
    lamp_coordinator = entry.runtime_data
    async_add_entities(
        [
            AzanSound(lamp_coordinator, slot, prayer, position)
            for position, (slot, prayer) in enumerate(PRAYER_SLOTS.items(), start=1)
        ]
        + [
            SurahSelect(lamp_coordinator),
            ReciterSelect(lamp_coordinator),
            TranslationSelect(lamp_coordinator),
        ]
    )


class PlaybackSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.lamp.address}_{key}"
        self._attr_device_info = coordinator.device_info


class SurahSelect(PlaybackSelect):
    _attr_name = "Surah"

    def __init__(self, coordinator):
        super().__init__(coordinator, "surah")
        self._attr_options = [f"{i}. {name}" for i, name in enumerate(SURAHS, 1)]

    @property
    def current_option(self):
        surah = self.coordinator.selected_surah
        return self.options[surah - 1] if surah is not None else None

    async def async_select_option(self, option):
        self.coordinator.set_selected_surah(self.options.index(option) + 1)
        self.coordinator.recitation_pending = True
        self.coordinator.async_update_listeners()


class ReciterSelect(PlaybackSelect):
    _attr_name = "Reciter"

    def __init__(self, coordinator):
        super().__init__(coordinator, "reciter")

    @property
    def options(self):
        return list(self.coordinator.reciters)

    @property
    def current_option(self):
        return next(
            (
                name
                for name, value in self.coordinator.reciters.items()
                if value == self.coordinator.selected_reciter
            ),
            None,
        )

    async def async_select_option(self, option):
        self.coordinator.selected_reciter = self.coordinator.reciters[option]
        self.coordinator.recitation_pending = True
        self.coordinator.async_update_listeners()


class TranslationSelect(PlaybackSelect):
    _attr_name = "Translation"

    def __init__(self, coordinator):
        super().__init__(coordinator, "translation")

    @property
    def available(self):
        return super().available and bool(self.coordinator.translations)

    @property
    def options(self):
        return list(self.coordinator.translations)

    @property
    def current_option(self):
        return next(
            (
                name
                for name, value in self.coordinator.translations.items()
                if value == self.coordinator.translation
            ),
            None,
        )

    async def async_select_option(self, option):
        await self.coordinator.async_set_translation(self.coordinator.translations[option])


class AzanSound(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, lamp_coordinator, slot, prayer, position):
        super().__init__(lamp_coordinator.settings)
        self._lamp = lamp_coordinator.lamp
        self._slot = slot
        self._attr_name = f"Prayer {position} · {prayer.capitalize()} azan sound"
        self._attr_unique_id = f"{self._lamp.address}_{prayer}_azan_sound"
        self._attr_device_info = lamp_coordinator.device_info
        self._attr_options = [
            *(("Fajr 1", "Fajr 2") + TONES if slot == 1 else TONES),
            "Off",
        ]

    @property
    def current_option(self):
        data = self.coordinator.data or {}
        if (mask := data.get("mask")) is not None and not mask & (
            1 << (self._slot - 1)
        ):
            return "Off"
        tone = data.get("tones", {}).get(self._slot)
        if tone is not None and 1 <= tone < len(self.options):
            return self.options[tone - 1]
        return None

    async def async_select_option(self, option):
        tone = None if option == "Off" else self.options.index(option) + 1
        await self.coordinator.async_set_prayer_sound(self._slot, tone)
