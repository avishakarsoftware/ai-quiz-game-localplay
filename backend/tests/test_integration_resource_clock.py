"""Durable callback/poll clocks, including legacy writers and exact snapshots."""
import asyncio
from datetime import datetime, timezone
import json
import sqlite3
from types import SimpleNamespace

import pytest

import config
import db
import main
from integration_clock import resource_updated_at
from socket_manager import socket_manager


QUESTIONS = [{"text": "Question?", "options": ["A", "B"], "answer_index": 0}]
PARTY = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def capture_callbacks(monkeypatch):
    calls = []
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        async def post(self, url, *, content, headers):
            calls.append({"raw": content, "body": json.loads(content), "headers": dict(headers)})
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)
    class SyncClient(Client):
        def post(self, url, *, content, headers):
            calls.append({"raw": content, "body": json.loads(content), "headers": dict(headers)})
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)
    monkeypatch.setattr(config, "REVELRY_CALLBACK_URL", "https://callback.invalid")
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "clock-test-synthetic-secret")
    monkeypatch.setattr(main.httpx, "AsyncClient", Client)
    monkeypatch.setattr(main.httpx, "Client", SyncClient)
    return calls


def emit_content(snapshot, event_type="content.updated"):
    asyncio.run(main._send_revelry_callback(event_type, {
        "external_container_id": PARTY, "content_id": snapshot["id"],
        "content": main._prepared_content_summary(snapshot),
    }))


def create_session():
    return db.create_game_session({
        "id": "provider-clock-session", "host_app": "revelry", "external_container_id": PARTY,
        "external_container_type": "party", "game_type": "quiz", "room_code": "CLOCK",
    })


@pytest.mark.parametrize("kind", ["quiz", "drawing"])
def test_same_second_saves_have_strict_clocks_and_exact_callback_snapshots(monkeypatch, capture_callbacks, kind):
    fixed_second = int(main.time.time())
    monkeypatch.setattr(db.time, "time", lambda: fixed_second)
    save = (lambda title: db.save_quiz_pack("owner", title, QUESTIONS, "clock-content")) if kind == "quiz" else (
        lambda title: db.save_game_content("owner", "drawing", title, {"game": {"prompts": ["Safe prompt"]}}, "clock-content"))
    first, second = save("First"), save("Second")
    assert first["updated_at"] == second["updated_at"] == fixed_second
    assert first["integration_updated_at_us"] < second["integration_updated_at_us"]
    # Emitting the older saved version later must retain its own title AND clock.
    emit_content(first)
    emit_content(second)
    for snapshot, call in zip((first, second), capture_callbacks):
        assert call["body"]["occurred_at"] == resource_updated_at(snapshot)
        assert call["body"]["payload"]["content"]["updated_at"] == resource_updated_at(snapshot)
        assert call["body"]["payload"]["content"]["title"] == snapshot["title"]
    assert capture_callbacks[0]["body"]["idempotency_key"] != capture_callbacks[1]["body"]["idempotency_key"]


@pytest.mark.parametrize("status", ["cancelled", "expired", "superseded", "complete"])
@pytest.mark.parametrize("started", [False, True])
def test_terminal_poll_and_runtime_callback_share_later_resource_clock(capture_callbacks, status, started):
    session = create_session()
    if started:
        session = db.update_game_session(session["id"], {"status": "active", "started_at": int(main.time.time())})
    before = resource_updated_at(session)
    closed = db.update_game_session(session["id"], {"status": status, "joinable": False})
    polled = main._format_session(closed)
    socket_manager._send_integration_callback(f"session.{status if status != 'complete' else 'completed'}", closed)
    assert before < polled["updated_at"] == capture_callbacks[0]["body"]["occurred_at"]
    assert polled["status"] == status and polled["joinable"] is False
    assert polled["completed_at"] is None


@pytest.mark.parametrize("transition", ["started", "completed", "cancelled"])
def test_runtime_missing_saved_transition_emits_no_callback(monkeypatch, capture_callbacks, transition):
    session = create_session()
    monkeypatch.setattr(db, "update_game_session", lambda *_args, **_kwargs: None)
    room = SimpleNamespace(room_code=session["room_code"])
    if transition == "started":
        socket_manager._mark_game_session_started_blocking(room)
    elif transition == "completed":
        socket_manager._mark_game_session_complete_blocking(room, {"title":"New result","players":[]})
    else:
        socket_manager._mark_game_session_closed_blocking(room,"host_cancelled","Closed")
    assert capture_callbacks == []
    assert db.get_game_session(session["id"])["status"] == "lobby"


def test_cancel_missing_saved_transition_returns_404_and_emits_no_callback(monkeypatch, capture_callbacks):
    from fastapi import HTTPException
    session = create_session()
    monkeypatch.setattr(db, "update_game_session", lambda *_args, **_kwargs: None)
    context = main.RevelryExternalContext(host_app="revelry",external_container_id=PARTY,external_container_type="party")
    actor = main.RevelryActor(external_user_id="host",capabilities=["manage_games"])
    with pytest.raises(HTTPException) as error:
        asyncio.run(main._cancel_revelry_session(session,context=context,actor=actor))
    assert error.value.status_code == 404 and capture_callbacks == []
    assert db.get_game_session(session["id"])["status"] == "lobby"


