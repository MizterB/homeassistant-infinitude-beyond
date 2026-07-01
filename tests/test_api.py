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
    HeatSource,
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


async def test_equipment_status_slugs(infinitude):
    # Known staging values map to slugs; opmode passes through.
    infinitude._status["idu"] = {"opstat": "Stage 1"}
    infinitude._status["odu"] = {"opstat": "Stage 3", "opmode": "heating"}
    assert infinitude.system.furnace_status == "stage_1"
    assert infinitude.system.heatpump_status == "stage_3"
    assert infinitude.system.heatpump_mode == "heating"


async def test_equipment_status_passthrough_and_absent(infinitude):
    # A value we didn't account for is passed through verbatim.
    infinitude._status["odu"] = {"opstat": "Turbo"}
    assert infinitude.system.heatpump_status == "Turbo"
    # No odu block -> nothing to report (sensor won't register).
    infinitude._status.pop("odu", None)
    assert infinitude.system.heatpump_status is None
    assert infinitude.system.heatpump_mode is None


async def test_heat_source_mapping(infinitude):
    for cfg, slug in (("system", "system"), ("idu only", "gas"), ("odu only", "heat_pump")):
        infinitude._config["heatsource"] = cfg
        assert infinitude.system.heat_source == slug
    # Unrecognized or missing config -> None (controlled set, no passthrough).
    infinitude._config["heatsource"] = "mystery"
    assert infinitude.system.heat_source is None
    infinitude._config.pop("heatsource", None)
    assert infinitude.system.heat_source is None


async def test_properties_tolerate_missing_payloads(infinitude):
    # An empty /api/status (or config) must not crash the entities.
    infinitude._status = None
    infinitude._config = None
    assert infinitude.system.humidifier_state is None
    assert infinitude.system.temperature_outside is None
    assert infinitude.system.vacation_state == "disabled"
    assert infinitude.zones["1"].temperature_current is None


async def test_set_heat_source_posts_config(infinitude):
    await infinitude.system.set_heat_source(HeatSource.HEATPUMP)
    posts = [p for p in infinitude.posts if p["path"] == "/api/config"]
    assert posts, "expected a POST to /api/config"
    assert posts[-1]["data"] == {"heatsource": "odu only"}


async def test_activity_current_recognizes_vacation(infinitude):
    zstatus = next(z for z in infinitude._status["zones"]["zone"] if z["id"] == "1")
    zstatus["currentActivity"] = "vacation"
    assert infinitude.zones["1"].activity_current is Activity.VACATION


async def test_vacation_state_disabled_when_off(infinitude):
    assert infinitude.system.vacation_state == "disabled"


async def test_vacation_state_from_window(infinitude):
    # Fixture clock is 2024-01-15 08:00 (-05:00).
    cfg = infinitude._config
    cfg["vacat"] = "on"
    cfg["vacstart"], cfg["vacend"] = (
        "2024-01-01T00:00:00-05:00",
        "2024-02-01T00:00:00-05:00",
    )
    assert infinitude.system.vacation_state == "active"
    cfg["vacstart"], cfg["vacend"] = (
        "2024-06-01T00:00:00-05:00",
        "2024-07-01T00:00:00-05:00",
    )
    assert infinitude.system.vacation_state == "scheduled"
    cfg["vacstart"], cfg["vacend"] = (
        "2023-06-01T00:00:00-05:00",
        "2023-07-01T00:00:00-05:00",
    )
    assert infinitude.system.vacation_state == "ended"


async def test_vacation_state_active_via_zone_beats_stale_window(infinitude):
    # A zone reporting the vacation activity means active even if the stored
    # window looks past.
    cfg = infinitude._config
    cfg["vacat"] = "on"
    cfg["vacstart"], cfg["vacend"] = (
        "2023-01-01T00:00:00-05:00",
        "2023-02-01T00:00:00-05:00",
    )
    zstatus = next(z for z in infinitude._status["zones"]["zone"] if z["id"] == "1")
    zstatus["currentActivity"] = "vacation"
    assert infinitude.system.vacation_state == "active"


def _last_config_post(infinitude):
    return [p for p in infinitude.posts if p["path"] == "/api/config"][-1]["data"]


async def test_set_vacation_enable_defaults_stale_window(infinitude):
    # Stale placeholder window -> enabling installs a fresh one.
    infinitude._config["vacstart"] = "2012-01-1T21:00:00-00:00"
    infinitude._config["vacend"] = "2013-01-1T21:00:00-00:00"
    await infinitude.system.set_vacation(enabled=True)
    post = _last_config_post(infinitude)
    assert post["vacat"] == "on"
    assert "vacstart" in post and "vacend" in post


async def test_set_vacation_keeps_valid_future_window(infinitude):
    # A valid future window (fixture clock is 2024-01-15) is left untouched.
    infinitude._config["vacstart"] = "2024-06-01T00:00:00-05:00"
    infinitude._config["vacend"] = "2024-07-01T00:00:00-05:00"
    await infinitude.system.set_vacation(enabled=True)
    assert _last_config_post(infinitude) == {"vacat": "on"}


async def test_set_vacation_writes_setpoints_and_fan(infinitude):
    await infinitude.system.set_vacation(heat=60, cool=80, fan=FanMode.LOW)
    assert _last_config_post(infinitude) == {
        "vacmint": "60.0",
        "vacmaxt": "80.0",
        "vacfan": "low",
    }


async def test_vacation_setpoints_parse_float_strings(infinitude):
    infinitude._config["vacmint"] = "60.0"
    infinitude._config["vacmaxt"] = "90.0"
    assert infinitude.system.vacation_heat == 60.0
    assert infinitude.system.vacation_cool == 90.0


async def test_set_vacation_disable(infinitude):
    await infinitude.system.set_vacation(enabled=False)
    assert _last_config_post(infinitude) == {"vacat": "off"}


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
