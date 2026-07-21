"""Tests for referral rewards (SPEC-REFERRAL)."""
import db
import config


def _fresh(wallet_id):
    conn = db._get_conn()
    conn.execute("DELETE FROM token_transactions WHERE wallet_id = ?", (wallet_id,))
    conn.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
    conn.commit()
    db.get_or_create_wallet(wallet_id, signup_bonus=False)


def test_code_is_stable_and_formatted():
    _fresh("ref-A")
    code1 = db.get_or_create_referral_code("ref-A")
    code2 = db.get_or_create_referral_code("ref-A")
    assert code1 == code2                     # stable
    assert len(code1) == 6
    assert all(c in db._REFERRAL_ALPHABET for c in code1)
    # no ambiguous characters
    assert not (set("01OIL") & set(code1))


def test_codes_are_unique_across_wallets():
    _fresh("ref-B1"); _fresh("ref-B2")
    assert db.get_or_create_referral_code("ref-B1") != db.get_or_create_referral_code("ref-B2")


def test_redeem_credits_both_parties_once():
    _fresh("ref-referrer"); _fresh("ref-referee")
    code = db.get_or_create_referral_code("ref-referrer")
    result = db.redeem_referral("ref-referee", code)
    assert result["status"] == "ok"
    assert result["reward"] == config.REFERRAL_REWARD
    # /referral/redeem returns result["new_balance"] — the SQLite path must supply it.
    assert result["new_balance"] == config.REFERRAL_REWARD
    assert db.get_wallet_balance("ref-referee") == config.REFERRAL_REWARD
    assert db.get_wallet_balance("ref-referrer") == config.REFERRAL_REWARD


def test_supabase_redeem_normalizes_balance_to_new_balance(monkeypatch):
    """The Postgres RPC returns the referee balance as `balance`; the /referral/redeem
    response and the SQLite wrapper use `new_balance`. Regression for the Supabase path
    reporting new_balance=0 even though both wallets were credited (fixed 2026-07-21)."""
    import supabase_db

    class _FakeSb:
        def rpc(self, name, params):
            assert name == "redeem_referral"
            return {"status": "ok", "reward": 20, "balance": 20, "referrer_id": "r"}

    monkeypatch.setattr(supabase_db, "_sb", lambda: _FakeSb())
    monkeypatch.setattr(supabase_db, "_effective_max_balance", lambda _wid: 1000)
    out = supabase_db.redeem_referral("referee", "ABC123")
    assert out["status"] == "ok"
    assert out["new_balance"] == 20      # normalized from `balance`
    assert out["balance"] == 20          # original key preserved


def test_self_referral_blocked():
    _fresh("ref-self")
    code = db.get_or_create_referral_code("ref-self")
    assert db.redeem_referral("ref-self", code)["status"] == "self_referral"


def test_unknown_code_invalid():
    _fresh("ref-x")
    assert db.redeem_referral("ref-x", "ZZZZZZ")["status"] == "invalid_code"
    assert db.redeem_referral("ref-x", "")["status"] == "invalid_code"


def test_double_redeem_blocked_no_double_credit():
    _fresh("ref-r2"); _fresh("ref-e2")
    code = db.get_or_create_referral_code("ref-r2")
    assert db.redeem_referral("ref-e2", code)["status"] == "ok"
    # same referee tries again (their referred_by is now set)
    assert db.redeem_referral("ref-e2", code)["status"] == "already_redeemed"
    assert db.get_wallet_balance("ref-e2") == config.REFERRAL_REWARD   # not doubled
    assert db.get_wallet_balance("ref-r2") == config.REFERRAL_REWARD


def test_daily_cap_enforced(monkeypatch):
    monkeypatch.setattr(config, "MAX_REFERRALS_PER_DAY", 2)
    _fresh("ref-cap"); _fresh("ref-c1"); _fresh("ref-c2"); _fresh("ref-c3")
    code = db.get_or_create_referral_code("ref-cap")
    assert db.redeem_referral("ref-c1", code)["status"] == "ok"
    assert db.redeem_referral("ref-c2", code)["status"] == "ok"
    # third referee hits the referrer's daily cap
    assert db.redeem_referral("ref-c3", code)["status"] == "cap_reached"
    # capped referee got nothing and is not marked referred
    assert db.get_wallet_balance("ref-c3") == 0
    w = db.get_or_create_wallet("ref-c3")
    assert w.get("referred_by") in (None, "")
    assert db.count_referrals_today("ref-cap") == 2


def test_new_referee_wallet_created_on_redeem():
    _fresh("ref-r3")
    code = db.get_or_create_referral_code("ref-r3")
    # brand-new referee id that has no wallet yet (clear any leftover state from prior runs —
    # the test DB persists across runs, and the idempotency check keys on referral txns).
    conn = db._get_conn()
    conn.execute("DELETE FROM token_transactions WHERE wallet_id = ?", ("ref-brand-new",))
    conn.execute("DELETE FROM token_transactions WHERE reference_id = ?", ("referral:ref-r3:ref-brand-new",))
    conn.execute("DELETE FROM wallets WHERE id = ?", ("ref-brand-new",))
    conn.commit()
    result = db.redeem_referral("ref-brand-new", code)
    assert result["status"] == "ok"
    assert db.get_wallet_balance("ref-brand-new") == config.REFERRAL_REWARD
