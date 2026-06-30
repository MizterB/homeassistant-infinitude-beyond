"""Layer 2 — entry setup, entity creation, and unload."""

from __future__ import annotations

from custom_components.infinitude_beyond.const import DOMAIN
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

    # The fixture enables zones 1 and 2 only -> two climate entities.
    climate_states = hass.states.async_all("climate")
    assert len(climate_states) == 2

    # System is in heat mode; zone 1 current 70F, zone 2 current 68F.
    states_by_temp = {s.attributes.get("current_temperature") for s in climate_states}
    assert states_by_temp == {70.0, 68.0}
    assert all(s.state == "heat" for s in climate_states)


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
