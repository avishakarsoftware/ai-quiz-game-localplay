#!/usr/bin/env bash
# =============================================================================
# Throwaway Postgres + PostgREST for the Supabase-path test suites.
#
#   ./scripts/parity-stack.sh up      # start, apply schema, print env exports
#   ./scripts/parity-stack.sh down    # remove both containers
#   ./scripts/parity-stack.sh env     # re-print the exports for a running stack
#
# WHY: production runs supabase_db.py over PostgREST, and that module was at 30% coverage with 33
# functions never executed (ANALYSIS-2026-08-09-coverage.md). Testing it needs the real REST layer,
# not a fake client — the likely bugs live in the PostgREST filter strings and response shapes that
# a fake would bypass. See backend/tests/postgrest_harness.py.
#
# Ports 55450/55451 are chosen to avoid this machine's other project containers (55432/55433 are
# taken by an unrelated stack). Nothing here touches gamma or production; the harness itself refuses
# to run against a non-loopback host because these suites TRUNCATE TABLES.
# =============================================================================

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PG_NAME="revelry-parity-pg"
REST_NAME="revelry-parity-rest"
PG_PORT="${PARITY_PG_PORT:-55450}"
REST_PORT="${PARITY_REST_PORT:-55451}"
PG_PASS="parity"
# Test-only secret. PostgREST needs >=32 chars for HS256.
JWT_SECRET="${PARITY_JWT_SECRET:-parity-postgrest-jwt-secret-at-least-32-chars-long}"
POSTGREST_IMAGE="postgrest/postgrest:v12.2.3"
PG_IMAGE="postgres:16"

die() { echo "[parity] ERROR: $*" >&2; exit 1; }

# PyJWT lives in backend/venv locally, but CI installs requirements into the system python.
# Resolve whichever has it, so the same script works in both places.
resolve_python() {
    for candidate in "$ROOT/backend/venv/bin/python" "$ROOT/backend/.venv/bin/python" python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
            if "$candidate" -c "import jwt" >/dev/null 2>&1; then
                echo "$candidate"; return 0
            fi
        fi
    done
    return 1
}

mint_jwt() {
    local py; py="$(resolve_python)" || die "no python with PyJWT found (pip install PyJWT)"
    # A service_role JWT, exactly the shape Supabase issues, so PostgREST assumes that role.
    "$py" - "$JWT_SECRET" <<'PY'
import sys
import jwt
print(jwt.encode({"role": "service_role"}, sys.argv[1], algorithm="HS256"))
PY
}

print_env() {
    local token; token="$(mint_jwt)" || die "could not mint a JWT (is PyJWT in backend/venv?)"
    cat <<EOF
export PARITY_POSTGRES_DSN='postgresql://postgres:${PG_PASS}@127.0.0.1:${PG_PORT}/parity'
export PARITY_POSTGREST_URL='http://127.0.0.1:${REST_PORT}'
export PARITY_POSTGREST_JWT='${token}'
EOF
}

case "${1:-up}" in
down)
    docker rm -f "$PG_NAME" "$REST_NAME" >/dev/null 2>&1
    echo "[parity] removed $PG_NAME and $REST_NAME"
    exit 0
    ;;
env)
    print_env
    exit 0
    ;;
up) ;;
*)  die "usage: $0 [up|down|env]" ;;
esac

for p in "$PG_PORT" "$REST_PORT"; do
    if command -v lsof >/dev/null 2>&1 && lsof -ti:"$p" >/dev/null 2>&1; then
        # Only complain if it isn't our own stack already listening.
        docker ps --format '{{.Names}}' | grep -qE "^($PG_NAME|$REST_NAME)$" || \
            die "port $p is in use by something else. Set PARITY_PG_PORT/PARITY_REST_PORT."
    fi
done

docker rm -f "$PG_NAME" "$REST_NAME" >/dev/null 2>&1

echo "[parity] starting $PG_IMAGE on 127.0.0.1:$PG_PORT"
docker run -d --name "$PG_NAME" \
    -e POSTGRES_PASSWORD="$PG_PASS" -e POSTGRES_DB=parity \
    -p "127.0.0.1:${PG_PORT}:5432" "$PG_IMAGE" >/dev/null || die "could not start Postgres"

for _ in $(seq 1 60); do
    docker exec "$PG_NAME" pg_isready -U postgres -q 2>/dev/null && break
    sleep 1
done
docker exec "$PG_NAME" pg_isready -U postgres -q 2>/dev/null || die "Postgres never became ready"

# Roles BEFORE the schema: the RLS policies reference service_role/anon, and applying the schema
# without them silently skips 52 policy statements (they error, the tables still get created, and it
# looks like it worked).
echo "[parity] creating Supabase-equivalent roles"
docker exec -i "$PG_NAME" psql -U postgres -d parity -q >/dev/null <<'SQL'
DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE service_role NOLOGIN BYPASSRLS; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticator LOGIN PASSWORD 'parity' NOINHERIT; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
GRANT anon, authenticated, service_role TO authenticator;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
SQL
ROLES=$(docker exec "$PG_NAME" psql -U postgres -d parity -tAc \
    "select count(*) from pg_roles where rolname in ('anon','authenticated','service_role','authenticator')")
[ "$ROLES" = "4" ] || die "expected 4 roles, found $ROLES (did the heredoc reach psql? -i is required)"

echo "[parity] applying sql/games-schema.sql (prod prefix: games_)"
ERRORS=$(docker exec -i "$PG_NAME" psql -U postgres -d parity < "$ROOT/sql/games-schema.sql" 2>&1 | grep -ci '^ERROR' || true)
[ "$ERRORS" = "0" ] || die "schema applied with $ERRORS errors"
docker exec -i "$PG_NAME" psql -U postgres -d parity -q >/dev/null <<'SQL'
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;
SQL

TABLES=$(docker exec "$PG_NAME" psql -U postgres -d parity -tAc \
    "select count(*) from information_schema.tables where table_schema='public' and table_name like 'games_%'")
FUNCS=$(docker exec "$PG_NAME" psql -U postgres -d parity -tAc \
    "select count(*) from information_schema.routines where routine_schema='public' and routine_name like 'games_%'")
echo "[parity] schema: $TABLES tables, $FUNCS functions"

echo "[parity] starting PostgREST on 127.0.0.1:$REST_PORT"
docker run -d --name "$REST_NAME" --link "$PG_NAME":pg \
    -e PGRST_DB_URI="postgres://authenticator:${PG_PASS}@pg:5432/parity" \
    -e PGRST_DB_SCHEMAS="public" \
    -e PGRST_DB_ANON_ROLE="anon" \
    -e PGRST_JWT_SECRET="$JWT_SECRET" \
    -p "127.0.0.1:${REST_PORT}:3000" "$POSTGREST_IMAGE" >/dev/null || die "could not start PostgREST"

for _ in $(seq 1 60); do
    curl -sf "http://127.0.0.1:${REST_PORT}/" >/dev/null 2>&1 && break
    sleep 1
done
curl -sf "http://127.0.0.1:${REST_PORT}/" >/dev/null 2>&1 || {
    docker logs "$REST_NAME" 2>&1 | tail -15 >&2
    die "PostgREST never became ready"
}

echo "[parity] ready. Export these, then run the suites:"
echo ""
print_env
