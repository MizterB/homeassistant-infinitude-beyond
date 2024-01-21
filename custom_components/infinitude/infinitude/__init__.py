"""Define a base client for interacting with Infinitude."""
import asyncio
import logging
from typing import Optional

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

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

        self.status: dict = {}
        self.config: dict = {}
        self.energy: dict = {}

        if not self._session or self._session.closed:
            self._session = ClientSession()

        self.system: InfinitudeSystem
        self.zones: dict[int, InfinitudeZone]

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

    def _compare_data(self, old, new, path=""):
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
        success = await self.update()
        if not success:
            _LOGGER.error(
                "Unable to connect to Infinitude at %s:%s", self.host, self.port
            )

        self.system = InfinitudeSystem(self)
        self.zones = {}
        for zone in self.config.get("zones", {}).get("zone", []):
            zone_id = zone.get("id")
            self.zones[zone_id] = InfinitudeZone(self, zone_id)

    async def update(self) -> bool:
        """Update all data from Infinitude."""
        try:
            async with asyncio.timeout(UPDATE_TIMEOUT):
                _LOGGER.debug("Updating status, config, and energy")
                status, config, energy = await asyncio.gather(
                    self._fetch_status(), self._fetch_config(), self._fetch_energy()
                )

                if self.status == {}:
                    self.status = status
                else:
                    await self.on_status_change(self.status, status)

                if self.config == {}:
                    self.config = config
                else:
                    await self.on_config_change(self.config, config)

                if self.energy == {}:
                    self.energy = energy
                else:
                    await self.on_energy_change(self.energy, energy)

        except asyncio.TimeoutError as e:
            _LOGGER.error("Update timed out after %s seconds", UPDATE_TIMEOUT)
            return False

        return True

    async def on_status_change(self, old: dict, new: dict) -> None:
        """Status change handler."""
        if old != {}:
            diff = self._compare_data(old, new)
            _LOGGER.debug("Status changed: %s", diff)
        self.status = new

    async def on_config_change(self, old: dict, new: dict) -> None:
        """Config change handler."""
        if old != {}:
            diff = self._compare_data(old, new)
            _LOGGER.debug("Config changed: %s", diff)
        self.config = new

    async def on_energy_change(self, old: dict, new: dict) -> None:
        """Energy change handler."""
        if old != {}:
            diff = self._compare_data(old, new)
            _LOGGER.debug("Energy changed: %s", diff)
        self.energy = new


class InfinitudeSystem:
    """Representation of system-wide Infinitude data."""

    def __init__(self, infinitude: Infinitude) -> None:
        """Initialize the InfinitudeSystem object."""
        self._infinitude = infinitude

    @property
    def config(self) -> dict:
        """Raw Infinitude config data for the system."""
        return self._infinitude.config

    @property
    def status(self):
        """Raw Infinitude status data for the system."""
        return self._infinitude.status

    @property
    def cfgem(self) -> str | None:
        """Value of 'cfgem'."""
        val = self.status.get("cfgem")
        if not val:
            return None
        return val

    @property
    def cfgtype(self) -> str | None:
        """Value of 'cfgtype'."""
        val = self.status.get("cfgtype")
        if not val:
            return None
        return val

    @property
    def filtrlvl(self) -> int | None:
        """Value of 'filtrlvl'."""
        val = self.status.get("filtrlvl")
        if not val:
            return None
        return int(val)

    @property
    def humid(self) -> str | None:
        """Value of 'humid'."""
        val = self.status.get("humid")
        if not val:
            return None
        return val

    @property
    def humlvl(self) -> int | None:
        """Value of 'humlvl'."""
        val = self.status.get("humlvl")
        if not val:
            return None
        return int(val)

    @property
    def localTime(self) -> str | None:
        """Value of 'localTime'."""
        val = self.status.get("localTime")
        if not val:
            return None
        return val

    @property
    def mode(self) -> str | None:
        """Value of 'mode'."""
        val = self.status.get("mode")
        if not val:
            return None
        return val

    @property
    def oat(self) -> int | None:
        """Value of 'oat'."""
        val = self.status.get("oat")
        if not val:
            return None
        return int(val)

    @property
    def oprstsmsg(self) -> str | None:
        """Value of 'oprstsmsg'."""
        val = self.status.get("oprstsmsg")
        if not val:
            return None
        return val

    @property
    def uvlvl(self) -> int | None:
        """Value of 'uvlvl'."""
        val = self.status.get("uvlvl")
        if not val:
            return None
        return int(val)

    @property
    def vacatrunning(self) -> str | None:
        """Value of 'vacatrunning'."""
        val = self.status.get("vacatrunning")
        if not val:
            return None
        return val

    @property
    def ventlvl(self) -> int | None:
        """Value of 'ventlvl'."""
        val = self.status.get("ventlvl")
        if not val:
            return None
        return int(val)

    @property
    def version(self) -> str | None:
        """Value of 'version'."""
        val = self.status.get("version")
        if not val:
            return None
        return val


