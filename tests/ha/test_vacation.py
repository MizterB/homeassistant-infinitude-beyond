"""Layer 2 — vacation control entities (#46 phase 2)."""

from __future__ import annotations


async def test_vacation_climate_registers_off_by_default(
    hass, mock_infinitude, config_entry
):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    vac = next(
        (
            s
            for s in hass.states.async_all("climate")
            if s.attributes.get("friendly_name", "").endswith("Vacation")
        ),
        None,
    )
    assert vac is not None
    # Fixture has vacat off.
    assert vac.state == "off"
    assert "heat_cool" in vac.attributes["hvac_modes"]


async def test_vacation_datetime_entities_register(
    hass, mock_infinitude, config_entry
):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    datetimes = {s.entity_id for s in hass.states.async_all("datetime")}
    assert any(e.endswith("vacation_start") for e in datetimes)
    assert any(e.endswith("vacation_end") for e in datetimes)
