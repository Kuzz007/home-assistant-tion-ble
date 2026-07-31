"""Fan platform for Tion Lite."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TionBleConfigEntry
from .const import DEFAULT_MAX_FAN_SPEED
from .entity import TionBleEntity
from .util import percentage_to_speed, speed_to_percentage


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Tion Lite fan."""
    async_add_entities([TionLiteFan(entry)])


class TionLiteFan(TionBleEntity, FanEntity):
    """Representation of a Tion Lite breezer."""

    _attr_name = None
    _attr_translation_key = "breezer"
    _attr_supported_features = (
        FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.SET_SPEED
    )

    def __init__(self, entry: TionBleConfigEntry) -> None:
        """Initialize the breezer entity."""
        super().__init__(entry, "breezer")

    @property
    def is_on(self) -> bool:
        """Return whether the breezer is on."""
        return self.coordinator.data.power

    @property
    def speed_count(self) -> int:
        """Return the number of discrete speeds."""
        return self.coordinator.data.max_fan_speed or DEFAULT_MAX_FAN_SPEED

    @property
    def percentage(self) -> int:
        """Return the current speed as a percentage."""
        if not self.is_on:
            return 0
        return speed_to_percentage(
            self.coordinator.data.fan_speed or 1, self.speed_count
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Turn on the breezer."""
        changes: dict[str, object] = {"power": True}
        if percentage is not None:
            changes["fan_speed"] = percentage_to_speed(percentage, self.speed_count)
        elif self.coordinator.data.fan_speed <= 0:
            changes["fan_speed"] = 1
        await self.coordinator.async_set_state(**changes)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the breezer."""
        await self.coordinator.async_set_state(power=False)

    async def async_set_percentage(self, percentage: int) -> None:
        """Set one of the six Tion speeds."""
        if percentage <= 0:
            await self.async_turn_off()
            return
        await self.coordinator.async_set_state(
            power=True,
            fan_speed=percentage_to_speed(percentage, self.speed_count),
        )
