"""Impostor over the wire (SPEC-PASS-AND-PLAY).

Unit tests cover the engine; these cover the WIRING, which is where new game types actually break:
a missing room state-attr, a start gate counting the wrong thing, a handler never dispatched.

The load-bearing case here is `test_starts_with_zero_connected_players`. A pass-and-play room has
exactly ONE websocket (the host's) and zero connected players — so any start gate written against
`connected_player_count()` makes the game permanently unstartable. That bug is invisible to the
engine tests and to tsc.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

import config
import socket_manager as sm
from main import app
from ws_test_utils import recv_until as _recv_until

client = TestClient(app)

_CODE_SEQ = iter(range(1000, 9999))


@pytest.fixture(autouse=True)
def _clean_rooms(monkeypatch):
    # The cleanup loop binds a task to whichever event loop is live; suppress it in tests.
    monkeypatch.setattr(sm.socket_manager, "start_cleanup_loop", lambda: None)
    # TestClient sends no Origin header, and backend/.env sets ALLOWED_ORIGINS, so the origin
    # guard would reject every socket here. The other socket suites clear it the same way.
    saved_origins = sm.socket_manager.allowed_origins
    sm.socket_manager.allowed_origins = []
    sm.socket_manager.rooms.clear()
    yield
    sm.socket_manager.rooms.clear()
    sm.socket_manager.allowed_origins = saved_origins


def _create_room(seat_names=("Maya", "Leo", "Ada"), **cfg):
    """Build the room directly, as the other socket suites do. Going through /room/create would
    also exercise sparks/auth, which isn't what these tests are about."""
    code = f"IMP{next(_CODE_SEQ)}"
    game_data = {
        "game_title": "Impostor",
        "seat_names": list(seat_names),
        **cfg,
    }
    room = sm.socket_manager.create_room(
        code,
        game_data,
        time_limit=30,
        organizer_token="secret",
        game_type="impostor",
        billing_mode="host_app_managed",
    )
    room.wallet_id = "wallet-test"
    return code, "secret"


class _Organizer:
    """Context manager for the host socket: correct /ws/{code}/{client_id} route + AUTH."""

    def __init__(self, room_code, token):
        self._ctx = client.websocket_connect(f"/ws/{room_code}/org-1?organizer=true")
        self._token = token

    def __enter__(self):
        self.ws = self._ctx.__enter__()
        self.ws.send_json({"type": "AUTH", "token": self._token})
        _recv_until(self.ws, "ROOM_CREATED")
        return self.ws

    def __exit__(self, *exc):
        return self._ctx.__exit__(*exc)


def _organizer(room_code, token):
    return _Organizer(room_code, token)


class TestSeatSetup:
    def test_seats_are_created_from_the_room_payload(self):
        code, token = _create_room(("Maya", "Leo", "Ada"))
        room = sm.socket_manager.rooms[code]
        assert [s["name"] for s in room.impostor_seats] == ["Maya", "Leo", "Ada"]

    def test_host_can_replace_seats_before_the_game_starts(self):
        code, token = _create_room(("Maya",))
        with _organizer(code, token) as ws:
            ws.send_json({"type": "IMPOSTOR_SET_SEATS", "seat_names": ["A", "B", "C", "D"]})
            msg = _recv_until(ws, "IMPOSTOR_SYNC")
            assert [s["name"] for s in msg["impostor_seats"]] == ["A", "B", "C", "D"]

    def test_seats_are_frozen_once_the_game_is_running(self):
        """Rebuilding the roster mid-game would invalidate the live round's roles and scores."""
        code, token = _create_room()
        with _organizer(code, token) as ws:
            ws.send_json({"type": "START_GAME"})
            _recv_until(ws, "IMPOSTOR_SYNC")
            ws.send_json({"type": "IMPOSTOR_SET_SEATS", "seat_names": ["X", "Y", "Z"]})
            ws.send_json({"type": "IMPOSTOR_ROLE_SEEN", "seat_id": "s0"})
            _recv_until(ws, "IMPOSTOR_SYNC")
            room = sm.socket_manager.rooms[code]
            assert [s["name"] for s in room.impostor_seats] == ["Maya", "Leo", "Ada"]


