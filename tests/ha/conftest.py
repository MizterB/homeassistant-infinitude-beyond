"""Fixtures for Layer 2 — Home Assistant integration tests.

Requires `pytest-homeassistant-custom-component`. If it (and Home Assistant)
are not installed, this whole subtree is skipped — see ``importorskip`` below and
``collect_ignore_glob`` in the parent conftest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SSL  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.infinitude_beyond.const import DOMAIN  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HOST = "test"
PORT = 3000
BASE = f"http://{HOST}:{PORT}"
ENTRY_DATA = {CONF_HOST: HOST, CONF_PORT: PORT, CONF_SSL: False}
UNIQUE_ID = f"{HOST}:{PORT}"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the custom integration for every test in this subtree."""
    yield


@pytest.fixture
def mock_infinitude(aioclient_mock):
    """Stub the four Infinitude REST endpoints with happy-path fixtures."""
    aioclient_mock.get(f"{BASE}/api/status/", json=_load("status.json"))
    aioclient_mock.get(f"{BASE}/api/config/", json=_load("config.json"))
    aioclient_mock.get(f"{BASE}/energy.json", json=_load("energy.json"))
    aioclient_mock.get(f"{BASE}/profile.json", json=_load("profile.json"))
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry for the integration."""
    return MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, unique_id=UNIQUE_ID)
