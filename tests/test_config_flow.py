"""Tests for the Chipsea Scale config flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.chipsea_scale.config_flow import normalize_address
from custom_components.chipsea_scale.const import DOMAIN

from .conftest import (
    ADDRESS,
    MANUFACTURER_ONLY_SERVICE_INFO,
    NAME,
    OTHER_DEVICE_SERVICE_INFO,
    SCALE_SERVICE_INFO,
    make_service_info,
)

DISCOVERED = "custom_components.chipsea_scale.config_flow.async_discovered_service_info"


@pytest.fixture(autouse=True)
def no_setup_entry():
    """Keep created entries from setting up the integration."""
    with patch("custom_components.chipsea_scale.async_setup_entry", return_value=True):
        yield


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    """A discovered scale is set up after confirmation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=SCALE_SERVICE_INFO
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    assert result["description_placeholders"] == {"name": NAME}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS


async def test_bluetooth_discovery_by_manufacturer(hass: HomeAssistant) -> None:
    """A scale without a known name is recognized by its manufacturer id."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=MANUFACTURER_ONLY_SERVICE_INFO,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {
        "name": MANUFACTURER_ONLY_SERVICE_INFO.address
    }


async def test_bluetooth_discovery_not_supported(hass: HomeAssistant) -> None:
    """Other devices sharing the generic service UUID are ignored."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=OTHER_DEVICE_SERVICE_INFO
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A scale that is already set up is not offered again."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=SCALE_SERVICE_INFO
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bluetooth_discovery_in_progress(hass: HomeAssistant) -> None:
    """A second discovery of the same scale is dropped."""
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=SCALE_SERVICE_INFO
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=SCALE_SERVICE_INFO
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"


async def test_user_picks_discovered_scale(hass: HomeAssistant) -> None:
    """The user step lists discovered scales only."""
    with patch(
        DISCOVERED,
        return_value=[
            SCALE_SERVICE_INFO,
            OTHER_DEVICE_SERVICE_INFO,
            make_service_info(address=ADDRESS.lower()),
        ],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    options = result["data_schema"].schema[CONF_ADDRESS].container
    assert options == {
        ADDRESS: f"{NAME} ({ADDRESS})",
        "manual": "Enter address manually",
    }

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_ADDRESS: ADDRESS}


async def test_user_takes_over_discovery_flow(hass: HomeAssistant) -> None:
    """Picking a scale that also has a pending discovery still sets it up."""
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=SCALE_SERVICE_INFO
    )
    with patch(DISCOVERED, return_value=[SCALE_SERVICE_INFO]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_user_hides_configured_scales(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """With every scale configured, the flow goes straight to manual entry."""
    with patch(DISCOVERED, return_value=[SCALE_SERVICE_INFO]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"


async def test_user_chooses_manual(hass: HomeAssistant) -> None:
    """The manual option leads to the address form."""
    with patch(DISCOVERED, return_value=[SCALE_SERVICE_INFO]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"


async def test_manual_entry(hass: HomeAssistant) -> None:
    """A typed address is validated, normalized and set up."""
    with patch(DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: "not a mac"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ADDRESS: "invalid_address"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: " aa-bb-cc-dd-ee-ff "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == ADDRESS
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS


async def test_manual_entry_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """A typed address that is already set up aborts."""
    with patch(DISCOVERED, return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS.lower()}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("AA:BB:CC:DD:EE:FF", ADDRESS),
        ("aabbccddeeff", ADDRESS),
        ("aa bb cc dd ee ff", ADDRESS),
        ("aa.bb.cc.dd.ee.ff", ADDRESS),
        ("AA:BB:CC:DD:EE", None),
        ("GG:BB:CC:DD:EE:FF", None),
        ("", None),
    ],
)
def test_normalize_address(value: str, expected: str | None) -> None:
    """Addresses are accepted in common notations."""
    assert normalize_address(value) == expected
