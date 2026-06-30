"""Layer 2 — connectivity binary sensor."""

from __future__ import annotations

from custom_components.infinitude_beyond.const import DOMAIN


def _connectivity_state(hass):
    for state in hass.states.async_all("binary_sensor"):
        if state.attributes.get("device_class") == "connectivity":
            return state
    return None


async def test_connectivity_sensor_tracks_coordinator_without_going_unavailable(
    hass, mock_infinitude, config_entry
):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    conn = _connectivity_state(hass)
    assert conn is not None, "expected a connectivity binary sensor"
    assert conn.state == "on"  # a successful setup means connected

    # A failed fetch must flip it to 'off' (disconnected) -- not 'unavailable',
    # which is what a plain coordinator entity would do and would make it useless.
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    coordinator.last_update_success = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    conn = hass.states.get(conn.entity_id)
    assert conn.state == "off"

    # And back on when the connection recovers.
    coordinator.last_update_success = True
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(conn.entity_id).state == "on"
