"""Tests for backend PostHog analytics (SPEC-ANALYTICS). No network — httpx is monkeypatched."""
import asyncio

import analytics
import config


def test_capture_noop_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setattr(analytics, "ENABLED", False)
    monkeypatch.setattr(analytics, "_post", lambda payload: calls.append(payload))
    asyncio.run(analytics.capture("wallet-1", "some_event", {"a": 1}))
    assert calls == []


def test_capture_noop_when_no_distinct_id(monkeypatch):
    calls = []
    monkeypatch.setattr(analytics, "ENABLED", True)
    monkeypatch.setattr(analytics, "_post", lambda payload: _record(calls, payload))
    asyncio.run(analytics.capture("", "some_event"))
    assert calls == []


async def _record_async(calls, payload):
    calls.append(payload)


def _record(calls, payload):
    # _post is awaited, so return a coroutine
    return _record_async(calls, payload)


def test_capture_builds_payload_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(analytics, "ENABLED", True)
    monkeypatch.setattr(config, "POSTHOG_API_KEY", "phc_test")
    monkeypatch.setattr(config, "ENVIRONMENT", "gamma")
    monkeypatch.setattr(analytics, "_post", lambda payload: _record(calls, payload))

    asyncio.run(analytics.capture("wallet-42", "iap_purchase_credited", {"sku": "spark_pack_50", "sparks": 50}))

    assert len(calls) == 1
    p = calls[0]
    assert p["api_key"] == "phc_test"
    assert p["event"] == "iap_purchase_credited"
    assert p["distinct_id"] == "wallet-42"
    assert p["properties"]["sku"] == "spark_pack_50"
    assert p["properties"]["sparks"] == 50
    assert p["properties"]["$lib"] == "revelry-backend"
    assert p["properties"]["env"] == "gamma"


def test_post_swallows_errors(monkeypatch):
    """_post must never raise, even if the HTTP client blows up."""
    class BoomClient:
        def __init__(self, *a, **k):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(analytics.httpx, "AsyncClient", BoomClient)
    # Should complete without raising.
    asyncio.run(analytics._post({"api_key": "x", "event": "e", "distinct_id": "d", "properties": {}}))


def test_capture_bg_no_running_loop_is_safe(monkeypatch):
    """capture_bg from a sync context (no loop) must not raise."""
    monkeypatch.setattr(analytics, "ENABLED", True)
    analytics.capture_bg("wallet-1", "e", {"x": 1})  # no running loop → logged + dropped, no exception
