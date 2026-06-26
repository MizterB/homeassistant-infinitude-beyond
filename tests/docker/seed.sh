#!/usr/bin/env bash
# Seed a hardware-free Infinitude with PUBLIC sample data.
#
# Infinitude only ingests POSTs whose Host header looks like thermostat/test
# traffic (bryant|carrier|ioncomfort|infinitude) -- see its before_dispatch
# hook -- so every push below sends `Host: infinitude`. No real-home data.
#
#   config  <- t/systems17.raw  (v1.7 system: programs, activities, hold/otmr)
#   status  <- defs/status.xml  (live snapshot: rt, currentActivity, oat, ...)
set -euo pipefail

HOST_PORT="${1:-localhost:13000}"
SERIAL="systems17test"
RAW="https://raw.githubusercontent.com/nebulous/infinitude/master"

tmp_cfg="$(mktemp)"; tmp_stat="$(mktemp)"
trap 'rm -f "$tmp_cfg" "$tmp_stat"' EXIT
curl -fsSL "$RAW/t/systems17.raw" -o "$tmp_cfg"
curl -fsSL "$RAW/defs/status.xml" -o "$tmp_stat"

curl -fsS -o /dev/null -w "config POST: %{http_code}\n" \
    -H "Host: infinitude" --data-urlencode "data@$tmp_cfg" \
    "http://${HOST_PORT}/systems/${SERIAL}"

curl -fsS -o /dev/null -w "status POST: %{http_code}\n" \
    -H "Host: infinitude" --data-urlencode "data@$tmp_stat" \
    "http://${HOST_PORT}/systems/${SERIAL}/status"

echo "Seeded. Verify: curl http://${HOST_PORT}/api/config/ and /api/status/"
