"""Temporary BlueZ pairing agent for Tion Lite.

This module intentionally does not enable postponed annotations. The dbus-fast
service decorators read D-Bus signatures from annotations while the class is
created.
"""

# ruff: noqa: UP037

import asyncio
import logging
from typing import Any

try:
    from dbus_fast import BusType, Message, MessageType, Variant
    from dbus_fast.aio import MessageBus
    from dbus_fast.service import ServiceInterface, method
except ImportError:  # pragma: no cover - dependency is provided by Home Assistant
    BusType = Message = MessageType = MessageBus = Variant = None  # type: ignore[assignment,misc]
    ServiceInterface = object  # type: ignore[assignment,misc]
    method = None  # type: ignore[assignment]
    _DBUS_AVAILABLE = False
except AttributeError:  # pragma: no cover - dbus-fast is not usable on Windows
    BusType = Message = MessageType = MessageBus = Variant = None  # type: ignore[assignment,misc]
    ServiceInterface = object  # type: ignore[assignment,misc]
    method = None  # type: ignore[assignment]
    _DBUS_AVAILABLE = False
else:
    _DBUS_AVAILABLE = True

_LOGGER = logging.getLogger(__name__)

_AGENT_PATH = "/org/homeassistant/tion_ble/pairing_agent"
_AGENT_MANAGER_PATH = "/org/bluez"
_BLUEZ_SERVICE = "org.bluez"
_AGENT_MANAGER_INTERFACE = "org.bluez.AgentManager1"
_DEVICE_INTERFACE = "org.bluez.Device1"
_OBJECT_MANAGER_INTERFACE = "org.freedesktop.DBus.ObjectManager"
_PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"


class BlueZPairingUnavailable(Exception):
    """Raised when the selected device cannot be paired through local BlueZ."""


class BlueZPairingError(Exception):
    """Raised when BlueZ tried but could not pair the device."""


if _DBUS_AVAILABLE:

    class _JustWorksAgent(ServiceInterface):  # type: ignore[misc]
        """Accept BlueZ Just Works callbacks while the user pairs a breezer."""

        def __init__(self) -> None:
            super().__init__("org.bluez.Agent1")
            self.callbacks: list[str] = []

        def _record(self, callback: str, device: str | None = None) -> None:
            self.callbacks.append(callback)
            _LOGGER.debug(
                "BlueZ pairing agent callback %s%s",
                callback,
                f" for {device}" if device else "",
            )

        @method()  # type: ignore[misc]
        def Release(self) -> None:  # noqa: N802
            """Handle BlueZ releasing the agent."""
            self._record("Release")

        @method()  # type: ignore[misc]
        def RequestPinCode(  # noqa: N802
            self,
            device: "o",  # type: ignore[name-defined]  # noqa: F821
        ) -> "s":  # type: ignore[name-defined]  # noqa: F821
            """Return the neutral PIN if BlueZ unexpectedly requests one."""
            self._record("RequestPinCode", device)
            return "000000"

        @method()  # type: ignore[misc]
        def RequestPasskey(  # noqa: N802
            self,
            device: "o",  # type: ignore[name-defined]  # noqa: F821
        ) -> "u":  # type: ignore[name-defined]  # noqa: F821
            """Return the neutral passkey if BlueZ unexpectedly requests one."""
            self._record("RequestPasskey", device)
            return 0

        @method()  # type: ignore[misc]
        def DisplayPinCode(  # noqa: N802
            self,
            device: "o",  # type: ignore[name-defined]  # noqa: F821
            _pin_code: "s",  # type: ignore[name-defined]  # noqa: F821
        ) -> None:
            """Acknowledge a PIN display notification."""
            self._record("DisplayPinCode", device)

        @method()  # type: ignore[misc]
        def DisplayPasskey(  # noqa: N802
            self,
            device: "o",  # type: ignore[name-defined]  # noqa: F821
            _passkey: "u",  # type: ignore[name-defined]  # noqa: F821
            _entered: "q",  # type: ignore[name-defined]  # noqa: F821
        ) -> None:
            """Acknowledge a passkey display notification."""
            self._record("DisplayPasskey", device)

        @method()  # type: ignore[misc]
        def RequestConfirmation(  # noqa: N802
            self,
            device: "o",  # type: ignore[name-defined]  # noqa: F821
            _passkey: "u",  # type: ignore[name-defined]  # noqa: F821
        ) -> None:
            """Confirm Just Works or numeric comparison pairing."""
            self._record("RequestConfirmation", device)

        @method()  # type: ignore[misc]
        def RequestAuthorization(  # noqa: N802
            self,
            device: "o",  # type: ignore[name-defined]  # noqa: F821
        ) -> None:
            """Authorize the user-initiated pairing request."""
            self._record("RequestAuthorization", device)

        @method()  # type: ignore[misc]
        def AuthorizeService(  # noqa: N802
            self,
            device: "o",  # type: ignore[name-defined]  # noqa: F821
            _uuid: "s",  # type: ignore[name-defined]  # noqa: F821
        ) -> None:
            """Authorize the service exposed by the selected breezer."""
            self._record("AuthorizeService", device)

        @method()  # type: ignore[misc]
        def Cancel(self) -> None:  # noqa: N802
            """Record cancellation so it is visible in an error message."""
            self._record("Cancel")


