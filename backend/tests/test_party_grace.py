"""First-party grace (REVIEW-2026-08 P1): a new host's first evening of rooms is free.

Before this, the economy paywalled a brand-new host at ~game 2 (20-spark grant, 10/room) —
mid-party, friends watching, the worst possible moment to ask for money. The grace window
anchors on the wallet's FIRST room and makes rooms free for PARTY_GRACE_HOURS, so the ask
arrives after a great first party.

State lives in the ledger as zero-amount 'grace_room' rows — no schema change; the window is
derived from the oldest marker. conftest pins PARTY_GRACE_HOURS=0 for the rest of the suite,
so these tests re-enable it explicitly.
"""
import time
import uuid

import pytest

import config
import db
import tokens

# conftest's fund_test_wallet replaces spend_room with a lambda; capture the real one at
# import time (same pattern as test_abuse_guards).
_REAL_SPEND_ROOM = tokens.spend_room


@pytest.fixture(autouse=True)
def grace_enabled(monkeypatch):
    monkeypatch.setattr(config, "PARTY_GRACE_HOURS", 6)
    monkeypatch.setattr(config, "PARTY_GRACE_MAX_ROOMS", 4)
    monkeypatch.setattr(tokens, "spend_room", _REAL_SPEND_ROOM)
    yield


def _host(balance: int = 20, signup_bonus: bool = True) -> str:
    wallet_id = str(uuid.uuid4())
    db.get_or_create_wallet(wallet_id, signup_bonus=signup_bonus)
    current_balance = db.get_wallet_balance(wallet_id)
    if balance > current_balance:
        db.credit_tokens(wallet_id, balance - current_balance, "test_fund")
    elif balance < current_balance:
        db.debit_tokens(wallet_id, current_balance - balance, "test_drain")
    return wallet_id


def test_first_evening_of_rooms_is_free():
    host = _host(20)
    # Way past the old paywall point: 4 rooms would have cost 40 sparks against a 20 balance.
    for n in range(4):
        ok, balance = tokens.spend_room(host)
        assert ok, f"room {n + 1} should be free inside the grace window"
        assert balance == 20, "grace rooms must not touch the balance"
    # ledger carries the audit trail
    anchor, rooms = db.party_grace_state(host)
    assert rooms == 4 and anchor > 0


def test_after_the_window_rooms_cost_sparks_again(monkeypatch):
    host = _host(20)
    ok, _ = tokens.spend_room(host)          # opens the window
    assert ok

    # jump past the window
    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + config.PARTY_GRACE_HOURS * 3600 + 60)
    ok, balance = tokens.spend_room(host)
    assert ok
    assert balance == 20 - config.COST_ROOM, "post-window rooms must debit normally"


def test_room_cap_inside_the_window():
    host = _host(100)
    for _ in range(config.PARTY_GRACE_MAX_ROOMS):
        assert tokens.spend_room(host)[0]
    ok, balance = tokens.spend_room(host)    # cap reached -> paid room
    assert ok
    assert balance == 100 - config.COST_ROOM


def test_broke_host_past_cap_hits_the_paywall():
    host = _host(0)
    for _ in range(config.PARTY_GRACE_MAX_ROOMS):
        assert tokens.spend_room(host)[0]
    ok, _ = tokens.spend_room(host)
    assert not ok, "outside grace with 0 sparks the normal paywall applies"


def test_veteran_payers_are_not_granted_a_surprise_free_evening():
    """Grace is a FIRST-party experience. A wallet that has ever paid for a room predates the
    feature (or already had its first party) and keeps paying."""
    host = _host(50)
    db.debit_tokens(host, config.COST_ROOM, "spend_room")   # historical paid room
    ok, balance = tokens.spend_room(host)
    assert ok
    assert balance == 50 - 2 * config.COST_ROOM  # historical debit + this normal debit, no grace
    assert db.party_grace_state(host) == (0, 0)


def test_grantless_wallets_are_not_granted_free_rooms():
    """Wallets created after the per-IP signup allowance is exhausted can still play, but they
    cannot be minted into free first-party hosts."""
    host = _host(0, signup_bonus=False)
    assert tokens.party_grace_status(host)["state"] == "ineligible"
    ok, _ = tokens.spend_room(host)
    assert not ok
    assert db.party_grace_state(host) == (0, 0)


