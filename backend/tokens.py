"""Token-based economy — wallet balance checks, spending, and status."""
import re
import logging
from typing import Optional

from fastapi import Request

import config
import db
import auth as auth_module

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


# --- Request helpers (carried over from premium.py) ---

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


# --- Wallet resolution ---

def get_wallet_id(req: Request) -> str:
    """Resolve wallet ID: user_id if signed in, else device_id."""
    session = auth_module.get_session_from_request(req)
    if session and session.get("user_id"):
        return session["user_id"]
    return get_device_id(req)


def ensure_wallet(wallet_id: str) -> dict:
    """Ensure a wallet exists for this ID, creating with signup bonus if new."""
    return db.get_or_create_wallet(wallet_id, signup_bonus=True)


# --- Balance checks ---

def get_token_status(wallet_id: str) -> dict:
    """Get full token status for the /tokens/balance endpoint.
    Auto-grants daily bonus if new UTC day."""
    wallet = db.get_or_create_wallet(wallet_id, signup_bonus=True)
    today = db._utc_date_str()

    # Auto-grant daily bonus (always call — db function handles idempotency atomically)
    daily_granted, new_balance = db.check_and_grant_daily_bonus(wallet_id)
    bonus_amount = 0
    if daily_granted:
        bonus_amount = new_balance - wallet["balance"]
        wallet["balance"] = new_balance

    # Calculate ads remaining
    ads_today = wallet["ads_watched_today"] if wallet["ads_watched_date"] == today else 0
    ads_remaining = max(0, config.MAX_ADS_PER_DAY - ads_today)

    return {
        "balance": wallet["balance"],
        "has_purchased": wallet["lifetime_purchased"] > 0,
        "daily_bonus_available": not daily_granted and wallet["last_daily_bonus_date"] != today,
        "daily_bonus_granted": daily_granted,
        "bonus_amount": bonus_amount,
        "cost_generate": config.COST_GENERATE,
        "cost_room": config.COST_ROOM,
        "ads_remaining_today": ads_remaining,
    }


def can_generate(wallet_id: str) -> bool:
    """Check if wallet has enough tokens to generate content."""
    return db.get_wallet_balance(wallet_id) >= config.COST_GENERATE


def spend_generate(wallet_id: str) -> tuple[bool, int]:
    """Debit tokens for content generation. Returns (success, new_balance)."""
    return db.debit_tokens(wallet_id, config.COST_GENERATE, "spend_generate")


def can_create_room(wallet_id: str) -> bool:
    """Check if wallet has enough tokens to create a room."""
    return db.get_wallet_balance(wallet_id) >= config.COST_ROOM


def spend_room(wallet_id: str) -> tuple[bool, int]:
    """Debit tokens for room creation. Returns (success, new_balance)."""
    return db.debit_tokens(wallet_id, config.COST_ROOM, "spend_room")


def use_premium_model(wallet_id: str) -> bool:
    """Check if this wallet qualifies for premium AI model (has ever purchased tokens)."""
    return db.has_ever_purchased(wallet_id)