@pytest.mark.parametrize("quiz", [False, True])
def test_delete_returns_exact_durable_later_clock_and_retains_no_personal_data(quiz, capture_callbacks):
    original = db.save_quiz_pack("private-owner", "Private title", QUESTIONS) if quiz else db.save_game_content(
        "private-owner", "drawing", "Private title", {"game": {"prompts": ["Private prompt"]}})
    delete = db.delete_quiz_pack if quiz else db.delete_game_content
    deleted = delete("private-owner", original["id"], return_snapshot=True)
    assert deleted["integration_updated_at_us"] > original["integration_updated_at_us"]
    emit_content(deleted, "content.deleted")
    assert capture_callbacks[0]["body"]["occurred_at"] == resource_updated_at(deleted)
    tombstones = [dict(row) for row in db._get_conn().execute("SELECT * FROM integration_content_tombstones")]
    assert all(set(row) == {"content_type", "content_id", "occurred_at_us"} for row in tombstones)
    assert "private-owner" not in json.dumps(tombstones) and "Private" not in json.dumps(tombstones)


def test_trigger_works_with_legacy_connection_and_keeps_seconds_units():
    # A rollback writer has no custom SQL functions and supplies only old columns.
    legacy = sqlite3.connect(db.DB_PATH)
    legacy.execute("INSERT INTO generated_content(id,wallet_id,content_type,title,payload,created_at,updated_at) VALUES('legacy-clock','owner','drawing','Old','{}',1,1)")
    legacy.commit()
    first = db.get_game_content("owner", "legacy-clock")
    legacy.execute("UPDATE generated_content SET title='New',updated_at=1 WHERE id='legacy-clock'")
    legacy.commit()
    second = db.get_game_content("owner", "legacy-clock")
    legacy.close()
    assert first["updated_at"] == second["updated_at"] == 1
    assert first["integration_updated_at_us"] < second["integration_updated_at_us"]


@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("payload_update", [False, True])
@pytest.mark.parametrize("supplied", [1, 999999999999999999])
def test_sqlite_rejects_private_clock_overrides_without_changing_resource(recursive, payload_update, supplied):
    original = db.save_game_content("owner", "drawing", "Original", {"game": {"prompts": ["cat"]}})
    legacy = sqlite3.connect(db.DB_PATH)
    legacy.execute(f"PRAGMA recursive_triggers={'ON' if recursive else 'OFF'}")
    try:
        change = "title='Override'," if payload_update else ""
        with pytest.raises(sqlite3.IntegrityError, match="integration_clock_override"):
            legacy.execute(f"UPDATE generated_content SET {change}integration_updated_at_us=? WHERE id=?", (supplied, original["id"]))
        legacy.rollback()
        assert db.get_game_content("owner", original["id"]) == original
        # Ordinary rollback-binary payload writes still work in either mode.
        legacy.execute("UPDATE generated_content SET title='Legacy update',updated_at=1 WHERE id=?", (original["id"],))
        legacy.commit()
        updated = db.get_game_content("owner", original["id"])
        assert updated["title"] == "Legacy update" and updated["integration_updated_at_us"] > original["integration_updated_at_us"]
        with pytest.raises(sqlite3.IntegrityError, match="integration_clock_override"):
            legacy.execute("INSERT INTO generated_content(id,wallet_id,content_type,title,payload,created_at,updated_at,integration_updated_at_us) VALUES('injected-clock','owner','drawing','Injected','{}',1,1,999999999999999999)")
        legacy.rollback()
        assert db.get_game_content("owner", "injected-clock") is None
    finally:
        legacy.close()


def test_clock_format_preserves_microseconds_without_float_rounding():
    value = 1791630000123456
    assert resource_updated_at({"integration_updated_at_us": value}) == "2026-10-10T11:00:00.123456Z"
    assert resource_updated_at({}) is None
    assert resource_updated_at({"updated_at": 1791630000}) == "2026-10-10T11:00:00.000000Z"


def test_sqlite_upgrade_keeps_historical_payloads_and_clocks_unfreshened():
    db.save_quiz_pack("owner", "Historical quiz", QUESTIONS)
    db.save_game_content("owner", "drawing", "Historical drawing", {"game":{"prompts":["cat"]}})
    create_session()
    connection = db._get_conn()
    # Recreate the pre-clock version using the original schema and old data.
    for trigger in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'integration_clock_%'").fetchall():
        connection.execute(f"DROP TRIGGER {trigger['name']}")
    tables = ("custom_quiz_packs","generated_content","game_sessions")
    for table in tables:
        connection.execute(f"ALTER TABLE {table} DROP COLUMN integration_updated_at_us")
    connection.execute("DROP TABLE integration_content_tombstones")
    connection.commit()
    before = {table:[dict(row) for row in connection.execute(f"SELECT * FROM {table}")] for table in tables}
    changes = connection.total_changes
    db._migrate_integration_resource_clocks()
    db._migrate_integration_resource_clocks()
    assert connection.total_changes == changes
    for table in tables:
        rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
        assert all(row.pop("integration_updated_at_us") is None for row in rows)
        assert rows == before[table]
    assert connection.execute("SELECT count(*) FROM integration_content_tombstones").fetchone()[0] == 0


def test_supabase_quiz_save_uses_atomic_snapshot_without_later_read(monkeypatch):
    import supabase_db
    pack = {"id": "pack-clock", "owner_wallet_id": "owner", "title": "Saved version", "integration_updated_at_us": 1791630000123456, "questions": QUESTIONS}
    class Adapter:
        def select(self, *args, **kwargs):
            # Ownership preflight only; a subsequent pack/contents read is a race.
            assert args == ("quiz_packs",)
            assert kwargs == {"filters": {"id": "eq.pack-clock"}, "limit": 1}
            return []
        def rpc(self, name, payload):
            assert name == "save_quiz_pack"
            return {"saved": True, "id": "pack-clock", "pack": pack}
    monkeypatch.setattr(supabase_db, "_sb", Adapter)
    saved = supabase_db.save_quiz_pack("owner", "Saved version", QUESTIONS, "pack-clock")
    assert saved == pack
