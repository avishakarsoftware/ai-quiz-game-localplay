"""Tests for spark gifting (SPEC-GIFTING)."""
import uuid

import db
import config


def _uuid():
    return str(uuid.uuid4())


def _fresh(wallet_id, balance=0):
    conn = db._get_conn()
    conn.execute("DELETE FROM token_transactions WHERE wallet_id = ?", (wallet_id,))
    conn.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
    conn.commit()
    db.get_or_create_wallet(wallet_id, signup_bonus=False)
    if balance:
        db.credit_tokens(wallet_id, balance, "test_seed")


def test_happy_path_moves_sparks_and_records_both_legs():
    _fresh("gift-sender", balance=100)
    _fresh("gift-recipient")
    code = db.get_or_create_referral_code("gift-recipient")

    result = db.gift_sparks("gift-sender", code, 30, idempotency_key="k1")
    assert result["status"] == "ok"
    assert result["amount"] == 30
    assert result["new_balance"] == 70            # sender debited
    assert result["recipient_id"] == "gift-recipient"
    assert not result.get("duplicate")
    assert db.get_wallet_balance("gift-sender") == 70
    assert db.get_wallet_balance("gift-recipient") == 30


def test_code_is_case_and_space_insensitive():
    _fresh("gift-s2", balance=50)
    _fresh("gift-r2")
    code = db.get_or_create_referral_code("gift-r2")
    # lowercased + padded still resolves
    result = db.gift_sparks("gift-s2", f"  {code.lower()}  ", 5, idempotency_key="k2")
    assert result["status"] == "ok"
    assert db.get_wallet_balance("gift-r2") == 5


def test_invalid_amounts_rejected_without_movement():
    _fresh("gift-s3", balance=100)
    _fresh("gift-r3")
    code = db.get_or_create_referral_code("gift-r3")
    for bad in (0, -5, config.GIFT_MAX_AMOUNT + 1):
        assert db.gift_sparks("gift-s3", code, bad, idempotency_key=f"amt{bad}")["status"] == "invalid_amount"
    assert db.get_wallet_balance("gift-s3") == 100
    assert db.get_wallet_balance("gift-r3") == 0


def test_unknown_and_empty_code_invalid():
    _fresh("gift-s4", balance=100)
    assert db.gift_sparks("gift-s4", "ZZZZZZ", 5, idempotency_key="k4a")["status"] == "invalid_code"
    assert db.gift_sparks("gift-s4", "", 5, idempotency_key="k4b")["status"] == "invalid_code"
    assert db.get_wallet_balance("gift-s4") == 100


def test_self_gift_blocked():
    _fresh("gift-self", balance=100)
    code = db.get_or_create_referral_code("gift-self")
    assert db.gift_sparks("gift-self", code, 10, idempotency_key="k5")["status"] == "self_gift"
    assert db.get_wallet_balance("gift-self") == 100


def test_insufficient_balance_blocked():
    _fresh("gift-poor", balance=5)
    _fresh("gift-r6")
    code = db.get_or_create_referral_code("gift-r6")
    result = db.gift_sparks("gift-poor", code, 10, idempotency_key="k6")
    assert result["status"] == "insufficient"
    assert result["new_balance"] == 5
    assert db.get_wallet_balance("gift-poor") == 5
    assert db.get_wallet_balance("gift-r6") == 0


def test_recipient_at_cap_rejected_conserving_sparks():
    _fresh("gift-s7", balance=100)
    _fresh("gift-full")
    code = db.get_or_create_referral_code("gift-full")
    # Fill the recipient to the cap; a further gift must not destroy the sender's sparks.
    db.credit_tokens("gift-full", config.MAX_TOKEN_BALANCE, "test_fill")
    assert db.get_wallet_balance("gift-full") == config.MAX_TOKEN_BALANCE
    result = db.gift_sparks("gift-s7", code, 10, idempotency_key="k7")
    assert result["status"] == "recipient_full"
    assert db.get_wallet_balance("gift-s7") == 100                       # not debited
    assert db.get_wallet_balance("gift-full") == config.MAX_TOKEN_BALANCE


def test_idempotency_key_replays_without_double_send():
    _fresh("gift-s8", balance=100)
    _fresh("gift-r8")
    code = db.get_or_create_referral_code("gift-r8")
    first = db.gift_sparks("gift-s8", code, 20, idempotency_key="dupe")
    assert first["status"] == "ok" and not first.get("duplicate")
    # Same key again → replay, nothing moves.
    second = db.gift_sparks("gift-s8", code, 20, idempotency_key="dupe")
    assert second["status"] == "ok"
    assert second["duplicate"] is True
    assert second["new_balance"] == 80
    assert db.get_wallet_balance("gift-s8") == 80                        # debited once
    assert db.get_wallet_balance("gift-r8") == 20                        # credited once


