"""Room-lifecycle scenarios that break real parties — the paths unit tests never reach.

ANALYSIS-2026-08-09-coverage.md §2: `socket_manager.py` has 1,878 uncovered lines but ZERO wholly
uncovered functions, so the gap is BRANCHES — reconnection, organizer drop/reclaim, room reset,
late joins. Codex's ordering makes this the prerequisite for the A1 decomposition: restructuring a
6.7k-line file that runs every live party is only safe once these paths are pinned.

Deliberately NOT duplicating what already exists: player-reconnect-with-score, reset-after-podium,
reset-with-new-quiz and spectator-mid-game-join are covered in test_e2e.py / test_ws_flow.py. What
had no coverage at all, verified by grep before writing this file:
  - `ORGANIZER_DISCONNECTED` — 0 tests
  - `GAME_IN_PROGRESS` (late join into a running game) — 0 tests, despite being the exact path
    behind the "QR join fails after restart" investigation, which was declared not-a-bug and then
    never pinned by a test
  - organizer reclaim cancelling the grace-period cleanup
  - two concurrent rooms staying isolated

Uses ws_test_utils.recv_until, which is wall-clock bounded: a missing broadcast fails the test
instead of hanging the run.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

import config
import socket_manager as sm
from main import app, quizzes

# The module holds a manager INSTANCE of the same name; rooms/allowed_origins live on it.
manager = sm.socket_manager
from ws_test_utils import recv_until

client = TestClient(app)


@pytest.fixture(autouse=True)
def _open_origins():
    """The WS origin guard rejects TestClient's header-less handshake."""
    saved = manager.allowed_origins
    manager.allowed_origins = []
    yield
    manager.allowed_origins = saved


@pytest.fixture(autouse=True)
def _clean_rooms():
    for room in list(manager.rooms.values()):
        for task_attr in ("timer_task", "_organizer_cleanup_task", "mafia_timer_task"):
            task = getattr(room, task_attr, None)
            if task:
                task.cancel()
                setattr(room, task_attr, None)
    manager.rooms.clear()
    yield
    manager.rooms.clear()


HEADERS = {"X-Device-ID": "00000000-0000-0000-0000-000000000001"}


def _make_room(game_type: str = "two_truths") -> tuple[str, str]:
    """two_truths: no LLM content needed and no pre-created content id, so these tests stay about
    the room lifecycle rather than content plumbing. It enforces MIN 3 players (the server says so),
    which is why the scenarios below seat three."""
    body = {"game_type": game_type, "time_limit": 30}
    res = client.post("/room/create", json=body, headers=HEADERS)
    assert res.status_code == 200, res.text
    data = res.json()
    return data["room_code"], data["organizer_token"]


def _seed_quiz(title: str = "Socket Scenario Quiz", questions: int = 1) -> str:
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = {
        "quiz_title": title,
        "questions": [
            {
                "id": idx + 1,
                "text": f"Question {idx + 1}?",
                "options": ["A", "B", "C", "D"],
                "answer_index": 0,
            }
            for idx in range(questions)
        ],
    }
    return quiz_id


def _make_quiz_room(quiz_id: str) -> tuple[str, str]:
    res = client.post("/room/create", json={"quiz_id": quiz_id, "time_limit": 30}, headers=HEADERS)
    assert res.status_code == 200, res.text
    data = res.json()
    return data["room_code"], data["organizer_token"]


def _seed_housie(title: str = "Socket Scenario Housie") -> str:
    res = client.post(
        "/housie/create",
        json={
            "game_title": title,
            "pattern_ids": ["quick_5", "first_line", "full_house"],
            "play_mode": "beginner",
            "caller_mode": "manual",
        },
        headers=HEADERS,
    )
    assert res.status_code == 200, res.text
    return res.json()["housie_id"]


