#!/usr/bin/env bash
# Seed a hardware-free Infinitude with PUBLIC sample data.
#
# Infinitude only ingests POSTs whose Host header looks like thermostat/test
# traffic (bryant|carrier|ioncomfort|infinitude) -- see its before_dispatch
# hook -- so every push below sends `Host: infinitude`. No real-home data.
#
#   config  <- t/systems17.raw  (public v1.7 system: programs, activities, hold/otmr)
#   status  <- ./status.xml      (local; modern schema, consistent with the config)
#
# Why a local status doc: the upstream defs/status.xml is ~12 years stale and
# omits fields a current system reports (notably zone `zoneconditioning` and
# `damperposition`). status.xml here mirrors a current v1.7 status schema and
# enables the SAME zones as the config (1-2), with fabricated values -- no
# real-home data.
set -euo pipefail

HOST_PORT="${1:-localhost:13000}"
SERIAL="systems17test"
HERE="$(cd "$(dirname "$0")" && pwd)"
RAW="https://raw.githubusercontent.com/nebulous/infinitude/master"

tmp_cfg="$(mktemp)"
trap 'rm -f "$tmp_cfg"' EXIT
curl -fsSL "$RAW/t/systems17.raw" -o "$tmp_cfg"

curl -fsS -o /dev/null -w "config POST: %{http_code}\n" \
    -H "Host: infinitude" --data-urlencode "data@$tmp_cfg" \
    "http://${HOST_PORT}/systems/${SERIAL}"

curl -fsS -o /dev/null -w "status POST: %{http_code}\n" \
    -H "Host: infinitude" --data-urlencode "data@${HERE}/status.xml" \
    "http://${HOST_PORT}/systems/${SERIAL}/status"

echo "Seeded. Verify: curl http://${HOST_PORT}/api/config/ and /api/status/"
