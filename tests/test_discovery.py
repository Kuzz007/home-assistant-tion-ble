"""Tests for Bluetooth discovery helpers."""

from custom_components.tion_ble.discovery import device_label, matches_tion_lite

SERVICE_UUID = "98f00001-3788-83ea-453e-f52244709ddb"


def test_matches_tion_lite_by_service_uuid() -> None:
    """An exact Tion service UUID is a supported advertisement."""
    assert matches_tion_lite(None, [SERVICE_UUID.upper()], SERVICE_UUID)


def test_matches_tion_lite_by_name_when_uuid_is_not_advertised() -> None:
    """A Tion name is accepted when an advertisement omits service UUIDs."""
    assert matches_tion_lite("Tion Lite", [], SERVICE_UUID)


def test_rejects_unrelated_bluetooth_device() -> None:
    """Unrelated Bluetooth devices are not shown in the picker."""
    assert not matches_tion_lite("Xiaomi Purifier", [], SERVICE_UUID)


def test_device_label_contains_name_address_and_signal() -> None:
    """The picker label contains the details needed to identify a device."""
    assert (
        device_label(
            "AA:BB:CC:DD:EE:FF", "Tion Lite", -61, lambda _address, name: str(name)
        )
        == "Tion Lite — AA:BB:CC:DD:EE:FF — RSSI -61 dBm"
    )
