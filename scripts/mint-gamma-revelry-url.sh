#!/usr/bin/env bash
#
# Mint a short-lived gamma party-games URL tied to the seeded "Gamma Full Flow
# Test Party" so the Revelry e2e matrix (incl. the mirror-results-back test)
# runs green. Mirrors revelryapp/scripts/mint-localplay-gamma-url.py, but pulls
# the integration secret from the running gamma container over SSH so it works
# without a local gcloud-secrets setup. The secret never leaves the VM; only the
# URL is written locally.
#
# Usage:
#   ./scripts/mint-gamma-revelry-url.sh                 # writes ./gamma_party_games_url.txt, 1h TTL
#   ./scripts/mint-gamma-revelry-url.sh 3600 /tmp/x.txt # custom ttl + output
#
# Then:
#   cd frontend && PREPROD_REVELRY=1 \
#     REVELRY_GAMMA_PARTY_GAMES_URL_FILE=../gamma_party_games_url.txt \
#     npm run test:e2e:gamma:revelry
#
set -euo pipefail

PARTY_ID="bc87a6df-9f2e-4ac3-acbf-b89dc82f127e"   # seeded gamma party (real, mirrors results)
PARTY_NAME="Gamma Full Flow Test Party"
TTL="${1:-3600}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${2:-$ROOT/gamma_party_games_url.txt}"
RETURN_URL="https://api-gamma.revelryapp.me/party/$PARTY_ID?tab=games"

PAYLOAD=$(cat <<JSON
{"external_context":{"host_app":"revelry","external_container_type":"party","external_container_id":"$PARTY_ID","external_container_title":"$PARTY_NAME","host_user_id":"gamma-e2e-host","return_url":"$RETURN_URL"},"actor":{"external_user_id":"gamma-e2e-host","display_name":"Gamma E2E Host","role":"host","capabilities":["operate_game","manage_games","author_content"]},"return_url":"$RETURN_URL","intent":"hub","ttl_seconds":$TTL}
JSON
)

URL=$(gcloud compute ssh revelry-backend --zone us-central1-a --command "
SECRET=\$(docker exec games-backend-gamma printenv REVELRY_INTEGRATION_SECRET)
curl -s -X POST http://127.0.0.1:8004/integrations/revelry/party-games-link \
  -H \"Authorization: Bearer \$SECRET\" -H 'Content-Type: application/json' \
  -H 'Host: gamesapi-gamma.revelryapp.me' -H 'X-Forwarded-Proto: https' \
  --data '$PAYLOAD'
" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('party_games_url',''))")

if [[ -z "$URL" || "$URL" != https://gamesapi-gamma.revelryapp.me/* ]]; then
  echo "error: failed to mint gamma party-games URL" >&2
  exit 1
fi

printf '%s\n' "$URL" > "$OUT"
echo "Wrote gamma party-games URL ($TTL s TTL) for party $PARTY_ID -> $OUT"
