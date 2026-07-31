"""Tests for discrete Tion fan speed conversion."""

from custom_components.tion_ble.util import (
    percentage_to_speed,
    speed_to_percentage,
)


def test_all_six_speeds_to_percentage() -> None:
    assert [speed_to_percentage(speed, 6) for speed in range(1, 7)] == [
        16,
        33,
        50,
        66,
        83,
        100,
    ]


def test_percentage_to_six_speeds() -> None:
    assert percentage_to_speed(1, 6) == 1
    assert percentage_to_speed(16, 6) == 1
    assert percentage_to_speed(17, 6) == 2
    assert percentage_to_speed(50, 6) == 3
    assert percentage_to_speed(83, 6) == 5
    assert percentage_to_speed(100, 6) == 6
