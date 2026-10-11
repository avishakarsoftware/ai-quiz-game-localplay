"""Classic authoring preserves two through four choices across import/save/update."""
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.mark.parametrize("count", [2, 3, 4])
def test_classic_choices_survive_import_update_and_save(count):
    quiz = {"quiz_title": "Capital cities", "questions": [{
        "id": 1, "text": "Choose a city", "options": ["Paris", "Rome", "Oslo", "Lima"][:count],
        "answer_index": count - 1,
    }]}
    with TestClient(app) as client:
        imported = client.post("/quiz/import", json={"quiz": quiz})
        assert imported.status_code == 200
        quiz_id = imported.json()["quiz_id"]
        updated = client.put(f"/quiz/{quiz_id}", json=quiz)
        assert updated.status_code == 200
        assert updated.json()["quiz"]["questions"][0]["options"] == quiz["questions"][0]["options"]
        saved = client.post("/quiz-packs", json={"quiz": quiz})
        assert saved.status_code == 200
        pack_id = saved.json()["pack"]["id"]
        materialized = client.post(f"/quiz-packs/{pack_id}/materialize")
        assert materialized.status_code == 200
        assert materialized.json()["quiz"]["questions"][0]["options"] == quiz["questions"][0]["options"]


@pytest.mark.parametrize("question", [None, 1, {"id": 1, "text": "City?",
    "options": ["Paris", "Rome"], "answer_index": True}])
def test_invalid_questions_return_validation_error(question):
    quiz = {"quiz_title": "Invalid", "questions": [question]}
    with TestClient(app) as client:
        assert client.post("/quiz/import", json={"quiz": quiz}).status_code == 422
        assert client.post("/quiz-packs", json={"quiz": quiz}).status_code == 422
