"""Binary sensor platform for Tion Lite."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TionBleConfigEntry
from .entity import TionBleEntity
from .protocol import TionLiteState


@dataclass(frozen=True, kw_only=True)
class TionBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a Tion Lite binary sensor."""

    value_fn: Callable[[TionLiteState], bool]
    requires_heater: bool = False


BINARY_SENSORS = (
    TionBinarySensorDescription(
        key="filter_required",
        translation_key="filter_required",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.filter_required,
    ),
    TionBinarySensorDescription(
        key="heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda state: state.heater and state.heater_output > 0,
        requires_heater=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tion Lite binary sensors."""
    state = entry.runtime_data.coordinator.data
    async_add_entities(
        TionLiteBinarySensor(entry, description)
        for description in BINARY_SENSORS
        if not description.requires_heater or state.heater_present
    )


class TionLiteBinarySensor(TionBleEntity, BinarySensorEntity):
    """A binary state reported by Tion Lite."""

    entity_description: TionBinarySensorDescription

    def __init__(
        self,
        entry: TionBleConfigEntry,
        description: TionBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the binary state."""
        return self.entity_description.value_fn(self.coordinator.data)
