"""Tests for setup, the connection lifecycle and the weight sensor."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chipsea_scale.const import DOMAIN
from custom_components.chipsea_scale.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import (
    ADDRESS,
    NAME,
    PACKET_123_G,
    inject_advertisement,
    make_service_info,
)

ENTITY_ID = "sensor.chipsea_ble_weight"
COORDINATOR = "custom_components.chipsea_scale.coordinator"


@pytest.fixture(autouse=True)
def fast_retries():
    """Make the reconnect loop retry without real delays."""
    with (
        patch(f"{COORDINATOR}.RETRY_BACKOFF_SECONDS", (0,)),
        patch(f"{COORDINATOR}.IDLE_POLL_SECONDS", 0),
    ):
        yield


def _fail_first(mock: AsyncMock, *errors: Exception) -> None:
    """Make the first connection attempts raise the given errors."""
    connect = mock.side_effect
    pending = list(errors)

    async def _connect(*args, **kwargs):
        if pending:
            raise pending.pop(0)
        return await connect(*args, **kwargs)

    mock.side_effect = _connect


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _wake_scale(hass: HomeAssistant, wait_for_connect: bool = True) -> None:
    """Advertise the scale and, by default, wait for the reconnect loop to end."""
    inject_advertisement(hass)
    await hass.async_block_till_done(wait_background_tasks=wait_for_connect)


async def test_setup_while_asleep(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Setup succeeds without the scale and the sensor is unavailable."""
    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    mock_establish_connection.assert_not_called()

    entity = entity_registry.async_get(ENTITY_ID)
    assert entity.unique_id == f"{ADDRESS}_weight"
    device = device_registry.async_get(entity.device_id)
    assert (DOMAIN, ADDRESS) in device.identifiers
    assert device.name == NAME
    assert device.manufacturer == "Chipsea"

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_reading_lifecycle(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """The sensor follows the scale waking up, weighing and sleeping."""
    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)

    assert len(mock_establish_connection.clients) == 1
    client = mock_establish_connection.clients[0]
    client.start_notify.assert_awaited_once()
    # Connected, but no reading yet
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    client.notify(PACKET_123_G)
    state = hass.states.get(ENTITY_ID)
    assert float(state.state) == 123
    assert state.attributes["unit_of_measurement"] == "g"
    assert state.attributes["scale_unit"] == "g"
    assert state.attributes["raw_weight"] == 123
    assert state.attributes["decimal_places"] == 0
    assert state.attributes["is_stable"] is False
    assert "last_measurement" in state.attributes

    # Garbage does not change the state
    client.notify(b"\x00\x01")
    assert float(hass.states.get(ENTITY_ID).state) == 123

    # Stable reading in kg with 3 decimals: 4.567 kg
    client.notify(bytes.fromhex("ca1000470011d700"))
    state = hass.states.get(ENTITY_ID)
    assert float(state.state) == 4567
    assert state.attributes["raw_weight"] == 4.567
    assert state.attributes["scale_unit"] == "kg"
    assert state.attributes["is_stable"] is True

    # Scale goes to sleep and stops advertising
    with patch(f"{COORDINATOR}.bluetooth.async_last_service_info", return_value=None):
        client.simulate_disconnect()
        await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE
    assert len(mock_establish_connection.clients) == 1


async def test_reconnects_after_link_drop(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """A dropped link is re-established while the scale keeps advertising."""
    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)

    mock_establish_connection.clients[0].simulate_disconnect()
    await hass.async_block_till_done(wait_background_tasks=True)

    assert len(mock_establish_connection.clients) == 2
    assert mock_config_entry.runtime_data.is_connected


async def test_retries_failed_connections(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed attempts are retried while awake and logged only once."""
    _fail_first(
        mock_establish_connection, BleakError("out of connection slots"), TimeoutError()
    )
    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)

    assert mock_establish_connection.call_count == 3
    assert mock_config_entry.runtime_data.is_connected
    assert caplog.text.count("Could not connect to Chipsea Scale") == 1
    assert "is back online" in caplog.text


async def test_unexpected_error_keeps_retrying(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unexpected exception is logged and does not end the loop."""
    _fail_first(mock_establish_connection, RuntimeError("boom"))
    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)

    assert mock_config_entry.runtime_data.is_connected
    assert "Unexpected error connecting" in caplog.text


