"""Define a base client for interacting with Infinitude."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
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
    HeatSource,  
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT: int = 30
UPDATE_TIMEOUT: int = 30


class Infinitude:
    """Object for interacting with the Infinitude API."""

    def __init__(
        self,
        host: str,
        port: int = 3000,
        ssl: bool = False,
        *,
        session: Optional[ClientSession] = None,
    ) -> None:
        """Initialize the Infinitude API."""
        self.host: str = host
        self.port: str = port
        self.ssl = ssl
        self._session: ClientSession = session

        self._status: dict = {}
        self._config: dict = {}
        self._energy: dict = {}
        self._profile: dict = {}

        if not self._session or self._session.closed:
            self._session = ClientSession()

        self.system: InfinitudeSystem
        self.zones: dict[int, InfinitudeZone]

    @property
    def url(self):
        """Get the base URL to connect to Infinitude."""
        protocol = "http"
        if self.ssl:
            protocol = "https"
        return f"{protocol}://{self.host}:{self.port}"

    async def _get(self, endpoint: str, **kwargs) -> dict:
        """Make a GET request to Infinitude."""
        url = f"{self.url}{endpoint}"
        try:
            async with self._session.get(url, **kwargs) as resp:
                data: dict = await resp.json(content_type=None)
                resp.raise_for_status()
                return data
        except ClientError as e:
            _LOGGER.error(e)

    async def _post(self, endpoint: str, data: dict, **kwargs) -> dict:
        """Make a POST request to Infinitude."""
        url = f"{self.url}{endpoint}"
        try:
            _LOGGER.debug("POST %s with %s and %s", url, data, kwargs)
            async with self._session.post(url, data=data, **kwargs) as resp:
                _LOGGER.debug(
                    "POST RESPONSE from %s with %s and %s is: %s",
                    url,
                    data,
                    kwargs,
                    await resp.text(),
                )
                resp.raise_for_status()
                resp_json: dict = await resp.json(content_type=None)
                return resp_json
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
        if old is None or new is None:
            return None
        diff = {}
        for key in old.keys() | new.keys():  # Union of keys
            new_path = f"{path}/{key}" if path else key

            if key not in old:
                diff[new_path] = ("Missing in old dict", new[key])
            elif key not in new:
                diff[new_path] = (old[key], "Missing in new dict")
            elif isinstance(old[key], dict) and isinstance(new[key], dict):
                deeper_diff = self._compare_data(old[key], new[key], path=new_path)
                if deeper_diff:
                    diff.update(deeper_diff)
            elif isinstance(old[key], list) and isinstance(new[key], list):
                # Compare list items individually for differences
                for i, item1 in enumerate(old[key]):
                    if i >= len(new[key]):
                        diff[f"{new_path}[{i}]"] = (item1, "Missing in new list")
                    elif isinstance(item1, dict) and isinstance(new[key][i], dict):
                        deeper_diff = self._compare_data(
                            item1, new[key][i], path=f"{new_path}[{i}]"
                        )
                        if deeper_diff:
                            diff.update(deeper_diff)
                    elif item1 != new[key][i]:
                        diff[f"{new_path}[{i}]"] = (item1, new[key][i])
                for i in range(len(old[key]), len(new[key])):
                    diff[f"{new_path}[{i}]"] = ("Missing in old list", new[key][i])
            elif old[key] != new[key]:
                diff[new_path] = (old[key], new[key])
        return diff

    async def _fetch_status(self) -> dict:
        """Retrieve status data from Infinitude."""
        data = await self._get("/api/status/")
        status = self._simplify_json(data)
        return status

    async def _fetch_config(self) -> dict:
        """Retrieve configuration data from Infinitude."""
        resp = await self._get("/api/config/")
        data = resp.get("data", {})
        config = self._simplify_json(data)
        return config

    async def _fetch_energy(self) -> dict:
        """Retrieve energy data from Infinitude."""
        data = await self._get("/energy.json")
        energy = self._simplify_json(data)
        return energy

    async def _fetch_profile(self) -> dict:
        """Retrieve profile data from Infinitude."""
        resp = await self._get("/profile.json")
        data = resp.get("system_profile", {})
        profile = self._simplify_json(data)
        return profile

    async def connect(self) -> None:
        """Connect to Infinitude."""
        try:
            async with asyncio.timeout(CONNECT_TIMEOUT):
                _LOGGER.debug("Connecting to Infinitude")
                status, config, energy, profile = await asyncio.gather(
                    self._fetch_status(),
                    self._fetch_config(),
                    self._fetch_energy(),
                    self._fetch_profile(),
                )
                self._status = status
                self._config = config
                self._energy = energy
                self._profile = profile

        except asyncio.TimeoutError as e:
            _LOGGER.error(
                "Failed to connect to Infinitude at %s:%s after %s seconds",
                self.host,
                self.port,
                CONNECT_TIMEOUT,
            )
            raise ConnectionError(e)

        self.system = InfinitudeSystem(self)
        self.zones = {}
        for zone in self._config.get("zones", {}).get("zone", []):
            zone_id = zone.get("id")
            self.zones[zone_id] = InfinitudeZone(self, zone_id)
            self.zones[zone_id]._update_activities()

    async def update(self) -> bool:
        """Update variable data from Infinitude."""
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
            raise TimeoutError(e)

        for zone in self.zones.values():
            zone._update_activities()

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
    def _status(self) -> dict:
        """Raw Infinitude status data for the system."""
        return self._infinitude._status

    @property
    def _energy(self) -> dict:
        """Raw Infinitude energy data for the system."""
        return self._infinitude._energy

    @property
    def _profile(self) -> dict:
        """Raw Infinitude profile data for the system."""
        return self._infinitude._profile

    @property
    def brand(self) -> str | None:
        """Brand of the system."""
        val = self._profile.get("brand")
        if not val:
            return None
        return str(val)

    @property
    def model(self) -> str | None:
        """Model of the system."""
        val = self._profile.get("model")
        if not val:
            return None
        return str(val)

    @property
    def serial(self) -> str | None:
        """Serial number of the system."""
        val = self._profile.get("serial")
        if not val:
            return None
        return str(val)

    @property
    def firmware(self) -> str | None:
        """Firmware revision of the system."""
        val = self._profile.get("firmware")
        if not val:
            return None
        return str(val)

    @property
    def temperature_unit(self) -> TemperatureUnit | None:
        """Unit of temperature used by the system."""
        val = self._status.get("cfgem")
        if not val:
            return None
        unit = next((u for u in TemperatureUnit if u.value == val), None)
        if unit is None:
            _LOGGER.warning("'%s' is an unknown TemperatureUnit", unit)
        return unit

    @property
    def local_time(self) -> datetime | None:
        """Local time."""
        localtime_str = self._status.get("localTime")
        try:
            # localTime string does not always contain a time zone
            matches = match(
                r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})?$",
                localtime_str,
            )
            localtime_naive_str = matches.group(1)
            localtime_naive_dt = datetime.strptime(
                localtime_naive_str, "%Y-%m-%dT%H:%M:%S"
            )
        except TypeError:
            _LOGGER.debug(
                "Unable to convert system localTime '%s' to datetime. Using now() instead.",
                localtime_str,
            )
            localtime_naive_dt = datetime.now()
        # Add TZ data
        localtime_dt = localtime_naive_dt.replace(tzinfo=self.local_timezone)
        return localtime_dt

    @property
    def local_timezone(self) -> timezone:
        """Gets the time zone.

        Returns the value provided by Infinitude's localTime if provided.
        Otherwise, returns this host system's timezone
        """
        localtime_str = self._status.get("localTime")
        # localTime string does not always contain a time zone
        # Use if provided, otherwise assume the system TZ
        matches = match(
            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})?$",
            localtime_str,
        )
        # Parse the TZ offset if found
        if matches.lastindex == 2:
            offset_str = matches.group(2)
            hours, minutes = map(int, offset_str.split(":"))
            offset = timedelta(hours=hours, minutes=minutes)
            tz = timezone(offset)
        else:
            tz = datetime.now().astimezone().tzinfo
        return tz

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

    async def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""

        endpoint = f"/api/config"
        data = {"mode": f"{hvac_mode.value}"}
        await self._infinitude._post(endpoint, data)

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
        state = next((s for s in HumidifierState if s.value == val), None)
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
    def furnace_status(self) -> str | None:
        """ System Furnace Status """
        idu = self._status.get("idu")
        if not idu:
            return None
        fstat = idu.get("opstat")
        if not fstat:
            return None
        return str(fstat)
        
    @property
    def heatpump_status(self) -> str | None:
        """ System Furnace Status """
        odu = self._status.get("odu")
        if not odu:
            return None
        hstat = odu.get("opstat")
        if not hstat:
            return None
        return str(hstat)    

    @property
    def heatpump_mode(self) -> str | None:
        """ System Furnace Status """
        odu = self._status.get("odu")
        if not odu:
            return None
        hmod = odu.get("opmode")
        if not hmod:
            return None
        return str(hmod)    

    @property
    def heat_source(self) -> str | None:
        """ System Furnace Status """
        hs = self._config.get("heatsource")
        if not hs:
            return None
        if hs  == "idu only":
           return str(HeatSource.GAS.value) 
        elif hs  == "odu only":
           return str(HeatSource.HEATPUMP.value) 
        elif hs  == "system":
           return str(HeatSource.SYSTEM.value) 
        else:
           return None  
            
    async def set_heat_source(self, heatsource:HeatSource) -> None:
        if heatsource == HeatSource.SYSTEM:
            data = {"heatsource": "system"}
        elif heatsource == HeatSource.GAS:
            data = {"heatsource": "idu only"}
        elif heatsource == HeatSource.HEATPUMP:
            data = {"heatsource": "odu only"}			
        _LOGGER.debug("API Call : {}".format(data))	
        endpoint = f"/api/config"
        await self._infinitude._post(endpoint, data)
        await self._infinitude.update()


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

    @property
    def energy(self) -> dict | None:
        """Energy data."""
        if isinstance(self._energy, dict) and self._energy != {}:
            return self._energy
        else:
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
    def _status(self) -> dict:
        """Raw Infinitude status data for the zone."""
        all_zones = self._infinitude._status.get("zones", {}).get("zone", [])
        zone_status = next(
            (zone for zone in all_zones if zone.get("id") == self.id), {}
        )
        return zone_status

    def _update_activities(self) -> None:
        dt = self._infinitude.system.local_time
        activity_scheduled = None
        activity_scheduled_start = None
        activity_next = None
        activity_next_start = None
        while activity_next is None:
            day_name = dt.strftime("%A")
            program = next(
                day for day in self._config["program"]["day"] if day["id"] == day_name
            )
            for period in program["period"]:
                if period["enabled"] == "off":
                    continue
                period_hh, period_mm = period["time"].split(":")
                period_dt = datetime(
                    year=dt.year,
                    month=dt.month,
                    day=dt.day,
                    hour=int(period_hh),
                    minute=int(period_mm),
                    tzinfo=self._infinitude.system.local_timezone,
                )
                if period_dt < dt:
                    activity_scheduled = period["activity"]
                    activity_scheduled_start = period_dt
                if period_dt >= dt:
                    activity_next = period["activity"]
                    activity_next_start = period_dt
                    break
            dt = datetime(
                year=dt.year,
                month=dt.month,
                day=dt.day,
                tzinfo=self._infinitude.system.local_timezone,
            ) + timedelta(days=1)

        self._activity_scheduled = activity_scheduled
        self._activity_scheduled_start = activity_scheduled_start
        self._activity_next = activity_next
        self._activity_next_start = activity_next_start

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
    def fan_mode(self) -> FanMode | None:
        """Fan mode."""
        val = self._status.get("fan")
        if not val:
            return None
        mode = next((m for m in FanMode if m.value == val), None)
        if mode is None:
            _LOGGER.warn("'%s' is an unknown FanMode", mode)
        return mode

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
        val = self._config.get("holdActivity")
        if not val or val == {}:
            return None
        activity = next((a for a in Activity if a.value == val), None)
        if activity is None:
            _LOGGER.warn("'%s' is an unknown Activity", activity)
        return activity

    @property
    def hold_until(self) -> datetime | None:
        """Hold until time."""
        val = self._status.get("otmr")
        if not isinstance(val, str):
            return None
        until_hh, until_mm = val.split(":")
        dt = self._infinitude.system.local_time
        until_dt = datetime(
            dt.year,
            dt.month,
            dt.day,
            int(until_hh),
            int(until_mm),
            tzinfo=self._infinitude.system.local_timezone,
        )
        if until_dt < dt:
            until_dt = until_dt + timedelta(days=1)
        return until_dt

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

    async def set_hold_mode(
        self,
        mode: HoldMode | None = None,
        activity: Activity | None = None,
        until: datetime | None = None,
    ) -> None:
        """Set hold mode.

        Default is to hold the current activity until the next scheduled activity
        """

        # Default mode: Until time or next activity
        if mode is None:
            mode = HoldMode.UNTIL

        # Default activity: current activity
        if activity is None:
            activity = self.activity_current

        # Default until: Next activity time
        if until is None:
            until = self.activity_next_start

        # Round until to the nearest 15-min interval
        until_min = until.minute
        nearest_fifteen = int(round(until_min / 15) * 15)
        until = until + timedelta(minutes=nearest_fifteen - until_min)

        # Convert until to string
        until_str = until.strftime("%H:%M")

        # Use dedicated API endpoint for hold
        # See https://github.com/nebulous/infinitude/blob/3672528b5b977c60508c00f2cae092e616f4eef3/infinitude#L194
        if mode == HoldMode.OFF:
            data = {
                "hold": HoldState.OFF.value,
                "activity": "",
                "until": "",
            }
        elif mode == HoldMode.INDEFINITE:
            data = {
                "hold": HoldState.ON.value,
                "activity": activity.value,
                "until": "forever",
            }
        elif mode == HoldMode.UNTIL:
            data = {
                "hold": HoldState.ON.value,
                "activity": activity.value,
                "until": until_str,
            }

        endpoint = f"/api/{self.id}/hold"
        await self._infinitude._post(endpoint, data)
        await self._infinitude.update()

    async def set_temperature(
        self,
        temperature: float | None = None,
        temperature_heat: float | None = None,
        temperature_cool: float | None = None,
    ) -> None:
        """Set new target temperature."""

        cool = self.temperature_cool
        if temperature_cool:
            cool = temperature_cool
        elif temperature:
            cool = temperature

        heat = self.temperature_heat
        if temperature_heat:
            heat = temperature_heat
        elif temperature:
            heat = temperature

        if heat > cool:
            raise ValueError(
                "Heating temperature (%s) cannot be greater than cooling temperature (%s)",
                heat,
                cool,
            )

        # Update the 'manual' activity with the updated temperatures
        # Use dedicated API endpoint for activity config
        # See https://github.com/nebulous/infinitude/blob/3672528b5b977c60508c00f2cae092e616f4eef3/infinitude#L253
        endpoint = f"/api/{self.id}/activity/{Activity.MANUAL.value}"
        data = {"htsp": f"{heat:.1f}", "clsp": f"{cool:.1f}"}
        await self._infinitude._post(endpoint, data)

        # Hold on the updated 'manual' activity until the next schedule change
        await self.set_hold_mode(mode=HoldMode.UNTIL, activity=Activity.MANUAL)
        await self._infinitude.update()

    async def set_fan_mode(self, fan_mode: FanMode) -> None:
        """Set the fan mode."""

        # Update the 'manual' activity with the updated fan mode
        # Use dedicated API endpoint for activity config
        # See https://github.com/nebulous/infinitude/blob/3672528b5b977c60508c00f2cae092e616f4eef3/infinitude#L253
        endpoint = f"/api/{self.id}/activity/{Activity.MANUAL.value}"
        data = {"fan": f"{fan_mode.value}"}
        await self._infinitude._post(endpoint, data)

        # Hold on the updated 'manual' activity until the next schedule change
        await self.set_hold_mode(mode=HoldMode.UNTIL, activity=Activity.MANUAL)
        await self._infinitude.update()
