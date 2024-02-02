from homeassistant.components.climate import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_AWAY,
    PRESET_HOME,
    PRESET_SLEEP,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_TEMPERATURE,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InfinitudeEntity
from .const import DOMAIN, PRESET_HOLD, PRESET_OVERRIDE, PRESET_SCHEDULE, PRESET_WAKE
from .infinitude.const import (
    Activity as InfActivity,
    FanMode as InfFanMode,
    HoldMode as InfHoldMode,
    HVACAction as InfHVACAction,
    HVACMode as InfHVACMode,
    TemperatureUnit as InfTemperatureUnit,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Infinitude climate platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([InfinitudeClimate(coordinator, "1")])


class InfinitudeClimate(InfinitudeEntity, ClimateEntity):
    """Representation of an Infinitude climate device."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_precision = PRECISION_TENTHS
    _attr_temperature_step = PRECISION_WHOLE
    _attr_preset_modes = [
        PRESET_SCHEDULE,
        PRESET_HOME,
        PRESET_AWAY,
        PRESET_SLEEP,
        PRESET_WAKE,
        PRESET_OVERRIDE,
        PRESET_HOLD,
    ]

    def __init__(self, coordinator, zone_id) -> None:
        """Initialize the climate device."""
        self._zone = coordinator.infinitude.zones.get(zone_id)
        self._system = coordinator.infinitude.system
        super().__init__(coordinator)

    @property
    def supported_features(self):
        """Return the supported features."""
        baseline = ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE
        if self._zone.hvac_mode == InfHVACMode.AUTO:
            return baseline | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        elif self._zone.hvac_mode in [InfHVACMode.HEAT, InfHVACMode.COOL]:
            return baseline | ClimateEntityFeature.TARGET_TEMPERATURE
        else:
            return baseline

    @property
    def unique_id(self) -> str:
        """Return the unique id."""
        return f"{self._system.serial}_zone_{self._zone.id}"

    @property
    def name(self) -> str:
        """Return the zone name."""
        return self._zone.name

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        unit = self._zone.temperature_unit
        if unit == InfTemperatureUnit.CELSIUS:
            return UnitOfTemperature.CELSIUS
        elif unit == InfTemperatureUnit.FARENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        return None

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._zone.temperature_current

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        if self._zone.hvac_mode == InfHVACMode.AUTO:
            if self._zone.hvac_action == InfHVACAction.ACTIVE_HEAT:
                return self.setpoint_heat
            elif self._zone.hvac_action == InfHVACAction.ACTIVE_COOL:
                return self.setpoint_cool
            else:
                return self._zone.temperature_current

        if self._zone.hvac_mode == InfHVACMode.HEAT:
            return self._zone.temperature_heat

        if self._zone.hvac_mode == InfHVACMode.COOL:
            return self._zone.temperature_cool

        return self._zone.temperature_current

    @property
    def target_temperature_high(self) -> float:
        """Return the high target temperature."""
        return self._zone.temperature_cool

    @property
    def target_temperature_low(self) -> float:
        """Return the low target temperature."""
        return self._zone.temperature_heat

    @property
    def current_humidity(self) -> float:
        """Return the current humidity."""
        return self._zone.humidity_current

    @property
    def hvac_action(self):
        """Return the current HVAC action."""
        if self._system.hvac_mode == InfHVACMode.OFF:
            return HVACAction.OFF
        elif self._zone.hvac_action == InfHVACAction.IDLE:
            return HVACAction.IDLE
        elif self._zone.hvac_action == InfHVACAction.ACTIVE_HEAT:
            return HVACAction.HEATING
        elif self._zone.hvac_action == InfHVACAction.ACTIVE_COOL:
            return HVACAction.COOLING
        else:
            return HVACAction.IDLE

    @property
    def hvac_modes(self):
        """Return the list of available HVAC operation modes."""
        return [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.HEAT_COOL,
            HVACMode.FAN_ONLY,
        ]

    @property
    def hvac_mode(self):
        """Return current HVAC mode."""
        mode_map = {
            InfHVACMode.OFF: HVACMode.OFF,
            InfHVACMode.HEAT: HVACMode.HEAT,
            InfHVACMode.COOL: HVACMode.COOL,
            InfHVACMode.AUTO: HVACMode.HEAT_COOL,
            InfHVACMode.FAN_ONLY: HVACMode.FAN_ONLY,
        }
        mode = mode_map.get(self._zone.hvac_mode, HVACMode.OFF)
        return mode

    @property
    def fan_modes(self):
        """Return the list of available HVAC operation modes."""
        return [FAN_AUTO, FAN_HIGH, FAN_MEDIUM, FAN_LOW]

    @property
    def fan_mode(self):
        """Return current fan mode."""
        mode_map = {
            InfFanMode.AUTO: FAN_AUTO,
            InfFanMode.HIGH: FAN_HIGH,
            InfFanMode.MEDIUM: FAN_MEDIUM,
            InfFanMode.LOW: FAN_LOW,
        }
        mode = mode_map.get(self._zone.fan_mode, InfFanMode.AUTO)
        return mode

    @property
    def preset_mode(self):
        """Return current preset mode."""
        # Update the preset mode based on current state
        # If hold is off, preset is the currently scheduled activity
        if self._zone.hold_mode == InfHoldMode.OFF:
            if self._zone.activity_scheduled == InfActivity.HOME:
                return PRESET_HOME
            elif self._zone.activity_scheduled == InfActivity.AWAY:
                return PRESET_AWAY
            elif self._zone.activity_scheduled == InfActivity.SLEEP:
                return PRESET_SLEEP
            elif self._zone.activity_scheduled == InfActivity.WAKE:
                return PRESET_WAKE
            else:
                return PRESET_SCHEDULE
        elif self._zone.hold_mode == InfHoldMode.UNTIL:
            # A temporary hold on the 'manual' activity is an 'override'
            if self._zone.hold_activity == InfActivity.MANUAL:
                return PRESET_OVERRIDE
            # A temporary hold is on a non-'manual' activity is that activity
            elif self._zone.hold_activity == InfActivity.HOME:
                return PRESET_HOME
            elif self._zone.hold_activity == InfActivity.AWAY:
                return PRESET_AWAY
            elif self._zone.hold_activity == InfActivity.SLEEP:
                return PRESET_SLEEP
            elif self._zone.hold_activity == InfActivity.WAKE:
                return PRESET_WAKE
        # An indefinite hold on any activity is a 'hold'
        else:
            return PRESET_HOLD
