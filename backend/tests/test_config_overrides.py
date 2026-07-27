"""Operator override layer for remote config (SPEC-REMOTE-CONFIG §admin).

The fetched config lives on IONOS and can't be written from the backend, so the override layer
is the only way to make a live change — a feature kill switch or an AI model swap — without a
frontend deploy. These tests pin the merge semantics and the admin gate.
"""
import asyncio

import pytest

import db
import remote_config


@pytest.fixture(autouse=True)
def _clean_overrides():
    remote_config.clear_overrides()
    yield
    remote_config.clear_overrides()


@pytest.fixture
def fetched(monkeypatch):
    """Pretend IONOS returned this, without going near the network."""
    base = {
        "version": 3,
        "feature_flags": {"show_upgrade_button": True, "enable_image_generation": True},
        "ai_models": {"free_model": "gemini-2.5-flash-lite", "paid_model": "gemini-2.5-flash-lite"},
    }
    monkeypatch.setattr(remote_config, "_cached_config", base)
    # Keep get_config from trying to refresh over the network.
    monkeypatch.setattr(remote_config, "_last_fetch", float("inf"))
    return base


def _cfg() -> dict:
    return asyncio.run(remote_config.get_config())


def test_no_overrides_returns_the_fetched_config_untouched(fetched):
    assert _cfg() == fetched


def test_override_merges_nested_without_dropping_siblings(fetched):
    """A top-level replace would silently delete enable_image_generation — the whole reason
    the merge is deep."""
    remote_config.set_overrides({"feature_flags": {"show_upgrade_button": False}})
    cfg = _cfg()
    assert cfg["feature_flags"]["show_upgrade_button"] is False
    assert cfg["feature_flags"]["enable_image_generation"] is True
    assert cfg["version"] == 3


def test_override_can_add_a_key_that_the_fetched_config_lacks(fetched):
    remote_config.set_overrides({"enabled_game_types": ["quiz", "poker"]})
    assert _cfg()["enabled_game_types"] == ["quiz", "poker"]


def test_overrides_survive_a_process_restart(fetched):
    """An in-memory kill switch evaporates during exactly the rollout it exists for."""
    remote_config.set_overrides({"feature_flags": {"show_upgrade_button": False}})
    assert db.get_setting(remote_config.OVERRIDES_KEY)          # persisted, not just cached
    assert remote_config.get_overrides()["feature_flags"]["show_upgrade_button"] is False


def test_setting_overrides_replaces_rather_than_accumulates(fetched):
    remote_config.set_overrides({"a": 1})
    remote_config.set_overrides({"b": 2})
    assert remote_config.get_overrides() == {"b": 2}


def test_clearing_restores_the_fetched_config(fetched):
    remote_config.set_overrides({"feature_flags": {"show_upgrade_button": False}})
    remote_config.clear_overrides()
    assert _cfg()["feature_flags"]["show_upgrade_button"] is True


def test_ai_model_selection_honours_overrides(fetched):
    """If /config/public reported a new model but generation still used the old one, the
    override would be actively misleading."""
    assert remote_config.get_free_model() == "gemini-2.5-flash-lite"
    remote_config.set_overrides({"ai_models": {"free_model": "gemini-9-turbo"}})
    assert remote_config.get_free_model() == "gemini-9-turbo"
    # Sibling key preserved by the deep merge.
    assert remote_config.get_paid_model() == "gemini-2.5-flash-lite"


def test_malformed_stored_overrides_are_ignored_not_fatal(fetched):
    """A hand-mangled settings row must not take down config reads (and AI model selection)."""
    db.set_setting(remote_config.OVERRIDES_KEY, "{not json")
    assert remote_config.get_overrides() == {}
    assert _cfg() == fetched


def test_non_dict_overrides_are_ignored(fetched):
    db.set_setting(remote_config.OVERRIDES_KEY, '["a", "list"]')
    assert remote_config.get_overrides() == {}


class TestAdminConfigEndpoints:
    def _client(self, monkeypatch, key="test-admin-key-0123456789"):
        from fastapi.testclient import TestClient
        import main
        monkeypatch.setattr(main, "ADMIN_API_KEY", key)
        return TestClient(main.app), {"Authorization": f"Bearer {key}"}

    def test_requires_the_admin_key(self, monkeypatch, fetched):
        client, _ = self._client(monkeypatch)
        assert client.get("/admin/config").status_code == 403
        assert client.put("/admin/config", json={"overrides": {}}).status_code == 403
        assert client.delete("/admin/config").status_code == 403

    def test_get_exposes_fetched_overrides_and_effective_separately(self, monkeypatch, fetched):
        client, headers = self._client(monkeypatch)
        remote_config.set_overrides({"feature_flags": {"show_upgrade_button": False}})
        body = client.get("/admin/config", headers=headers).json()
        assert body["fetched"]["feature_flags"]["show_upgrade_button"] is True
        assert body["overrides"]["feature_flags"]["show_upgrade_button"] is False
        assert body["effective"]["feature_flags"]["show_upgrade_button"] is False

    def test_put_then_delete_round_trips(self, monkeypatch, fetched):
        client, headers = self._client(monkeypatch)
        res = client.put("/admin/config", headers=headers,
                         json={"overrides": {"enabled_game_types": ["quiz"]}})
        assert res.status_code == 200
        assert res.json()["effective"]["enabled_game_types"] == ["quiz"]

        res = client.delete("/admin/config", headers=headers)
        assert res.status_code == 200
        assert res.json()["overrides"] == {}
        assert "enabled_game_types" not in res.json()["effective"]

    def test_503_when_no_admin_key_is_configured(self, monkeypatch, fetched):
        client, headers = self._client(monkeypatch, key="")
        assert client.get("/admin/config", headers=headers).status_code == 503
