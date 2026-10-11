"""Qualify the narrow account-content RPC migration only on a disposable local database."""
import os
from pathlib import Path
import re
import uuid

import pytest

from postgres_target_safety import connect_local_postgres

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ("games_", "games_gamma_")


def _migration(prefix):
    suffix = "_gamma" if prefix == "games_gamma_" else ""
    return ROOT / "sql" / "migrations" / f"20261010T000000_account_content_deletion{suffix}.sql"


@pytest.mark.parametrize("prefix", PREFIXES)
def test_rendered_schema_and_targeted_delete_rpc_match_template(prefix):
    template = (ROOT / "sql/templates/games-schema.template.sql").read_text()
    rendered = ROOT / "sql" / ("games-gamma-schema.sql" if prefix == "games_gamma_" else "games-schema.sql")
    assert rendered.read_text() == template.replace("__PREFIX__", prefix)
    function = re.search(r"CREATE OR REPLACE FUNCTION __PREFIX__delete_account\(.*?\n\$\$;", template, re.S)
    assert function is not None
    assert function.group(0).replace("__PREFIX__", prefix) in _migration(prefix).read_text()


@pytest.fixture(params=PREFIXES)
def local_rpc(request):
    dsn = os.getenv("PARITY_POSTGRES_DSN", "")
    if not dsn:
        pytest.skip("PARITY_POSTGRES_DSN not set — requires a disposable local Postgres")
    pytest.importorskip("psycopg")
    prefix = request.param
    with connect_local_postgres(dsn, autocommit=True) as conn:
        rendered = ROOT / "sql" / ("games-gamma-schema.sql" if prefix == "games_gamma_" else "games-schema.sql")
        conn.execute(rendered.read_text())
        # Exercise the migration's own grant, rather than the harness's broad grant.
        conn.execute(f"REVOKE EXECUTE ON FUNCTION {prefix}delete_account(TEXT) FROM service_role")
        conn.execute(_migration(prefix).read_text())
        yield conn, prefix


def test_migration_allows_only_service_role(local_rpc):
    import psycopg

    conn, prefix = local_rpc
    signature = f"public.{prefix}delete_account(text)"
    for role, allowed in (("anon", False), ("authenticated", False), ("service_role", True)):
        assert conn.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, signature)).fetchone()[0] is allowed
    assert conn.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_proc p, LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) a "
        "WHERE p.oid = %s::regprocedure AND a.grantee = 0 AND a.privilege_type = 'EXECUTE')", (signature,),
    ).fetchone()[0] is False
    user = f"qa-account-{uuid.uuid4().hex}"
    for role in ("anon", "authenticated"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with conn.transaction():
                conn.execute(f"SET LOCAL ROLE {role}")
                conn.execute(f"SELECT {prefix}delete_account(%s)", (user,))
    assert conn.execute(f"SELECT 1 FROM {prefix}deleted_accounts WHERE user_id = %s", (user,)).fetchone() is None
    with conn.transaction():
        conn.execute("SET LOCAL ROLE service_role")
        assert conn.execute(f"SELECT {prefix}delete_account(%s)", (user,)).fetchone()[0] == {"deleted": True}


def _seed(conn, prefix, owner):
    pack, question, media = (uuid.uuid4().hex for _ in range(3))
    conn.execute(f"INSERT INTO {prefix}wallets (id, balance, created_at, updated_at) VALUES (%s, 100, 0, 0)", (owner,))
    conn.execute(f"INSERT INTO {prefix}token_transactions (wallet_id, amount, reason, balance_after, created_at) VALUES (%s, 100, 'qa', 100, 0)", (owner,))
    conn.execute(f"INSERT INTO {prefix}quiz_packs (id, owner_wallet_id, title, status, question_count, created_at, updated_at) "
                 "VALUES (%s, %s, 'QA pack', 'deleted', 1, 0, 0)", (pack, owner))
    conn.execute(f"INSERT INTO {prefix}quiz_questions (id, pack_id, position, text, options, answer_index, created_at, updated_at) "
                 "VALUES (%s, %s, 0, 'QA question', '[\"One\", \"Two\"]', 0, 0, 0)", (question, pack))
    conn.execute(f"INSERT INTO {prefix}media_assets (id, owner_wallet_id, storage_backend, storage_path, public_url, mime_type, created_at, updated_at) "
                 "VALUES (%s, %s, 'ionos', 'qa/image.png', 'https://example.invalid/qa.png', 'image/png', 0, 0)", (media, owner))
    return pack, question, media


def test_migration_deletes_owned_content_and_preserves_foreign_content_and_ledger(local_rpc):
    conn, prefix = local_rpc
    owner, stranger = (f"qa-account-{uuid.uuid4().hex}" for _ in range(2))
    owned = _seed(conn, prefix, owner)
    foreign = _seed(conn, prefix, stranger)
    with conn.transaction():
        conn.execute("SET LOCAL ROLE service_role")
        assert conn.execute(f"SELECT {prefix}delete_account(%s)", (owner,)).fetchone()[0] == {"deleted": True}
    for table, own_id, foreign_id in zip(("quiz_packs", "quiz_questions", "media_assets"), owned, foreign):
        assert conn.execute(f"SELECT 1 FROM {prefix}{table} WHERE id = %s", (own_id,)).fetchone() is None
        assert conn.execute(f"SELECT 1 FROM {prefix}{table} WHERE id = %s", (foreign_id,)).fetchone()
    assert conn.execute(f"SELECT balance FROM {prefix}wallets WHERE id = %s", (stranger,)).fetchone()[0] == 100
    assert conn.execute(f"SELECT 1 FROM {prefix}token_transactions WHERE wallet_id = %s", (owner,)).fetchone()


def test_migration_failure_rolls_back_content_wallet_and_denylist(local_rpc):
    import psycopg

    conn, prefix = local_rpc
    owner = f"qa-account-{uuid.uuid4().hex}"
    owned = _seed(conn, prefix, owner)
    trigger = f"qa_account_{uuid.uuid4().hex}"
    conn.execute(f"CREATE FUNCTION {trigger}() RETURNS trigger LANGUAGE plpgsql AS $$ "
                 "BEGIN RAISE EXCEPTION 'simulated media deletion failure'; END; $$")
    conn.execute(f"CREATE TRIGGER {trigger} BEFORE DELETE ON {prefix}media_assets FOR EACH ROW EXECUTE FUNCTION {trigger}()")
    try:
        with pytest.raises(psycopg.errors.RaiseException, match="simulated media deletion failure"):
            with conn.transaction():
                conn.execute("SET LOCAL ROLE service_role")
                conn.execute(f"SELECT {prefix}delete_account(%s)", (owner,))
        for table, row_id in zip(("quiz_packs", "quiz_questions", "media_assets"), owned):
            assert conn.execute(f"SELECT 1 FROM {prefix}{table} WHERE id = %s", (row_id,)).fetchone()
        assert conn.execute(f"SELECT balance FROM {prefix}wallets WHERE id = %s", (owner,)).fetchone()[0] == 100
        assert conn.execute(f"SELECT 1 FROM {prefix}deleted_accounts WHERE user_id = %s", (owner,)).fetchone() is None
    finally:
        conn.execute(f"DROP TRIGGER {trigger} ON {prefix}media_assets")
        conn.execute(f"DROP FUNCTION {trigger}()")
