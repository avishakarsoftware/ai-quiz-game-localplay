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
        monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", [])
        assert auth.verify_google_token("fake_token") is None

    def test_invalid_token_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "test-client-id")
        monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", ["test-client-id"])
        # verify_google_token catches all exceptions internally and returns None
        result = auth.verify_google_token("invalid_garbage_token")
        assert result is None

    def test_accepts_configured_web_and_ios_audiences(self, monkeypatch):
        audiences = [
            "458966837298-9hjencou1ag2o17ln06iuuj86j5p8igj.apps.googleusercontent.com",
            "458966837298-ncc86ha91tct2lo9ah16g8v9ibp4ckki.apps.googleusercontent.com",
        ]
        monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", audiences)

        with patch(
            "google.oauth2.id_token.verify_oauth2_token",
            return_value={
                "iss": "https://accounts.google.com",
                "sub": "google_sub",
                "email": "g@example.com",
            },
        ) as verify:
            result = auth.verify_google_token("fake_token")

        assert result == {"sub": "google_sub", "email": "g@example.com"}
        assert verify.call_args.kwargs["audience"] == audiences


class TestAppleTokenVerification:
    """Test Apple ID token verification."""

    def test_missing_client_id_returns_none(self, monkeypatch):
        monkeypatch.setattr(config, "APPLE_CLIENT_ID", "")
        monkeypatch.setattr(config, "APPLE_CLIENT_IDS", [])
        assert auth.verify_apple_token("fake_token") is None

    def test_accepts_configured_web_and_native_audiences(self, monkeypatch):
        class FakeJwksClient:
            def get_signing_key_from_jwt(self, token):
                assert token == "fake_token"
                return type("Key", (), {"key": "public-key"})()

        audiences = ["me.revelryapp.quiz.web", "me.revelryapp.quiz"]
        monkeypatch.setattr(config, "APPLE_CLIENT_IDS", audiences)
        monkeypatch.setattr(auth, "_get_apple_jwks_client", lambda: FakeJwksClient())

        with patch("auth.jwt.decode", return_value={"sub": "apple_sub", "email": "a@example.com"}) as decode:
            result = auth.verify_apple_token("fake_token")

        assert result == {"sub": "apple_sub", "email": "a@example.com"}
        assert decode.call_args.kwargs["audience"] == audiences


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

    def test_room_create_succeeds_with_zero_balance(self, test_app, monkeypatch):
        """Room creation succeeds even with zero balance (charge is on game start)."""
        from main import quizzes, socket_manager
        quiz_id = "test-zero-balance"
        quizzes[quiz_id] = {"quiz_title": "Test", "questions": [{"id": 1, "text": "Q", "options": ["A", "B", "C", "D"], "answer_index": 0, "image_prompt": ""}]}

        # Undo conftest monkeypatch: make spend_room fail (simulating zero balance)
        monkeypatch.setattr(tokens_mod, "spend_room", lambda wallet_id: (False, 0))

        res = test_app.post("/room/create", json={
            "quiz_id": quiz_id,
            "game_type": "quiz",
            "time_limit": 15,
        }, headers=_DEVICE_HEADERS)
        assert res.status_code == 200  # Room creation is free; charge happens on START_GAME
        room_code = res.json()["room_code"]
        socket_manager.rooms.pop(room_code, None)
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


# removed 2026-08-04: TestWindowExpiry guarded an off-by-one in the pre-spark rolling 24h
# free-usage window (db.peek_free_usage). That whole mechanism is gone — daily limits are now
# calendar-day based via _utc_date_str(), which has its own coverage in test_streak_bonus.py and
# test_tokens.py. The device_usage table survives only for account merge/deletion and admin lookup.


