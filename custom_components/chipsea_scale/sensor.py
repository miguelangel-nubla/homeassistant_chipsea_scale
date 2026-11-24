"""Sensor platform for the Chipsea Scale integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_ADDRESS, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ChipseaScaleCoordinator
from .models import ChipseaScaleConfigEntry

# Entities only read pushed coordinator data
PARALLEL_UPDATES = 0

WEIGHT_DESCRIPTION = SensorEntityDescription(
    key="weight",
    translation_key="weight",
    device_class=SensorDeviceClass.WEIGHT,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfMass.GRAMS,
    suggested_display_precision=0,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ChipseaScaleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Chipsea Scale sensor."""
    async_add_entities([ChipseaScaleWeightSensor(entry, WEIGHT_DESCRIPTION)])


class ChipseaScaleWeightSensor(
    CoordinatorEntity[ChipseaScaleCoordinator], SensorEntity
):
    """Weight on the scale, in grams whatever unit the scale displays."""

    _attr_has_entity_name = True
    # These change with nearly every reading and would bloat the database
    _unrecorded_attributes = frozenset({"raw_weight", "last_measurement"})

    def __init__(
        self, entry: ChipseaScaleConfigEntry, description: SensorEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(entry.runtime_data)
        self.entity_description = description
        address: str = entry.data[CONF_ADDRESS]
        self._attr_unique_id = f"{address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address.lower())},
            name=entry.title,
            manufacturer="Chipsea",
            model="Smart Scale",
        )

    @property
    def available(self) -> bool:
        """Return True while connected and a reading has arrived."""
        return (
            super().available
            and self.coordinator.is_connected
            and self.coordinator.data is not None
        )

    @property
    def native_value(self) -> float | None:
        """Return the weight in grams."""
        if (data := self.coordinator.data) is None:
            return None
        return round(data.reading.weight_grams, 2)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the reading as shown on the scale."""
        if (data := self.coordinator.data) is None:
            return None
        reading = data.reading
        return {
            "scale_unit": reading.unit,
            "raw_weight": reading.raw_weight,
            "decimal_places": reading.decimals,
            "is_stable": reading.is_stable,
            "last_measurement": data.last_measurement.isoformat(),
        }
