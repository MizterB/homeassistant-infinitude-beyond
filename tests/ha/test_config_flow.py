"""Layer 2 — config flow tests."""

from __future__ import annotations

from unittest.mock import patch

from custom_components.infinitude_beyond.const import DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.data_entry_flow import FlowResultType

from .conftest import BASE, ENTRY_DATA, UNIQUE_ID


async def test_form_is_shown(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert not result["errors"]


async def test_user_flow_creates_entry(hass, mock_infinitude):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(
        "custom_components.infinitude_beyond.async_setup_entry", return_value=True
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], ENTRY_DATA
        )
        await hass.async_block_till_done()

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == UNIQUE_ID
    assert result2["data"] == {CONF_HOST: "test", CONF_PORT: 3000, CONF_SSL: False}


async def test_aborts_if_already_configured(hass, mock_infinitude, config_entry):
    config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_user_flow_cannot_connect(hass, aioclient_mock):
    # When the GETs fail, connect() raises ConnectionError and the flow reports
    # cannot_connect instead of crashing with "Unknown error" (issue #20).
    for path in ("/api/status/", "/api/config/", "/energy.json", "/profile.json"):
        aioclient_mock.get(f"{BASE}{path}", status=500)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )

    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {"base": "cannot_connect"}