class TestTokenBalanceEndpoint:
    """Test GET /tokens/balance and GET /entitlements/current (alias)."""

    def test_no_device_id(self, test_app, monkeypatch):
        # Undo conftest monkeypatch so get_wallet_id uses real implementation
        from tokens import get_device_id
        import auth as auth_module
        def real_get_wallet_id(req):
            session = auth_module.get_session_from_request(req)
            if session and session.get("user_id"):
                return session["user_id"]
            return get_device_id(req)
        monkeypatch.setattr(tokens_mod, "get_wallet_id", real_get_wallet_id)
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

    def test_restore_lookup_failure_returns_503(self, test_app, monkeypatch):
        def boom(*_args, **_kwargs):
            raise TimeoutError("db timeout")

        monkeypatch.setattr(db, "find_restorable_entitlement", boom)

        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)

        assert res.status_code == 503
        assert "Could not check purchases" in res.json()["detail"]

    def test_restore_credit_failure_returns_503(self, test_app, monkeypatch):
        monkeypatch.setattr(db, "find_restorable_entitlement", lambda *_args, **_kwargs: {
            "id": "ent-restore-1",
            "status": "active",
            "games_remaining": 1,
        })

        def boom(*_args, **_kwargs):
            raise TimeoutError("db timeout")

        monkeypatch.setattr(db, "credit_tokens", boom)

        res = test_app.post("/purchases/restore", headers=_DEVICE_HEADERS)

        assert res.status_code == 503
        assert "Could not restore purchases" in res.json()["detail"]


class TestPromoCheckout:
    """Test promo_id validation in the checkout endpoint."""

    def test_promo_id_validation_strips_invalid(self):
        """promo_id with special characters should be silently discarded (validator returns '')."""
        from main import CheckoutRequest
        req = CheckoutRequest(device_id=_DEVICE_ID, promo_id="launch<script>alert(1)</script>")
        assert req.promo_id == ""  # Validator silently discards invalid chars

    def test_promo_id_too_long_discarded(self):
        """promo_id longer than 50 chars should be silently discarded."""
        from main import CheckoutRequest
        req = CheckoutRequest(device_id=_DEVICE_ID, promo_id="a" * 51)
        assert req.promo_id == ""  # Validator silently discards oversized promo_id

    def test_promo_id_valid_passes_through(self):
        """Valid promo_id (alphanumeric, underscores, hyphens, <=50 chars) passes through."""
        from main import CheckoutRequest
        req = CheckoutRequest(device_id=_DEVICE_ID, promo_id="launch_2026-special")
        assert req.promo_id == "launch_2026-special"

    def test_promo_id_empty_is_valid(self):
        """Empty promo_id is the default and should pass through."""
        from main import CheckoutRequest
        req = CheckoutRequest(device_id=_DEVICE_ID)
        assert req.promo_id == ""


class TestSigninDeviceIdBinding:
    """Sign-in should reject mismatched body device_id vs X-Device-Id header."""

    def test_signin_mismatched_device_id_400(self, test_app):
        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "fake-token",
            "device_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        }, headers={"X-Device-Id": "11111111-2222-3333-4444-555555555555"})
        assert res.status_code == 400
        assert "does not match" in res.json()["detail"]

    def test_signin_matching_device_id_passes_validation(self, test_app):
        """Matching header should not cause 400 (will get 401 from invalid token)."""
        device = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "fake-token",
            "device_id": device,
        }, headers={"X-Device-Id": device})
        # Gets past device_id check — fails on token verification (401)
        assert res.status_code == 401

    def test_signin_no_header_passes_validation(self, test_app):
        """Missing X-Device-Id header should not cause 400 (old clients)."""
        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "fake-token",
            "device_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        })
        assert res.status_code == 401  # Fails on token, not device_id


class TestQuizAnswerStripping:
    """Public quiz endpoint should strip answer_index from questions."""

    def test_get_quiz_strips_answers(self, test_app):
        """GET /quiz/{id} should not include answer_index."""
        from main import quizzes, quiz_timestamps
        import time
        quiz_id = "test-strip-answers"
        quizzes[quiz_id] = {
            "quiz_title": "Test",
            "questions": [
                {"id": "q1", "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 2},
            ],
        }
        quiz_timestamps[quiz_id] = time.time()
        res = test_app.get(f"/quiz/{quiz_id}")
        assert res.status_code == 200
        data = res.json()
        for q in data["questions"]:
            assert "answer_index" not in q
        # Clean up
        del quizzes[quiz_id]
        del quiz_timestamps[quiz_id]


class TestHistoryAuth:
    """History endpoints should require device identity."""

    def test_history_no_device_id_401(self, test_app, monkeypatch):
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "")
        res = test_app.get("/history")
        assert res.status_code == 401

    def test_history_detail_no_device_id_401(self, test_app, monkeypatch):
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "")
        res = test_app.get("/history/NONEXISTENT")
        assert res.status_code == 401


