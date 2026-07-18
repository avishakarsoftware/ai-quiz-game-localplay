"""Postgres parity tests for the rendered Supabase schema (sql/games-schema.sql).

The SQLite adapter (db.py) and the Supabase RPCs (rendered from
sql/templates/games-schema.template.sql) implement the same wallet semantics,
but until now the SQL side was only ever validated by applying it to the live
project. This module applies the rendered production-prefix schema to a real
Postgres and exercises the RPCs, asserting the SAME behavior the SQLite tests
assert — so template drift breaks CI instead of gamma.

Runs only when PARITY_POSTGRES_DSN is set (CI provides a postgres:16 service
container; locally: `docker run -e POSTGRES_PASSWORD=parity -p 5432:5432 postgres:16`
then PARITY_POSTGRES_DSN=postgresql://postgres:parity@localhost:5432/postgres).
Skips cleanly otherwise so the default local run is unaffected.
"""
import os
import pathlib
import uuid

import pytest

DSN = os.getenv("PARITY_POSTGRES_DSN", "")

psycopg = pytest.importorskip("psycopg") if DSN else None
if not DSN:
    pytest.skip("PARITY_POSTGRES_DSN not set — Postgres parity suite skipped", allow_module_level=True)

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "sql" / "games-schema.sql"

# Mirrors config.py defaults the RPC constants are rendered from.
SIGNUP_BONUS = 20
DAILY_BONUS = 10   # STREAK_BASE
STREAK_STEP = 5    # c_step constant inside games_grant_daily_bonus
STREAK_MAX = 30    # c_max constant inside games_grant_daily_bonus
MAX_BALANCE = 1000


@pytest.fixture(scope="module")
def conn():
    connection = psycopg.connect(DSN, autocommit=True)
    with connection.cursor() as cur:
        # The rendered schema GRANTs to Supabase's built-in roles; create them
        # as no-login roles so the grants apply on vanilla Postgres.
        for role in ("anon", "authenticated", "service_role"):  # fixed safe set — not user input
            cur.execute(
                f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; "
                f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
            )
        cur.execute(SCHEMA_PATH.read_text())
    yield connection
    connection.close()


def _rpc(conn, fn: str, *args):
    placeholders = ", ".join(["%s"] * len(args))
    with conn.cursor() as cur:
        cur.execute(f"SELECT {fn}({placeholders})", args)
        return cur.fetchone()[0]


def _wallet(conn, wallet_id: str | None = None, signup_bonus: bool = True) -> str:
    wallet_id = wallet_id or f"parity_{uuid.uuid4().hex[:12]}"
    _rpc(conn, "games_ensure_wallet", wallet_id, signup_bonus, SIGNUP_BONUS)
    return wallet_id