def _join(code: str, client_id: str, nickname: str):
    ws = client.websocket_connect(f"/ws/{code}/{client_id}")
    sock = ws.__enter__()
    sock.send_json({"type": "JOIN", "nickname": nickname})
    recv_until(sock, "JOINED_ROOM")
    return ws, sock


# ORDER MATTERS, and it is the real order: host opens the room, THEN guests scan the QR.
# socket_manager only sends ROOM_CREATED when the room has no players and no game progress
# (socket_manager.py:1304) — connect the organizer after a player and the server correctly treats
# it as a RECLAIM, answering HOST_RECONNECTED + ORGANIZER_RECONNECTED instead. Getting this
# backwards was my first mistake here, and the message list in the timeout is what revealed it.
def _open_organizer(code: str, token: str, client_id: str = "org-1"):
    ctx = client.websocket_connect(f"/ws/{code}/{client_id}?organizer=true")
    sock = ctx.__enter__()
    sock.send_json({"type": "AUTH", "token": token})
    recv_until(sock, "ROOM_CREATED")
    return ctx, sock


# --- organizer drop and reclaim ----------------------------------------------

def test_organizer_disconnect_notifies_players_and_arms_cleanup():
    """A host whose phone sleeps must be announced to the players, and the room must be scheduled
    for cleanup rather than lingering forever against MAX_ROOMS."""
    code, token = _make_room()
    org_ctx, _org = _open_organizer(code, token)
    player_ctx, player = _join(code, "p1", "Ada")
    try:
        recv_until(player, "PLAYER_JOINED", max_messages=10)
        org_ctx.__exit__(None, None, None)          # host's phone sleeps

        message = recv_until(player, "ORGANIZER_DISCONNECTED", max_messages=10)
        assert message["type"] == "ORGANIZER_DISCONNECTED", (
            "players must learn the host dropped, or they stare at a frozen screen"
        )
        room = manager.rooms[code]
        assert room._organizer_cleanup_task is not None, (
            "the grace-period cleanup must be armed, or an abandoned room squats a MAX_ROOMS slot"
        )
    finally:
        player_ctx.__exit__(None, None, None)


def test_organizer_reclaims_the_room_and_cancels_cleanup():
    """The host reopens the tab inside the grace window: the same organizer token must reclaim the
    room, cancel the pending deletion, and resync state."""
    code, token = _make_room()
    org_ctx, _org = _open_organizer(code, token)
    player_ctx, player = _join(code, "p1", "Ada")
    try:
        recv_until(player, "PLAYER_JOINED", max_messages=10)
        org_ctx.__exit__(None, None, None)
        recv_until(player, "ORGANIZER_DISCONNECTED", max_messages=10)

        with client.websocket_connect(f"/ws/{code}/org-2?organizer=true") as org2:
            org2.send_json({"type": "AUTH", "token": token})
            sync = recv_until(org2, "ORGANIZER_RECONNECTED", max_messages=10)
            assert sync["room_code"] == code
            assert sync["state"] == "LOBBY"
            assert sync["player_count"] == 1, "the reclaiming host must see the waiting player"
            assert manager.rooms[code]._organizer_cleanup_task is None, (
                "reclaiming must cancel the scheduled deletion, or the room dies mid-party"
            )
    finally:
        player_ctx.__exit__(None, None, None)


def test_wrong_token_cannot_reclaim_an_orphaned_room():
    """The grace window must not become a hijack window."""
    code, _token = _make_room()
    with client.websocket_connect(f"/ws/{code}/org-x?organizer=true") as org:
        org.send_json({"type": "AUTH", "token": "not-the-real-token"})
        message = recv_until(org, "ERROR", max_messages=5)
        assert message["type"] == "ERROR", "an unauthenticated organizer must be refused"


# --- late joins --------------------------------------------------------------

