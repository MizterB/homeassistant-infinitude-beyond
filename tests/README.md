# Tests

## Layers

- **Layer 1 — API client (`test_api.py`).** Exercises the vendored
  `infinitude` client with **no Home Assistant dependency**. Fixtures are served
  by a real in-process `aiohttp` test server (`conftest.py`), so the suite is not
  coupled to aiohttp's internal mocking API.
- **Layer 2 — Home Assistant integration (`ha/`).** Uses
  `pytest-homeassistant-custom-component` to drive the config flow and entity
  platforms. It is **skipped automatically** when Home Assistant isn't installed
  (so Layer 1 can run in a minimal env) via `pytest.importorskip` and
  `collect_ignore_glob` in the parent `conftest.py`.

## Running

```bash
scripts/setup     # install Layer 1 test deps
scripts/test      # run pytest (Layer 2 is skipped unless HA is installed)
scripts/lint      # ruff check tests/

# To also run Layer 2 locally:
pip install pytest-homeassistant-custom-component
pytest
```

Both layers target Python 3.14.

## Fixtures (`fixtures/`)

The committed fixtures are **synthetic and PII-free** — generated to match the
shape of a real Carrier v1.7 system, with fabricated serials/MAC/PIN, a fixed
`-05:00` timezone, a canonical weekly schedule, and generic zone names. No data
from any real home is committed.

- `status.json`, `config.json`, `energy.json`, `profile.json` — happy-path
  baseline (raw, pre-`_simplify_json` form, with the real endpoint wrappers).
- `config_no_schedule.json` — every program period disabled (repro for the
  `_update_activities` day-walk loop, issue #42).

**Never commit real captures.** If you capture from a live system for reference,
put the raw files under `fixtures/raw/` (git-ignored) and only commit
synthetic/anonymized derivatives.

## Regression repros

Known open bugs are encoded as `xfail(strict=True)` tests so they document the
defect and will flip to a hard failure (prompting removal of the `xfail`) the
moment the bug is fixed:

| Test | Issue |
|------|-------|
| `test_post_non_json_body_does_not_crash` | #38 / #39 — `_post` crashes on a non-JSON/empty body |
| `test_compare_data_handles_type_change` | #18 — `_compare_data` calls `.keys()` on a non-dict |
| `test_hold_until_prefers_config_otmr` | "Hold indefinitely" mislabel (reads lagging `status.otmr`) |
| `test_update_activities_terminates_without_schedule` | #42 — infinite day-walk with no active schedule |

## Future: end-to-end against a real Infinitude

Upstream `nebulous/infinitude` ships a `Dockerfile` + `docker-compose.yaml` that
run the server **hardware-free** (no `SERIAL_TTY`; `EMULATE_SAM`), seeded via its
`state/` dir (e.g. the public `t/systems17.raw` v1.7 sample). A compose service
can provide a full HA → Infinitude loop with no thermostat — and regenerate the
baseline fixtures above from public sample data.
