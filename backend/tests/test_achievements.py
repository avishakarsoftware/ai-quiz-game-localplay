"""Tests for achievements / badges (SPEC-ACHIEVEMENTS)."""
import uuid

import db
import config


def _uuid():
    return str(uuid.uuid4())


def _fresh(wallet_id):
    conn = db._get_conn()
    conn.execute("DELETE FROM achievements WHERE wallet_id = ?", (wallet_id,))
    conn.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
    conn.commit()
    db.get_or_create_wallet(wallet_id, signup_bonus=False)


def test_award_is_idempotent_and_reports_first_grant():
    w = _uuid()
    _fresh(w)
    assert db.award_achievement(w, "welcome") is True     # first grant
    assert db.award_achievement(w, "welcome") is False    # already held
    assert db.list_achievements(w).keys() == {"welcome"}


def test_unknown_badge_id_is_rejected():
    w = _uuid()
    _fresh(w)
    assert db.award_achievement(w, "not_a_real_badge") is False
    assert db.list_achievements(w) == {}


def test_list_returns_awarded_at_timestamps():
    w = _uuid()
    _fresh(w)
    db.award_achievement(w, "first_gift")
    earned = db.list_achievements(w)
    assert "first_gift" in earned
    assert isinstance(earned["first_gift"], int) and earned["first_gift"] > 0


def test_multiple_badges_coexist():
    w = _uuid()
    _fresh(w)
    for badge in ("welcome", "first_referral", "first_gift"):
        assert db.award_achievement(w, badge) is True
    assert set(db.list_achievements(w)) == {"welcome", "first_referral", "first_gift"}


def test_catalog_ids_match_frozenset():
    assert config.ACHIEVEMENT_IDS == frozenset(b["id"] for b in config.ACHIEVEMENT_CATALOG)
    # every catalog id is awardable
    w = _uuid()
    _fresh(w)
    for badge in config.ACHIEVEMENT_CATALOG:
        assert db.award_achievement(w, badge["id"]) is True


# --- HTTP endpoint (/achievements) ---
# conftest's fund_test_wallet patches tokens.get_wallet_id to always return TEST_DEVICE_ID.
TEST_DEVICE_ID = "00000000-0000-0000-0000-000000000001"


def _client():
    from fastapi.testclient import TestClient
    from main import app, _rate_limit_store
    _rate_limit_store.clear()
    return TestClient(app)


def test_endpoint_returns_full_catalog_with_earned_flags():
    _fresh(TEST_DEVICE_ID)
    db.award_achievement(TEST_DEVICE_ID, "first_gift")
    res = _client().get("/achievements", headers={"X-Device-Id": TEST_DEVICE_ID})
    assert res.status_code == 200
    body = res.json()
    ids = [b["id"] for b in body["badges"]]
    assert ids == [b["id"] for b in config.ACHIEVEMENT_CATALOG]      # full catalog, in order
    by_id = {b["id"]: b for b in body["badges"]}
    assert by_id["first_gift"]["earned"] is True
    assert by_id["first_gift"]["awarded_at"] is not None
    # every badge carries display metadata for the (dumb) frontend
    assert by_id["welcome"]["emoji"] and by_id["welcome"]["name"] and by_id["welcome"]["description"]


def test_endpoint_awards_welcome_on_first_view():
    _fresh(TEST_DEVICE_ID)
    assert "welcome" not in db.list_achievements(TEST_DEVICE_ID)
    res = _client().get("/achievements", headers={"X-Device-Id": TEST_DEVICE_ID})
    assert res.status_code == 200
    by_id = {b["id"]: b for b in res.json()["badges"]}
    assert by_id["welcome"]["earned"] is True                        # granted lazily on view
    assert "welcome" in db.list_achievements(TEST_DEVICE_ID)


def test_referral_redeem_awards_both_parties(monkeypatch):
    """The /referral/redeem success path awards first_referral to referee AND referrer."""
    monkeypatch.setattr(config, "SIGNUP_BONUS_TOKENS", 0)
    referrer, referee = _uuid(), TEST_DEVICE_ID
    _fresh(referrer)
    _fresh(referee)
    code = db.get_or_create_referral_code(referrer)
    res = _client().post("/referral/redeem", headers={"X-Device-Id": referee}, json={"code": code})
    assert res.status_code == 200
    assert "first_referral" in db.list_achievements(referee)
    assert "first_referral" in db.list_achievements(referrer)


def test_gift_awards_first_gift_to_sender():
    """The /tokens/gift success path awards first_gift to the sender (not on a duplicate replay)."""
    _fresh(TEST_DEVICE_ID)
    db.credit_tokens(TEST_DEVICE_ID, 100, "test_seed")
    recipient = _uuid()
    _fresh(recipient)
    code = db.get_or_create_referral_code(recipient)
    res = _client().post("/tokens/gift", headers={"X-Device-Id": TEST_DEVICE_ID},
                         json={"code": code, "amount": 10, "idempotency_key": "a1"})
    assert res.status_code == 200
    assert "first_gift" in db.list_achievements(TEST_DEVICE_ID)
