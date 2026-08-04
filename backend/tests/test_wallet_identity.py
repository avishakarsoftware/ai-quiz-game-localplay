"""L1/L2 tests for identity → wallet resolution and the token-verification guards.

`tokens.get_wallet_id` decides WHOSE sparks get spent on every paid action. conftest pins it to a
fixed test device for the whole suite, so the real implementation — the signed-in branch in
particular — was never executed by any test. Everything here exercises the real functions.
"""
import os
import sys
import threading
import uuid

import pytest
from starlette.requests import Request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import auth
import config
import db
import tokens as tokens_mod


DEVICE = "aaaaaaaa-9999-8888-7777-666666666666"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET", "test-secret-key-for-identity-tests-32b!")
    monkeypatch.setattr(db, "_local", threading.local())
    monkeypatch.setattr(db, "DB_DIR", str(tmp_path))
    monkeypatch.setattr(db, "DB_PATH", os.path.join(str(tmp_path), "revelry.db"))
    db.init_db()
    # Undo conftest's pin (it replaces get_wallet_id with a fixed device id for the whole suite)
    # so the REAL wallet resolution runs. Reload restores the module's own functions.
    import importlib
    importlib.reload(tokens_mod)
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def _req(**headers) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": raw})


def _signed_in_user(device_id: str = DEVICE) -> tuple[str, str]:
    """Create a user + session token as the real sign-in flow would."""
    user = db.find_or_create_user("google", f"sub_{uuid.uuid4().hex[:8]}", "u@example.com")
    return user["id"], auth.create_session_token(user["id"], device_id)


class TestPolymorphicWallet:
    """Signed in → the wallet is the user id; signed out → the device id. Getting this backwards
    means a signed-in user spends (or tops up) the wrong wallet: sparks appear to vanish when they
    sign in on a second device, and purchases land somewhere they cannot see."""

    def test_signed_in_request_resolves_to_the_user_wallet(self):
        user_id, token = _signed_in_user()
        resolved = tokens_mod.get_wallet_id(_req(**{"X-Session-Token": token, "X-Device-Id": DEVICE}))
        assert resolved == user_id

    def test_signed_out_request_resolves_to_the_device_wallet(self):
        assert tokens_mod.get_wallet_id(_req(**{"X-Device-Id": DEVICE})) == DEVICE

    def test_garbage_session_token_falls_back_to_the_device(self):
        """A corrupted/expired token must degrade to guest mode, not to an empty wallet id —
        an empty wallet id makes every paid endpoint answer 400 and the app looks broken."""
        resolved = tokens_mod.get_wallet_id(
            _req(**{"X-Session-Token": "not.a.jwt", "X-Device-Id": DEVICE}))
        assert resolved == DEVICE

    def test_non_uuid_device_id_resolves_to_nothing(self):
        """Free-text device ids must not become wallets — otherwise a caller can mint wallets
        (and signup bonuses) under any key it likes, e.g. "1"."""
        assert tokens_mod.get_wallet_id(_req(**{"X-Device-Id": "1"})) == ""
        assert tokens_mod.get_wallet_id(_req()) == ""

    def test_session_for_a_deleted_account_does_not_resurrect_the_wallet(self):
        """Session JWTs are stateless and outlive deletion. After deletion the held token must
        read as signed-out (App Store 5.1.1(v) — deletion has to actually stick)."""
        user_id, token = _signed_in_user()
        db.get_or_create_wallet(user_id, signup_bonus=False)
        db.delete_account(user_id)

        resolved = tokens_mod.get_wallet_id(_req(**{"X-Session-Token": token, "X-Device-Id": DEVICE}))

        assert resolved == DEVICE
        assert db.is_account_deleted(user_id) is True

    def test_balance_endpoint_reports_the_user_wallet_not_the_device_wallet(self, client):
        """End-to-end proof through HTTP: with both headers present, the signed-in user's balance
        wins. If the device wallet leaked through, a user could see (and spend) sparks belonging
        to whoever last used the device."""
        user_id, token = _signed_in_user()
        db.get_or_create_wallet(DEVICE, signup_bonus=False)
        db.credit_tokens(DEVICE, 7, "admin_grant")
        db.get_or_create_wallet(user_id, signup_bonus=False)
        db.credit_tokens(user_id, 42, "admin_grant")

        res = client.get("/tokens/balance",
                         headers={"X-Session-Token": token, "X-Device-Id": DEVICE})

        assert res.status_code == 200
        # /tokens/balance also grants the daily login bonus, so compare against the wallet the
        # endpoint actually touched rather than a hard-coded number.
        assert res.json()["balance"] == db.get_wallet_balance(user_id)
        assert res.json()["balance"] >= 42
        assert db.get_wallet_balance(DEVICE) == 7  # device wallet untouched

    def test_balance_without_any_identity_creates_no_wallet(self, client):
        """An anonymous probe must not create ledger rows — otherwise crawlers and health checks
        inflate wallet counts and hand out signup bonuses."""
        res = client.get("/tokens/balance")

        assert res.status_code == 200
        assert res.json()["balance"] == 0
        assert db._get_conn().execute("SELECT COUNT(*) c FROM wallets").fetchone()["c"] == 0


