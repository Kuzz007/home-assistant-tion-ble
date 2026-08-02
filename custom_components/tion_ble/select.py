"""Select platform for Tion Lite."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TionBleConfigEntry
from .const import DEFAULT_MAX_FAN_SPEED
from .entity import TionBleEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ventilation speed control."""
    async_add_entities([TionFanSpeedSelect(entry)])


class TionFanSpeedSelect(TionBleEntity, SelectEntity):
    """Explicit selector for the six Tion Lite ventilation speeds."""

    _attr_translation_key = "fan_speed"
    _attr_icon = "mdi:fan-chevron-up"

    def __init__(self, entry: TionBleConfigEntry) -> None:
        """Initialize the fan speed selector."""
        super().__init__(entry, "fan_speed")
        max_speed = self.coordinator.data.max_fan_speed or DEFAULT_MAX_FAN_SPEED
        self._attr_options = [str(speed) for speed in range(1, max_speed + 1)]

    @property
    def current_option(self) -> str:
        """Return the current discrete ventilation speed."""
        speed = self.coordinator.data.fan_speed
        if speed <= 0:
            speed = 1
        return str(min(speed, len(self.options)))

    async def async_select_option(self, option: str) -> None:
        """Select a speed and turn on the breezer when necessary."""
        if option not in self.options:
            raise ValueError(f"Unsupported Tion Lite speed: {option}")
        await self.coordinator.async_set_state(
            power=True,
            fan_speed=int(option),
        )
