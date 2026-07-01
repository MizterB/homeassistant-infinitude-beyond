"""Datetime entities for Infinitude (the vacation window)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.datetime import (
    DateTimeEntity,
    DateTimeEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InfinitudeDataUpdateCoordinator, InfinitudeEntity
from .const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class InfinitudeDateTimeDescription(DateTimeEntityDescription):
    """Describes an Infinitude datetime entity."""

    value_fn: Callable[[InfinitudeEntity], datetime | None]
    set_fn: Callable[[InfinitudeEntity, datetime], Awaitable[None]]


DATETIMES: tuple[InfinitudeDateTimeDescription, ...] = (
    InfinitudeDateTimeDescription(
        key="vacation_start",
        translation_key="vacation_start",
        value_fn=lambda entity: entity.system.vacation_start,
        set_fn=lambda entity, value: entity.system.set_vacation(start=value),
    ),
    InfinitudeDateTimeDescription(
        key="vacation_end",
        translation_key="vacation_end",
        value_fn=lambda entity: entity.system.vacation_end,
        set_fn=lambda entity, value: entity.system.set_vacation(end=value),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Infinitude datetime entities from config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        InfinitudeDateTimeEntity(coordinator, description) for description in DATETIMES
    )


class InfinitudeDateTimeEntity(InfinitudeEntity, DateTimeEntity):
    """A configurable Infinitude datetime (system-scoped)."""

    entity_description: InfinitudeDateTimeDescription

    def __init__(
        self,
        coordinator: InfinitudeDataUpdateCoordinator,
        entity_description: InfinitudeDateTimeDescription,
    ) -> None:
        """Set up the instance."""
        self.entity_description = entity_description
        super().__init__(coordinator)

    @property
    def unique_id(self) -> str:
        """Key-based id (stable across display language)."""
        return f"{self._id_base}_system_{self.entity_description.key}"

    @property
    def native_value(self) -> datetime | None:
        """Return the current value."""
        return self.entity_description.value_fn(self)

    async def async_set_value(self, value: datetime) -> None:
        """Write the new value."""
        await self.entity_description.set_fn(self, value)
