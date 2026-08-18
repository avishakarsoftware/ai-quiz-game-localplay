"""Run the REAL `supabase_db.py` against a REAL PostgREST + Postgres.

WHY THIS EXISTS (ANALYSIS-2026-08-09-coverage.md §1)
`supabase_db.py` — the module production actually runs — sat at **30% coverage**, with 33 functions
never executed once, while `db.py` (SQLite, local dev only) sat at 87%. Coverage was inverted with
respect to risk. The pre-existing `test_postgres_parity.py` tests the **SQL functions** directly via
psycopg; it never imports `supabase_db`, so the Python layer — PostgREST filter strings, response
reshaping, key names — had no coverage from either suite. That is exactly the class of bug that has
already shipped here once (the Supabase `new_balance` response key).

WHY REAL POSTGREST RATHER THAN A FAKE CLIENT
A psycopg-backed stand-in for `SupabaseClient` would exercise the business logic but bypass
`_request` — and `_request` plus the `filters={"id": "eq.<x>"}` strings are precisely where the
likely bugs are. A fake would validate my own re-implementation of PostgREST semantics. So the stack
is genuine: real HTTP, real PostgREST query parsing, real Postgres constraints and RPCs.

THE ONE PIECE OF GLUE, AND ITS LIMITS
`SupabaseClient` hardcodes `/rest/v1/...` paths; PostgREST serves at `/...`. So a tiny threaded
forwarder strips that prefix and forwards method, query, body and headers **verbatim**. It emulates
no PostgREST behavior — it is a dumb pipe, which is what keeps the fidelity argument above honest.

SAFETY (non-negotiable — Codex's rail, enforced here rather than merely documented)
This suite TRUNCATES TABLES. `_assert_local_target()` refuses to run against anything but a
loopback host, so a stray `PARITY_POSTGREST_URL=https://<project>.supabase.co` aborts instead of
wiping gamma or production. Never point these vars at a hosted Supabase project.

USAGE
    ./scripts/parity-stack.sh up        # prints the three env vars to export
    PARITY_POSTGRES_DSN=... PARITY_POSTGREST_URL=... PARITY_POSTGREST_JWT=... \
        venv/bin/python -m pytest tests/test_supabase_money_rails.py -q
Skips cleanly when the vars are absent, so the default local run is unaffected.
"""
import http.server
import os
import socketserver
import threading
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

import pytest

DSN = os.getenv("PARITY_POSTGRES_DSN", "")
POSTGREST_URL = os.getenv("PARITY_POSTGREST_URL", "")
POSTGREST_JWT = os.getenv("PARITY_POSTGREST_JWT", "")

HARNESS_READY = bool(DSN and POSTGREST_URL and POSTGREST_JWT)
SKIP_REASON = (
    "PARITY_POSTGRES_DSN / PARITY_POSTGREST_URL / PARITY_POSTGREST_JWT not set — "
    "Supabase-over-PostgREST suite skipped (run ./scripts/parity-stack.sh up)"
)

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0", "pg", "postgres"}


def _assert_local_target() -> None:
    """Refuse to run destructive tests against anything that isn't loopback.

    This suite truncates tables. A misconfigured env var must fail loudly, not quietly destroy
    gamma or production wallet data.
    """
    for label, url in (("PARITY_POSTGREST_URL", POSTGREST_URL), ("PARITY_POSTGRES_DSN", DSN)):
        host = (urlparse(url).hostname or "").lower()
        if host not in _LOCAL_HOSTS:
            raise RuntimeError(
                f"REFUSING TO RUN: {label} points at {host!r}, not a local test stack. "
                "This suite TRUNCATES TABLES. Point it at a throwaway Postgres "
                "(./scripts/parity-stack.sh up) — never at a hosted Supabase project."
            )
        if "supabase.co" in (url or ""):
            raise RuntimeError(f"REFUSING TO RUN: {label} looks like a hosted Supabase project.")


