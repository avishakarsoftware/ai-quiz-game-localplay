"""Concurrency on the production money rails (real PostgREST + Postgres).

Codex's sharpening of the coverage analysis, and it is the right one: races matter more than line
coverage. Every test here fires N genuinely simultaneous requests at ONE wallet through the real
REST layer and asserts the invariant that money cannot be created or destroyed.

The SQLite path gets its atomicity from `BEGIN IMMEDIATE`. The Supabase path gets it from whatever
the SQL functions in sql/templates/ actually do — which had never been tested under contention from
the Python layer. If any of these fail, the bug is real and reachable in production, because a party
generates exactly this pattern: several people tapping at once.

Threads (not asyncio) because `SupabaseClient` uses a blocking httpx client per call, so threads
produce true overlap. A Barrier makes them start together instead of merely near each other.
"""
import threading
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

WORKERS = 8


def _wallet() -> str:
    return str(uuid.uuid4())


def _race(fn, workers: int = WORKERS):
    """Run `fn(i)` on `workers` threads released simultaneously. Returns (results, errors)."""
    barrier = threading.Barrier(workers)
    results: list = []
    errors: list = []
    lock = threading.Lock()

    def run(index: int) -> None:
        try:
            barrier.wait(timeout=30)
            value = fn(index)
            with lock:
                results.append(value)
        except Exception as exc:  # noqa: BLE001 — collected and asserted on by the caller
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results, errors


# --- the classic double-spend ------------------------------------------------

def test_concurrent_debits_cannot_overspend(sdb):
    """One room's worth of sparks, eight simultaneous attempts to spend it.

    Exactly one may succeed and the balance must land at 0 — never negative. This is the shape of
    a real party: the host double-taps Start, or two devices race.
    """
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    sdb.credit_tokens(wallet, 10, "test_fund")

    results, errors = _race(lambda _i: sdb.debit_tokens(wallet, 10, "spend_room"))
    assert not errors, f"unexpected errors: {errors[:2]}"

    succeeded = [ok for ok, _ in results if ok]
    final = sdb.get_wallet_balance(wallet)
    assert final >= 0, f"BALANCE WENT NEGATIVE ({final}) — sparks were created from nothing"
    assert len(succeeded) == 1, (
        f"{len(succeeded)} of {WORKERS} debits succeeded against a 10-spark balance; "
        f"final balance {final}. Only one may win."
    )
    assert final == 0


def test_concurrent_partial_debits_conserve_the_balance(sdb):
    """40 sparks, eight simultaneous 10-spark debits: exactly four may win and the balance must
    land at 0. Catches a lost-update race that a single-debit test would miss."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    sdb.credit_tokens(wallet, 40, "test_fund")

    results, errors = _race(lambda _i: sdb.debit_tokens(wallet, 10, "spend_room"))
    assert not errors, f"unexpected errors: {errors[:2]}"

    succeeded = sum(1 for ok, _ in results if ok)
    final = sdb.get_wallet_balance(wallet)
    assert final >= 0, f"BALANCE WENT NEGATIVE ({final})"
    assert succeeded == 4, f"{succeeded} debits of 10 succeeded against 40 sparks (final {final})"
    assert final == 0


# --- webhook replay under contention ----------------------------------------

def test_concurrent_same_reference_purchase_credits_exactly_once(sdb):
    """Stripe and RevenueCat both retry. If two deliveries of ONE payment overlap, the wallet must
    be credited once — otherwise a retry storm mints sparks."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    reference = f"cs_race_{uuid.uuid4().hex[:12]}"

    _, errors = _race(lambda _i: sdb.credit_purchase(wallet, 200, reference))
    assert not errors, f"unexpected errors: {errors[:2]}"

    final = sdb.get_wallet_balance(wallet)
    assert final == 200, (
        f"balance {final} after {WORKERS} concurrent deliveries of ONE purchase reference — "
        "expected exactly one credit of 200"
    )


def test_concurrent_distinct_purchases_all_land(sdb):
    """The mirror of the above: genuinely different payments must not be collapsed by the
    idempotency guard."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    refs = [f"cs_multi_{uuid.uuid4().hex[:10]}" for _ in range(WORKERS)]

    _, errors = _race(lambda i: sdb.credit_purchase(wallet, 50, refs[i]))
    assert not errors, f"unexpected errors: {errors[:2]}"
    assert sdb.get_wallet_balance(wallet) == 50 * WORKERS, "distinct references must each credit"


# --- grants that must happen once -------------------------------------------

def test_concurrent_daily_bonus_grants_once(sdb):
    """Several devices/tabs polling /tokens/balance at midnight must not multiply the bonus."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)

    results, errors = _race(lambda _i: sdb.check_and_grant_daily_bonus(wallet))
    assert not errors, f"unexpected errors: {errors[:2]}"

    granted = [r for r in results if r[0]]
    final = sdb.get_wallet_balance(wallet)
    assert len(granted) == 1, f"{len(granted)} concurrent calls each granted a daily bonus (balance {final})"
    assert final == granted[0][3], "balance must equal exactly one reward"


def test_concurrent_wallet_creation_grants_one_signup_bonus(sdb):
    """A cold-start burst (app opens, several requests fire) must not multiply the signup grant."""
    wallet = _wallet()
    _, errors = _race(lambda _i: sdb.get_or_create_wallet(wallet, signup_bonus=True))
    assert not errors, f"unexpected errors: {errors[:2]}"
    final = sdb.get_wallet_balance(wallet)
    assert final == config.SIGNUP_BONUS_TOKENS, (
        f"balance {final} after {WORKERS} concurrent creations — expected exactly one signup grant"
    )


# --- the cap under contention ------------------------------------------------

def test_concurrent_credits_respect_the_cap(sdb):
    """Eight simultaneous credits near the ceiling must not push the balance past MAX_TOKEN_BALANCE."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    sdb.credit_tokens(wallet, config.MAX_TOKEN_BALANCE - 50, "test_fund")

    _, errors = _race(lambda i: sdb.credit_tokens(wallet, 50, f"race_{i}"))
    assert not errors, f"unexpected errors: {errors[:2]}"
    final = sdb.get_wallet_balance(wallet)
    assert final <= config.MAX_TOKEN_BALANCE, (
        f"balance {final} exceeds the cap {config.MAX_TOKEN_BALANCE} under concurrent credits"
    )


# --- grace, under the same pressure -----------------------------------------

def test_concurrent_grace_room_records_do_not_corrupt_the_window(sdb):
    """Grace rooms are ledger markers; concurrent writes must still yield a coherent count and a
    stable anchor, or the free-evening window could silently extend itself."""
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=True)

    _, errors = _race(lambda _i: sdb.record_grace_room(wallet))
    assert not errors, f"unexpected errors: {errors[:2]}"

    anchor, rooms = sdb.party_grace_state(wallet)
    assert rooms == WORKERS, f"expected {WORKERS} grace markers, found {rooms}"
    assert anchor > 0, "the anchor must be the earliest marker, not null"


def test_concurrent_migrate_grace_proofs_is_idempotent(sdb):
    """Two sign-in requests racing must not duplicate the migrated window."""
    device, user = _wallet(), _wallet()
    sdb.get_or_create_wallet(device, signup_bonus=True)
    sdb.get_or_create_wallet(user, signup_bonus=False)
    sdb.record_grace_room(device)

    _, errors = _race(lambda _i: sdb.migrate_grace_proofs(device, user), workers=4)
    assert not errors, f"unexpected errors: {errors[:2]}"

    _, rooms = sdb.party_grace_state(user)
    assert rooms == 1, f"concurrent migration duplicated the grace window ({rooms} markers)"
