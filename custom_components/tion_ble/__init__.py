"""Tion Lite local Bluetooth integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .client import TionLiteClient
from .const import PLATFORMS
from .coordinator import TionBleCoordinator


@dataclass(slots=True)
class TionBleRuntimeData:
    """Runtime data for a Tion BLE config entry."""

    client: TionLiteClient
    coordinator: TionBleCoordinator


type TionBleConfigEntry = ConfigEntry[TionBleRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
) -> bool:
    """Set up Tion BLE from a config entry."""
    client = TionLiteClient(hass, entry.data[CONF_ADDRESS], entry.title)
    coordinator = TionBleCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = TionBleRuntimeData(client, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: TionBleConfigEntry,
) -> bool:
    """Unload a Tion BLE config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
