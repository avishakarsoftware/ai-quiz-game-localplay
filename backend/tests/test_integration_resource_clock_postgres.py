"""Opt-in real producer/consumer SQL contract on a fresh owned Docker fixture.

Requires LOCALPLAY_CLOCK_POSTGRES_DSN, LOCALPLAY_CLOCK_POSTGRES_CONTAINER and,
for cross-app cases, REVELRY_CONTRACT_REPO. Creates/drops only unique test DBs.
"""
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest

from integration_clock import resource_updated_at
from postgres_target_safety import assert_local_postgres_dsn
from test_integration_resource_clock import capture_callbacks, emit_content, PARTY, QUESTIONS


DSN = os.environ.get("LOCALPLAY_CLOCK_POSTGRES_DSN", "")
CONTAINER = os.environ.get("LOCALPLAY_CLOCK_POSTGRES_CONTAINER", "")
REVELRY = os.environ.get("REVELRY_CONTRACT_REPO", "")
ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not DSN or not CONTAINER, reason="requires explicit fresh owned local clock PostgreSQL fixture")


@pytest.fixture(scope="module")
def pg():
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    assert_local_postgres_dsn(DSN)
    info = json.loads(subprocess.check_output(["docker", "inspect", CONTAINER], text=True))[0]
    assert info["Config"]["Labels"]["codex.task"] == "localplay-clock-20261010"
    assert not any(mount["Type"] == "bind" for mount in info["Mounts"])
    ports = info["NetworkSettings"]["Ports"]["5432/tcp"]
    assert all(port["HostIp"] == "127.0.0.1" for port in ports)
    assert str(conninfo_to_dict(DSN)["port"]) in {port["HostPort"] for port in ports}
    name = "localplay_clock_" + uuid.uuid4().hex
    admin = psycopg.connect(DSN, autocommit=True)
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    conn = psycopg.connect(make_conninfo(DSN, dbname=name), autocommit=True)
    conn.execute("SET statement_timeout='20s'")
    try:
        for role in ("anon", "authenticated", "service_role"):
            conn.execute(sql.SQL("DO $$ BEGIN CREATE ROLE {} NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$").format(sql.Identifier(role)))
        for filename in ("games-schema.sql", "games-gamma-schema.sql"):
            conn.execute((ROOT / "sql" / filename).read_text())
        yield conn
    finally:
        conn.close()
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
        admin.close()


@pytest.mark.parametrize("prefix", ["games_", "games_gamma_"])
def test_real_postgres_old_writer_clock_exact_quiz_snapshot_and_delete(pg, prefix):
    content = "clock_" + uuid.uuid4().hex
    first = pg.execute(f"SELECT public.{prefix}save_quiz_pack(%s,%s,%s,%s::jsonb)", ("owner", content, "First", json.dumps(QUESTIONS))).fetchone()[0]["pack"]
    second = pg.execute(f"SELECT public.{prefix}save_quiz_pack(%s,%s,%s,%s::jsonb)", ("owner", content, "Second", json.dumps(QUESTIONS))).fetchone()[0]["pack"]
    assert first["title"] == "First" and second["title"] == "Second"
    assert first["integration_updated_at_us"] < second["integration_updated_at_us"]
    assert isinstance(first["updated_at"], int) and first["updated_at"] < 10**11
    assert first["questions"][0]["text"] == "Question?"
    deleted = pg.execute(f"SELECT public.{prefix}delete_integration_content(%s,%s,'quiz')", ("owner", content)).fetchone()[0]
    assert deleted["integration_updated_at_us"] > second["integration_updated_at_us"]
    # A legacy writer supplies only original columns, even a stale seconds time.
    generated = "legacy_" + uuid.uuid4().hex
    row = pg.execute(f"INSERT INTO public.{prefix}generated_content(id,wallet_id,content_type,title,payload,created_at,updated_at) VALUES(%s,'owner','drawing','Old','{{}}',1,1) RETURNING *", (generated,))
    columns = [column.name for column in row.description]
    original = dict(zip(columns, row.fetchone()))
    deleted = pg.execute(f"SELECT public.{prefix}delete_integration_content(%s,%s,'game')", ("owner", generated)).fetchone()[0]
    assert deleted["title"] == "Old" and deleted["updated_at"] == 1
    assert deleted["integration_updated_at_us"] > original["integration_updated_at_us"]
    tomb = pg.execute(f"SELECT to_jsonb(t) FROM public.{prefix}integration_content_tombstones t WHERE content_id=%s", (generated,)).fetchone()[0]
    assert set(tomb) == {"content_type", "content_id", "occurred_at_us"}
    assert "owner" not in json.dumps(tomb)
    assert pg.execute("SELECT has_function_privilege('anon',%s,'EXECUTE')", (f"public.{prefix}delete_integration_content(text,text,text)",)).fetchone()[0] is False
    assert pg.execute("SELECT has_function_privilege('service_role',%s,'EXECUTE')", (f"public.{prefix}stamp_integration_clock()",)).fetchone()[0] is False


