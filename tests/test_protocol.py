"""Tests for the Tion Lite BLE protocol."""

import struct

import pytest

from custom_components.tion_ble.protocol import (
    FRAME_TYPE_STATE_REQUEST,
    FrameAssembler,
    TionProtocolError,
    build_frame,
    build_state_set_payload,
    crc16_ccitt_false,
    fragment_frame,
    parse_frame,
    parse_state_response,
)


def _state_payload() -> bytes:
    state = bytearray(57)
    state[0] = 0xD7
    state[1] = 0x03
    state[2] = 2
    struct.pack_into("<b", state, 3, 20)
    state[4] = 4
    struct.pack_into("<bbb", state, 5, -15, 22, 40)
    struct.pack_into("<IIII", state, 8, 3600, 1800, 86400, 720)
    struct.pack_into("<I", state, 24, 0x01020304)
    state[28:48] = bytes(range(20))
    struct.pack_into("<bbb", state, 48, 10, 20, 25)
    state[51:54] = bytes((2, 4, 6))
    state[54] = 6
    state[55] = 50
    state[56] = 7
    return struct.pack("<I", 123) + state


def test_crc_known_vector() -> None:
    assert crc16_ccitt_false(b"123456789") == 0x29B1


def test_frame_round_trip_and_checksum() -> None:
    raw = build_frame(FRAME_TYPE_STATE_REQUEST, b"test", ble_request_id=9)

    assert crc16_ccitt_false(raw) == 0
    frame = parse_frame(raw)
    assert frame.frame_type == FRAME_TYPE_STATE_REQUEST
    assert frame.ble_request_id == 9
    assert frame.payload == b"test"


def test_invalid_frame_is_rejected() -> None:
    raw = bytearray(build_frame(FRAME_TYPE_STATE_REQUEST))
    raw[3] ^= 0x01

    with pytest.raises(TionProtocolError, match="checksum"):
        parse_frame(bytes(raw))


def test_fragmentation_and_reassembly() -> None:
    raw = build_frame(FRAME_TYPE_STATE_REQUEST, bytes(range(70)))
    packets = fragment_frame(raw)

    assert all(len(packet) <= 20 for packet in packets)
    assert packets[0][0] == 0x00
    assert packets[-1][0] == 0xC0

    assembler = FrameAssembler()
    complete = None
    for packet in packets:
        complete = assembler.feed(packet)
    assert complete == raw


def test_lone_packet() -> None:
    raw = build_frame(FRAME_TYPE_STATE_REQUEST)
    packets = fragment_frame(raw)

    assert len(packets) == 1
    assert packets[0][0] == 0x80
    assert FrameAssembler().feed(packets[0]) == raw


def test_state_response_decoding() -> None:
    state = parse_state_response(_state_payload())

    assert state.power is True
    assert state.sound is True
    assert state.led is True
    assert state.filter_required is True
    assert state.auto is False
    assert state.heater is True
    assert state.heater_present is True
    assert state.kiv_present is True
    assert state.kiv_active is True
    assert state.target_temperature == 20
    assert state.fan_speed == 4
    assert state.outdoor_temperature == -15
    assert state.current_temperature == 22
    assert state.pcb_temperature == 40
    assert state.work_time == 3600
    assert state.fan_time == 1800
    assert state.filter_time == 86400
    assert state.airflow_volume == 2.0
    assert state.errors == 0x01020304
    assert state.button_temperatures == (10, 20, 25)
    assert state.button_fan_speeds == (2, 4, 6)
    assert state.max_fan_speed == 6
    assert state.heater_output == 50


def test_state_set_preserves_all_settings() -> None:
    state = parse_state_response(_state_payload()).updated(
        power=False,
        heater=False,
        fan_speed=6,
        target_temperature=25,
    )

    payload = build_state_set_payload(state, request_id=42)

    assert len(payload) == 18
    assert struct.unpack_from("<I", payload)[0] == 42
    assert payload[4] & 0x01 == 0
    assert payload[4] & 0x02
    assert payload[4] & 0x04
    assert payload[4] & 0x10 == 0
    assert payload[6] == 2
    assert struct.unpack_from("<b", payload, 7)[0] == 25
    assert payload[8] == 6
    assert struct.unpack_from("<bbb", payload, 9) == (10, 20, 25)
    assert tuple(payload[12:15]) == (2, 4, 6)


def test_filter_reset_uses_181_days() -> None:
    state = parse_state_response(_state_payload())
    payload = build_state_set_payload(state, request_id=1, filter_reset=True)

    assert payload[5] & 0x01
    assert struct.unpack_from("<H", payload, 15)[0] == 181


def test_real_tion_lite_capture() -> None:
    """Decode a real notification sequence captured from Tion Lite."""
    packets = (
        bytes.fromhex("0049003a4e31120dd71f8fbfc94037cfd8020f04"),
        bytes.fromhex("40090f1a808e0500e98b050017c2e700261b1800"),
        bytes.fromhex("4000000000000000000000000300040200000000"),
        bytes.fromhex("c000000000000a1419020406061800b5ad"),
    )
    assembler = FrameAssembler()
    complete = None
    for packet in packets:
        complete = assembler.feed(packet)

    assert complete is not None
    frame = parse_frame(complete)
    state = parse_state_response(frame.payload)
    assert state.power is True
    assert state.heater is True
    assert state.target_temperature == 15
    assert state.fan_speed == 4
    assert state.outdoor_temperature == 9
    assert state.current_temperature == 15
    assert state.pcb_temperature == 26
    assert state.max_fan_speed == 6
    assert state.heater_output == 24
