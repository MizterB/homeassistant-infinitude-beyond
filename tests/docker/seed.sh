#!/usr/bin/env bash
# Seed a hardware-free Infinitude with PUBLIC v1.7 sample config data.
#
# Infinitude only ingests POSTs whose Host header looks like thermostat/test
# traffic (bryant|carrier|ioncomfort|infinitude) -- see its before_dispatch
# hook -- so we send `Host: infinitude`. This populates /api/config/ with the
# maintainer's public sample system (t/systems17.raw). No real-home data.
#
# NOTE: /api/status/ stays empty -- live status (current temps, activities,
# otmr) is a separate push the public sample does not include. For status-
# dependent assertions, use the synthetic fixtures in tests/fixtures/.
set -euo pipefail

HOST_PORT="${1:-localhost:13000}"
SAMPLE_URL="https://raw.githubusercontent.com/nebulous/infinitude/master/t/systems17.raw"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
curl -fsSL "$SAMPLE_URL" -o "$tmp"

curl -fsS -o /dev/null -w "seed POST: %{http_code}\n" \
    -H "Host: infinitude" \
    --data-urlencode "data@$tmp" \
    "http://${HOST_PORT}/systems/systems17test"

echo "Seeded. Verify: curl http://${HOST_PORT}/api/config/"
