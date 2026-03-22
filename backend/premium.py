"""Device-based usage tracking and JWT premium tokens."""
import re
import time
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Request

import config

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_USAGE_WINDOW = 24 * 60 * 60  # 24 hours in seconds

# device_id -> list of generation timestamps
_device_usage: dict[str, list[float]] = defaultdict(list)

# device_id -> premium token (pending pickup after Stripe checkout)
_pending_tokens: dict[str, str] = {}


def get_device_id(req: Request) -> str:
    """Extract and validate device ID from X-Device-Id header."""
    device_id = (req.headers.get("X-Device-Id") or "").strip()
    if device_id and _UUID_RE.match(device_id):
        return device_id
    return ""


def check_device_limit(device_id: str) -> bool:
    """Return True if device is under the free tier limit."""
    now = time.time()
    # Prune old entries
    _device_usage[device_id] = [
        t for t in _device_usage[device_id] if now - t < _USAGE_WINDOW
    ]
    return len(_device_usage[device_id]) < config.FREE_TIER_LIMIT


def record_device_usage(device_id: str) -> None:
    """Record a successful generation for the device."""
    _device_usage[device_id].append(time.time())


def get_device_usage_count(device_id: str) -> int:
    """Return the number of generations in the current 24h window."""
    now = time.time()
    _device_usage[device_id] = [
        t for t in _device_usage[device_id] if now - t < _USAGE_WINDOW
    ]
    return len(_device_usage[device_id])


def create_premium_token(device_id: str) -> str:
    """Create a signed JWT premium token for the given device."""
    exp = datetime.now(timezone.utc) + timedelta(hours=config.PREMIUM_DURATION_HOURS)
    payload = {
        "device_id": device_id,
        "exp": exp,
        "tier": "party_pass",
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
    """Check if the request has a valid premium token."""
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth[7:]
    device_id = get_device_id(req)
    if not device_id:
        return False
    return verify_premium_token(token, device_id)


def store_pending_token(device_id: str, token: str) -> None:
    """Store a token for pickup after Stripe checkout redirect."""
    _pending_tokens[device_id] = token


def pop_pending_token(device_id: str) -> Optional[str]:
    """Retrieve and remove a pending token for the device."""
    return _pending_tokens.pop(device_id, None)
