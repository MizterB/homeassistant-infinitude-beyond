"""Sensors for Infinitude."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InfinitudeEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Infinitude sensors from config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        [
            InfinitudeCurrentActivitySensor(coordinator, "1"),
            InfinitudeNextActivitySensor(coordinator, "1"),
            InfinitudeNextActivityStartSensor(coordinator, "1"),
            InfinitudeScheduledActivitySensor(coordinator, "1"),
            InfinitudeScheduledActivityStartSensor(coordinator, "1"),
            InfinitudeHoldActivitySensor(coordinator, "1"),
            InfinitudeHoldModeSensor(coordinator, "1"),
            InfinitudeHoldStateSensor(coordinator, "1"),
            InfinitudeHoldUntilSensor(coordinator, "1"),
        ]
    )


class InfinitudeCurrentActivitySensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_name = "Current activity"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.activity_current.value


class InfinitudeNextActivitySensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_name = "Next activity"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.activity_next.value


class InfinitudeNextActivityStartSensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Next activity start"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.activity_next_start


class InfinitudeScheduledActivitySensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_name = "Scheduled activity"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.activity_scheduled.value


class InfinitudeScheduledActivityStartSensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Scheduled activity start"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.activity_scheduled_start


class InfinitudeHoldActivitySensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_name = "Hold activity"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        if self._zone.hold_activity:
            return self._zone.hold_activity.value
        return None


class InfinitudeHoldModeSensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_name = "Hold mode"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.hold_mode.value


class InfinitudeHoldStateSensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_name = "Hold state"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.hold_state.value


class InfinitudeHoldUntilSensor(InfinitudeEntity, SensorEntity):
    """Representation of an Infinitude sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_name = "Hold until"

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the sensor device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        self._attr_unique_id = f"{self._system.serial}_zone_{self._zone.id}_{self.name}"
        super().__init__(coordinator)

    @property
    def native_value(self) -> str:
        """Return native value of sensor."""
        return self._zone.hold_until