@pytest.mark.parametrize("prefix", ["games_", "games_gamma_"])
def test_concurrent_quiz_saves_return_each_locked_payload_and_clock(pg, prefix):
    import psycopg
    from psycopg.conninfo import make_conninfo
    content = "concurrent_clock_" + uuid.uuid4().hex
    def save(index):
        questions = [{"text": f"Version {index}?", "options": ["A", "B"], "answer_index": 0}]
        with psycopg.connect(make_conninfo(DSN, dbname=pg.info.dbname), autocommit=True) as connection:
            return connection.execute(f"SELECT public.{prefix}save_quiz_pack(%s,%s,%s,%s::jsonb)",
                ("owner", content, f"Version {index}", json.dumps(questions))).fetchone()[0]["pack"]
    with ThreadPoolExecutor(max_workers=4) as workers:
        saved = list(workers.map(save, range(8)))
    assert len({item["integration_updated_at_us"] for item in saved}) == len(saved)
    for item in saved:
        assert item["questions"][0]["text"] == item["title"] + "?"
    current = pg.execute(f"SELECT to_jsonb(p) FROM public.{prefix}quiz_packs p WHERE id=%s", (content,)).fetchone()[0]
    latest = max(saved, key=lambda item: item["integration_updated_at_us"])
    assert current["title"] == latest["title"] and current["integration_updated_at_us"] == latest["integration_updated_at_us"]


@pytest.fixture
def legacy_pg(pg):
    """A separate owned database with the exact current pre-clock schema."""
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    name = "localplay_clock_upgrade_" + uuid.uuid4().hex
    pg.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    connection = psycopg.connect(make_conninfo(DSN, dbname=name), autocommit=True)
    try:
        for filename in ("games-schema.sql", "games-gamma-schema.sql"):
            schema = (ROOT / "sql" / filename).read_text()
            start = schema.index("-- Durable provider ordering clocks.")
            end = schema.index("-- RPCs are server-only.", start)
            connection.execute(schema[:start] + schema[end:])
        connection.execute("CREATE TABLE unrelated_clock_sentinel(id int PRIMARY KEY,value text); INSERT INTO unrelated_clock_sentinel VALUES(1,'untouched')")
        for prefix in ("games_", "games_gamma_"):
            connection.execute(f"INSERT INTO public.{prefix}generated_content(id,wallet_id,content_type,title,payload,created_at,updated_at) VALUES('historical','owner','drawing','Original','{{}}',1,1)")
        yield connection
    finally:
        connection.close()
        pg.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.parametrize("prefix,suffix,other", [("games_", "", "games_gamma_"), ("games_gamma_", "_gamma", "games_")])
