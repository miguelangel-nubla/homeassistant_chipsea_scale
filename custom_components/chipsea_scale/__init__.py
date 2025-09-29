"""The Chipsea Scale integration."""
from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import ChipseaScaleDataUpdateCoordinator
from .models import ChipseaScaleConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ChipseaScaleConfigEntry) -> bool:
    """Set up Chipsea Scale from a config entry."""
    address = entry.data[CONF_ADDRESS]

    coordinator = ChipseaScaleDataUpdateCoordinator(hass, address, entry)
    entry.runtime_data = coordinator

    # Register for Bluetooth advertisements to detect when device comes back online
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            coordinator._async_handle_bluetooth_event,  # noqa: SLF001
            {"address": address.upper()},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChipseaScaleConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unload_ok

