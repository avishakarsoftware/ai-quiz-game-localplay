"""Tests for the login-streak daily bonus (SPEC-STREAK-BONUS)."""
import db
import config

TODAY = "2026-07-07"
YESTERDAY = "2026-07-06"


def _patch_dates(monkeypatch):
    monkeypatch.setattr(db, "_utc_date_str", lambda: TODAY)
    monkeypatch.setattr(db, "_utc_yesterday_str", lambda: YESTERDAY)


def _fresh(wallet_id, *, balance=0, last_date="", streak=0):
    """Create/reset a wallet in a known state (no signup bonus)."""
    conn = db._get_conn()
    conn.execute("DELETE FROM token_transactions WHERE wallet_id = ?", (wallet_id,))
    conn.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
    conn.commit()
    db.get_or_create_wallet(wallet_id, signup_bonus=False)
    conn.execute(
        "UPDATE wallets SET balance = ?, last_daily_bonus_date = ?, bonus_streak = ? WHERE id = ?",
        (balance, last_date, streak, wallet_id),
    )
    conn.commit()


def test_day1_grants_base(monkeypatch):
    _patch_dates(monkeypatch)
    _fresh("streak-day1")
    granted, bal, streak, reward = db.check_and_grant_daily_bonus("streak-day1")
    assert granted is True
    assert streak == 1
    assert reward == config.STREAK_BASE
    assert bal == config.STREAK_BASE


def test_consecutive_day_increments_and_scales(monkeypatch):
    _patch_dates(monkeypatch)
    # Claimed yesterday at streak 2 → today should be streak 3.
    _fresh("streak-consec", balance=100, last_date=YESTERDAY, streak=2)
    granted, bal, streak, reward = db.check_and_grant_daily_bonus("streak-consec")
    assert granted is True
    assert streak == 3
    assert reward == min(config.STREAK_BASE + 2 * config.STREAK_STEP, config.STREAK_MAX)
    assert bal == 100 + reward


def test_gap_resets_streak(monkeypatch):
    _patch_dates(monkeypatch)
    # Last claim was several days ago (not yesterday) → streak resets to 1.
    _fresh("streak-gap", balance=100, last_date="2026-07-01", streak=5)
    granted, bal, streak, reward = db.check_and_grant_daily_bonus("streak-gap")
    assert granted is True
    assert streak == 1
    assert reward == config.STREAK_BASE


def test_same_day_is_idempotent(monkeypatch):
    _patch_dates(monkeypatch)
    _fresh("streak-same", balance=50, last_date=TODAY, streak=4)
    granted, bal, streak, reward = db.check_and_grant_daily_bonus("streak-same")
    assert granted is False
    assert bal == 50               # no credit
    assert streak == 4             # reports stored streak unchanged


def test_reward_clamps_at_streak_max(monkeypatch):
    _patch_dates(monkeypatch)
    # Big prior streak → today's reward should hit the STREAK_MAX ceiling.
    _fresh("streak-clamp", balance=0, last_date=YESTERDAY, streak=50)
    granted, bal, streak, reward = db.check_and_grant_daily_bonus("streak-clamp")
    assert granted is True
    assert streak == 51
    assert reward == config.STREAK_MAX


def test_balance_cap_does_not_block_streak(monkeypatch):
    _patch_dates(monkeypatch)
    # Wallet already at cap: no tokens added, but the streak still advances and it counts as granted.
    _fresh("streak-cap", balance=config.MAX_TOKEN_BALANCE, last_date=YESTERDAY, streak=2)
    granted, bal, streak, reward = db.check_and_grant_daily_bonus("streak-cap")
    assert granted is True
    assert bal == config.MAX_TOKEN_BALANCE
    assert streak == 3
    wallet = db.get_or_create_wallet("streak-cap")
    assert wallet["bonus_streak"] == 3
