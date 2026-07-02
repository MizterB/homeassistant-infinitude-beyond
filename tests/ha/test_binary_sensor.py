"""Layer 2 — connectivity binary sensors."""

from __future__ import annotations

from custom_components.infinitude_beyond.const import DOMAIN


def _state(hass, name_suffix):
    for state in hass.states.async_all("binary_sensor"):
        if state.attributes.get("friendly_name", "").endswith(name_suffix):
            return state
    return None


async def _setup(hass, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][config_entry.entry_id]


async def test_infinitude_connectivity_tracks_reachability(
    hass, mock_infinitude, config_entry
):
    coordinator = await _setup(hass, config_entry)
    inf = _state(hass, "Infinitude connectivity")
    assert inf is not None and inf.state == "on"

    # Flips to disconnected without going unavailable, and recovers.
    coordinator.last_update_success = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(inf.entity_id).state == "off"

    coordinator.last_update_success = True
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(inf.entity_id).state == "on"


async def test_thermostat_connectivity_reflects_reporting(
    hass, mock_infinitude, config_entry
):
    coordinator = await _setup(hass, config_entry)
    tstat = _state(hass, "Thermostat connectivity")
    inf = _state(hass, "Infinitude connectivity")
    assert tstat is not None and tstat.state == "on"

    # Thermostat stops reporting while Infinitude stays reachable: only the
    # thermostat sensor drops.
    coordinator.infinitude._status = None
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(tstat.entity_id).state == "off"
    assert hass.states.get(inf.entity_id).state == "on"

    # If HA can't reach Infinitude, we can't confirm the thermostat -> off.
    coordinator.last_update_success = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(tstat.entity_id).state == "off"
