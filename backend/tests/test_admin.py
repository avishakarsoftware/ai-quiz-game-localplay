"""Tests for admin endpoints: lookup, grant (token-based)."""
import sys
import os
import time
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import db
import config
from fastapi.testclient import TestClient


_DEVICE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_DEVICE_ID_2 = "aaaaaaaa-bbbb-cccc-dddd-ffffffffffff"
_ADMIN_KEY = "test-admin-key-1234"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Each test gets a fresh database."""
    import threading
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret-key-for-admin-tests-32bytes!")
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "revelry.db"))
    db.init_db()
    yield


@pytest.fixture
def client(monkeypatch):
    """Test client with admin key configured."""
    import main
    monkeypatch.setattr(main, "ADMIN_API_KEY", _ADMIN_KEY)
    return TestClient(main.app)


def admin_headers():
    return {"Authorization": f"Bearer {_ADMIN_KEY}"}


# ============================================================================
# Auth / access control
# ============================================================================

class TestAdminAuth:
    def test_no_admin_key_configured_returns_503(self, monkeypatch):
        import main
        monkeypatch.setattr(main, "ADMIN_API_KEY", "")
        c = TestClient(main.app)
        resp = c.get("/admin/lookup", params={"device_id": _DEVICE_ID})
        assert resp.status_code == 503

    def test_wrong_key_returns_403(self, client):
        resp = client.get("/admin/lookup", params={"device_id": _DEVICE_ID},
                          headers={"Authorization": "Bearer wrong-key"})
        assert resp.status_code == 403

    def test_missing_header_returns_403(self, client):
        resp = client.get("/admin/lookup", params={"device_id": _DEVICE_ID})
        assert resp.status_code == 403

    def test_correct_key_passes(self, client):
        resp = client.get("/admin/lookup", params={"device_id": _DEVICE_ID},
                          headers=admin_headers())
        assert resp.status_code == 200


# ============================================================================
# Lookup (token-based)
# ============================================================================

class TestAdminLookup:
    def test_lookup_by_wallet_id(self, client):
        """Lookup by wallet_id returns wallet info."""
        db.get_or_create_wallet(_DEVICE_ID, signup_bonus=True)
        resp = client.get("/admin/lookup", params={"wallet_id": _DEVICE_ID},
                          headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "wallet" in data
        assert data["wallet"]["balance"] >= 0

    def test_lookup_by_wallet_id_not_found(self, client):
        resp = client.get("/admin/lookup", params={"wallet_id": "nonexistent-wallet"},
                          headers=admin_headers())
        assert resp.status_code == 404

    def test_lookup_by_device_id(self, client):
        resp = client.get("/admin/lookup", params={"device_id": _DEVICE_ID},
                          headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "wallet" in data
        assert "legacy" in data

    def test_lookup_by_user_id(self, client):
        user = db.find_or_create_user("google", "sub-123", "test@example.com")
        resp = client.get("/admin/lookup", params={"user_id": user["id"]},
                          headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert "wallet" in data
        assert "legacy" in data

    def test_lookup_by_email(self, client):
        db.find_or_create_user("google", "sub-456", "alice@example.com")
        db.find_or_create_user("apple", "sub-789", "alice.relay@privaterelay.appleid.com")
        resp = client.get("/admin/lookup", params={"email": "alice"},
                          headers=admin_headers())
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 2

    def test_lookup_by_email_not_found(self, client):
        resp = client.get("/admin/lookup", params={"email": "nobody@nowhere.com"},
                          headers=admin_headers())
        assert resp.status_code == 404

    def test_lookup_no_params_returns_400(self, client):
        resp = client.get("/admin/lookup", headers=admin_headers())
        assert resp.status_code == 400


# ============================================================================
# Grant (token-based)
# ============================================================================

class TestAdminGrant:
    def test_grant_to_device(self, client):
        resp = client.post("/admin/grant", params={"device_id": _DEVICE_ID, "amount": 100},
                           headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "granted"
        assert data["tokens_granted"] == 100
        assert data["wallet_id"] == _DEVICE_ID

    def test_grant_to_user(self, client):
        user = db.find_or_create_user("google", "sub-grant", "grant@example.com")
        resp = client.post("/admin/grant", params={"user_id": user["id"], "amount": 50},
                           headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["wallet_id"] == user["id"]
        assert data["tokens_granted"] == 50

    def test_grant_to_wallet_id(self, client):
        resp = client.post("/admin/grant", params={"wallet_id": _DEVICE_ID_2, "amount": 200},
                           headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["wallet_id"] == _DEVICE_ID_2
        assert data["tokens_granted"] == 200

    def test_grant_default_amount(self, client):
        resp = client.post("/admin/grant", params={"device_id": _DEVICE_ID},
                           headers=admin_headers())
        assert resp.status_code == 200
        assert resp.json()["tokens_granted"] == 110  # default amount

    def test_grant_no_params_returns_400(self, client):
        resp = client.post("/admin/grant", headers=admin_headers())
        assert resp.status_code == 400


# ============================================================================
# Round 2 bug fixes (still relevant)
# ============================================================================

class TestRound2BugFixes:
    """Tests for bugs found in Round 2 review."""

    def test_find_or_create_user_concurrent_safety(self):
        """find_or_create_user handles IntegrityError gracefully."""
        user1 = db.find_or_create_user("google", "sub-concurrent", "c@test.com")
        user2 = db.find_or_create_user("google", "sub-concurrent", "c@test.com")
        assert user1["id"] == user2["id"]

    def test_admin_auth_header_rename(self, client):
        """Verify _check_admin works correctly after auth_header variable rename."""
        resp = client.get("/admin/lookup", params={"device_id": _DEVICE_ID},
                          headers=admin_headers())
        assert resp.status_code == 200


# ============================================================================
# db-level admin functions (still relevant)
# ============================================================================

class TestDbAdminFunctions:
    def test_lookup_user_by_email_partial_match(self):
        db.find_or_create_user("google", "sub-a", "john.doe@gmail.com")
        db.find_or_create_user("google", "sub-b", "john.smith@outlook.com")
        db.find_or_create_user("google", "sub-c", "alice@gmail.com")
        results = db.lookup_user_by_email("john")
        assert len(results) == 2

    def test_lookup_user_by_email_no_match(self):
        results = db.lookup_user_by_email("zzz_nonexistent")
        assert results == []


# ============================================================================
# Round 1 bug fixes (still relevant, non-entitlement)
# ============================================================================

class TestRound1BugFixes:
    """Tests for bugs found in Round 1 review."""

    def test_lookup_email_with_wildcards(self):
        """LIKE wildcards in email search should be escaped."""
        db.find_or_create_user("google", "sub-wild", "test_user@gmail.com")
        db.find_or_create_user("google", "sub-other", "testXuser@gmail.com")
        # Searching for literal "_" should only match the underscore, not X
        results = db.lookup_user_by_email("test_user")
        assert len(results) == 1
        assert results[0]["email"] == "test_user@gmail.com"

    def test_lookup_email_with_percent(self):
        """Percent sign in email search should be treated literally."""
        db.find_or_create_user("google", "sub-pct", "user%100@gmail.com")
        db.find_or_create_user("google", "sub-normal", "user200@gmail.com")
        results = db.lookup_user_by_email("user%100")
        assert len(results) == 1


# ============================================================================
# Round 3 bug fixes (still relevant)
# ============================================================================

class TestRound3BugFixes:
    """Tests for bugs found in Round 3 review."""

    def test_find_or_create_user_returns_updated_email(self):
        """When email changes, returned dict should have the new email."""
        user1 = db.find_or_create_user("google", "sub-email", "old@example.com")
        assert user1["email"] == "old@example.com"
        user2 = db.find_or_create_user("google", "sub-email", "new@example.com")
        assert user2["email"] == "new@example.com"
        assert user2["id"] == user1["id"]
        # Also verify DB has new email
        db_user = db.get_user(user1["id"])
        assert db_user["email"] == "new@example.com"

    def test_create_session_token_no_secret_returns_none(self, monkeypatch):
        """create_session_token should return None if JWT_SECRET is empty."""
        import auth
        monkeypatch.setattr(config, "JWT_SECRET", "")
        token = auth.create_session_token("user-123", _DEVICE_ID)
        assert token is None

    def test_create_session_token_includes_iat(self):
        """Session tokens should include iat (issued-at) claim."""
        import auth
        import jwt as pyjwt
        token = auth.create_session_token("user-123", _DEVICE_ID)
        assert token is not None
        payload = pyjwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        assert "iat" in payload
        assert isinstance(payload["iat"], int)

    def test_signin_fails_with_no_secret(self, monkeypatch):
        """signin should fail gracefully if JWT_SECRET is empty."""
        import auth
        monkeypatch.setattr(config, "JWT_SECRET", "")
        monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "test-client-id")
        # Mock Google verification to succeed
        monkeypatch.setattr(auth, "verify_id_token",
                            lambda p, t: {"sub": "test-sub", "email": "t@t.com"})
        result = auth.signin("google", "fake-token", _DEVICE_ID)
        assert result is None  # Should fail because session token creation fails

    def test_restore_expired_returns_reason(self):
        """restore_purchases should return reason='expired' for expired IAP entitlements."""
        import main
        conn = db._get_conn()
        now = int(time.time())
        conn.execute(
            "INSERT INTO entitlements (id, device_id, status, games_remaining, expires_at, "
            "created_at, apple_transaction_id) VALUES (?, ?, 'expired_time', 0, ?, ?, ?)",
            ("ent-iap-exp", _DEVICE_ID, now - 100, now - 1000, "txn_123"),
        )
        conn.commit()
        c = TestClient(main.app)
        resp = c.post("/purchases/restore", headers={"X-Device-Id": _DEVICE_ID})
        assert resp.status_code == 200
        data = resp.json()
        assert data["restored"] is False
        assert data["reason"] == "expired"
