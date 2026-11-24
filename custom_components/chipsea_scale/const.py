"""Constants for the Chipsea Scale integration."""

from __future__ import annotations

DOMAIN = "chipsea_scale"

# Bluetooth service and characteristic UUIDs
SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"

# Bluetooth SIG company identifier advertised by Chipsea scales (0x10CA)
MANUFACTURER_ID = 4298

# Lowercase device name prefixes accepted during discovery
DEVICE_NAME_PREFIXES = ("smartchef", "chipsea-ble", "proficook", "pc-kw")
