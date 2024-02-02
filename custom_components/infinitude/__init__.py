"""The Infinitude integration."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .infinitude.api import Infinitude

PLATFORMS: list[Platform] = [Platform.CLIMATE]

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = 15
UPDATE_TIMEOUT = 30


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Infinitude from a config entry."""

    coordinator = InfinitudeDataUpdateCoordinator(
        hass,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_SSL],
    )
    await coordinator.connect()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class InfinitudeDataUpdateCoordinator(DataUpdateCoordinator):
    """Data update coordinator for Infinitude."""

    def __init__(self, hass: HomeAssistant, host: str, port: int, ssl: bool) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
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
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout while communicating with API: {err}") from err


class InfinitudeEntity(CoordinatorEntity[InfinitudeDataUpdateCoordinator]):
    """Base class for Infinitude entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: InfinitudeDataUpdateCoordinator,
        **kwargs,
    ) -> None:
        """Init Infinitude entity."""
        self.infinitude = coordinator.infinitude
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return a device description for device registry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.infinitude.system.serial)},
            serial_number=self.infinitude.system.serial,
            manufacturer=self.infinitude.system.brand,
            model=self.infinitude.system.model,
            name=f"{self.infinitude.host}:{self.infinitude.port}",
            sw_version=self.infinitude.system.firmware,
        )

    # @abc.abstractproperty
    # def unique_id(self) -> str:
    #     """Return the unique ID for this entity."""

    # @abc.abstractproperty
    # def device_info(self) -> DeviceInfo:
    #     """Returns the device info for the controller entity"""
