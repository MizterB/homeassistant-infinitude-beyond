"""Layer 2 — climate preset modes (slugs, translations, legacy aliases)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.infinitude_beyond.climate import (
    InfinitudeClimate,
    InfinitudeVacationClimate,
)
from custom_components.infinitude_beyond.const import (
    PRESET_HOLD,
    PRESET_HOLD_UNTIL,
    PRESET_SCHEDULE,
    PRESET_WAKE,
)
from custom_components.infinitude_beyond.infinitude.const import (
    Activity,
    FanMode,
    HeatSource,
    HoldMode,
    HVACAction as InfHVACAction,
    HVACMode as InfHVACMode,
)
from homeassistant.components.climate import HVACMode

COMPONENT = Path(__file__).resolve().parents[2] / "custom_components" / "infinitude_beyond"
CUSTOM_PRESETS = (PRESET_SCHEDULE, PRESET_WAKE, PRESET_HOLD, PRESET_HOLD_UNTIL)


def _make_entity():
    """A climate entity backed by a mock zone, no hass needed."""
    zone = MagicMock()
    zone.set_hold_mode = AsyncMock()
    coordinator = MagicMock()
    coordinator.infinitude.zones = {"1": zone}
    entity = InfinitudeClimate(coordinator, "1")
    # No vacation in play for these unit tests (skip behavior-C / vacation preset).
    entity.system.vacation_enabled = False
    entity.system.vacation_active = False
    entity.system.set_vacation = AsyncMock()
    return entity, zone


def test_custom_presets_are_slugs():
    slug = re.compile(r"^[a-z0-9_-]+$")
    for preset in CUSTOM_PRESETS:
        assert slug.match(preset), f"{preset!r} is not a slug"


@pytest.mark.parametrize("source", ["strings.json", "translations/en.json"])
def test_presets_have_display_translations(source):
    data = json.loads((COMPONENT / source).read_text())
    states = data["entity"]["climate"]["infinitude_beyond_translation"][
        "state_attributes"
    ]["preset_mode"]["state"]
    for preset in CUSTOM_PRESETS:
        assert preset in states, f"{preset!r} missing a display name in {source}"


@pytest.mark.parametrize(
    "preset",
    [PRESET_HOLD, "Hold indefinitely"],
    ids=["slug", "legacy"],
)
async def test_set_preset_mode_accepts_slug_and_legacy_name(preset):
    # New slug and the pre-slug display name both map to an indefinite hold.
    entity, zone = _make_entity()
    await entity.async_set_preset_mode(preset)
    zone.set_hold_mode.assert_awaited_once_with(
        mode=HoldMode.INDEFINITE, activity=Activity.MANUAL
    )


async def test_set_preset_mode_legacy_hold_until():
    entity, zone = _make_entity()
    await entity.async_set_preset_mode("Hold until next activity")
    zone.set_hold_mode.assert_awaited_once_with(
        mode=HoldMode.UNTIL, activity=Activity.MANUAL
    )


async def test_set_heat_source_maps_slug_to_enum():
    entity, _zone = _make_entity()
    entity.system.set_heat_source = AsyncMock()
    await entity.async_set_heat_source("heat_pump")
    entity.system.set_heat_source.assert_awaited_once_with(HeatSource.HEATPUMP)


@pytest.mark.parametrize(
    "action,attr,value",
    [
        (InfHVACAction.ACTIVE_COOL, "temperature_cool", 75.0),
        (InfHVACAction.ACTIVE_HEAT, "temperature_heat", 68.0),
    ],
    ids=["cool", "heat"],
)
def test_target_temperature_in_auto_uses_zone_setpoint(action, attr, value):
    # #72: the Auto branch referenced a nonexistent self.setpoint_* and crashed
    # whenever a zone in Auto was actively heating/cooling.
    entity, zone = _make_entity()
    zone.hvac_mode = InfHVACMode.AUTO
    zone.hvac_action = action
    setattr(zone, attr, value)
    assert entity.target_temperature == value


async def test_preset_mode_reports_vacation():
    entity, _zone = _make_entity()
    entity.system.vacation_active = True
    assert entity.preset_mode == "vacation"


def test_vacation_preset_is_offered_last():
    entity, _zone = _make_entity()
    assert "vacation" in entity.preset_modes
    assert entity.preset_modes[-1] == "vacation"


async def test_selecting_vacation_preset_enables_vacation():
    entity, _zone = _make_entity()
    await entity.async_set_preset_mode("vacation")
    entity.system.set_vacation.assert_awaited_once_with(enabled=True)


async def test_zone_preset_change_exits_vacation():
    # Behavior C: picking a normal preset while vacation is on ends vacation.
    entity, zone = _make_entity()
    entity.system.vacation_enabled = True
    await entity.async_set_preset_mode("home")
    entity.system.set_vacation.assert_awaited_once_with(enabled=False)


def _make_vacation_entity():
    from unittest.mock import MagicMock

    coordinator = MagicMock()
    coordinator.infinitude.zones = {}
    entity = InfinitudeVacationClimate(coordinator)
    entity.system.set_vacation = AsyncMock()
    return entity


async def test_vacation_climate_hvac_mode_toggles_vacation():
    entity = _make_vacation_entity()
    await entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    entity.system.set_vacation.assert_awaited_with(enabled=True)
    await entity.async_set_hvac_mode(HVACMode.OFF)
    entity.system.set_vacation.assert_awaited_with(enabled=False)


async def test_vacation_climate_service_maps_fan_slug():
    entity = _make_vacation_entity()
    await entity.async_set_vacation(enabled=True, heat=60, cool=80, fan="low")
    kwargs = entity.system.set_vacation.await_args.kwargs
    assert kwargs["enabled"] is True
    assert kwargs["heat"] == 60 and kwargs["cool"] == 80
    assert kwargs["fan"] is FanMode.LOW
