"""Gifting, referrals, achievements, ad-reward, restore and account lifecycle — on real PostgREST.

The second half of the priority list from ANALYSIS-2026-08-09-coverage.md, in Codex's order: after
the core money rails come the features that MOVE sparks between wallets (gifting, referrals) and the
ones that grant them (achievements, ad reward, daily), plus the purchase-restore and account
lifecycle paths that touch entitlements.

Each of these has a working SQLite implementation and tests to match; none of them had ever been
executed against Postgres from the Python layer. Replay/duplicate behaviour is asserted everywhere
it exists, because that is what protects the economy from retries.
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


def _funded(sdb, amount: int) -> str:
    wallet = _wallet()
    sdb.get_or_create_wallet(wallet, signup_bonus=False)
    if amount:
        sdb.credit_tokens(wallet, amount, "test_fund")
    return wallet


# --- referrals ---------------------------------------------------------------

def test_referral_code_is_stable_per_wallet(sdb):
    wallet = _funded(sdb, 0)
    first = sdb.get_or_create_referral_code(wallet)
    assert first, "a wallet must get a referral code"
    assert sdb.get_or_create_referral_code(wallet) == first, "the code must not churn per call"


def test_referral_redeem_pays_both_sides_once(sdb):
    referrer = _funded(sdb, 0)
    referee = _funded(sdb, 0)
    code = sdb.get_or_create_referral_code(referrer)

    result = sdb.redeem_referral(referee, code)
    assert result.get("status") == "ok", result
    assert sdb.get_wallet_balance(referee) == config.REFERRAL_REWARD
    assert sdb.get_wallet_balance(referrer) == config.REFERRAL_REWARD

    # A second attempt must not pay again.
    again = sdb.redeem_referral(referee, code)
    assert again.get("status") != "ok", again
    assert sdb.get_wallet_balance(referee) == config.REFERRAL_REWARD
    assert sdb.get_wallet_balance(referrer) == config.REFERRAL_REWARD


def test_referral_rejects_self_and_unknown_codes(sdb):
    wallet = _funded(sdb, 0)
    own_code = sdb.get_or_create_referral_code(wallet)
    assert sdb.redeem_referral(wallet, own_code).get("status") != "ok", "self-referral must fail"
    assert sdb.redeem_referral(wallet, "NOSUCHCODE").get("status") != "ok"
    assert sdb.get_wallet_balance(wallet) == 0, "no failed path may pay out"


# --- gifting -----------------------------------------------------------------

def test_gift_moves_sparks_between_wallets(sdb):
    sender = _funded(sdb, 50)
    recipient = _funded(sdb, 0)
    code = sdb.get_or_create_referral_code(recipient)

    result = sdb.gift_sparks(sender, code, 10, idempotency_key=f"gift_{uuid.uuid4().hex[:8]}")
    assert result.get("status") == "ok", result
    assert sdb.get_wallet_balance(sender) == 40
    assert sdb.get_wallet_balance(recipient) == 10, "sparks must be conserved, not created"


def test_gift_replay_with_same_key_moves_nothing(sdb):
    sender = _funded(sdb, 50)
    recipient = _funded(sdb, 0)
    code = sdb.get_or_create_referral_code(recipient)
    key = f"gift_{uuid.uuid4().hex[:8]}"

    sdb.gift_sparks(sender, code, 10, idempotency_key=key)
    replay = sdb.gift_sparks(sender, code, 10, idempotency_key=key)
    assert replay.get("duplicate") is True or replay.get("status") != "ok", replay
    assert sdb.get_wallet_balance(sender) == 40, "a replayed gift must move nothing"
    assert sdb.get_wallet_balance(recipient) == 10


def test_gift_refused_when_sender_cannot_afford_it(sdb):
    sender = _funded(sdb, 5)
    recipient = _funded(sdb, 0)
    code = sdb.get_or_create_referral_code(recipient)
    result = sdb.gift_sparks(sender, code, 50, idempotency_key=f"gift_{uuid.uuid4().hex[:8]}")
    assert result.get("status") != "ok", result
    assert sdb.get_wallet_balance(sender) == 5
    assert sdb.get_wallet_balance(recipient) == 0


def test_gift_to_self_refused(sdb):
    wallet = _funded(sdb, 50)
    code = sdb.get_or_create_referral_code(wallet)
    result = sdb.gift_sparks(wallet, code, 10, idempotency_key=f"gift_{uuid.uuid4().hex[:8]}")
    assert result.get("status") != "ok", "self-gifting is a no-op laundering path"
    assert sdb.get_wallet_balance(wallet) == 50


# --- achievements ------------------------------------------------------------

def test_award_achievement_is_idempotent(sdb):
    wallet = _funded(sdb, 0)
    assert sdb.award_achievement(wallet, "welcome") is True
    assert sdb.award_achievement(wallet, "welcome") is False, "re-awarding must be a no-op"
    earned = sdb.list_achievements(wallet)
    assert "welcome" in (earned if isinstance(earned, (list, set, dict)) else [])


# --- ad reward (locked in prod, but the DB path still has to be right) -------

def test_ad_reward_respects_the_daily_cap(sdb):
    wallet = _funded(sdb, 0)
    granted_count = 0
    for _ in range(config.MAX_ADS_PER_DAY + 3):
        granted, _balance, _remaining = sdb.check_and_grant_ad_reward(wallet)
        if granted:
            granted_count += 1
    assert granted_count == config.MAX_ADS_PER_DAY, (
        f"{granted_count} ad rewards granted against a cap of {config.MAX_ADS_PER_DAY}"
    )


# --- webhook bookkeeping -----------------------------------------------------

def test_webhook_event_processed_marker_roundtrip(sdb):
    event_id = f"evt_{uuid.uuid4().hex[:12]}"
    assert sdb.is_webhook_event_processed(event_id) is False
    sdb.mark_webhook_event_processed(event_id)
    assert sdb.is_webhook_event_processed(event_id) is True, (
        "the replay guard the Stripe webhook depends on"
    )


def test_credit_total_for_reference_sums_only_that_reference(sdb):
    wallet = _funded(sdb, 0)
    reference = f"cs_{uuid.uuid4().hex[:10]}"
    sdb.credit_purchase(wallet, 100, reference)
    sdb.credit_purchase(wallet, 50, f"cs_other_{uuid.uuid4().hex[:8]}")
    assert sdb.get_credit_total_for_reference(reference, "purchase") == 100, (
        "refund math reads this; over-counting would over-debit a refunded customer"
    )


# --- entitlements + restore --------------------------------------------------

def test_restorable_entitlement_found_for_device(sdb):
    device = _wallet()
    sdb.get_or_create_wallet(device, signup_bonus=False)
    sdb.create_entitlement(
        uuid.uuid4().hex, device_id=device, apple_transaction_id=f"txn_{uuid.uuid4().hex[:10]}",
        games=5, status="active",
    )
    found = sdb.find_restorable_entitlement(device)
    assert found is not None, "/purchases/restore depends on this lookup"
    assert found.get("status") == "active"


def test_iap_audit_marker_is_not_restorable(sdb):
    """games=0 + a neutral status must stay OUT of the restore path, or an audit row would be
    converted into free sparks (the shape of the bug fixed in /purchases/restore)."""
    device = _wallet()
    sdb.get_or_create_wallet(device, signup_bonus=False)
    sdb.create_entitlement(
        uuid.uuid4().hex, device_id=device, apple_transaction_id=f"txn_{uuid.uuid4().hex[:10]}",
        games=0, status="iap_consumed",
    )
    assert sdb.find_restorable_entitlement(device) is None


# --- account lifecycle -------------------------------------------------------

def test_merge_wallet_moves_the_balance_once(sdb):
    device = _funded(sdb, 40)
    user = _wallet()
    sdb.get_or_create_wallet(user, signup_bonus=False)

    sdb.merge_wallet(device, user)
    assert sdb.get_wallet_balance(user) == 40
    assert sdb.get_wallet_balance(device) == 0

    # A second merge must not duplicate sparks (max one merge per target).
    other = _funded(sdb, 25)
    sdb.merge_wallet(other, user)
    assert sdb.get_wallet_balance(user) == 40, "a second merge into one user wallet must be refused"


def test_account_deletion_denylists_and_retains_the_ledger(sdb, postgrest_stack):
    """SPEC-ACCOUNT-DELETION: the wallet goes, the financial ledger STAYS (it is also the
    idempotency guard for credit_purchase)."""
    user = _wallet()
    sdb.get_or_create_wallet(user, signup_bonus=False)
    sdb.credit_purchase(user, 100, f"cs_{uuid.uuid4().hex[:10]}")

    assert sdb.is_account_deleted(user) is False
    assert sdb.delete_account(user) is True
    assert sdb.is_account_deleted(user) is True, "the denylist stops resurrection"
    assert sdb.delete_account(user) is False, "deleting twice must report already-deleted"

    from postgrest_harness import DSN
    with postgrest_stack.connect(DSN, autocommit=True) as conn:
        rows = conn.execute(
            "SELECT count(*) FROM games_token_transactions WHERE wallet_id = %s", (user,),
        ).fetchone()
    assert rows[0] > 0, "the purchase ledger must survive account deletion"


# --- stats -------------------------------------------------------------------

def test_game_result_feeds_wallet_stats(sdb):
    wallet = _funded(sdb, 0)
    room = "ABC123"
    recorded = sdb.record_game_result(
        room_code=room, wallet_id=wallet, game_type="quiz", game_title="Test Quiz",
        player_count=4, winner_nickname="Ada", top_score=30, completed_at=1_700_000_000,
    )
    assert recorded is True
    # Same room twice must not double-count (the badge trigger reads this).
    assert sdb.record_game_result(
        room_code=room, wallet_id=wallet, game_type="quiz", game_title="Test Quiz",
        player_count=4, winner_nickname="Ada", top_score=30, completed_at=1_700_000_000,
    ) is False

    stats = sdb.get_wallet_stats(wallet)
    assert stats.get("games_hosted") == 1, stats
    assert sdb.get_recent_games(wallet, limit=5), "recent games must list the result"
