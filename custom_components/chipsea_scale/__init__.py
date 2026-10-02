"""The Chipsea Scale integration."""
from __future__ import annotations

import logging

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

    # Watch for advertisements and keep the scale connected while it is awake
    entry.async_on_unload(coordinator.async_start())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ChipseaScaleConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unload_ok

