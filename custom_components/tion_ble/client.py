"""Bluetooth client for Tion Lite."""

from __future__ import annotations

import asyncio
import logging
import struct

from bleak.backends.device import BLEDevice
from bleak_retry_connector import (
    BLEAK_RETRY_EXCEPTIONS,
    BleakClientWithServiceCache,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .bluez_pairing import (
    BlueZPairingError,
    BlueZPairingUnavailable,
    async_pair_with_bluez,
)
from .const import (
    NOTIFY_CHARACTERISTIC_UUID,
    PAIRING_SETTLE_DELAY,
    PAIRING_TIMEOUT,
    RESPONSE_TIMEOUT,
    TRANSACTION_TIMEOUT,
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
        """Pair first, let the breezer settle, then read its state."""
        await self._async_pair()
        await asyncio.sleep(PAIRING_SETTLE_DELAY)
        return await self.async_update()

    async def async_update(self) -> TionLiteState:
        """Read the current state."""
        request_id = self._next_request_id()
        response = await self._async_exchange(
            build_frame(
                FRAME_TYPE_STATE_REQUEST,
                struct.pack("<I", request_id),
            ),
            FRAME_TYPE_STATE_RESPONSE,
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
        request_id = self._next_request_id()
        desired = current.updated(**changes)
        payload = build_state_set_payload(desired, request_id=request_id)
        response = await self._async_exchange(
            build_frame(FRAME_TYPE_STATE_SET, payload),
            FRAME_TYPE_STATE_RESPONSE,
        )
        try:
            return parse_state_response(response.payload)
        except TionProtocolError as err:
            raise TionBleConnectionError(str(err)) from err

    def _next_request_id(self) -> int:
        """Return a non-zero request identifier used by the Lite protocol."""
        self._request_id = (self._request_id + 1) & 0xFFFFFFFF
        if self._request_id == 0:
            self._request_id = 1
        return self._request_id

    def _ble_device(self) -> BLEDevice:
        """Return the currently visible connectable BLE device."""
        lookup_address = self.address.upper() if ":" in self.address else self.address
        ble_device = bluetooth.async_ble_device_from_address(
            self._hass, lookup_address, connectable=True
        )
        if ble_device is None:
            raise TionBleDeviceNotFound(
                f"Tion Lite {self.address} is not visible over Bluetooth"
            )
        return ble_device

    async def _async_pair(self) -> None:
        """Pair through a local BlueZ agent, falling back for proxy adapters."""
        ble_device = self._ble_device()
        try:
            await async_pair_with_bluez(self.address, PAIRING_TIMEOUT)
            return
        except BlueZPairingUnavailable as err:
            _LOGGER.debug(
                "%s: direct BlueZ pairing is unavailable (%s); using Bleak",
                self.address,
                err,
            )
        except BlueZPairingError as err:
            raise TionBleConnectionError(f"BlueZ pairing failed: {err}") from err

        await self._async_pair_with_bleak(ble_device)

    async def _async_pair_with_bleak(self, ble_device: BLEDevice) -> None:
        """Pair through Bleak when the device is provided by a remote scanner."""
        client: BleakClientWithServiceCache | None = None
        operation = "pairing"
        try:
            async with asyncio.timeout(PAIRING_TIMEOUT):
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    max_attempts=3,
                    pair=True,
                )
        except TimeoutError as err:
            raise TionBleConnectionError(
                f"Tion Lite {self.address} did not finish OS pairing within "
                f"{PAIRING_TIMEOUT:.0f} seconds"
            ) from err
        except BLEAK_RETRY_EXCEPTIONS as err:
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
                        "%s: error while disconnecting after Bluetooth pairing",
                        self.address,
                        exc_info=True,
                    )

    async def _async_exchange(
        self,
        request: bytes,
        expected_frame_type: int,
    ):
        """Send one request and wait for its complete response."""
        ble_device = self._ble_device()

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
            async with asyncio.timeout(TRANSACTION_TIMEOUT):
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.name,
                    max_attempts=3,
                    pair=False,
                )
                operation = "enabling notifications"
                await client.start_notify(
                    NOTIFY_CHARACTERISTIC_UUID, _notification_handler
                )
                operation = "writing request"
                for packet in fragment_frame(request):
                    await client.write_gatt_char(
                        WRITE_CHARACTERISTIC_UUID, packet, response=False
                    )
                operation = "waiting for response"
                async with asyncio.timeout(RESPONSE_TIMEOUT):
                    return await response_future
        except TimeoutError as err:
            raise TionBleConnectionError(
                f"Tion Lite {self.address}: {operation} timed out"
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