class TestAdminGrantSecurity:
    """Test admin grant amount validation at endpoint level."""

    def test_admin_grant_negative_amount_400(self, test_app, monkeypatch):
        import main as main_mod
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "test-key")
        res = test_app.post("/admin/grant?wallet_id=test-wallet&amount=-50",
                            headers={"Authorization": "Bearer test-key"})
        assert res.status_code == 400

    def test_admin_grant_zero_amount_400(self, test_app, monkeypatch):
        import main as main_mod
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "test-key")
        res = test_app.post("/admin/grant?wallet_id=test-wallet&amount=0",
                            headers={"Authorization": "Bearer test-key"})
        assert res.status_code == 400

    def test_admin_grant_huge_amount_400(self, test_app, monkeypatch):
        import main as main_mod
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "test-key")
        res = test_app.post(f"/admin/grant?wallet_id=test-wallet&amount={config.MAX_TOKEN_BALANCE + 1}",
                            headers={"Authorization": "Bearer test-key"})
        assert res.status_code == 400


class TestAnswerStrippingAllEndpoints:
    """Answers must never leak from any quiz endpoint."""

    def test_get_quiz_strips_answers(self, test_app):
        from main import quizzes, quiz_timestamps
        import time as _time
        qid = "strip-test-get"
        quizzes[qid] = {
            "quiz_title": "Test",
            "questions": [{"id": "q1", "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 2}],
        }
        quiz_timestamps[qid] = _time.time()
        res = test_app.get(f"/quiz/{qid}")
        assert res.status_code == 200
        for q in res.json()["questions"]:
            assert "answer_index" not in q
        del quizzes[qid]
        del quiz_timestamps[qid]

    def test_import_quiz_keeps_answers_for_private_review(self, test_app):
        quiz_data = {
            "quiz_title": "Imported",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0}],
        }
        res = test_app.post("/quiz/import", json={"quiz": quiz_data})
        assert res.status_code == 200
        assert res.json()["quiz"]["questions"][0]["answer_index"] == 0


class TestContentMutationAuth:
    """Content mutation endpoints require authentication."""

    def test_update_quiz_no_auth_401(self, test_app, monkeypatch):
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "")
        res = test_app.put("/quiz/nonexistent", json={
            "quiz_title": "X",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B"], "answer_index": 0}],
        })
        assert res.status_code == 401

    def test_delete_question_no_auth_401(self, test_app, monkeypatch):
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "")
        res = test_app.delete("/quiz/nonexistent/question/1")
        assert res.status_code == 401

    def test_import_quiz_no_auth_401(self, test_app, monkeypatch):
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "")
        quiz_data = {
            "quiz_title": "Test",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B"], "answer_index": 0}],
        }
        res = test_app.post("/quiz/import", json={"quiz": quiz_data})
        assert res.status_code == 401

    def test_import_mlt_no_auth_401(self, test_app, monkeypatch):
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "")
        mlt_data = {
            "game_title": "Test",
            "statements": [{"id": 1, "text": "S?"}],
        }
        res = test_app.post("/mlt/import", json={"game": mlt_data})
        assert res.status_code == 401


class TestSystemInfoProtection:
    """System info endpoint should be protected when admin key is set."""

    def test_system_info_protected_when_admin_key_set(self, test_app, monkeypatch):
        import main as main_mod
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "test-admin-key-1234567890")
        res = test_app.get("/system/info")
        assert res.status_code == 403

    def test_system_info_accessible_with_admin_key(self, test_app, monkeypatch):
        import main as main_mod
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "test-admin-key-1234567890")
        res = test_app.get("/system/info", headers={"Authorization": "Bearer test-admin-key-1234567890"})
        assert res.status_code == 200
        assert "ip" in res.json()

    def test_system_info_blocked_when_no_admin_key(self, test_app, monkeypatch):
        import main as main_mod
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "")
        res = test_app.get("/system/info")
        assert res.status_code == 403


