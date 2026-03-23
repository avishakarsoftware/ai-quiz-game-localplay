"""Tests for the token-based economy system: wallets, spending, daily bonus, ads, migration."""
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import db
import config
import tokens as tokens_mod


# --- Override conftest's auto-monkeypatch: we test real token functions here ---

@pytest.fixture(autouse=True)
def real_token_functions(fund_test_wallet, monkeypatch):
    """Undo conftest's monkeypatching and clean wallet state for each test."""
    import importlib
    importlib.reload(tokens_mod)
    monkeypatch.setattr(tokens_mod, "spend_generate", tokens_mod.spend_generate)
    monkeypatch.setattr(tokens_mod, "spend_room", tokens_mod.spend_room)
    monkeypatch.setattr(tokens_mod, "can_generate", tokens_mod.can_generate)
    monkeypatch.setattr(tokens_mod, "can_create_room", tokens_mod.can_create_room)
    monkeypatch.setattr(tokens_mod, "ensure_wallet", tokens_mod.ensure_wallet)
    monkeypatch.setattr(tokens_mod, "use_premium_model", tokens_mod.use_premium_model)
    # Clean wallet and entitlement tables so each test starts fresh
    conn = db._get_conn()
    conn.execute("DELETE FROM wallets")
    conn.execute("DELETE FROM token_transactions")
    conn.execute("DELETE FROM entitlements")
    conn.commit()
    yield


TEST_DEVICE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_DEVICE_2 = "11111111-2222-3333-4444-555555555555"
TEST_USER = "user-uuid-1234"


class TestWalletCreation:
    def test_new_wallet_gets_signup_bonus(self):
        wallet = db.get_or_create_wallet(TEST_DEVICE, signup_bonus=True)
        assert wallet["balance"] == config.SIGNUP_BONUS_TOKENS
        assert wallet["lifetime_purchased"] == 0

    def test_get_existing_wallet_no_double_bonus(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=True)
        wallet = db.get_or_create_wallet(TEST_DEVICE, signup_bonus=True)
        assert wallet["balance"] == config.SIGNUP_BONUS_TOKENS  # Not doubled

    def test_wallet_without_signup_bonus(self):
        wallet = db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        assert wallet["balance"] == 0

    def test_get_wallet_balance(self):
        db.get_or_create_wallet(TEST_DEVICE)
        assert db.get_wallet_balance(TEST_DEVICE) == config.SIGNUP_BONUS_TOKENS

    def test_nonexistent_wallet_balance_is_zero(self):
        assert db.get_wallet_balance("nonexistent-wallet") == 0


class TestDebitTokens:
    def test_debit_success(self):
        db.get_or_create_wallet(TEST_DEVICE)
        ok, new_bal = db.debit_tokens(TEST_DEVICE, 5, "test_debit")
        assert ok is True
        assert new_bal == config.SIGNUP_BONUS_TOKENS - 5

    def test_debit_insufficient_balance(self):
        db.get_or_create_wallet(TEST_DEVICE)
        ok, bal = db.debit_tokens(TEST_DEVICE, config.SIGNUP_BONUS_TOKENS + 1, "test_debit")
        assert ok is False
        assert bal == config.SIGNUP_BONUS_TOKENS

    def test_debit_nonexistent_wallet(self):
        ok, bal = db.debit_tokens("no-wallet", 1, "test_debit")
        assert ok is False
        assert bal == 0

    def test_debit_creates_transaction(self):
        db.get_or_create_wallet(TEST_DEVICE)
        db.debit_tokens(TEST_DEVICE, 3, "spend_generate")
        conn = db._get_conn()
        txns = conn.execute(
            "SELECT * FROM token_transactions WHERE wallet_id = ? AND reason = 'spend_generate'",
            (TEST_DEVICE,),
        ).fetchall()
        assert len(txns) == 1
        assert txns[0]["amount"] == -3