def test_idempotency_replay_reports_original_amount_when_retry_body_changes():
    """A retry with the same key but a changed body must replay the original transaction details.
    Otherwise clients can show "sent 80" even though only 20 moved."""
    _fresh("gift-s8b", balance=100)
    _fresh("gift-r8b")
    code = db.get_or_create_referral_code("gift-r8b")
    first = db.gift_sparks("gift-s8b", code, 20, idempotency_key="same-key")
    second = db.gift_sparks("gift-s8b", code, 80, idempotency_key="same-key")
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["duplicate"] is True
    assert second["amount"] == 20
    assert second["original_amount"] == 20
    assert second["new_balance"] == 80
    assert db.get_wallet_balance("gift-s8b") == 80
    assert db.get_wallet_balance("gift-r8b") == 20


def test_idempotency_replay_ignores_changed_recipient_code():
    _fresh("gift-s8c", balance=100)
    _fresh("gift-r8c-original")
    _fresh("gift-r8c-other")
    original_code = db.get_or_create_referral_code("gift-r8c-original")
    other_code = db.get_or_create_referral_code("gift-r8c-other")
    first = db.gift_sparks("gift-s8c", original_code, 20, idempotency_key="same-key-recipient")
    second = db.gift_sparks("gift-s8c", other_code, 20, idempotency_key="same-key-recipient")
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["duplicate"] is True
    assert second["recipient_id"] == "gift-r8c-original"
    assert db.get_wallet_balance("gift-r8c-original") == 20
    assert db.get_wallet_balance("gift-r8c-other") == 0


def test_idempotency_replay_ignores_emptied_recipient_code():
    """SQLite↔Postgres parity: a same-key retry whose code is now empty must replay the original gift,
    NOT return invalid_code. The `gift_sparks` RPC checks the replay before the recipient/empty-code
    guard; db.gift_sparks must do the same, or the two backends disagree on this input."""
    _fresh("gift-s8d", balance=100)
    _fresh("gift-r8d")
    code = db.get_or_create_referral_code("gift-r8d")
    first = db.gift_sparks("gift-s8d", code, 20, idempotency_key="same-key-empty")
    second = db.gift_sparks("gift-s8d", "   ", 20, idempotency_key="same-key-empty")
    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["duplicate"] is True
    assert second["recipient_id"] == "gift-r8d"
    assert db.get_wallet_balance("gift-s8d") == 80          # debited once
    assert db.get_wallet_balance("gift-r8d") == 20


def test_empty_code_without_prior_is_invalid():
    """The other side of the parity coin: an empty code with no prior gift is still invalid_code."""
    _fresh("gift-s8e", balance=100)
    assert db.gift_sparks("gift-s8e", "   ", 20, idempotency_key="no-prior")["status"] == "invalid_code"
    assert db.gift_sparks("gift-s8e", "", 20, idempotency_key="")["status"] == "invalid_code"
    assert db.get_wallet_balance("gift-s8e") == 100


def test_daily_count_cap_enforced(monkeypatch):
    monkeypatch.setattr(config, "MAX_GIFTS_PER_DAY", 2)
    monkeypatch.setattr(config, "MAX_GIFT_TOKENS_PER_DAY", 10000)        # keep the token cap out of the way
    _fresh("gift-capper", balance=100)
    _fresh("gift-c1"); _fresh("gift-c2"); _fresh("gift-c3")
    codes = [db.get_or_create_referral_code(w) for w in ("gift-c1", "gift-c2", "gift-c3")]
    assert db.gift_sparks("gift-capper", codes[0], 1, idempotency_key="c1")["status"] == "ok"
    assert db.gift_sparks("gift-capper", codes[1], 1, idempotency_key="c2")["status"] == "ok"
    # third distinct gift hits the per-day COUNT cap
    assert db.gift_sparks("gift-capper", codes[2], 1, idempotency_key="c3")["status"] == "daily_cap"
    assert db.get_wallet_balance("gift-c3") == 0


def test_daily_token_cap_enforced(monkeypatch):
    monkeypatch.setattr(config, "MAX_GIFTS_PER_DAY", 100)                # keep the count cap out of the way
    monkeypatch.setattr(config, "MAX_GIFT_TOKENS_PER_DAY", 25)
    _fresh("gift-tcap", balance=100)
    _fresh("gift-t1"); _fresh("gift-t2")
    c1 = db.get_or_create_referral_code("gift-t1")
    c2 = db.get_or_create_referral_code("gift-t2")
    assert db.gift_sparks("gift-tcap", c1, 20, idempotency_key="t1")["status"] == "ok"
    # 20 already sent; another 20 would exceed the 25-spark daily total
    assert db.gift_sparks("gift-tcap", c2, 20, idempotency_key="t2")["status"] == "daily_cap"
    # a 5-spark gift still fits (20 + 5 == 25)
    assert db.gift_sparks("gift-tcap", c2, 5, idempotency_key="t3")["status"] == "ok"
    assert db.get_wallet_balance("gift-tcap") == 75