class TestSecretStrengthCheck:
    """Startup secret validation should warn on weak secrets."""

    def test_warns_short_jwt_secret(self, monkeypatch):
        from main import _check_secret_strength
        import main as main_mod
        monkeypatch.setattr(config, "JWT_SECRET", "tooshort")
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "")
        monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
        warnings = _check_secret_strength()
        assert any("JWT_SECRET" in w for w in warnings)

    def test_warns_short_admin_key(self, monkeypatch):
        from main import _check_secret_strength
        import main as main_mod
        monkeypatch.setattr(config, "JWT_SECRET", "")
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "short")
        monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
        warnings = _check_secret_strength()
        assert any("ADMIN_API_KEY" in w for w in warnings)

    def test_no_warnings_when_unset(self, monkeypatch):
        from main import _check_secret_strength
        import main as main_mod
        monkeypatch.setattr(config, "JWT_SECRET", "")
        monkeypatch.setattr(main_mod, "ADMIN_API_KEY", "")
        monkeypatch.setattr(config, "STRIPE_WEBHOOK_SECRET", "")
        warnings = _check_secret_strength()
        assert len(warnings) == 0


class TestLLMBudget:
    """Global LLM budget should cap total calls."""

    def test_budget_rejects_when_exhausted(self, monkeypatch):
        from main import _check_llm_budget, _llm_call_timestamps
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_HOUR", 3)
        _llm_call_timestamps.clear()
        assert _check_llm_budget() is True
        assert _check_llm_budget() is True
        assert _check_llm_budget() is True
        assert _check_llm_budget() is False

    def test_budget_unlimited_when_zero(self, monkeypatch):
        from main import _check_llm_budget, _llm_call_timestamps
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_HOUR", 0)
        _llm_call_timestamps.clear()
        for _ in range(100):
            assert _check_llm_budget() is True

    def test_budget_prunes_old_entries(self, monkeypatch):
        import time as _time
        from main import _check_llm_budget, _llm_call_timestamps
        monkeypatch.setattr(config, "MAX_LLM_CALLS_PER_HOUR", 2)
        _llm_call_timestamps.clear()
        _llm_call_timestamps.append(_time.time() - 7200)
        _llm_call_timestamps.append(_time.time() - 7200)
        assert _check_llm_budget() is True


class TestHistoryScoping:
    """History endpoints should only return the requesting wallet's games."""

    def test_history_scoped_to_wallet(self, test_app, monkeypatch):
        from main import game_history
        game_history.clear()
        game_history.append({"room_code": "AAAA", "wallet_id": "wallet-a", "game_title": "A"})
        game_history.append({"room_code": "BBBB", "wallet_id": "wallet-b", "game_title": "B"})
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "wallet-a")
        res = test_app.get("/history")
        assert res.status_code == 200
        assert len(res.json()["games"]) == 1
        assert res.json()["games"][0]["room_code"] == "AAAA"
        game_history.clear()

    def test_history_detail_403_for_other_wallet(self, test_app, monkeypatch):
        from main import game_history
        game_history.clear()
        game_history.append({"room_code": "CCCC", "wallet_id": "wallet-c", "game_title": "C"})
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "wallet-d")
        res = test_app.get("/history/CCCC")
        assert res.status_code == 403
        game_history.clear()


# ---------------------------------------------------------------------------
# JWT exp field type
# ---------------------------------------------------------------------------

class TestJwtExpField:
    """JWT exp must be an integer timestamp, not a datetime object."""

    def test_session_token_exp_is_int(self):
        import jwt as pyjwt
        token = auth.create_session_token("user-1", "dev-1")
        payload = pyjwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        assert isinstance(payload["exp"], (int, float))
        assert isinstance(payload["iat"], (int, float))
        assert payload["exp"] > payload["iat"]

    def test_session_token_roundtrip(self):
        token = auth.create_session_token("user-roundtrip", "dev-roundtrip")
        result = auth.verify_session_token(token)
        assert result is not None
        assert result["user_id"] == "user-roundtrip"
        assert result["device_id"] == "dev-roundtrip"


