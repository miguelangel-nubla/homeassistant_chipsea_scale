# Chipsea scale Bluetooth protocol

These notes describe what the integration relies on. They come from observing SmartChef, ProfiCook and `Chipsea-BLE` kitchen scales, not from official documentation.

## Discovery

Scales are recognized by any of:

| Field | Value |
| --- | --- |
| Local name | starts with `Chipsea-BLE`, `smartchef`, `proficook` or `pc-kw` (case-insensitive) |
| Manufacturer ID | `4298` (`0x10CA`) |
| Service UUID | `0000fff0-0000-1000-8000-00805f9b34fb` (shared with many unrelated devices, so it is only a hint) |

## Connection

The scale only advertises and accepts connections while it is on. It turns itself off after a short period of inactivity, which drops the connection.

| Item | UUID |
| --- | --- |
| Service | `0000fff0-0000-1000-8000-00805f9b34fb` |
| Weight characteristic (notify) | `0000fff1-0000-1000-8000-00805f9b34fb` |

Nothing has to be written to the scale. After notifications are enabled on the weight characteristic, it sends a packet for every reading.

## Weight packet

Packets are usually 19 bytes. Only the first 7 are used.

| Byte | Meaning |
| --- | --- |
| 0 | Header, always `0xCA` |
| 1 | Command, `0x10` for weight readings |
| 2 | Unknown |
| 3 | Status (see below) |
| 4 | Unknown |
| 5–6 | Weight, 16-bit unsigned big-endian, in the displayed unit, without the decimal point |
| 7+ | Unknown |

### Status byte

| Bits | Meaning |
| --- | --- |
| 7 | Sign: `1` negative (after tare), `0` positive |
| 6–3 | Displayed unit (see below) |
| 2–1 | Number of decimal places on the display |
| 0 | Stable: `1` settled, `0` still changing |

| Unit bits | Unit |
| --- | --- |
| `0000` | grams |
| `0011` | ounces |
| `0110` | pounds |
| `1000` | kilograms |

Packets with other unit codes are ignored.

### Decoding

```
weight = raw / 10^decimals
if sign: weight = -weight
grams  = weight × {g: 1, kg: 1000, lb: 453.59237, oz: 28.349523125}[unit]
```

Readings beyond ±5000 g are treated as corrupt and ignored.

### Examples

| Packet (first 8 bytes) | Status | Reading |
| --- | --- | --- |
| `ca 10 00 00 00 00 7b 00` | `0x00`: g, 0 decimals, changing | 123 g |
| `ca 10 00 03 00 04 d2 00` | `0x03`: g, 1 decimal, stable | 123.4 g |
| `ca 10 00 46 00 08 08 00` | `0x46`: kg, 3 decimals, changing | 2.056 kg = 2056 g |
| `ca 10 00 c7 00 00 96 00` | `0xC7`: kg, 3 decimals, negative, stable | −0.150 kg = −150 g |
| `ca 10 00 1c 00 03 e8 00` | `0x1C`: oz, 2 decimals, changing | 10.00 oz ≈ 283.5 g |

These examples are covered by `tests/test_parser.py`.
