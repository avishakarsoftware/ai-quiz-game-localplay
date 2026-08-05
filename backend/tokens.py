"""Token-based economy — wallet balance checks, spending, and status."""
import re
import logging
from typing import Optional

from fastapi import Request

import config
from contextvars import ContextVar

# Set per-request by main.py's middleware; empty when there is no HTTP context (tests, internal
# calls) — in which case the signup gate ALLOWS, because a gate that misfires on internal paths
# would be worse than the farming it prevents.
_request_client_ip: ContextVar[str] = ContextVar("request_client_ip", default="")

# {ip: (utc_date_str, bonus_creations_today)} — in-memory like every other limiter here; a
# restart resets it, which merely re-opens the day's allowance. Single-process by design.
_signup_grants_by_ip: dict = {}


def set_request_client_ip(ip: str) -> None:
    _request_client_ip.set(ip or "")


def _signup_bonus_allowed() -> bool:
    """Consume one unit of the per-IP bonus allowance. Call ONLY when actually creating a wallet.

    Any fresh UUID in X-Device-Id used to get SIGNUP_BONUS_TOKENS unconditionally: mint ids,
    farm grants, spend them on LLM generation — draining the shared hourly LLM budget
    (REVIEW-2026-08 S2). Past the cap the wallet is still created, just grantless, so a real
    guest at a big party can always play; only the freebie stops. Legit parties fit far under
    the default (guests join rooms — they don't each need a bonus-bearing wallet-per-minute)."""
    limit = config.SIGNUP_BONUS_IP_DAILY_LIMIT
    if limit <= 0:
        return True
    ip = _request_client_ip.get()
    if not ip:
        return True
    today = db._utc_date_str()
    date, count = _signup_grants_by_ip.get(ip, (today, 0))
    if date != today:
        count = 0
    if count >= limit:
        return False
    _signup_grants_by_ip[ip] = (today, count + 1)
    return True


def _create_or_get_wallet_gated(wallet_id: str) -> dict:
    if db.wallet_exists(wallet_id):
        return db.get_or_create_wallet(wallet_id, signup_bonus=True)  # existing: no creation happens
    return db.get_or_create_wallet(wallet_id, signup_bonus=_signup_bonus_allowed())
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
    key = (
        req.headers.get("X-Idempotency-Key")
        or req.headers.get("Idempotency-Key")
        or ""
    ).strip()
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
    """Ensure a wallet exists for this ID, creating with signup bonus if new.
    The bonus is subject to the per-IP daily allowance — see _signup_bonus_allowed."""
    return _create_or_get_wallet_gated(wallet_id)


# --- Balance checks ---

def get_token_status(wallet_id: str) -> dict:
    """Get full token status for the /tokens/balance endpoint.
    Auto-grants daily bonus if new UTC day."""
    wallet = _create_or_get_wallet_gated(wallet_id)
    today = db._utc_date_str()

    # Auto-grant daily bonus (always call — db function handles idempotency atomically)
    daily_granted, new_balance, streak, _reward = db.check_and_grant_daily_bonus(wallet_id)
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
        "bonus_streak": streak,
        "streak_next_reward": db._streak_reward(streak + 1),
        "cost_generate": config.COST_GENERATE,
        "cost_room": config.COST_ROOM,
        "ads_remaining_today": ads_remaining,
    }


def can_generate(wallet_id: str) -> bool:
    """Check if wallet has enough tokens to generate content."""
    return db.get_wallet_balance(wallet_id) >= config.COST_GENERATE


def spend_generate(wallet_id: str) -> tuple[bool, int]:
    """Debit tokens for content generation. Returns (success, new_balance)."""
    success, balance = db.debit_tokens(wallet_id, config.COST_GENERATE, "spend_generate")
    if success:
        logger.info("spend_generate: wallet=%s cost=%d balance=%d", wallet_id[:8], config.COST_GENERATE, balance)
    else:
        logger.warning("spend_generate failed: wallet=%s insufficient balance", wallet_id[:8])
    return success, balance


def can_create_room(wallet_id: str) -> bool:
    """Check if wallet has enough tokens to create a room."""
    return db.get_wallet_balance(wallet_id) >= config.COST_ROOM


def spend_room(wallet_id: str) -> tuple[bool, int]:
    """Debit tokens for game start/reset. Returns (success, new_balance)."""
    success, balance = db.debit_tokens(wallet_id, config.COST_ROOM, "spend_room")
    if success:
        logger.info("spend_room: wallet=%s cost=%d balance=%d", wallet_id[:8], config.COST_ROOM, balance)
    else:
        logger.warning("spend_room failed: wallet=%s insufficient balance", wallet_id[:8])
    return success, balance


def use_premium_model(wallet_id: str) -> bool:
    """Check if this wallet qualifies for premium AI model (has ever purchased tokens)."""
    return db.has_ever_purchased(wallet_id)
