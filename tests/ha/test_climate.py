"""Layer 2 — climate preset modes (slugs, translations, legacy aliases)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.infinitude_beyond.climate import InfinitudeClimate
from custom_components.infinitude_beyond.const import (
    PRESET_HOLD,
    PRESET_HOLD_UNTIL,
    PRESET_SCHEDULE,
    PRESET_WAKE,
)
from custom_components.infinitude_beyond.infinitude.const import (
    Activity,
    HeatSource,
    HoldMode,
)

COMPONENT = Path(__file__).resolve().parents[2] / "custom_components" / "infinitude_beyond"
CUSTOM_PRESETS = (PRESET_SCHEDULE, PRESET_WAKE, PRESET_HOLD, PRESET_HOLD_UNTIL)


def _make_entity():
    """A climate entity backed by a mock zone, no hass needed."""
    zone = MagicMock()
    zone.set_hold_mode = AsyncMock()
    coordinator = MagicMock()
    coordinator.infinitude.zones = {"1": zone}
    return InfinitudeClimate(coordinator, "1"), zone


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


async def test_preset_mode_reports_vacation_but_not_selectable():
    entity, zone = _make_entity()
    zone.activity_current = Activity.VACATION
    # Displayed as the current preset...
    assert entity.preset_mode == "vacation"
    # ...but never offered as a selectable option (control lives elsewhere).
    assert "vacation" not in entity.preset_modes
