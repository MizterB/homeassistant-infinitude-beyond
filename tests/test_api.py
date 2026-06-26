"""Layer 1 unit tests for the vendored Infinitude API client.

These run with no Home Assistant dependency — just the client, a real in-process
aiohttp test server, and synthetic v1.7 fixtures (see conftest.py).

Tests are grouped into:
  * happy-path property/behavior coverage (should always pass), and
  * regression repros for known open bugs, marked xfail(strict=True) so they
    document the defect and will flip to a hard failure the moment the bug is
    fixed (telling us to drop the xfail).
"""

from __future__ import annotations

from datetime import timedelta

import infinitude.api as api_module
import pytest
from infinitude.const import (
    FanMode,
    HoldMode,
    HoldState,
    HVACMode,
    TemperatureUnit,
)


@pytest.fixture(autouse=True)
def _allow_local_sockets():
    """Layer 1 uses a real local aiohttp server.

    When pytest-socket is present (it ships with pytest-homeassistant-custom-
    component and blocks sockets session-wide), re-enable them for these tests.
    No-op in the HA-free environment where pytest-socket isn't installed.
    """
    try:
        import pytest_socket
    except ImportError:
        yield
        return
    pytest_socket.enable_socket()
    yield


# --------------------------------------------------------------------------- #
# Happy-path coverage
# --------------------------------------------------------------------------- #


async def test_connect_discovers_all_zones(infinitude):
    assert sorted(infinitude.zones.keys()) == [str(i) for i in range(1, 9)]
    assert infinitude.zones["1"].name == "Living Room"
    assert infinitude.zones["2"].name == "Bedroom"


async def test_zone_enabled_flags(infinitude):
    assert infinitude.zones["1"].enabled is True
    assert infinitude.zones["3"].enabled is False


async def test_system_profile(infinitude):
    sys = infinitude.system
    assert sys.brand == "Carrier"
    assert sys.model == "SYSTXCCITC01-A"
    assert sys.serial == "0000W000000"
    assert sys.temperature_unit is TemperatureUnit.FARENHEIT


async def test_system_hvac_and_outside_temp(infinitude):
    assert infinitude.system.hvac_mode is HVACMode.HEAT
    assert infinitude.system.temperature_outside == 34


async def test_idu_modulation(infinitude):
    # idu type is 'furnacemodulating' with opstat 35 in the fixture
    assert infinitude.system.idu_modulation == 35
    assert infinitude.system.airflow_cfm == 800.0


async def test_zone_temperatures(infinitude):
    zone = infinitude.zones["1"]
    assert zone.temperature_current == 70.0
    assert zone.temperature_cool == 75.0
    assert zone.temperature_heat == 68.0
    assert zone.fan_mode is FanMode.AUTO  # 'off' maps to AUTO


async def test_local_time_timezone(infinitude):
    # Fixture localTime carries a -05:00 offset.
    lt = infinitude.system.local_time
    assert lt.utcoffset().total_seconds() == -5 * 3600


async def test_scheduled_and_next_activity_computed(infinitude):
    # 2024-01-15T08:00 (Monday) with periods wake@06, away@08, home@17, sleep@22.
    # At exactly 08:00 the 'away' period starts -> next == away.
    zone = infinitude.zones["1"]
    assert zone.activity_next is not None
    assert zone.activity_next_start is not None
    assert zone.activity_scheduled is not None


async def test_hold_off_by_default(infinitude):
    zone = infinitude.zones["1"]
    assert zone.hold_state is HoldState.OFF
    assert zone.hold_mode is HoldMode.OFF


async def test_set_temperature_posts_manual_activity(infinitude):
    await infinitude.zones["1"].set_temperature(temperature=72)

    activity_posts = [
        p for p in infinitude.posts if p["path"] == "/api/1/activity/manual"
    ]
    assert activity_posts, "expected a POST to the manual activity endpoint"
    data = activity_posts[0]["data"]
    assert data["htsp"] == "72.0"
    assert data["clsp"] == "72.0"
    assert "fan" in data
    # set_temperature should also place a hold.
    assert any(p["path"] == "/api/1/hold" for p in infinitude.posts)


