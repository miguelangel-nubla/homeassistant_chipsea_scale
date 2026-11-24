"""Config flow for the Chipsea Scale integration."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
import voluptuous as vol

from .const import DEVICE_NAME_PREFIXES, DOMAIN, MANUFACTURER_ID

MANUAL_ENTRY = "manual"
_MAC_PATTERN = re.compile(r"^[0-9A-F]{12}$")


def is_supported_device(service_info: BluetoothServiceInfoBleak) -> bool:
    """Return True if the advertisement looks like a Chipsea scale."""
    if MANUFACTURER_ID in service_info.manufacturer_data:
        return True
    name = (service_info.name or "").lower()
    return name.startswith(DEVICE_NAME_PREFIXES)


def normalize_address(address: str) -> str | None:
    """Return the address as AA:BB:CC:DD:EE:FF, or None if it is not a MAC."""
    cleaned = re.sub(r"[\s:\-.]", "", address).upper()
    if not _MAC_PATTERN.match(cleaned):
        return None
    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))


def _title(service_info: BluetoothServiceInfoBleak) -> str:
    """Return a readable name for a discovered scale."""
    return service_info.name or service_info.address


class ChipseaScaleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chipsea Scale."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a scale found by Bluetooth discovery."""
        if not is_supported_device(discovery_info):
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address.upper())
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setting up a discovered scale."""
        assert self._discovery_info is not None
        title = _title(self._discovery_info)

        if user_input is not None:
            return self.async_create_entry(
                title=title,
                data={CONF_ADDRESS: self._discovery_info.address.upper()},
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": title},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a discovered scale or enter an address."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address == MANUAL_ENTRY:
                return await self.async_step_manual()

            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_title(self._discovered_devices[address]),
                data={CONF_ADDRESS: address},
            )

        current_addresses = self._async_current_ids(include_ignore=False)
        self._discovered_devices = {
            address: info
            for info in async_discovered_service_info(self.hass, connectable=True)
            if (address := info.address.upper()) not in current_addresses
            and is_supported_device(info)
        }
        if not self._discovered_devices:
            return await self.async_step_manual()

        options = {
            address: f"{_title(info)} ({address})"
            for address, info in self._discovered_devices.items()
        }
        options[MANUAL_ENTRY] = "Enter address manually"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)}),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user enter the scale's Bluetooth address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if (address := normalize_address(user_input[CONF_ADDRESS])) is None:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=address, data={CONF_ADDRESS: address}
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): str}),
            errors=errors,
        )
