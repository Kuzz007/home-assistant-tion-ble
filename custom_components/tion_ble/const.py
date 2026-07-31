"""Constants for the Tion BLE integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "tion_ble"
MANUFACTURER: Final = "Tion"
MODEL: Final = "Tion Lite"

SERVICE_UUID: Final = "98f00001-3788-83ea-453e-f52244709ddb"
WRITE_CHARACTERISTIC_UUID: Final = "98f00002-3788-83ea-453e-f52244709ddb"
NOTIFY_CHARACTERISTIC_UUID: Final = "98f00003-3788-83ea-453e-f52244709ddb"

UPDATE_INTERVAL: Final = timedelta(seconds=60)
RESPONSE_TIMEOUT: Final = 10.0

DEFAULT_MAX_FAN_SPEED: Final = 6
MIN_TARGET_TEMPERATURE: Final = 1
MAX_TARGET_TEMPERATURE: Final = 25

PLATFORMS: Final = ["binary_sensor", "fan", "number", "sensor", "switch"]
