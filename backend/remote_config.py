"""Fetches AI model config from the remote config.json on IONOS.

Allows changing which LLM model is used for free/paid users without
redeploying the backend. Falls back to env var defaults if fetch fails.
"""
import asyncio
import json
import logging
import time
from typing import Optional

import httpx

import config
import db

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


OVERRIDES_KEY = "remote_config_overrides"


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge `patch` onto `base`, returning a new dict.

    Nested rather than top-level so an operator can flip one flag without having to restate
    the whole `feature_flags` object (and silently drop the keys they didn't mention).
    """
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def get_overrides() -> dict:
    """Operator-set overrides from the DB. Never raises — a settings-store problem must not
    take down config reads (which would take down AI model selection with it)."""
    try:
        raw = db.get_setting(OVERRIDES_KEY)
        if not raw:
            return {}
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001
        logger.warning("Could not read remote-config overrides", exc_info=True)
        return {}


def set_overrides(patch: dict) -> dict:
    """Replace the override layer wholesale and return what was stored."""
    db.set_setting(OVERRIDES_KEY, json.dumps(patch))
    return patch


def clear_overrides() -> None:
    db.delete_setting(OVERRIDES_KEY)


async def get_config() -> dict:
    """Get cached remote config, refreshing if stale. Never clears a good cache on failure.

    Operator overrides are merged on top of the fetched config. The fetched source lives on
    IONOS, so it can't be edited from the backend — the override layer is what makes a live
    change (a feature kill switch, an AI model swap) possible without a frontend deploy.
    """
    global _last_fetch
    if time.time() - _last_fetch > _FETCH_INTERVAL:
        result = await _fetch_remote_config()
        if result is None:
            # Fetch failed — keep using old cache, but don't retry for another minute
            _last_fetch = time.time() - _FETCH_INTERVAL + 60
    overrides = get_overrides()
    if not overrides:
        return _cached_config
    return _deep_merge(_cached_config if isinstance(_cached_config, dict) else {}, overrides)


def _get_ai_models() -> dict:
    """Safely extract ai_models dict, tolerating malformed config.

    Applies operator overrides too — otherwise an override could change what `/config/public`
    reports while the backend kept generating with the old model, which is worse than having
    no override at all. This is the path that makes a live model swap real.
    """
    base = _cached_config if isinstance(_cached_config, dict) else {}
    overrides = get_overrides()
    merged = _deep_merge(base, overrides) if overrides else base
    ai = merged.get("ai_models")
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