def test_prepared_upgrade_isolated_no_backfill_and_old_binary_compatible(legacy_pg, prefix, suffix, other):
    connection = legacy_pg
    before = connection.execute(f"SELECT to_jsonb(c),xmin::text FROM public.{prefix}generated_content c WHERE id='historical'").fetchone()
    other_before = connection.execute(f"SELECT to_jsonb(c),xmin::text FROM public.{other}generated_content c WHERE id='historical'").fetchone()
    migration = (ROOT / f"sql/migrations/20261010T010000_integration_resource_clocks{suffix}.sql").read_text()
    connection.execute(migration)
    connection.execute(migration)  # Reinstallation must remain evidence-neutral.
    after = connection.execute(f"SELECT to_jsonb(c),xmin::text FROM public.{prefix}generated_content c WHERE id='historical'").fetchone()
    assert after[0].pop("integration_updated_at_us") is None
    assert after == before
    assert connection.execute(f"SELECT to_jsonb(c),xmin::text FROM public.{other}generated_content c WHERE id='historical'").fetchone() == other_before
    assert connection.execute("SELECT value FROM unrelated_clock_sentinel").fetchone()[0] == "untouched"
    assert connection.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name='integration_updated_at_us'", (other + "generated_content",)).fetchone()[0] == 0
    # Rollback code writes only original columns; clocks are provided by the DB.
    first = connection.execute(f"UPDATE public.{prefix}generated_content SET title='Old writer',updated_at=1 WHERE id='historical' RETURNING to_jsonb({prefix}generated_content)").fetchone()[0]
    second = connection.execute(f"UPDATE public.{prefix}generated_content SET title='Old writer again',updated_at=1,integration_updated_at_us=999999999999999999 WHERE id='historical' RETURNING to_jsonb({prefix}generated_content)").fetchone()[0]
    assert second["integration_updated_at_us"] > first["integration_updated_at_us"]
    assert second["integration_updated_at_us"] < 10**16 and second["updated_at"] == first["updated_at"] == 1
    saved = connection.execute(f"SELECT public.{prefix}save_quiz_pack('owner','legacy-rpc','Old client',%s::jsonb)", (json.dumps(QUESTIONS),)).fetchone()[0]
    assert saved["saved"] is True and saved["id"] == "legacy-rpc"  # Original client keys preserved.
    deleted = connection.execute(f"SELECT public.{prefix}delete_integration_content('owner','historical','game')").fetchone()[0]
    assert deleted["title"] == "Old writer again" and deleted["integration_updated_at_us"] > second["integration_updated_at_us"]
    recreated = connection.execute(f"INSERT INTO public.{prefix}generated_content(id,wallet_id,content_type,title,payload,created_at,updated_at) VALUES('historical','owner','drawing','Recreated','{{}}',1,1) RETURNING to_jsonb({prefix}generated_content)").fetchone()[0]
    assert recreated["integration_updated_at_us"] > deleted["integration_updated_at_us"]
    connection.execute(f"SELECT public.{prefix}delete_account('owner')")
    tombs = connection.execute(f"SELECT to_jsonb(t) FROM public.{prefix}integration_content_tombstones t").fetchall()
    assert {item[0]["content_type"] for item in tombs} == {"game", "quiz"}
    assert all(set(item[0]) == {"content_type", "content_id", "occurred_at_us"} for item in tombs)
    assert "owner" not in json.dumps(tombs) and "Old client" not in json.dumps(tombs)


@pytest.mark.parametrize("prefix", ["games_", "games_gamma_"])
def test_concurrent_physical_delete_and_same_id_recreate_rejects_stale_clock(pg, prefix):
    """An insert can stamp before its unique-index wait on an in-flight delete."""
    import psycopg
    from psycopg.conninfo import make_conninfo
    content = "reuse_" + uuid.uuid4().hex
    key = uuid.uuid4().int % (2**62)
    function = "clock_fixture_barrier_" + uuid.uuid4().hex
    deleting, inserting = "clock_delete_" + uuid.uuid4().hex, "clock_insert_" + uuid.uuid4().hex
    pg.execute(f"INSERT INTO public.{prefix}generated_content(id,wallet_id,content_type,title,payload,created_at,updated_at) VALUES(%s,'owner','drawing','Original','{{}}',1,1)", (content,))
    pg.execute(f"CREATE FUNCTION public.{function}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_advisory_xact_lock({key}); RETURN OLD; END $$")
    pg.execute(f"CREATE TRIGGER aaa_clock_fixture_barrier AFTER DELETE ON public.{prefix}generated_content FOR EACH ROW EXECUTE FUNCTION public.{function}()")
    pg.execute("SELECT pg_advisory_lock(%s)", (key,))
    def delete():
        with psycopg.connect(make_conninfo(DSN, dbname=pg.info.dbname), autocommit=True, application_name=deleting) as connection:
            connection.execute(f"DELETE FROM public.{prefix}generated_content WHERE id=%s", (content,))
    def insert():
        try:
            with psycopg.connect(make_conninfo(DSN, dbname=pg.info.dbname), autocommit=True, application_name=inserting) as connection:
                return connection.execute(f"INSERT INTO public.{prefix}generated_content(id,wallet_id,content_type,title,payload,created_at,updated_at) VALUES(%s,'owner','drawing','Recreated','{{}}',1,1) RETURNING to_jsonb({prefix}generated_content)", (content,)).fetchone()[0]
        except psycopg.errors.SerializationFailure as error:
            return str(error)
    def wait_for_lock(application, event):
        until = time.monotonic() + 5
        while time.monotonic() < until:
            if pg.execute("SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event=%s", (application,event)).fetchone():
                return
            time.sleep(.01)
        raise AssertionError(f"Fixture did not reach {event} barrier")
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            removed = workers.submit(delete)
            wait_for_lock(deleting, "advisory")
            recreated = workers.submit(insert)
            try:
                wait_for_lock(inserting, "transactionid")
            finally:
                pg.execute("SELECT pg_advisory_unlock(%s)", (key,))
            removed.result(timeout=5)
            outcome = recreated.result(timeout=5)
        assert isinstance(outcome,str) and "integration_clock_retry" in outcome
        assert pg.execute(f"SELECT 1 FROM public.{prefix}generated_content WHERE id=%s", (content,)).fetchone() is None
        # Retrying from a fresh statement returns an exact, later snapshot.
        retried = insert()
        deleted_at = pg.execute(f"SELECT occurred_at_us FROM public.{prefix}integration_content_tombstones WHERE content_type='game' AND content_id=%s", (content,)).fetchone()[0]
        assert retried["title"] == "Recreated" and retried["integration_updated_at_us"] > deleted_at
    finally:
        pg.execute("SELECT pg_advisory_unlock(%s)", (key,))
        pg.execute(f"DROP TRIGGER aaa_clock_fixture_barrier ON public.{prefix}generated_content")
        pg.execute(f"DROP FUNCTION public.{function}()")