class _PrefixStrippingProxy(http.server.BaseHTTPRequestHandler):
    """Maps /rest/v1/<path> -> <path> on the upstream PostgREST. A pipe, not an emulator."""

    upstream = ""

    def _forward(self) -> None:
        path = self.path
        if path.startswith("/rest/v1"):
            path = path[len("/rest/v1"):]
        body: Optional[bytes] = None
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            body = self.rfile.read(length)
        request = urllib.request.Request(self.upstream + path, data=body, method=self.command)
        for key, value in self.headers.items():
            if key.lower() not in ("host", "content-length"):
                request.add_header(key, value)
        try:
            with urllib.request.urlopen(request) as response:
                payload, status, headers = response.read(), response.status, response.headers
        except urllib.error.HTTPError as exc:            # 4xx/5xx must reach the client verbatim:
            payload, status, headers = exc.read(), exc.code, exc.headers   # SupabaseDBError depends on it
        except urllib.error.URLError as exc:
            payload, status, headers = str(exc).encode(), 502, {}
        self.send_response(status)
        for key, value in (headers.items() if headers else []):
            if key.lower() not in ("transfer-encoding", "connection", "content-length"):
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PATCH = do_DELETE = do_PUT = _forward

    def log_message(self, *args) -> None:  # keep pytest output clean
        pass


class _ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


# Every table the schema defines, so truncation can't silently miss one and leak state between
# tests. Ordered arbitrarily — TRUNCATE ... CASCADE handles dependencies.
_TABLES = (
    "wallets", "token_transactions", "users", "entitlements", "device_usage",
    "deleted_accounts", "webhook_events", "idempotency_keys", "pending_tokens",
    "achievements", "gifts", "share_snapshots", "game_results", "app_settings",
    "quiz_packs", "quiz_questions", "generated_content", "media_assets",
    "game_sessions", "host_app_catalog_flags",
)


def start_proxy() -> tuple[_ThreadedServer, str]:
    """Start the forwarder; returns (server, base_url) for config.SUPABASE_URL."""
    _assert_local_target()
    _PrefixStrippingProxy.upstream = POSTGREST_URL.rstrip("/")
    server = _ThreadedServer(("127.0.0.1", 0), _PrefixStrippingProxy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def truncate_all(psycopg_module) -> None:
    """Wipe every games_* table. Guarded by _assert_local_target()."""
    _assert_local_target()
    with psycopg_module.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cur:
            existing = [
                t for (t,) in cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name LIKE 'games_%'"
                ).fetchall()
            ]
            wanted = {f"games_{t}" for t in _TABLES} & set(existing)
            if wanted:
                cur.execute(f"TRUNCATE {', '.join(sorted(wanted))} CASCADE")


@pytest.fixture(scope="session")
def _proxy_base_url():
    """Session-scoped: the forwarder only (starting it per test would be wasteful).

    Deliberately does NOT mutate config — a session-scoped config change would leak into every
    later test in the run, which is precisely the cross-suite contamination fixed earlier the same
    day for the SQLite DB_DIR. Config is applied per test, via monkeypatch, below.
    """
    if not HARNESS_READY:
        pytest.skip(SKIP_REASON, allow_module_level=False)
    pytest.importorskip("psycopg")
    _assert_local_target()
    server, base_url = start_proxy()
    try:
        yield base_url
    finally:
        server.shutdown()


@pytest.fixture
def postgrest_stack(_proxy_base_url, monkeypatch):
    """Per-test: point config at the local stack (auto-reverted) and hand back psycopg."""
    import psycopg

    import config
    import supabase_db

    monkeypatch.setattr(config, "DB_BACKEND", "supabase")
    monkeypatch.setattr(config, "SUPABASE_URL", _proxy_base_url)
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", POSTGREST_JWT)
    monkeypatch.setattr(config, "TABLE_PREFIX", "games_")
    # The cached client holds the previous base_url; drop it either side of the test.
    monkeypatch.setattr(supabase_db, "_client", None)
    yield psycopg
    supabase_db._client = None


@pytest.fixture
def sdb(postgrest_stack):
    """Per-test: truncated database, returns the supabase_db module under test."""
    truncate_all(postgrest_stack)
    import supabase_db
    return supabase_db
