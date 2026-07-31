"""Config flow for Tion BLE."""

from __future__ import annotations

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
                ).async_update(pair=True)
            except TionBleError:
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
        """Let the user select a discovered device or enter its MAC address."""
        if user_input is not None:
            address = format_mac(str(user_input[CONF_ADDRESS]).strip())
            if len(address) != 17 or address.count(":") != 5:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._user_schema(),
                    errors={CONF_ADDRESS: "invalid_address"},
                )

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._address = address
            discovery = self._discovered.get(address)
            self._title = _device_title(
                address, discovery.name if discovery is not None else None
            )
            return await self.async_step_bluetooth_confirm()

        await bluetooth.async_request_active_scan(self.hass)
        configured_addresses = self._async_current_ids(include_ignore=False)
        for discovery_info in async_discovered_service_info(self.hass):
            address = format_mac(discovery_info.address)
            service_uuids = {uuid.lower() for uuid in discovery_info.service_uuids}
            if address in configured_addresses or SERVICE_UUID not in service_uuids:
                continue
            self._discovered[address] = discovery_info

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(),
        )

    def _user_schema(self) -> vol.Schema:
        """Return the user-step schema."""
        if self._discovered:
            return vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: _device_title(address, info.name)
                            for address, info in self._discovered.items()
                        }
                    )
                }
            )
        return vol.Schema(
            {
                vol.Required(CONF_ADDRESS): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
                )
            }
        )
