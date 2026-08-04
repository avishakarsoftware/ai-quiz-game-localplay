#!/bin/bash
# =============================================================================
# L6 Visual Regression (SPEC-TESTING §1, §7)
# =============================================================================
# Brings up a THROWAWAY local stack and runs frontend/e2e/visual-regression.spec.ts
# against it, then tears everything down.
#
#   ./scripts/visual-regression.sh                     # compare against committed baselines
#   ./scripts/visual-regression.sh --update-snapshots   # accept new baselines
#   ./scripts/visual-regression.sh --project chromium-desktop
#
# Anything you pass is forwarded to `playwright test`.
#
# Why a dedicated stack rather than `make dev`:
#   * Its own SQLite dir under a temp folder, so a run can never mutate your dev wallet/history
#     (and every run starts from the same blank state, which is what makes the balances and the
#     "no hosting stats yet" drawer reproducible).
#   * Its own ports (9310 / 5199), so it neither collides with `make dev` (9100 / 9200) nor with
#     the default Playwright dev server (5173).
#   * Never gamma or prod: those generate quiz text with an LLM, so no screenshot of a question
#     screen could ever be a stable baseline. Local + curated content only.
# Those two ports belong to this suite; leftovers from a crashed run are killed on start.
# =============================================================================

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT=9310
FRONTEND_PORT=5199
API_URL="http://127.0.0.1:$BACKEND_PORT"
BASE_URL="http://127.0.0.1:$FRONTEND_PORT"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PY="$ROOT/backend/venv/bin/python3"
[ -x "$PY" ] || PY="$ROOT/backend/.venv/bin/python3"
[ -x "$PY" ] || PY="$ROOT/.venv/bin/python3"
if [ ! -x "$PY" ]; then
    echo -e "${RED}No backend virtualenv found. Run 'make install' first.${NC}"
    exit 1
fi

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/revelry-visual.XXXXXX")"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null
    # The vite/uvicorn child processes can outlive the shell job on abrupt exits.
    lsof -ti:$FRONTEND_PORT 2>/dev/null | xargs kill 2>/dev/null
    lsof -ti:$BACKEND_PORT 2>/dev/null | xargs kill 2>/dev/null
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

# Clear leftovers from an interrupted previous run.
lsof -ti:$BACKEND_PORT 2>/dev/null | xargs kill 2>/dev/null
lsof -ti:$FRONTEND_PORT 2>/dev/null | xargs kill 2>/dev/null

mkdir -p "$WORK_DIR/db"

echo -e "${YELLOW}Starting throwaway backend on :$BACKEND_PORT (db: $WORK_DIR/db) ...${NC}"
(
    cd "$ROOT/backend" || exit 1
    DB_DIR="$WORK_DIR/db" \
    JWT_SECRET="visual-regression-secret-32bytes!" \
    ADMIN_API_KEY="visual-regression-admin-key" \
    ALLOWED_ORIGINS="$BASE_URL,http://localhost:$FRONTEND_PORT" \
    exec "$PY" -m uvicorn main:app --host 127.0.0.1 --port "$BACKEND_PORT"
) > "$WORK_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

for _ in $(seq 1 40); do
    curl -sf "$API_URL/health" >/dev/null 2>&1 && break
    sleep 0.5
done
if ! curl -sf "$API_URL/health" >/dev/null 2>&1; then
    echo -e "${RED}Backend failed to start. Log:${NC}"
    tail -30 "$WORK_DIR/backend.log"
    exit 1
fi
echo -e "  Backend: ${GREEN}ready${NC}"

echo -e "${YELLOW}Starting frontend dev server on :$FRONTEND_PORT ...${NC}"
(
    cd "$ROOT/frontend" || exit 1
    VITE_API_URL="$API_URL" \
    exec npx vite --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) > "$WORK_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

for _ in $(seq 1 60); do
    curl -sf "$BASE_URL/" >/dev/null 2>&1 && break
    sleep 0.5
done
if ! curl -sf "$BASE_URL/" >/dev/null 2>&1; then
    echo -e "${RED}Frontend failed to start. Log:${NC}"
    tail -30 "$WORK_DIR/frontend.log"
    exit 1
fi
echo -e "  Frontend: ${GREEN}ready${NC}"
echo ""

cd "$ROOT/frontend" || exit 1

# EVERY spec that calls toHaveScreenshot must run here, or its baselines rot unnoticed.
# Learned the hard way on 2026-08-04: this script ran only visual-regression.spec.ts, so the 4
# baselines in bingo-authoring.spec.ts and drawing-game.spec.ts went 2+ months without being
# exercised and both were failing on master — a stale baseline from 2026-05-31 against a UI that had
# moved on. Nobody noticed because "the visual suite passes" was true and misleading.
# src/__tests__/visualSuiteCoverage.test.ts fails if a screenshot spec is missing from this list.
VISUAL_SPECS=(
    e2e/visual-regression.spec.ts
    e2e/bingo-authoring.spec.ts
    e2e/drawing-game.spec.ts
)

# Dedicated output dir: Playwright wipes its outputDir on start, so sharing test-results/ with
# another suite running concurrently destroys the expected/actual/diff images you need to review.
VISUAL_SNAPSHOTS=1 \
PLAYWRIGHT_BASE_URL="$BASE_URL" \
LIVE_API_BASE_URL="$API_URL" \
npx playwright test "${VISUAL_SPECS[@]}" --workers=1 --output=test-results-visual "$@"
STATUS=$?

echo ""
if [ $STATUS -eq 0 ]; then
    echo -e "${GREEN}Visual regression: PASS${NC}"
else
    echo -e "${RED}Visual regression: FAIL${NC} — open the HTML report to review expected/actual/diff:"
    echo -e "  cd frontend && npx playwright show-report"
    echo -e "Accept the new look only after reviewing it: ${YELLOW}npm run test:e2e:visual:update${NC}"
fi
exit $STATUS
