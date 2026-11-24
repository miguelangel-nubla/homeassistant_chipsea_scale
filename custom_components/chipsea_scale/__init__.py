"""The Chipsea Scale integration."""

from __future__ import annotations

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .coordinator import ChipseaScaleCoordinator
from .models import ChipseaScaleConfigEntry

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: ChipseaScaleConfigEntry
) -> bool:
    """Set up Chipsea Scale from a config entry."""
    coordinator = ChipseaScaleCoordinator(hass, entry, entry.data[CONF_ADDRESS])
    entry.runtime_data = coordinator

    # The scale sleeps most of the time, so setup never waits for it. Watching
    # advertisements connects whenever it wakes up.
    entry.async_on_unload(coordinator.async_start())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ChipseaScaleConfigEntry
) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
    return unload_ok
