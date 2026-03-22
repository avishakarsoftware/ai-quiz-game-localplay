"""Device-based usage tracking and JWT premium tokens — backed by SQLite."""
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Request

import config
import db

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def get_device_id(req: Request) -> str:
    """Extract and validate device ID from X-Device-Id header."""
    device_id = (req.headers.get("X-Device-Id") or "").strip()
    if device_id and _UUID_RE.match(device_id):
        return device_id
    return ""


def get_platform(req: Request) -> str:
    """Extract platform from X-Platform header."""
    return (req.headers.get("X-Platform") or "web").strip().lower()


def get_idempotency_key(req: Request) -> str:
    """Extract idempotency key from header."""
    key = (req.headers.get("X-Idempotency-Key") or "").strip()
    if key and _UUID_RE.match(key):
        return key
    return ""


def create_premium_token(device_id: str, entitlement_id: str = "", games_remaining: int = 10) -> Optional[str]:
    """Create a signed JWT premium token for the given device. Returns None if JWT_SECRET is not configured."""
    if not config.JWT_SECRET:
        return None
    exp = datetime.now(timezone.utc) + timedelta(hours=config.PREMIUM_DURATION_HOURS)
    payload = {
        "device_id": device_id,
        "entitlement_id": entitlement_id,
        "exp": exp,
        "tier": "party_pass",
        "games_remaining": games_remaining,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def verify_premium_token(token: str, device_id: str) -> bool:
    """Verify a premium token is valid and matches the device ID."""
    if not config.JWT_SECRET:
        return False
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        return payload.get("device_id") == device_id
    except jwt.InvalidTokenError:
        return False


def is_premium(req: Request) -> bool:
    """Check if the request has a valid premium token (fast path — DB is authoritative)."""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth[7:]
    device_id = get_device_id(req)
    if not device_id:
        return False
    return verify_premium_token(token, device_id)


def has_active_entitlement(device_id: str) -> bool:
    """Check if device has an active entitlement (peek only, no decrement)."""
    if not device_id:
        return False
    ent = db.get_active_entitlement(device_id)
    return ent is not None


def check_and_use_entitlement(device_id: str) -> tuple[bool, Optional[dict]]:
    """Check for active entitlement and decrement if found.
    Returns (has_entitlement, entitlement_dict_or_none)."""
    ent = db.get_active_entitlement(device_id)
    if not ent:
        return False, None
    if db.decrement_entitlement(ent["id"]):
        ent["games_remaining"] -= 1
        return True, ent
    return False, None


def peek_free_limit(device_id: str) -> tuple[bool, int]:
    """Check free usage without incrementing. Returns (can_play, used_count)."""
    return db.peek_free_usage(device_id)


def check_free_limit(device_id: str) -> tuple[bool, int]:
    """Check and increment free usage. Returns (allowed, count)."""
    return db.check_and_increment_free_usage(device_id)


def has_active_entitlement_for_user(user_id: str) -> bool:
    """Check if user has an active entitlement (peek only, no decrement)."""
    if not user_id:
        return False
    ent = db.get_active_entitlement_for_user(user_id)
    return ent is not None


def check_and_use_entitlement_for_user(user_id: str) -> tuple[bool, Optional[dict]]:
    """Check for user's active entitlement and decrement if found."""
    ent = db.get_active_entitlement_for_user(user_id)
    if not ent:
        return False, None
    if db.decrement_entitlement(ent["id"]):
        ent["games_remaining"] -= 1
        return True, ent
    return False, None


def peek_user_free_limit(user_id: str) -> tuple[bool, int]:
    """Check user free usage without incrementing (cross-device)."""
    return db.peek_user_free_usage(user_id)


def check_user_free_limit(user_id: str, device_id: str) -> tuple[bool, int]:
    """Check and increment user free usage (cross-device). Returns (allowed, count)."""
    return db.check_and_increment_user_free_usage(user_id, device_id)


def get_entitlement_status(device_id: str, user_id: str = "") -> dict:
    """Get full entitlement status for the /entitlements/current endpoint.
    If user_id is provided, checks user-scoped entitlements and cross-device free usage."""
    # Signed-in user: check user-scoped entitlements first
    if user_id:
        ent = db.get_active_entitlement_for_user(user_id)
        free_used = db.get_user_free_usage_count(user_id)
    else:
        ent = db.get_active_entitlement(device_id)
        free_used = db.get_free_usage_count(device_id)

    if ent:
        return {
            "premium": True,
            "status": ent["status"],
            "games_remaining": ent["games_remaining"],
            "expires_at": ent["expires_at"],
            "free_games_used": free_used,
            "free_games_limit": config.FREE_TIER_LIMIT,
            "pending_purchase": False,
        }
    return {
        "premium": False,
        "status": None,
        "games_remaining": 0,
        "expires_at": None,
        "free_games_used": free_used,
        "free_games_limit": config.FREE_TIER_LIMIT,
        "pending_purchase": False,
    }
