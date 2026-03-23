"""Fetches AI model config from the remote config.json on IONOS.

Allows changing which LLM model is used for free/paid users without
redeploying the backend. Falls back to env var defaults if fetch fails.
"""
import asyncio
import logging
import time
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)

# Cache
_cached_config: dict = {}
_last_fetch: float = 0.0
_FETCH_INTERVAL = 300  # 5 minutes

# Remote config URL — set via env var, or derive from ALLOWED_ORIGINS with /quiz/ path
REMOTE_CONFIG_URL = config.REMOTE_CONFIG_URL or (
    config.ALLOWED_ORIGINS.split(",")[0].strip().rstrip("/") + "/quiz/config.json"
    if config.ALLOWED_ORIGINS else ""
)


async def _fetch_remote_config() -> Optional[dict]:
    """Fetch config.json from the frontend origin."""
    global _cached_config, _last_fetch
    if not REMOTE_CONFIG_URL:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(REMOTE_CONFIG_URL)
            if res.status_code == 200:
                data = res.json()
                _cached_config = data
                _last_fetch = time.time()
                logger.debug("Remote config fetched: ai_models=%s", data.get("ai_models"))
                return data
    except Exception as e:
        logger.warning("Failed to fetch remote config from %s: %s", REMOTE_CONFIG_URL, e)
    return None


async def get_config() -> dict:
    """Get cached remote config, refreshing if stale. Never clears a good cache on failure."""
    global _last_fetch
    if time.time() - _last_fetch > _FETCH_INTERVAL:
        result = await _fetch_remote_config()
        if result is None:
            # Fetch failed — keep using old cache, but don't retry for another minute
            _last_fetch = time.time() - _FETCH_INTERVAL + 60
    return _cached_config


def _get_ai_models() -> dict:
    """Safely extract ai_models dict, tolerating malformed config."""
    ai = _cached_config.get("ai_models") if isinstance(_cached_config, dict) else None
    return ai if isinstance(ai, dict) else {}


def get_free_model() -> str:
    """Get the model to use for free-tier users."""
    return _get_ai_models().get("free_model") or config.GEMINI_MODEL


def get_paid_model() -> str:
    """Get the model to use for paid users."""
    return _get_ai_models().get("paid_model") or config.GEMINI_MODEL


def get_provider() -> str:
    """Get the AI provider from remote config."""
    return _get_ai_models().get("provider") or config.DEFAULT_PROVIDER


async def init():
    """Initial fetch on startup."""
    if not REMOTE_CONFIG_URL:
        logger.warning("REMOTE_CONFIG_URL not configured — using hardcoded AI model defaults")
    await _fetch_remote_config()
    ai = _cached_config.get("ai_models", {})
    logger.info("Remote AI config: free=%s, paid=%s, provider=%s",
                ai.get("free_model", "default"), ai.get("paid_model", "default"),
                ai.get("provider", "default"))
