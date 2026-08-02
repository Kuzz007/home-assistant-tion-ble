"""Tests for Tion Lite connection setup."""

import asyncio
import struct
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
    parse_frame,
)


@pytest.fixture
def client() -> TionLiteClient:
    """Create a client without requiring a running Home Assistant instance."""
    return TionLiteClient(object(), "AA:BB:CC:DD:EE:FF", "Tion Lite")


async def test_setup_pairs_then_waits_and_reads_state(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pair in a separate connection before reading the state."""
    state = object()
    calls = MagicMock()
    pair = AsyncMock()
    sleep = AsyncMock()
    update = AsyncMock(return_value=state)
    calls.attach_mock(pair, "pair")
    calls.attach_mock(sleep, "sleep")
    calls.attach_mock(update, "update")
    monkeypatch.setattr(client, "_async_pair", pair)
    monkeypatch.setattr(client_module.asyncio, "sleep", sleep)
    monkeypatch.setattr(client, "async_update", update)

    assert await client.async_setup() is state
    assert calls.mock_calls == [call.pair(), call.sleep(3.0), call.update()]


async def test_setup_stops_when_pairing_fails(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not send protocol data after a pairing failure."""
    pair = AsyncMock(side_effect=TionBleConnectionError("not authorized"))
    update = AsyncMock()
    monkeypatch.setattr(client, "_async_pair", pair)
    monkeypatch.setattr(client, "async_update", update)

    with pytest.raises(TionBleConnectionError, match="not authorized"):
        await client.async_setup()

    update.assert_not_awaited()


async def test_pair_uses_own_connection_and_disconnects(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pair without notifications and close the pairing connection."""
    ble_device = object()
    bleak_client = MagicMock(is_connected=True)
    bleak_client.pair = AsyncMock()
    bleak_client.disconnect = AsyncMock()
    establish = AsyncMock(return_value=bleak_client)
    monkeypatch.setattr(client, "_ble_device", lambda: ble_device)
    monkeypatch.setattr(client_module, "establish_connection", establish)

    await client._async_pair()

    assert establish.await_args.kwargs["pair"] is False
    assert establish.await_args.kwargs["max_attempts"] == 3
    bleak_client.pair.assert_awaited_once_with()
    bleak_client.disconnect.assert_awaited_once_with()


async def test_pair_does_not_connect_when_device_is_not_visible(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pairing cannot start when no scanner currently sees the device."""
    monkeypatch.setattr(
        client,
        "_ble_device",
        MagicMock(side_effect=TionBleDeviceNotFound("not visible")),
    )
    establish = AsyncMock()
    monkeypatch.setattr(client_module, "establish_connection", establish)

    with pytest.raises(TionBleDeviceNotFound):
        await client._async_pair()

    establish.assert_not_awaited()


async def test_update_sends_four_byte_protocol_request_id(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Match the state request emitted by the Tion Remote protocol."""
    response = parse_frame(build_frame(FRAME_TYPE_STATE_RESPONSE, bytes(4 + 57)))
    exchange = AsyncMock(return_value=response)
    monkeypatch.setattr(client, "_async_exchange", exchange)

    await client.async_update()

    request = parse_frame(exchange.await_args.args[0])
    assert request.frame_type == FRAME_TYPE_STATE_REQUEST
    assert request.payload == struct.pack("<I", 1)


async def test_exchange_uses_write_without_response(
    client: TionLiteClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tion Lite expects unacknowledged GATT writes and replies by notification."""
    client._hass = MagicMock(loop=asyncio.get_running_loop())
    notification_handler = None
    response_frame = build_frame(FRAME_TYPE_STATE_RESPONSE)
    bleak_client = MagicMock(is_connected=True)

    async def start_notify(_uuid: str, handler) -> None:
        nonlocal notification_handler
        notification_handler = handler

    async def write_gatt_char(_uuid: str, _packet: bytes, *, response: bool) -> None:
        assert response is False
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
    assert client_module.establish_connection.await_args.kwargs["pair"] is False
    bleak_client.disconnect.assert_awaited_once()
