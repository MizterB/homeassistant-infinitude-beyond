from enum import Enum, IntEnum


class TemperatureUnit(Enum):
    """Temperature units reported by Infinitude (cfgem)."""

    CELSIUS = "C"
    FARENHEIT = "F"


class HoldState(Enum):
    """Hold states reported by Infinitude (hold)."""

    OFF = "off"
    ON = "on"


class HoldMode(Enum):
    """Computed hold modes, based on thermostat display values."""

    OFF = "per schedule"
    INDEFINITE = "hold"
    UNTIL = "hold until"


class FanMode(Enum):
    """Fan modes reported by Infinitude (fan)."""

    AUTO = "off"
    HIGH = "high"
    MEDIUM = "med"
    LOW = "low"


class Activity(Enum):
    """Activity names supported in the API."""

    HOME = "home"
    AWAY = "away"
    SLEEP = "sleep"
    WAKE = "wake"
    MANUAL = "manual"


class ActivityIndex(IntEnum):
    """Indexes assigned to activities in the API."""

    HOME = 0
    AWAY = 1
    SLEEP = 2
    WAKE = 3
    MANUAL = 4


class HVACAction(Enum):
    """HVAC actions reported by Infinitude (zoneconditioning)."""

    ACTIVE_HEAT = "active_heat"
    ACTIVE_COOL = "active_cool"
    PREP_COOL = "prep_cool"
    PREP_HEAT = "prep_heat"  # Not confirmed as valid value
    IDLE = "idle"


class HVACMode(Enum):
    """HVAC modes reported by Infinitude (mode)."""

    AUTO = "auto"
    HEAT = "heat"
    COOL = "cool"
    OFF = "off"
    FAN_ONLY = "fanonly"


class Occupancy(Enum):
    """HVAC modes reported by Infinitude (occupancy)."""

    OCCUPIED = "occupied"
    UNOCCUPIED = "unoccupied"
    MOTION = "motion"


class HumidifierState(Enum):
    """Humidifier states reported by Infinitude (humid)."""

    ON = "on"
    OFF = "off"
