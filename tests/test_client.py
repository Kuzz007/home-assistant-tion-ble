"""Tests for Tion Lite connection setup."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.tion_ble import client as client_module
from custom_components.tion_ble.client import (
    TionBleConnectionError,
    TionBleDeviceNotFound,
    TionLiteClient,
)
from custom_components.tion_ble.protocol import (
    FRAME_TYPE_STATE_REQUEST,
    FRAME_TYPE_STATE_RESPONSE,
    build_frame,
    fragment_frame,
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


async def test_exchange_uses_write_with_response(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tion's write characteristic requires an acknowledged GATT write."""
    notification_handler = None
    response_frame = build_frame(FRAME_TYPE_STATE_RESPONSE)
    bleak_client = MagicMock(is_connected=True)

    async def start_notify(_uuid: str, handler) -> None:
        nonlocal notification_handler
        notification_handler = handler

    async def write_gatt_char(_uuid: str, _packet: bytes, *, response: bool) -> None:
        assert response is True
        assert notification_handler is not None
        for response_packet in fragment_frame(response_frame):
            notification_handler(None, bytearray(response_packet))

    bleak_client.start_notify = AsyncMock(side_effect=start_notify)
    bleak_client.write_gatt_char = AsyncMock(side_effect=write_gatt_char)
    bleak_client.disconnect = AsyncMock()

    monkeypatch.setattr(
        client_module.bluetooth,
        "async_ble_device_from_address",
        lambda *_args, **_kwargs: object(),
        raising=False,
    )
    monkeypatch.setattr(
        client_module,
        "establish_connection",
        AsyncMock(return_value=bleak_client),
    )

    result = await client._async_exchange(
        build_frame(FRAME_TYPE_STATE_REQUEST), FRAME_TYPE_STATE_RESPONSE
    )

    assert result.frame_type == FRAME_TYPE_STATE_RESPONSE
    bleak_client.disconnect.assert_awaited_once()
