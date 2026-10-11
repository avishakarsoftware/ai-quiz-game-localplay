"""Exact mutation snapshots over real PostgREST, on the opt-in local harness."""
import uuid

import pytest

import config
import main
from integration_clock import resource_updated_at
from postgrest_harness import HARNESS_READY, SKIP_REASON, _proxy_base_url, postgrest_stack, sdb

pytestmark = pytest.mark.skipif(not HARNESS_READY, reason=SKIP_REASON)
QUESTIONS = [{"text":"Question?","options":["A","B"],"answer_index":0}]


@pytest.fixture(params=["games_", "games_gamma_"])
def adapter(sdb, monkeypatch, request):
    monkeypatch.setattr(config, "TABLE_PREFIX", request.param)
    monkeypatch.setattr(sdb, "_client", None)
    return sdb


def test_real_rest_content_save_delete_return_exact_payload_and_clock(adapter):
    owner = "clock_" + uuid.uuid4().hex
    quiz = adapter.save_quiz_pack(owner, "First", QUESTIONS)
    changed = adapter.save_quiz_pack(owner, "Second", QUESTIONS, quiz["id"])
    assert quiz["title"] == "First" and changed["title"] == "Second"
    assert resource_updated_at(quiz) < resource_updated_at(changed)
    assert adapter.delete_quiz_pack("stranger", quiz["id"], return_snapshot=True) is None
    deleted = adapter.delete_quiz_pack(owner, quiz["id"], return_snapshot=True)
    assert deleted["title"] == "Second" and resource_updated_at(deleted) > resource_updated_at(changed)
    assert adapter.get_quiz_pack(owner, quiz["id"]) is None
    content = adapter.save_game_content(owner, "drawing", "Original", {"game":{"prompts":["cat"]}})
    updated = adapter.save_game_content(owner, "drawing", "Edited", {"game":{"prompts":["dog"]}}, content["id"])
    assert resource_updated_at(content) < resource_updated_at(updated)
    assert content["payload"]["game"]["prompts"] == ["cat"]
    assert adapter.delete_game_content("stranger", content["id"], return_snapshot=True) is None
    removed = adapter.delete_game_content(owner, content["id"], return_snapshot=True)
    assert removed["title"] == "Edited" and removed["payload"]["game"]["prompts"] == ["dog"]
    assert resource_updated_at(removed) > resource_updated_at(updated)
    assert adapter.get_game_content(owner, content["id"]) is None


@pytest.mark.parametrize("terminal", ["cancelled","expired","superseded","complete"])
def test_real_rest_terminal_poll_uses_exact_saved_transition_clock(adapter, terminal):
    identity = uuid.uuid4().hex
    initial = adapter.create_game_session({"id":identity,"host_app":"revelry","external_container_id":identity,"external_container_type":"party","game_type":"quiz","room_code":identity[:6]})
    started = adapter.update_game_session(identity,{"status":"active","started_at":initial["created_at"]})
    closed = adapter.update_game_session(identity,{"status":terminal,"joinable":False})
    assert resource_updated_at(initial) < resource_updated_at(started) < resource_updated_at(closed)
    assert main._format_session(closed)["updated_at"] == resource_updated_at(closed)
    assert main._format_session(adapter.get_game_session(identity))["updated_at"] == resource_updated_at(closed)
    assert main._format_session(closed)["status"] == terminal and main._format_session(closed)["joinable"] is False


def test_real_rest_rejects_caller_clock_authority(adapter):
    identity = uuid.uuid4().hex
    client = adapter._sb()
    original = client.insert("generated_content",{"id":identity,"wallet_id":"owner","content_type":"drawing","title":"Original","payload":{},"created_at":1,"updated_at":1,"integration_updated_at_us":999999999999999999})[0]
    assert original["integration_updated_at_us"] < 10**16
    current = original
    for attempted in (1,999999999999999999):
        updated = client.update("generated_content",{"integration_updated_at_us":attempted},filters={"id":f"eq.{identity}"})[0]
        assert updated["title"] == "Original" and updated["updated_at"] == 1
        assert current["integration_updated_at_us"] < updated["integration_updated_at_us"] < 10**16
        current = updated