def test_late_join_into_a_running_game_is_told_so():
    """Scanning the QR after the game started must produce GAME_IN_PROGRESS, not a silent hang or a
    corrupted roster. This is the documented behaviour of the 'QR fails after restart' report — it
    had never been pinned by a test."""
    code, token = _make_room()
    org_ctx, org = _open_organizer(code, token)
    p1_ctx, _p1 = _join(code, "p1", "Ada")
    p2_ctx, _p2 = _join(code, "p2", "Grace")
    p3_ctx, _p3 = _join(code, "p3", "Hopper")
    try:
        org.send_json({"type": "START_GAME"})
        recv_until(org, "GAME_STARTING", max_messages=20)

        with client.websocket_connect(f"/ws/{code}/latecomer") as late:
            late.send_json({"type": "JOIN", "nickname": "Latecomer"})
            message = recv_until(late, "GAME_IN_PROGRESS", max_messages=10)
            assert message["type"] == "GAME_IN_PROGRESS"
            assert message["total_questions"] >= 1
    finally:
        p3_ctx.__exit__(None, None, None)
        p2_ctx.__exit__(None, None, None)
        p1_ctx.__exit__(None, None, None)
        org_ctx.__exit__(None, None, None)


def test_join_nonexistent_room_is_rejected_not_hung():
    with client.websocket_connect("/ws/ZZZZZZ/p1") as ws:
        ws.send_json({"type": "JOIN", "nickname": "Nobody"})
        message = recv_until(ws, "ERROR", max_messages=5)
        assert message["type"] == "ERROR"


# --- the JOIN branches: in-progress vs locked lobby --------------------------

def test_locked_lobby_reports_a_lock_not_a_running_game():
    """The host used TOGGLE_LOCK while still in the lobby. Here "ask the host to unlock" IS
    actionable, so this branch must keep the lock wording."""
    code, token = _make_room()
    org_ctx, org = _open_organizer(code, token)
    try:
        org.send_json({"type": "TOGGLE_LOCK"})
        recv_until(org, "ROOM_LOCK_STATUS", max_messages=10)

        with client.websocket_connect(f"/ws/{code}/late-locked") as late:
            late.send_json({"type": "JOIN", "nickname": "Late"})
            message = recv_until(late, "ERROR", max_messages=10)
            assert "locked" in message.get("message", "").lower(), message
    finally:
        org_ctx.__exit__(None, None, None)


def test_reset_is_ignored_outside_the_podium():
    """RESET_ROOM silently returns unless state == PODIUM (socket_manager.py). Pinned because it is
    easy to "fix" the silence into a mid-game reset and wipe a live round."""
    code, token = _make_room()
    org_ctx, org = _open_organizer(code, token)
    p1_ctx, _p1 = _join(code, "p1", "Ada")
    p2_ctx, _p2 = _join(code, "p2", "Grace")
    p3_ctx, _p3 = _join(code, "p3", "Hopper")
    try:
        org.send_json({"type": "START_GAME"})
        recv_until(org, "GAME_STARTING", max_messages=20)
        state_before = manager.rooms[code].state

        org.send_json({"type": "RESET_ROOM"})
        # No ROOM_RESET is expected; the room must simply carry on.
        assert manager.rooms[code].state == state_before, (
            "a mid-game RESET_ROOM must not wipe the round in progress"
        )
        assert manager.rooms[code].room_code == code
    finally:
        p3_ctx.__exit__(None, None, None)
        p2_ctx.__exit__(None, None, None)
        p1_ctx.__exit__(None, None, None)
        org_ctx.__exit__(None, None, None)


