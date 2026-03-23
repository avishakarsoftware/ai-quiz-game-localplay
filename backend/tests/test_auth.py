"""Tests for Phase 2: auth, session tokens, token balance, and wallet merge."""
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
import tokens as tokens_mod
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

    def test_session_token_rejects_non_session_jwt(self):
        """Session verification must reject JWTs without type=session."""
        import jwt as pyjwt
        payload = {
            "device_id": _DEVICE_ID,
            "exp": time.time() + 3600,
            "type": "party_pass",
        }
        token = pyjwt.encode(payload, config.JWT_SECRET, algorithm="HS256")
        result = auth.verify_session_token(token)
        assert result is None

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

    def test_signin_merges_wallet(self, test_app):
        """Signing in should merge device wallet to user wallet."""
        # Fund the device wallet before sign-in
        db.credit_tokens(_DEVICE_ID, 50, "test_setup")

        with patch("auth.verify_id_token", return_value={"sub": "merge_sub", "email": "merge@test.com"}):
            res = test_app.post("/auth/signin", json={
                "provider": "google",
                "id_token": "valid_token",
                "device_id": _DEVICE_ID,
            })
            assert res.status_code == 200
            user_id = res.json()["user"]["id"]

        # User wallet should have the merged tokens
        balance = db.get_wallet_balance(user_id)
        assert balance >= 50


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
        assert "tokens" in data
        assert "balance" in data["tokens"]

    def test_me_deleted_user(self, test_app):
        """If user is deleted but has valid session, return 401."""
        token = auth.create_session_token("nonexistent_user", _DEVICE_ID)
        res = test_app.get("/auth/me", headers={"X-Session-Token": token})
        assert res.status_code == 401


class TestTokenSpendingAtRoomCreate:
    """Test that room creation spends tokens (conftest monkeypatches spend to succeed)."""

    def test_room_create_succeeds_with_tokens(self, test_app):
        """Room creation succeeds when token spending succeeds (monkeypatched)."""
        from main import quizzes
        from socket_manager import socket_manager
        quiz_id = "test-token-spend"
        quizzes[quiz_id] = {"quiz_title": "Test", "questions": [{"id": 1, "text": "Q", "options": ["A", "B", "C", "D"], "answer_index": 0, "image_prompt": ""}]}

        res = test_app.post("/room/create", json={
            "quiz_id": quiz_id,
            "game_type": "quiz",
            "time_limit": 15,
        }, headers=_DEVICE_HEADERS)
        assert res.status_code == 200
        room_code = res.json()["room_code"]
        socket_manager.rooms.pop(room_code, None)
        quizzes.pop(quiz_id, None)

    def test_room_create_402_when_no_tokens(self, test_app, monkeypatch):
        """Room creation returns 402 when token spending fails."""
        from main import quizzes
        quiz_id = "test-no-tokens"
        quizzes[quiz_id] = {"quiz_title": "Test", "questions": [{"id": 1, "text": "Q", "options": ["A", "B", "C", "D"], "answer_index": 0, "image_prompt": ""}]}

        # Undo conftest monkeypatch: make spend_room fail
        monkeypatch.setattr(tokens_mod, "spend_room", lambda wallet_id: (False, 0))

        res = test_app.post("/room/create", json={
            "quiz_id": quiz_id,
            "game_type": "quiz",
            "time_limit": 15,
        }, headers=_DEVICE_HEADERS)
        assert res.status_code == 402
        quizzes.pop(quiz_id, None)


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


class TestTokenBalanceEndpoint:
    """Test GET /tokens/balance and GET /entitlements/current (alias)."""

    def test_no_device_id(self, test_app):
        res = test_app.get("/tokens/balance")
        data = res.json()
        assert "balance" in data
        assert data["balance"] == 0

    def test_with_device_id(self, test_app):
        res = test_app.get("/tokens/balance", headers=_DEVICE_HEADERS)
        data = res.json()
        assert "balance" in data
        assert "cost_generate" in data
        assert "cost_room" in data

    def test_entitlements_current_is_alias(self, test_app):
        """Legacy /entitlements/current returns same format as /tokens/balance."""
        res = test_app.get("/entitlements/current", headers=_DEVICE_HEADERS)
        data = res.json()
        assert "balance" in data
        assert "cost_generate" in data


class TestRestorePurchases:
    """Test POST /purchases/restore endpoint."""

    def test_no_device_id(self, test_app):
        res = test_app.post("/purchases/restore")
        assert res.status_code == 400

    def test_no_purchases_to_restore(self, test_app):
        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)
        data = res.json()
        assert data["restored"] is False
