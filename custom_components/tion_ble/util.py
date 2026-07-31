"""Pure helper functions for Tion BLE."""

from __future__ import annotations


def speed_to_percentage(speed: int, speed_count: int) -> int:
    """Convert a discrete Tion speed to a Home Assistant percentage."""
    speed_count = max(1, speed_count)
    speed = max(1, min(speed, speed_count))
    return speed * 100 // speed_count


def percentage_to_speed(percentage: int, speed_count: int) -> int:
    """Convert a percentage to the nearest discrete Tion speed."""
    speed_count = max(1, speed_count)
    for speed in range(1, speed_count + 1):
        if percentage <= speed * 100 // speed_count:
            return speed
    return speed_count