@pytest.fixture(scope="module")
def consumer(pg):
    if not REVELRY:
        pytest.skip("requires explicit Revelry source checkout for real pending SQL contract")
    root = Path(REVELRY).resolve()
    pg.execute("""CREATE TABLE users(id uuid PRIMARY KEY,name text);
      CREATE TABLE parties(id uuid PRIMARY KEY); CREATE TABLE gamma_parties(id uuid PRIMARY KEY);
      CREATE TABLE feed_posts(id uuid PRIMARY KEY,party_id uuid REFERENCES parties);
      CREATE TABLE gamma_feed_posts(id uuid PRIMARY KEY,party_id uuid REFERENCES gamma_parties);
      CREATE TABLE other_app_clock_sentinel(id int PRIMARY KEY,value text);
      INSERT INTO other_app_clock_sentinel VALUES(1,'untouched');""")
    for timestamp in ("20260523000000", "20260523001000", "20260524000000", "20260524134500", "20260706160000", "20260709160000"):
        paths = list((root / "supabase/migrations").glob(timestamp + "_*.sql"))
        assert len(paths) == 1
        pg.execute(paths[0].read_text())
    pg.execute((root / "supabase/migrations/20261005130000_localplay_callback_recovery.sql").read_text())
    pg.execute((root / "supabase/gamma-upgrades/20261005131000_localplay_callback_recovery_gamma_only.sql").read_text())
    spec = importlib.util.spec_from_file_location("real_revelry_callback_contract", root / "backend/app/games/callbacks.py")
    callbacks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(callbacks)
    return callbacks


def process_content(pg, callbacks, captured, prefix, party, setup, revision, op):
    event = callbacks.verify_callback(captured["raw"], captured["headers"], "clock-test-synthetic-secret")["event"]
    at = event["occurred_at"]
    values = {"localplay_content_id": event["content_id"], "game_type": "quiz", "status": "ready", "title": captured["body"]["payload"]["content"]["title"]}
    projection = {"schema_version": 1, "source": "callback", "effective_occurred_at": at, "checkin": None,
                  "lineage": [], "sessions": [], "prepared": [{"op": op, "id": setup, "values": values, "previous_content_id": None, "effective_occurred_at": at}]}
    return pg.execute(f"SELECT public.{prefix}apply_localplay_callback(%s::jsonb,%s::jsonb,%s::jsonb)",
        (json.dumps(event), json.dumps(projection), json.dumps({"party_revision": revision}))).fetchone()[0]


