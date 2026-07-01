"""Sensors for Infinitude."""

import logging
from collections.abc import Callable
from dataclasses import dataclass

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
    # Whether to register the sensor at all. Defaults to always; set it for
    # sensors that only apply to certain hardware so we don't create entities
    # that can never report a value.
    exists_fn: Callable[[InfinitudeEntity], bool] = lambda _entity: True


@dataclass(frozen=True, kw_only=True)
class InfinitudeSensorDescription(
    SensorEntityDescription, InfinitudeSensorDescriptionMixin
):
    """Class describing Infinitude sensor entities.

    ``kw_only`` keeps the inherited required fields from clashing with the
    mixin's defaulted ``exists_fn``; every description already passes its
    fields by keyword.
    """


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
        # Airflow reads as None when idle, so gate on the IDU reporting at all.
        exists_fn=lambda entity: entity.system.has_idu,
    ),
    InfinitudeSensorDescription(
        key="idu_modulation",
        name="IDU modulation",
        native_unit_of_measurement="%",
        value_fn=lambda entity: entity.system.idu_modulation,
        # Only a modulating furnace reports this; non-None means the IDU does.
        exists_fn=lambda entity: entity.system.idu_modulation is not None,
    ),
    InfinitudeSensorDescription(
        key="odu_modulation",
        name="ODU modulation",
        native_unit_of_measurement="%",
        value_fn=lambda entity: entity.system.odu_modulation,
        # Only a modulating outdoor unit reports this.
        exists_fn=lambda entity: entity.system.odu_modulation is not None,
    ),
    InfinitudeSensorDescription(
        key="furnace_status",
        translation_key="furnace_status",
        value_fn=lambda entity: entity.system.furnace_status,
        exists_fn=lambda entity: entity.system.furnace_status is not None,
    ),
    InfinitudeSensorDescription(
        key="heatpump_status",
        translation_key="heatpump_status",
        value_fn=lambda entity: entity.system.heatpump_status,
        exists_fn=lambda entity: entity.system.heatpump_status is not None,
    ),
    InfinitudeSensorDescription(
        key="heatpump_mode",
        translation_key="heatpump_mode",
        value_fn=lambda entity: entity.system.heatpump_mode,
        exists_fn=lambda entity: entity.system.heatpump_mode is not None,
    ),
    InfinitudeSensorDescription(
        key="heat_source",
        translation_key="heat_source",
        value_fn=lambda entity: entity.system.heat_source,
        exists_fn=lambda entity: entity.system.heat_source is not None,
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
        entity = InfinitudeSensorEntity(coordinator, entity_description)
        if entity_description.exists_fn(entity):
            entities.append(entity)
    zones = [z for z in coordinator.infinitude.zones.values() if z.enabled]
    for zone in zones:
        for entity_description in ZONE_SENSORS:
            entity = InfinitudeSensorEntity(coordinator, entity_description, zone.id)
            if entity_description.exists_fn(entity):
                entities.append(entity)
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
    def unique_id(self) -> str:
        """Return the unique id.

        Translated sensors key on the stable description key rather than the
        base class's name, which would otherwise vary with the display language.
        """
        if self.entity_description.translation_key:
            scope = f"zone_{self.zone.id}" if self.zone else "system"
            return f"{self._id_base}_{scope}_{self.entity_description.key}"
        return super().unique_id

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
