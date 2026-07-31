"""Data coordinator for Tion BLE."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .client import TionBleError, TionLiteClient
from .const import DOMAIN, UPDATE_INTERVAL
from .protocol import TionLiteState

_LOGGER = logging.getLogger(__name__)


class TionBleCoordinator(DataUpdateCoordinator[TionLiteState]):
    """Coordinate polling and serialized commands for one Tion Lite."""

    def __init__(self, hass: HomeAssistant, client: TionLiteClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{client.address}",
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client
        self._command_lock = asyncio.Lock()

    async def _async_update_data(self) -> TionLiteState:
        try:
            return await self.client.async_update()
        except TionBleError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set_state(self, **changes: object) -> None:
        """Send state changes and immediately publish the response."""
        async with self._command_lock:
            if self.data is None:
                await self.async_request_refresh()
            try:
                state = await self.client.async_set_state(self.data, **changes)
            except TionBleError as err:
                raise UpdateFailed(str(err)) from err
            self.async_set_updated_data(state)
