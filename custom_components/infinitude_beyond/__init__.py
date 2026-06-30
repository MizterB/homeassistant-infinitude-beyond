"""The Infinitude integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .infinitude.api import Infinitude

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = 15
UPDATE_TIMEOUT = 30


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Infinitude from a config entry."""

    coordinator = InfinitudeDataUpdateCoordinator(
        hass,
        entry,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_SSL],
    )
    try:
        await coordinator.connect()
    except Exception as ex:
        _LOGGER.error("Error connecting to Infinitude: %s", ex)
        raise ConfigEntryNotReady from ex

    _async_migrate_to_entry_id(hass, entry)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _rebase_id(old: str, base: str, markers: tuple[str, ...]) -> str | None:
    """Replace the prefix before the earliest marker with ``base``.

    Returns None when no marker is present or the id is already rebased.
    """
    best = None
    for marker in markers:
        idx = old.find(marker)
        if idx != -1 and (best is None or idx < best):
            best = idx
    if best is None:
        return None
    new = f"{base}{old[best:]}"
    return new if new != old else None


def _is_none_prefixed(uid: str) -> bool:
    return uid.startswith("None_")


@callback
def _async_migrate_to_entry_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rebase entity and device ids onto the config entry id.

    Preserves entity_id (and history). When an install already split, the
    serial-based entry wins and the "None" duplicate is left in place. Runs
    before platforms register so entities bind to the migrated rows.
    """
    base = entry.entry_id
    ent_reg = er.async_get(hass)
    entities = er.async_entries_for_config_entry(ent_reg, entry.entry_id)

    taken = {e.unique_id for e in entities}
    groups: dict[str, list[er.RegistryEntry]] = {}
    for ent in entities:
        target = _rebase_id(ent.unique_id, base, ("_zone_", "_system_"))
        if target is not None:
            groups.setdefault(target, []).append(ent)

    for target, candidates in groups.items():
        if target in taken:
            continue
        candidates.sort(key=lambda e: _is_none_prefixed(e.unique_id))
        ent_reg.async_update_entity(candidates[0].entity_id, new_unique_id=target)
        taken.add(target)

    dev_reg = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    taken_idents = {
        ident for d in devices for dom, ident in d.identifiers if dom == DOMAIN
    }
    devices.sort(
        key=lambda d: any(
            _is_none_prefixed(i) for dom, i in d.identifiers if dom == DOMAIN
        )
    )
    for device in devices:
        new_identifiers = set()
        changed = False
        for domain, ident in device.identifiers:
            new_ident = ident
            if domain == DOMAIN:
                rebased = _rebase_id(ident, base, ("_zone_", "_system"))
                if rebased is not None and rebased not in taken_idents:
                    new_ident = rebased
                    changed = True
                    taken_idents.add(rebased)
            new_identifiers.add((domain, new_ident))
        if changed:
            dev_reg.async_update_device(device.id, new_identifiers=new_identifiers)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class InfinitudeDataUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Infinitude."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        port: int,
        ssl: bool,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{host}:{port}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        session = async_get_clientsession(hass)
        self.infinitude: Infinitude = Infinitude(
            host=host, port=port, ssl=ssl, session=session
        )

    async def connect(self) -> None:
        """Connect to Infinitude."""
        await self.infinitude.connect()

    async def _async_update_data(self) -> None:
        """Fetch data from Infinitude."""
        try:
            await self.infinitude.update()
        except (TimeoutError, ConnectionError) as err:
            raise UpdateFailed(f"Error communicating with Infinitude: {err}") from err


class InfinitudeEntity(CoordinatorEntity[InfinitudeDataUpdateCoordinator]):
    """Base class for Infinitude entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: InfinitudeDataUpdateCoordinator,
        zone_id: str | None = None,
        **kwargs,
    ) -> None:
        """Init Infinitude entity."""
        self.infinitude = coordinator.infinitude
        self.system = coordinator.infinitude.system
        self.zone = None
        if zone_id:
            self.zone = coordinator.infinitude.zones.get(zone_id)
        super().__init__(coordinator)

    @property
    def _id_base(self) -> str:
        """Stable identity prefix for entities and devices."""
        return self.coordinator.config_entry.entry_id

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        if self.zone:
            return f"{self._id_base}_zone_{self.zone.id}_{self.name}"
        return f"{self._id_base}_system_{self.name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry.

        Each Infinitude zone is a separate device, plus a device for the overall system
        """
        if self.zone:
            if self.zone.name and len(self.zone.name) > 0:
                name = self.zone.name
            else:
                name = f"Zone {self.zone.id}"
            identifier = f"{self._id_base}_zone_{self.zone.id}"
        else:
            name = "Infinitude System"
            identifier = f"{self._id_base}_system"

        return DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            serial_number=self.infinitude.system.serial,
            manufacturer=self.infinitude.system.brand,
            model=self.infinitude.system.model,
            name=name,
            sw_version=self.infinitude.system.firmware,
            configuration_url=f"{self.infinitude.url}",
        )