async def async_pair_with_bluez(address: str, timeout: float) -> None:
    """Pair a locally visible device using a temporary NoInputNoOutput agent."""
    if not _DBUS_AVAILABLE:
        raise BlueZPairingUnavailable("dbus-fast is unavailable")

    bus: Any = None
    agent_exported = False
    agent_registered = False
    agent = _JustWorksAgent()

    try:
        try:
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        except Exception as err:
            raise BlueZPairingUnavailable(
                f"cannot access the BlueZ system bus: {_error_detail(err)}"
            ) from err

        device_path = await _find_device_path(bus, address)
        if device_path is None:
            raise BlueZPairingUnavailable(
                f"{address} is not present in the local BlueZ object tree"
            )

        if await _is_paired(bus, device_path):
            _LOGGER.debug("%s is already paired in BlueZ", address)
            return

        bus.export(_AGENT_PATH, agent)
        agent_exported = True
        register_reply = await bus.call(
            Message(
                destination=_BLUEZ_SERVICE,
                path=_AGENT_MANAGER_PATH,
                interface=_AGENT_MANAGER_INTERFACE,
                member="RegisterAgent",
                signature="os",
                body=[_AGENT_PATH, "NoInputNoOutput"],
            )
        )
        _raise_for_reply_error(register_reply, "registering the pairing agent")
        agent_registered = True

        _LOGGER.debug("Pairing %s through BlueZ with a temporary agent", address)
        try:
            async with asyncio.timeout(timeout):
                pair_reply = await bus.call(
                    Message(
                        destination=_BLUEZ_SERVICE,
                        path=device_path,
                        interface=_DEVICE_INTERFACE,
                        member="Pair",
                    )
                )
        except TimeoutError as err:
            raise BlueZPairingError(
                f"Device1.Pair timed out after {timeout:.0f} seconds; "
                f"agent callbacks: {_format_callbacks(agent.callbacks)}"
            ) from err

        if pair_reply.message_type == MessageType.ERROR:
            error_name = pair_reply.error_name or "unknown D-Bus error"
            if "AlreadyExists" not in error_name:
                raise BlueZPairingError(
                    f"{error_name}: {_reply_body(pair_reply)}; "
                    f"agent callbacks: {_format_callbacks(agent.callbacks)}"
                )

        await _async_trust_device(bus, device_path)
        _LOGGER.info(
            "%s paired successfully; BlueZ agent callbacks: %s",
            address,
            _format_callbacks(agent.callbacks),
        )
    finally:
        if bus is not None:
            if agent_registered:
                try:
                    await bus.call(
                        Message(
                            destination=_BLUEZ_SERVICE,
                            path=_AGENT_MANAGER_PATH,
                            interface=_AGENT_MANAGER_INTERFACE,
                            member="UnregisterAgent",
                            signature="o",
                            body=[_AGENT_PATH],
                        )
                    )
                except Exception:
                    _LOGGER.debug("Could not unregister pairing agent", exc_info=True)
            if agent_exported:
                try:
                    bus.unexport(_AGENT_PATH, agent)
                except Exception:
                    _LOGGER.debug("Could not unexport pairing agent", exc_info=True)
            bus.disconnect()


async def _find_device_path(bus: Any, address: str) -> str | None:
    """Find a BlueZ Device1 object by its advertised address."""
    reply = await bus.call(
        Message(
            destination=_BLUEZ_SERVICE,
            path="/",
            interface=_OBJECT_MANAGER_INTERFACE,
            member="GetManagedObjects",
        )
    )
    _raise_for_reply_error(reply, "reading BlueZ devices")

    expected = address.upper()
    managed_objects = reply.body[0] if reply.body else {}
    for path, interfaces in managed_objects.items():
        device = interfaces.get(_DEVICE_INTERFACE)
        if device is None:
            continue
        device_address = _variant_value(device.get("Address"))
        if isinstance(device_address, str) and device_address.upper() == expected:
            return str(path)
    return None


async def _is_paired(bus: Any, device_path: str) -> bool:
    """Return whether BlueZ has completed pairing for the device."""
    reply = await bus.call(
        Message(
            destination=_BLUEZ_SERVICE,
            path=device_path,
            interface=_PROPERTIES_INTERFACE,
            member="Get",
            signature="ss",
            body=[_DEVICE_INTERFACE, "Paired"],
        )
    )
    _raise_for_reply_error(reply, "reading the paired state")
    return bool(_variant_value(reply.body[0])) if reply.body else False


async def _async_trust_device(bus: Any, device_path: str) -> None:
    """Mark the newly paired breezer trusted for later GATT connections."""
    reply = await bus.call(
        Message(
            destination=_BLUEZ_SERVICE,
            path=device_path,
            interface=_PROPERTIES_INTERFACE,
            member="Set",
            signature="ssv",
            body=[_DEVICE_INTERFACE, "Trusted", Variant("b", True)],
        )
    )
    if reply.message_type == MessageType.ERROR:
        _LOGGER.debug(
            "BlueZ paired the breezer but could not mark it trusted: %s: %s",
            reply.error_name,
            _reply_body(reply),
        )


def _raise_for_reply_error(reply: Any, action: str) -> None:
    """Raise a readable error for a failed low-level D-Bus request."""
    if reply.message_type != MessageType.ERROR:
        return
    raise BlueZPairingError(
        f"BlueZ failed while {action}: {reply.error_name or 'unknown error'}: "
        f"{_reply_body(reply)}"
    )


def _variant_value(value: Any) -> Any:
    """Unwrap a D-Bus Variant while accepting plain values in tests."""
    return value.value if hasattr(value, "value") else value


def _reply_body(reply: Any) -> str:
    """Format a D-Bus reply body without leaking implementation details."""
    if not reply.body:
        return "no details"
    return "; ".join(str(_variant_value(item)) for item in reply.body)


def _format_callbacks(callbacks: list[str]) -> str:
    """Format callbacks for diagnostics shown by the config flow."""
    return ", ".join(callbacks) if callbacks else "none"


def _error_detail(err: Exception) -> str:
    """Return a non-empty exception description."""
    return str(err) or type(err).__name__
