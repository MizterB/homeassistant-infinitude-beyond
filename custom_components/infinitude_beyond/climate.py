"""Climate for Infinitude."""

from datetime import timedelta
import logging

import voluptuous as vol

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
from homeassistant.const import PRECISION_TENTHS, PRECISION_WHOLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import InfinitudeDataUpdateCoordinator, InfinitudeEntity
from .const import DOMAIN, PRESET_HOLD, PRESET_HOLD_UNTIL, PRESET_SCHEDULE, PRESET_WAKE
from .infinitude.const import (
    Activity as InfActivity,
    FanMode as InfFanMode,
    HoldMode as InfHoldMode,
    HVACAction as InfHVACAction,
    HVACMode as InfHVACMode,
    TemperatureUnit as InfTemperatureUnit,
)

_LOGGER = logging.getLogger(__name__)


ATTR_HOLD_ACTIVITY = "activity"
ATTR_HOLD_MODE = "mode"
ATTR_HOLD_UNTIL = "until"
SERVICE_SET_HOLD_MODE = "set_hold_mode"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Infinitude climates from config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    zones = [z for z in coordinator.infinitude.zones.values() if z.enabled]
    for zone in zones:
        entities.extend([InfinitudeClimate(coordinator, zone.id)])
    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_HOLD_MODE,
        {
            vol.Optional(ATTR_HOLD_MODE, default=None): vol.Any(
                None, vol.In([hm.value for hm in InfHoldMode])
            ),
            vol.Optional(ATTR_HOLD_ACTIVITY, default=None): vol.Any(
                None, vol.In([a.value for a in InfActivity])
            ),
            vol.Optional(ATTR_HOLD_UNTIL, default=None): vol.Any(
                None,
                vol.All(
                    cv.time_period, cv.positive_timedelta, lambda td: td.total_seconds()
                ),
            ),
        },
        "async_set_hold_mode",
    )


