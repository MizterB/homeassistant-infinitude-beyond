"""Layer 2 — sensor registration."""

from __future__ import annotations

from homeassistant.helpers import entity_registry as er


async def test_modulation_sensors_only_register_when_reported(
    hass, mock_infinitude, config_entry
):
    # The fixture system reports an IDU (furnacemodulating, with airflow) but no
    # ODU. So IDU modulation and Airflow register; ODU modulation does not,
    # rather than sitting on the device page as a permanent "unknown".
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    names = {
        s.attributes.get("friendly_name", "")
        for s in hass.states.async_all("sensor")
    }
    assert any(n.endswith("IDU modulation") for n in names)
    assert any(n.endswith("Airflow") for n in names)
    assert not any(n.endswith("ODU modulation") for n in names)


async def test_status_sensors_gate_and_use_key_based_ids(
    hass, mock_infinitude, config_entry
):
    # The fixture reports an IDU (furnace status) but no ODU and no heat source.
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    names = {s.attributes.get("friendly_name", "") for s in hass.states.async_all("sensor")}
    assert any(n.endswith("Furnace status") for n in names)
    assert not any(n.endswith("Heat pump status") for n in names)
    assert not any(n.endswith("Heat pump mode") for n in names)
    assert not any(n.endswith("Heat source") for n in names)

    # Translated sensors key on the description key, not the localized name.
    reg = er.async_get(hass)
    furnace = next(
        e
        for e in er.async_entries_for_config_entry(reg, config_entry.entry_id)
        if e.translation_key == "furnace_status"
    )
    assert furnace.unique_id == f"{config_entry.entry_id}_system_furnace_status"


async def test_humidity_sensor_per_enabled_zone(hass, mock_infinitude, config_entry):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    humidity = [
        s
        for s in hass.states.async_all("sensor")
        if s.attributes.get("device_class") == "humidity"
    ]
    # Fixture enables zones 1 and 2, both reporting rh 42.
    assert len(humidity) == 2
    assert all(s.state == "42" for s in humidity)
    assert all(s.attributes.get("unit_of_measurement") == "%" for s in humidity)


async def test_vacation_sensor_registers_and_reports_state(
    hass, mock_infinitude, config_entry
):
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    reg = er.async_get(hass)
    vac = next(
        (
            e
            for e in er.async_entries_for_config_entry(reg, config_entry.entry_id)
            if e.translation_key == "vacation"
        ),
        None,
    )
    assert vac is not None
    assert vac.unique_id == f"{config_entry.entry_id}_system_vacation"
    # Fixture has vacat off -> disabled.
    assert hass.states.get(vac.entity_id).state == "disabled"