# ---------------------------------------------------------------------------
# Content ownership enforcement
# ---------------------------------------------------------------------------

class TestContentOwnership:
    """Content can only be modified by its creator."""

    def test_quiz_update_by_owner(self, test_app, monkeypatch):
        from main import quizzes, content_owners
        import tokens as tokens_mod
        qid = "owner-test-quiz"
        quizzes[qid] = {
            "quiz_title": "Owned Quiz",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0, "image_prompt": "t"}],
        }
        content_owners[qid] = "wallet-owner"
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "wallet-owner")
        res = test_app.put(f"/quiz/{qid}", json={
            "quiz_title": "Updated",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0}],
        })
        assert res.status_code == 200
        quizzes.pop(qid, None)
        content_owners.pop(qid, None)

    def test_quiz_update_by_non_owner_rejected(self, test_app, monkeypatch):
        from main import quizzes, content_owners
        import tokens as tokens_mod
        qid = "owner-test-quiz-2"
        quizzes[qid] = {
            "quiz_title": "Owned Quiz",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0, "image_prompt": "t"}],
        }
        content_owners[qid] = "wallet-owner"
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "wallet-attacker")
        res = test_app.put(f"/quiz/{qid}", json={
            "quiz_title": "Hacked",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0}],
        })
        assert res.status_code == 403
        quizzes.pop(qid, None)
        content_owners.pop(qid, None)

    def test_quiz_delete_question_by_non_owner_rejected(self, test_app, monkeypatch):
        from main import quizzes, content_owners
        import tokens as tokens_mod
        qid = "owner-test-quiz-3"
        quizzes[qid] = {
            "quiz_title": "Owned",
            "questions": [
                {"id": 1, "text": "Q1?", "options": ["A", "B", "C", "D"], "answer_index": 0},
                {"id": 2, "text": "Q2?", "options": ["A", "B", "C", "D"], "answer_index": 1},
            ],
        }
        content_owners[qid] = "wallet-owner"
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "wallet-attacker")
        res = test_app.delete(f"/quiz/{qid}/question/1")
        assert res.status_code == 403
        quizzes.pop(qid, None)
        content_owners.pop(qid, None)

    def test_quiz_export_by_non_owner_rejected(self, test_app, monkeypatch):
        from main import quizzes, content_owners
        import tokens as tokens_mod
        qid = "owner-test-quiz-4"
        quizzes[qid] = {
            "quiz_title": "Owned",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0}],
        }
        content_owners[qid] = "wallet-owner"
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "wallet-attacker")
        res = test_app.get(f"/quiz/{qid}/export")
        assert res.status_code == 403
        quizzes.pop(qid, None)
        content_owners.pop(qid, None)

    def test_mlt_update_by_non_owner_rejected(self, test_app, monkeypatch):
        from main import mlt_scenarios, content_owners
        import tokens as tokens_mod
        sid = "owner-test-mlt"
        mlt_scenarios[sid] = {
            "game_title": "Owned MLT",
            "statements": [{"id": 1, "text": "Most likely to X"}],
        }
        content_owners[sid] = "wallet-owner"
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "wallet-attacker")
        res = test_app.put(f"/mlt/{sid}", json={
            "game_title": "Hacked",
            "statements": [{"id": 1, "text": "Hacked statement"}],
        })
        assert res.status_code == 403
        mlt_scenarios.pop(sid, None)
        content_owners.pop(sid, None)

    def test_unowned_content_still_editable(self, test_app, monkeypatch):
        """Content without an owner (e.g. seeded in tests) can be edited by anyone."""
        from main import quizzes, content_owners
        import tokens as tokens_mod
        qid = "no-owner-quiz"
        quizzes[qid] = {
            "quiz_title": "Unowned",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0, "image_prompt": "t"}],
        }
        # No entry in content_owners
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "any-wallet")
        res = test_app.put(f"/quiz/{qid}", json={
            "quiz_title": "Updated",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0}],
        })
        assert res.status_code == 200
        quizzes.pop(qid, None)
        content_owners.pop(qid, None)


