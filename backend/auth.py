"""Authentication: Google/Apple ID token verification and session JWTs."""
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import httpx
from jwt import PyJWKClient
from fastapi import Request

import config
import db

logger = logging.getLogger(__name__)

# --- Apple JWKS caching ---
_apple_jwks_client: Optional[PyJWKClient] = None
_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"


def _get_apple_jwks_client() -> PyJWKClient:
    """Get or create a cached PyJWKClient for Apple's JWKS endpoint."""
    global _apple_jwks_client
    if _apple_jwks_client is None:
        _apple_jwks_client = PyJWKClient(_APPLE_JWKS_URL, cache_jwk_set=True, lifespan=86400)
    return _apple_jwks_client


# --- ID Token Verification ---

def verify_google_token(id_token: str) -> Optional[dict]:
    """Verify a Google ID token. Returns {"sub", "email"} or None."""
    if not config.GOOGLE_CLIENT_ID:
        logger.error("GOOGLE_CLIENT_ID not configured")
        return None
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        claims = google_id_token.verify_oauth2_token(
            id_token,
            google_requests.Request(),
            audience=config.GOOGLE_CLIENT_ID,
        )
        # verify_oauth2_token checks sig, exp, iss, aud
        iss = claims.get("iss", "")
        if iss not in ("accounts.google.com", "https://accounts.google.com"):
            logger.warning("Google token has unexpected issuer: %s", iss)
            return None
        sub = claims.get("sub")
        if not sub:
            return None
        return {"sub": sub, "email": claims.get("email")}
    except Exception as e:
        logger.warning("Google token verification failed: %s", e)
        return None


def verify_apple_token(id_token: str) -> Optional[dict]:
    """Verify an Apple ID token using JWKS. Returns {"sub", "email"} or None."""
    if not config.APPLE_CLIENT_ID:
        logger.error("APPLE_CLIENT_ID not configured")
        return None
    try:
        jwks_client = _get_apple_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.APPLE_CLIENT_ID,
            issuer="https://appleid.apple.com",
        )
        sub = claims.get("sub")
        if not sub:
            return None
        return {"sub": sub, "email": claims.get("email")}
    except Exception as e:
        logger.warning("Apple token verification failed: %s", e)
        return None


def verify_id_token(provider: str, id_token: str) -> Optional[dict]:
    """Verify an ID token from the given provider. Returns {"sub", "email"} or None."""
    if provider == "google":
        return verify_google_token(id_token)
    elif provider == "apple":
        return verify_apple_token(id_token)
    return None


# --- Session JWTs ---

def create_session_token(user_id: str, device_id: str) -> Optional[str]:
    """Create a signed session JWT (30-day expiry). Returns None if JWT_SECRET is not configured."""
    if not config.JWT_SECRET:
        logger.error("Cannot create session token: JWT_SECRET not configured")
        return None
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=config.SESSION_JWT_EXPIRY_DAYS)
    payload = {
        "user_id": user_id,
        "device_id": device_id,
        "iat": int(now.timestamp()),
        "exp": exp,
        "type": "session",
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def verify_session_token(token: str) -> Optional[dict]:
    """Verify a session JWT. Returns {"user_id", "device_id"} or None."""
    if not config.JWT_SECRET:
        return None
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "session":
            return None
        user_id = payload.get("user_id")
        device_id = payload.get("device_id")
        if not user_id or not device_id:
            return None
        if not isinstance(user_id, str) or not isinstance(device_id, str):
            return None
        return {"user_id": user_id, "device_id": device_id}
    except jwt.InvalidTokenError:
        return None


def get_session_from_request(req: Request) -> Optional[dict]:
    """Extract and verify session token from X-Session-Token header.
    Returns {"user_id", "device_id"} or None."""
    token = (req.headers.get("X-Session-Token") or "").strip()
    if not token:
        return None
    return verify_session_token(token)


# --- Sign-In Flow ---

def signin(provider: str, id_token: str, device_id: str) -> Optional[dict]:
    """Full sign-in flow: verify token, find/create user, merge entitlements.
    Returns {"user": {...}, "session_token": "..."} or None on failure."""
    # 1. Verify the ID token
    claims = verify_id_token(provider, id_token)
    if not claims:
        return None

    sub = claims["sub"]
    email = claims.get("email")

    # 2. Find or create user
    user = db.find_or_create_user(provider, sub, email)

    # 3. Merge device entitlements/usage to user
    db.merge_device_to_user(user["id"], device_id)

    # 4. Merge device token wallet to user wallet
    db.merge_wallet(device_id, user["id"])

    # 4. Create session JWT
    session_token = create_session_token(user["id"], device_id)
    if not session_token:
        return None

    logger.info("User signed in: %s (provider=%s, device=%s)", user["id"][:8], provider, device_id[:8])

    return {
        "user": {
            "id": user["id"],
            "provider": user["provider"],
            "email": user.get("email"),
        },
        "session_token": session_token,
    }
