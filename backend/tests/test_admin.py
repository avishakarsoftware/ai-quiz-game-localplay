"""Tests for admin endpoints: lookup, revoke, grant (device + user-scoped)."""
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
# Lookup
# ============================================================================

class TestAdminLookup:
    def test_lookup_by_device(self, client):
        db.create_entitlement("ent-1", _DEVICE_ID)
        resp = client.get("/admin/lookup", params={"device_id": _DEVICE_ID},
                          headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_id"] == _DEVICE_ID
        assert len(data["entitlements"]) == 1

    def test_lookup_by_entitlement_id(self, client):
        db.create_entitlement("ent-2", _DEVICE_ID)
        resp = client.get("/admin/lookup", params={"entitlement_id": "ent-2"},
                          headers=admin_headers())
        assert resp.status_code == 200
        assert resp.json()["id"] == "ent-2"

    def test_lookup_entitlement_not_found(self, client):
        resp = client.get("/admin/lookup", params={"entitlement_id": "nonexistent"},
                          headers=admin_headers())
        assert resp.status_code == 404

    def test_lookup_by_user_id(self, client):
        user = db.find_or_create_user("google", "sub-123", "test@example.com")
        db.create_entitlement("ent-u1", _DEVICE_ID, user_id=user["id"])
        resp = client.get("/admin/lookup", params={"user_id": user["id"]},
                          headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"]["id"] == user["id"]
        assert len(data["entitlements"]) == 1
        assert _DEVICE_ID in data["devices"]

    def test_lookup_by_user_id_not_found(self, client):
        resp = client.get("/admin/lookup", params={"user_id": "nonexistent"},
                          headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"] is None
        assert data["entitlements"] == []

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
# Revoke
# ============================================================================

class TestAdminRevoke:
    def test_revoke_entitlement(self, client):
        db.create_entitlement("ent-r1", _DEVICE_ID)
        resp = client.post("/admin/revoke", params={"entitlement_id": "ent-r1"},
                           headers=admin_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"
        ent = db.lookup_entitlement("ent-r1")
        assert ent["status"] == "revoked_refunded"

    def test_revoke_nonexistent_returns_404(self, client):
        resp = client.post("/admin/revoke", params={"entitlement_id": "nope"},
                           headers=admin_headers())
        assert resp.status_code == 404


# ============================================================================
# Grant
# ============================================================================

class TestAdminGrant:
    def test_grant_to_device(self, client):
        resp = client.post("/admin/grant", params={"device_id": _DEVICE_ID, "games": 10, "hours": 6},
                           headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "granted"
        assert data["games"] == 10
        assert data["hours"] == 6
        assert data["device_id"] == _DEVICE_ID
        # Verify in db
        ent = db.lookup_entitlement(data["entitlement_id"])
        assert ent["games_remaining"] == 10
        assert ent["device_id"] == _DEVICE_ID
        assert ent["user_id"] is None

    def test_grant_to_user(self, client):
        user = db.find_or_create_user("google", "sub-grant", "grant@example.com")
        resp = client.post("/admin/grant", params={"user_id": user["id"], "games": 25},
                           headers=admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == user["id"]
        assert data["device_id"] == "admin-grant"
        # Verify user can use it
        ent = db.get_active_entitlement_for_user(user["id"])
        assert ent is not None
        assert ent["games_remaining"] == 25

    def test_grant_to_user_and_device(self, client):
        user = db.find_or_create_user("apple", "sub-both", "both@example.com")
        resp = client.post("/admin/grant",
                           params={"user_id": user["id"], "device_id": _DEVICE_ID_2},
                           headers=admin_headers())
        assert resp.status_code == 200
        ent = db.lookup_entitlement(resp.json()["entitlement_id"])
        assert ent["user_id"] == user["id"]
        assert ent["device_id"] == _DEVICE_ID_2

    def test_grant_to_nonexistent_user_returns_404(self, client):
        resp = client.post("/admin/grant", params={"user_id": "fake-user-id"},
                           headers=admin_headers())
        assert resp.status_code == 404

    def test_grant_no_params_returns_400(self, client):
        resp = client.post("/admin/grant", headers=admin_headers())
        assert resp.status_code == 400


# ============================================================================
# Round 2 bug fixes
# ============================================================================

class TestRound2BugFixes:
    """Tests for bugs found in Round 2 review."""

    def test_checkout_without_session_no_user_id(self, monkeypatch):
        """Checkout by guest should create entitlement with user_id=None."""
        import auth as auth_mod
        import main
        monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_fake")
        monkeypatch.setattr(config, "STRIPE_PRICE_ID", "price_fake")
        monkeypatch.setattr(auth_mod, "get_session_from_request", lambda req: None)

        from unittest.mock import MagicMock, patch
        mock_session = MagicMock()
        mock_session.id = "sess_guest_456"
        mock_session.url = "https://checkout.stripe.com/test"
        with patch("stripe.checkout.Session.create", return_value=mock_session):
            c = TestClient(main.app)
            resp = c.post("/checkout/create",
                          json={"device_id": _DEVICE_ID},
                          headers={"X-Device-Id": _DEVICE_ID})
        assert resp.status_code == 200
        ent = db.get_entitlement_by_stripe_session("sess_guest_456")
        assert ent is not None
        assert ent["user_id"] is None

    def test_revoke_expired_entitlement_succeeds(self):
        """admin_revoke should work on expired_time entitlements."""
        conn = db._get_conn()
        now = int(time.time())
        conn.execute(
            "INSERT INTO entitlements (id, device_id, status, games_remaining, expires_at, created_at) "
            "VALUES (?, ?, 'expired_time', 0, ?, ?)",
            ("ent-exp", _DEVICE_ID, now - 100, now - 1000),
        )
        conn.commit()
        assert db.admin_revoke("ent-exp")
        assert db.lookup_entitlement("ent-exp")["status"] == "revoked_refunded"

    def test_revoke_exhausted_entitlement_succeeds(self):
        """admin_revoke should work on exhausted_games entitlements."""
        conn = db._get_conn()
        now = int(time.time())
        conn.execute(
            "INSERT INTO entitlements (id, device_id, status, games_remaining, expires_at, created_at) "
            "VALUES (?, ?, 'exhausted_games', 0, ?, ?)",
            ("ent-exh", _DEVICE_ID, now + 1000, now),
        )
        conn.commit()
        assert db.admin_revoke("ent-exh")
        assert db.lookup_entitlement("ent-exh")["status"] == "revoked_refunded"

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
# db-level admin functions
# ============================================================================

class TestDbAdminFunctions:
    def test_lookup_by_user_multiple_devices(self):
        user = db.find_or_create_user("google", "sub-multi", "multi@example.com")
        db.create_entitlement("ent-d1", _DEVICE_ID, user_id=user["id"])
        db.create_entitlement("ent-d2", _DEVICE_ID_2, user_id=user["id"])
        result = db.lookup_by_user(user["id"])
        assert len(result["entitlements"]) == 2
        assert set(result["devices"]) == {_DEVICE_ID, _DEVICE_ID_2}

    def test_lookup_user_by_email_partial_match(self):
        db.find_or_create_user("google", "sub-a", "john.doe@gmail.com")
        db.find_or_create_user("google", "sub-b", "john.smith@outlook.com")
        db.find_or_create_user("google", "sub-c", "alice@gmail.com")
        results = db.lookup_user_by_email("john")
        assert len(results) == 2

    def test_lookup_user_by_email_no_match(self):
        results = db.lookup_user_by_email("zzz_nonexistent")
        assert results == []

    def test_admin_grant_with_user_id(self):
        user = db.find_or_create_user("apple", "sub-grant2", "g2@example.com")
        eid = db.admin_grant(_DEVICE_ID, games=10, hours=2, user_id=user["id"])
        ent = db.lookup_entitlement(eid)
        assert ent["user_id"] == user["id"]
        assert ent["device_id"] == _DEVICE_ID
        assert ent["games_remaining"] == 10


# ============================================================================
# Round 1 bug fixes
# ============================================================================

class TestRound1BugFixes:
    """Tests for bugs found in Round 1 review."""

    def test_revoke_pending_entitlement_fails(self):
        """admin_revoke should NOT revoke pending_payment entitlements."""
        db.create_entitlement("ent-pending", _DEVICE_ID, stripe_session_id="sess_123", status="pending_payment")
        assert not db.admin_revoke("ent-pending")
        ent = db.lookup_entitlement("ent-pending")
        assert ent["status"] == "pending_payment"  # unchanged

    def test_revoke_active_entitlement_succeeds(self):
        db.create_entitlement("ent-active", _DEVICE_ID)
        assert db.admin_revoke("ent-active")
        ent = db.lookup_entitlement("ent-active")
        assert ent["status"] == "revoked_refunded"

    def test_revoke_already_revoked_fails(self):
        db.create_entitlement("ent-rev", _DEVICE_ID)
        assert db.admin_revoke("ent-rev")
        assert not db.admin_revoke("ent-rev")  # already revoked

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

    def test_get_active_entitlement_device_only(self):
        """get_active_entitlement should only return device-scoped (user_id IS NULL) entitlements."""
        user = db.find_or_create_user("google", "sub-dev", "dev@example.com")
        # Create user-scoped entitlement
        db.create_entitlement("ent-user", _DEVICE_ID, user_id=user["id"])
        # Should NOT be returned by device-only lookup
        assert db.get_active_entitlement(_DEVICE_ID) is None
        # Create device-only entitlement
        db.create_entitlement("ent-device", _DEVICE_ID)
        assert db.get_active_entitlement(_DEVICE_ID) is not None

    def test_checkout_links_entitlement_to_user(self, client, monkeypatch):
        """Checkout should link entitlement to signed-in user."""
        import auth as auth_mod
        user = db.find_or_create_user("google", "sub-checkout", "checkout@example.com")
        monkeypatch.setattr(config, "STRIPE_SECRET_KEY", "sk_test_fake")
        monkeypatch.setattr(config, "STRIPE_PRICE_ID", "price_fake")
        # Mock session to simulate signed-in user
        monkeypatch.setattr(auth_mod, "get_session_from_request",
                            lambda req: {"user_id": user["id"], "device_id": _DEVICE_ID})

        from unittest.mock import MagicMock, patch
        mock_session = MagicMock()
        mock_session.id = "sess_test_123"
        mock_session.url = "https://checkout.stripe.com/test"
        with patch("stripe.checkout.Session.create", return_value=mock_session):
            from main import app
            from fastapi.testclient import TestClient
            c = TestClient(app)
            resp = c.post("/checkout/create",
                          json={"device_id": _DEVICE_ID},
                          headers={"X-Device-Id": _DEVICE_ID})
        assert resp.status_code == 200
        # Verify the pending entitlement is linked to user
        ent = db.get_entitlement_by_stripe_session("sess_test_123")
        assert ent is not None
        assert ent["user_id"] == user["id"]


# ============================================================================
# Round 3 bug fixes
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
