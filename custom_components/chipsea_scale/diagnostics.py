"""Diagnostics support for Chipsea Scale."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from .models import ChipseaScaleConfigEntry

TO_REDACT = {CONF_ADDRESS}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ChipseaScaleConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "connection": {
            "connected": coordinator.is_connected,
            "notification_enabled": coordinator.notification_enabled,
            **coordinator.connection_stats,
        },
        "last_reading": (
            {
                **asdict(data.reading),
                "last_measurement": data.last_measurement.isoformat(),
            }
            if data
            else None
        ),
    }
