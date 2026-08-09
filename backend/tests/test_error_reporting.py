"""error_reporting: observability must be a feature, never a dependency.

Replaces the Sentry wiring (dropped 2026-08-09 — a third-party account and vendor SDK for a job
Google already does inside the project that hosts the VM). Same invariants as before: inert by
default, survives a broken client, and cannot take the app down.
"""
import builtins
import logging

import config
import error_reporting


def teardown_function() -> None:
    """Never leave a handler attached to the root logger — it would follow every later test."""
    error_reporting.shutdown()


def test_noop_when_disabled(monkeypatch):
    """Default state: flag off, nothing imported, no handler attached."""
    monkeypatch.setattr(config, "ERROR_REPORTING_ENABLED", False)
    real_import = builtins.__import__

    def tripwire(name, *args, **kwargs):
        assert not name.startswith("google.cloud.logging"), \
            "the Cloud Logging client must not be imported when the flag is off"
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", tripwire)
    before = len(logging.getLogger().handlers)
    assert error_reporting.init() is False
    assert len(logging.getLogger().handlers) == before


def test_survives_missing_package(monkeypatch):
    """Flag on but the library absent (older image): startup proceeds. An observability failure
    that crashed the app would be strictly worse than having no observability."""
    monkeypatch.setattr(config, "ERROR_REPORTING_ENABLED", True)
    monkeypatch.setattr(error_reporting, "_handler", None)
    real_import = builtins.__import__

    def fail_google(name, *args, **kwargs):
        if name.startswith("google.cloud.logging"):
            raise ImportError("google-cloud-logging not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_google)
    assert error_reporting.init() is False   # reported, not raised


def test_survives_credential_failure(monkeypatch):
    """On a machine with no GCE metadata / ADC, Client() raises. Must be swallowed."""
    monkeypatch.setattr(config, "ERROR_REPORTING_ENABLED", True)
    monkeypatch.setattr(error_reporting, "_handler", None)

    import google.cloud.logging

    def boom(*a, **k):
        raise RuntimeError("could not determine credentials")

    monkeypatch.setattr(google.cloud.logging, "Client", boom)
    assert error_reporting.init() is False


class _FakeHandler(logging.Handler):
    """Stands in for CloudLoggingHandler so nothing touches the network."""

    def __init__(self, client, name=""):  # noqa: D107 — mirrors the real signature
        super().__init__()
        self.log_name = name
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


def _install_fake(monkeypatch) -> _FakeHandler:
    monkeypatch.setattr(config, "ERROR_REPORTING_ENABLED", True)
    monkeypatch.setattr(error_reporting, "_handler", None)
    import google.cloud.logging
    from google.cloud.logging import handlers as gcl_handlers

    monkeypatch.setattr(google.cloud.logging, "Client", lambda *a, **k: object())
    created: list[_FakeHandler] = []

    def factory(client, name="", **kwargs):
        h = _FakeHandler(client, name=name)
        created.append(h)
        return h

    monkeypatch.setattr(gcl_handlers, "CloudLoggingHandler", factory)
    assert error_reporting.init() is True
    return created[0]


def test_reports_errors_but_not_info(monkeypatch):
    handler = _install_fake(monkeypatch)
    log = logging.getLogger("test.reporting")
    log.info("routine chatter")
    log.warning("also not an incident")
    log.error("this is an incident")
    levels = [r.levelno for r in handler.records]
    assert logging.ERROR in levels, "ERROR must be reported"
    assert logging.INFO not in levels and logging.WARNING not in levels, \
        f"only ERROR+ should ship; got {levels} — a chatty handler burns log quota and buries signal"


def test_captures_the_traceback(monkeypatch):
    """The stack trace IS the signal Error Reporting groups on. A bare one-line message is
    ingested as a plain log entry and never becomes an error event."""
    handler = _install_fake(monkeypatch)
    log = logging.getLogger("test.reporting")
    try:
        raise ValueError("wallet exploded")
    except ValueError:
        log.error("Background task %r crashed", "question-timer:ABC123", exc_info=True)

    assert handler.records, "nothing was reported"
    rendered = handler.format(handler.records[-1])
    assert "Traceback" in rendered, f"no traceback in the payload: {rendered[:200]}"
    assert "wallet exploded" in rendered
    assert "question-timer:ABC123" in rendered, "the task name must survive into the report"


def test_log_name_separates_environments(monkeypatch):
    """A gamma stack trace must not look like a production incident."""
    monkeypatch.setattr(config, "ENVIRONMENT", "gamma")
    handler = _install_fake(monkeypatch)
    assert "gamma" in handler.log_name


def test_init_is_idempotent(monkeypatch):
    handler = _install_fake(monkeypatch)
    root_before = len(logging.getLogger().handlers)
    assert error_reporting.init() is True      # second call
    assert len(logging.getLogger().handlers) == root_before, \
        "a double init must not attach a second handler (every error would report twice)"
    assert handler is error_reporting._handler