async def test_notification_setup_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """A link without notifications is dropped and retried."""
    connect = mock_establish_connection.side_effect
    attempts = 0

    async def _connect(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        client = await connect(*args, **kwargs)
        if attempts == 1:
            client.start_notify.side_effect = BleakError("GATT error")
        return client

    mock_establish_connection.side_effect = _connect

    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)

    first, second = mock_establish_connection.clients
    first.disconnect.assert_awaited_once()
    assert not first.is_connected
    assert second.is_connected
    assert mock_config_entry.runtime_data.is_connected


async def test_no_connectable_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """Without an adapter that can reach the scale nothing is attempted."""
    with (
        patch(f"{COORDINATOR}.RETRY_BACKOFF_SECONDS", (3600,)),
        patch(
            f"{COORDINATOR}.bluetooth.async_ble_device_from_address", return_value=None
        ) as mock_lookup,
    ):
        await _setup(hass, mock_config_entry)
        await _wake_scale(hass, wait_for_connect=False)

    mock_lookup.assert_called_once()
    mock_establish_connection.assert_not_called()
    # Still retrying while the scale is awake
    assert not mock_config_entry.runtime_data._reconnect_task.done()


async def test_waits_while_asleep(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """A stale advertisement means asleep: watch, don't connect."""
    await _setup(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    stale = make_service_info(time=0)
    fresh = make_service_info()
    with (
        patch(
            f"{COORDINATOR}.bluetooth.async_last_service_info",
            side_effect=[stale, stale, fresh],
        ),
        patch(
            f"{COORDINATOR}.bluetooth.async_ble_device_from_address",
            return_value=fresh.device,
        ),
    ):
        await coordinator._async_reconnect_loop()

    assert len(mock_establish_connection.clients) == 1
    assert coordinator.is_connected


async def test_unload_disconnects(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """Unloading stops notifications and disconnects without reconnecting."""
    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)
    client = mock_establish_connection.clients[0]

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    client.stop_notify.assert_awaited_once()
    client.disconnect.assert_awaited_once()
    assert len(mock_establish_connection.clients) == 1

    # Advertisements after unload are ignored
    await _wake_scale(hass)
    assert len(mock_establish_connection.clients) == 1


async def test_unload_cancels_reconnect_loop(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """Unloading while retrying stops the loop."""
    mock_establish_connection.side_effect = BleakError("unreachable")
    with patch(f"{COORDINATOR}.RETRY_BACKOFF_SECONDS", (3600,)):
        await _setup(hass, mock_config_entry)
        await _wake_scale(hass, wait_for_connect=False)
        task = mock_config_entry.runtime_data._reconnect_task
        assert task is not None
        assert not task.done()

        assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
        assert task.done()


async def test_stale_disconnect_callback_ignored(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """A late callback from a replaced client does not drop the current one."""
    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)
    old = mock_establish_connection.clients[0]
    old.simulate_disconnect()
    await hass.async_block_till_done(wait_background_tasks=True)
    new = mock_establish_connection.clients[1]
    new.notify(PACKET_123_G)

    mock_config_entry.runtime_data._on_disconnect(old)
    assert mock_config_entry.runtime_data.is_connected
    assert float(hass.states.get(ENTITY_ID).state) == 123


async def test_diagnostics(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_establish_connection: AsyncMock,
) -> None:
    """Diagnostics show the connection and last reading without the address."""
    await _setup(hass, mock_config_entry)
    await _wake_scale(hass)
    mock_establish_connection.clients[0].notify(PACKET_123_G)

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_config_entry)

    assert diagnostics["entry"]["data"] == {"address": "**REDACTED**"}
    assert ADDRESS not in str(diagnostics)
    assert diagnostics["connection"]["connected"] is True
    assert diagnostics["connection"]["notification_enabled"] is True
    assert diagnostics["connection"]["connection_attempts"] == 1
    assert diagnostics["last_reading"]["weight_grams"] == 123
    assert diagnostics["last_reading"]["unit"] == "g"