@pytest.mark.parametrize("provider,consumer_prefix", [("games_", ""), ("games_gamma_", "gamma_")])
def test_same_second_real_producer_envelopes_apply_to_existing_consumer_sql(pg, consumer, capture_callbacks, provider, consumer_prefix):
    import main
    party, setup = str(uuid.uuid4()), str(uuid.uuid4())
    pg.execute(f"INSERT INTO public.{consumer_prefix}parties(id) VALUES(%s)", (party,))
    content = "paired_" + uuid.uuid4().hex
    # Freeze the legacy seconds field while database clocks remain authoritative.
    first = pg.execute(f"SELECT public.{provider}save_quiz_pack(%s,%s,%s,%s::jsonb)", ("owner", content, "First", json.dumps(QUESTIONS))).fetchone()[0]["pack"]
    second = pg.execute(f"UPDATE public.{provider}quiz_packs SET title='Second',updated_at=%s WHERE id=%s RETURNING to_jsonb({provider}quiz_packs)", (first["updated_at"], content)).fetchone()[0]
    second["questions"] = QUESTIONS
    assert first["updated_at"] == second["updated_at"]
    for snapshot, kind in ((first, "content.created"), (second, "content.updated")):
        import asyncio
        asyncio.run(main._send_revelry_callback(kind, {"external_container_id": party, "content_id": content, "content": main._prepared_content_summary(snapshot)}))
    one = process_content(pg, consumer, capture_callbacks[0], consumer_prefix, party, setup, 0, "insert")
    two = process_content(pg, consumer, capture_callbacks[1], consumer_prefix, party, setup, one["party_revision"], "update")
    assert two["outcome"] == "applied" and two["prepared"][0]["title"] == "Second"
    duplicate = process_content(pg, consumer, capture_callbacks[1], consumer_prefix, party, setup, 999, "update")
    assert duplicate["duplicate"] is True
    assert pg.execute("SELECT value FROM other_app_clock_sentinel WHERE id=1").fetchone()[0] == "untouched"


@pytest.mark.parametrize("consumer_prefix", ["", "gamma_"])
@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("terminal", ["cancelled", "expired", "superseded", "complete"])
def test_missed_terminal_callback_recovers_via_real_provider_poll_and_consumer_sql(pg, consumer, capture_callbacks, consumer_prefix, started, terminal):
    import main
    from socket_manager import socket_manager
    provider = "games_gamma_" if consumer_prefix else "games_"
    party, row_id, session_id = str(uuid.uuid4()), str(uuid.uuid4()), uuid.uuid4().hex
    pg.execute(f"INSERT INTO public.{consumer_prefix}parties(id) VALUES(%s)", (party,))
    status = "active" if started else "lobby"
    result = pg.execute(f"INSERT INTO public.{provider}game_sessions(id,host_app,external_container_id,external_container_type,game_type,room_code,status,created_at,started_at,expires_at,last_activity_at,updated_at) VALUES(%s,'revelry',%s,'party','quiz','CLOCK',%s,1,%s,9999999999,1,1) RETURNING to_jsonb({provider}game_sessions)", (session_id, party, status, 1 if started else None)).fetchone()[0]
    socket_manager._send_integration_callback("session.started" if started else "session.created", result)
    event = consumer.verify_callback(capture_callbacks[0]["raw"], capture_callbacks[0]["headers"], "clock-test-synthetic-secret")["event"]
    def projection(source, snapshot):
        at = main._format_session(snapshot)["updated_at"]
        return {"schema_version":1,"source":source,"sessions":[{"op":"insert" if source=="callback" else "update","id":row_id,"values":{"localplay_session_id":session_id,"game_type":"quiz","status":snapshot["status"],"joinable":snapshot["joinable"]},"effective_occurred_at":at}],"prepared":[],"lineage":[],"checkin":None,"effective_occurred_at":at}
    first = pg.execute(f"SELECT public.{consumer_prefix}apply_localplay_callback(%s::jsonb,%s::jsonb,%s::jsonb)", (json.dumps(event),json.dumps(projection("callback", result)),json.dumps({"party_revision":0}))).fetchone()[0]
    closed = pg.execute(f"UPDATE public.{provider}game_sessions SET status=%s,joinable=false,updated_at=1 WHERE id=%s RETURNING to_jsonb({provider}game_sessions)", (terminal,session_id)).fetchone()[0]
    # Intentionally emit no terminal callback. Poll must carry its durable clock.
    recovered = pg.execute(f"SELECT public.{consumer_prefix}apply_localplay_projection(%s,'status',%s::jsonb,%s::jsonb)", (party,json.dumps(projection("status",closed)),json.dumps({"party_revision":first["party_revision"]}))).fetchone()[0]
    assert recovered["sessions"][0]["status"] == terminal
    assert recovered["sessions"][0]["joinable"] is False
    assert main._format_session(closed)["updated_at"] > event["occurred_at"].replace("+00:00","Z")
