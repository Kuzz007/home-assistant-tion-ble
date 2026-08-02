"""Tests for the explicit Tion Lite speed selector."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("homeassistant.components.select")

from custom_components.tion_ble.select import TionFanSpeedSelect


@pytest.fixture
def speed_select() -> TionFanSpeedSelect:
    """Create a speed selector backed by a minimal coordinator."""
    coordinator = MagicMock()
    coordinator.data = SimpleNamespace(max_fan_speed=6, fan_speed=4)
    coordinator.async_set_state = AsyncMock()
    entry = MagicMock()
    entry.title = "Tion Lite"
    entry.runtime_data.coordinator = coordinator
    entry.runtime_data.client.address = "AA:BB:CC:DD:EE:FF"
    return TionFanSpeedSelect(entry)


def test_speed_select_exposes_all_six_steps(
    speed_select: TionFanSpeedSelect,
) -> None:
    """Display the native Tion speed steps rather than approximate labels."""
    assert speed_select.options == ["1", "2", "3", "4", "5", "6"]
    assert speed_select.current_option == "4"


async def test_selecting_speed_turns_on_breezer(
    speed_select: TionFanSpeedSelect,
) -> None:
    """A selected speed should be applied immediately and enable airflow."""
    await speed_select.async_select_option("6")

    speed_select.coordinator.async_set_state.assert_awaited_once_with(
        power=True,
        fan_speed=6,
    )
