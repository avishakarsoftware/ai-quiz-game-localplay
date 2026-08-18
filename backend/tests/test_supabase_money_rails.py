"""The money rails of `supabase_db.py`, exercised against real PostgREST + Postgres.

This is the module PRODUCTION runs, and it was at 30% coverage with 33 functions never executed
(ANALYSIS-2026-08-09-coverage.md §1). `test_postgres_parity.py` covers the SQL functions via
psycopg; nothing covered this Python layer — the PostgREST filter strings, the response reshaping,
the key names. A wrong key here returns plausible-looking data and loses money silently, which has
happened before (the Supabase `new_balance` key).

Every test below drives the real `supabase_db` function over real HTTP. Skips unless
./scripts/parity-stack.sh is up. See tests/postgrest_harness.py for the safety rail — this suite
truncates tables and refuses any non-loopback target.
"""
import uuid

import pytest

import config
from postgrest_harness import (  # noqa: F401
    HARNESS_READY,
    SKIP_REASON,
    _proxy_base_url,
    postgrest_stack,
    sdb,
)

pytestmark = pytest.mark.skipif(not HARNESS_READY, reason=SKIP_REASON)


def _wallet() -> str:
    return str(uuid.uuid4())


# --- wallet creation + the signup grant --------------------------------------

def test_signup_bonus_granted_once(sdb):
    wallet = _wallet()
    first = sdb.get_or_create_wallet(wallet, signup_bonus=True)
    assert first["balance"] == config.SIGNUP_BONUS_TOKENS
    # Second call must not re-grant. This is the single most expensive possible bug in the file.
    again = sdb.get_or_create_wallet(wallet, signup_bonus=True)
    assert again["balance"] == config.SIGNUP_BONUS_TOKENS
    assert sdb.get_wallet_balance(wallet) == config.SIGNUP_BONUS_TOKENS


def test_wallet_without_bonus_starts_empty(sdb):
    wallet = _wallet()
    assert sdb.get_or_create_wallet(wallet, signup_bonus=False)["balance"] == 0
    assert sdb.wallet_exists(wallet) is True
    assert sdb.wallet_exists(_wallet()) is False


# --- debit / credit ----------------------------------------------------------

def test_debit_succeeds_and_reports_new_balance(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=True)
    ok, balance = sdb.debit_tokens(wallet, 10, "room_create")
    assert ok is True
    assert balance == config.SIGNUP_BONUS_TOKENS - 10
    assert sdb.get_wallet_balance(wallet) == balance


