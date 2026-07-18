"""Tests for in-app account deletion (SPEC-ACCOUNT-DELETION).

Required by App Store Review Guideline 5.1.1(v). The two cases that matter most here are the
ones the spec flags as most likely to silently regress:
  * a live session JWT must NOT resurrect a deleted account (§2) — JWTs are stateless and
    outlive deletion, and get_or_create_wallet would otherwise re-mint the wallet *with a
    fresh signup bonus*, making deletion cosmetic and farmable;
  * a late refund/purchase webhook must NOT recreate the user (§4.3).
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import auth
import config
import db
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret-for-account-deletion")
    db.init_db()
    conn = db._get_conn()
    for table in ("wallets", "token_transactions", "users", "deleted_accounts",
                  "generated_content", "entitlements", "device_usage"):
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    yield


def _signed_in_user(balance: int = 0):
    """Create a user + their wallet (wallet id == user id, per tokens.get_wallet_id)."""
    user_id = str(uuid.uuid4())
    device_id = f"dev-{uuid.uuid4()}"
    conn = db._get_conn()
    conn.execute(
        "INSERT INTO users (id, provider, provider_subject_id, email, created_at) "
        "VALUES (?, 'google', ?, ?, 0)",
        (user_id, f"sub-{user_id}", f"{user_id}@example.com"),
    )
    conn.commit()
    db.get_or_create_wallet(user_id, signup_bonus=False)
    if balance:
        db.credit_tokens(user_id, balance, reason="test_seed")
    token = auth.create_session_token(user_id, device_id)
    return user_id, device_id, {"X-Session-Token": token, "X-Device-Id": device_id}


class TestEndpointContract:
    def test_deletes_account_and_returns_ok(self):
        user_id, _, headers = _signed_in_user(balance=240)
        res = client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)
        assert res.status_code == 200
        assert res.json() == {"deleted": True}
        assert db.get_user(user_id) is None

    def test_requires_confirmation_string(self):
        user_id, _, headers = _signed_in_user()
        res = client.request("DELETE", "/account", json={"confirm": "yes"}, headers=headers)
        assert res.status_code == 400
        assert db.get_user(user_id) is not None, "account must survive an unconfirmed call"

    def test_missing_confirmation_does_not_delete(self):
        user_id, _, headers = _signed_in_user()
        res = client.request("DELETE", "/account", json={}, headers=headers)
        assert res.status_code == 400
        assert db.get_user(user_id) is not None

    def test_requires_a_session(self):
        res = client.request("DELETE", "/account", json={"confirm": "DELETE"})
        assert res.status_code == 401

    def test_second_delete_is_410_not_500(self):
        """Idempotent by contract: the client may retry on a flaky connection."""
        _, _, headers = _signed_in_user()
        assert client.request("DELETE", "/account", json={"confirm": "DELETE"},
                              headers=headers).status_code == 200
        again = client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)
        # The stale session now reads as signed-out, so 401 or 410 are both correct; a 500 is not.
        assert again.status_code in (401, 410)


class TestDataRemoval:
    def test_removes_pii_wallet_and_content(self):
        user_id, _, headers = _signed_in_user(balance=100)
        conn = db._get_conn()
        conn.execute(
            "INSERT INTO generated_content (id, wallet_id, content_type, title, payload, created_at) "
            "VALUES (?, ?, 'quiz', 'My Quiz', '{}', 0)",
            (str(uuid.uuid4()), user_id),
        )
        conn.commit()

        client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)

        assert db.get_user(user_id) is None, "PII (email) must be gone"
        assert conn.execute("SELECT 1 FROM wallets WHERE id = ?", (user_id,)).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM generated_content WHERE wallet_id = ?", (user_id,)
        ).fetchone() is None

    def test_retains_transaction_ledger(self):
        """Deliberate, disclosed exception (§3): financial record + idempotency guard.

        The ledger is pseudonymous once `users` is gone — its only identifier is a random UUID.
        """
        user_id, _, headers = _signed_in_user(balance=50)
        client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)
        rows = db._get_conn().execute(
            "SELECT 1 FROM token_transactions WHERE wallet_id = ?", (user_id,)
        ).fetchall()
        assert rows, "purchase/spend ledger is retained on purpose — see SPEC §3"


class TestNoResurrection:
    """§2 — the whole reason the denylist exists."""

    def test_live_session_token_cannot_resurrect_the_account(self):
        user_id, _, headers = _signed_in_user(balance=500)
        client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)

        # Same still-valid JWT, used again straight after deletion.
        res = client.get("/tokens/balance", headers=headers)
        assert res.status_code == 200, "should degrade to guest, not error"

        conn = db._get_conn()
        assert conn.execute("SELECT 1 FROM wallets WHERE id = ?", (user_id,)).fetchone() is None, \
            "the deleted user's wallet must NOT be re-created"
        assert db.get_user(user_id) is None

    def test_no_second_signup_bonus_for_a_deleted_id(self):
        """The farmable version of the bug: delete, reuse token, collect another bonus."""
        user_id, _, headers = _signed_in_user()
        client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)
        with pytest.raises(db.AccountDeletedError):
            db.get_or_create_wallet(user_id, signup_bonus=True)

    def test_session_for_deleted_user_reads_as_signed_out(self):
        _, _, headers = _signed_in_user()
        client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)
        assert client.get("/auth/me", headers=headers).status_code == 401

    def test_denylist_survives_and_is_queryable(self):
        user_id, _, headers = _signed_in_user()
        assert db.is_account_deleted(user_id) is False
        client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)
        assert db.is_account_deleted(user_id) is True


class TestLateWebhook:
    """§4.3 — a refund or delayed purchase arriving after deletion must not undo it."""

    def test_late_credit_does_not_recreate_the_user(self):
        user_id, _, headers = _signed_in_user()
        client.request("DELETE", "/account", json={"confirm": "DELETE"}, headers=headers)

        try:
            db.credit_purchase(user_id, 200, reference_id=f"iap:APP_STORE:{uuid.uuid4()}")
        except db.AccountDeletedError:
            pass  # refusing outright is also acceptable

        assert db.get_user(user_id) is None, "a late webhook must never resurrect PII"
        assert db._get_conn().execute(
            "SELECT 1 FROM wallets WHERE id = ?", (user_id,)
        ).fetchone() is None
