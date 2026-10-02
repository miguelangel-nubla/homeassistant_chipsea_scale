# Chipsea Scale Integration for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=miguelangel-nubla&repository=homeassistant_chipsea_scale&category=integration)

A Home Assistant custom integration for Chipsea-based Bluetooth smart scales including:
- Chipsea-BLE branded scales
- SmartChef kitchen scales  
- ProfiCook PC-KW scales
- And other Chipsea-based smart scales

## Features

- **Automatic Discovery**: Bluetooth devices are automatically discovered
- **Real-time Updates**: Instant weight readings when scale is in use
- **Multiple Units**: Supports grams, kilograms, pounds, and ounces
- **Smart Availability**: Entity becomes unavailable when scale goes to sleep
- **Battery Efficient**: Connects only while the scale is advertising - no connection attempts while it sleeps
- **Reliable Reconnection**: Keeps retrying while the scale is awake, so a failed attempt or a quick power-cycle never leaves it disconnected
- **Gold Quality**: Meets Home Assistant's Gold quality standards

## Supported Devices

This integration works with Bluetooth smart scales that use the Chipsea chipset and protocol, including:

- Scales advertising as "Chipsea-BLE"
- SmartChef kitchen scales
- ProfiCook PC-KW series
- Generic scales with manufacturer ID 4298
- Scales using service UUID `0000fff0-0000-1000-8000-00805f9b34fb`

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations" 
3. Click the 3 dots menu and select "Custom repositories"
4. Add this repository URL: `https://github.com/miguelangel-nubla/homeassistant_chipsea_scale`
5. Select category "Integration" and click "Add"
6. Find "Chipsea Scale" in the list and click "Download"
7. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page][releases]
2. Extract the files to your `custom_components` directory:
   ```
   custom_components/
   └── chipsea_scale/
       ├── __init__.py
       ├── config_flow.py
       ├── coordinator.py
       ├── models.py
       ├── sensor.py
       ├── const.py
       ├── diagnostics.py
       ├── manifest.json
       ├── strings.json
       └── hacs.json
   ```
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Chipsea Scale"
4. Follow the setup wizard:
   - Your scale should be automatically discovered
   - If not found, you can manually enter the Bluetooth address
5. The integration will create a weight sensor for your scale

## Usage

- **Power on your scale** by stepping on it or placing an item
- The weight sensor will show the current measurement in grams
- Additional attributes show the scale's native unit and raw reading
- When the scale goes to sleep, the entity becomes "unavailable"
- Wake the scale by using it again - the entity will immediately become available

## Sensor Attributes

The weight sensor provides these attributes:

- `scale_unit`: The unit reported by the scale (g, kg, lb, oz)
- `raw_weight`: The weight in the scale's native unit
- `decimal_places`: Number of decimal places from the scale
- `is_stable`: Whether the reading is stable
- `last_measurement`: Timestamp of the last reading

## Troubleshooting

### Scale Not Discovered
- Ensure the scale is powered on and in pairing/advertising mode
- Check that Bluetooth is enabled on your Home Assistant system
- Try manually adding the scale using its MAC address

### Connection Issues
- Battery-powered scales disconnect frequently to save power - this is normal
- The integration will automatically reconnect when the scale advertises
- Check the diagnostic information for connection statistics

### Getting Diagnostic Information
Go to **Settings** → **Devices & Services** → **Chipsea Scale** → **Download Diagnostics** to get detailed information for troubleshooting.

## Contributing

Issues and feature requests are welcome! Please check the [issue tracker][issues] before creating a new issue.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

[releases-shield]: https://img.shields.io/github/release/miguelangel-nubla/homeassistant_chipsea_scale.svg?style=for-the-badge
[releases]: https://github.com/miguelangel-nubla/homeassistant_chipsea_scale/releases
[commits-shield]: https://img.shields.io/github/commit-activity/y/miguelangel-nubla/homeassistant_chipsea_scale.svg?style=for-the-badge
[commits]: https://github.com/miguelangel-nubla/homeassistant_chipsea_scale/commits/main
[license-shield]: https://img.shields.io/github/license/miguelangel-nubla/homeassistant_chipsea_scale.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[issues]: https://github.com/miguelangel-nubla/homeassistant_chipsea_scale/issues