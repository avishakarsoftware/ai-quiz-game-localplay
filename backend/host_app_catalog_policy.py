from __future__ import annotations

import copy
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import config

logger = logging.getLogger(__name__)

POLICY_CACHE_TTL_SECONDS = 60
ALLOWED_CAPABILITY_KEYS = {
    "can_create_content",
    "can_edit_content",
    "can_quick_start",
    "supports_ai_generation",
    "supports_images",
    "payments_enabled",
    "embedded_authoring_supported",
}
LIVE_STATUSES = {"live", "gamma"}
LOCAL_ENVIRONMENTS = {"local", "dev", "development", "test", "testing"}


@dataclass(frozen=True)
class CatalogPolicyContext:
    environment: str
    host_app: str
    external_container_id: str = ""
    external_user_id: str = ""
    include_planned: bool = False


_cache: dict[tuple[str, str], tuple[float, dict[str, dict[str, Any]]]] = {}


def clear_policy_cache() -> None:
    _cache.clear()


def current_environment() -> str:
    return (getattr(config, "ENVIRONMENT", "") or "local").strip().lower() or "local"


def _is_production(environment: str) -> bool:
    return environment in {"production", "prod"}


def _is_development(environment: str) -> bool:
    return environment in LOCAL_ENVIRONMENTS


def _load_policy_map(environment: str, host_app: str, loader: Callable[[str, str], list[dict]]) -> dict[str, dict[str, Any]]:
    cache_key = (environment, host_app)
    now = time.time()
    cached = _cache.get(cache_key)
    if cached and now - cached[0] < POLICY_CACHE_TTL_SECONDS:
        return cached[1]
    rows = loader(environment, host_app)
    policy: dict[str, dict[str, Any]] = {}
    for row in rows:
        game_id = str(row.get("game_id") or "").strip()
        if not game_id:
            continue
        policy[game_id] = dict(row)
    _cache[cache_key] = (now, policy)
    return policy


def _static_supports_host_app(game: dict[str, Any], host_app: str) -> bool:
    return bool(game.get("host_app_supported") and host_app in (game.get("supported_host_apps") or []))


def _allowlist_allows(policy: dict[str, Any], context: CatalogPolicyContext) -> bool:
    party_ids = set(str(item) for item in (policy.get("allowlist_party_ids") or []) if item)
    user_ids = set(str(item) for item in (policy.get("allowlist_external_user_ids") or []) if item)
    if party_ids and context.external_container_id not in party_ids:
        return False
    if user_ids and context.external_user_id not in user_ids:
        return False
    return True


def _rollout_allows(policy: dict[str, Any], context: CatalogPolicyContext, game_id: str) -> bool:
    percentage = policy.get("rollout_percentage")
    if percentage is None:
        return True
    try:
        percentage_int = int(percentage)
    except (TypeError, ValueError):
        return False
    if percentage_int >= 100:
        return True
    if percentage_int <= 0:
        return False
    stable_subject = context.external_container_id or context.external_user_id
    if not stable_subject:
        return False
    digest = hashlib.sha256(f"{context.host_app}:{stable_subject}:{game_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < percentage_int


def _effective_game(game: dict[str, Any], policy: Optional[dict[str, Any]], context: CatalogPolicyContext) -> Optional[dict[str, Any]]:
    game_id = str(game.get("id") or game.get("game_type") or "")
    if not _static_supports_host_app(game, context.host_app):
        return None

    if not policy:
        if _is_production(context.environment):
            return None
        return copy.deepcopy(game)

    if not policy.get("enabled"):
        if policy.get("status") == "planned" and context.include_planned:
            planned = copy.deepcopy(game)
            planned["status"] = "planned"
            planned["launchable"] = False
            return planned
        return None

    if not _allowlist_allows(policy, context):
        return None
    if not _rollout_allows(policy, context, game_id):
        return None

    status = str(policy.get("status") or "disabled")
    if status == "planned" and not context.include_planned:
        return None

    effective = copy.deepcopy(game)
    effective["status"] = status
    overrides = policy.get("capability_overrides") or {}
    for key, value in overrides.items():
        if key not in ALLOWED_CAPABILITY_KEYS:
            logger.warning("Ignoring unknown host-app catalog capability override: %s", key)
            continue
        effective[key] = bool(effective.get(key)) and bool(value)
    effective["launchable"] = bool(effective.get("launchable")) and status in LIVE_STATUSES
    if status == "planned":
        effective["launchable"] = False
    return effective


def effective_catalog(
    static_catalog: list[dict[str, Any]],
    *,
    host_app: str = "",
    external_container_id: str = "",
    external_user_id: str = "",
    include_planned: bool = False,
    environment: str = "",
    loader: Optional[Callable[[str, str], list[dict[str, Any]]]] = None,
) -> list[dict[str, Any]]:
    if not host_app:
        return [copy.deepcopy(game) for game in static_catalog]

    import db

    env = (environment or current_environment()).strip().lower() or "local"
    context = CatalogPolicyContext(
        environment=env,
        host_app=host_app,
        external_container_id=external_container_id,
        external_user_id=external_user_id,
        include_planned=include_planned,
    )
    policy_loader = loader or db.list_host_app_catalog_flags
    try:
        policy_map = _load_policy_map(env, host_app, policy_loader)
    except Exception:
        logger.exception("Failed to load host-app catalog policy")
        if _is_production(env):
            return []
        policy_map = {}

    games: list[dict[str, Any]] = []
    for game in static_catalog:
        game_id = str(game.get("id") or game.get("game_type") or "")
        effective = _effective_game(game, policy_map.get(game_id), context)
        if effective:
            games.append(effective)
    return games


def is_game_allowed(
    static_catalog: list[dict[str, Any]],
    game_type: str,
    *,
    host_app: str,
    external_container_id: str = "",
    external_user_id: str = "",
    required_capability: str = "",
    environment: str = "",
    loader: Optional[Callable[[str, str], list[dict[str, Any]]]] = None,
) -> bool:
    games = effective_catalog(
        static_catalog,
        host_app=host_app,
        external_container_id=external_container_id,
        external_user_id=external_user_id,
        environment=environment,
        loader=loader,
    )
    for game in games:
        if game_type not in {game.get("id"), game.get("game_type")}:
            continue
        if not game.get("launchable"):
            return False
        if required_capability and not game.get(required_capability):
            return False
        return True
    return False