class InfinitudeClimate(InfinitudeEntity, ClimateEntity):
    """Representation of an Infinitude climate entity."""

    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
    )
    _attr_precision = PRECISION_TENTHS
    _attr_temperature_step = PRECISION_WHOLE
    _attr_name = "Thermostat"
    _attr_translation_key = "infinitude_beyond_translation"
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: InfinitudeDataUpdateCoordinator,
        zone_id: str | None = None,
    ) -> None:
        """Set up the instance."""
        super().__init__(coordinator, zone_id)

    @property
    def supported_features(self):
        """Return the supported features."""
        baseline = ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.PRESET_MODE
        if self.zone.hvac_mode == InfHVACMode.AUTO:
            return baseline | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        elif self.zone.hvac_mode in [InfHVACMode.HEAT, InfHVACMode.COOL]:
            return baseline | ClimateEntityFeature.TARGET_TEMPERATURE
        else:
            return baseline

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        unit = self.zone.temperature_unit
        if unit == InfTemperatureUnit.CELSIUS:
            return UnitOfTemperature.CELSIUS
        elif unit == InfTemperatureUnit.FARENHEIT:
            return UnitOfTemperature.FAHRENHEIT
        return None

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self.zone.temperature_current

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        if self.zone.hvac_mode == InfHVACMode.AUTO:
            if self.zone.hvac_action in [
                InfHVACAction.ACTIVE_HEAT,
                InfHVACAction.PREP_HEAT,
            ]:
                return self.setpoint_heat
            elif self.zone.hvac_action in [
                InfHVACAction.ACTIVE_COOL,
                InfHVACAction.PREP_COOL,
            ]:
                return self.setpoint_cool
            else:
                return self.zone.temperature_current

        if self.zone.hvac_mode == InfHVACMode.HEAT:
            return self.zone.temperature_heat

        if self.zone.hvac_mode == InfHVACMode.COOL:
            return self.zone.temperature_cool

        return self.zone.temperature_current

    @property
    def target_temperature_high(self) -> float:
        """Return the high target temperature."""
        return self.zone.temperature_cool

    @property
    def target_temperature_low(self) -> float:
        """Return the low target temperature."""
        return self.zone.temperature_heat

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        if "temperature" in kwargs:
            temperature = kwargs["temperature"]
            await self.zone.set_temperature(temperature=temperature)
        elif "target_temp_low" in kwargs and "target_temp_high" in kwargs:
            temperature_heat = kwargs["target_temp_low"]
            temperature_cool = kwargs["target_temp_high"]
            await self.zone.set_temperature(
                temperature_heat=temperature_heat, temperature_cool=temperature_cool
            )

    @property
    def current_humidity(self) -> float:
        """Return the current humidity."""
        return self.zone.humidity_current

    @property
    def hvac_action(self):
        """Return the current HVAC action."""
        if self.infinitude.system.hvac_mode == InfHVACMode.OFF:
            return HVACAction.OFF
        elif self.zone.hvac_action == InfHVACAction.IDLE:
            return HVACAction.IDLE
        elif self.zone.hvac_action == InfHVACAction.ACTIVE_HEAT:
            return HVACAction.HEATING
        elif self.zone.hvac_action == InfHVACAction.PREP_HEAT:
            return HVACAction.PREHEATING
        elif self.zone.hvac_action == InfHVACAction.ACTIVE_COOL:
            return HVACAction.COOLING
        elif self.zone.hvac_action == InfHVACAction.PREP_COOL:
            return (
                HVACAction.COOLING
            )  # HVACAction.PRECOOLING not defined as of HA 2024.7
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
        mode = mode_map.get(self.zone.hvac_mode, HVACMode.OFF)
        return mode

    async def async_set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        _LOGGER.debug("Set hvac mode: %s", hvac_mode)
        mode_map = {
            HVACMode.OFF: InfHVACMode.OFF,
            HVACMode.HEAT: InfHVACMode.HEAT,
            HVACMode.COOL: InfHVACMode.COOL,
            HVACMode.HEAT_COOL: InfHVACMode.AUTO,
            HVACMode.FAN_ONLY: InfHVACMode.FAN_ONLY,
        }
        mode = mode_map.get(hvac_mode)
        if mode is None:
            _LOGGER.error("Invalid hvac mode: %s", hvac_mode)
        else:
            await self.infinitude.system.set_hvac_mode(mode)

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
        mode = mode_map.get(self.zone.fan_mode, InfFanMode.AUTO)
        return mode

    async def async_set_fan_mode(self, fan_mode):
        """Set new target fan mode."""
        _LOGGER.debug("Set fan mode: %s", fan_mode)
        mode_map = {
            FAN_AUTO: InfFanMode.AUTO,
            FAN_HIGH: InfFanMode.HIGH,
            FAN_MEDIUM: InfFanMode.MEDIUM,
            FAN_LOW: InfFanMode.LOW,
        }
        mode = mode_map.get(fan_mode)
        if mode is None:
            _LOGGER.error("Invalid fan mode: %s", fan_mode)
        else:
            await self.zone.set_fan_mode(mode)

    @property
    def preset_modes(self) -> list:
        """Return available preset modes."""
        modes = [
            PRESET_SCHEDULE,
            PRESET_HOME,
            PRESET_AWAY,
            PRESET_SLEEP,
            PRESET_WAKE,
            PRESET_HOLD,
            PRESET_HOLD_UNTIL,
        ]
        return modes

    @property
    def preset_mode(self):
        """Return current preset mode."""
        # If hold is off, preset is the currently scheduled activity
        if self.zone.hold_mode == InfHoldMode.OFF:
            if self.zone.activity_scheduled == InfActivity.HOME:
                return PRESET_HOME
            elif self.zone.activity_scheduled == InfActivity.AWAY:
                return PRESET_AWAY
            elif self.zone.activity_scheduled == InfActivity.SLEEP:
                return PRESET_SLEEP
            elif self.zone.activity_scheduled == InfActivity.WAKE:
                return PRESET_WAKE
            else:
                return PRESET_SCHEDULE
        elif self.zone.hold_mode == InfHoldMode.UNTIL:
            # A temporary hold on the 'manual' activity is an 'override' or 'hold until'
            if self.zone.hold_activity == InfActivity.MANUAL:
                return PRESET_HOLD_UNTIL
            # A temporary hold is on a non-'manual' activity is that activity
            elif self.zone.hold_activity == InfActivity.HOME:
                return PRESET_HOME
            elif self.zone.hold_activity == InfActivity.AWAY:
                return PRESET_AWAY
            elif self.zone.hold_activity == InfActivity.SLEEP:
                return PRESET_SLEEP
            elif self.zone.hold_activity == InfActivity.WAKE:
                return PRESET_WAKE
        # An indefinite hold on any activity is a 'hold'
        else:
            return PRESET_HOLD

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""
        _LOGGER.debug("Set preset mode: %s", preset_mode)
        if preset_mode == PRESET_SCHEDULE:
            # Remove all holds to restore the normal schedule
            await self.zone.set_hold_mode(mode=InfHoldMode.OFF)
        elif preset_mode == PRESET_HOME:
            # Set to home until the next scheduled activity
            await self.zone.set_hold_mode(
                mode=InfHoldMode.UNTIL, activity=InfActivity.HOME
            )
        elif preset_mode == PRESET_AWAY:
            # Set to away until the next scheduled activity
            await self.zone.set_hold_mode(
                mode=InfHoldMode.UNTIL, activity=InfActivity.AWAY
            )
        elif preset_mode == PRESET_SLEEP:
            # Set to sleep until the next scheduled activity
            await self.zone.set_hold_mode(
                mode=InfHoldMode.UNTIL, activity=InfActivity.SLEEP
            )
        elif preset_mode == PRESET_WAKE:
            # Set to wake until the next scheduled activity
            await self.zone.set_hold_mode(
                mode=InfHoldMode.UNTIL, activity=InfActivity.WAKE
            )
        elif preset_mode == PRESET_HOLD:
            # Set to manual and hold indefinitely
            await self.zone.set_hold_mode(
                mode=InfHoldMode.INDEFINITE, activity=InfActivity.MANUAL
            )
        elif preset_mode == PRESET_HOLD_UNTIL:
            # Set to manual and hold indefinitely
            await self.zone.set_hold_mode(
                mode=InfHoldMode.UNTIL, activity=InfActivity.MANUAL
            )
        else:
            _LOGGER.error("Invalid preset mode: %s", preset_mode)

    async def async_set_hold_mode(self, mode, activity, until):
        "Set the hold mode."
        hold_mode = next((m for m in InfHoldMode if m.value == mode), None)
        hold_activity = next((a for a in InfActivity if a.value == activity), None)
        hold_until = None
        if until is not None:
            today = self.system.local_time.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            hold_until = today + timedelta(seconds=until)
        await self.zone.set_hold_mode(
            mode=hold_mode, activity=hold_activity, until=hold_until
        )
