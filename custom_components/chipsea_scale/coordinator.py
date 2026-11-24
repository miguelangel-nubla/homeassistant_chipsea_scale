"""Connection handling for Chipsea scales."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
import logging
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import CHARACTERISTIC_UUID, DOMAIN
from .models import ChipseaScaleConfigEntry, ChipseaScaleData
from .parser import parse_notification

_LOGGER = logging.getLogger(__name__)

# Reconnection policy
ADVERTISEMENT_FRESH_SECONDS = 30  # Scale counts as awake if it advertised this recently
IDLE_POLL_SECONDS = 5  # How often to check for advertisements while the scale sleeps
RETRY_BACKOFF_SECONDS = (
    2,
    5,
    10,
    20,
    30,
)  # Delay after each consecutive failed connect
CONNECT_MAX_ATTEMPTS = 2  # Attempts per connect; the reconnect loop retries beyond that


class ChipseaScaleConnectionError(Exception):
    """Raised when a connection to the scale could not be set up."""


class ChipseaScaleCoordinator(DataUpdateCoordinator[ChipseaScaleData | None]):
    """Keep a connection to the scale while it is awake and publish its readings.

    The scale pushes readings over notifications; nothing is polled. ``data`` is
    None whenever there is no connection or no reading since the last connect.
    """

    config_entry: ChipseaScaleConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: ChipseaScaleConfigEntry, address: str
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN} {address}",
            update_interval=None,
        )
        self.address = address.upper()
        self.data = None
        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task[None] | None = None
        self._shutting_down = False
        self._notification_enabled = False
        self._unavailable_logged = False
        self._connection_attempts = 0
        self._total_disconnections = 0
        self._last_successful_connection: datetime | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if connected to the scale."""
        return self._client is not None and self._client.is_connected

    @property
    def notification_enabled(self) -> bool:
        """Return True if weight notifications are enabled."""
        return self._notification_enabled

    @property
    def connection_stats(self) -> dict[str, Any]:
        """Return connection statistics for diagnostics."""
        last = self._last_successful_connection
        return {
            "connection_attempts": self._connection_attempts,
            "total_disconnections": self._total_disconnections,
            "last_successful_connection": last.isoformat() if last else None,
            "current_connection_duration": (
                (dt_util.utcnow() - last).total_seconds()
                if last and self.is_connected
                else None
            ),
        }

    async def _async_update_data(self) -> ChipseaScaleData | None:
        """Return the latest reading; all updates are pushed by the scale."""
        return self.data

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Start watching for the scale; return a callback that stops it."""
        # Registering replays the last known advertisement, so this also
        # starts the first connection attempt if the scale is already awake.
        return bluetooth.async_register_callback(
            self.hass,
            self._async_handle_bluetooth_event,
            bluetooth.BluetoothCallbackMatcher(address=self.address),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Start connecting when the scale advertises."""
        _LOGGER.debug(
            "Advertisement from %s (rssi %s)", service_info.address, service_info.rssi
        )
        self._async_ensure_reconnect_loop()

    @callback
    def _async_ensure_reconnect_loop(self) -> None:
        """Start the reconnect loop unless connected or it is already running."""
        if self._shutting_down or self.is_connected:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            # Never cancel an attempt in flight; the loop retries on its own
            return
        # Background task so a connection attempt never holds up HA startup
        self._reconnect_task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_reconnect_loop(),
            f"{DOMAIN} reconnect {self.address}",
        )

    async def _async_reconnect_loop(self) -> None:
        """Connect while the scale is advertising, retrying until it succeeds.

        HA only calls back when an advertisement's content changes, so an
        unchanged advertisement never calls back again until HA forgets the
        scale, minutes after it goes quiet. So this loop watches the last
        advertisement's timestamp instead of waiting for callbacks.
        """
        failures = 0
        while not self.is_connected and not self._shutting_down:
            service_info = bluetooth.async_last_service_info(
                self.hass, self.address, connectable=True
            )
            if service_info is None:
                # HA forgot the scale; its next advertisement calls back again
                _LOGGER.debug("%s no longer known to Bluetooth", self.address)
                return

            if (
                bluetooth.MONOTONIC_TIME() - service_info.time
                > ADVERTISEMENT_FRESH_SECONDS
            ):
                # Asleep, but HA still remembers it, so waking up with the same
                # advertisement will not call back. Keep watching.
                failures = 0
                await asyncio.sleep(IDLE_POLL_SECONDS)
                continue

            try:
                await self._async_connect()
            except ChipseaScaleConnectionError as err:
                self._log_unavailable(err)
            except Exception:
                # An escaped error would end the loop for good
                _LOGGER.exception("Unexpected error connecting to %s", self.address)
            if self.is_connected:
                return

            delay = RETRY_BACKOFF_SECONDS[min(failures, len(RETRY_BACKOFF_SECONDS) - 1)]
            failures += 1
            _LOGGER.debug(
                "Connecting to %s failed, retrying in %ds", self.address, delay
            )
            await asyncio.sleep(delay)

    async def _async_connect(self) -> None:
        """Connect to the scale and subscribe to weight notifications."""
        async with self._connect_lock:
            if self.is_connected:
                return

            # Always look up the current device; a cached one may point at a
            # proxy that no longer hears the scale
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise ChipseaScaleConnectionError(
                    "no connectable Bluetooth adapter or proxy can reach the scale"
                )

            _LOGGER.debug("Connecting to %s", self.address)
            self._connection_attempts += 1
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self.address,
                    disconnected_callback=self._on_disconnect,
                    max_attempts=CONNECT_MAX_ATTEMPTS,
                    ble_device_callback=lambda: (
                        bluetooth.async_ble_device_from_address(
                            self.hass, self.address, connectable=True
                        )
                        or ble_device
                    ),
                )
            except (TimeoutError, BleakError) as err:
                raise ChipseaScaleConnectionError(
                    str(err) or type(err).__name__
                ) from err

            self._client = client
            try:
                await client.start_notify(CHARACTERISTIC_UUID, self._on_notification)
            except (TimeoutError, BleakError) as err:
                # Connected but useless without weight notifications; drop the
                # link so the reconnect loop starts over
                self._client = None
                with contextlib.suppress(TimeoutError, BleakError):
                    await client.disconnect()
                raise ChipseaScaleConnectionError(
                    f"could not enable weight notifications: {err}"
                ) from err

            self._notification_enabled = True
            self._last_successful_connection = dt_util.utcnow()
            if self._unavailable_logged:
                _LOGGER.info("Chipsea Scale %s is back online", self.address)
                self._unavailable_logged = False
            _LOGGER.debug("Connected to %s", self.address)

    def _log_unavailable(self, err: Exception) -> None:
        """Log a failed connection once until the scale is reachable again."""
        if self._unavailable_logged:
            _LOGGER.debug("Connecting to %s failed: %s", self.address, err)
            return
        _LOGGER.info(
            "Could not connect to Chipsea Scale %s, will keep retrying while it is awake: %s",
            self.address,
            err,
        )
        self._unavailable_logged = True

    @callback
    def _on_notification(
        self, _characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle a weight notification from the scale."""
        _LOGGER.debug("Notification from %s: %s", self.address, data.hex())
        if (reading := parse_notification(data)) is None:
            return
        self.async_set_updated_data(
            ChipseaScaleData(reading=reading, last_measurement=dt_util.utcnow())
        )

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle the scale disconnecting, usually because it went to sleep."""
        if self._client is not None and client is not self._client:
            # Late callback from a client we already replaced
            return

        self._total_disconnections += 1
        _LOGGER.debug(
            "Disconnected from %s (total %d)", self.address, self._total_disconnections
        )
        self._client = None
        self._notification_enabled = False
        self.data = None
        self.async_update_listeners()

        # If the scale is still on (link drop) it advertises again right away
        # and the loop reconnects; if it was switched off, the loop waits
        self._async_ensure_reconnect_loop()

    async def async_shutdown(self) -> None:
        """Stop reconnecting and disconnect from the scale."""
        self._shutting_down = True
        await super().async_shutdown()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
        self._reconnect_task = None

        client, self._client = self._client, None
        if client is not None and client.is_connected:
            with contextlib.suppress(TimeoutError, BleakError):
                if self._notification_enabled:
                    await client.stop_notify(CHARACTERISTIC_UUID)
                await client.disconnect()
        self._notification_enabled = False
