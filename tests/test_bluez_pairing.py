"""Tests for the temporary BlueZ pairing agent."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.tion_ble import bluez_pairing
from custom_components.tion_ble.bluez_pairing import (
    BlueZPairingError,
    async_pair_with_bluez,
)


class _FakeBus:
    """Return scripted BlueZ replies while recording the pairing sequence."""

    def __init__(self, pair_error: bool = False, already_paired: bool = False) -> None:
        self.pair_error = pair_error
        self.already_paired = already_paired
        self.calls = []
        self.exported_agent = None
        self.unexport = MagicMock()
        self.disconnected = False

    def export(self, _path, agent) -> None:
        self.exported_agent = agent

    async def call(self, message):
        self.calls.append(message)
        if message.member == "GetManagedObjects":
            return _reply(
                body=[
                    {
                        "/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF": {
                            "org.bluez.Device1": {
                                "Address": bluez_pairing.Variant(
                                    "s", "AA:BB:CC:DD:EE:FF"
                                )
                            }
                        }
                    }
                ]
            )
        if message.member == "Get":
            return _reply(body=[bluez_pairing.Variant("b", self.already_paired)])
        if message.member == "Pair" and self.pair_error:
            self.exported_agent.Cancel()
            return _reply(
                error="org.bluez.Error.AuthenticationFailed",
                body=["Authentication Failed"],
            )
        return _reply()

    def disconnect(self) -> None:
        self.disconnected = True


class _FakeBusFactory:
    """Mimic dbus-fast MessageBus(...).connect()."""

    def __init__(self, bus: _FakeBus) -> None:
        self._bus = bus

    async def connect(self) -> _FakeBus:
        return self._bus


def _reply(*, error: str | None = None, body: list | None = None):
    """Build the subset of a dbus-fast reply used by the integration."""
    message_type = (
        bluez_pairing.MessageType.ERROR
        if error
        else bluez_pairing.MessageType.METHOD_RETURN
    )
    return SimpleNamespace(
        message_type=message_type,
        error_name=error,
        body=[] if body is None else body,
    )


@pytest.fixture(autouse=True)
def require_dbus_fast() -> None:
    """These low-level tests require Home Assistant's dbus-fast dependency."""
    if not bluez_pairing._DBUS_AVAILABLE:
        pytest.skip("dbus-fast is not installed")


async def test_pair_registers_agent_on_same_bus_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Register, pair, trust, and unregister in the required BlueZ order."""
    bus = _FakeBus()
    monkeypatch.setattr(
        bluez_pairing,
        "MessageBus",
        lambda **_kwargs: _FakeBusFactory(bus),
    )

    await async_pair_with_bluez("AA:BB:CC:DD:EE:FF", 10.0)

    assert [message.member for message in bus.calls] == [
        "GetManagedObjects",
        "Get",
        "RegisterAgent",
        "Pair",
        "Set",
        "UnregisterAgent",
    ]
    register = bus.calls[2]
    assert register.body == [bluez_pairing._AGENT_PATH, "NoInputNoOutput"]
    assert bus.unexport.call_count == 1
    assert bus.disconnected is True


async def test_pair_error_reports_agent_callbacks_and_still_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose whether BlueZ reached the agent before authentication failed."""
    bus = _FakeBus(pair_error=True)
    monkeypatch.setattr(
        bluez_pairing,
        "MessageBus",
        lambda **_kwargs: _FakeBusFactory(bus),
    )

    with pytest.raises(
        BlueZPairingError,
        match=r"AuthenticationFailed.*agent callbacks: Cancel",
    ):
        await async_pair_with_bluez("AA:BB:CC:DD:EE:FF", 10.0)

    assert bus.calls[-1].member == "UnregisterAgent"
    assert bus.unexport.call_count == 1
    assert bus.disconnected is True


async def test_already_paired_device_needs_no_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep an existing bond and avoid registering another agent."""
    bus = _FakeBus(already_paired=True)
    monkeypatch.setattr(
        bluez_pairing,
        "MessageBus",
        lambda **_kwargs: _FakeBusFactory(bus),
    )

    await async_pair_with_bluez("AA:BB:CC:DD:EE:FF", 10.0)

    assert [message.member for message in bus.calls] == ["GetManagedObjects", "Get"]
    bus.unexport.assert_not_called()
    assert bus.disconnected is True
