"""Tests for the backend /config/public endpoint (SPEC-REMOTE-CONFIG)."""
import remote_config
import config
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)


async def _fake_config():
    return {"version": 7, "feature_flags": {"show_upgrade_button": False}, "welcome_message": "hi"}


async def _boom_config():
    raise RuntimeError("remote fetch failed")


def test_public_config_superset_with_economy(monkeypatch):
    monkeypatch.setattr(remote_config, "get_config", _fake_config)
    res = client.get("/config/public")
    assert res.status_code == 200
    body = res.json()
    # passthrough of the fetched config
    assert body["version"] == 7
    assert body["welcome_message"] == "hi"
    # backend-authoritative economy is always present
    assert body["economy"]["cost_room"] == config.COST_ROOM
    assert body["economy"]["cost_generate"] == config.COST_GENERATE
    # feature flags augmented (fetched value preserved, backend flags added)
    assert body["feature_flags"]["show_upgrade_button"] is False
    assert body["feature_flags"]["ads_enabled"] is False
    assert "referral_enabled" in body["feature_flags"]
    assert "enabled_game_types" in body


def test_public_config_never_500_on_fetch_error(monkeypatch):
    monkeypatch.setattr(remote_config, "get_config", _boom_config)
    res = client.get("/config/public")
    assert res.status_code == 200
    body = res.json()
    # still returns a valid config with backend defaults
    assert body["economy"]["cost_room"] == config.COST_ROOM
    assert body["feature_flags"]["ads_enabled"] is False
