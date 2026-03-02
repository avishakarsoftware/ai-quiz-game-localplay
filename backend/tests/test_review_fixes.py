"""
Tests for the 4 backend fixes from code review:
1. Nickname hijacking prevention via session tokens
2. Fifty-fifty reconnect state preservation
3. (Fix 3 is frontend-only, not tested here)
4. Spectator heartbeat / Room structure
"""
import sys
import os
import asyncio
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from socket_manager import Room, SocketManager
import config


# ---------------------------------------------------------------------------
# Mock WebSocket
# ---------------------------------------------------------------------------

class MockWebSocket:
    """Lightweight mock for fastapi.WebSocket."""
    def __init__(self):
        self.sent_messages: list[dict] = []
        self.closed = False
        self.close_code = None

    async def send_json(self, data: dict):
        self.sent_messages.append(data)

    async def close(self, code: int = 1000):
        self.closed = True
        self.close_code = code

    async def accept(self):
        pass

    @property
    def headers(self):
        return {"origin": ""}

    def last(self, msg_type: str) -> dict | None:
        """Return the last sent message of a given type."""
        for msg in reversed(self.sent_messages):
            if msg.get("type") == msg_type:
                return msg
        return None

    def all(self, msg_type: str) -> list[dict]:
        """Return all sent messages of a given type."""
        return [m for m in self.sent_messages if m.get("type") == msg_type]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_quiz(num_questions=5):
    return {
        "quiz_title": "Unit Test Quiz",
        "questions": [
            {
                "id": i + 1,
                "text": f"Question {i + 1}?",
                "options": ["A", "B", "C", "D"],
                "answer_index": 0,
            }
            for i in range(num_questions)
        ],
    }


def make_room(num_questions=5, time_limit=15, token="test-token"):
    return Room("UNIT01", make_quiz(num_questions), time_limit, organizer_token=token)


def add_player(room, client_id, nickname, score=0, team=None):
    """Add a player to the room with a mock WebSocket connection."""
    ws = MockWebSocket()
    room.connections[client_id] = ws
    room.players[client_id] = {
        "nickname": nickname,
        "score": score,
        "prev_rank": 0,
        "streak": 0,
        "avatar": "",
    }
    room.power_ups[nickname] = {"double_points": True, "fifty_fifty": True}
    if team:
        room.teams[nickname] = team
    return ws


def add_organizer(room, client_id="org-1"):
    ws = MockWebSocket()
    room.connections[client_id] = ws
    room.organizer = ws
    room.organizer_id = client_id
    return ws


def add_spectator(room, client_id="spec-1"):
    ws = MockWebSocket()
    room.spectators[client_id] = ws
    return ws


async def join_fresh_player(sm, room, client_id, nickname, avatar="", session_token=None):
    """Send a JOIN message for a fresh player and return the websocket."""
    ws = MockWebSocket()
    room.connections[client_id] = ws
    msg = {"type": "JOIN", "nickname": nickname, "avatar": avatar}
    if session_token is not None:
        msg["session_token"] = session_token
    await sm.handle_message(room, client_id, msg, is_organizer=False)
    return ws


# ===========================================================================
# Fix 1: Nickname Hijacking — Session Tokens
# ===========================================================================