class TestStartGate:
    def test_starts_with_zero_connected_players(self):
        """THE pass-and-play invariant: one host socket, no player sockets, and it must still
        start. A gate written against connected_player_count() fails here and only here."""
        code, token = _create_room(("Maya", "Leo", "Ada"))
        with _organizer(code, token) as ws:
            room = sm.socket_manager.rooms[code]
            assert room.connected_player_count() == 0
            ws.send_json({"type": "START_GAME"})
            msg = _recv_until(ws, "IMPOSTOR_SYNC")
            assert msg["impostor"]["phase"] == "IMP_REVEAL_ROLES"

    def test_refuses_to_start_below_the_seat_minimum(self):
        code, token = _create_room(("Maya", "Leo"))       # only 2 seats
        with _organizer(code, token) as ws:
            ws.send_json({"type": "START_GAME"})
            err = _recv_until(ws, "ERROR")
            assert str(config.MIN_IMPOSTOR_PLAYERS) in err["message"]


class TestFullRoundOverTheWire:
    def test_reveal_clues_vote_and_catch(self):
        code, token = _create_room(("Maya", "Leo", "Ada"))
        with _organizer(code, token) as ws:
            ws.send_json({"type": "START_GAME"})
            state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            assert state["phase"] == "IMP_REVEAL_ROLES"
            # The secret must NOT be on the wire during the round.
            assert state["secret_word"] == ""
            assert state["impostor_id"] == ""

            # Pass the phone: every seat sees their role.
            for sid in ("s0", "s1", "s2"):
                ws.send_json({"type": "IMPOSTOR_ROLE_SEEN", "seat_id": sid})
                state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            assert state["phase"] == "IMP_CLUES"

            # Speak clues until voting opens.
            for _ in range(20):
                if state["phase"] != "IMP_CLUES":
                    break
                ws.send_json({"type": "IMPOSTOR_CLUE_SPOKEN", "seat_id": state["turn"]["current"]})
                state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            assert state["phase"] == "IMP_VOTING"

            # Everyone votes for s0.
            for voter in ("s1", "s2"):
                ws.send_json({"type": "IMPOSTOR_VOTE", "voter_id": voter, "accused_id": "s0"})
                state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            ws.send_json({"type": "IMPOSTOR_CLOSE_VOTE"})
            state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]

            # s0 was convicted by strict majority (2 of 3). Either they were the impostor (guess
            # phase) or they weren't (impostor survived) — both are valid, and the secret is now
            # revealed either way.
            assert state["phase"] in ("IMP_ACCUSED_GUESS", "IMP_REVEAL")
            if state["phase"] == "IMP_ACCUSED_GUESS":
                ws.send_json({"type": "IMPOSTOR_ACCUSED_GUESS", "guess": "definitely wrong"})
                state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
                assert state["outcome"] == "impostor_caught"
            else:
                assert state["outcome"] == "impostor_survived"
            assert state["secret_word"]          # revealed once resolved

    def test_podium_records_seat_count_not_zero_players(self):
        """A pass-and-play room has no connected players, so stats would record every party as
        0 players unless the seat count is substituted."""
        import main
        code, token = _create_room(("Maya", "Leo", "Ada"))
        main.game_history.clear()
        with _organizer(code, token) as ws:
            ws.send_json({"type": "START_GAME"})
            _recv_until(ws, "IMPOSTOR_SYNC")
            room = sm.socket_manager.rooms[code]
            # Jump to the last round so NEXT_ROUND ends the game.
            room.impostor_state["round_number"] = room.impostor_state["config"]["total_rounds"]
            ws.send_json({"type": "IMPOSTOR_NEXT_ROUND"})
            _recv_until(ws, "PODIUM")
        assert main.game_history, "podium did not record a game"
        assert main.game_history[-1]["player_count"] == 3

    def test_podium_leaderboard_uses_seat_names(self):
        code, token = _create_room(("Maya", "Leo", "Ada"))
        with _organizer(code, token) as ws:
            ws.send_json({"type": "START_GAME"})
            _recv_until(ws, "IMPOSTOR_SYNC")
            room = sm.socket_manager.rooms[code]
            room.impostor_state["round_number"] = room.impostor_state["config"]["total_rounds"]
            ws.send_json({"type": "IMPOSTOR_NEXT_ROUND"})
            podium = _recv_until(ws, "PODIUM")
        names = {row["nickname"] for row in podium["leaderboard"]}
        assert names == {"Maya", "Leo", "Ada"}


