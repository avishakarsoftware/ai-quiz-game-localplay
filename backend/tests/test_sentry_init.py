"""_init_sentry: observability must be a feature, never a dependency (REVIEW-2026-08 O2)."""
import builtins

import config
import main


def test_noop_without_dsn(monkeypatch):
    """Default state: no DSN, nothing imported, nothing initialized."""
    monkeypatch.setattr(config, "SENTRY_DSN", "")
    real_import = builtins.__import__

    def tripwire(name, *args, **kwargs):
        assert name != "sentry_sdk", "sentry_sdk must not even be imported without a DSN"
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", tripwire)
    main._init_sentry()  # must not raise, must not import


def test_survives_missing_sdk(monkeypatch):
    """DSN set but the package is absent (e.g. old image): startup must proceed. An
    observability failure that takes the app down would be worse than no observability."""
    monkeypatch.setattr(config, "SENTRY_DSN", "https://key@example.ingest.sentry.io/1")
    real_import = builtins.__import__

    def fail_sentry(name, *args, **kwargs):
        if name == "sentry_sdk":
            raise ImportError("sentry_sdk not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_sentry)
    main._init_sentry()  # must not raise


def test_initializes_with_environment_tag(monkeypatch):
    """When the SDK is present, init carries the DSN and deploy environment so prod and
    gamma events are distinguishable."""
    captured = {}

    class FakeSdk:
        @staticmethod
        def init(**kwargs):
            captured.update(kwargs)

    real_import = builtins.__import__

    def fake_sentry(name, *args, **kwargs):
        if name == "sentry_sdk":
            return FakeSdk
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(config, "SENTRY_DSN", "https://key@example.ingest.sentry.io/1")
    monkeypatch.setattr(config, "ENVIRONMENT", "gamma")
    monkeypatch.setattr(builtins, "__import__", fake_sentry)
    main._init_sentry()
    assert captured["dsn"] == "https://key@example.ingest.sentry.io/1"
    assert captured["environment"] == "gamma"
    assert captured["traces_sample_rate"] == 0
