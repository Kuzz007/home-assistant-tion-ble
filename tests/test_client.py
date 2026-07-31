"""Tests for Tion Lite connection setup."""

from unittest.mock import AsyncMock, call

import pytest

from custom_components.tion_ble.client import (
    TionBleConnectionError,
    TionBleDeviceNotFound,
    TionLiteClient,
)


@pytest.fixture
def client() -> TionLiteClient:
    """Create a client without requiring a running Home Assistant instance."""
    return TionLiteClient(object(), "AA:BB:CC:DD:EE:FF", "Tion Lite")


async def test_setup_connects_without_pairing_first(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not request an OS-level bond when a regular GATT connection works."""
    state = object()
    update = AsyncMock(return_value=state)
    monkeypatch.setattr(client, "async_update", update)

    assert await client.async_setup() is state
    update.assert_awaited_once_with(pair=False)


async def test_setup_retries_with_pairing(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fall back to OS-level pairing after a regular connection failure."""
    state = object()
    update = AsyncMock(side_effect=[TionBleConnectionError("not authorized"), state])
    monkeypatch.setattr(client, "async_update", update)

    assert await client.async_setup() is state
    assert update.await_args_list == [call(pair=False), call(pair=True)]


async def test_setup_does_not_pair_when_device_is_not_visible(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pairing cannot help when no scanner currently sees the device."""
    update = AsyncMock(side_effect=TionBleDeviceNotFound("not visible"))
    monkeypatch.setattr(client, "async_update", update)

    with pytest.raises(TionBleDeviceNotFound):
        await client.async_setup()

    update.assert_awaited_once_with(pair=False)
