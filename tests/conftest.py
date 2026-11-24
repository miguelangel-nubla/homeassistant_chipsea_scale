"""Fixtures for Chipsea Scale tests."""

from __future__ import annotations

from collections.abc import Callable, Generator
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.backends.device import BLEDevice
from homeassistant.components.bluetooth import (
    MONOTONIC_TIME,
    BluetoothServiceInfoBleak,
    async_get_advertisement_callback,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chipsea_scale.const import (
    DOMAIN,
    MANUFACTURER_ID,
    SERVICE_UUID,
)

# bleak < 1.0 requires rssi; newer versions warn when it is passed
_BLE_DEVICE_EXTRA = (
    {"rssi": -60} if "rssi" in inspect.signature(BLEDevice.__init__).parameters else {}
)

ADDRESS = "AA:BB:CC:DD:EE:FF"
NAME = "Chipsea-BLE"

# 0xCA header, status 0x00 (grams, 0 decimals, unstable), weight 0x007B = 123
PACKET_123_G = bytes.fromhex("ca10000000007b00")


def make_service_info(
    name: str | None = NAME,
    address: str = ADDRESS,
    manufacturer_data: dict[int, bytes] | None = None,
    service_uuids: list[str] | None = None,
    time: float | None = None,
) -> BluetoothServiceInfoBleak:
    """Build an advertisement as the bluetooth integration reports it."""
    return BluetoothServiceInfoBleak(
        name=name or "",
        address=address,
        rssi=-60,
        manufacturer_data=manufacturer_data or {},
        service_data={},
        service_uuids=service_uuids if service_uuids is not None else [SERVICE_UUID],
        source="local",
        device=BLEDevice(address, name, {}, **_BLE_DEVICE_EXTRA),
        advertisement=None,
        connectable=True,
        time=time if time is not None else MONOTONIC_TIME(),
        tx_power=None,
    )


SCALE_SERVICE_INFO = make_service_info()
MANUFACTURER_ONLY_SERVICE_INFO = make_service_info(
    name=None, address="11:22:33:44:55:66", manufacturer_data={MANUFACTURER_ID: b"\x00"}
)
OTHER_DEVICE_SERVICE_INFO = make_service_info(
    name="Some Thermometer", address="66:55:44:33:22:11"
)


def inject_advertisement(
    hass: HomeAssistant, service_info: BluetoothServiceInfoBleak | None = None
) -> None:
    """Feed an advertisement into the bluetooth integration."""
    async_get_advertisement_callback(hass)(service_info or make_service_info())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture(autouse=True)
def auto_enable_bluetooth(enable_bluetooth: None) -> None:
    """Set up a mocked bluetooth stack for every test."""


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a config entry for the scale, added to hass."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=ADDRESS,
        data={CONF_ADDRESS: ADDRESS},
    )
    entry.add_to_hass(hass)
    return entry


class MockScaleClient:
    """A connected Bleak client that lets tests push notifications."""

    def __init__(self, disconnected_callback: Callable[[Any], None]) -> None:
        """Initialize the client."""
        self.is_connected = True
        self._disconnected_callback = disconnected_callback
        self._notify_callback: Callable[[Any, bytearray], None] | None = None
        self.start_notify = AsyncMock(side_effect=self._start_notify)
        self.stop_notify = AsyncMock()
        self.disconnect = AsyncMock(side_effect=self._disconnect)

    async def _start_notify(
        self, _uuid: str, callback: Callable[[Any, bytearray], None]
    ) -> None:
        self._notify_callback = callback

    async def _disconnect(self) -> None:
        self.simulate_disconnect()

    def notify(self, data: bytes) -> None:
        """Push a notification as the scale would."""
        assert self._notify_callback is not None
        self._notify_callback(MagicMock(), bytearray(data))

    def simulate_disconnect(self) -> None:
        """Drop the link as the scale does when it goes to sleep."""
        if not self.is_connected:
            return
        self.is_connected = False
        self._disconnected_callback(self)


@pytest.fixture
def mock_establish_connection() -> Generator[AsyncMock]:
    """Patch establish_connection to hand out MockScaleClient instances.

    The mock's ``clients`` attribute lists every client it created.
    """
    clients: list[MockScaleClient] = []

    async def _connect(
        _client_class: Any,
        _device: BLEDevice,
        _name: str,
        disconnected_callback: Callable[[Any], None],
        **_kwargs: Any,
    ) -> MockScaleClient:
        client = MockScaleClient(disconnected_callback)
        clients.append(client)
        return client

    with patch(
        "custom_components.chipsea_scale.coordinator.establish_connection",
        side_effect=_connect,
    ) as mock:
        mock.clients = clients
        yield mock
