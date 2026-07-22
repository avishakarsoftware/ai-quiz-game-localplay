"""Fail-fast guard against a deployment accidentally running on ephemeral SQLite.

SQLite in a deployed container is destroyed on every rebuild, so gamma/prod must use Supabase.
config.validate_runtime_db_config() is the startup backstop; these tests pin its decision table.
"""
import pytest

import config


def _set(monkeypatch, *, backend, url="", key="", env="local"):
    monkeypatch.setattr(config, "DB_BACKEND", backend)
    monkeypatch.setattr(config, "SUPABASE_URL", url)
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", key)
    monkeypatch.setattr(config, "ENVIRONMENT", env)


def test_local_sqlite_dev_is_allowed(monkeypatch):
    # The default developer setup: sqlite, no Supabase vars, ENVIRONMENT=local. Must not raise.
    _set(monkeypatch, backend="sqlite")
    config.validate_runtime_db_config()


def test_supabase_with_full_creds_is_allowed(monkeypatch):
    _set(monkeypatch, backend="supabase", url="https://x.supabase.co", key="svc-key", env="gamma")
    config.validate_runtime_db_config()


def test_sqlite_with_supabase_creds_present_is_rejected(monkeypatch):
    # The footgun: creds are configured (clear deploy intent) but the backend is still sqlite.
    _set(monkeypatch, backend="sqlite", url="https://x.supabase.co", key="svc-key")
    with pytest.raises(config.RuntimeConfigError, match="ephemeral"):
        config.validate_runtime_db_config()


def test_sqlite_in_named_deploy_environment_is_rejected(monkeypatch):
    # Explicit LOCALPLAY_ENV=production but sqlite backend, even with no Supabase vars set.
    _set(monkeypatch, backend="sqlite", env="production")
    with pytest.raises(config.RuntimeConfigError):
        config.validate_runtime_db_config()


def test_supabase_without_credentials_is_rejected(monkeypatch):
    _set(monkeypatch, backend="supabase", url="", key="", env="gamma")
    with pytest.raises(config.RuntimeConfigError, match="SUPABASE_URL"):
        config.validate_runtime_db_config()


def test_supabase_with_only_url_is_rejected(monkeypatch):
    _set(monkeypatch, backend="supabase", url="https://x.supabase.co", key="", env="gamma")
    with pytest.raises(config.RuntimeConfigError):
        config.validate_runtime_db_config()
