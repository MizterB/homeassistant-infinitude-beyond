"""Binary sensors for Infinitude."""

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import InfinitudeDataUpdateCoordinator, InfinitudeEntity
from .const import DOMAIN
from .infinitude.const import HumidifierState as InfHumidifierState

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class InfinitudeBinarySensorDescriptionMixin:
    """Mixin for Infinitude binary sensor."""

    value_fn: Callable[[InfinitudeEntity], StateType]


@dataclass(frozen=True)
class InfinitudeBinarySensorDescription(
    BinarySensorEntityDescription, InfinitudeBinarySensorDescriptionMixin
):
    """Class describing Infinitude binary sensor entities."""


SYSTEM_BINARY_SENSORS: list[InfinitudeBinarySensorDescription] = [
    InfinitudeBinarySensorDescription(
        key="humidifier_state",
        name="Humidifier state",
        value_fn=lambda entity: entity.system.humidifier_state == InfHumidifierState.ON,
    )
]

ZONE_BINARY_SENSORS: tuple[InfinitudeBinarySensorDescription, ...] = ()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Infinitude binary sensors from config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    for entity_description in SYSTEM_BINARY_SENSORS:
        entities.append(InfinitudeBinarySensorEntity(coordinator, entity_description))
    zones = [z for z in coordinator.infinitude.zones.values() if z.enabled]
    for zone in zones:
        for entity_description in ZONE_BINARY_SENSORS:
            entities.append(
                InfinitudeBinarySensorEntity(coordinator, entity_description, zone.id)
            )
    async_add_entities(entities)


class InfinitudeBinarySensorEntity(InfinitudeEntity, BinarySensorEntity):
    """Representation of an Infinitude binary sensor."""

    entity_description: InfinitudeBinarySensorDescription

    def __init__(
        self,
        coordinator: InfinitudeDataUpdateCoordinator,
        entity_description: InfinitudeBinarySensorDescription,
        zone_id: str | None = None,
    ) -> None:
        """Set up the instance."""
        self.entity_description = entity_description
        super().__init__(coordinator, zone_id)

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.entity_description.value_fn(self)
