"""Server-side product analytics — fire-and-forget PostHog capture.

No-op unless POSTHOG_API_KEY is set (see SPEC-ANALYTICS). Never raises into request handlers:
every failure is swallowed and logged at debug level. Backend events use the same distinct_id
(wallet_id = user_id if signed in, else device_id) as the frontend, so they unify on one person.
"""
import asyncio
import logging

import httpx

import config

logger = logging.getLogger(__name__)

ENABLED = bool(config.POSTHOG_API_KEY)
_CAPTURE_URL = f"{config.POSTHOG_HOST.rstrip('/')}/capture/"
_TIMEOUT = 2.0

# Hold strong refs to in-flight fire-and-forget tasks so the event loop doesn't GC them mid-flight.
_pending: set = set()


async def _post(payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.post(_CAPTURE_URL, json=payload)
    except Exception as e:  # noqa: BLE001 — analytics must never break a request
        logger.debug("PostHog capture failed: %s", e)


async def capture(distinct_id: str, event: str, properties: dict | None = None) -> None:
    """Send one event to PostHog. No-op when disabled or distinct_id is empty."""
    if not ENABLED or not distinct_id:
        return
    props = dict(properties or {})
    props.setdefault("$lib", "revelry-backend")
    if config.ENVIRONMENT:
        props.setdefault("env", config.ENVIRONMENT)
    await _post({
        "api_key": config.POSTHOG_API_KEY,
        "event": event,
        "distinct_id": distinct_id,
        "properties": props,
    })


def capture_bg(distinct_id: str, event: str, properties: dict | None = None) -> None:
    """Fire-and-forget capture from inside an async context (schedules a task, never awaits)."""
    if not ENABLED or not distinct_id:
        return
    try:
        task = asyncio.get_running_loop().create_task(capture(distinct_id, event, properties))
        _pending.add(task)
        task.add_done_callback(_pending.discard)
    except RuntimeError:
        # No running loop (e.g. called from sync context) — skip rather than block.
        logger.debug("capture_bg called without a running loop; event %s dropped", event)