def _balance(conn, wallet_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT balance FROM games_wallets WHERE id = %s", (wallet_id,))
        row = cur.fetchone()
        return row[0] if row else -1


def test_schema_applies_cleanly(conn):
    """The fixture already applied sql/games-schema.sql; assert the core objects exist."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name LIKE 'games_%'"
        )
        assert cur.fetchone()[0] >= 10
        cur.execute(
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='public' AND p.proname LIKE 'games_%'"
        )
        assert cur.fetchone()[0] >= 10


def test_ensure_wallet_signup_bonus_idempotent(conn):
    wallet = _wallet(conn)
    assert _balance(conn, wallet) == SIGNUP_BONUS
    _rpc(conn, "games_ensure_wallet", wallet, True, SIGNUP_BONUS)  # second call: no double bonus
    assert _balance(conn, wallet) == SIGNUP_BONUS


def test_credit_purchase_idempotent_on_reference(conn):
    wallet = _wallet(conn)
    ref = f"iap:test:{uuid.uuid4().hex[:8]}"
    r1 = _rpc(conn, "games_credit_purchase", wallet, 50, ref, "", MAX_BALANCE)
    assert r1.get("credited") in (True, 50) or r1.get("success") in (True, None)
    after_first = _balance(conn, wallet)
    assert after_first == SIGNUP_BONUS + 50
    _rpc(conn, "games_credit_purchase", wallet, 50, ref, "", MAX_BALANCE)  # same reference → no-op
    assert _balance(conn, wallet) == after_first


def test_debit_tokens_success_and_insufficient(conn):
    wallet = _wallet(conn)  # balance 20
    ok = _rpc(conn, "games_debit_tokens", wallet, 10, "room_create", None)
    assert ok["success"] is True and ok["balance"] == SIGNUP_BONUS - 10
    bad = _rpc(conn, "games_debit_tokens", wallet, 999, "room_create", None)
    assert bad["success"] is False
    assert _balance(conn, wallet) == SIGNUP_BONUS - 10  # unchanged on failure


def test_daily_bonus_streak_math_matches_sqlite(conn):
    wallet = _wallet(conn, signup_bonus=False)
    # Day 1: streak=1, reward=STREAK_BASE
    r1 = _rpc(conn, "games_grant_daily_bonus", wallet, "2026-07-08", DAILY_BONUS, MAX_BALANCE)
    assert r1["granted"] is True and r1["streak"] == 1 and r1["reward"] == DAILY_BONUS
    # Same day again: idempotent
    r2 = _rpc(conn, "games_grant_daily_bonus", wallet, "2026-07-08", DAILY_BONUS, MAX_BALANCE)
    assert r2["granted"] is False and r2["streak"] == 1
    # Consecutive day: streak=2, reward=base+step
    r3 = _rpc(conn, "games_grant_daily_bonus", wallet, "2026-07-09", DAILY_BONUS, MAX_BALANCE)
    assert r3["granted"] is True and r3["streak"] == 2 and r3["reward"] == DAILY_BONUS + STREAK_STEP
    # Gap day: streak resets to 1
    r4 = _rpc(conn, "games_grant_daily_bonus", wallet, "2026-07-12", DAILY_BONUS, MAX_BALANCE)
    assert r4["granted"] is True and r4["streak"] == 1 and r4["reward"] == DAILY_BONUS


def test_daily_bonus_reward_caps_at_streak_max(conn):
    wallet = _wallet(conn, signup_bonus=False)
    day = 8
    expected_last = None
    for i in range(7):  # 7 consecutive days; reward should plateau at STREAK_MAX
        r = _rpc(conn, "games_grant_daily_bonus", wallet, f"2026-07-{day + i:02d}", DAILY_BONUS, MAX_BALANCE)
        expected = min(DAILY_BONUS + i * STREAK_STEP, STREAK_MAX)
        assert r["reward"] == expected, f"day {i + 1}: reward {r['reward']} != {expected}"
        expected_last = r
    assert expected_last["streak"] == 7


def test_referral_full_flow_parity(conn):
    referrer = _wallet(conn)
    referee = _wallet(conn)
    code = "PARITY" + uuid.uuid4().hex[:2].upper()
    set_result = _rpc(conn, "games_set_referral_code", referrer, code)
    assert set_result.get("collision") in (False, None)

    reward, per_day, since = 20, 10, 0
    ok = _rpc(conn, "games_redeem_referral", referee, code, reward, MAX_BALANCE, per_day, since)
    assert ok["status"] == "ok" and ok["reward"] == reward
    assert _balance(conn, referee) == SIGNUP_BONUS + reward
    assert _balance(conn, referrer) == SIGNUP_BONUS + reward

    # Second redeem by same referee: already_redeemed, no double credit
    again = _rpc(conn, "games_redeem_referral", referee, code, reward, MAX_BALANCE, per_day, since)
    assert again["status"] == "already_redeemed"
    assert _balance(conn, referee) == SIGNUP_BONUS + reward

    # Self-referral blocked
    self_ref = _rpc(conn, "games_redeem_referral", referrer, code, reward, MAX_BALANCE, per_day, since)
    assert self_ref["status"] == "self_referral"

    # Unknown code
    bogus = _rpc(conn, "games_redeem_referral", _wallet(conn), "NOPE99", reward, MAX_BALANCE, per_day, since)
    assert bogus["status"] == "invalid_code"


def test_referral_daily_cap(conn):
    referrer = _wallet(conn)
    code = "CAP" + uuid.uuid4().hex[:3].upper()
    _rpc(conn, "games_set_referral_code", referrer, code)
    cap = 2
    for _ in range(cap):
        r = _rpc(conn, "games_redeem_referral", _wallet(conn), code, 20, MAX_BALANCE, cap, 0)
        assert r["status"] == "ok"
    over = _rpc(conn, "games_redeem_referral", _wallet(conn), code, 20, MAX_BALANCE, cap, 0)
    assert over["status"] == "cap_reached"


# ---------------------------------------------------------------------------
# Account deletion (SPEC-ACCOUNT-DELETION)
# ---------------------------------------------------------------------------
# These exist because SQLite could not have caught the bug they cover: the ledger
# used to be `REFERENCES games_wallets(id) ON DELETE CASCADE`, so deleting a wallet
# destroyed the user's whole purchase history on Postgres while SQLite (no FK)
# retained it. Every SQLite test asserted retention — i.e. the suite certified the
# opposite of production behaviour.

def _user(conn, user_id: str | None = None) -> str:
    """Create a users row + the wallet keyed on that same id (wallet id == user id)."""
    user_id = user_id or f"parity_user_{uuid.uuid4().hex[:12]}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO games_users (id, provider, provider_subject_id, email, created_at) "
            "VALUES (%s, 'google', %s, %s, 0)",
            (user_id, f"sub-{user_id}", f"{user_id}@example.com"),
        )
    _wallet(conn, user_id, signup_bonus=True)
    return user_id


def test_ledger_has_no_cascade_from_wallets(conn):
    """The regression guard: no FK from token_transactions -> wallets."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'games_token_transactions'::regclass AND contype = 'f'"
        )
        assert cur.fetchall() == [], (
            "token_transactions must not FK-cascade from wallets — deleting an account "
            "would destroy the retained purchase ledger (SPEC-ACCOUNT-DELETION §3)"
        )