def test_reset_after_podium_moves_players_into_next_lobby():
    """The same QR/room is reused between games: players parked on the previous podium must receive
    ROOM_RESET and become lobby players for the next game. Otherwise the host sees stale seats, the
    players see "waiting for host", and START_GAME refuses because nobody is actually in the new
    lobby — exactly the big-party failure mode."""
    first_quiz = _seed_quiz("First Quiz", questions=1)
    room_code, token = _make_quiz_room(first_quiz)
    org_ctx, org = _open_organizer(room_code, token)
    p1_ctx, p1 = _join(room_code, "p1", "Ada")
    p2_ctx, p2 = _join(room_code, "p2", "Grace")
    try:
        recv_until(org, "PLAYER_JOINED", max_messages=10)
        recv_until(org, "PLAYER_JOINED", max_messages=10)

        org.send_json({"type": "START_GAME"})
        recv_until(org, "GAME_STARTING", max_messages=20)
        recv_until(p1, "GAME_STARTING", max_messages=20)
        recv_until(p2, "GAME_STARTING", max_messages=20)

        org.send_json({"type": "NEXT_QUESTION"})
        recv_until(p1, "QUESTION", max_messages=20)
        recv_until(p2, "QUESTION", max_messages=20)
        p1.send_json({"type": "ANSWER", "answer_index": 0})
        p2.send_json({"type": "ANSWER", "answer_index": 1})
        recv_until(org, "QUESTION_OVER", max_messages=20)

        org.send_json({"type": "NEXT_QUESTION"})
        recv_until(org, "PODIUM", max_messages=20)
        recv_until(p1, "PODIUM", max_messages=20)
        recv_until(p2, "PODIUM", max_messages=20)

        next_quiz = _seed_quiz("Next Quiz", questions=1)
        org.send_json({"type": "RESET_ROOM", "game_type": "quiz", "content_id": next_quiz, "time_limit": 20})
        org_reset = recv_until(org, "ROOM_RESET", max_messages=20)
        p1_reset = recv_until(p1, "ROOM_RESET", max_messages=20)
        p2_reset = recv_until(p2, "ROOM_RESET", max_messages=20)

        for reset in (org_reset, p1_reset, p2_reset):
            assert reset["room_code"] == room_code
            assert reset["game_type"] == "quiz"
            assert reset["player_count"] == 2
            assert {player["nickname"] for player in reset["players"]} == {"Ada", "Grace"}

        org.send_json({"type": "START_GAME"})
        recv_until(org, "GAME_STARTING", max_messages=20)
        recv_until(p1, "GAME_STARTING", max_messages=20)
        recv_until(p2, "GAME_STARTING", max_messages=20)
    finally:
        p2_ctx.__exit__(None, None, None)
        p1_ctx.__exit__(None, None, None)
        org_ctx.__exit__(None, None, None)


def test_reset_after_podium_to_default_social_game_keeps_players_startable():
    """A host can choose a different default/config-driven game after results without making guests
    rescan. This pins the non-quiz RESET_ROOM path used by "Choose Another Game" for catalog games
    that do not have a generated content_id."""
    room_code, token = _make_room("two_truths")
    org_ctx, org = _open_organizer(room_code, token)
    p1_ctx, p1 = _join(room_code, "p1", "Ada")
    p2_ctx, p2 = _join(room_code, "p2", "Grace")
    p3_ctx, p3 = _join(room_code, "p3", "Hopper")
    p4_ctx, p4 = _join(room_code, "p4", "Maya")
    try:
        recv_until(org, "PLAYER_JOINED", max_messages=10)
        recv_until(org, "PLAYER_JOINED", max_messages=10)
        recv_until(org, "PLAYER_JOINED", max_messages=10)
        recv_until(org, "PLAYER_JOINED", max_messages=10)

        manager.rooms[room_code].state = "PODIUM"
        org.send_json({"type": "RESET_ROOM", "game_type": "common_ground", "time_limit": 45})
        org_reset = recv_until(org, "ROOM_RESET", max_messages=20)
        p1_reset = recv_until(p1, "ROOM_RESET", max_messages=20)
        p2_reset = recv_until(p2, "ROOM_RESET", max_messages=20)
        p3_reset = recv_until(p3, "ROOM_RESET", max_messages=20)
        p4_reset = recv_until(p4, "ROOM_RESET", max_messages=20)

        for reset in (org_reset, p1_reset, p2_reset, p3_reset, p4_reset):
            assert reset["room_code"] == room_code
            assert reset["game_type"] == "common_ground"
            assert reset["player_count"] == 4
            assert {player["nickname"] for player in reset["players"]} == {"Ada", "Grace", "Hopper", "Maya"}

        room = manager.rooms[room_code]
        assert room.state == "LOBBY"
        assert room.game_type == "common_ground"
        assert room.connected_player_count() == 4

        org.send_json({"type": "START_GAME"})
        start = recv_until(org, "GAME_STARTING", max_messages=20)
        assert start["game_type"] == "common_ground"
        assert recv_until(p1, "GAME_STARTING", max_messages=20)["game_type"] == "common_ground"
    finally:
        p4_ctx.__exit__(None, None, None)
        p3_ctx.__exit__(None, None, None)
        p2_ctx.__exit__(None, None, None)
        p1_ctx.__exit__(None, None, None)
        org_ctx.__exit__(None, None, None)


