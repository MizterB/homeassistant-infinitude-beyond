"""Define a base client for interacting with Infinitude."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from re import match

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

from .const import (
    Activity,
    FanMode,
    HeatSource,
    HoldMode,
    HoldState,
    HumidifierState,
    HVACAction,
    HVACMode,
    Occupancy,
    TemperatureUnit,
)

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT: int = 30
UPDATE_TIMEOUT: int = 30

# Known equipment status values -> translation slugs. Unknown values pass
# through as-is (see _opstat_slug).
_OPSTAT_SLUGS = {
    "off": "off",
    "stage 1": "stage_1",
    "stage 2": "stage_2",
    "stage 3": "stage_3",
    "stage 4": "stage_4",
    "stage 5": "stage_5",
    "defrost": "defrost",
    "dehumidify": "dehumidify",
}

# Infinitude config <-> heat source slug.
_HEAT_SOURCE_FROM_CONFIG = {
    "system": HeatSource.SYSTEM,
    "idu only": HeatSource.GAS,
    "odu only": HeatSource.HEATPUMP,
}
_HEAT_SOURCE_TO_CONFIG = {v: k for k, v in _HEAT_SOURCE_FROM_CONFIG.items()}


def _opstat_slug(value) -> str | None:
    """Slug for a known staging status; the raw value for anything else."""
    if value in (None, ""):
        return None
    return _OPSTAT_SLUGS.get(str(value).strip().lower(), str(value))


def _vacation_datetime_str(dt: datetime) -> str:
    """Format a vacation timestamp the way Infinitude's UI writes it.

    Local wall-clock, minute precision, no offset (e.g. 2026-07-01T10:00).
    """
    return dt.strftime("%Y-%m-%dT%H:%M")


class Infinitude:
    """Object for interacting with the Infinitude API."""

    def __init__(
        self,
        host: str,
        port: int = 3000,
        ssl: bool = False,
        *,
        session: ClientSession | None = None,
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
        self._warned_post_non_json: bool = False

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
        """GET from Infinitude.

        Raise ConnectionError on any request failure. Returning None here meant
        the fetchers blew up later on a None response (issue #20); raising lets
        connect() report it as a connection problem.
        """
        url = f"{self.url}{endpoint}"
        try:
            async with self._session.get(url, **kwargs) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except ClientError as e:
            # Debug only: this fires every update cycle during an outage.
            _LOGGER.debug("GET %s failed: %s", url, e)
            raise ConnectionError from e

    async def _post(self, endpoint: str, data: dict, **kwargs) -> dict | None:
        """POST to Infinitude.

        Some Infinitude versions return an empty or non-JSON body on a
        successful POST, and nothing here uses the response. Parse it only when
        it's there; never let a bad or empty body raise, or a temp/hold change
        shows an error in HA even though it actually worked.
        """
        url = f"{self.url}{endpoint}"
        try:
            _LOGGER.debug("POST %s with %s and %s", url, data, kwargs)
            async with self._session.post(url, data=data, **kwargs) as resp:
                text = await resp.text()
                _LOGGER.debug(
                    "POST RESPONSE from %s with %s and %s is: %s",
                    url,
                    data,
                    kwargs,
                    text,
                )
                resp.raise_for_status()
                stripped = text.strip()
                if stripped:
                    try:
                        result = json.loads(stripped)
                    except ValueError:
                        result = None
                    if result is not None:
                        if (
                            isinstance(result, dict)
                            and result.get("status") == "fail"
                        ):
                            _LOGGER.warning(
                                "Infinitude reported a failed write to %s: %s",
                                endpoint,
                                result,
                            )
                        return result
                # Empty or non-JSON body: the request still succeeded.
                self._warn_non_json_post(endpoint)
                return None
        except ClientError as e:
            _LOGGER.error(e)

    async def _post_json(self, endpoint: str, payload: dict) -> None:
        """POST a JSON body (used for saving the full systems document)."""
        url = f"{self.url}{endpoint}"
        try:
            _LOGGER.debug("POST(json) %s with %s", url, payload)
            async with self._session.post(url, json=payload) as resp:
                resp.raise_for_status()
        except ClientError as e:
            _LOGGER.error("POST %s failed: %s", url, e)
            raise ConnectionError from e

    async def modify_config(self, changes: dict) -> None:
        """Change system config fields the way the Infinitude UI does.

        Field-level POSTs to /api/config are rejected by current Infinitude
        (they return {"status":"fail"}). The UI saves by posting the whole
        systems document to /systems/infinitude, so mirror that: pull the doc,
        set the fields on its config, post it back.
        """
        doc = await self._get("/systems.json")
        try:
            system = doc["system"][0]
            config = system["config"][0]
        except (KeyError, IndexError, TypeError) as err:
            raise ConnectionError("Unexpected systems document") from err
        for key, value in changes.items():
            config[key] = [value]
        await self._post_json("/systems/infinitude", {"system": [system]})
        await self.update()

    def _warn_non_json_post(self, endpoint: str) -> None:
        """Log once that Infinitude sent an empty or non-JSON POST response."""
        if not self._warned_post_non_json:
            self._warned_post_non_json = True
            _LOGGER.warning(
                "Infinitude returned an empty or non-JSON response to POST %s, "
                "but the request still went through. This usually means an older "
                "Infinitude; if it keeps happening, upgrade to the latest version. "
                "Further messages like this are logged at debug level.",
                endpoint,
            )
        else:
            _LOGGER.debug(
                "Empty or non-JSON POST response from %s (request still went "
                "through).",
                endpoint,
            )

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
        status = self._simplify_json(data)
        return status

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

        except TimeoutError as e:
            _LOGGER.error(
                "Failed to connect to Infinitude at %s:%s after %s seconds",
                self.host,
                self.port,
                CONNECT_TIMEOUT,
            )
            raise ConnectionError from e

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
                status, config, energy = await asyncio.gather(
                    self._fetch_status(), self._fetch_config(), self._fetch_energy()
                )
                await self._update_status(status)
                await self._update_config(config)
                await self._update_energy(energy)
        except TimeoutError as e:
            _LOGGER.error("Update timed out after %s seconds", UPDATE_TIMEOUT)
            raise TimeoutError from e

        for zone in self.zones.values():
            if zone.enabled:
                zone._update_activities()

    async def _update_status(self, status) -> None:
        """Status update handler."""
        try:
            changes = self._compare_data(self._status, status)
            # Filter out changes that are only related to localTime
            significant_changes = {k: v for k, v in changes.items() if k != "localTime"}
            if significant_changes:
                _LOGGER.debug("Status changed: %s", significant_changes)
        except Exception as e:
            _LOGGER.debug("Exception while comparing status changes: %s", e)
        self._status = status

    async def _update_config(self, config) -> None:
        """Config update handler."""
        try:
            changes = self._compare_data(self._config, config)
            if changes:
                _LOGGER.debug("Config changed: %s", changes)
        except Exception as e:
            _LOGGER.debug("Exception while comparing config changes: %s", e)
        self._config = config

    async def _update_energy(self, energy) -> None:
        """Energy update handler."""
        try:
            changes = self._compare_data(self._energy, energy)
            if changes:
                _LOGGER.debug("Energy changed: %s", changes)
        except Exception as e:
            _LOGGER.debug("Exception while comparing energy changes: %s", e)
        self._energy = energy


class InfinitudeSystem:
    """Representation of system-wide Infinitude data."""

    def __init__(self, infinitude: Infinitude) -> None:
        """Initialize the InfinitudeSystem object."""
        self._infinitude = infinitude

    @property
    def _config(self) -> dict:
        """Raw Infinitude config data for the system."""
        return self._infinitude._config or {}

    @property
    def _status(self) -> dict:
        """Raw Infinitude status data for the system."""
        return self._infinitude._status or {}

    @property
    def _energy(self) -> dict:
        """Raw Infinitude energy data for the system."""
        return self._infinitude._energy or {}

    @property
    def _profile(self) -> dict:
        """Raw Infinitude profile data for the system."""
        return self._infinitude._profile or {}

    @property
    def connected(self) -> bool:
        """Whether Infinitude is returning live thermostat data.

        An empty status means Infinitude is reachable but the thermostat isn't
        reporting to it.
        """
        return bool(self._status)

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
            _LOGGER.warning("'%s' is an unknown TemperatureUnit", val)
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
        return localtime_naive_dt.replace(tzinfo=self.local_timezone)

    @property
    def local_timezone(self) -> timezone:
        """Gets the time zone.

        Returns the value provided by Infinitude's localTime if provided.
        Otherwise, returns this host system's timezone.
        """
        localtime_str = self._status.get("localTime")

        # If localTime is not provided, fallback to system timezone
        if localtime_str is None:
            return datetime.now().astimezone().tzinfo

        # Match the datetime string with optional timezone offset
        matches = match(
            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:\d{2})?$",
            localtime_str,
        )
        if matches and matches.lastindex == 2:
            offset_str = matches.group(2)
            hours, minutes = map(int, offset_str.split(":"))

            # Adjust for negative offsets
            if hours < 0:
                minutes = -minutes

            # Sometimes there is timezone variability of a minute or two
            # ...so round to the nearest 5 minutes
            total_minutes = hours * 60 + minutes
            rounded_minutes = 5 * round(total_minutes / 5)
            rounded_hours, rounded_minutes = divmod(rounded_minutes, 60)

            # Generate the timezone object
            offset = timedelta(hours=rounded_hours, minutes=rounded_minutes)
            tz = timezone(offset)
        else:
            # If no timezone offset found, fallback to system timezone
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
            _LOGGER.warning("'%s' is an unknown HVACMode", val)
        return mode

    async def set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        await self._infinitude.modify_config({"mode": hvac_mode.value})

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
            _LOGGER.warning("'%s' is an unknown HumidifierState", val)
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
        """Ventilator pre-filter level."""
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
    def has_idu(self) -> bool:
        """Whether the system reports indoor unit runtime data.

        Variable/communicating indoor units publish an ``idu`` block; simpler
        units (e.g. a fancoil) don't. Used to decide whether the airflow sensor
        is worth registering at all.
        """
        return self._status.get("idu") is not None

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

    @property
    def odu_modulation(self) -> int | None:
        """Outdoor unit compressor modulation percentage.

        Only get this if the ODU type is 'proteus' or 'gs3ngipac'
        """
        odu = self._status.get("odu")
        if not odu:
            return None
        if odu.get("type") in ["proteus", "gs3ngipac"]:
            odu_opstat = odu.get("opstat")
            if odu_opstat.isnumeric():
                return int(odu_opstat)
            if odu_opstat == "dehumidify":
                return 1
            if odu_opstat == "off":
                return 0
        return None

    @property
    def furnace_status(self) -> str | None:
        """Indoor unit operating status."""
        idu = self._status.get("idu")
        if not idu:
            return None
        return _opstat_slug(idu.get("opstat"))

    @property
    def heatpump_status(self) -> str | None:
        """Outdoor unit operating status (heat pump stage)."""
        odu = self._status.get("odu")
        if not odu:
            return None
        return _opstat_slug(odu.get("opstat"))

    @property
    def heatpump_mode(self) -> str | None:
        """Outdoor unit operating mode."""
        odu = self._status.get("odu")
        if not odu:
            return None
        val = odu.get("opmode")
        return str(val) if val else None

    @property
    def heat_source(self) -> str | None:
        """Configured heat source for dual-fuel systems."""
        hs = self._config.get("heatsource")
        if not hs:
            return None
        mapped = _HEAT_SOURCE_FROM_CONFIG.get(str(hs).strip().lower())
        return mapped.value if mapped else None

    async def set_heat_source(self, heatsource: HeatSource) -> None:
        """Set the heat source for a dual-fuel system."""
        await self._infinitude.modify_config(
            {"heatsource": _HEAT_SOURCE_TO_CONFIG[heatsource]}
        )

    @property
    def energy(self) -> dict | None:
        """Energy data."""
        if isinstance(self._energy, dict) and self._energy != {}:
            return self._energy
        else:
            return None

    def _vacation_datetime(self, value) -> datetime | None:
        """Parse a vacation window timestamp, tolerating single-digit fields."""
        if not isinstance(value, str):
            return None
        matches = match(
            r"^(\d{4})-(\d{1,2})-(\d{1,2})T(\d{2}):(\d{2})(?::(\d{2}))?", value
        )
        if not matches:
            return None
        year, month, day, hour, minute = (int(g) for g in matches.groups()[:5])
        second = int(matches.group(6) or 0)
        try:
            return datetime(
                year, month, day, hour, minute, second, tzinfo=self.local_timezone
            )
        except ValueError:
            return None

    @property
    def vacation_state(self) -> str:
        """Derived vacation state: disabled, scheduled, active, or ended."""
        if str(self._config.get("vacat", "off")).lower() != "on":
            return "disabled"
        zones = self._infinitude.zones or {}
        if any(z.activity_current == Activity.VACATION for z in zones.values()):
            return "active"
        now = self.local_time
        start = self._vacation_datetime(self._config.get("vacstart"))
        end = self._vacation_datetime(self._config.get("vacend"))
        if now and start and now < start:
            return "scheduled"
        if now and end and now >= end:
            return "ended"
        return "active"

    @property
    def vacation_enabled(self) -> bool:
        """Whether vacation is enabled in config."""
        return str(self._config.get("vacat", "off")).lower() == "on"

    @property
    def vacation_active(self) -> bool:
        """Whether vacation is currently in effect."""
        return self.vacation_state == "active"

    @property
    def vacation_start(self) -> datetime | None:
        """Configured vacation start."""
        return self._vacation_datetime(self._config.get("vacstart"))

    @property
    def vacation_end(self) -> datetime | None:
        """Configured vacation end."""
        return self._vacation_datetime(self._config.get("vacend"))

    @property
    def vacation_heat(self) -> float | None:
        """Vacation heat (minimum) setpoint."""
        val = self._config.get("vacmint")
        return float(val) if val not in (None, "") else None

    @property
    def vacation_cool(self) -> float | None:
        """Vacation cool (maximum) setpoint."""
        val = self._config.get("vacmaxt")
        return float(val) if val not in (None, "") else None

    @property
    def vacation_fan(self) -> FanMode | None:
        """Vacation fan mode."""
        val = self._config.get("vacfan")
        if not val:
            return None
        return next((f for f in FanMode if f.value == val), None)

    async def set_vacation(
        self,
        *,
        enabled: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        heat: int | None = None,
        cool: int | None = None,
        fan: FanMode | None = None,
    ) -> None:
        """Write vacation config in a single request.

        When enabling without an explicit window (or with a stale/past one),
        default to the next quarter hour .. seven days later.
        """
        # Write local wall-clock: reads apply the system timezone, so the
        # written value must be in that same frame.
        tz = self.local_timezone
        if start is not None:
            start = start.replace(tzinfo=tz) if start.tzinfo is None else start.astimezone(tz)
        if end is not None:
            end = end.replace(tzinfo=tz) if end.tzinfo is None else end.astimezone(tz)

        changes: dict = {}
        if enabled is not None:
            changes["vacat"] = "on" if enabled else "off"
        if start is not None:
            changes["vacstart"] = _vacation_datetime_str(start)
        if end is not None:
            changes["vacend"] = _vacation_datetime_str(end)
        if heat is not None:
            changes["vacmint"] = str(float(heat))
        if cool is not None:
            changes["vacmaxt"] = str(float(cool))
        if fan is not None:
            changes["vacfan"] = fan.value

        if changes.get("vacat") == "on" and start is None and end is None:
            now = self.local_time
            cur_start, cur_end = self.vacation_start, self.vacation_end
            if not cur_start or not cur_end or (now and cur_end <= now):
                base = (now or datetime.now(tz=tz)).replace(second=0, microsecond=0)
                base += timedelta(minutes=(15 - base.minute % 15) % 15 or 15)
                changes["vacstart"] = _vacation_datetime_str(base)
                changes["vacend"] = _vacation_datetime_str(base + timedelta(days=7))

        if not changes:
            return
        await self._infinitude.modify_config(changes)


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
        all_zones = (self._infinitude._config or {}).get("zones", {}).get("zone", [])
        zone_config = next(
            (zone for zone in all_zones if zone.get("id") == self.id), {}
        )
        return zone_config

    @property
    def _status(self) -> dict:
        """Raw Infinitude status data for the zone."""
        all_zones = (self._infinitude._status or {}).get("zones", {}).get("zone", [])
        zone_status = next(
            (zone for zone in all_zones if zone.get("id") == self.id), {}
        )
        return zone_status

    def _update_activities(self) -> None:
        """Compute scheduled and next activities from the program schedule.

        Handles after-midnight times (e.g. 00:00 / 00:15) that may appear
        later in the period list by treating backwards time jumps as
        wrapping into the next day.
        """
        now = self._infinitude.system.local_time
        tz = self._infinitude.system.local_timezone

        activity_scheduled = None
        activity_scheduled_start = None
        activity_next = None
        activity_next_start = None

        if now is None:
            self._activity_scheduled = None
            self._activity_scheduled_start = None
            self._activity_next = None
            self._activity_next_start = None
            return

        try:
            program_days = self._config.get("program", {}).get("day", [])
            if not program_days:
                raise KeyError("Missing program/day schedule in zone config")

            timeline: list[tuple[datetime, str]] = []
            base_date = now.date()

            for day_offset in (-1, 0, 1, 2):
                day_date = base_date + timedelta(days=day_offset)
                day_name = day_date.strftime("%A")

                day_cfg = next(
                    (d for d in program_days if d.get("id") == day_name), None
                )
                if not day_cfg:
                    continue

                periods = day_cfg.get("period", [])
                if not periods:
                    continue

                wrap_days = 0
                prev_minutes = None

                for period in periods:
                    if period.get("enabled") == "off":
                        continue

                    time_str = period.get("time")
                    activity = period.get("activity")
                    if not time_str or not activity:
                        continue

                    hh, mm = map(int, time_str.split(":"))
                    minutes = hh * 60 + mm

                    if prev_minutes is not None and minutes < prev_minutes:
                        wrap_days += 1
                    prev_minutes = minutes

                    period_date = day_date + timedelta(days=wrap_days)
                    period_dt = datetime(
                        period_date.year,
                        period_date.month,
                        period_date.day,
                        hh,
                        mm,
                        tzinfo=tz,
                    )

                    timeline.append((period_dt, activity))

            if not timeline:
                raise ValueError("No enabled periods found in program schedule")

            timeline.sort(key=lambda x: x[0])

            for dt, act in timeline:
                if dt <= now:
                    activity_scheduled = act
                    activity_scheduled_start = dt
                elif dt > now and activity_next is None:
                    activity_next = act
                    activity_next_start = dt
                    break

        except Exception as e:
            _LOGGER.debug(
                "Error updating activities: %s\nZone config is %s", e, self._config
            )

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
            _LOGGER.warning("'%s' is an unknown FanMode", val)
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
            _LOGGER.warning("'%s' is an unknown HVACAction", val)
        return action

    @property
    def hold_state(self) -> HoldState | None:
        """Hold state."""
        val = self._config.get("hold")
        if not val:
            return None
        hold = next((h for h in HoldState if h.value == val), None)
        if hold is None:
            _LOGGER.warning("'%s' is an unknown HoldState", hold)
        return hold

    @property
    def hold_activity(self) -> Activity | None:
        """Hold activity."""
        val = self._config.get("holdActivity")
        if not val or val == {}:
            return None
        activity = next((a for a in Activity if a.value == val), None)
        if activity is None:
            _LOGGER.warning("'%s' is an unknown Activity", val)
        return activity

    @property
    def hold_until(self) -> datetime | None:
        """Hold until time.

        Read 'otmr' from config first: Infinitude writes hold/holdActivity/otmr
        to config synchronously when a hold is set, while the status 'otmr' lags
        until the thermostat next syncs back. Reading status alone briefly
        reports a timed hold as indefinite. Fall back to status for any version
        that doesn't expose otmr in config. An empty value or the literal
        'forever' (indefinite hold) has no time component.
        """
        val = self._config.get("otmr")
        if not isinstance(val, str):
            val = self._status.get("otmr")
        if not isinstance(val, str) or ":" not in val:
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
            _LOGGER.debug("'%s' is an unknown Activity", val)
        return activity

    @property
    def activity_scheduled(self) -> Activity | None:
        """Currently scheduled activity."""
        activity = next(
            (a for a in Activity if a.value == self._activity_scheduled), None
        )
        if activity is None:
            _LOGGER.debug(
                "'%s' is an unknown Scheduled Activity", self._activity_scheduled
            )
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
            _LOGGER.warning("'%s' is an unknown Next Activity", self._activity_next)
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
            _LOGGER.warning("'%s' is an unknown Occupancy", val)
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
        # Include the current fan mode, so we don't restore the fan mode from the previous manual activity
        endpoint = f"/api/{self.id}/activity/{Activity.MANUAL.value}"
        data = {
            "htsp": f"{heat:.1f}",
            "clsp": f"{cool:.1f}",
            "fan": self.fan_mode.value,
        }
        await self._infinitude._post(endpoint, data)

        # Hold on the updated 'manual' activity until the next schedule change
        await self.set_hold_mode(mode=HoldMode.UNTIL, activity=Activity.MANUAL)
        await self._infinitude.update()

    async def set_fan_mode(self, fan_mode: FanMode) -> None:
        """Set the fan mode."""

        # Update the 'manual' activity with the updated fan mode
        # Use dedicated API endpoint for activity config
        # See https://github.com/nebulous/infinitude/blob/3672528b5b977c60508c00f2cae092e616f4eef3/infinitude#L253
        # Include the current target target temperatures, so we don't restore ones from the previous manual activity
        endpoint = f"/api/{self.id}/activity/{Activity.MANUAL.value}"
        data = {
            "fan": f"{fan_mode.value}",
            "htsp": f"{self.temperature_heat:.1f}",
            "clsp": f"{self.temperature_cool:.1f}",
        }
        await self._infinitude._post(endpoint, data)

        # Hold on the updated 'manual' activity until the next schedule change
        await self.set_hold_mode(mode=HoldMode.UNTIL, activity=Activity.MANUAL)
        await self._infinitude.update()
