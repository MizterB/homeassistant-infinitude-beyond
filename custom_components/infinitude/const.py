"""Constants for the Infinitude integration."""

from enum import Enum

DOMAIN = "infinitude"


class Preset(Enum):
    """Climate presets supported by integration."""

    SCHEDULE = "schedule"
    HOME = "home"
    AWAY = "away"
    SLEEP = "sleep"
    WAKE = "wake"
    MANUAL = "override"
