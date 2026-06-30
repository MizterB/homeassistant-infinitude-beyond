# Hardware-free Infinitude test bed

Runs the real `nebulous/infinitude` server with **no thermostat**, for local
end-to-end exercise and for regenerating config fixtures from **public** sample
data (never a real home).

## Usage

```bash
cd tests/docker
docker compose up -d            # boots Infinitude on http://localhost:13000
./seed.sh                       # loads public sample config + status

curl http://localhost:13000/api/config/   # -> real v1.7 config JSON
curl http://localhost:13000/api/status/   # -> live status snapshot JSON
docker compose down
```

## How it works

- **Boots hardware-free** — `EMULATE_SAM=1`, no `SERIAL_TTY`.
- **Seeds with two pushes** — Infinitude only ingests requests whose Host
  matches `bryant|carrier|ioncomfort|infinitude` (its `before_dispatch` hook),
  so `seed.sh` sends `Host: infinitude`:
  - config <- public `t/systems17.raw` POSTed to `/systems/{serial}` →
    `/api/config/` (zone programs, activities, `hold`, `otmr`)
  - status <- local `status.xml` POSTed to `/systems/{serial}/status` →
    `/api/status/` (`rt`, `currentActivity`, `oat`, `zoneconditioning`, ...)

No real-home data: the config is the maintainer's public sample; the status doc
is hand-authored with fabricated values.

## Why a local status doc (not `defs/status.xml`)

The upstream `defs/status.xml` is ~12 years stale and omits fields a current
system reports — verified by diffing against a live v1.7 `/api/status/`:

- zone level: missing **`zoneconditioning`** (drives the integration's
  `hvac_action`) and `damperposition`
- top level: missing `localTime`, `oprstsmsg`, `version`

`status.xml` here mirrors the current schema **and** enables the **same zones as
the config (1–2)**, so the bed presents one coherent system rather than two
mismatched samples.

## Notes

- Possible follow-up: point a devcontainer HA instance at this bed for a fully
  hardware-free HA→Infinitude loop.
