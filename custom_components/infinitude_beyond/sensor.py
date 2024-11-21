"""Sensors for Infinitude."""

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import InfinitudeDataUpdateCoordinator, InfinitudeEntity
from .const import DOMAIN
from .infinitude.const import TemperatureUnit as InfTemperatureUnit

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class InfinitudeSensorDescriptionMixin:
    """Mixin for Infinitude sensor."""

    value_fn: Callable[[InfinitudeEntity], StateType]


@dataclass(frozen=True)
class InfinitudeSensorDescription(
    SensorEntityDescription, InfinitudeSensorDescriptionMixin
):
    """Class describing Infinitude sensor entities."""


SYSTEM_SENSORS: tuple[InfinitudeSensorDescription, ...] = (
    InfinitudeSensorDescription(
        key="local_time",
        name="Local time",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity: entity.system.local_time,
    ),
    InfinitudeSensorDescription(
        key="local_timezone",
        name="Local timezone",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity: entity.system.local_timezone,
    ),
    InfinitudeSensorDescription(
        key="hvac_mode",
        name="HVAC mode",
        value_fn=lambda entity: (
            entity.system.hvac_mode.value if entity.system.hvac_mode else None
        ),
    ),
    InfinitudeSensorDescription(
        key="filter_level",
        name="Filter level",
        native_unit_of_measurement="%",
        value_fn=lambda entity: entity.system.filter_level,
    ),
    InfinitudeSensorDescription(
        key="humidifier_level",
        name="Humidifier level",
        native_unit_of_measurement="%",
        value_fn=lambda entity: entity.system.humidifier_level,
    ),
    InfinitudeSensorDescription(
        key="ventilator_level",
        name="Ventilator level",
        native_unit_of_measurement="%",
        value_fn=lambda entity: entity.system.ventilator_level,
    ),
    InfinitudeSensorDescription(
        key="uv_level",
        name="UV level",
        native_unit_of_measurement="%",
        value_fn=lambda entity: entity.system.uv_level,
    ),
    InfinitudeSensorDescription(
        key="temperature_outside",
        name="Outside temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda entity: entity.system.temperature_outside,
    ),
    InfinitudeSensorDescription(
        key="airflow_cfm",
        name="Airflow",
        # device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement="ft³/min",
        value_fn=lambda entity: entity.system.airflow_cfm,
    ),
    InfinitudeSensorDescription(
        key="idu_modulation",
        name="IDU modulation",
        native_unit_of_measurement="%",
        value_fn=lambda entity: entity.system.idu_modulation,
    ),
    InfinitudeSensorDescription(
        key="hpstage",
        name="Heat pump stage",
        value_fn=lambda entity: entity.system.heatpump_stage,
    ),
)

ZONE_SENSORS: tuple[InfinitudeSensorDescription, ...] = (
    InfinitudeSensorDescription(
        key="activity_current",
        name="Current activity",
        value_fn=lambda entity: (
            entity.zone.activity_current.value if entity.zone.activity_current else None
        )
    ),
    InfinitudeSensorDescription(
        key="activity_next",
        name="Next activity",
        value_fn=lambda entity: (
            entity.zone.activity_next.value if entity.zone.activity_next else None
        )
    ),
    InfinitudeSensorDescription(
        key="activity_next_start",
        name="Next activity start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda entity: entity.zone.activity_next_start,
    ),
    InfinitudeSensorDescription(
        key="activity_scheduled",
        name="Scheduled activity",
        value_fn=lambda entity: (
            entity.zone.activity_scheduled.value if entity.zone.activity_scheduled else None
        )
    ),
    InfinitudeSensorDescription(
        key="activity_scheduled_start",
        name="Scheduled activity start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda entity: entity.zone.activity_scheduled_start,
    ),
    InfinitudeSensorDescription(
        key="hold_activity",
        name="Hold activity",
        value_fn=lambda entity: (
            entity.zone.hold_activity.value if entity.zone.hold_activity else None
        ),
    ),
    InfinitudeSensorDescription(
        key="hold_mode",
        name="Hold mode",
        value_fn=lambda entity: entity.zone.hold_mode.value,
    ),
    InfinitudeSensorDescription(
        key="hold_state",
        name="Hold state",
        value_fn=lambda entity: entity.zone.hold_state.value,
    ),
    InfinitudeSensorDescription(
        key="hold_until",
        name="Hold until",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda entity: entity.zone.hold_until,
    ),
    InfinitudeSensorDescription(
        key="occupancy",
        name="Occupancy",
        value_fn=lambda entity: entity.zone.occupancy,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Infinitude sensors from config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    for entity_description in SYSTEM_SENSORS:
        entities.append(InfinitudeSensorEntity(coordinator, entity_description))
    zones = [z for z in coordinator.infinitude.zones.values() if z.enabled]
    for zone in zones:
        for entity_description in ZONE_SENSORS:
            entities.append(
                InfinitudeSensorEntity(coordinator, entity_description, zone.id)
            )
    async_add_entities(entities)


class InfinitudeSensorEntity(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    entity_description: InfinitudeSensorDescription

    def __init__(
        self,
        coordinator: InfinitudeDataUpdateCoordinator,
        entity_description: InfinitudeSensorDescription,
        zone_id: str | None = None,
    ) -> None:
        """Set up the instance."""
        self.entity_description = entity_description
        super().__init__(coordinator, zone_id)

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        return self.entity_description.value_fn(self)

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the native unit of measurement."""
        if self.device_class == SensorDeviceClass.TEMPERATURE:
            if self.system.temperature_unit == InfTemperatureUnit.CELSIUS:
                return UnitOfTemperature.CELSIUS
            else:
                return UnitOfTemperature.FAHRENHEIT
        return self.entity_description.native_unit_of_measurement
