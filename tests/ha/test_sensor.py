"""Layer 2 — sensor registration."""

from __future__ import annotations


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
