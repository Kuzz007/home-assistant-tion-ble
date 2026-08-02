"""Config flow for Tion BLE."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, override

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac

from .client import TionBleError, TionLiteClient
from .const import DOMAIN, SERVICE_UUID
from .discovery import device_label, matches_tion_lite

_LOGGER = logging.getLogger(__name__)
SCAN_DURATION = 10.0


def _device_title(address: str, advertised_name: str | None = None) -> str:
    """Build a readable title for a Tion Lite."""
    if advertised_name and advertised_name != address:
        return advertised_name
    return f"Tion Lite {address[-5:].replace(':', '')}"


class TionBleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tion BLE."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._address: str | None = None
        self._connect_error: str | None = None
        self._connect_succeeded = False
        self._connect_task: asyncio.Task[None] | None = None
        self._title: str | None = None
        self._discovered: dict[str, BluetoothServiceInfoBleak] = {}
        self._scan_task: asyncio.Task[None] | None = None

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle Bluetooth discovery."""
        address = format_mac(discovery_info.address)
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        self._address = address
        self._title = _device_title(address, discovery_info.name)
        self.context["title_placeholders"] = {"name": self._title}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered device before starting the connection task."""
        assert self._address is not None
        assert self._title is not None

        if user_input is not None:
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._title},
        )

    async def async_step_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect in the background so the config-flow request cannot time out."""
        assert self._address is not None
        assert self._title is not None

        if self._connect_task is None:
            self._connect_error = None
            self._connect_succeeded = False
            self._connect_task = self.hass.async_create_task(
                self._async_connect(),
                f"Connect Tion Lite {self._address}",
                eager_start=False,
            )

        if not self._connect_task.done():
            return self.async_show_progress(
                step_id="connect",
                progress_action="connecting",
                progress_task=self._connect_task,
            )

        self._connect_task.result()
        self._connect_task = None
        return self.async_show_progress_done(next_step_id="connect_result")

    async def _async_connect(self) -> None:
        """Validate the initial connection and retain a user-visible result."""
        assert self._address is not None
        assert self._title is not None
        try:
            await TionLiteClient(self.hass, self._address, self._title).async_setup()
        except TionBleError as err:
            self._connect_error = str(err) or type(err).__name__
            _LOGGER.error(
                "Unable to set up Tion Lite %s: %s",
                self._address,
                err,
                exc_info=True,
            )
        except Exception as err:
            self._connect_error = f"{type(err).__name__}: {err}"
            _LOGGER.exception(
                "Unexpected error while setting up Tion Lite %s: %s",
                self._address,
                err,
            )
        else:
            self._connect_succeeded = True

    async def async_step_connect_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry or show the exact connection error."""
        assert self._address is not None
        assert self._title is not None

        if not self._connect_succeeded:
            if self._connect_error is None:
                self._connect_error = "Connection task finished without a result"
            return await self.async_step_connection_error()

        return self.async_create_entry(
            title=self._title,
            data={CONF_ADDRESS: self._address},
        )

    async def async_step_connection_error(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show an actionable error without relying on Home Assistant logs."""
        return self.async_show_menu(
            step_id="connection_error",
            menu_options=["connect", "scan"],
            description_placeholders={
                "error": self._connect_error or "Unknown Bluetooth error"
            },
        )

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start an active Bluetooth scan."""
        return await self.async_step_scan()

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Scan for nearby Tion Lite devices and show progress."""
        if self._scan_task is None:
            self._discovered.clear()
            self._scan_task = self.hass.async_create_task(
                self._async_scan(), eager_start=False
            )

        if not self._scan_task.done():
            return self.async_show_progress(
                step_id="scan",
                progress_action="scanning",
                progress_task=self._scan_task,
            )

        self._scan_task = None
        return self.async_show_progress_done(
            next_step_id="scan_result" if self._discovered else "no_devices"
        )

    async def _async_scan(self) -> None:
        """Run an active scan and collect likely Tion Lite devices."""
        await bluetooth.async_request_active_scan(self.hass, SCAN_DURATION)

        configured_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass):
            address = format_mac(discovery_info.address)
            if address in configured_addresses or not matches_tion_lite(
                discovery_info.name, discovery_info.service_uuids, SERVICE_UUID
            ):
                continue
            self._discovered[address] = discovery_info

    async def async_step_scan_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show actions after one or more Tion Lite devices were found."""
        return self.async_show_menu(
            step_id="scan_result",
            menu_options=["select", "scan", "manual"],
            description_placeholders={"count": str(len(self._discovered))},
        )

    async def async_step_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain that scanning did not find a supported device."""
        return self.async_show_menu(
            step_id="no_devices",
            menu_options=["scan", "manual"],
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user select a discovered Tion Lite."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._address = address
            discovery = self._discovered[address]
            self._title = _device_title(address, discovery.name)
            return await self.async_step_bluetooth_confirm()

        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: device_label(
                                address, info.name, info.rssi, _device_title
                            )
                            for address, info in sorted(
                                self._discovered.items(),
                                key=lambda item: item[1].rssi,
                                reverse=True,
                            )
                        }
                    )
                }
            ),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user enter a Tion Lite MAC address manually."""
        errors: dict[str, str] = {}
        if user_input is not None:
            address = format_mac(str(user_input[CONF_ADDRESS]).strip())
            if len(address) == 17 and address.count(":") == 5:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                self._address = address
                discovery = self._discovered.get(address)
                self._title = _device_title(
                    address, discovery.name if discovery is not None else None
                )
                return await self.async_step_bluetooth_confirm()
            errors[CONF_ADDRESS] = "invalid_address"

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                    )
                }
            ),
            errors=errors,
        )
