# Hardware-free Infinitude test bed

Runs the real `nebulous/infinitude` server with **no thermostat**, for local
end-to-end exercise and for regenerating config fixtures from **public** sample
data (never a real home).

## Usage

```bash
cd tests/docker
docker compose up -d            # boots Infinitude on http://localhost:13000
./seed.sh                       # loads public v1.7 sample config (systems17.raw)

curl http://localhost:13000/api/config/   # -> real v1.7 config JSON
docker compose down
```

## What works, and the boundary

- **Boots hardware-free** — `EMULATE_SAM=1`, no `SERIAL_TTY`. Verified.
- **`/api/config/` seeds from public data** — `seed.sh` POSTs the maintainer's
  `t/systems17.raw` with `Host: infinitude` (Infinitude only ingests requests
  whose Host matches `bryant|carrier|ioncomfort|infinitude`). This yields a real
  v1.7 config: zone programs, activities, `hold`, `otmr`.
- **`/api/status/` stays empty** — live status (current temperatures,
  `currentActivity`, hold `otmr`) is a *separate* push from the thermostat that
  the public config sample does not contain. So this bed is not yet a full
  HA→Infinitude loop, and the synthetic fixtures in `../fixtures/` remain the
  source of truth for status-dependent tests.

## Follow-ups

- Source or synthesize a public status document to push (enabling full e2e and
  config-derived status fixtures).
- Add a compose service + helper to point a devcontainer HA instance at this bed.
