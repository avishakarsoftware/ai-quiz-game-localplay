"""Real libpq parsing must reject remote targets without opening a connection."""
import pytest

psycopg = pytest.importorskip("psycopg")

import postgrest_harness
from postgres_target_safety import connect_local_postgres


@pytest.fixture(autouse=True)
def clear_libpq_routing(monkeypatch):
    for name in ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("dsn,env", [
    ("postgresql://user:secret@db.project.supabase.co/parity", {}),
    ("postgresql://localhost/parity?host=db.project.supabase.co", {}),
    ("postgresql://localhost/parity?hostaddr=203.0.113.10", {}),
    ("host=localhost hostaddr=203.0.113.10 dbname=parity", {}),
    ("host=127.0.0.1,db.project.supabase.co dbname=parity", {}),
    ("postgresql://localhost/parity?hostaddr=127.0.0.1,203.0.113.10", {}),
    ("postgresql://localhost/parity?service=production", {}),
    ("host=localhost dbname=parity", {"PGSERVICE": "production"}),
    ("host=localhost dbname=parity", {"PGHOSTADDR": "203.0.113.10"}),
    ("dbname=parity", {"PGHOST": "db.project.supabase.co"}),
    ("dbname=parity", {}),
    ("not a valid DSN containing secret-password", {}),
])
def test_remote_or_ambiguous_targets_refused_before_connect(monkeypatch, dsn, env):
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: pytest.fail("Opened a network connection"))
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError, match="REFUSING TO RUN") as failure:
        connect_local_postgres(dsn, autocommit=True)
    assert "secret" not in str(failure.value)


@pytest.mark.parametrize("dsn,env", [
    ("postgresql://postgres:parity@127.0.0.1:55450/parity", {}),
    ("postgresql://postgres@localhost/parity", {}),
    ("postgresql://postgres@[::1]/parity", {}),
    ("host=127.0.0.1 port=55450 dbname=parity user=postgres", {}),
    ("host=localhost hostaddr=127.0.0.1 dbname=parity", {}),
    ("host=127.0.0.1,::1 dbname=parity", {}),
    ("host=pg dbname=parity", {}),
    ("dbname=parity", {"PGHOST": "localhost"}),
    ("dbname=parity", {"PGHOSTADDR": "127.0.0.1"}),
    ("host=localhost hostaddr=127.0.0.1 dbname=parity", {"PGHOSTADDR": "203.0.113.10"}),
])
def test_explicit_local_targets_allowed_without_network(monkeypatch, dsn, env):
    calls = []
    result = object()

    def capture_connect(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    monkeypatch.setattr(psycopg, "connect", capture_connect)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    assert connect_local_postgres(dsn, autocommit=True) is result
    assert calls == [((dsn,), {"autocommit": True})]


def test_postgrest_harness_checks_parsed_dsn_before_starting_proxy(monkeypatch):
    monkeypatch.setattr(postgrest_harness, "DSN", "postgresql://localhost/parity?hostaddr=203.0.113.10")
    monkeypatch.setattr(postgrest_harness, "POSTGREST_URL", "http://127.0.0.1:55451")
    monkeypatch.setattr(postgrest_harness, "_ThreadedServer", lambda *args: pytest.fail("Started proxy"))
    with pytest.raises(RuntimeError, match="REFUSING TO RUN"):
        postgrest_harness.start_proxy()
