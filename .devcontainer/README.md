# Dev container

Brings up a Home Assistant workspace **and** the hardware-free Infinitude bed
(`tests/docker`) on one network, so you can develop against either a local or a
real Infinitude.

## Start

Open the folder in a devcontainer (VS Code: "Reopen in Container"). On create it
installs `requirements.dev.txt` (runnable HA + both test layers).

Run Home Assistant:

```bash
scripts/develop          # serves HA at http://localhost:8123
```

Run the tests:

```bash
scripts/test             # Layer 1 + Layer 2 (HA is installed here)
scripts/lint
```

## Point HA at either Infinitude

When you add the **Infinitude Beyond** integration in the HA UI:

| Mode | Host | Port | Notes |
|------|------|------|-------|
| Local bed | `infinitude` | `3000` | seed it first (below) |
| Real system | your host | your port | container has outbound network |

### Seed the local bed

The `infinitude` service starts empty; load public/synthetic sample data:

```bash
tests/docker/seed.sh infinitude:3000
```

This populates `/api/config/` and `/api/status/` so HA sees a coherent two-zone
system. See `tests/docker/README.md` for what gets seeded and why.
