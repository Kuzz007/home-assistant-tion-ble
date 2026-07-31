"""Tion Lite BLE protocol codec."""

from __future__ import annotations

import struct
from dataclasses import dataclass, replace
from typing import Final

FRAME_MAGIC: Final = 0x3A
FRAME_RANDOM: Final = 0xAD
FRAME_TYPE_STATE_SET: Final = 0x1230
FRAME_TYPE_STATE_RESPONSE: Final = 0x1231
FRAME_TYPE_STATE_REQUEST: Final = 0x1232
FRAME_TYPE_DEVICE_INFO_REQUEST: Final = 0x4009
FRAME_TYPE_DEVICE_INFO_RESPONSE: Final = 0x400A

PACKET_FIRST: Final = 0x00
PACKET_CURRENT: Final = 0x40
PACKET_LONE: Final = 0x80
PACKET_LAST: Final = 0xC0
PACKET_DATA_SIZE: Final = 19

STATE_SIZE: Final = 57
STATE_RESPONSE_SIZE: Final = 4 + STATE_SIZE
STATE_SET_SIZE: Final = 4 + 14


class TionProtocolError(ValueError):
    """Raised when a Tion BLE frame is invalid."""


@dataclass(frozen=True, slots=True)
class TionFrame:
    """Decoded Tion BLE frame."""

    frame_type: int
    ble_request_id: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class TionLiteState:
    """Decoded state of a Tion Lite."""

    power: bool
    sound: bool
    led: bool
    filter_required: bool
    auto: bool
    heater: bool
    heater_present: bool
    kiv_present: bool
    kiv_active: bool
    gate: int
    target_temperature: int
    fan_speed: int
    outdoor_temperature: int
    current_temperature: int
    pcb_temperature: int
    work_time: int
    fan_time: int
    filter_time: int
    airflow_counter: int
    errors: int
    error_counts: bytes
    button_temperatures: tuple[int, int, int]
    button_fan_speeds: tuple[int, int, int]
    max_fan_speed: int
    heater_output: int
    test_type: int

    def updated(self, **changes: object) -> TionLiteState:
        """Return a copy with the requested changes."""
        return replace(self, **changes)

    @property
    def airflow_volume(self) -> float:
        """Return total supplied air volume in cubic metres."""
        return self.airflow_counter * 10 / 3600


@dataclass(frozen=True, slots=True)
class TionLiteDeviceInfo:
    """Decoded Tion Lite firmware information."""

    work_mode: int
    device_type: int
    firmware: int
    hardware: int


def crc16_ccitt_false(data: bytes, initial: int = 0xFFFF) -> int:
    """Calculate CRC-16/CCITT-FALSE."""
    crc = initial
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else crc << 1
    return crc & 0xFFFF


def build_frame(
    frame_type: int, payload: bytes = b"", ble_request_id: int = 1
) -> bytes:
    """Build a complete Tion Lite frame."""
    frame_size = 10 + len(payload) + 2
    frame_without_crc = struct.pack(
        "<HBBHI", frame_size, FRAME_MAGIC, FRAME_RANDOM, frame_type, ble_request_id
    ) + bytes(payload)
    checksum = crc16_ccitt_false(frame_without_crc)
    return frame_without_crc + struct.pack(">H", checksum)


def parse_frame(data: bytes) -> TionFrame:
    """Validate and decode a complete Tion Lite frame."""
    if len(data) < 12:
        raise TionProtocolError("Frame is too short")

    frame_size, magic, _random, frame_type, ble_request_id = struct.unpack_from(
        "<HBBHI", data
    )
    if frame_size != len(data):
        raise TionProtocolError(
            f"Invalid frame size: header says {frame_size}, received {len(data)}"
        )
    if magic != FRAME_MAGIC:
        raise TionProtocolError(f"Invalid frame magic: 0x{magic:02X}")
    if crc16_ccitt_false(data) != 0:
        raise TionProtocolError("Invalid frame checksum")

    return TionFrame(frame_type, ble_request_id, data[10:-2])


def fragment_frame(frame: bytes) -> list[bytes]:
    """Split a frame into 20-byte GATT packets."""
    chunks = [
        frame[offset : offset + PACKET_DATA_SIZE]
        for offset in range(0, len(frame), PACKET_DATA_SIZE)
    ]
    if len(chunks) == 1:
        return [bytes((PACKET_LONE,)) + chunks[0]]

    packets: list[bytes] = []
    for index, chunk in enumerate(chunks):
        if index == 0:
            packet_type = PACKET_FIRST
        elif index == len(chunks) - 1:
            packet_type = PACKET_LAST
        else:
            packet_type = PACKET_CURRENT
        packets.append(bytes((packet_type,)) + chunk)
    return packets


