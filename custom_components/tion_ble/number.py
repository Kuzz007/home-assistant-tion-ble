"""Number platform for Tion Lite."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TionBleConfigEntry
from .const import MAX_TARGET_TEMPERATURE, MIN_TARGET_TEMPERATURE
from .entity import TionBleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the target temperature control."""
    async_add_entities([TionTargetTemperature(entry)])


class TionTargetTemperature(TionBleEntity, NumberEntity):
    """Target supply air temperature."""

    _attr_translation_key = "target_temperature"
    _attr_icon = "mdi:thermometer"
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_min_value = MIN_TARGET_TEMPERATURE
    _attr_native_max_value = MAX_TARGET_TEMPERATURE
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, entry: TionBleConfigEntry) -> None:
        """Initialize the number entity."""
        super().__init__(entry, "target_temperature")

    @property
    def native_value(self) -> int:
        """Return the current target temperature."""
        return self.coordinator.data.target_temperature

    async def async_set_native_value(self, value: float) -> None:
        """Set the target temperature."""
        await self.coordinator.async_set_state(target_temperature=round(value))