class TestSessionTokens:
    """Tests for session token generation, storage, and verification."""

    @pytest.mark.asyncio
    async def test_fresh_join_returns_session_token(self):
        """A fresh JOIN should return JOINED_ROOM with a non-empty session_token."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = await join_fresh_player(sm, room, "p1", "Alice")
        joined = ws.last("JOINED_ROOM")
        assert joined is not None
        assert "session_token" in joined
        assert isinstance(joined["session_token"], str)
        assert len(joined["session_token"]) > 0

    @pytest.mark.asyncio
    async def test_fresh_join_stores_token_in_room(self):
        """The generated session token should be stored in room.player_tokens."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = await join_fresh_player(sm, room, "p1", "Alice")
        joined = ws.last("JOINED_ROOM")
        assert "Alice" in room.player_tokens
        assert room.player_tokens["Alice"] == joined["session_token"]

    @pytest.mark.asyncio
    async def test_reconnect_with_correct_token_succeeds(self):
        """Disconnected player reconnecting with correct token should succeed."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join and capture token
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")
        token = ws1.last("JOINED_ROOM")["session_token"]

        # Start game so disconnect preserves data
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        # Disconnect (simulate)
        room._remove_connection("p1")
        assert "Alice" in room.disconnected_players

        # Reconnect with correct token
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token=token)
        reconnected = ws2.last("RECONNECTED")
        assert reconnected is not None
        assert "p2" in room.players
        assert room.players["p2"]["nickname"] == "Alice"

    @pytest.mark.asyncio
    async def test_reconnect_with_wrong_token_rejected(self):
        """Disconnected player reconnecting with wrong token should be rejected."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join and capture token
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")

        # Start game and disconnect
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        room._remove_connection("p1")
        assert "Alice" in room.disconnected_players

        # Reconnect with wrong token
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token="wrong-token")
        err = ws2.last("ERROR")
        assert err is not None
        assert "taken" in err["message"].lower()
        # Alice should still be in disconnected_players (not popped)
        assert "Alice" in room.disconnected_players

    @pytest.mark.asyncio
    async def test_reconnect_with_no_token_rejected(self):
        """Disconnected player reconnecting without a token should be rejected."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join and capture token
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")

        # Start game and disconnect
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()
        room._remove_connection("p1")

        # Reconnect with no token (omitted entirely)
        ws2 = await join_fresh_player(sm, room, "p2", "Alice")
        err = ws2.last("ERROR")
        assert err is not None
        assert "taken" in err["message"].lower()
        assert "Alice" in room.disconnected_players

    @pytest.mark.asyncio
    async def test_duplicate_nickname_with_correct_token_succeeds(self):
        """Active player reconnecting with correct token should kick old and succeed."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join and capture token
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")
        token = ws1.last("JOINED_ROOM")["session_token"]

        # Move to QUESTION state
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        # Same nickname joins with correct token (new device)
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token=token)

        # Old connection should be kicked
        kicked = ws1.last("KICKED")
        assert kicked is not None
        assert ws1.closed

        # New connection should have reconnected
        reconnected = ws2.last("RECONNECTED")
        assert reconnected is not None
        assert "p2" in room.players
        assert "p1" not in room.players

    @pytest.mark.asyncio
    async def test_duplicate_nickname_with_wrong_token_rejected(self):
        """Imposter trying to steal active nickname with wrong token should be rejected."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join original player
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")

        # Move to QUESTION state
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        # Imposter tries with wrong token
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token="imposter-token")

        err = ws2.last("ERROR")
        assert err is not None
        assert "taken" in err["message"].lower()

        # Original player should NOT be kicked
        assert not ws1.closed
        assert ws1.last("KICKED") is None
        assert "p1" in room.players

    @pytest.mark.asyncio
    async def test_duplicate_nickname_without_token_rejected(self):
        """Imposter trying to steal active nickname without any token should be rejected."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join original player
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")

        # Move to QUESTION state
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        # Imposter tries without token
        ws2 = await join_fresh_player(sm, room, "p2", "Alice")

        err = ws2.last("ERROR")
        assert err is not None
        assert "taken" in err["message"].lower()

        # Original player should NOT be kicked
        assert not ws1.closed
        assert "p1" in room.players

    @pytest.mark.asyncio
    async def test_reset_clears_stale_player_tokens(self):
        """After reset, tokens for stale players (still in room.players but
        no longer connected) should be cleared, while tokens for connected
        players remain."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join two players via JOIN handler so tokens are generated
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")
        alice_token = room.player_tokens["Alice"]

        # Manually add Bob as a stale player (in room.players but NOT in room.connections)
        # This simulates a player whose connection was dropped without _remove_connection
        room.players["p2"] = {"nickname": "Bob", "score": 100, "prev_rank": 0, "streak": 0, "avatar": ""}
        room.power_ups["Bob"] = {"double_points": True, "fifty_fifty": True}
        room.player_tokens["Bob"] = "bobs-token"
        # Note: p2 is NOT in room.connections, making it stale

        # Move to PODIUM and reset
        room.state = "PODIUM"
        room.reset_for_new_game(make_quiz(3), 20)

        # Alice (connected) should still have her token
        assert "Alice" in room.player_tokens
        assert room.player_tokens["Alice"] == alice_token

        # Bob (stale — in players but not connections) should have token cleared
        assert "Bob" not in room.player_tokens
        assert "p2" not in room.players

    @pytest.mark.asyncio
    async def test_reconnected_response_includes_session_token(self):
        """The RECONNECTED payload should include session_token."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join and capture token
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")
        token = ws1.last("JOINED_ROOM")["session_token"]

        # Start game and disconnect
        room.state = "LEADERBOARD"
        room.current_question_index = 2
        room._remove_connection("p1")

        # Reconnect
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token=token)
        reconnected = ws2.last("RECONNECTED")
        assert reconnected is not None
        assert "session_token" in reconnected
        assert reconnected["session_token"] == token


# ===========================================================================
# Fix 2: Fifty-Fifty Reconnect State
# ===========================================================================