class TestIdempotencyKeyExtraction:
    """Gifting and other one-shot money moves are de-duplicated on this key."""

    def test_accepts_either_header_spelling(self):
        key = str(uuid.uuid4())
        assert tokens_mod.get_idempotency_key(_req(**{"X-Idempotency-Key": key})) == key
        assert tokens_mod.get_idempotency_key(_req(**{"Idempotency-Key": key})) == key

    def test_rejects_a_non_uuid_key(self):
        """A short, guessable key (e.g. "1") would let one caller's retry collide with another's
        first attempt, replaying a gift result that was never theirs."""
        assert tokens_mod.get_idempotency_key(_req(**{"X-Idempotency-Key": "1"})) == ""
        assert tokens_mod.get_idempotency_key(_req()) == ""


class TestSessionTokenGuards:
    def test_no_jwt_secret_means_no_valid_sessions(self, monkeypatch):
        """If JWT_SECRET is missing in an environment, verification must fail closed. Failing
        open would accept unsigned/foreign tokens as valid sign-ins."""
        token = auth.create_session_token("user-1", DEVICE)
        monkeypatch.setattr(config, "JWT_SECRET", "")
        assert auth.verify_session_token(token) is None
        assert auth.create_session_token("user-1", DEVICE) is None

    def test_token_signed_with_another_secret_is_rejected(self):
        import jwt as pyjwt
        forged = pyjwt.encode(
            {"user_id": "attacker", "device_id": DEVICE, "type": "session"},
            "some-other-secret-entirely", algorithm="HS256")
        assert auth.verify_session_token(forged) is None

    def test_none_algorithm_token_is_rejected(self):
        """The classic JWT bypass: an unsigned token claiming alg=none. Accepting it is full
        account takeover by user id."""
        import jwt as pyjwt
        unsigned = pyjwt.encode(
            {"user_id": "victim", "device_id": DEVICE, "type": "session"},
            key="", algorithm="none")
        assert auth.verify_session_token(unsigned) is None

    def test_non_string_ids_are_rejected(self):
        """A numeric or object user_id would flow into SQL/wallet keys as an unexpected type."""
        import jwt as pyjwt
        weird = pyjwt.encode({"user_id": 12345, "device_id": DEVICE, "type": "session"},
                             config.JWT_SECRET, algorithm="HS256")
        assert auth.verify_session_token(weird) is None

    def test_expired_token_is_rejected(self):
        import jwt as pyjwt
        expired = pyjwt.encode(
            {"user_id": "u1", "device_id": DEVICE, "type": "session", "exp": 1000000000},
            config.JWT_SECRET, algorithm="HS256")
        assert auth.verify_session_token(expired) is None


class TestIdTokenProviderRouting:
    def test_unknown_provider_is_never_verified(self):
        """verify_id_token is the only gate in front of find_or_create_user. If an unrecognised
        provider fell through to a truthy result, anyone could claim any identity."""
        assert auth.verify_id_token("microsoft", "whatever") is None
        assert auth.verify_id_token("", "whatever") is None
        assert auth.verify_id_token("GOOGLE", "whatever") is None  # case-sensitive by design

    def test_apple_provider_routes_to_apple_verifier(self, monkeypatch):
        called = {}

        def fake_apple(token):
            called["token"] = token
            return {"sub": "s"}

        monkeypatch.setattr(auth, "verify_apple_token", fake_apple)
        assert auth.verify_id_token("apple", "tok") == {"sub": "s"}
        assert called["token"] == "tok"


