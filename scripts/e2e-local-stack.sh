#!/usr/bin/env bash
# =============================================================================
# Boot a throwaway local stack (backend + vite) and run a command against it.
#
#   ./scripts/e2e-local-stack.sh npx playwright test e2e/all-games.spec.ts --project chromium-desktop
#
# The command runs from frontend/ with:
#   PLAYWRIGHT_BASE_URL  -> the throwaway vite server
#   LIVE_API_BASE_URL    -> the throwaway backend (fresh SQLite in a temp dir)
#
# This is the same boot pattern as visual-regression.sh, extracted so CI can run the
# all-games behavioral suite without a human remembering to start a stack (REVIEW-2026-08 T1
# — the canonical "every game is playable" suite previously ran in no CI at all).
# Ports 9100/9200 match the documented all-games convention (package.json test:e2e:all-games).
# =============================================================================

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT="${E2E_BACKEND_PORT:-9100}"
FRONTEND_PORT="${E2E_FRONTEND_PORT:-9200}"
API_URL="http://127.0.0.1:$BACKEND_PORT"
BASE_URL="http://127.0.0.1:$FRONTEND_PORT"

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 <command...>   (runs from frontend/ against the throwaway stack)" >&2
    exit 1
fi

PY="$ROOT/backend/venv/bin/python3"
[ -x "$PY" ] || PY="$ROOT/backend/.venv/bin/python3"
[ -x "$PY" ] || PY="$ROOT/.venv/bin/python3"
if [ ! -x "$PY" ]; then
    echo "No backend virtualenv found (backend/venv). Run 'make install' first." >&2
    exit 1
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/revelry-e2e.XXXXXX")"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    # vite/uvicorn children can outlive the shell job on abrupt exits
    lsof -ti:$FRONTEND_PORT 2>/dev/null | xargs kill 2>/dev/null
    lsof -ti:$BACKEND_PORT 2>/dev/null | xargs kill 2>/dev/null
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

# Clear leftovers from an interrupted previous run.
lsof -ti:$BACKEND_PORT 2>/dev/null | xargs kill 2>/dev/null
lsof -ti:$FRONTEND_PORT 2>/dev/null | xargs kill 2>/dev/null

mkdir -p "$WORK_DIR/db"

# SIGNUP_BONUS_IP_DAILY_LIMIT=0 below: the per-IP signup-bonus allowance (REVIEW-2026-08 S2) is
# meaningless in a throwaway single-IP harness and actively breaks it. This suite mints ~76 device
# wallets from one address, so wallet #21+ gets the daily bonus only (10 sparks, exactly COST_ROOM)
# and — since grace requires a signup-bonus proof (2026-08-08 hardening) — no free rooms either.
# That combination failed 37 of 76 all-games tests in CI. 0 disables the allowance.
# NOTE: keep it inside the unbroken `VAR=x \` chain. A comment line between continuations makes
# bash join `... # comment` and swallow everything after it, INCLUDING the exec — `bash -n` still
# passes and the backend simply never starts.
echo "[stack] backend on :$BACKEND_PORT (db: $WORK_DIR/db)"
(
    cd "$ROOT/backend" || exit 1
    DB_DIR="$WORK_DIR/db" \
    JWT_SECRET="e2e-local-stack-secret-32bytes!!" \
    ADMIN_API_KEY="e2e-local-stack-admin-key" \
    ALLOWED_ORIGINS="$BASE_URL,http://localhost:$FRONTEND_PORT" \
    SIGNUP_BONUS_IP_DAILY_LIMIT=0 \
    exec "$PY" -m uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT"
) > "$WORK_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

for _ in $(seq 1 60); do
    curl -sf "$API_URL/health" >/dev/null 2>&1 && break
    sleep 0.5
done
if ! curl -sf "$API_URL/health" >/dev/null 2>&1; then
    echo "[stack] backend failed to start:" >&2
    tail -30 "$WORK_DIR/backend.log" >&2
    exit 1
fi

echo "[stack] frontend on :$FRONTEND_PORT"
(
    cd "$ROOT/frontend" || exit 1
    VITE_API_URL="$API_URL" \
    exec npx vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) > "$WORK_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

for _ in $(seq 1 90); do
    curl -sf "$BASE_URL/" >/dev/null 2>&1 && break
    sleep 0.5
done
if ! curl -sf "$BASE_URL/" >/dev/null 2>&1; then
    echo "[stack] frontend failed to start:" >&2
    tail -30 "$WORK_DIR/frontend.log" >&2
    exit 1
fi

echo "[stack] ready — running: $*"
(
    cd "$ROOT/frontend" || exit 1
    PLAYWRIGHT_BASE_URL="$BASE_URL" \
    LIVE_API_BASE_URL="$API_URL" \
    "$@"
)
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo "[stack] command failed ($STATUS). Backend log tail:" >&2
    tail -20 "$WORK_DIR/backend.log" >&2
fi
exit $STATUS
