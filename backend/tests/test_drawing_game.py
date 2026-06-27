import asyncio

import pytest
from fastapi.testclient import TestClient

from drawing_engine import clue_for_prompt, is_correct_guess, normalize_guess, _sanitize_drawing_game, _validate_drawing_game
import main
from main import app
from socket_manager import Room, SocketManager


client = TestClient(app)
AUTH_HEADERS = {"X-Device-Id": "11111111-1111-4111-8111-111111111111"}


@pytest.fixture(autouse=True)
def clear_drawing_state():
    main.drawing_games.clear()
    main.drawing_timestamps.clear()
    main.content_owners.clear()
    main.pending_generation_charges.clear()
    main.socket_manager.rooms.clear()
    yield
    main.drawing_games.clear()
    main.drawing_timestamps.clear()
    main.content_owners.clear()
    main.pending_generation_charges.clear()
    main.socket_manager.rooms.clear()


class MockWebSocket:
    def __init__(self):
        self.sent_messages = []

    async def send_json(self, data):
        self.sent_messages.append(data)


def make_drawing_game():
    return {
        "game_title": "Drawing Night",
        "prompts": [
            {"id": 1, "text": "robot chef", "aliases": ["robot cook"], "difficulty": "medium"},
            {"id": 2, "text": "flying cars", "aliases": ["flying car"], "difficulty": "easy"},
        ],
    }


def add_player(room, client_id, nickname):
    ws = MockWebSocket()
    room.connections[client_id] = ws
    room.players[client_id] = {"nickname": nickname, "score": 0, "prev_rank": 0, "streak": 0, "avatar": ""}
    return ws


def test_normalize_guess_strips_articles_punctuation_and_plurals():
    assert normalize_guess("The robot chefs!") == "robot chef"
    assert normalize_guess("A flying car") == "flying car"
    assert normalize_guess("puppies") == "puppy"


def test_is_correct_guess_uses_aliases_without_fuzzy_matching():
    prompt = {"text": "robot chef", "aliases": ["robot cook"]}
    assert is_correct_guess("the robot cook!", prompt)
    assert is_correct_guess("robot chefs", prompt)
    assert not is_correct_guess("robot chief", prompt)


def test_clue_for_prompt_progressively_reveals_letters():
    assert clue_for_prompt("cat", 0) == "_ _ _"
    assert clue_for_prompt("cold cat", 0) == "_ _ _ _   _ _ _"
    assert clue_for_prompt("cold cat", 0.50) == "c _ _ _   _ _ _"
    assert clue_for_prompt("cold cat", 0.75) == "c _ _ _   c _ _"
    assert clue_for_prompt("cold cat", 0.90) == "c _ _ d   c _ t"


def test_sanitize_and_validate_drawing_game():
    raw = {
        "game_title": "<b>Sketch</b>",
        "prompts": [{"id": 1, "text": "<i>haunted houses</i>", "aliases": ["the haunted house"], "difficulty": "weird"}],
    }
    game = _sanitize_drawing_game(raw)
    assert game["game_title"] == "Sketch"
    assert game["prompts"][0]["text"] == "haunted houses"
    assert game["prompts"][0]["difficulty"] == "medium"
    assert _validate_drawing_game(game, attempt=0)


def test_import_drawing_sanitizes_validates_and_stores_game():
    response = client.post("/drawing/import", json=make_drawing_game(), headers=AUTH_HEADERS)

    assert response.status_code == 200, response.text
    body = response.json()
    drawing_id = body["drawing_id"]
    assert drawing_id in main.drawing_games
    assert main.content_owners[drawing_id]
    assert body["game"]["game_title"] == "Drawing Night"
    assert body["game"]["prompts"][0]["text"] == "robot chef"

    get_response = client.get(f"/drawing/{drawing_id}")
    assert get_response.status_code == 200
    assert get_response.json()["game_title"] == "Drawing Night"


def test_import_drawing_rejects_unplayable_prompts():
    response = client.post(
        "/drawing/import",
        json={
            "game_title": "Bad Drawing",
            "prompts": [{"id": 1, "text": "this drawing prompt has too many words to be playable"}],
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_drawing_round_sends_secret_prompt_only_to_drawer():
    manager = SocketManager()
    room = Room("DRAW01", make_drawing_game(), time_limit=30, game_type="drawing")
    add_player(room, "p1", "Alice")
    add_player(room, "p2", "Bob")

    await manager.start_question(room)

    alice_msg = room.connections["p1"].sent_messages[-1]
    bob_msg = room.connections["p2"].sent_messages[-1]
    drawer_msg = alice_msg if alice_msg["is_drawer"] else bob_msg
    guesser_msg = bob_msg if alice_msg["is_drawer"] else alice_msg

    assert drawer_msg["drawing_prompt"]["text"] == "robot chef"
    assert "text" not in guesser_msg["drawing_prompt"]
    assert guesser_msg["drawing_clue"] == "_ _ _ _ _   _ _ _ _"
    room.timer_task.cancel()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_drawing_start_game_enters_first_round_without_extra_next_message():
    manager = SocketManager()
    room = Room("DRAW05", make_drawing_game(), time_limit=30, game_type="drawing", billing_mode="host_app_managed")
    room.wallet_id = "test-wallet"
    add_player(room, "p1", "Alice")
    add_player(room, "p2", "Bob")

    await manager.handle_message(room, "organizer", {"type": "START_GAME"}, is_organizer=True)

    assert room.state == "QUESTION"
    assert room.current_question_index == 0
    assert room.current_drawer in {"Alice", "Bob"}
    assert any(msg.get("type") == "QUESTION" and msg.get("game_type") == "drawing" for msg in room.connections["p1"].sent_messages)
    if room.timer_task:
        room.timer_task.cancel()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_drawing_guess_scores_guesser_and_drawer():
    manager = SocketManager()
    room = Room("DRAW02", make_drawing_game(), time_limit=30, game_type="drawing")
    add_player(room, "p1", "Alice")
    add_player(room, "p2", "Bob")
    room.current_question_index = 0
    room.state = "QUESTION"
    room.question_start_time = 0
    room.current_drawer = "Alice"

    await manager._handle_drawing_guess(room, "p2", {"type": "GUESS", "guess": "robot cook"})

    assert "Bob" in room.correct_guessers
    assert room.players["p2"]["score"] > 0
    assert room.players["p1"]["score"] >= 200


@pytest.mark.asyncio
async def test_drawing_manual_mode_does_not_schedule_auto_advance():
    manager = SocketManager()
    game = make_drawing_game()
    game["auto_advance"] = False
    room = Room("DRAW03", game, time_limit=30, game_type="drawing")
    add_player(room, "p1", "Alice")
    add_player(room, "p2", "Bob")
    room.current_question_index = 0
    room.state = "LEADERBOARD"
    room.current_drawer = "Alice"

    await manager._end_drawing_round(room)

    assert room.drawing_auto_task is None


@pytest.mark.asyncio
async def test_drawing_auto_mode_schedules_inter_round_pause():
    manager = SocketManager()
    game = make_drawing_game()
    game["auto_advance"] = True
    game["inter_round_seconds"] = 5
    room = Room("DRAW04", game, time_limit=30, game_type="drawing")
    add_player(room, "p1", "Alice")
    add_player(room, "p2", "Bob")
    room.current_question_index = 0
    room.state = "LEADERBOARD"
    room.current_drawer = "Alice"

    await manager._end_drawing_round(room)

    assert room.drawing_auto_task is not None
    room.drawing_auto_task.cancel()
    await asyncio.sleep(0)