async def test_set_fan_mode_posts_manual_activity(infinitude):
    await infinitude.zones["1"].set_fan_mode(FanMode.HIGH)

    activity_posts = [
        p for p in infinitude.posts if p["path"] == "/api/1/activity/manual"
    ]
    assert activity_posts[0]["data"]["fan"] == "high"


# --------------------------------------------------------------------------- #
# Regression repros for open bugs (xfail until fixed)
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="#38/#39: _post crashes on a non-JSON/empty 200 body "
    "(resp.json raises JSONDecodeError). Drop xfail once _post guards this.",
)
async def test_post_non_json_body_does_not_crash(infinitude):
    # The test server returns a non-JSON 200 body for POST /api/config, as
    # Infinitude does. _post calls resp.json() on it unconditionally and raises.
    await infinitude.system.set_hvac_mode(HVACMode.HEAT)


@pytest.mark.xfail(
    strict=True,
    reason="#18: _compare_data calls .keys() on a value that changed type "
    "(dict -> float). Drop xfail once _compare_data guards non-dict inputs.",
)
async def test_compare_data_handles_type_change(infinitude):
    # Mirrors the reported traceback: a previously-dict payload arrives as a float.
    diff = infinitude._compare_data({"energy": {"usage": 1}}, 5.0)
    assert diff is None or isinstance(diff, dict)


@pytest.mark.xfail(
    strict=True,
    reason="Task #1: hold_until reads otmr only from (lagging) status; a timed "
    "hold is mislabeled INDEFINITE until status catches up. Fix reads config first.",
)
async def test_hold_until_prefers_config_otmr(infinitude):
    # Simulate the window right after a timed hold: config has otmr, status lags.
    zcfg = next(z for z in infinitude._config["zones"]["zone"] if z["id"] == "1")
    zcfg["hold"] = "on"
    zcfg["holdActivity"] = "manual"
    zcfg["otmr"] = "14:00"
    zstatus = next(z for z in infinitude._status["zones"]["zone"] if z["id"] == "1")
    zstatus["hold"] = "on"
    zstatus["otmr"] = {}  # not yet synced

    zone = infinitude.zones["1"]
    assert zone.hold_state is HoldState.ON
    assert zone.hold_mode is HoldMode.UNTIL  # currently INDEFINITE -> the bug


class _LoopGuard(BaseException):
    """Raised to break out of an unbounded day-walk.

    Subclasses BaseException (not Exception) so _update_activities's broad
    ``except Exception`` cannot swallow it -- it propagates out to the test.
    """


@pytest.mark.xfail(
    strict=True,
    reason="#42: _update_activities walks days forever when no schedule is "
    "active. Drop xfail once the day-walk is bounded to 7 days.",
)
async def test_update_activities_terminates_without_schedule(infinitude, monkeypatch):
    # Swap zone 1 to a fully-disabled schedule (simplified, as connect() stores it).
    from tests.conftest import load_fixture

    no_sched = infinitude._simplify_json(load_fixture("config_no_schedule.json")["data"])
    infinitude._config = no_sched
    zone = infinitude.zones["1"]

    # _update_activities advances one day per loop via `timedelta(days=1)`. Trip a
    # guard once it walks past two weeks -- a bounded (<=7-day) implementation
    # never gets there; the current unbounded loop does, almost immediately.
    calls = {"n": 0}

    def counting_timedelta(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 14:
            raise _LoopGuard
        return timedelta(*args, **kwargs)

    monkeypatch.setattr(api_module, "timedelta", counting_timedelta)

    walked_unbounded = False
    try:
        zone._update_activities()
    except _LoopGuard:
        walked_unbounded = True

    assert not walked_unbounded, "_update_activities walked past 14 days (unbounded)"
