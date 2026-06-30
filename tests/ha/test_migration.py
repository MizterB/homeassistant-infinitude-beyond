"""Layer 2 — identity migration off the serial number (issue #40)."""

from __future__ import annotations

import pytest
from custom_components.infinitude_beyond.const import DOMAIN
from homeassistant.helpers import device_registry as dr, entity_registry as er

# Matches the serial in the profile fixture.
SERIAL = "0000W000000"


@pytest.mark.parametrize("old_prefix", [SERIAL, "None"], ids=["serial", "none"])
async def test_entity_unique_ids_migrate_to_entry_id(
    hass, mock_infinitude, config_entry, old_prefix
):
    # Pre-existing entity keyed on the old (serial or "None") prefix.
    config_entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    old = ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{old_prefix}_system_HVAC mode", config_entry=config_entry
    )
    entity_id = old.entity_id

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Same entity_id (so recorder history and template helpers survive), but the
    # unique_id is rebased onto the stable config entry id.
    migrated = ent_reg.async_get(entity_id)
    assert migrated is not None
    assert migrated.unique_id == f"{config_entry.entry_id}_system_HVAC mode"


async def test_duplicate_prefers_serial_entry(hass, mock_infinitude, config_entry):
    # An already-split install: the serial entry holds history, the "None" one
    # is the empty duplicate. The serial one must win the migration.
    config_entry.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    serial_entry = ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{SERIAL}_system_HVAC mode", config_entry=config_entry
    )
    none_entry = ent_reg.async_get_or_create(
        "sensor", DOMAIN, "None_system_HVAC mode", config_entry=config_entry
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Serial entry rebased onto the entry id (and stays live); the None
    # duplicate is left untouched for manual cleanup.
    assert (
        ent_reg.async_get(serial_entry.entity_id).unique_id
        == f"{config_entry.entry_id}_system_HVAC mode"
    )
    assert ent_reg.async_get(none_entry.entity_id).unique_id == "None_system_HVAC mode"


async def test_device_identifier_migrates_to_entry_id(
    hass, mock_infinitude, config_entry
):
    config_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    old_device = dev_reg.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, f"{SERIAL}_system")},
        name="Infinitude System",
    )

    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    migrated = dev_reg.async_get(old_device.id)
    assert migrated is not None
    assert (DOMAIN, f"{config_entry.entry_id}_system") in migrated.identifiers
    assert (DOMAIN, f"{SERIAL}_system") not in migrated.identifiers