class TestGoogleTokenClaims:
    def test_wrong_issuer_is_rejected(self, monkeypatch):
        """A token minted by another IdP but audienced at us must not sign anyone in."""
        from unittest.mock import patch
        monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", ["client-1"])
        with patch("google.oauth2.id_token.verify_oauth2_token",
                   return_value={"iss": "https://evil.example.com", "sub": "s1",
                                 "email": "e@x.com"}):
            assert auth.verify_google_token("tok") is None

    def test_claims_without_subject_are_rejected(self, monkeypatch):
        """`sub` becomes the account's provider key. Without it we would create a user keyed on
        None — and every such sign-in would collide onto the same account."""
        from unittest.mock import patch
        monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", ["client-1"])
        with patch("google.oauth2.id_token.verify_oauth2_token",
                   return_value={"iss": "accounts.google.com", "email": "e@x.com"}):
            assert auth.verify_google_token("tok") is None

    def test_bare_issuer_form_is_accepted(self, monkeypatch):
        """Google issues both `accounts.google.com` and the https form; rejecting the bare form
        would lock out a slice of real users."""
        from unittest.mock import patch
        monkeypatch.setattr(config, "GOOGLE_CLIENT_IDS", ["client-1"])
        with patch("google.oauth2.id_token.verify_oauth2_token",
                   return_value={"iss": "accounts.google.com", "sub": "s1", "email": "e@x.com"}):
            assert auth.verify_google_token("tok") == {"sub": "s1", "email": "e@x.com"}


class TestAppleTokenClaims:
    def test_claims_without_subject_are_rejected(self, monkeypatch):
        from unittest.mock import patch
        monkeypatch.setattr(config, "APPLE_CLIENT_IDS", ["me.revelryapp.quiz"])
        monkeypatch.setattr(auth, "_get_apple_jwks_client",
                            lambda: type("C", (), {"get_signing_key_from_jwt":
                                                   lambda self, t: type("K", (), {"key": "k"})()})())
        with patch("auth.jwt.decode", return_value={"email": "a@example.com"}):
            assert auth.verify_apple_token("tok") is None

    def test_jwks_failure_is_a_rejection_not_a_crash(self, monkeypatch):
        """Apple's key endpoint being down must produce a clean "sign-in failed", not a 500 that
        the client cannot interpret."""
        def boom():
            raise RuntimeError("jwks unreachable")

        monkeypatch.setattr(config, "APPLE_CLIENT_IDS", ["me.revelryapp.quiz"])
        monkeypatch.setattr(auth, "_get_apple_jwks_client", boom)
        assert auth.verify_apple_token("tok") is None

    def test_signature_failure_is_a_rejection(self, monkeypatch):
        from unittest.mock import patch
        import jwt as pyjwt
        monkeypatch.setattr(config, "APPLE_CLIENT_IDS", ["me.revelryapp.quiz"])
        monkeypatch.setattr(auth, "_get_apple_jwks_client",
                            lambda: type("C", (), {"get_signing_key_from_jwt":
                                                   lambda self, t: type("K", (), {"key": "k"})()})())
        with patch("auth.jwt.decode", side_effect=pyjwt.InvalidSignatureError("bad sig")):
            assert auth.verify_apple_token("tok") is None


class TestAppleJwksClientIsCached:
    def test_client_is_created_once_and_reused(self, monkeypatch):
        """Apple rate-limits its JWKS endpoint. Building a fresh client per verification would
        re-fetch keys on every Apple sign-in and eventually lock all Apple users out. (Constructing
        PyJWKClient does not hit the network; only key lookup does.)"""
        monkeypatch.setattr(auth, "_apple_jwks_client", None)
        first = auth._get_apple_jwks_client()
        second = auth._get_apple_jwks_client()
        assert first is second


class TestSignInFlow:
    def test_signin_rejects_an_unverifiable_token(self, monkeypatch):
        monkeypatch.setattr(auth, "verify_id_token", lambda p, t: None)
        assert auth.signin("google", "tok", DEVICE) is None
        assert db._get_conn().execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0

    def test_signin_moves_device_sparks_to_the_user_wallet(self, monkeypatch):
        """The whole point of signing in is that your sparks follow you. Losing them here is the
        most visible possible money bug."""
        monkeypatch.setattr(auth, "verify_id_token",
                            lambda p, t: {"sub": "sub_merge_1", "email": "m@example.com"})
        db.get_or_create_wallet(DEVICE, signup_bonus=False)
        db.credit_tokens(DEVICE, 35, "admin_grant")

        result = auth.signin("google", "tok", DEVICE)

        assert result is not None
        user_id = result["user"]["id"]
        assert db.get_wallet_balance(user_id) == 35
        assert db.get_wallet_balance(DEVICE) == 0

    def test_signin_without_jwt_secret_fails_instead_of_half_signing_in(self, monkeypatch):
        """If we cannot mint a session there is no point creating one client-side: the app would
        show a signed-in shell with no working session token."""
        monkeypatch.setattr(auth, "verify_id_token",
                            lambda p, t: {"sub": "sub_nosecret", "email": "n@example.com"})
        monkeypatch.setattr(config, "JWT_SECRET", "")
        assert auth.signin("google", "tok", DEVICE) is None
