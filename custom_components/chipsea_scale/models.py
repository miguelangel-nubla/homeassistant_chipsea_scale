"""Data models for the Chipsea Scale integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .parser import ScaleReading

if TYPE_CHECKING:
    from .coordinator import ChipseaScaleCoordinator


@dataclass(frozen=True, slots=True)
class ChipseaScaleData:
    """The latest reading from the scale and when it arrived."""

    reading: ScaleReading
    last_measurement: datetime


type ChipseaScaleConfigEntry = ConfigEntry[ChipseaScaleCoordinator]
