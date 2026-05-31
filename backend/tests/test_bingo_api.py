from fastapi.testclient import TestClient

import main
from main import app


client = TestClient(app)
AUTH_HEADERS = {"X-Device-Id": "11111111-1111-4111-8111-111111111111"}


def _deck(count=25):
    return [{"kind": "text", "display": f"Item {index}", "value": f"item {index}"} for index in range(count)]


def setup_function():
    main.bingo_games.clear()
    main.bingo_timestamps.clear()
    main.content_owners.clear()
    main.pending_generation_charges.clear()
    main.socket_manager.rooms.clear()


def teardown_function():
    setup_function()


def test_create_bingo_accepts_custom_text_deck():
    res = client.post(
        "/bingo/create",
        headers=AUTH_HEADERS,
        json={"game_title": "Custom Bingo", "deck": _deck(25), "free_center": True},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["bingo_id"] in main.bingo_games
    assert body["game"]["game_title"] == "Custom Bingo"
    assert len(body["game"]["deck"]) == 25


def test_create_bingo_rejects_too_small_deck():
    res = client.post(
        "/bingo/create",
        headers=AUTH_HEADERS,
        json={"game_title": "Tiny Bingo", "deck": _deck(10), "free_center": True},
    )
    assert res.status_code == 422


def test_generate_bingo_stores_generated_content(monkeypatch):
    async def fake_generate(prompt, difficulty, num_items, provider, model_override=None):
        return {
            "game_title": "Baby Bingo",
            "deck": _deck(30),
            "patterns": [],
            "free_center": True,
            "free_center_label": "FREE",
            "caller_mode": "manual",
            "claim_requires_latest_call": False,
        }

    monkeypatch.setattr(main.bingo_engine, "generate_game", fake_generate)
    res = client.post(
        "/bingo/generate",
        headers=AUTH_HEADERS,
        json={"prompt": "baby shower", "difficulty": "medium", "num_items": 30, "provider": "gemini"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["bingo_id"] in main.bingo_games
    assert body["bingo_id"] in main.pending_generation_charges
    assert body["game"]["game_title"] == "Baby Bingo"
    assert len(body["game"]["deck"]) == 30


def test_room_create_accepts_bingo_id():
    create = client.post(
        "/bingo/create",
        headers=AUTH_HEADERS,
        json={"game_title": "Room Bingo", "deck": _deck(25), "free_center": True},
    )
    bingo_id = create.json()["bingo_id"]
    res = client.post(
        "/room/create",
        headers=AUTH_HEADERS,
        json={"game_type": "bingo", "bingo_id": bingo_id},
    )
    assert res.status_code == 200, res.text
    room = main.socket_manager.rooms[res.json()["room_code"]]
    assert room.game_type == "bingo"
    assert room.content_id == bingo_id
