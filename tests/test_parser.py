"""Tests for the Chipsea notification decoder."""

from __future__ import annotations

import pytest

from custom_components.chipsea_scale.parser import ScaleReading, parse_notification


def _packet(status: int, raw: int) -> bytes:
    """Build a notification with the given status byte and raw weight."""
    return bytes([0xCA, 0x10, 0x00, status, 0x00]) + raw.to_bytes(2, "big") + b"\x00"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        # Grams, no decimals, unstable
        (_packet(0x00, 123), ScaleReading(123.0, 123.0, "g", 0, False)),
        # Grams, 1 decimal, stable
        (_packet(0x03, 1234), ScaleReading(123.4, 123.4, "g", 1, True)),
        # Kilograms, 3 decimals, unstable (example from PROTOCOL.md)
        (_packet(0x46, 2056), ScaleReading(2056.0, 2.056, "kg", 3, False)),
        # Kilograms, 3 decimals, negative, stable
        (_packet(0xC7, 150), ScaleReading(-150.0, -0.15, "kg", 3, True)),
        # Ounces, 2 decimals
        (_packet(0x1C, 1000), ScaleReading(283.49523125, 10.0, "oz", 2, False)),
        # Pounds, 2 decimals
        (_packet(0x34, 250), ScaleReading(1133.980925, 2.5, "lb", 2, False)),
        # Zero reading
        (_packet(0x01, 0), ScaleReading(0.0, 0.0, "g", 0, True)),
    ],
)
def test_parse_valid(data: bytes, expected: ScaleReading) -> None:
    """Valid packets decode to the expected reading."""
    reading = parse_notification(data)
    assert reading is not None
    assert reading.weight_grams == pytest.approx(expected.weight_grams)
    assert reading.raw_weight == pytest.approx(expected.raw_weight)
    assert (reading.unit, reading.decimals, reading.is_stable) == (
        expected.unit,
        expected.decimals,
        expected.is_stable,
    )


def test_parse_long_packet() -> None:
    """Scales that send 19 byte packets decode the same way."""
    reading = parse_notification(bytearray(_packet(0x00, 500) + bytes(11)))
    assert reading is not None
    assert reading.weight_grams == 500


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\xca\x10\x00\x00\x00\x00", id="too_short"),
        pytest.param(b"\xcb" + _packet(0x00, 100)[1:], id="wrong_header"),
        pytest.param(_packet(0x08, 100), id="unknown_unit"),
        pytest.param(_packet(0x00, 5001), id="over_max"),
        pytest.param(_packet(0x80, 5001), id="under_min"),
    ],
)
def test_parse_rejected(data: bytes) -> None:
    """Packets that are not weight readings are ignored."""
    assert parse_notification(data) is None
