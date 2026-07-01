"""Layer 2 — entry setup, entity creation, and unload."""

from __future__ import annotations

from custom_components.infinitude_beyond.const import DOMAIN
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.config_entries import ConfigEntryState
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM


async def test_setup_creates_climate_entities(hass, mock_infinitude, config_entry):
    # The system reports Fahrenheit; pin HA to US units so state values are not
    # converted to Celsius (otherwise 70F/68F surface as 21.1C/20.0C).
    hass.config.units = US_CUSTOMARY_SYSTEM

    config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED

    # The fixture enables zones 1 and 2 -> two zone thermostats (plus the
    # system-wide Vacation climate, which has no current_temperature).
    zone_states = [
        s
        for s in hass.states.async_all("climate")
        if s.attributes.get("current_temperature") is not None
    ]
    assert len(zone_states) == 2

    # System is in heat mode; zone 1 current 70F, zone 2 current 68F.
    states_by_temp = {s.attributes.get("current_temperature") for s in zone_states}
    assert states_by_temp == {70.0, 68.0}
    assert all(s.state == "heat" for s in zone_states)


async def test_climate_target_temperature_supported_in_any_mode(
    hass, mock_infinitude, config_entry
):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Pick a zone thermostat (the vacation climate only supports a temp range).
    zone = next(
        s
        for s in hass.states.async_all("climate")
        if s.attributes.get("current_temperature") is not None
    )
    feats = zone.attributes["supported_features"]
    assert feats & ClimateEntityFeature.TARGET_TEMPERATURE
    assert feats & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE


async def test_unload_entry(hass, mock_infinitude, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert DOMAIN not in hass.data or config_entry.entry_id not in hass.data.get(
        DOMAIN, {}
    )