def test_disabled_flag_restores_old_behavior(monkeypatch):
    monkeypatch.setattr(config, "PARTY_GRACE_HOURS", 0)
    host = _host(20)
    ok, balance = tokens.spend_room(host)
    assert ok and balance == 10


class TestGraceStatus:
    def test_lifecycle(self, monkeypatch):
        host = _host(20)
        assert tokens.party_grace_status(host)["state"] == "available"

        tokens.spend_room(host)
        status = tokens.party_grace_status(host)
        assert status["state"] == "active"
        assert status["rooms_used"] == 1
        assert status["until"] > time.time()

        real_time = time.time
        monkeypatch.setattr(time, "time", lambda: real_time() + config.PARTY_GRACE_HOURS * 3600 + 60)
        assert tokens.party_grace_status(host)["state"] == "expired"

    def test_status_never_consumes(self):
        host = _host(20)
        for _ in range(5):
            tokens.party_grace_status(host)
        assert db.party_grace_state(host) == (0, 0)
        assert tokens.party_grace_status(host)["state"] == "available"

    def test_veteran_is_ineligible(self):
        host = _host(50)
        db.debit_tokens(host, config.COST_ROOM, "spend_room")
        assert tokens.party_grace_status(host)["state"] == "ineligible"


class TestGraceSurvivesSignIn:
    """merge_wallet moves balance only, so before migrate_grace_proofs the sign-in flow
    stranded every grace proof on the device wallet: a brand-new host who signed in BEFORE
    hosting (the flow the app itself encourages) read as ineligible and silently lost their
    free first party — while a veteran's history vanished, handing them a fresh free evening."""

    def test_new_host_keeps_eligibility_after_sign_in(self):
        device = _host(20)                       # signup bonus on the device wallet
        user = f"user-{uuid.uuid4()}"
        db.merge_wallet(device, user)
        db.migrate_grace_proofs(device, user)
        assert tokens.party_grace_status(user)["state"] == "available", (
            "signing in before the first game must not cost a new host their free party"
        )

    def test_open_window_carries_over_without_resetting(self):
        device = _host(20)
        tokens.spend_room(device)                # opens the window on the device wallet
        tokens.spend_room(device)
        device_anchor, device_rooms = db.party_grace_state(device)

        user = f"user-{uuid.uuid4()}"
        db.merge_wallet(device, user)
        db.migrate_grace_proofs(device, user)
        user_anchor, user_rooms = db.party_grace_state(user)
        assert user_anchor == device_anchor, "the deadline must carry over, not restart"
        assert user_rooms == device_rooms == 2
        assert tokens.party_grace_status(user)["state"] == "active"

    def test_veteran_stays_ineligible_after_sign_in(self):
        device = _host(50)
        db.debit_tokens(device, config.COST_ROOM, "spend_room")   # paid room history
        user = f"user-{uuid.uuid4()}"
        db.merge_wallet(device, user)
        db.migrate_grace_proofs(device, user)
        assert tokens.party_grace_status(user)["state"] == "ineligible", (
            "sign-in must not launder away a veteran's paid history into a fresh free evening"
        )

    def test_proofs_migrate_even_when_merge_wallet_noops_on_zero_balance(self):
        device = _host(0)                        # signup bonus row exists, balance drained to 0
        db.get_or_create_wallet(device, signup_bonus=False)
        user = f"user-{uuid.uuid4()}"
        db.merge_wallet(device, user)            # no-ops: nothing to transfer
        db.migrate_grace_proofs(device, user)    # must still carry the proof
        assert tokens.party_grace_status(user)["state"] == "available"

    def test_migration_is_idempotent(self):
        device = _host(20)
        tokens.spend_room(device)
        user = f"user-{uuid.uuid4()}"
        db.merge_wallet(device, user)
        db.migrate_grace_proofs(device, user)
        first = db.party_grace_state(user)
        db.migrate_grace_proofs(device, user)    # double sign-in / retry
        assert db.party_grace_state(user) == first, "re-running must not duplicate the window"