class TestCatalog:
    def test_impostor_is_offered_and_flagged_pass_and_play(self):
        res = client.get("/catalog")
        assert res.status_code == 200
        entry = next((g for g in res.json()["games"] if g["id"] == "impostor"), None)
        assert entry is not None, "impostor missing from the catalog"
        assert entry.get("interaction") == "pass_and_play"

    def test_the_family_set_is_derived_from_the_catalog_not_hand_listed(self):
        """Guards the drift that shipped the occasion bingos broken: three separate hardcoded
        lists still said ['bingo','baby_bingo'] after new members were added."""
        from game_catalog import GAME_CATALOG, PASS_AND_PLAY_GAME_TYPES
        expected = {g["game_type"] for g in GAME_CATALOG if g.get("interaction") == "pass_and_play"}
        assert PASS_AND_PLAY_GAME_TYPES == expected
        assert "impostor" in PASS_AND_PLAY_GAME_TYPES

    def test_rules_exist_so_the_modal_works(self):
        res = client.get("/catalog/impostor/rules")
        if res.status_code == 404:
            pytest.skip("no per-game rules endpoint in this build")
        assert res.status_code == 200
        assert "Impostor" in json.dumps(res.json())


class TestRateLimit:
    """Pass-and-play funnels every seat's action through ONE socket, so the per-client cap that
    suits one-phone-per-player throttles the host mid-game. Found by the full-round test above:
    the vote came back as ERROR "Too many messages" after ~11 rapid messages.
    """

    def test_pass_and_play_gets_a_higher_cap_than_a_normal_room(self):
        assert config.PASS_PLAY_RATE_LIMIT_PER_SEC > config.WS_RATE_LIMIT_PER_SEC

    def test_the_cap_covers_a_full_round_of_host_taps(self):
        """A 3-seat round is 3 reveals + 6 clues + 3 votes + close + next = 14 messages, and a
        host can easily tap that inside a second. An 8-seat round is far more."""
        seats, clue_rounds = 3, 2
        messages = seats + (seats * clue_rounds) + seats + 2
        assert config.PASS_PLAY_RATE_LIMIT_PER_SEC > messages

    def test_a_full_round_of_rapid_messages_is_not_throttled(self):
        code, token = _create_room(("Maya", "Leo", "Ada"))
        with _organizer(code, token) as ws:
            ws.send_json({"type": "START_GAME"})
            state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            for sid in ("s0", "s1", "s2"):
                ws.send_json({"type": "IMPOSTOR_ROLE_SEEN", "seat_id": sid})
                state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            for _ in range(20):
                if state["phase"] != "IMP_CLUES":
                    break
                ws.send_json({"type": "IMPOSTOR_CLUE_SPOKEN", "seat_id": state["turn"]["current"]})
                state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            for voter in ("s1", "s2"):
                ws.send_json({"type": "IMPOSTOR_VOTE", "voter_id": voter, "accused_id": "s0"})
                # A throttled room answers ERROR here instead of a sync.
                state = _recv_until(ws, "IMPOSTOR_SYNC")["impostor"]
            assert state["phase"] == "IMP_VOTING"