class TestCreditTokens:
    def test_credit_success(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        ok, new_bal = db.credit_tokens(TEST_DEVICE, 50, "test_credit")
        assert ok is True
        assert new_bal == 50

    def test_credit_capped_at_max(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        ok, new_bal = db.credit_tokens(TEST_DEVICE, config.MAX_TOKEN_BALANCE + 100, "test")
        assert ok is True
        assert new_bal == config.MAX_TOKEN_BALANCE

    def test_credit_creates_wallet_if_missing(self):
        ok, new_bal = db.credit_tokens("new-wallet-id", 50, "test")
        assert ok is True
        assert new_bal == 50


class TestCreditPurchase:
    def test_purchase_increments_lifetime(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        db.credit_purchase(TEST_DEVICE, 110, "stripe-session-123")
        wallet = db.get_or_create_wallet(TEST_DEVICE)
        assert wallet["lifetime_purchased"] == 110
        assert wallet["balance"] == 110

    def test_has_ever_purchased(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        assert db.has_ever_purchased(TEST_DEVICE) is False
        db.credit_purchase(TEST_DEVICE, 110, "stripe-session-123")
        assert db.has_ever_purchased(TEST_DEVICE) is True


class TestDailyBonus:
    def test_grants_on_new_day(self):
        db.get_or_create_wallet(TEST_DEVICE)
        granted, new_bal = db.check_and_grant_daily_bonus(TEST_DEVICE)
        assert granted is True
        assert new_bal == config.SIGNUP_BONUS_TOKENS + config.DAILY_BONUS_TOKENS

    def test_no_double_grant_same_day(self):
        db.get_or_create_wallet(TEST_DEVICE)
        db.check_and_grant_daily_bonus(TEST_DEVICE)
        granted, _ = db.check_and_grant_daily_bonus(TEST_DEVICE)
        assert granted is False

    def test_resets_ad_counter(self):
        db.get_or_create_wallet(TEST_DEVICE)
        # Watch some ads first
        conn = db._get_conn()
        today = db._utc_date_str()
        conn.execute(
            "UPDATE wallets SET ads_watched_today = 3, ads_watched_date = ? WHERE id = ?",
            (today, TEST_DEVICE),
        )
        conn.commit()
        # Daily bonus resets ad counter
        db.check_and_grant_daily_bonus(TEST_DEVICE)
        wallet = db.get_or_create_wallet(TEST_DEVICE)
        assert wallet["ads_watched_today"] == 0


class TestAdReward:
    def test_grant_ad_reward(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        granted, new_bal, remaining = db.check_and_grant_ad_reward(TEST_DEVICE)
        assert granted is True
        assert new_bal == config.AD_REWARD_TOKENS
        assert remaining == config.MAX_ADS_PER_DAY - 1

    def test_daily_cap_enforced(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        for _ in range(config.MAX_ADS_PER_DAY):
            db.check_and_grant_ad_reward(TEST_DEVICE)
        granted, _, remaining = db.check_and_grant_ad_reward(TEST_DEVICE)
        assert granted is False
        assert remaining == 0


class TestMergeWallet:
    def test_merge_transfers_balance(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=True)
        db.get_or_create_wallet(TEST_USER, signup_bonus=False)
        db.merge_wallet(TEST_DEVICE, TEST_USER)
        assert db.get_wallet_balance(TEST_DEVICE) == 0
        assert db.get_wallet_balance(TEST_USER) == config.SIGNUP_BONUS_TOKENS

    def test_merge_transfers_lifetime_purchased(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        db.credit_purchase(TEST_DEVICE, 110, "stripe-1")
        db.get_or_create_wallet(TEST_USER, signup_bonus=False)
        db.merge_wallet(TEST_DEVICE, TEST_USER)
        assert db.has_ever_purchased(TEST_USER) is True

    def test_merge_creates_target_if_missing(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=True)
        db.merge_wallet(TEST_DEVICE, TEST_USER)
        assert db.get_wallet_balance(TEST_USER) == config.SIGNUP_BONUS_TOKENS

    def test_merge_zero_balance_is_noop(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        db.merge_wallet(TEST_DEVICE, TEST_USER)
        assert db.get_wallet_balance(TEST_USER) == 0  # No wallet created


class TestTokensModule:
    """Test the tokens.py business logic layer."""

    def test_spend_generate(self):
        db.get_or_create_wallet(TEST_DEVICE)
        ok, new_bal = tokens_mod.spend_generate(TEST_DEVICE)
        assert ok is True
        assert new_bal == config.SIGNUP_BONUS_TOKENS - config.COST_GENERATE

    def test_spend_room(self):
        db.get_or_create_wallet(TEST_DEVICE)
        ok, new_bal = tokens_mod.spend_room(TEST_DEVICE)
        assert ok is True
        assert new_bal == config.SIGNUP_BONUS_TOKENS - config.COST_ROOM

    def test_can_generate_with_tokens(self):
        db.get_or_create_wallet(TEST_DEVICE)
        assert tokens_mod.can_generate(TEST_DEVICE) is True

    def test_cannot_generate_with_zero_balance(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        assert tokens_mod.can_generate(TEST_DEVICE) is False

    def test_can_create_room_with_tokens(self):
        db.get_or_create_wallet(TEST_DEVICE)
        assert tokens_mod.can_create_room(TEST_DEVICE) is True

    def test_cannot_create_room_with_low_balance(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        db.credit_tokens(TEST_DEVICE, config.COST_ROOM - 1, "test")
        assert tokens_mod.can_create_room(TEST_DEVICE) is False

    def test_use_premium_model_after_purchase(self):
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        assert tokens_mod.use_premium_model(TEST_DEVICE) is False
        db.credit_purchase(TEST_DEVICE, 110, "stripe-1")
        assert tokens_mod.use_premium_model(TEST_DEVICE) is True


class TestGetTokenStatus:
    def test_new_wallet_status(self):
        status = tokens_mod.get_token_status(TEST_DEVICE)
        assert status["balance"] >= config.SIGNUP_BONUS_TOKENS  # signup + maybe daily bonus
        assert status["cost_generate"] == config.COST_GENERATE
        assert status["cost_room"] == config.COST_ROOM
        assert status["has_purchased"] is False

    def test_daily_bonus_auto_granted(self):
        db.get_or_create_wallet(TEST_DEVICE)
        status = tokens_mod.get_token_status(TEST_DEVICE)
        # First call on a new wallet should grant daily bonus
        assert status["daily_bonus_granted"] is True
        assert status["bonus_amount"] == config.DAILY_BONUS_TOKENS

    def test_daily_bonus_not_double_granted(self):
        tokens_mod.get_token_status(TEST_DEVICE)  # First call grants it
        status = tokens_mod.get_token_status(TEST_DEVICE)  # Second call
        assert status["daily_bonus_granted"] is False


class TestMigrateEntitlements:
    def test_active_entitlement_migrated(self):
        # Create an old-style active entitlement
        conn = db._get_conn()
        now = int(time.time())
        conn.execute(
            "INSERT INTO entitlements (id, device_id, status, games_remaining, expires_at, created_at) "
            "VALUES ('ent-1', ?, 'active', 7, ?, ?)",
            (TEST_DEVICE, now + 86400, now),
        )
        conn.commit()

        db.migrate_entitlements_to_wallets()

        # Check wallet was created with correct tokens
        balance = db.get_wallet_balance(TEST_DEVICE)
        assert balance == 7 * config.COST_ROOM  # 70 tokens

        # Check entitlement was marked as migrated
        row = conn.execute("SELECT status FROM entitlements WHERE id = 'ent-1'").fetchone()
        assert row["status"] == "migrated_to_tokens"

    def test_migration_is_idempotent(self):
        conn = db._get_conn()
        now = int(time.time())
        conn.execute(
            "INSERT INTO entitlements (id, device_id, status, games_remaining, expires_at, created_at) "
            "VALUES ('ent-2', ?, 'active', 5, ?, ?)",
            (TEST_DEVICE_2, now + 86400, now),
        )
        conn.commit()

        db.migrate_entitlements_to_wallets()
        balance_after_first = db.get_wallet_balance(TEST_DEVICE_2)
        db.migrate_entitlements_to_wallets()  # Second run
        balance_after_second = db.get_wallet_balance(TEST_DEVICE_2)
        assert balance_after_first == balance_after_second


class TestAdRewardEndpoint:
    """Test the /tokens/ad-reward HTTP endpoint."""

    def test_ad_reward_success(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        # Create wallet for the device
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        res = client.post("/tokens/ad-reward", headers={"X-Device-Id": TEST_DEVICE})
        assert res.status_code == 200
        data = res.json()
        assert data["granted"] is True
        assert data["tokens_added"] == config.AD_REWARD_TOKENS
        assert data["new_balance"] == config.AD_REWARD_TOKENS
        assert data["ads_remaining_today"] == config.MAX_ADS_PER_DAY - 1

    def test_ad_reward_daily_cap(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        db.get_or_create_wallet(TEST_DEVICE, signup_bonus=False)
        # Watch MAX_ADS_PER_DAY ads
        for _ in range(config.MAX_ADS_PER_DAY):
            res = client.post("/tokens/ad-reward", headers={"X-Device-Id": TEST_DEVICE})
            assert res.status_code == 200
        # Next one should be rejected
        res = client.post("/tokens/ad-reward", headers={"X-Device-Id": TEST_DEVICE})
        assert res.status_code == 429

    def test_ad_reward_no_device_id(self):
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        res = client.post("/tokens/ad-reward")
        assert res.status_code == 400


class TestAdminTokenFunctions:
    def test_admin_grant_tokens(self):
        new_bal = db.admin_grant_tokens(TEST_DEVICE, 50)
        assert new_bal == 50

    def test_admin_lookup_wallet(self):
        db.get_or_create_wallet(TEST_DEVICE)
        db.debit_tokens(TEST_DEVICE, 1, "test")
        result = db.admin_lookup_wallet(TEST_DEVICE)
        assert result is not None
        assert result["wallet"]["balance"] == config.SIGNUP_BONUS_TOKENS - 1
        assert len(result["transactions"]) >= 1
