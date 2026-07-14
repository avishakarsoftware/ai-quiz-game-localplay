"""Tests for room_snapshot — live games surviving a backend restart."""
import asyncio
import json
import os
import time

import pytest

import room_snapshot
from socket_manager import Room, SocketManager


@pytest.fixture(autouse=True)
def snapshot_dir(tmp_path, monkeypatch):
    d = tmp_path / "room_snapshots"
    monkeypatch.setattr(room_snapshot, "SNAPSHOT_DIR", str(d))
    return d


def _quiz_room(code="SNAP01", state="LOBBY"):
    quiz = {"quiz_title": "T", "questions": [{"question": "q1", "options": ["a", "b"], "correct_index": 0}]}
    room = Room(code, quiz, time_limit=15, organizer_token="sekrit", game_type="quiz")
    room.state = state
    room.players["client_a"] = {"nickname": "Maya", "score": 500, "prev_rank": 1, "streak": 2,
                                "avatar": "🦊", "connection_status": "connected"}
    room.player_tokens["Maya"] = "session_token_maya"
    room.answered_players.add("client_a")
    room.bonus_questions.add(1)
    return room


def _restore_one(manager=None):
    factory = lambda code, gd, tl, tok, cid, gt, bm: Room(
        code, gd, tl, organizer_token=tok, content_id=cid, game_type=gt, billing_mode=bm)
    return room_snapshot.load_all(factory, ttl_seconds=1800)


class TestSnapshotRoundTrip:
    def test_durable_fields_survive(self, snapshot_dir):
        room = _quiz_room(state="QUESTION")
        room.current_question_index = 3
        room.question_start_time = time.time()
        room_snapshot.save_all({room.room_code: room})

        restored = _restore_one()
        assert len(restored) == 1
        r = restored[0]
        assert r.room_code == "SNAP01"
        assert r.organizer_token == "sekrit"          # organizer can reclaim
        assert r.player_tokens["Maya"] == "session_token_maya"  # player can reclaim
        assert r.current_question_index == 3
        assert r.quiz["questions"][0]["question"] == "q1"
        assert isinstance(r.answered_players, set) and "client_a" in r.answered_players
        assert isinstance(r.bonus_questions, set) and 1 in r.bonus_questions

    def test_live_members_not_serialized(self, snapshot_dir):
        room = _quiz_room()
        room_snapshot.save_all({room.room_code: room})
        data = json.loads((snapshot_dir / "SNAP01.json").read_text())
        for attr in ("connections", "organizer", "spectators", "timer_task", "lock",
                     "msg_timestamps", "mafia_timer_task"):
            assert attr not in data

    def test_restored_room_has_fresh_live_members(self, snapshot_dir):
        room = _quiz_room()
        room_snapshot.save_all({room.room_code: room})
        r = _restore_one()[0]
        assert r.connections == {} and r.spectators == {}
        assert r.organizer is None and r.organizer_id is None
        assert r.timer_task is None
        assert isinstance(r.lock, asyncio.Lock)


class TestRestoreNormalization:
    def test_lobby_seats_marked_offline(self, snapshot_dir):
        room = _quiz_room(state="LOBBY")
        room_snapshot.save_all({room.room_code: room})
        r = _restore_one()[0]
        assert r.players["client_a"]["connection_status"] == "offline"
        assert r.players["client_a"]["disconnected_at"] > 0

    def test_active_seats_move_to_disconnected_players(self, snapshot_dir):
        room = _quiz_room(state="QUESTION")
        room_snapshot.save_all({room.room_code: room})
        r = _restore_one()[0]
        assert r.players == {}
        seat = r.disconnected_players["Maya"]
        assert seat["score"] == 500 and seat["streak"] == 2
        assert seat["_answered_client_id"] == "client_a"  # answered state reclaimable

    def test_running_housie_autocaller_restores_stopped(self, snapshot_dir):
        room = _quiz_room(state="QUESTION")
        room.housie_auto_status = "running"
        room.housie_next_auto_call_at = "soon"
        room_snapshot.save_all({room.room_code: room})
        r = _restore_one()[0]
        assert r.housie_auto_status == "stopped"
        assert r.housie_next_auto_call_at is None


class TestLifecycle:
    def test_expired_snapshot_skipped_and_removed(self, snapshot_dir):
        room = _quiz_room()
        room.last_activity = time.time() - 99999
        room_snapshot.save_all({room.room_code: room})
        assert _restore_one() == []
        assert not (snapshot_dir / "SNAP01.json").exists()

    def test_save_all_prunes_closed_rooms(self, snapshot_dir):
        a, b = _quiz_room("AAAA11"), _quiz_room("BBBB22")
        room_snapshot.save_all({"AAAA11": a, "BBBB22": b})
        assert (snapshot_dir / "BBBB22.json").exists()
        room_snapshot.save_all({"AAAA11": a})  # b closed
        assert not (snapshot_dir / "BBBB22.json").exists()

    def test_delete_removes_file(self, snapshot_dir):
        room = _quiz_room()
        room_snapshot.save_all({room.room_code: room})
        room_snapshot.delete("SNAP01")
        assert not (snapshot_dir / "SNAP01.json").exists()

    def test_corrupt_snapshot_does_not_break_restore(self, snapshot_dir):
        room = _quiz_room()
        room_snapshot.save_all({room.room_code: room})
        (snapshot_dir / "ZZZZ99.json").write_text("{not json")
        restored = _restore_one()
        assert [r.room_code for r in restored] == ["SNAP01"]


class TestManagerIntegration:
    def test_manager_restore_registers_room_and_restarts_question_timer(self, snapshot_dir):
        room = _quiz_room(state="QUESTION")
        room.current_question_index = 0
        room_snapshot.save_all({room.room_code: room})

        async def run():
            mgr = SocketManager()
            count = mgr.restore_rooms()
            assert count == 1
            restored = mgr.rooms["SNAP01"]
            assert restored.state == "QUESTION"
            assert restored.timer_task is not None  # countdown restarted
            restored.timer_task.cancel()
            return True

        assert asyncio.run(run())

    def test_manager_restore_lobby_room_no_timer(self, snapshot_dir):
        room = _quiz_room(state="LOBBY")
        room_snapshot.save_all({room.room_code: room})

        async def run():
            mgr = SocketManager()
            assert mgr.restore_rooms() == 1
            assert mgr.rooms["SNAP01"].timer_task is None
            return True

        assert asyncio.run(run())

    def test_party_quests_state_round_trips(self, snapshot_dir):
        import party_quests_engine
        cfg = party_quests_engine.validate_config({})
        state = party_quests_engine.create_initial_state(["Maya", "Leo"], cfg)
        room = Room("PQ0001", {"game_title": "PQ"}, game_type="party_quests")
        room.state = "QUESTS_ACTIVE"
        room.party_quests_state = state
        room_snapshot.save_all({room.room_code: room})
        r = _restore_one()[0]
        assert r.party_quests_state["phase"] == "QUESTS_ACTIVE"
        assert set(r.party_quests_state["quest_boards_by_player"]) == {"Maya", "Leo"}