def test_delete_account_removes_pii_wallet_and_content(conn):
    user_id = _user(conn)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO games_generated_content (id, wallet_id, content_type, title, payload, created_at) "
            "VALUES (%s, %s, 'quiz', 'T', '{}'::jsonb, 0)",
            (str(uuid.uuid4()), user_id),
        )

    assert _rpc(conn, "games_delete_account", user_id)["deleted"] is True

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM games_users WHERE id = %s", (user_id,))
        assert cur.fetchone() is None, "PII must be gone"
        cur.execute("SELECT 1 FROM games_wallets WHERE id = %s", (user_id,))
        assert cur.fetchone() is None
        cur.execute("SELECT 1 FROM games_generated_content WHERE wallet_id = %s", (user_id,))
        assert cur.fetchone() is None


def test_delete_account_retains_the_ledger(conn):
    """The case the cascade silently broke."""
    user_id = _user(conn)
    _rpc(conn, "games_credit_purchase", user_id, 200, f"iap:TEST:{uuid.uuid4()}", "", MAX_BALANCE)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM games_token_transactions WHERE wallet_id = %s", (user_id,))
        before = cur.fetchone()[0]
    assert before > 0

    _rpc(conn, "games_delete_account", user_id)

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM games_token_transactions WHERE wallet_id = %s", (user_id,))
        assert cur.fetchone()[0] == before, (
            "the purchase ledger must survive account deletion — financial record + "
            "credit_purchase idempotency guard"
        )


def test_delete_account_is_idempotent(conn):
    user_id = _user(conn)
    assert _rpc(conn, "games_delete_account", user_id)["deleted"] is True
    second = _rpc(conn, "games_delete_account", user_id)
    assert second["deleted"] is False
    assert second["reason"] == "already_deleted"


def test_denylist_records_the_deletion(conn):
    user_id = _user(conn)
    _rpc(conn, "games_delete_account", user_id)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM games_deleted_accounts WHERE user_id = %s", (user_id,))
        assert cur.fetchone() is not None