def test_debit_refused_when_insufficient_and_balance_untouched(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    sdb.credit_tokens(wallet, 5, "test_fund")
    ok, balance = sdb.debit_tokens(wallet, 10, "room_create")
    assert ok is False
    assert sdb.get_wallet_balance(wallet) == 5, "a refused debit must not move the balance"


def test_credit_clamps_at_the_cap(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    sdb.credit_tokens(wallet, config.MAX_TOKEN_BALANCE, "test_fund")
    _, balance = sdb.credit_tokens(wallet, 500, "test_overflow")
    assert balance == config.MAX_TOKEN_BALANCE, "the cap is the invariant of last resort"


@pytest.mark.parametrize("amount", [0, -5])
def test_non_positive_amounts_rejected(sdb, amount):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=True)
    with pytest.raises(ValueError):
        sdb.debit_tokens(wallet, amount, "room_create")
    with pytest.raises(ValueError):
        sdb.credit_tokens(wallet, amount, "test")


# --- purchases: the idempotency that protects real money --------------------

def test_credit_purchase_is_idempotent_on_reference(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    reference = f"cs_test_{uuid.uuid4().hex[:12]}"

    ok, balance = sdb.credit_purchase(wallet, 200, reference)
    assert ok is True and balance == 200

    # A re-delivered Stripe webhook, or a RevenueCat retry, must credit NOTHING further.
    ok2, balance2 = sdb.credit_purchase(wallet, 200, reference)
    assert balance2 == 200, "replaying a purchase reference must not double-credit"
    assert sdb.get_wallet_balance(wallet) == 200


def test_distinct_references_both_credit(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    sdb.credit_purchase(wallet, 50, f"cs_{uuid.uuid4().hex[:10]}")
    _, balance = sdb.credit_purchase(wallet, 50, f"cs_{uuid.uuid4().hex[:10]}")
    assert balance == 100, "two genuine purchases must both land"


def test_purchase_at_the_cap_does_not_exceed_it(sdb):
    """The M1 finding, on the Postgres path: at the cap a purchase must clamp rather than
    overflow. /checkout/create now refuses beforehand, but this is the backstop."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    sdb.credit_tokens(wallet, config.MAX_TOKEN_BALANCE - 10, "test_fund")
    _, balance = sdb.credit_purchase(wallet, 500, f"cs_{uuid.uuid4().hex[:10]}")
    assert balance == config.MAX_TOKEN_BALANCE


# --- daily bonus + streak ----------------------------------------------------

def test_daily_bonus_grants_once_per_day(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    granted, balance, streak, reward = sdb.check_and_grant_daily_bonus(wallet)
    assert granted is True
    assert streak == 1
    assert balance == reward > 0

    granted2, balance2, streak2, _ = sdb.check_and_grant_daily_bonus(wallet)
    assert granted2 is False, "a second call the same UTC day must not grant again"
    assert balance2 == balance
    assert streak2 == streak


# --- admin grant: the support remediation path ------------------------------

def test_admin_grant_credits_and_records_the_audit_note(sdb, postgrest_stack):
    """The M2 runbook depends on `note` reaching the ledger — without it a remediation grant
    cannot be tied back to the payment it fixes."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    balance = sdb.admin_grant_tokens(wallet, 55, note="support:cs_test_999")
    assert balance == 55

    with postgrest_stack.connect(
        __import__("postgrest_harness").DSN, autocommit=True
    ) as conn:
        row = conn.execute(
            "SELECT reference_id FROM games_token_transactions "
            "WHERE wallet_id = %s AND reason = 'admin_grant' ORDER BY created_at DESC LIMIT 1",
            (wallet,),
        ).fetchone()
    assert row is not None and row[0] == "support:cs_test_999"


# --- idempotency keys --------------------------------------------------------

def test_idempotency_key_roundtrip(sdb):
    key = f"idem_{uuid.uuid4().hex[:10]}"
    device = _wallet()
    assert sdb.check_idempotency(key, device) is None
    sdb.record_idempotency(key, device, "result-123")
    assert sdb.check_idempotency(key, device) == "result-123"


# --- users -------------------------------------------------------------------

def test_find_or_create_user_is_stable_for_the_same_subject(sdb):
    subject = f"sub_{uuid.uuid4().hex[:12]}"
    first = sdb.find_or_create_user("google", subject, "person@example.com")
    again = sdb.find_or_create_user("google", subject, "person@example.com")
    assert first["id"] == again["id"], "the same provider subject must map to one user"


# --- grace proofs across the sign-in merge ----------------------------------

def test_migrate_grace_proofs_carries_identity(sdb):
    """Written 2026-08-09 and, until this test, 15 of its 16 lines had never executed on the
    Postgres path — every 'verified' run that day exercised SQLite."""
    device, user = _wallet(), _wallet()
    sdb.get_or_create_wallet(device, signup_bonus=True)
    sdb.get_or_create_wallet(user, signup_bonus=False)

    assert sdb.has_signup_bonus(device) is True
    assert sdb.has_signup_bonus(user) is False

    sdb.migrate_grace_proofs(device, user)
    assert sdb.has_signup_bonus(user) is True, (
        "without the migrated proof, signing in before the first game silently costs a new host "
        "their free party"
    )


def test_migrate_grace_proofs_is_idempotent(sdb):
    device, user = _wallet(), _wallet()
    sdb.get_or_create_wallet(device, signup_bonus=True)
    sdb.get_or_create_wallet(user, signup_bonus=False)
    sdb.migrate_grace_proofs(device, user)
    first = sdb.party_grace_state(user)
    sdb.migrate_grace_proofs(device, user)
    assert sdb.party_grace_state(user) == first, "a repeated sign-in must not duplicate the window"


def test_grace_window_state_reads_from_the_ledger(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=True)
    assert sdb.party_grace_state(wallet) == (0, 0)
    sdb.record_grace_room(wallet)
    sdb.record_grace_room(wallet)
    anchor, rooms = sdb.party_grace_state(wallet)
    assert rooms == 2 and anchor > 0, "the window anchors on the FIRST free room"


def test_veteran_room_spend_is_visible(sdb):
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=True)
    assert sdb.has_room_spend(wallet) is False
    sdb.debit_tokens(wallet, 10, "spend_room")
    assert sdb.has_room_spend(wallet) is True, (
        "grace eligibility depends on this: if it misreads, a veteran gets a fresh free evening"
    )


# --- cross-backend contract parity ------------------------------------------

def test_replay_contract_matches_sqlite(sdb):
    """Both backends must answer a replayed purchase identically.

    Measured 2026-08-09: SQLite and Supabase both return (True, balance) on a sequential replay —
    `success` means "this payment is credited", not "I credited it just now". The concurrent-loser
    path added the same day had to be aligned to this after initially returning False, which would
    have made a caller checking `if not ok` raise a false alarm on a fulfilled payment.
    """
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    reference = f"cs_contract_{uuid.uuid4().hex[:10]}"
    first = sdb.credit_purchase(wallet, 100, reference)
    replay = sdb.credit_purchase(wallet, 100, reference)
    assert first == (True, 100)
    assert replay == (True, 100), (
        "a replay must report the payment as credited with the unchanged balance — the same tuple "
        "db.py (SQLite) returns"
    )