def test_supabase_gift_normalizes_balance_to_new_balance(monkeypatch):
    """The Postgres RPC returns the sender balance as `balance`; the /tokens/gift response and the
    SQLite wrapper use `new_balance`. Guard the Supabase path against reporting new_balance=0."""
    import supabase_db

    class _FakeSb:
        def rpc(self, name, params):
            assert name == "gift_sparks"
            assert params["p_sender_id"] == "sender"
            assert params["p_code"] == "ABC123"        # uppercased + trimmed by the wrapper
            assert params["p_amount"] == 15
            return {"status": "ok", "amount": 15, "balance": 85, "recipient_id": "r"}

    monkeypatch.setattr(supabase_db, "_sb", lambda: _FakeSb())
    out = supabase_db.gift_sparks("sender", "  abc123 ", 15, idempotency_key="k")
    assert out["status"] == "ok"
    assert out["new_balance"] == 85       # normalized from `balance`
    assert out["balance"] == 85           # original key preserved


def test_supabase_gift_validates_amount_before_rpc(monkeypatch):
    """Amount validation happens in the wrapper so a bad amount never reaches the RPC."""
    import supabase_db

    def _boom():
        raise AssertionError("RPC should not be called for an invalid amount")

    monkeypatch.setattr(supabase_db, "_sb", lambda: _boom())
    assert supabase_db.gift_sparks("s", "ABC123", 0)["status"] == "invalid_amount"
    assert supabase_db.gift_sparks("s", "ABC123", config.GIFT_MAX_AMOUNT + 1)["status"] == "invalid_amount"


def test_supabase_gift_defers_empty_code_to_rpc(monkeypatch):
    """Parity: the wrapper must NOT short-circuit an empty code — the RPC replays a prior gift before
    its recipient/empty-code check, so the wrapper has to call it (an empty p_code reaches the RPC)."""
    import supabase_db

    seen = {}

    class _FakeSb:
        def rpc(self, name, params):
            seen["called"] = True
            seen["p_code"] = params["p_code"]
            return {"status": "ok", "duplicate": True, "amount": 20, "balance": 80, "recipient_id": "r"}

    monkeypatch.setattr(supabase_db, "_sb", lambda: _FakeSb())
    out = supabase_db.gift_sparks("sender", "   ", 20, idempotency_key="k")
    assert seen.get("called") is True      # RPC was called, not short-circuited
    assert seen["p_code"] == ""            # empty code passed through for the RPC to decide
    assert out["status"] == "ok" and out["duplicate"] is True


# --- HTTP endpoint (/tokens/gift) ---
# conftest's fund_test_wallet fixture patches tokens.get_wallet_id to always return this id, so the
# endpoint always acts as that wallet regardless of the X-Device-Id header. Seed it as the sender.
TEST_DEVICE_ID = "00000000-0000-0000-0000-000000000001"


def _client():
    from fastapi.testclient import TestClient
    from main import app, _rate_limit_store
    _rate_limit_store.clear()
    return TestClient(app)


def test_endpoint_happy_path_returns_sent():
    _fresh(TEST_DEVICE_ID, balance=100)
    recipient = _uuid()
    _fresh(recipient)
    code = db.get_or_create_referral_code(recipient)
    res = _client().post("/tokens/gift", headers={"X-Device-Id": TEST_DEVICE_ID},
                         json={"code": code, "amount": 25, "idempotency_key": "e1"})
    assert res.status_code == 200
    assert res.json() == {"sent": True, "amount": 25, "new_balance": 75, "duplicate": False}
    assert db.get_wallet_balance(recipient) == 25


def test_endpoint_duplicate_replay_reports_original_amount():
    _fresh(TEST_DEVICE_ID, balance=100)
    recipient = _uuid()
    _fresh(recipient)
    code = db.get_or_create_referral_code(recipient)
    client = _client()
    first = client.post("/tokens/gift", headers={"X-Device-Id": TEST_DEVICE_ID},
                        json={"code": code, "amount": 25, "idempotency_key": "http-dupe"})
    second = client.post("/tokens/gift", headers={"X-Device-Id": TEST_DEVICE_ID},
                         json={"code": code, "amount": 75, "idempotency_key": "http-dupe"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"sent": True, "amount": 25, "new_balance": 75, "duplicate": True}
    assert db.get_wallet_balance(recipient) == 25


def test_endpoint_maps_domain_errors_to_status_codes():
    _fresh(TEST_DEVICE_ID, balance=100)
    # unknown code → 404
    r1 = _client().post("/tokens/gift", headers={"X-Device-Id": TEST_DEVICE_ID},
                        json={"code": "ZZZZZZ", "amount": 5, "idempotency_key": "e2"})
    assert r1.status_code == 404
    # self-gift → 400
    self_code = db.get_or_create_referral_code(TEST_DEVICE_ID)
    r2 = _client().post("/tokens/gift", headers={"X-Device-Id": TEST_DEVICE_ID},
                        json={"code": self_code, "amount": 5, "idempotency_key": "e3"})
    assert r2.status_code == 400
    # amount over the per-gift ceiling → 400
    r3 = _client().post("/tokens/gift", headers={"X-Device-Id": TEST_DEVICE_ID},
                        json={"code": "ABC123", "amount": config.GIFT_MAX_AMOUNT + 1, "idempotency_key": "e4"})
    assert r3.status_code == 400
    assert db.get_wallet_balance(TEST_DEVICE_ID) == 100