# ---------------------------------------------------------------------------
# Webhook dedupe in DB
# ---------------------------------------------------------------------------

class TestWebhookDedupe:
    """Webhook event deduplication should be durable in the database."""

    def test_new_event_not_processed(self):
        assert not db.is_webhook_event_processed("evt_test_123")

    def test_mark_and_check_processed(self):
        db.mark_webhook_event_processed("evt_test_456")
        assert db.is_webhook_event_processed("evt_test_456")

    def test_duplicate_mark_is_idempotent(self):
        db.mark_webhook_event_processed("evt_test_789")
        db.mark_webhook_event_processed("evt_test_789")  # no error
        assert db.is_webhook_event_processed("evt_test_789")


# ---------------------------------------------------------------------------
# Refund incremental debit tracking
# ---------------------------------------------------------------------------

class TestRefundIncrementalDebit:
    """Partial refunds should track prior debits to prevent double-debiting."""

    def test_no_prior_debits(self):
        assert db.get_refund_debits_for_session("ses_no_refund") == 0

    def test_tracks_refund_debits(self):
        wallet_id = "refund-test-wallet"
        db.get_or_create_wallet(wallet_id, signup_bonus=False)
        db.credit_tokens(wallet_id, 200, "purchase", "ses_refund_1")
        db.debit_tokens(wallet_id, 50, "refund", "ses_refund_1")
        assert db.get_refund_debits_for_session("ses_refund_1") == 50
        # Second partial refund
        db.debit_tokens(wallet_id, 30, "refund", "ses_refund_1")
        assert db.get_refund_debits_for_session("ses_refund_1") == 80

    def test_does_not_count_non_refund_debits(self):
        wallet_id = "refund-test-wallet-2"
        db.get_or_create_wallet(wallet_id, signup_bonus=False)
        db.credit_tokens(wallet_id, 200, "purchase", "ses_refund_2")
        db.debit_tokens(wallet_id, 10, "spend_room", "ses_refund_2")
        assert db.get_refund_debits_for_session("ses_refund_2") == 0


# ---------------------------------------------------------------------------
# History migration on signin
# ---------------------------------------------------------------------------

class TestHistoryMergeOnSignin:
    """Game history wallet_id should be updated when device merges to user."""

    def test_history_migrated_on_signin(self, test_app, monkeypatch):
        from main import game_history
        game_history.clear()
        game_history.append({"room_code": "HIST1", "wallet_id": _DEVICE_ID, "game_title": "Pre-signin game"})

        # Mock auth.signin to return a fake user
        import auth as auth_mod
        fake_result = {
            "user": {"id": "user-merged-123", "provider": "google", "email": "t@t.com"},
            "session_token": "fake-token",
        }
        monkeypatch.setattr(auth_mod, "signin", lambda p, t, d: fake_result)
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_device_id", lambda req: _DEVICE_ID)

        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "fake-id-token",
            "device_id": _DEVICE_ID,
        }, headers=_DEVICE_HEADERS)
        assert res.status_code == 200

        # History should now be under user wallet
        assert game_history[0]["wallet_id"] == "user-merged-123"
        game_history.clear()

    def test_history_not_migrated_for_other_devices(self, test_app, monkeypatch):
        from main import game_history
        game_history.clear()
        game_history.append({"room_code": "HIST2", "wallet_id": "other-device-id", "game_title": "Other game"})

        import auth as auth_mod
        fake_result = {
            "user": {"id": "user-merged-456", "provider": "google", "email": "t@t.com"},
            "session_token": "fake-token",
        }
        monkeypatch.setattr(auth_mod, "signin", lambda p, t, d: fake_result)
        import tokens as tokens_mod
        monkeypatch.setattr(tokens_mod, "get_device_id", lambda req: _DEVICE_ID)

        res = test_app.post("/auth/signin", json={
            "provider": "google",
            "id_token": "fake-id-token",
            "device_id": _DEVICE_ID,
        }, headers=_DEVICE_HEADERS)
        assert res.status_code == 200

        # Other device's history should be untouched
        assert game_history[0]["wallet_id"] == "other-device-id"
        game_history.clear()
