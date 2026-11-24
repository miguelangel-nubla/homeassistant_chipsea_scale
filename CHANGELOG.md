# Changelog

## 1.3.0

Prepared for the Home Assistant Marketplace.

### Changed
- The weight is reported with decimals instead of being rounded to whole grams. The display still defaults to whole grams; change it in the entity settings.
- Packets with an unrecognized unit are ignored instead of being reported as grams.
- `raw_weight` and `last_measurement` are no longer stored in the recorder history.
- Requires Home Assistant 2025.2 or newer.

### Fixed
- The setup dialogs and the entity name were not translated.
- Scales recognized only by the Chipsea manufacturer ID were rejected during discovery.
- Setup ran its own Bluetooth scan instead of using Home Assistant's adapters and proxies.
- Unloading the integration did not wait for a pending reconnect attempt.
- Bluetooth proxies are now loaded before the scale connects.

### Removed
- The `battery_level` attribute, which was never populated.

### Added
- Brand icons for light and dark themes, and an entity icon.
- Translated names for the sensor attributes.
- Tests, and CI for hassfest, the Marketplace checks, linting and tests.
- `PROTOCOL.md` describing the Bluetooth protocol.
