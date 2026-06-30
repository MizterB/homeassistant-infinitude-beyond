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

import logging
from datetime import timedelta

import infinitude.api as api_module
import pytest
from infinitude.const import (
    Activity,
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
    assert infinitude.system.has_idu is True


async def test_odu_modulation(infinitude):
    # The fixture has no odu block, so there's nothing to report.
    assert infinitude.system.odu_modulation is None

    odu = infinitude._status["odu"] = {"type": "proteus"}
    odu["opstat"] = "45"
    assert infinitude.system.odu_modulation == 45
    odu["opstat"] = "dehumidify"
    assert infinitude.system.odu_modulation == 1
    odu["opstat"] = "off"
    assert infinitude.system.odu_modulation == 0

    # A unit type we don't read modulation from reports nothing.
    infinitude._status["odu"] = {"type": "ac2stg", "opstat": "60"}
    assert infinitude.system.odu_modulation is None


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
# POST response handling (#38/#39)
# --------------------------------------------------------------------------- #


async def test_post_non_json_body_does_not_crash(infinitude):
    # Older Infinitude returns a non-JSON 200 body to a POST (the test server
    # sends "Success"); _post must swallow the parse failure, not raise.
    await infinitude.system.set_hvac_mode(HVACMode.HEAT)


async def test_post_empty_body_returns_none_and_warns(infinitude, caplog):
    # An empty body is the exact #38/#39 condition (orjson "char 0"). _post
    # returns None and logs a one-time hint to upgrade Infinitude.
    with caplog.at_level(logging.WARNING):
        result = await infinitude._post("/api/empty-test", {})
    assert result is None
    assert "upgrade" in caplog.text.lower()


async def test_get_raises_connection_error_on_failure(infinitude):
    # A failed GET must raise (not return None), so connect() can report a
    # connection problem instead of blowing up later in the fetchers (#20).
    with pytest.raises(ConnectionError):
        await infinitude._get("/api/fail")


# --------------------------------------------------------------------------- #
# Regression repros for open bugs (xfail until fixed)
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="#18: _compare_data calls .keys() on a value that changed type "
    "(dict -> float). Drop xfail once _compare_data guards non-dict inputs.",
)
async def test_compare_data_handles_type_change(infinitude):
    # Mirrors the reported traceback: a previously-dict payload arrives as a float.
    diff = infinitude._compare_data({"energy": {"usage": 1}}, 5.0)
    assert diff is None or isinstance(diff, dict)


async def test_hold_until_prefers_config_otmr(infinitude):
    # Right after a timed hold, config carries otmr while status lags. hold_until
    # must read config first so the hold is reported as timed (UNTIL), not
    # indefinite. (Regression test for the "Hold indefinitely" mislabel.)
    zcfg = next(z for z in infinitude._config["zones"]["zone"] if z["id"] == "1")
    zcfg["hold"] = "on"
    zcfg["holdActivity"] = "manual"
    zcfg["otmr"] = "14:00"
    zstatus = next(z for z in infinitude._status["zones"]["zone"] if z["id"] == "1")
    zstatus["hold"] = "on"
    zstatus["otmr"] = {}  # not yet synced

    zone = infinitude.zones["1"]
    assert zone.hold_state is HoldState.ON
    assert zone.hold_mode is HoldMode.UNTIL


async def test_hold_indefinite_when_otmr_forever(infinitude):
    # Infinitude stores otmr="forever" for an indefinite hold. hold_until must
    # treat that as no time component (and not crash on split(":")).
    zcfg = next(z for z in infinitude._config["zones"]["zone"] if z["id"] == "1")
    zcfg["hold"] = "on"
    zcfg["holdActivity"] = "manual"
    zcfg["otmr"] = "forever"

    zone = infinitude.zones["1"]
    assert zone.hold_until is None
    assert zone.hold_mode is HoldMode.INDEFINITE


class _LoopGuard(BaseException):
    """Raised to break out of an unbounded day-walk.

    Subclasses BaseException (not Exception) so _update_activities's broad
    ``except Exception`` cannot swallow it -- it propagates out to the test.
    """


async def test_update_activities_terminates_without_schedule(infinitude, monkeypatch):
    # Swap zone 1 to a fully-disabled schedule (simplified, as connect() stores it).
    from tests.conftest import load_fixture

    no_sched = infinitude._simplify_json(load_fixture("config_no_schedule.json")["data"])
    infinitude._config = no_sched
    zone = infinitude.zones["1"]

    # The loop advances one day per iteration via timedelta(days=1). Count only
    # those day advances (local_timezone also builds timedeltas) and trip a guard
    # past a week -- a bounded (<=7-day) walk never gets there; the old unbounded
    # loop would spin into the millions.
    day_steps = {"n": 0}

    def counting_timedelta(*args, **kwargs):
        if kwargs.get("days"):
            day_steps["n"] += 1
            if day_steps["n"] > 8:
                raise _LoopGuard
        return timedelta(*args, **kwargs)

    monkeypatch.setattr(api_module, "timedelta", counting_timedelta)

    walked_unbounded = False
    try:
        zone._update_activities()
    except _LoopGuard:
        walked_unbounded = True

    assert not walked_unbounded, "_update_activities walked past a week (unbounded)"
    assert zone.activity_next is None  # no enabled schedule -> no next activity


async def test_update_activities_handles_after_midnight_wrap(infinitude):
    # A period whose time wraps past midnight (sleep@00:00 listed after wake@06:00)
    # belongs to the next day, not the same day. The fixture clock is Monday 08:00,
    # so the active activity is wake -- not the midnight sleep entry (#47).
    days = [
        "Sunday",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
    ]
    zcfg = next(z for z in infinitude._config["zones"]["zone"] if z["id"] == "1")
    zcfg["program"]["day"] = [
        {
            "id": d,
            "period": [
                {"id": "1", "time": "06:00", "activity": "wake", "enabled": "on"},
                {"id": "2", "time": "00:00", "activity": "sleep", "enabled": "on"},
            ],
        }
        for d in days
    ]

    zone = infinitude.zones["1"]
    zone._update_activities()

    assert zone.activity_scheduled is Activity.WAKE
    assert zone.activity_next is Activity.SLEEP
