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


def _host(balance: int = 20) -> str:
    wallet_id = str(uuid.uuid4())
    db.get_or_create_wallet(wallet_id, signup_bonus=False)
    if balance:
        db.credit_tokens(wallet_id, balance, "test_fund")
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
