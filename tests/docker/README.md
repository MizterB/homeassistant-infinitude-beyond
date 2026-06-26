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
- **Seeds from public data, two pushes** — Infinitude only ingests requests
  whose Host matches `bryant|carrier|ioncomfort|infinitude` (its
  `before_dispatch` hook), so `seed.sh` sends `Host: infinitude`:
  - config <- `t/systems17.raw` POSTed to `/systems/{serial}` → `/api/config/`
    (zone programs, activities, `hold`, `otmr`)
  - status <- `defs/status.xml` POSTed to `/systems/{serial}/status` →
    `/api/status/` (`rt`, `currentActivity`, `oat`, ...)

Both samples are the maintainer's public fixtures — no real-home data.

## Notes

- The two public samples don't perfectly agree on which zones are enabled
  (config enables zones 1–2; the status sample enables 1, 3–8). Fine for a
  smoke/e2e target; the synthetic fixtures in `../fixtures/` remain the
  controlled inputs for assertion-level tests.
- Possible follow-up: point a devcontainer HA instance at this bed for a fully
  hardware-free HA→Infinitude loop.
