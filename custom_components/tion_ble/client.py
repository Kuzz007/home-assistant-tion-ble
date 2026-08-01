"""Bluetooth client for Tion Lite."""

from __future__ import annotations

import asyncio
import logging

from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .const import (
    NOTIFY_CHARACTERISTIC_UUID,
    RESPONSE_TIMEOUT,
    WRITE_CHARACTERISTIC_UUID,
)
from .protocol import (
    FRAME_TYPE_STATE_REQUEST,
    FRAME_TYPE_STATE_RESPONSE,
    FRAME_TYPE_STATE_SET,
    FrameAssembler,
    TionLiteState,
    TionProtocolError,
    build_frame,
    build_state_set_payload,
    fragment_frame,
    parse_frame,
    parse_state_response,
)

_LOGGER = logging.getLogger(__name__)


class TionBleError(Exception):
    """Base error for Tion BLE communication."""


class TionBleDeviceNotFound(TionBleError):
    """Raised when Home Assistant cannot currently see the device."""


class TionBleConnectionError(TionBleError):
    """Raised when a Bluetooth transaction fails."""


class TionLiteClient:
    """Perform short-lived transactions with one Tion Lite."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        """Initialize the client."""
        self._hass = hass
        self.address = address
        self.name = name
        self._request_id = 0

    async def async_setup(self) -> TionLiteState:
        """Read state, falling back to OS-level pairing only when required."""
        try:
            return await self.async_update(pair=False)
        except TionBleDeviceNotFound:
            raise
        except TionBleConnectionError as err:
            _LOGGER.warning(
                "%s: connection without OS-level pairing failed: %s; "
                "retrying with pairing",
                self.address,
                err,
            )

        return await self.async_update(pair=True)

    async def async_update(self, *, pair: bool = False) -> TionLiteState:
        """Read the current state."""
        response = await self._async_exchange(
            build_frame(FRAME_TYPE_STATE_REQUEST),
            FRAME_TYPE_STATE_RESPONSE,
            pair=pair,
        )
        try:
            return parse_state_response(response.payload)
        except TionProtocolError as err:
            raise TionBleConnectionError(str(err)) from err

    async def async_set_state(
        self,
        current: TionLiteState,
        **changes: object,
    ) -> TionLiteState:
        """Change state and return the state reported by the breezer."""
        self._request_id = (self._request_id + 1) & 0xFFFFFFFF
        desired = current.updated(**changes)
        payload = build_state_set_payload(desired, request_id=self._request_id)
        response = await self._async_exchange(
            build_frame(FRAME_TYPE_STATE_SET, payload),
            FRAME_TYPE_STATE_RESPONSE,
        )
        try:
            return parse_state_response(response.payload)
        except TionProtocolError as err:
            raise TionBleConnectionError(str(err)) from err

    async def _async_exchange(
        self,
        request: bytes,
        expected_frame_type: int,
        *,
        pair: bool = False,
    ):
        """Send one request and wait for its complete response."""
        lookup_address = self.address.upper() if ":" in self.address else self.address
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, lookup_address, connectable=True
        )
        if ble_device is None:
            raise TionBleDeviceNotFound(
                f"Tion Lite {self.address} is not visible over Bluetooth"
            )

        assembler = FrameAssembler()
        response_future = self._hass.loop.create_future()

        def _notification_handler(_sender, data: bytearray) -> None:
            if response_future.done():
                return
            try:
                complete = assembler.feed(bytes(data))
                if complete is None:
                    return
                frame = parse_frame(complete)
                if frame.frame_type == expected_frame_type:
                    response_future.set_result(frame)
                else:
                    _LOGGER.debug(
                        "%s: ignoring frame type 0x%04X while waiting for 0x%04X",
                        self.address,
                        frame.frame_type,
                        expected_frame_type,
                    )
            except TionProtocolError as err:
                response_future.set_exception(err)

        client: BleakClientWithServiceCache | None = None
        operation = "connecting"
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                max_attempts=3,
                pair=pair,
            )
            operation = "enabling notifications"
            await client.start_notify(NOTIFY_CHARACTERISTIC_UUID, _notification_handler)
            operation = "writing request"
            for packet in fragment_frame(request):
                await client.write_gatt_char(
                    WRITE_CHARACTERISTIC_UUID, packet, response=True
                )
            operation = "waiting for response"
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                return await response_future
        except TimeoutError as err:
            raise TionBleConnectionError(
                f"Tion Lite {self.address} did not answer the state request "
                f"(OS pairing: {'on' if pair else 'off'})"
            ) from err
        except (TionProtocolError, *BLEAK_RETRY_EXCEPTIONS) as err:
            detail = str(err) or type(err).__name__
            raise TionBleConnectionError(f"{operation} failed: {detail}") from err
        except Exception as err:
            detail = str(err) or type(err).__name__
            raise TionBleConnectionError(
                f"Unexpected error while {operation}: {type(err).__name__}: {detail}"
            ) from err
        finally:
            if client is not None and client.is_connected:
                try:
                    await client.disconnect()
                except Exception:
                    _LOGGER.warning(
                        "%s: error while disconnecting after Bluetooth transaction",
                        self.address,
                        exc_info=True,
                    )
