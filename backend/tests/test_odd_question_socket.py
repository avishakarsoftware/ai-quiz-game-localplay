"""Odd Question over the wire (SPEC-GAME-IMPOSTOR §9).

Written before the socket wiring, so "wired correctly" has a definition. The assertion that matters
most is the prompt leak: per-viewer prompt scoping is what's most likely to break in translation
from the pure engine to the socket layer, and a leak destroys the game outright.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import odd_question_engine as oddq
from main import app, game_history
from socket_manager import socket_manager


client = TestClient(app)


def _teardown_rooms():
    for room in socket_manager.rooms.values():
        if room.timer_task:
            room.timer_task.cancel()
            room.timer_task = None
        if room._organizer_cleanup_task:
            room._organizer_cleanup_task.cancel()
            room._organizer_cleanup_task = None
    socket_manager.rooms.clear()
    socket_manager.stop_cleanup_loop()


@pytest.fixture(autouse=True)
def clear_state():
    _teardown_rooms()
    game_history.clear()
    saved_origins = socket_manager.allowed_origins
    socket_manager.allowed_origins = []
    yield
    _teardown_rooms()
    game_history.clear()
    socket_manager.allowed_origins = saved_origins


def recv_until(ws, msg_type, max_messages=80):
    for index in range(max_messages):
        try:
            data = ws.receive_json()
        except Exception as exc:
            raise TimeoutError(f"Closed while waiting for {msg_type} after {index} messages: {exc}")
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"Never received {msg_type}")


def recv_oddq(ws, phase=None, max_messages=120):
    """Odd Question joins the "simple social" family, so it rides the shared SIMPLE_SOCIAL_SYNC
    envelope with an `odd_question` key — same as would_you_rather/acronym — rather than inventing
    its own message type."""
    for _ in range(max_messages):
        data = recv_until(ws, "SIMPLE_SOCIAL_SYNC", max_messages=max_messages)
        state = data.get("odd_question", {})
        if phase is None or state.get("phase") == phase:
            return data
    raise TimeoutError(f"Never received odd_question phase {phase}")


def test_odd_question_full_round_over_the_wire(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "ODQ001",
        {"game_title": "Odd Question", "total_rounds": 1},
        time_limit=30,
        organizer_token="secret",
        game_type="odd_question",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect("/ws/ODQ001/org-1?organizer=true") as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        contexts = []
        try:
            sockets = {}
            for client_id, nickname in [("p1", "Avi"), ("p2", "Ruchi"), ("p3", "Maya")]:
                ctx = client.websocket_connect(f"/ws/ODQ001/{client_id}")
                ws = ctx.__enter__()
                contexts.append(ctx)
                sockets[nickname] = ws
                ws.send_json({"type": "JOIN", "nickname": nickname, "avatar": "🙂"})
                recv_until(ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            assert recv_until(org_ws, "GAME_STARTING")["game_type"] == "odd_question"

            # --- THE critical invariant, asserted over the wire ---
            prompts = {}
            odd_flags = {}
            for nickname, ws in sockets.items():
                state = recv_oddq(ws, phase=oddq.PHASE_ANSWERING)["odd_question"]
                prompts[nickname] = state["prompt"]
                odd_flags[nickname] = state["you_are_odd"]

            odd_players = [n for n, flag in odd_flags.items() if flag]
            assert len(odd_players) == 1, f"exactly one odd one expected, got {odd_players}"
            odd = odd_players[0]

            minority = oddq.current_pair(room.odd_question_state)["minority"]
            majority = oddq.current_pair(room.odd_question_state)["majority"]
            assert prompts[odd] == minority
            for other in [n for n in sockets if n != odd]:
                assert prompts[other] == majority
                # The minority prompt must not reach a non-odd player at all.
                assert prompts[other] != minority

            # --- answer, then vote ---
            for nickname, ws in sockets.items():
                ws.send_json({"type": "ODDQ_ANSWER", "text": f"answer from {nickname}"})

            org_ws.send_json({"type": "ODDQ_START_VOTING"})
            voting = recv_oddq(sockets[odd], phase=oddq.PHASE_VOTING)["odd_question"]
            assert len(voting["answers"]) == 3

            # Both innocents correctly name the odd one — a strict majority of 3.
            for other in [n for n in sockets if n != odd]:
                sockets[other].send_json({"type": "ODDQ_VOTE", "accused": odd})

            org_ws.send_json({"type": "ODDQ_REVEAL"})
            reveal = recv_oddq(org_ws, phase=oddq.PHASE_REVEAL)["odd_question"]
            result = reveal["round_result"]
            assert result["caught"] is True
            assert result["odd_player_id"] == odd
            # The reveal shows BOTH prompts — that's what makes the round legible in hindsight.
            assert result["majority_prompt"] == majority
            assert result["minority_prompt"] == minority

            scores = {row["player_id"]: row["score"] for row in reveal["standings"]}
            assert scores[odd] == 0
            for other in [n for n in sockets if n != odd]:
                assert scores[other] == oddq.POINTS_CORRECT_VOTE

            org_ws.send_json({"type": "END_QUIZ"})
            podium = recv_until(org_ws, "PODIUM")
            assert podium["game_type"] == "odd_question"
        finally:
            for ctx in reversed(contexts):
                ctx.__exit__(None, None, None)


def test_odd_question_refuses_to_start_below_the_minimum(monkeypatch):
    """At 2 players the vote is trivial, so starting must fail loudly rather than produce a
    degenerate round."""
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "ODQ002",
        {"game_title": "Odd Question"},
        time_limit=30,
        organizer_token="secret",
        game_type="odd_question",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect("/ws/ODQ002/org-1?organizer=true") as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        ctx = client.websocket_connect("/ws/ODQ002/p1")
        ws = ctx.__enter__()
        try:
            ws.send_json({"type": "JOIN", "nickname": "Solo", "avatar": "🙂"})
            recv_until(ws, "JOINED_ROOM")
            recv_until(org_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            error = recv_until(org_ws, "ERROR")
            assert "3" in error["message"] or "player" in error["message"].lower()
            assert room.state == "LOBBY"
        finally:
            ctx.__exit__(None, None, None)
