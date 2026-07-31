"""Sensor platform for Tion Lite."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TionBleConfigEntry
from .entity import TionBleEntity
from .protocol import TionLiteState


def _temperature(value: int) -> int | None:
    """Discard the protocol's invalid-temperature sentinel values."""
    return None if value <= -100 else value


@dataclass(frozen=True, kw_only=True)
class TionSensorDescription(SensorEntityDescription):
    """Describe a Tion Lite sensor."""

    value_fn: Callable[[TionLiteState], int | float | str | None]


SENSORS = (
    TionSensorDescription(
        key="outdoor_temperature",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: _temperature(state.outdoor_temperature),
    ),
    TionSensorDescription(
        key="supply_temperature",
        translation_key="supply_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda state: _temperature(state.current_temperature),
    ),
    TionSensorDescription(
        key="pcb_temperature",
        translation_key="pcb_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: _temperature(state.pcb_temperature),
    ),
    TionSensorDescription(
        key="filter_time",
        translation_key="filter_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.filter_time,
    ),
    TionSensorDescription(
        key="work_time",
        translation_key="work_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.work_time,
    ),
    TionSensorDescription(
        key="fan_time",
        translation_key="fan_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: state.fan_time,
    ),
    TionSensorDescription(
        key="airflow_volume",
        translation_key="airflow_volume",
        device_class=SensorDeviceClass.VOLUME,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=lambda state: state.airflow_volume,
    ),
    TionSensorDescription(
        key="heater_output",
        translation_key="heater_output",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:radiator",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda state: state.heater_output,
    ),
    TionSensorDescription(
        key="errors",
        translation_key="errors",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda state: f"0x{state.errors:08X}",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Tion Lite sensors."""
    async_add_entities(TionLiteSensor(entry, description) for description in SENSORS)


class TionLiteSensor(TionBleEntity, SensorEntity):
    """A sensor reported by Tion Lite."""

    entity_description: TionSensorDescription

    def __init__(
        self,
        entry: TionBleConfigEntry,
        description: TionSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | float | str | None:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
