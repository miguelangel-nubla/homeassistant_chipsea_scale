"""DataUpdateCoordinator for Chipsea Scale."""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta
import logging
import struct
from typing import TYPE_CHECKING, Any

from bleak import BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CHARACTERISTIC_UUID, DOMAIN
from .models import ChipseaScaleData

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

_LOGGER = logging.getLogger(__name__)

# Protocol constants
PACKET_HEADER = 0xCA
MIN_PACKET_LENGTH = 7
WEIGHT_BYTES_START = 5
STATUS_BYTE_INDEX = 3

# Status byte bit masks
SIGN_BIT_MASK = 0x80
STABLE_BIT_MASK = 0x01
UNIT_DECIMAL_MASK = 0x3F

# Unit type constants
UNIT_GRAMS = 0x00
UNIT_OUNCES = 0x03
UNIT_POUNDS = 0x06
UNIT_KILOGRAMS = 0x08

# Weight validation limits
MAX_WEIGHT_GRAMS = 5000  # 5kg in grams


class ChipseaScaleDataUpdateCoordinator(DataUpdateCoordinator[ChipseaScaleData]):
    """Class to manage fetching data from the Chipsea Scale."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        self.address = address.upper()
        self._config_entry = config_entry
        self._client: BleakClientWithServiceCache | None = None
        self._ble_device: BLEDevice | None = None
        self._connect_lock = asyncio.Lock()
        self._notification_enabled = False
        self._unavailable_logged = False
        self._connection_attempts = 0
        self._last_successful_connection = None
        self._total_disconnections = 0
        self._reconnect_task: asyncio.Task | None = None
        self._ha_started = False
        self._pending_reconnect = False

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
            config_entry=config_entry,
        )

        self._bluetooth_callback_unload = None

        # Listen for HA startup completion
        self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, self._on_ha_started
        )

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the scale."""
        return self._client is not None and self._client.is_connected

    @property
    def notification_enabled(self) -> bool:
        """Return True if notifications are enabled."""
        return self._notification_enabled

    @property
    def connection_stats(self) -> dict[str, Any]:
        """Return connection statistics for diagnostics."""
        return {
            "connection_attempts": self._connection_attempts,
            "total_disconnections": self._total_disconnections,
            "last_successful_connection": (
                self._last_successful_connection.isoformat()
                if self._last_successful_connection
                else None
            ),
            "current_connection_duration": (
                (datetime.now() - self._last_successful_connection).total_seconds()
                if self._last_successful_connection and self.is_connected
                else None
            ),
        }

    @callback
    def _on_ha_started(self, _) -> None:
        """Handle HA startup completion."""
        self._ha_started = True
        if self._pending_reconnect:
            _LOGGER.info("HA started, processing pending reconnection")
            self._pending_reconnect = False
            self._reconnect_task = self.hass.async_create_task(self._async_reconnect())

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle Bluetooth events."""
        _LOGGER.debug("Bluetooth event received: change=%s, address=%s, rssi=%s",
                     change, service_info.address, getattr(service_info, 'rssi', 'N/A'))
        if change == bluetooth.BluetoothChange.ADVERTISEMENT:
            self._ble_device = service_info.device
            if not self._client or not self._client.is_connected:
                # Cancel any ongoing reconnection attempt
                if self._reconnect_task and not self._reconnect_task.done():
                    self._reconnect_task.cancel()

                if self._ha_started:
                    # HA has started, safe to reconnect immediately
                    _LOGGER.info("Scale detected, attempting reconnection")
                    self._reconnect_task = self.hass.async_create_task(self._async_reconnect())
                else:
                    # HA still starting up, defer reconnection
                    _LOGGER.info("Scale detected during startup, deferring reconnection")
                    self._pending_reconnect = True

    async def _async_update_data(self) -> ChipseaScaleData:
        """Return current data - all updates are reactive via Bluetooth notifications."""
        return self.data or ChipseaScaleData()

    async def _ensure_connected(self) -> None:
        """Ensure we have a connection to the scale."""
        async with self._connect_lock:
            if self._client and self._client.is_connected:
                return

            _LOGGER.debug("Connecting to Chipsea Scale at %s", self.address)

            # Get BLE device
            if not self._ble_device:
                self._ble_device = bluetooth.async_ble_device_from_address(
                    self.hass, self.address, connectable=True
                )

            if not self._ble_device:
                raise UpdateFailed(f"Could not find device with address {self.address}")

            # Connect to device using bleak-retry-connector
            try:
                self._connection_attempts += 1
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    self._ble_device,
                    self.address,
                    disconnected_callback=self._on_disconnect,
                )

                await self._setup_notifications()

                self._last_successful_connection = datetime.now()

                if not self._unavailable_logged:
                    _LOGGER.info("Successfully connected to Chipsea Scale (attempt %d)",
                                self._connection_attempts)

                if self._unavailable_logged:
                    _LOGGER.info("Chipsea Scale is back online")
                    self._unavailable_logged = False

            except (TimeoutError, BleakError) as err:
                error_msg = str(err).lower()
                expected_errors = {
                    "no backend with an available connection slot",
                    "device is no longer reachable", 
                    "out of connection slots",
                    "device disconnected",
                    "not connected"
                }
                
                is_expected_error = any(phrase in error_msg for phrase in expected_errors)
                
                if not self._unavailable_logged:
                    if is_expected_error:
                        _LOGGER.info("Device not reachable (expected for battery-powered scales): %s", err)
                    else:
                        _LOGGER.error("Failed to connect to Chipsea Scale: %s", err)
                    self._unavailable_logged = True
                    
                raise UpdateFailed(f"Failed to connect: {err}") from err

    async def _setup_notifications(self) -> None:
        """Set up notifications for weight updates."""
        if not self._client or not self._client.is_connected:
            return

        try:
            await self._client.start_notify(CHARACTERISTIC_UUID, self._notification_callback)
            self._notification_enabled = True
            _LOGGER.debug("Notifications enabled for characteristic %s", CHARACTERISTIC_UUID)

        except BleakError as err:
            _LOGGER.error("Failed to enable notifications: %s", err)
            raise UpdateFailed(f"Failed to enable notifications: {err}") from err

    def _notification_callback(self, _: Any, data: bytearray) -> None:
        """Handle notification from the scale."""
        if not data:
            return

        _LOGGER.debug("Received notification data: %s", data.hex())

        try:
            weight_data = self._decode_weight_bytes(data)
            if weight_data:
                if not self.data:
                    self.data = ChipseaScaleData()

                # Update all weight-related fields
                self.data.weight = weight_data["weight"]  # Normalized to grams
                self.data.is_stable = weight_data.get("stable", False)
                self.data.unit = weight_data["unit"]  # Scale's native unit
                self.data.raw_weight = weight_data["raw_weight"]  # Weight in native unit
                self.data.decimals = weight_data["decimals"]  # Decimal places
                self.data.last_measurement = datetime.now()

                # Update battery level if available
                if "battery_level" in weight_data:
                    self.data.battery_level = weight_data["battery_level"]


                # Notify Home Assistant of the update
                self.async_set_updated_data(self.data)

        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("Error processing notification: %s", err)


    def _validate_packet(self, data: bytearray) -> bool:
        """Validate packet header and basic structure."""
        if len(data) < MIN_PACKET_LENGTH:
            _LOGGER.debug("Insufficient data length: %d bytes (minimum %d expected)", len(data), MIN_PACKET_LENGTH)
            return False

        if data[0] != PACKET_HEADER:
            _LOGGER.debug("Invalid packet header: %02x (expected %02x)", data[0], PACKET_HEADER)
            return False

        return True

    def _extract_unit_and_decimals(self, status_byte: int) -> tuple[str, int]:
        """Extract unit type and decimal places from status byte."""
        unit_middle_bits = (status_byte >> 1) & UNIT_DECIMAL_MASK
        unit_bits = (unit_middle_bits >> 2) & 0x0F
        decimal_bits = unit_middle_bits & 0x03
        
        unit_map = {
            UNIT_KILOGRAMS: "kg",
            UNIT_OUNCES: "oz", 
            UNIT_POUNDS: "lb",
            UNIT_GRAMS: "g"
        }
        
        unit_detected = unit_map.get(unit_bits, "unknown")
        
        _LOGGER.debug("Status byte=0x%02x: unit_bits=0x%x decimals=%d -> %s", 
                     status_byte, unit_bits, decimal_bits, unit_detected)
        
        return unit_detected, decimal_bits

    def _convert_to_grams(self, weight: float, unit: str) -> float:
        """Convert weight from native unit to grams."""
        conversion_factors = {
            "g": 1.0,
            "kg": 1000.0,
            "lb": 453.592,
            "oz": 28.3495
        }
        
        if unit in conversion_factors:
            return weight * conversion_factors[unit]
        else:
            return weight

    def _decode_weight_bytes(self, data: bytearray) -> dict[str, Any] | None:
        """Decode weight from characteristic data using Chipsea protocol."""
        if len(data) > 8:
            _LOGGER.debug("Extended packet size: %d bytes, using first 8 bytes", len(data))
            data = data[:8]

        if not self._validate_packet(data):
            return None

        try:
            _LOGGER.debug("Raw packet: %s", ' '.join(f'{b:02x}' for b in data))
            
            weight_raw = struct.unpack('>H', data[WEIGHT_BYTES_START:WEIGHT_BYTES_START+2])[0]
            
            status_byte = data[STATUS_BYTE_INDEX] if len(data) > STATUS_BYTE_INDEX else 0
            is_negative = bool(status_byte & SIGN_BIT_MASK)
            is_stable = bool(status_byte & STABLE_BIT_MASK)
            
            unit_detected, decimal_bits = self._extract_unit_and_decimals(status_byte)
            
            _LOGGER.debug("Weight raw=0x%04x (%d) negative=%s stable=%s unit=%s decimals=%d", 
                         weight_raw, weight_raw, is_negative, is_stable, unit_detected, decimal_bits)

            if weight_raw == 0:
                weight_in_detected_unit = 0.0
            else:
                scale_factor = 10 ** decimal_bits if decimal_bits > 0 else 1
                weight_in_detected_unit = float(weight_raw) / scale_factor
                if is_negative:
                    weight_in_detected_unit = -weight_in_detected_unit
            

            weight_grams = self._convert_to_grams(weight_in_detected_unit, unit_detected)

            if unit_detected in {"g", "kg", "lb", "oz"} and abs(weight_grams) > MAX_WEIGHT_GRAMS:
                _LOGGER.warning("Weight value out of range: %.1fg (max: %dg)", weight_grams, MAX_WEIGHT_GRAMS)
                return None

            _LOGGER.debug(
                "Decoded weight: raw=%d, calculated=%.3f%s -> %.1fg (stable: %s)",
                weight_raw, weight_in_detected_unit, unit_detected, weight_grams, is_stable
            )

            return {
                "weight": weight_grams, 
                "stable": is_stable, 
                "unit": unit_detected,
                "raw_weight": weight_in_detected_unit,
                "decimals": decimal_bits
            }

        except (struct.error, ValueError, IndexError) as err:
            _LOGGER.error("Error decoding weight data: %s", err)
            return None

    def _on_disconnect(self, _: BleakClientWithServiceCache) -> None:
        """Handle disconnection."""
        self._total_disconnections += 1
        _LOGGER.info("Chipsea Scale disconnected (total: %d)", self._total_disconnections)

        # Reset connection state
        self._client = None
        self._notification_enabled = False
        self._unavailable_logged = False
        self.data = None

        # Cancel ongoing reconnection and re-register callback
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        self._register_bluetooth_callback()

        self.async_update_listeners()

    def _register_bluetooth_callback(self) -> None:
        """Register Bluetooth callback for device detection."""
        if self._bluetooth_callback_unload:
            self._bluetooth_callback_unload()

        self._bluetooth_callback_unload = bluetooth.async_register_callback(
            self.hass,
            self._async_handle_bluetooth_event,
            {"address": self.address},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

    async def _async_reconnect(self) -> None:
        """Attempt to reconnect to the scale."""
        _LOGGER.debug("Attempting to reconnect to Chipsea Scale")
        try:
            await self._ensure_connected()
        except asyncio.CancelledError:
            _LOGGER.debug("Connection attempt was cancelled")
            raise
        except UpdateFailed:
            pass

    async def async_shutdown(self) -> None:
        """Disconnect from the scale."""
        # Cancel reconnection task and unload callback
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._bluetooth_callback_unload:
            self._bluetooth_callback_unload()

        # Disconnect client
        if self._client and self._client.is_connected:
            with contextlib.suppress(BleakError):
                if self._notification_enabled:
                    await self._client.stop_notify(CHARACTERISTIC_UUID)
                await self._client.disconnect()

        self._client = None
        self._notification_enabled = False