def test_reset_after_podium_to_housie_keeps_players_startable():
    """Bingo-family games use saved content ids and a separate caller/ticket runtime. A finished
    room can still reset into Housie without changing the QR or losing connected players."""
    room_code, token = _make_room("two_truths")
    org_ctx, org = _open_organizer(room_code, token)
    p1_ctx, p1 = _join(room_code, "p1", "Ada")
    p2_ctx, p2 = _join(room_code, "p2", "Grace")
    try:
        recv_until(org, "PLAYER_JOINED", max_messages=10)
        recv_until(org, "PLAYER_JOINED", max_messages=10)

        manager.rooms[room_code].state = "PODIUM"
        housie_id = _seed_housie("Next Housie")
        org.send_json({"type": "RESET_ROOM", "game_type": "housie", "content_id": housie_id, "time_limit": 30})
        org_reset = recv_until(org, "ROOM_RESET", max_messages=20)
        p1_reset = recv_until(p1, "ROOM_RESET", max_messages=20)
        p2_reset = recv_until(p2, "ROOM_RESET", max_messages=20)

        for reset in (org_reset, p1_reset, p2_reset):
            assert reset["room_code"] == room_code
            assert reset["game_type"] == "housie"
            assert reset["player_count"] == 2
            assert {player["nickname"] for player in reset["players"]} == {"Ada", "Grace"}

        room = manager.rooms[room_code]
        assert room.state == "LOBBY"
        assert room.game_type == "housie"
        assert room.content_id == housie_id
        assert room.connected_player_count() == 2

        org.send_json({"type": "START_GAME"})
        assert recv_until(org, "GAME_STARTING", max_messages=20)["game_type"] == "housie"
        assert recv_until(p1, "GAME_STARTING", max_messages=20)["game_type"] == "housie"
        assert recv_until(p2, "GAME_STARTING", max_messages=20)["game_type"] == "housie"
        org_sync = recv_until(org, "BINGO_SYNC", max_messages=20)
        assert org_sync["game_type"] == "housie"
        assert org_sync["player_count"] == 2
        assert org_sync["bingo"]["layout"] == "housie_3x9_15"
    finally:
        p2_ctx.__exit__(None, None, None)
        p1_ctx.__exit__(None, None, None)
        org_ctx.__exit__(None, None, None)


def test_room_code_is_stable_across_its_lifetime():
    """The QR a guest scanned must stay valid: the code is assigned once and never rotates, which is
    what makes the "QR stops working" report a non-bug. Pinned so a refactor cannot quietly change
    it and break every shared link."""
    code, token = _make_room()
    org_ctx, org = _open_organizer(code, token)
    p1_ctx, _p1 = _join(code, "p1", "Ada")
    p2_ctx, _p2 = _join(code, "p2", "Grace")
    p3_ctx, _p3 = _join(code, "p3", "Hopper")
    try:
        assert manager.rooms[code].room_code == code
        org.send_json({"type": "START_GAME"})
        recv_until(org, "GAME_STARTING", max_messages=20)
        assert manager.rooms[code].room_code == code, "the code must not change when a game starts"
    finally:
        p3_ctx.__exit__(None, None, None)
        p2_ctx.__exit__(None, None, None)
        p1_ctx.__exit__(None, None, None)
        org_ctx.__exit__(None, None, None)


