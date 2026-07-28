"""Host cleanup controls for offline lobby seats (BACKLOG: party-scale lobby continuity).

Offline seats are preserved for LOBBY_RECONNECT_GRACE_SECONDS so a slept phone keeps its place.
The gap these close: the host had no way to reclaim those seats early, so a lobby could sit full
of greyed-out stale entries with the host unable to do anything about it.
"""
import time

import pytest

from socket_manager import Room


def _lobby_with(*names: str) -> Room:
    room = Room("TEST01", {}, game_type="quiz")
    room.state = "LOBBY"
    for i, name in enumerate(names):
        room.players[f"c{i}"] = {
            "nickname": name, "score": 0, "prev_rank": 0, "streak": 0, "avatar": "",
        }
    return room


def _mark_offline(room: Room, nickname: str, *, seconds_ago: float = 5.0):
    for client_id, player in room.players.items():
        if player["nickname"] == nickname:
            player["disconnected_at"] = time.time() - seconds_ago
            return client_id
    raise AssertionError(f"no such player: {nickname}")


@pytest.fixture(autouse=True)
def _all_seats_offline(monkeypatch):
    """`is_player_connected` consults live websockets, which don't exist in a unit test.
    Default everyone to offline; tests that need a connected seat override it."""
    monkeypatch.setattr(Room, "is_player_connected", lambda self, cid: False)


def test_removes_a_single_offline_seat():
    room = _lobby_with("Maya", "Leo")
    _mark_offline(room, "Maya")
    assert room.remove_offline_lobby_player("Maya") is True
    assert [p["nickname"] for p in room.players.values()] == ["Leo"]


def test_refuses_to_remove_a_connected_player():
    """Seat cleanup is not a kick tool — removing someone actively in the lobby is a different
    feature with a different abuse surface."""
    room = _lobby_with("Maya", "Leo")
    Room.is_player_connected = lambda self, cid: self.players[cid]["nickname"] == "Maya"  # type: ignore[method-assign]
    try:
        assert room.remove_offline_lobby_player("Maya") is False
        assert len(room.players) == 2
    finally:
        del Room.is_player_connected  # restore the fixture's patch


def test_unknown_nickname_is_a_no_op():
    room = _lobby_with("Maya")
    assert room.remove_offline_lobby_player("Nobody") is False
    assert room.remove_offline_lobby_player("") is False
    assert len(room.players) == 1


def test_only_works_in_lobby():
    """Mid-game the roster drives scoring; silently dropping a seat there would corrupt results."""
    room = _lobby_with("Maya")
    _mark_offline(room, "Maya")
    room.state = "QUESTION"
    assert room.remove_offline_lobby_player("Maya") is False
    assert len(room.players) == 1


def test_force_prune_clears_every_offline_seat_without_waiting_for_the_grace_period():
    room = _lobby_with("Maya", "Leo", "Ada")
    for name in ("Maya", "Leo", "Ada"):
        _mark_offline(room, name, seconds_ago=1.0)   # well inside the grace window
    assert room.prune_expired_lobby_players() == []  # unforced: grace still protects them
    removed = room.prune_expired_lobby_players(force=True)
    assert sorted(removed) == ["Ada", "Leo", "Maya"]
    assert room.players == {}


def test_removal_also_clears_the_seat_s_side_tables():
    """A stale team/token entry keyed by nickname would resurrect or mis-score a removed guest."""
    room = _lobby_with("Maya")
    _mark_offline(room, "Maya")
    room.teams["Maya"] = "Red"
    room.power_ups["Maya"] = ["skip"]
    room.player_tokens["Maya"] = "tok"
    assert room.remove_offline_lobby_player("Maya") is True
    assert "Maya" not in room.teams
    assert "Maya" not in room.power_ups
    assert "Maya" not in room.player_tokens


class TestLobbyTtlOccupancy:
    """The party-length lobby TTL (LOBBY_RECONNECT_GRACE_SECONDS, 90 min) must apply only to a
    lobby somebody is still part of. An abandoned lobby squatting 90 min against the global
    MAX_ROOMS cap triples room-exhaustion exposure while protecting nobody's seat."""

    def _expired_lobby(self, monkeypatch, *, seconds_idle: float) -> Room:
        room = Room("TTL001", {}, game_type="quiz")
        room.state = "LOBBY"
        monkeypatch.setattr(room, "last_activity", time.time() - seconds_idle)
        return room

    def test_occupied_lobby_survives_past_the_base_room_ttl(self, monkeypatch):
        import config
        room = self._expired_lobby(monkeypatch, seconds_idle=config.ROOM_TTL_SECONDS + 60)
        room.players["c1"] = {"nickname": "Maya", "score": 0, "prev_rank": 0, "streak": 0, "avatar": ""}
        assert room.is_expired() is False          # grace window still protecting a seat

    def test_abandoned_lobby_expires_at_the_base_room_ttl(self, monkeypatch):
        import config
        room = self._expired_lobby(monkeypatch, seconds_idle=config.ROOM_TTL_SECONDS + 60)
        assert not room.players and not room.connections
        assert room.is_expired() is True           # nobody left; free the MAX_ROOMS slot

    def test_occupied_lobby_still_expires_after_the_full_grace(self, monkeypatch):
        import config
        room = self._expired_lobby(monkeypatch, seconds_idle=config.LOBBY_RECONNECT_GRACE_SECONDS + 60)
        room.players["c1"] = {"nickname": "Maya", "score": 0, "prev_rank": 0, "streak": 0, "avatar": ""}
        assert room.is_expired() is True           # the grace is long, not infinite

    def test_in_game_rooms_are_untouched_by_the_lobby_grace(self, monkeypatch):
        import config
        room = self._expired_lobby(monkeypatch, seconds_idle=config.ROOM_TTL_SECONDS + 60)
        room.state = "QUESTION"
        room.players["c1"] = {"nickname": "Maya", "score": 0, "prev_rank": 0, "streak": 0, "avatar": ""}
        assert room.is_expired() is True           # mid-game TTL semantics unchanged
