"""Decoder for Chipsea scale weight notifications.

Kept free of Home Assistant imports so the protocol can be tested on its own.
See PROTOCOL.md in the repository for the packet layout.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

_LOGGER = logging.getLogger(__name__)

PACKET_HEADER = 0xCA
MIN_PACKET_LENGTH = 7
STATUS_BYTE_INDEX = 3
WEIGHT_BYTES_START = 5

# Status byte layout: bit 7 sign, bits 6-3 unit, bits 2-1 decimals, bit 0 stable
SIGN_BIT_MASK = 0x80
STABLE_BIT_MASK = 0x01

UNIT_GRAMS = "g"
UNIT_KILOGRAMS = "kg"
UNIT_POUNDS = "lb"
UNIT_OUNCES = "oz"

UNIT_CODES: dict[int, str] = {
    0x0: UNIT_GRAMS,
    0x3: UNIT_OUNCES,
    0x6: UNIT_POUNDS,
    0x8: UNIT_KILOGRAMS,
}

GRAMS_PER_UNIT: dict[str, float] = {
    UNIT_GRAMS: 1.0,
    UNIT_KILOGRAMS: 1000.0,
    UNIT_POUNDS: 453.59237,
    UNIT_OUNCES: 28.349523125,
}

# Readings beyond this are treated as corrupt packets
MAX_WEIGHT_GRAMS = 5000


@dataclass(frozen=True, slots=True)
class ScaleReading:
    """A single decoded weight reading."""

    weight_grams: float
    raw_weight: float  # Weight in the unit shown on the scale
    unit: str  # Unit shown on the scale
    decimals: int  # Decimal places shown on the scale
    is_stable: bool


def parse_notification(data: bytes | bytearray) -> ScaleReading | None:
    """Decode a weight notification, or return None if it is not one."""
    if len(data) < MIN_PACKET_LENGTH:
        _LOGGER.debug("Ignoring short packet: %s", data.hex())
        return None
    if data[0] != PACKET_HEADER:
        _LOGGER.debug("Ignoring packet with unknown header: %s", data.hex())
        return None

    status = data[STATUS_BYTE_INDEX]
    unit_code = (status >> 3) & 0x0F
    decimals = (status >> 1) & 0x03
    unit = UNIT_CODES.get(unit_code)
    if unit is None:
        _LOGGER.debug(
            "Ignoring packet with unknown unit code 0x%x: %s", unit_code, data.hex()
        )
        return None

    raw = int.from_bytes(data[WEIGHT_BYTES_START : WEIGHT_BYTES_START + 2], "big")
    raw_weight = raw / 10**decimals
    if status & SIGN_BIT_MASK:
        raw_weight = -raw_weight

    weight_grams = raw_weight * GRAMS_PER_UNIT[unit]
    if abs(weight_grams) > MAX_WEIGHT_GRAMS:
        _LOGGER.debug(
            "Ignoring out of range weight %.1f g: %s", weight_grams, data.hex()
        )
        return None

    return ScaleReading(
        weight_grams=weight_grams,
        raw_weight=raw_weight,
        unit=unit,
        decimals=decimals,
        is_stable=bool(status & STABLE_BIT_MASK),
    )