class TestFiftyFiftyReconnect:
    """Tests for fifty-fifty power-up state preservation across reconnects."""

    @pytest.mark.asyncio
    async def test_fifty_fifty_stores_remove_indices(self):
        """Activating fifty-fifty should store remove indices in power_ups."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        ws = add_player(room, "p1", "Alice")
        room.state = "QUESTION"
        room.current_question_index = 0

        await sm.handle_message(room, "p1", {
            "type": "USE_POWER_UP", "power_up": "fifty_fifty"
        }, is_organizer=False)

        activated = ws.last("POWER_UP_ACTIVATED")
        assert activated is not None
        assert activated["power_up"] == "fifty_fifty"
        assert "remove_indices" in activated

        # Check stored in power_ups dict
        pups = room.power_ups["Alice"]
        assert "fifty_fifty_remove_indices" in pups
        assert pups["fifty_fifty_remove_indices"] == activated["remove_indices"]

    @pytest.mark.asyncio
    async def test_reconnect_includes_fifty_fifty_indices(self):
        """Reconnecting during QUESTION after using 50/50 should include remove_indices."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join player
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")
        token = ws1.last("JOINED_ROOM")["session_token"]

        # Start game
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        # Use fifty-fifty
        await sm.handle_message(room, "p1", {
            "type": "USE_POWER_UP", "power_up": "fifty_fifty"
        }, is_organizer=False)
        stored_indices = room.power_ups["Alice"]["fifty_fifty_remove_indices"]

        # Disconnect
        room._remove_connection("p1")

        # Reconnect during QUESTION
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token=token)
        reconnected = ws2.last("RECONNECTED")
        assert reconnected is not None
        assert "remove_indices" in reconnected
        assert reconnected["remove_indices"] == stored_indices

    @pytest.mark.asyncio
    async def test_reconnect_includes_power_ups_state(self):
        """RECONNECTED payload should include power_ups dict with correct availability."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join player
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")
        token = ws1.last("JOINED_ROOM")["session_token"]

        # Start game
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        # Use fifty-fifty (consumes it)
        await sm.handle_message(room, "p1", {
            "type": "USE_POWER_UP", "power_up": "fifty_fifty"
        }, is_organizer=False)

        # Disconnect and reconnect
        room._remove_connection("p1")
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token=token)
        reconnected = ws2.last("RECONNECTED")

        assert "power_ups" in reconnected
        # fifty_fifty was used, so it should be False
        assert reconnected["power_ups"]["fifty_fifty"] is False
        # double_points was not used, so it should be True
        assert reconnected["power_ups"]["double_points"] is True

    @pytest.mark.asyncio
    async def test_start_question_clears_fifty_fifty_indices(self):
        """Starting a new question should clear fifty_fifty_remove_indices for all players."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")
        add_player(room, "p1", "Alice")
        add_player(room, "p2", "Bob")

        # Set state and use fifty-fifty
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        await sm.handle_message(room, "p1", {
            "type": "USE_POWER_UP", "power_up": "fifty_fifty"
        }, is_organizer=False)
        assert "fifty_fifty_remove_indices" in room.power_ups["Alice"]

        # Also set double_points_active for Bob
        room.power_ups["Bob"]["double_points_active"] = True

        # End current question, then start next
        await sm.end_question(room)
        room.state = "LEADERBOARD"
        await sm.start_question(room)

        # Both should be cleared
        assert "fifty_fifty_remove_indices" not in room.power_ups["Alice"]
        assert "double_points_active" not in room.power_ups["Alice"]
        assert "double_points_active" not in room.power_ups["Bob"]

    @pytest.mark.asyncio
    async def test_reconnect_without_fifty_fifty_has_no_remove_indices(self):
        """Reconnecting when 50/50 was NOT used should NOT include remove_indices."""
        room = make_room()
        sm = SocketManager()
        add_organizer(room, "org-1")

        # Join player (no power-up usage)
        ws1 = await join_fresh_player(sm, room, "p1", "Alice")
        token = ws1.last("JOINED_ROOM")["session_token"]

        # Start game
        room.state = "QUESTION"
        room.current_question_index = 0
        room.question_start_time = time.time()

        # Disconnect and reconnect without using fifty-fifty
        room._remove_connection("p1")
        ws2 = await join_fresh_player(sm, room, "p2", "Alice", session_token=token)
        reconnected = ws2.last("RECONNECTED")
        assert reconnected is not None
        assert "remove_indices" not in reconnected


# ===========================================================================
# Fix 4: Spectator Heartbeat / Room Structure
# ===========================================================================

class TestSpectatorHeartbeat:
    """Tests for spectator-related Room structure and broadcast behaviour."""

    def test_room_has_player_tokens_field(self):
        """Room init should include player_tokens dict."""
        room = make_room()
        assert hasattr(room, "player_tokens")
        assert isinstance(room.player_tokens, dict)
        assert len(room.player_tokens) == 0

    @pytest.mark.asyncio
    async def test_spectator_broadcast_includes_spectators(self):
        """Room.broadcast should send to spectators as well as players/organizer."""
        room = make_room()
        org_ws = add_organizer(room, "org-1")
        p_ws = add_player(room, "p1", "Alice")
        spec_ws = add_spectator(room, "spec-1")

        await room.broadcast({"type": "TEST_MSG"})

        assert org_ws.last("TEST_MSG") is not None
        assert p_ws.last("TEST_MSG") is not None
        assert spec_ws.last("TEST_MSG") is not None
