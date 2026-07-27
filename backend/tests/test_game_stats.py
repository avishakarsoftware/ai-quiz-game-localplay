"""Tests for per-wallet game results and the stats screen (SPEC-GAME-STATS)."""
import time
import uuid

import config
import db


# Mirrors conftest.TEST_DEVICE_ID. conftest isn't importable as a module from here, and the
# autouse `fund_test_wallet` fixture pins tokens.get_wallet_id to this id for every request —
# so endpoint tests must seed THIS wallet, not one derived from an X-Device-Id header.
CONFTEST_WALLET = "00000000-0000-0000-0000-000000000001"


def _fresh(wallet_id: str, *room_codes: str):
    """Clear a wallet's rows, plus any room_codes the test reuses.

    room_code is the PRIMARY KEY, so a row left behind by an earlier run under a *different*
    wallet makes the next INSERT OR IGNORE a silent no-op — the idempotency guard doing its
    job, but it reads as "the write didn't happen". Deleting by wallet alone isn't enough.
    """
    conn = db._get_conn()
    conn.execute("DELETE FROM game_results WHERE wallet_id = ?", (wallet_id,))
    for code in room_codes:
        conn.execute("DELETE FROM game_results WHERE room_code = ?", (code,))
    conn.commit()


def _record(wallet_id: str, room_code: str, game_type: str = "quiz", players: int = 3,
            winner: str = "Maya", score: int = 900, at: int | None = None) -> bool:
    return db.record_game_result(
        room_code=room_code, wallet_id=wallet_id, game_type=game_type,
        game_title=game_type.title(), player_count=players,
        winner_nickname=winner, top_score=score,
        completed_at=at if at is not None else int(time.time()),
    )


def test_records_a_game_and_aggregates_it():
    _fresh("stats-w1", "ROOM01")
    assert _record("stats-w1", "ROOM01", "quiz", players=4) is True
    stats = db.get_wallet_stats("stats-w1")
    assert stats["games_hosted"] == 1
    assert stats["players_entertained"] == 4
    assert stats["favorite_game_type"] == "quiz"
    assert stats["distinct_games_played"] == 1


def test_same_room_is_idempotent_so_a_replayed_podium_cannot_double_count():
    """Several engines can re-enter PODIUM for one room (re-broadcast, reconnect). Without the
    room_code PK guard every stat on the screen inflates."""
    _fresh("stats-w2", "SAME01")
    assert _record("stats-w2", "SAME01", players=5) is True
    assert _record("stats-w2", "SAME01", players=5) is False      # second write ignored
    stats = db.get_wallet_stats("stats-w2")
    assert stats["games_hosted"] == 1
    assert stats["players_entertained"] == 5


def test_empty_wallet_returns_zeros_not_none():
    """A first-time host must render, not crash the section."""
    _fresh("stats-empty")
    stats = db.get_wallet_stats("stats-empty")
    assert stats["games_hosted"] == 0
    assert stats["players_entertained"] == 0
    assert stats["favorite_game_type"] == ""
    assert stats["by_game_type"] == []
    assert db.get_recent_games("stats-empty") == []


def test_favorite_game_is_the_most_hosted_type():
    _fresh("stats-w3", "R1", "R2", "R3")
    _record("stats-w3", "R1", "poker")
    _record("stats-w3", "R2", "poker")
    _record("stats-w3", "R3", "quiz")
    stats = db.get_wallet_stats("stats-w3")
    assert stats["favorite_game_type"] == "poker"
    assert stats["favorite_game_count"] == 2
    assert stats["distinct_games_played"] == 2
    assert stats["by_game_type"][0] == {"game_type": "poker", "count": 2}


def test_recent_games_are_newest_first_and_capped():
    _fresh("stats-w4", *[f"REC{i}" for i in range(5)])
    now = int(time.time())
    for i in range(5):
        _record("stats-w4", f"REC{i}", "quiz", at=now + i)
    recent = db.get_recent_games("stats-w4", limit=3)
    assert [r["room_code"] for r in recent] == ["REC4", "REC3", "REC2"]


def test_recent_games_limit_is_clamped():
    _fresh("stats-w5", "ONE")
    _record("stats-w5", "ONE")
    assert len(db.get_recent_games("stats-w5", limit=9999)) == 1   # clamps, does not raise
    assert len(db.get_recent_games("stats-w5", limit=0)) == 1      # 0 -> default, not empty


def test_walletless_and_roomless_writes_are_rejected():
    """Revelry-hosted rooms have no wallet to attribute to; silently skip rather than write junk."""
    assert db.record_game_result("R", "", "quiz", "Quiz", 2, "x", 1, int(time.time())) is False
    assert db.record_game_result("", "w", "quiz", "Quiz", 2, "x", 1, int(time.time())) is False


