"""Base entity for Tion BLE."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import TionBleConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import TionBleCoordinator


class TionBleEntity(CoordinatorEntity[TionBleCoordinator]):
    """Base class for entities belonging to one Tion Lite."""

    _attr_has_entity_name = True

    def __init__(self, entry: TionBleConfigEntry, key: str) -> None:
        """Initialize the entity."""
        coordinator = entry.runtime_data.coordinator
        super().__init__(coordinator)
        address = format_mac(entry.runtime_data.client.address)
        self._attr_unique_id = f"{address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=entry.title,
            serial_number=address.upper(),
        )
