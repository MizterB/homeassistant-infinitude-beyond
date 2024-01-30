"""Define a base client for interacting with Infinitude."""
import asyncio
import logging
from datetime import datetime, timedelta
from re import match
from typing import Optional

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

from .const import (
    Activity,
    FanMode,
    HoldMode,
    HoldState,
    HumidifierState,
    HVACAction,
    HVACMode,
    Occupancy,
    TemperatureUnit,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_TIMEOUT: int = 10


class Infinitude:
    """Object for interacting with the Infinitude API."""

    def __init__(
        self, host: str, port: int, *, session: Optional[ClientSession] = None
    ) -> None:
        """Initialize the Infinitude API."""
        self.host: str = host
        self.port: str = port
        self._session: ClientSession = session

        self._protocol: str = "http"
        self._url_base: str = f"{self._protocol}://{self.host}:{self.port}"

        self._status: dict = {}
        self._config: dict = {}
        self._energy: dict = {}

        if not self._session or self._session.closed:
            self._session = ClientSession()

        self.system: InfinitudeSystem
        self.zones: dict[int, InfinitudeZone]
        self.energy: dict[str, str]

    async def _get(self, endpoint: str, **kwargs) -> dict:
        """Make a GET request to Infinitude."""
        url = f"{self._url_base}{endpoint}"
        try:
            async with self._session.get(url, **kwargs) as resp:
                data: dict = await resp.json(content_type=None)
                resp.raise_for_status()
                return data
        except ClientError as e:
            _LOGGER.error(e)

    async def _put(self, endpoint: str, data: dict, **kwargs) -> dict:
        """Make a PUT request to Infinitude."""
        url = f"{self._url_base}{endpoint}"
        try:
            async with self._session.put(url, data=data, **kwargs) as resp:
                data: dict = await resp.json(content_type=None)
                resp.raise_for_status()
                return data
        except ClientError as e:
            _LOGGER.error(e)

    def _simplify_json(self, data) -> dict:
        """Remove all single item lists and replace with the item."""
        if isinstance(data, dict):
            return {key: self._simplify_json(value) for key, value in data.items()}
        elif isinstance(data, list):
            if len(data) == 1:
                return self._simplify_json(data[0])
            else:
                return [self._simplify_json(item) for item in data]
        else:
            return data

    def _compare_data(self, old, new, path="") -> dict | None:
        """Recursively compare old and new data dicts and return the differences."""
        diff = {}
        for key in old.keys() | new.keys():
            if key not in old:
                diff[f"{path}/{key}"] = ("Missing in old", new[key])
            elif key not in new:
                diff[f"{path}/{key}"] = (old[key], "Missing in new")
            elif isinstance(old[key], dict) and isinstance(new[key], dict):
                deeper_diff = self._compare_data(
                    old[key], new[key], path=f"{path}/{key}"
                )
                if deeper_diff:
                    diff.update(deeper_diff)
            elif old[key] != new[key]:
                diff[f"{path}/{key}"] = (old[key], new[key])
        if diff == {}:
            return None
        return diff

    async def _fetch_status(self) -> dict:
        """Retrieve status data from Infinitude."""
        data = await self._get("/api/status/")
        status = self._simplify_json(data)
        return status

    async def _fetch_config(self) -> dict:
        """Retrieve configuration data from Infinitude."""
        resp = await self._get("/api/config/")
        status = resp.get("status")
        if status != "success":
            raise Exception(
                f"Fetch of config was not successful. Status value in the response was '{status}'."
            )
        data = resp.get("data")
        config = self._simplify_json(data)
        return config

    async def _fetch_energy(self) -> dict:
        """Retrieve energy data from Infinitude."""
        data = await self._get("/energy.json")
        energy = self._simplify_json(data)
        return energy

    async def connect(self) -> None:
        """Connect to Infinitude."""
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                _LOGGER.debug("Connecting to Infinitude")
                status, config, energy = await asyncio.gather(
                    self._fetch_status(), self._fetch_config(), self._fetch_energy()
                )
                self._status = status
                self._config = config
                self._energy = energy

        except asyncio.TimeoutError as e:
            _LOGGER.error(
                "Failed to connect to Infinitude at %s:%s after %s seconds",
                self.host,
                self.port,
                UPDATE_TIMEOUT,
            )
            raise

        self.system = InfinitudeSystem(self)
        self.zones = {}
        for zone in self._config.get("zones", {}).get("zone", []):
            zone_id = zone.get("id")
            self.zones[zone_id] = InfinitudeZone(self, zone_id)
            self.zones[zone_id]._update_activities()

    async def update(self) -> bool:
        """Update all data from Infinitude."""
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                _LOGGER.debug("Updating from Infinitude")
                status, config, energy = await asyncio.gather(
                    self._fetch_status(), self._fetch_config(), self._fetch_energy()
                )
                await self._update_status(status)
                await self._update_config(config)
                await self._update_energy(energy)
        except asyncio.TimeoutError as e:
            _LOGGER.error("Update timed out after %s seconds", UPDATE_TIMEOUT)
            return False

        for zone in self.zones.values():
            zone._update_activities()

        return True

    async def _update_status(self, status) -> None:
        """Status update handler."""
        changes = self._compare_data(self._status, status)
        if changes:
            _LOGGER.debug("Status changed: %s", changes)
        self._status = status

    async def _update_config(self, config) -> None:
        """Config update handler."""
        changes = self._compare_data(self._config, config)
        if changes:
            _LOGGER.debug("Config changed: %s", changes)
        self._config = config

    async def _update_energy(self, energy) -> None:
        """Energy update handler."""
        changes = self._compare_data(self._energy, energy)
        if changes:
            _LOGGER.debug("Energy changed: %s", changes)
        self._energy = energy

    @property
    def energy(self) -> dict:
        """Get the energy data from Infinitude."""
        return self._energy.get("energy", {})


class InfinitudeSystem:
    """Representation of system-wide Infinitude data."""

    def __init__(self, infinitude: Infinitude) -> None:
        """Initialize the InfinitudeSystem object."""
        self._infinitude = infinitude

    @property
    def _config(self) -> dict:
        """Raw Infinitude config data for the system."""
        return self._infinitude._config

    @property
    def _status(self):
        """Raw Infinitude status data for the system."""
        return self._infinitude._status

    @property
    def temperature_unit(self) -> TemperatureUnit | None:
        """Unit of temperature used by the system."""
        val = self._status.get("cfgem")
        if not val:
            return None
        unit = next((u for u in TemperatureUnit if u.value == val), None)
        if unit is None:
            _LOGGER.warn("'%s' is an unknown TemperatureUnit", unit)
        return unit

    @property
    def local_time(self) -> datetime | None:
        """Local time."""
        localtime_str = self._status.get("localTime")
        try:
            # localTime string can include a TZ offset in some systems.  It should be stripped off
            # since the timestamp is already in the local time.
            matches = match(
                r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})?$",
                localtime_str,
            )
            localtime_str = matches.group(1)
            localtime_dt = datetime.strptime(localtime_str, "%Y-%m-%dT%H:%M:%S")
        except TypeError:
            _LOGGER.info(
                "Unable to convert system localTime '%s' to datetime. Using now() instead.",
                localtime_str,
            )
            localtime_dt = datetime.now()
        return localtime_dt

    @property
    def hvac_mode(self) -> HVACMode | None:
        """HVAC mode."""
        val = self._config.get("mode")
        if not val:
            return None
        mode = next((m for m in HVACMode if m.value == val), None)
        if mode is None:
            _LOGGER.warn("'%s' is an unknown HVACMode", mode)
        return mode

    @property
    def filter_level(self) -> int | None:
        """Filter level."""
        val = self._status.get("filtrlvl")
        if not val:
            return None
        return int(val)

    @property
    def humidifier_state(self) -> HumidifierState | None:
        """Humidifer state."""
        val = self._status.get("humid")
        if not val:
            return None
        state = next((s for s in HVACMode if s.value == val), None)
        if state is None:
            _LOGGER.warn("'%s' is an unknown HumidifierState", state)
        return state

    @property
    def humidifier_level(self) -> int | None:
        """Humidifier pad level."""
        val = self._status.get("humlvl")
        if not val:
            return None
        return int(val)

    @property
    def ventilator_level(self) -> int | None:
        """ventilator pre-filter level."""
        val = self._status.get("ventlvl")
        if not val:
            return None
        return int(val)

    @property
    def uv_level(self) -> int | None:
        """UV lamp level."""
        val = self._status.get("uvlvl")
        if not val:
            return None
        return int(val)

    @property
    def temperature_outside(self) -> int | None:
        """Outside temperature."""
        val = self._status.get("oat")
        if not val:
            return None
        return int(val)

    @property
    def airflow_cfm(self) -> float | None:
        """System airflow in CFM."""
        idu = self._status.get("idu")
        if not idu:
            return None
        cfm = idu.get("cfm")
        if not cfm:
            return None
        return float(cfm)

    @property
    def idu_modulation(self) -> int | None:
        """Indoor unit gas valve modulation percentage.

        Only get this if the IDU type is 'furnacemodulating'
        """
        idu = self._status.get("idu")
        if not idu:
            return None
        if idu.get("type") == "furnacemodulating":
            idu_opstat = idu.get("opstat")
            if idu_opstat.isnumeric():
                return int(idu_opstat)
            else:
                return 0
        return None