def test_stats_are_scoped_per_wallet():
    _fresh("stats-a", "AA1")
    _fresh("stats-b", "BB1", "BB2")
    _record("stats-a", "AA1")
    _record("stats-b", "BB1")
    _record("stats-b", "BB2")
    assert db.get_wallet_stats("stats-a")["games_hosted"] == 1
    assert db.get_wallet_stats("stats-b")["games_hosted"] == 2


class TestStatsEndpoint:
    """conftest's autouse `fund_test_wallet` pins tokens.get_wallet_id to TEST_DEVICE_ID for
    every request, so these tests seed THAT wallet — an X-Device-Id header is ignored here."""

    def test_stats_endpoint_returns_aggregates(self):
        from fastapi.testclient import TestClient
        from main import app
        _fresh(CONFTEST_WALLET, "HTTP1")
        _record(CONFTEST_WALLET, "HTTP1", "would_you_rather", players=6)
        client = TestClient(app)
        res = client.get("/stats")
        assert res.status_code == 200
        body = res.json()
        assert body["available"] is True
        assert body["games_hosted"] == 1
        assert body["players_entertained"] == 6
        # The raw game_type id must never reach the UI.
        assert body["favorite_game_type"] == "would_you_rather"
        assert body["favorite_game_title"] and body["favorite_game_title"] != "would_you_rather"
        assert body["recent"][0]["room_code"] == "HTTP1"

    def test_stats_requires_auth(self, monkeypatch):
        from fastapi.testclient import TestClient
        import tokens as tokens_mod
        from main import app
        # Undo conftest's pin so an unauthenticated request really resolves to no wallet.
        monkeypatch.setattr(tokens_mod, "get_wallet_id", lambda req: "")
        client = TestClient(app)
        assert client.get("/stats").status_code == 401

    def test_stats_degrades_to_unavailable_instead_of_500(self, monkeypatch):
        """Shipping the code before the Supabase table exists must not error the drawer."""
        from fastapi.testclient import TestClient
        import main
        from main import app

        def boom(_wallet_id):
            raise RuntimeError("relation \"games_game_results\" does not exist")

        monkeypatch.setattr(main.db, "get_wallet_stats", boom)
        client = TestClient(app)
        res = client.get("/stats")
        assert res.status_code == 200
        assert res.json()["available"] is False
        assert res.json()["games_hosted"] == 0


class TestGameCompletionRecording:
    def test_record_game_completion_writes_history_and_a_durable_row(self):
        import main
        _fresh("stats-summary", "SUMM01")
        main.game_history.clear()
        summary = {
            "room_code": "SUMM01",
            "game_type": "drawing",
            "game_title": "Drawing",
            "player_count": 4,
            "leaderboard": [{"nickname": "Ada", "score": 700}, {"nickname": "Leo", "score": 300}],
            "completed_at": int(time.time()),
            "wallet_id": "stats-summary",
        }
        main.record_game_completion(summary)
        assert main.game_history[-1] is summary
        recent = db.get_recent_games("stats-summary")
        assert recent[0]["room_code"] == "SUMM01"
        assert recent[0]["winner_nickname"] == "Ada"
        assert recent[0]["top_score"] == 700

    def test_history_ring_is_still_trimmed(self, monkeypatch):
        import main
        monkeypatch.setattr(config, "MAX_GAME_HISTORY", 3)
        main.game_history.clear()
        for i in range(6):
            main.record_game_completion({"room_code": f"T{i}", "wallet_id": "", "completed_at": 0})
        assert len(main.game_history) == 3
        assert [g["room_code"] for g in main.game_history] == ["T3", "T4", "T5"]

    def test_a_db_failure_never_breaks_the_podium(self, monkeypatch):
        """Stats are a side effect; a broken write must not propagate into the game loop."""
        import main
        main.game_history.clear()

        def boom(**_kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(main.db, "record_game_result", boom)
        main.record_game_completion({
            "room_code": "BOOM1", "wallet_id": "stats-boom", "player_count": 2,
            "leaderboard": [], "completed_at": int(time.time()),
        })
        # In-memory history still recorded it, and no exception escaped.
        assert main.game_history[-1]["room_code"] == "BOOM1"

    def test_walletless_summary_skips_the_durable_write(self, monkeypatch):
        import main
        main.game_history.clear()
        called = {"n": 0}
        monkeypatch.setattr(main.db, "record_game_result", lambda **k: called.__setitem__("n", called["n"] + 1))
        main.record_game_completion({"room_code": "NOWALLET", "wallet_id": "", "completed_at": 0})
        assert called["n"] == 0
        assert main.game_history[-1]["room_code"] == "NOWALLET"