# --- isolation between concurrent rooms -------------------------------------

def test_two_concurrent_rooms_do_not_leak_into_each_other():
    """Two parties at once on one process: a broadcast in one room must never reach the other.
    Rooms are in-memory dicts keyed by code, so a mis-scoped broadcast is a plausible refactor
    error — and would surface as strangers' answers appearing mid-game."""
    code_a, token_a = _make_room()
    code_b, token_b = _make_room()
    assert code_a != code_b

    org_a_ctx, _org_a = _open_organizer(code_a, token_a, client_id="org-a")
    org_b_ctx, _org_b = _open_organizer(code_b, token_b, client_id="org-b")
    a_ctx, a_player = _join(code_a, "pa", "Ada")
    b_ctx, _b_player = _join(code_b, "pb", "Bob")
    try:
        recv_until(a_player, "PLAYER_JOINED", max_messages=10)
        second_ctx, _second = _join(code_a, "pa2", "Alice")
        try:
            event = recv_until(a_player, "PLAYER_JOINED", max_messages=10)
            assert event["player_count"] == 2, "room A must see its own second player"
            # Asserting room B received NOTHING via a blocking read would hang, so check state.
            assert manager.rooms[code_b].connected_player_count() == 1, (
                "room B's roster must be untouched by room A's activity"
            )
            assert set(manager.rooms[code_a].players) != set(manager.rooms[code_b].players), (
                "the two rooms must not share player state"
            )
        finally:
            second_ctx.__exit__(None, None, None)
    finally:
        b_ctx.__exit__(None, None, None)
        a_ctx.__exit__(None, None, None)
        org_b_ctx.__exit__(None, None, None)
        org_a_ctx.__exit__(None, None, None)


def test_room_codes_are_unique_across_many_creates():
    """Codes are the only thing a guest types; a collision would drop someone into a stranger's
    party."""
    codes = set()
    for _ in range(25):
        code, _token = _make_room()
        assert code not in codes, f"duplicate room code issued: {code}"
        codes.add(code)
    assert len(codes) == 25


def test_room_capacity_is_recovered_after_host_cancel(monkeypatch):
    """The global room cap is shared by every live party on a process. Hitting it must fail
    closed, and a host-cancelled room must immediately free the slot; otherwise one noisy party
    can wedge all new room creation until TTL cleanup."""
    monkeypatch.setattr(config, "MAX_ROOMS", 2)

    code_a, token_a = _make_room()
    code_b, _token_b = _make_room()
    blocked = client.post(
        "/room/create",
        json={"game_type": "two_truths", "time_limit": 30},
        headers=HEADERS,
    )
    assert blocked.status_code == 429
    assert "too many active rooms" in blocked.json()["detail"].lower()

    with client.websocket_connect(f"/ws/{code_a}/org-cap?organizer=true") as org:
        org.send_json({"type": "AUTH", "token": token_a})
        recv_until(org, "ROOM_CREATED", max_messages=10)
        org.send_json({"type": "CANCEL_GAME"})
        closed = recv_until(org, "ROOM_CLOSED", max_messages=10)
        assert closed["reason"] == "host_cancelled"

    assert code_a not in manager.rooms
    assert code_b in manager.rooms

    replacement = client.post(
        "/room/create",
        json={"game_type": "two_truths", "time_limit": 30},
        headers=HEADERS,
    )
    assert replacement.status_code == 200, replacement.text
