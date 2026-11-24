# Chipsea Scale for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![Validate][validate-shield]][validate]
[![Tests][tests-shield]][tests]
[![License][license-shield]](LICENSE)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=miguelangel-nubla&repository=homeassistant_chipsea_scale&category=integration)

A Home Assistant integration for Bluetooth kitchen scales built on the Chipsea chipset, such as:

- Scales advertising as `Chipsea-BLE`
- SmartChef kitchen scales
- ProfiCook PC-KW scales
- Other scales advertising the Chipsea Bluetooth manufacturer ID (4298)

## Features

- **Automatic discovery** of scales over Bluetooth, including through ESPHome Bluetooth proxies
- **Instant readings**: the scale pushes every weight change; nothing is polled
- **Any display unit**: readings in g, kg, lb or oz are all reported in grams
- **Honest availability**: the sensor is unavailable while the scale sleeps and returns as soon as it wakes up
- **Battery friendly**: connects only while the scale is advertising, and keeps retrying while it is awake so a failed attempt never leaves it disconnected

## Installation

### Home Assistant Marketplace

1. Click the button above, or in Home Assistant go to **Settings** → **Marketplace**, add `https://github.com/miguelangel-nubla/homeassistant_chipsea_scale` as a custom repository of type **Integration**, and open it.
2. Click **Download**.
3. Restart Home Assistant.

On Home Assistant versions before 2026.11, the same steps work in HACS.

### Manual

1. Download the latest release from the [releases page][releases].
2. Copy the `custom_components/chipsea_scale` folder into your Home Assistant `config/custom_components` folder.
3. Restart Home Assistant.

## Configuration

Wake the scale by placing something on it. Home Assistant usually discovers it on its own and shows a notification under **Settings** → **Devices & services**. You can also add it yourself:

1. Go to **Settings** → **Devices & services** → **Add integration** and search for **Chipsea Scale**.
2. Pick your scale from the list, or choose **Enter address manually** and type its Bluetooth address (for example `AA:BB:CC:DD:EE:FF`).

A scale added by address can be set up while it is asleep. It connects the next time it wakes up.

## Entities

| Entity | Description |
| --- | --- |
| Weight | Current weight in grams. Unavailable while the scale is asleep or until the first reading after it wakes up. |

The weight sensor also has these attributes:

| Attribute | Description |
| --- | --- |
| `scale_unit` | Unit shown on the scale's display (`g`, `kg`, `lb` or `oz`) |
| `raw_weight` | Weight as shown on the display, in `scale_unit` |
| `decimal_places` | Decimal places shown on the display |
| `is_stable` | Whether the scale reports the reading as settled |
| `last_measurement` | When the reading arrived |

`raw_weight` and `last_measurement` change with almost every reading, so they are not stored in the recorder history.

## Troubleshooting

**The scale is not discovered**
- Make sure the scale is on. Most scales only advertise for a short time after they wake up.
- Make sure a Bluetooth adapter or an ESPHome Bluetooth proxy that supports active connections is within range.
- Add the scale manually by its Bluetooth address.

**The sensor is unavailable**
- This is normal while the scale is off or asleep. It becomes available again with the first reading after it wakes up.
- The integration logs a single message when it cannot connect to an awake scale, and another when it is back online.

**Diagnostics**
Go to **Settings** → **Devices & services** → **Chipsea Scale** → ⋮ → **Download diagnostics**. The file includes connection statistics and the last reading. The Bluetooth address is redacted. For more detail, enable debug logging on the same page and reproduce the problem.

## Development

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest --cov
ruff check . && ruff format --check .
```

The protocol is described in [protocol_notes.txt](protocol_notes.txt).

## Contributing

Issues and pull requests are welcome. Please check the [issue tracker][issues] first.

## License

MIT. See [LICENSE](LICENSE).

[releases-shield]: https://img.shields.io/github/release/miguelangel-nubla/homeassistant_chipsea_scale.svg?style=for-the-badge
[releases]: https://github.com/miguelangel-nubla/homeassistant_chipsea_scale/releases
[validate-shield]: https://img.shields.io/github/actions/workflow/status/miguelangel-nubla/homeassistant_chipsea_scale/validate.yaml?branch=master&label=validate&style=for-the-badge
[validate]: https://github.com/miguelangel-nubla/homeassistant_chipsea_scale/actions/workflows/validate.yaml
[tests-shield]: https://img.shields.io/github/actions/workflow/status/miguelangel-nubla/homeassistant_chipsea_scale/tests.yaml?branch=master&label=tests&style=for-the-badge
[tests]: https://github.com/miguelangel-nubla/homeassistant_chipsea_scale/actions/workflows/tests.yaml
[license-shield]: https://img.shields.io/github/license/miguelangel-nubla/homeassistant_chipsea_scale.svg?style=for-the-badge
[issues]: https://github.com/miguelangel-nubla/homeassistant_chipsea_scale/issues
