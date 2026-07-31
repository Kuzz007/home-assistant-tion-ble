"""Helpers for finding Tion Lite devices."""

from __future__ import annotations

from collections.abc import Callable, Iterable


def matches_tion_lite(
    name: str | None, service_uuids: Iterable[str], service_uuid: str
) -> bool:
    """Return whether a Bluetooth advertisement likely belongs to Tion Lite."""
    normalized_uuids = {uuid.lower() for uuid in service_uuids}
    return service_uuid.lower() in normalized_uuids or (
        name is not None and "tion" in name.casefold()
    )


def device_label(
    address: str,
    name: str | None,
    rssi: int,
    title_builder: Callable[[str, str | None], str],
) -> str:
    """Build a device-picker label with address and signal strength."""
    return f"{title_builder(address, name)} — {address} — RSSI {rssi} dBm"
