#!/usr/bin/env bash
# Demo-day pre-warm: wait until the backend is fully ready, then print quota + golden run.
#   bash backend/scripts/prewarm.sh [BASE_URL]
set -euo pipefail
BASE="${1:-https://ripun-j-kashyap--mimic-backend-web.modal.run}"
echo "Pre-warming $BASE"
start=$(date +%s)
until curl -sf -m 20 "$BASE/health" | grep -q '"browser_ready":true'; do
  echo "  waiting… $(( $(date +%s) - start ))s"; sleep 3
done
echo "✅ ready in $(( $(date +%s) - start ))s: $(curl -s "$BASE/health")"
echo "Quota: $(curl -s "$BASE/health/quota")"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/demo/")
echo "Demo site: HTTP $code"
echo "Golden run: $(curl -s "$BASE/runs/golden")"
