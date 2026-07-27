"""Odd One Out over the wire (SPEC-GAME-ODD-ONE-OUT §9).

Written before the socket wiring, so "wired correctly" has a definition. The assertion that matters
most is the prompt leak: per-viewer prompt scoping is what's most likely to break in translation
from the pure engine to the socket layer, and a leak destroys the game outright.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import odd_one_out_engine as ooo
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


def recv_ooo(ws, phase=None, max_messages=120):
    """Odd One Out joins the "simple social" family, so it rides the shared SIMPLE_SOCIAL_SYNC
    envelope with an `odd_one_out` key — same as would_you_rather/acronym — rather than inventing
    its own message type."""
    for _ in range(max_messages):
        data = recv_until(ws, "SIMPLE_SOCIAL_SYNC", max_messages=max_messages)
        state = data.get("odd_one_out", {})
        if phase is None or state.get("phase") == phase:
            return data
    raise TimeoutError(f"Never received odd_one_out phase {phase}")


def test_odd_one_out_full_round_over_the_wire(monkeypatch):
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "OOO001",
        {"game_title": "Odd One Out", "total_rounds": 1},
        time_limit=30,
        organizer_token="secret",
        game_type="odd_one_out",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect("/ws/OOO001/org-1?organizer=true") as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        contexts = []
        try:
            sockets = {}
            for client_id, nickname in [("p1", "Avi"), ("p2", "Ruchi"), ("p3", "Maya")]:
                ctx = client.websocket_connect(f"/ws/OOO001/{client_id}")
                ws = ctx.__enter__()
                contexts.append(ctx)
                sockets[nickname] = ws
                ws.send_json({"type": "JOIN", "nickname": nickname, "avatar": "🙂"})
                recv_until(ws, "JOINED_ROOM")
                recv_until(org_ws, "PLAYER_JOINED")

            org_ws.send_json({"type": "START_GAME"})
            assert recv_until(org_ws, "GAME_STARTING")["game_type"] == "odd_one_out"

            # --- THE critical invariant, asserted over the wire ---
            prompts = {}
            odd_flags = {}
            for nickname, ws in sockets.items():
                state = recv_ooo(ws, phase=ooo.PHASE_ANSWERING)["odd_one_out"]
                prompts[nickname] = state["prompt"]
                odd_flags[nickname] = state["you_are_odd"]

            odd_players = [n for n, flag in odd_flags.items() if flag]
            assert len(odd_players) == 1, f"exactly one odd one expected, got {odd_players}"
            odd = odd_players[0]

            minority = ooo.current_pair(room.ooo_state)["minority"]
            majority = ooo.current_pair(room.ooo_state)["majority"]
            assert prompts[odd] == minority
            for other in [n for n in sockets if n != odd]:
                assert prompts[other] == majority
                # The minority prompt must not reach a non-odd player at all.
                assert prompts[other] != minority

            # --- answer, then vote ---
            for nickname, ws in sockets.items():
                ws.send_json({"type": "OOO_ANSWER", "text": f"answer from {nickname}"})

            org_ws.send_json({"type": "OOO_START_VOTING"})
            voting = recv_ooo(sockets[odd], phase=ooo.PHASE_VOTING)["odd_one_out"]
            assert len(voting["answers"]) == 3

            # Both innocents correctly name the odd one — a strict majority of 3.
            for other in [n for n in sockets if n != odd]:
                sockets[other].send_json({"type": "OOO_VOTE", "accused": odd})

            org_ws.send_json({"type": "OOO_REVEAL"})
            reveal = recv_ooo(org_ws, phase=ooo.PHASE_REVEAL)["odd_one_out"]
            result = reveal["round_result"]
            assert result["caught"] is True
            assert result["odd_player_id"] == odd
            # The reveal shows BOTH prompts — that's what makes the round legible in hindsight.
            assert result["majority_prompt"] == majority
            assert result["minority_prompt"] == minority

            scores = {row["player_id"]: row["score"] for row in reveal["standings"]}
            assert scores[odd] == 0
            for other in [n for n in sockets if n != odd]:
                assert scores[other] == ooo.POINTS_CORRECT_VOTE

            org_ws.send_json({"type": "END_QUIZ"})
            podium = recv_until(org_ws, "PODIUM")
            assert podium["game_type"] == "odd_one_out"
        finally:
            for ctx in reversed(contexts):
                ctx.__exit__(None, None, None)


def test_odd_one_out_refuses_to_start_below_the_minimum(monkeypatch):
    """At 2 players the vote is trivial, so starting must fail loudly rather than produce a
    degenerate round."""
    monkeypatch.setattr(socket_manager, "start_cleanup_loop", lambda: None)
    room = socket_manager.create_room(
        "OOO002",
        {"game_title": "Odd One Out"},
        time_limit=30,
        organizer_token="secret",
        game_type="odd_one_out",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"

    with client.websocket_connect("/ws/OOO002/org-1?organizer=true") as org_ws:
        org_ws.send_json({"type": "AUTH", "token": "secret"})
        assert org_ws.receive_json()["type"] == "ROOM_CREATED"

        ctx = client.websocket_connect("/ws/OOO002/p1")
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