class FrameAssembler:
    """Reassemble Tion frames from GATT notifications."""

    def __init__(self) -> None:
        """Initialize an empty assembler."""
        self._buffer = bytearray()

    def feed(self, packet: bytes) -> bytes | None:
        """Add one GATT packet and return a complete frame when available."""
        if not packet:
            raise TionProtocolError("Empty BLE packet")

        packet_type = packet[0]
        payload = packet[1:]
        if packet_type == PACKET_LONE:
            self._buffer.clear()
            return bytes(payload)
        if packet_type == PACKET_FIRST:
            self._buffer = bytearray(payload)
            return None
        if packet_type == PACKET_CURRENT:
            if not self._buffer:
                raise TionProtocolError("Continuation packet without first packet")
            self._buffer.extend(payload)
            return None
        if packet_type == PACKET_LAST:
            if not self._buffer:
                raise TionProtocolError("Last packet without first packet")
            self._buffer.extend(payload)
            frame = bytes(self._buffer)
            self._buffer.clear()
            return frame
        raise TionProtocolError(f"Unknown BLE packet type: 0x{packet_type:02X}")


def parse_state_response(payload: bytes) -> TionLiteState:
    """Decode a state response payload."""
    if len(payload) < STATE_RESPONSE_SIZE:
        raise TionProtocolError(f"State response is too short: {len(payload)} bytes")

    state = payload[4 : 4 + STATE_SIZE]
    flags = state[0]
    extra_flags = state[1]
    counters = struct.unpack_from("<IIII", state, 8)
    button_temperatures = struct.unpack_from("<bbb", state, 48)
    button_fan_speeds = tuple(state[51:54])

    return TionLiteState(
        power=bool(flags & 0x01),
        sound=bool(flags & 0x02),
        led=bool(flags & 0x04),
        filter_required=bool(flags & 0x10),
        auto=bool(flags & 0x20),
        heater=bool(flags & 0x40),
        heater_present=bool(flags & 0x80),
        kiv_present=bool(extra_flags & 0x01),
        kiv_active=bool(extra_flags & 0x02),
        gate=state[2],
        target_temperature=struct.unpack_from("<b", state, 3)[0],
        fan_speed=state[4],
        outdoor_temperature=struct.unpack_from("<b", state, 5)[0],
        current_temperature=struct.unpack_from("<b", state, 6)[0],
        pcb_temperature=struct.unpack_from("<b", state, 7)[0],
        work_time=counters[0],
        fan_time=counters[1],
        filter_time=counters[2],
        airflow_counter=counters[3],
        errors=struct.unpack_from("<I", state, 24)[0],
        error_counts=bytes(state[28:48]),
        button_temperatures=button_temperatures,
        button_fan_speeds=button_fan_speeds,
        max_fan_speed=state[54],
        heater_output=state[55],
        test_type=state[56],
    )


def build_state_set_payload(
    state: TionLiteState,
    *,
    request_id: int,
    filter_reset: bool = False,
) -> bytes:
    """Build a state-set payload while preserving all current settings."""
    flags = (
        int(state.power)
        | (int(state.sound) << 1)
        | (int(state.led) << 2)
        | (int(state.auto) << 3)
        | (int(state.heater) << 4)
    )
    reset_flags = int(filter_reset)
    temperatures = state.button_temperatures or (10, 20, 25)
    fan_speeds = state.button_fan_speeds or (2, 4, 6)
    filter_days = 181 if filter_reset else 0

    data = struct.pack(
        "<BBBbBbbbBBBH B",
        flags,
        reset_flags,
        2,
        state.target_temperature,
        state.fan_speed,
        *temperatures,
        *fan_speeds,
        filter_days,
        0,
    )
    if len(data) != 14:
        raise AssertionError(f"Unexpected state-set size: {len(data)}")
    return struct.pack("<I", request_id) + data


def parse_device_info(payload: bytes) -> TionLiteDeviceInfo:
    """Decode a device information response payload."""
    if len(payload) < 9:
        raise TionProtocolError("Device information response is too short")
    work_mode, device_type, firmware, hardware = struct.unpack_from("<BIHH", payload)
    return TionLiteDeviceInfo(work_mode, device_type, firmware, hardware)