class InfinitudeZone:
    """Representation of zone-specific Infinitude data."""

    def __init__(self, infinitude: Infinitude, id: str) -> None:
        """Initialize the InfinitudeZone object."""
        self._infinitude = infinitude
        self.id = id

    @property
    def index(self):
        """0-based index for the zone, for use in the REST API."""
        return int(self.id) - 1

    @property
    def config(self) -> dict:
        """Raw Infinitude config data for the zone."""
        all_zones = self._infinitude.config.get("zones", {}).get("zone", [])
        zone_config = next(
            (zone for zone in all_zones if zone.get("id") == self.id), {}
        )
        return zone_config

    @property
    def status(self):
        """Raw Infinitude status data for the zone."""
        all_zones = self._infinitude.status.get("zones", {}).get("zone", [])
        zone_status = next(
            (zone for zone in all_zones if zone.get("id") == self.id), {}
        )
        return zone_status

    @property
    def setpoint_cool(self) -> float | None:
        """Target cooling temperature."""
        val = self.status.get("clsp")
        if not val:
            return None
        return float(val)

    @property
    def current_activity(self) -> str | None:
        """Current activity."""
        val = self.status.get("currentActivity")
        if not val:
            return None
        return val

    @property
    def damper_position(self) -> int | None:
        """Damper position."""
        val = self.status.get("damperposition")
        if not val:
            return None
        return int(val)

    @property
    def enabled(self) -> bool | None:
        """Is the zone enabled."""
        val = self.status.get("enabled")
        if not val:
            return None
        return val == "on"

    @property
    def fan(self) -> str | None:
        """Fan state."""
        val = self.status.get("fan")
        if not val:
            return None
        return val

    @property
    def hold(self) -> str | None:
        """Hold state."""
        val = self.status.get("hold")
        if not val:
            return None
        return val

    @property
    def setpoint_heat(self) -> float | None:
        """Target heating temperature."""
        val = self.status.get("htsp")
        if not val:
            return None
        return float(val)

    @property
    def name(self) -> str | None:
        """Name of the zone."""
        val = self.status.get("name")
        if not val:
            return None
        return val

    @property
    def otmr(self) -> dict | None:
        """otmr description is TBD"""
        val = self.status.get("otmr")
        if not val:
            return {}
        return val

    @property
    def humidity(self) -> int | None:
        """Current humidity."""
        val = self.status.get("rh")
        if not val:
            return None
        return int(val)

    @property
    def temperature(self) -> float | None:
        """Current temperature."""
        val = self.status.get("rt")
        if not val:
            return None
        return float(val)

    @property
    def zone_conditioning(self) -> str | None:
        """Zone conditioning state."""
        val = self.status.get("zoneconditioning")
        if not val:
            return None
        return val


async def main() -> None:
    """Test the Infinitude API."""
    logging.basicConfig(level=logging.DEBUG)
    session = ClientSession()
    infinitude = Infinitude("infinitude.chadsville.lan", 3000, session=session)
    await infinitude.connect()
    ...

    # await infinitude._put("/api/config", {"blight": 1})
    # await infinitude._put("/api/1/hold", {"activity": "home", "until": "23:45"})
    # await infinitude._put(
    #     "/api/1/hold", {"hold": "off", "holdActivity": "", "otmr": ""}
    # )
    while True:
        await infinitude.update()
        await asyncio.sleep(15)
    ...

    session.close()


asyncio.run(main())
