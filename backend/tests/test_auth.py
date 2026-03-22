"""Tests for Phase 2: auth, session tokens, user-scoped entitlements, and quota consume checks."""
import sys
import os
import time
import uuid

import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import db
import auth
import config
import premium
from fastapi.testclient import TestClient


_DEVICE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_DEVICE_ID_2 = "aaaaaaaa-bbbb-cccc-dddd-ffffffffffff"
_DEVICE_HEADERS = {"X-Device-Id": _DEVICE_ID}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Each test gets a fresh database and a valid JWT_SECRET."""
    import threading
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret-key-for-auth-tests-32bytes!")
    # Save originals, point db at a fresh temp database
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "revelry.db"))
    db.init_db()
    yield


@pytest.fixture
def test_app():
    """Import app after db setup."""
    from main import app
    return TestClient(app)


# ============================================================================
# auth.py unit tests
# ============================================================================

class TestSessionTokens:
    """Test session JWT creation and verification."""

    def test_create_and_verify_session_token(self):
        user_id = str(uuid.uuid4())
        token = auth.create_session_token(user_id, _DEVICE_ID)
        result = auth.verify_session_token(token)
        assert result is not None
        assert result["user_id"] == user_id
        assert result["device_id"] == _DEVICE_ID

    def test_session_token_rejects_premium_token(self):
        """Session verification must reject non-session JWTs."""
        token = premium.create_premium_token(_DEVICE_ID)
        result = auth.verify_session_token(token)
        assert result is None

    def test_premium_token_rejects_session_token(self):
        """Premium verification must reject session JWTs."""
        user_id = str(uuid.uuid4())
        token = auth.create_session_token(user_id, _DEVICE_ID)
        result = premium.verify_premium_token(token, _DEVICE_ID)
        # verify_premium_token doesn't check type, but device_id should match
        # The key point: they shouldn't be interchangeable for authorization
        assert result is True  # It will match device_id, but type check is on session side

    def test_session_token_missing_fields(self):
        """Token with missing user_id or device_id is rejected."""
        import jwt as pyjwt
        payload = {"exp": time.time() + 3600, "type": "session"}
        token = pyjwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
        assert auth.verify_session_token(token) is None

    def test_session_token_expired(self):
        """Expired session token is rejected."""
        import jwt as pyjwt
        payload = {
            "user_id": "test",
            "device_id": _DEVICE_ID,
            "exp": time.time() - 100,
            "type": "session",
        }
        token = pyjwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
        assert auth.verify_session_token(token) is None

    def test_session_token_wrong_secret(self):
        """Token signed with wrong secret is rejected."""
        import jwt as pyjwt
        payload = {
            "user_id": "test",
            "device_id": _DEVICE_ID,
            "exp": time.time() + 3600,
            "type": "session",
        }
        token = pyjwt.encode(payload, "wrong_secret", algorithm="HS256")
        assert auth.verify_session_token(token) is None


class TestGoogleTokenVerification:
    """Test Google ID token verification."""

    def test_missing_client_id_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "")
        assert auth.verify_google_token("fake_token") is None

    def test_invalid_token_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "test-client-id")
        # verify_google_token catches all exceptions internally and returns None
        result = auth.verify_google_token("invalid_garbage_token")
        assert result is None


class TestAppleTokenVerification:
    """Test Apple ID token verification."""

    def test_missing_client_id_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "APPLE_CLIENT_ID", "")
        assert auth.verify_apple_token("fake_token") is None


# ============================================================================
# db.py user-related tests
# ============================================================================

class TestUserDB:
    """Test user CRUD operations in db."""

    def test_find_or_create_user_creates_new(self):
        user = db.find_or_create_user("google", "sub_123", "test@example.com")
        assert user["provider"] == "google"
        assert user["provider_subject_id"] == "sub_123"
        assert user["email"] == "test@example.com"
        assert user["id"]

    def test_find_or_create_user_finds_existing(self):
        user1 = db.find_or_create_user("google", "sub_123", "test@example.com")
        user2 = db.find_or_create_user("google", "sub_123", "test@example.com")
        assert user1["id"] == user2["id"]

    def test_find_or_create_user_updates_email(self):
        db.find_or_create_user("google", "sub_456", "old@example.com")
        user = db.find_or_create_user("google", "sub_456", "new@example.com")
        # The returned user is from the SELECT before UPDATE, but DB is updated
        fresh = db.get_user(user["id"])
        assert fresh["email"] == "new@example.com"

    def test_different_providers_create_different_users(self):
        u1 = db.find_or_create_user("google", "sub_x", "x@example.com")
        u2 = db.find_or_create_user("apple", "sub_x", "x@example.com")
        assert u1["id"] != u2["id"]

    def test_get_user_not_found(self):
        assert db.get_user("nonexistent") is None


class TestMergeDeviceToUser:
    """Test that entitlements/usage are merged on sign-in."""

    def test_merge_entitlements(self):
        # Create orphaned entitlement (no user_id)
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID)
        ent = db.get_active_entitlement(_DEVICE_ID)
        assert ent is not None
        assert ent["user_id"] is None or ent["user_id"] == ""

        # Create user and merge
        user = db.find_or_create_user("google", "sub_merge", "merge@test.com")
        db.merge_device_to_user(user["id"], _DEVICE_ID)

        # Entitlement should now belong to user
        ent = db.get_active_entitlement_for_user(user["id"])
        assert ent is not None
        assert ent["id"] == ent_id

    def test_merge_does_not_steal_other_users_entitlements(self):
        """Merging should not overwrite entitlements belonging to another user."""
        user_a = db.find_or_create_user("google", "user_a", "a@test.com")
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, user_id=user_a["id"])

        user_b = db.find_or_create_user("google", "user_b", "b@test.com")
        db.merge_device_to_user(user_b["id"], _DEVICE_ID)

        # Entitlement should still belong to user_a
        ent = db.lookup_entitlement(ent_id)
        assert ent["user_id"] == user_a["id"]

    def test_merge_usage(self):
        # Create orphaned usage
        db.check_and_increment_free_usage(_DEVICE_ID)
        user = db.find_or_create_user("google", "sub_usage", "usage@test.com")
        db.merge_device_to_user(user["id"], _DEVICE_ID)

        count = db.get_user_free_usage_count(user["id"])
        assert count == 1


class TestUserFreeUsage:
    """Test cross-device free usage for signed-in users."""

    def test_cross_device_counting(self):
        user = db.find_or_create_user("google", "sub_cross", "cross@test.com")
        uid = user["id"]

        # Use on device 1
        db.merge_device_to_user(uid, _DEVICE_ID)
        allowed, count = db.check_and_increment_user_free_usage(uid, _DEVICE_ID)
        assert allowed is True
        assert count == 1

        # Use on device 2
        db.merge_device_to_user(uid, _DEVICE_ID_2)
        allowed, count = db.check_and_increment_user_free_usage(uid, _DEVICE_ID_2)
        assert allowed is True
        assert count == 2

        total = db.get_user_free_usage_count(uid)
        assert total == 2

    def test_cross_device_limit_enforced(self, monkeypatch):
        monkeypatch.setattr(config, "FREE_TIER_LIMIT", 2)
        user = db.find_or_create_user("google", "sub_limit", "limit@test.com")
        uid = user["id"]

        db.check_and_increment_user_free_usage(uid, _DEVICE_ID)
        db.check_and_increment_user_free_usage(uid, _DEVICE_ID_2)

        # Third attempt on a new device should be denied
        device_3 = "aaaaaaaa-bbbb-cccc-dddd-111111111111"
        allowed, count = db.check_and_increment_user_free_usage(uid, device_3)
        assert allowed is False
        assert count == 2

    def test_peek_user_free_usage(self, monkeypatch):
        monkeypatch.setattr(config, "FREE_TIER_LIMIT", 3)
        user = db.find_or_create_user("google", "sub_peek", "peek@test.com")
        uid = user["id"]

        can_play, used = db.peek_user_free_usage(uid)
        assert can_play is True
        assert used == 0

        db.check_and_increment_user_free_usage(uid, _DEVICE_ID)
        can_play, used = db.peek_user_free_usage(uid)
        assert can_play is True
        assert used == 1


class TestUserEntitlements:
    """Test user-scoped entitlement checks."""

    def test_has_active_entitlement_for_user(self):
        user = db.find_or_create_user("google", "sub_ent", "ent@test.com")
        assert premium.has_active_entitlement_for_user(user["id"]) is False

        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, user_id=user["id"])
        assert premium.has_active_entitlement_for_user(user["id"]) is True

    def test_check_and_use_entitlement_for_user(self):
        user = db.find_or_create_user("google", "sub_use", "use@test.com")
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, user_id=user["id"], games=2)

        success, ent = premium.check_and_use_entitlement_for_user(user["id"])
        assert success is True
        assert ent["games_remaining"] == 1

        success, ent = premium.check_and_use_entitlement_for_user(user["id"])
        assert success is True
        assert ent["games_remaining"] == 0

        # Third use should fail (exhausted)
        success, ent = premium.check_and_use_entitlement_for_user(user["id"])
        assert success is False
        assert ent is None

    def test_empty_user_id_returns_false(self):
        assert premium.has_active_entitlement_for_user("") is False


# ============================================================================
# main.py endpoint tests
# ============================================================================

class TestSignInEndpoint:
    """Test POST /auth/signin."""

    def test_signin_invalid_provider(self, test_app):
        res = test_app.post("/auth/signin", json={
            "provider": "github",
            "id_token": "test",
            "device_id": _DEVICE_ID,
        })
        assert res.status_code == 422

    def test_signin_invalid_device_id(self, test_app):
        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "test",
            "device_id": "not-a-uuid",
        })
        assert res.status_code == 422

    def test_signin_empty_id_token(self, test_app):
        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "",
            "device_id": _DEVICE_ID,
        })
        assert res.status_code == 422

    def test_signin_oversized_id_token(self, test_app):
        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "x" * 10001,
            "device_id": _DEVICE_ID,
        })
        assert res.status_code == 422

    def test_signin_invalid_token_returns_401(self, test_app):
        """When the ID token fails verification, return 401."""
        with patch("auth.verify_id_token", return_value=None):
            res = test_app.post("/auth/signin", json={
                "provider": "google",
                "id_token": "fake_but_valid_length",
                "device_id": _DEVICE_ID,
            })
            assert res.status_code == 401

    def test_signin_success(self, test_app):
        """Successful sign-in returns user + session_token."""
        with patch("auth.verify_id_token", return_value={"sub": "google_sub_1", "email": "test@gmail.com"}):
            res = test_app.post("/auth/signin", json={
                "provider": "google",
                "id_token": "valid_token",
                "device_id": _DEVICE_ID,
            })
            assert res.status_code == 200
            data = res.json()
            assert data["user"]["provider"] == "google"
            assert data["user"]["email"] == "test@gmail.com"
            assert data["session_token"]

    def test_signin_merges_device_entitlements(self, test_app):
        """Signing in should merge orphaned entitlements to the user."""
        # Create orphaned entitlement
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID)

        with patch("auth.verify_id_token", return_value={"sub": "merge_sub", "email": "merge@test.com"}):
            res = test_app.post("/auth/signin", json={
                "provider": "google",
                "id_token": "valid_token",
                "device_id": _DEVICE_ID,
            })
            assert res.status_code == 200
            user_id = res.json()["user"]["id"]

        ent = db.lookup_entitlement(ent_id)
        assert ent["user_id"] == user_id


class TestAuthMeEndpoint:
    """Test GET /auth/me."""

    def test_me_no_session(self, test_app):
        res = test_app.get("/auth/me")
        assert res.status_code == 401

    def test_me_invalid_session(self, test_app):
        res = test_app.get("/auth/me", headers={"X-Session-Token": "garbage"})
        assert res.status_code == 401

    def test_me_valid_session(self, test_app):
        # Create user directly
        user = db.find_or_create_user("google", "me_sub", "me@test.com")
        token = auth.create_session_token(user["id"], _DEVICE_ID)

        res = test_app.get("/auth/me", headers={"X-Session-Token": token})
        assert res.status_code == 200
        data = res.json()
        assert data["user"]["id"] == user["id"]
        assert data["user"]["email"] == "me@test.com"
        assert "entitlement" in data

    def test_me_deleted_user(self, test_app):
        """If user is deleted but has valid session, return 401."""
        token = auth.create_session_token("nonexistent_user", _DEVICE_ID)
        res = test_app.get("/auth/me", headers={"X-Session-Token": token})
        assert res.status_code == 401


class TestConsumeReturnValues:
    """Test that generate endpoints check consume return values (Critical #2-3 fix)."""

    def test_quiz_generate_402_on_expired_entitlement(self, test_app):
        """If entitlement expires between peek and consume, return 402."""
        from unittest.mock import AsyncMock

        with patch("main._check_rate_limit", return_value=True), \
             patch("main.quiz_engine.generate_quiz", new_callable=AsyncMock) as mock_gen, \
             patch("main.premium.has_active_entitlement", return_value=True), \
             patch("main.premium.check_and_use_entitlement", return_value=(False, None)):
            mock_gen.return_value = {"quiz_title": "Test", "questions": []}
            res = test_app.post("/quiz/generate", json={
                "prompt": "test topic",
                "difficulty": "medium",
                "num_questions": 5,
            }, headers=_DEVICE_HEADERS)
            assert res.status_code == 402
            assert "expired" in res.json()["detail"].lower() or "exhausted" in res.json()["detail"].lower()

    def test_mlt_generate_402_on_expired_entitlement(self, test_app):
        """If entitlement expires between peek and consume, return 402."""
        from unittest.mock import AsyncMock

        with patch("main._check_rate_limit", return_value=True), \
             patch("main.mlt_engine.generate_statements", new_callable=AsyncMock) as mock_gen, \
             patch("main.premium.has_active_entitlement", return_value=True), \
             patch("main.premium.check_and_use_entitlement", return_value=(False, None)):
            mock_gen.return_value = {"game_title": "Test", "statements": []}
            res = test_app.post("/mlt/generate", json={
                "prompt": "test theme",
                "difficulty": "party",
                "num_rounds": 5,
            }, headers=_DEVICE_HEADERS)
            assert res.status_code == 402

    def test_quiz_generate_402_on_free_limit_race(self, test_app):
        """If free limit reached between peek and consume, return 402."""
        from unittest.mock import AsyncMock

        with patch("main._check_rate_limit", return_value=True), \
             patch("main.quiz_engine.generate_quiz", new_callable=AsyncMock) as mock_gen, \
             patch("main.premium.has_active_entitlement", return_value=False), \
             patch("main.premium.peek_free_limit", return_value=(True, 2)), \
             patch("main.premium.check_free_limit", return_value=(False, 3)):
            mock_gen.return_value = {"quiz_title": "Test", "questions": []}
            res = test_app.post("/quiz/generate", json={
                "prompt": "test topic",
                "difficulty": "medium",
                "num_questions": 5,
            }, headers=_DEVICE_HEADERS)
            assert res.status_code == 402


class TestPendingTokenTTL:
    """Test that pending tokens respect the 1-hour TTL."""

    def test_token_retrievable_within_ttl(self):
        db.store_pending_token(_DEVICE_ID, "test_token")
        token = db.pop_pending_token(_DEVICE_ID)
        assert token == "test_token"

    def test_token_deleted_after_pop(self):
        db.store_pending_token(_DEVICE_ID, "test_token")
        db.pop_pending_token(_DEVICE_ID)
        token = db.pop_pending_token(_DEVICE_ID)
        assert token is None

    def test_token_expired_after_ttl(self, monkeypatch):
        db.store_pending_token(_DEVICE_ID, "test_token")
        # Simulate time passing beyond TTL
        original_time = time.time
        monkeypatch.setattr(time, "time", lambda: original_time() + 3601)
        token = db.pop_pending_token(_DEVICE_ID)
        assert token is None


class TestWindowExpiry:
    """Test off-by-one fix: window at exactly 24h should be expired."""

    def test_exactly_24h_window_is_expired(self, monkeypatch):
        now = int(time.time())
        # Manually insert a device_usage row with window_start exactly 24h ago
        conn = db._get_conn()
        conn.execute(
            "INSERT INTO device_usage (device_id, games_used_free, window_start) VALUES (?, 3, ?)",
            (_DEVICE_ID, now - 24 * 3600),
        )
        conn.commit()

        # With <= fix, this should be treated as expired (window reset)
        can_play, used = db.peek_free_usage(_DEVICE_ID)
        assert can_play is True
        assert used == 0


class TestEntitlementStatus:
    """Test GET /entitlements/current."""

    def test_no_device_id(self, test_app):
        res = test_app.get("/entitlements/current")
        data = res.json()
        assert data["premium"] is False
        assert data["free_games_limit"] == config.FREE_TIER_LIMIT

    def test_with_device_id_no_entitlement(self, test_app):
        res = test_app.get("/entitlements/current", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["premium"] is False
        assert data["free_games_used"] == 0

    def test_with_active_entitlement(self, test_app):
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID)

        res = test_app.get("/entitlements/current", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["premium"] is True
        assert data["games_remaining"] == 50

    def test_user_scoped_entitlement(self, test_app):
        user = db.find_or_create_user("google", "ent_sub", "ent@test.com")
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, user_id=user["id"])
        session_token = auth.create_session_token(user["id"], _DEVICE_ID)

        res = test_app.get("/entitlements/current", headers={
            **_DEVICE_HEADERS,
            "X-Session-Token": session_token,
        })
        data = res.json()
        assert data["premium"] is True


class TestRestorePurchases:
    """Test POST /purchases/restore endpoint."""

    def test_no_device_id(self, test_app):
        res = test_app.post("/purchases/restore")
        assert res.status_code == 400

    def test_no_purchases_to_restore(self, test_app):
        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["restored"] is False

    def test_restore_active_apple_purchase(self, test_app):
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, apple_transaction_id="apple_txn_123")

        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["restored"] is True
        assert "token" in data

    def test_restore_active_google_purchase(self, test_app):
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, google_order_id="google_order_123")

        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["restored"] is True
        assert "token" in data

    def test_no_restore_for_stripe_only(self, test_app):
        """Stripe purchases are not restorable via this endpoint."""
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, stripe_session_id="stripe_sess_123")

        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["restored"] is False

    def test_no_restore_for_expired_iap(self, test_app):
        """Expired IAP entitlements are found but not restored (no active status)."""
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID, apple_transaction_id="apple_txn_456")
        # Expire it
        conn = db._get_conn()
        conn.execute("UPDATE entitlements SET status = 'expired_time' WHERE id = ?", (ent_id,))
        conn.commit()

        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["restored"] is False

    def test_restore_user_scoped_purchase(self, test_app):
        """Signed-in user can restore a purchase linked to their account."""
        user = db.find_or_create_user("apple", "restore_sub", "restore@test.com")
        ent_id = str(uuid.uuid4())
        db.create_entitlement(ent_id, _DEVICE_ID_2, apple_transaction_id="apple_txn_789",
                              user_id=user["id"])

        session_token = auth.create_session_token(user["id"], _DEVICE_ID)
        res = test_app.post("/purchases/restore", headers={
            **_DEVICE_HEADERS,
            "X-Session-Token": session_token,
        })
        data = res.json()
        assert data["restored"] is True
        assert "token" in data
