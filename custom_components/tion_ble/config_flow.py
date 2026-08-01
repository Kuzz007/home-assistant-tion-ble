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
        """Confirm a discovered device and establish pairing."""
        assert self._address is not None
        assert self._title is not None
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await TionLiteClient(
                    self.hass, self._address, self._title
                ).async_setup()
            except TionBleError as err:
                _LOGGER.error(
                    "Unable to set up Tion Lite %s: %s",
                    self._address,
                    err,
                    exc_info=True,
                )
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception(
                    "Unexpected error while setting up Tion Lite %s: %s",
                    self._address,
                    err,
                )
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=self._title,
                    data={CONF_ADDRESS: self._address},
                )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            errors=errors,
            description_placeholders={"name": self._title},
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