class InfinitudeZone:
    """Representation of zone-specific Infinitude data."""

    def __init__(self, infinitude: Infinitude, id: str) -> None:
        """Initialize the InfinitudeZone object."""
        self._infinitude = infinitude
        self.id = id

        self._activity_next = None
        self._activity_next_start = None
        self._activity_scheduled = None
        self._activity_scheduled_start = None

    @property
    def _config(self) -> dict:
        """Raw Infinitude config data for the zone."""
        all_zones = self._infinitude._config.get("zones", {}).get("zone", [])
        zone_config = next(
            (zone for zone in all_zones if zone.get("id") == self.id), {}
        )
        return zone_config

    @property
    def _status(self):
        """Raw Infinitude status data for the zone."""
        all_zones = self._infinitude._status.get("zones", {}).get("zone", [])
        zone_status = next(
            (zone for zone in all_zones if zone.get("id") == self.id), {}
        )
        return zone_status

    def _update_activities(self):
        while self._activity_next is None:
            dt = self._infinitude.system.local_time
            day_name = dt.strftime("%A")
            program = next(
                (day for day in self._config["program"]["day"] if day["id"] == day_name)
            )
            for period in program["period"]:
                if period["enabled"] == "off":
                    continue
                period_hh, period_mm = period["time"].split(":")
                period_dt = datetime(
                    dt.year, dt.month, dt.day, int(period_hh), int(period_mm)
                )
                if period_dt < dt:
                    self._activity_scheduled = period["activity"]
                    self._activity_scheduled_start = period_dt
                if period_dt >= dt:
                    self._activity_next = period["activity"]
                    self._activity_next_start = period_dt
                    break
            dt = datetime(year=dt.year, month=dt.month, day=dt.day) + timedelta(days=1)

    @property
    def index(self):
        """0-based index for the zone, for use in the REST API."""
        return int(self.id) - 1

    @property
    def name(self) -> str | None:
        """Name of the zone."""
        val = self._status.get("name")
        if not val:
            return None
        return val

    @property
    def enabled(self) -> bool | None:
        """Is the zone enabled."""
        val = self._status.get("enabled")
        if not val:
            return None
        return val == "on"

    @property
    def temperature_unit(self) -> TemperatureUnit | None:
        """Unit of temperature used by the system."""
        return self._infinitude.system.temperature_unit

    @property
    def temperature_current(self) -> float | None:
        """Current temperature."""
        val = self._status.get("rt")
        if not val:
            return None
        return float(val)

    @property
    def temperature_cool(self) -> float | None:
        """Target cooling temperature."""
        val = self._status.get("clsp")
        if not val:
            return None
        return float(val)

    @property
    def temperature_heat(self) -> float | None:
        """Target heating temperature."""
        val = self._status.get("htsp")
        if not val:
            return None
        return float(val)

    @property
    def humidity_current(self) -> int | None:
        """Current humidity."""
        val = self._status.get("rh")
        if not val:
            return None
        return int(val)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """HVAC mode used by the system."""
        return self._infinitude.system.hvac_mode

    @property
    def hvac_action(self) -> HVACAction | None:
        """HVAC action."""
        val = self._status.get("zoneconditioning")
        if not val:
            return None
        action = next((a for a in HVACAction if a.value == val), None)
        if action is None:
            _LOGGER.warn("'%s' is an unknown HVACAction", action)
        return action

    @property
    def fan_mode(self) -> FanMode | None:
        """Fan mode."""
        val = self._status.get("fan")
        if not val:
            return None
        fan = next((f for f in FanMode if f.value == val), None)
        if fan is None:
            _LOGGER.warn("'%s' is an unknown FanState", fan)
        return fan

    @property
    def hold_state(self) -> HoldState | None:
        """Hold state."""
        val = self._config.get("hold")
        if not val:
            return None
        hold = next((h for h in HoldState if h.value == val), None)
        if hold is None:
            _LOGGER.warn("'%s' is an unknown HoldState", hold)
        return hold

    @property
    def hold_activity(self) -> Activity | None:
        """Hold activity."""
        val = self._status.get("holdActivity")
        if not val:
            return None
        activity = next((a for a in Activity if a.value == val), None)
        if activity is None:
            _LOGGER.warn("'%s' is an unknown Activity", activity)
        return activity

    @property
    def hold_until(self) -> str | None:
        """Hold until time as "HH:MM"."""
        val = self._status.get("otmr")
        if not isinstance(val, str):
            return None
        return val

    @property
    def hold_mode(self) -> HoldMode | None:
        """Hold mode."""
        if self.hold_state == HoldState.ON:
            if self.hold_until is not None:
                return HoldMode.UNTIL
            else:
                return HoldMode.INDEFINITE
        return HoldMode.OFF

    @property
    def activity_current(self) -> Activity | None:
        """Current activity."""
        val = self._status.get("currentActivity")
        if not val:
            return None
        activity = next((a for a in Activity if a.value == val), None)
        if activity is None:
            _LOGGER.warn("'%s' is an unknown Activity", activity)
        return activity

    @property
    def activity_scheduled(self) -> Activity | None:
        """Currently scheduled activity."""
        activity = next(
            (a for a in Activity if a.value == self._activity_scheduled), None
        )
        if activity is None:
            _LOGGER.warn("'%s' is an unknown Activity", activity)
        return activity

    @property
    def activity_scheduled_start(self) -> datetime | None:
        """Time when the currently scheduled activity started."""
        return self._activity_scheduled_start

    @property
    def activity_next(self) -> Activity | None:
        """Next scheduled activity."""
        activity = next((a for a in Activity if a.value == self._activity_next), None)
        if activity is None:
            _LOGGER.warn("'%s' is an unknown Activity", activity)
        return activity

    @property
    def activity_next_start(self) -> datetime | None:
        """Time when the next scheduled activity will start."""
        return self._activity_next_start

    @property
    def occupancy(self) -> Occupancy | None:
        """Occupancy of the zone."""
        val = self._status.get("occupancy")
        if not val:
            return None
        occupancy = next((o for o in Occupancy if o.value == val), None)
        if occupancy is None:
            _LOGGER.warn("'%s' is an unknown Occupancy", occupancy)
        return occupancy
