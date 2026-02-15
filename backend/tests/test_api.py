"""API endpoint tests using FastAPI TestClient."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from main import app, quizzes
import config


@pytest.fixture(autouse=True)
def clear_state():
    """Clear in-memory state before each test."""
    quizzes.clear()
    yield
    quizzes.clear()


client = TestClient(app)


# ---------------------------------------------------------------------------
# Health & Root
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    def test_root(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "running" in res.json()["message"].lower()

    def test_health(self):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "healthy"

    def test_system_info(self):
        res = client.get("/system/info")
        assert res.status_code == 200
        assert "ip" in res.json()


# ---------------------------------------------------------------------------
# Quiz CRUD Tests
# ---------------------------------------------------------------------------

def seed_quiz():
    """Insert a quiz directly and return its id."""
    quiz_data = {
        "quiz_title": "Test Quiz",
        "questions": [
            {"id": 1, "text": "Q1?", "options": ["A", "B", "C", "D"], "answer_index": 0, "image_prompt": "test"},
            {"id": 2, "text": "Q2?", "options": ["True", "False"], "answer_index": 1, "image_prompt": "test"},
            {"id": 3, "text": "Q3?", "options": ["A", "B", "C", "D"], "answer_index": 2, "image_prompt": "test"},
        ],
    }
    import uuid
    quiz_id = str(uuid.uuid4())
    quizzes[quiz_id] = quiz_data
    return quiz_id


class TestQuizGet:
    def test_get_existing_quiz(self):
        qid = seed_quiz()
        res = client.get(f"/quiz/{qid}")
        assert res.status_code == 200
        assert res.json()["quiz_title"] == "Test Quiz"
        assert len(res.json()["questions"]) == 3

    def test_get_nonexistent_quiz(self):
        res = client.get("/quiz/nonexistent")
        assert res.status_code == 404


class TestQuizUpdate:
    def test_update_quiz_success(self):
        qid = seed_quiz()
        updated = {
            "quiz_title": "Updated Title",
            "questions": [
                {"id": 1, "text": "Updated Q1?", "options": ["X", "Y", "Z", "W"], "answer_index": 3, "image_prompt": "test"},
            ],
        }
        res = client.put(f"/quiz/{qid}", json=updated)
        assert res.status_code == 200
        assert res.json()["quiz"]["quiz_title"] == "Updated Title"
        assert len(res.json()["quiz"]["questions"]) == 1

        # Verify persisted
        res2 = client.get(f"/quiz/{qid}")
        assert res2.json()["quiz_title"] == "Updated Title"

    def test_update_quiz_not_found(self):
        res = client.put("/quiz/nonexistent", json={
            "quiz_title": "T",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0}],
        })
        assert res.status_code == 404

    def test_update_quiz_empty_questions_rejected(self):
        qid = seed_quiz()
        res = client.put(f"/quiz/{qid}", json={"quiz_title": "T", "questions": []})
        assert res.status_code == 422  # Pydantic validation error

    def test_update_quiz_invalid_answer_index(self):
        qid = seed_quiz()
        res = client.put(f"/quiz/{qid}", json={
            "quiz_title": "T",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B"], "answer_index": 5}],
        })
        assert res.status_code == 422

    def test_update_quiz_three_options_rejected(self):
        qid = seed_quiz()
        res = client.put(f"/quiz/{qid}", json={
            "quiz_title": "T",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B", "C"], "answer_index": 0}],
        })
        assert res.status_code == 422

    def test_update_quiz_tf_valid(self):
        qid = seed_quiz()
        res = client.put(f"/quiz/{qid}", json={
            "quiz_title": "TF Quiz",
            "questions": [{"id": 1, "text": "Earth is round?", "options": ["True", "False"], "answer_index": 0}],
        })
        assert res.status_code == 200
        assert len(res.json()["quiz"]["questions"][0]["options"]) == 2


class TestQuizDeleteQuestion:
    def test_delete_question_success(self):
        qid = seed_quiz()
        res = client.delete(f"/quiz/{qid}/question/2")
        assert res.status_code == 200
        assert len(res.json()["quiz"]["questions"]) == 2
        ids = [q["id"] for q in res.json()["quiz"]["questions"]]
        assert 2 not in ids

    def test_delete_question_not_found(self):
        qid = seed_quiz()
        res = client.delete(f"/quiz/{qid}/question/999")
        assert res.status_code == 404

    def test_delete_quiz_not_found(self):
        res = client.delete("/quiz/nonexistent/question/1")
        assert res.status_code == 404

    def test_delete_last_question_rejected(self):
        """Cannot delete the only remaining question."""
        qid = seed_quiz()
        # Delete 2 of 3
        client.delete(f"/quiz/{qid}/question/2")
        client.delete(f"/quiz/{qid}/question/3")
        # Try to delete the last one
        res = client.delete(f"/quiz/{qid}/question/1")
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Difficulty Validation Tests
# ---------------------------------------------------------------------------

class TestDifficultyValidation:
    def test_valid_difficulties(self):
        for d in ("easy", "medium", "hard"):
            assert d in config.VALID_DIFFICULTIES

    def test_quiz_request_default_difficulty(self):
        """Default difficulty should be 'medium'."""
        from main import QuizRequest
        req = QuizRequest(prompt="test topic")
        assert req.difficulty == "medium"

    def test_quiz_request_valid_difficulties(self):
        from main import QuizRequest
        for d in ("easy", "medium", "hard"):
            req = QuizRequest(prompt="test", difficulty=d)
            assert req.difficulty == d

    def test_quiz_request_invalid_difficulty(self):
        from main import QuizRequest
        with pytest.raises(Exception):
            QuizRequest(prompt="test", difficulty="impossible")

    def test_quiz_request_case_insensitive(self):
        from main import QuizRequest
        req = QuizRequest(prompt="test", difficulty="EASY")
        assert req.difficulty == "easy"


# ---------------------------------------------------------------------------
# Room Creation Tests
# ---------------------------------------------------------------------------

class TestRoomCreation:
    def test_create_room_success(self):
        qid = seed_quiz()
        res = client.post("/room/create", json={"quiz_id": qid, "time_limit": 20})
        assert res.status_code == 200
        assert "room_code" in res.json()
        assert len(res.json()["room_code"]) == 6

    def test_create_room_quiz_not_found(self):
        res = client.post("/room/create", json={"quiz_id": "nonexistent", "time_limit": 15})
        assert res.status_code == 404

    def test_create_room_invalid_time_limit(self):
        qid = seed_quiz()
        res = client.post("/room/create", json={"quiz_id": qid, "time_limit": 2})
        assert res.status_code == 422
        res = client.post("/room/create", json={"quiz_id": qid, "time_limit": 120})
        assert res.status_code == 422

    def test_create_room_default_time_limit(self):
        qid = seed_quiz()
        res = client.post("/room/create", json={"quiz_id": qid})
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# Prompt Validation Tests
# ---------------------------------------------------------------------------

class TestPromptValidation:
    def test_empty_prompt_rejected(self):
        res = client.post("/quiz/generate", json={"prompt": ""})
        assert res.status_code == 422

    def test_whitespace_prompt_rejected(self):
        res = client.post("/quiz/generate", json={"prompt": "   "})
        assert res.status_code == 422

    def test_long_prompt_rejected(self):
        res = client.post("/quiz/generate", json={"prompt": "x" * 501})
        assert res.status_code == 422


# ---------------------------------------------------------------------------
# Num Questions Validation
# ---------------------------------------------------------------------------

class TestNumQuestions:
    def test_default_num_questions(self):
        from main import QuizRequest
        req = QuizRequest(prompt="test")
        assert req.num_questions == config.DEFAULT_NUM_QUESTIONS

    def test_valid_num_questions(self):
        from main import QuizRequest
        req = QuizRequest(prompt="test", num_questions=5)
        assert req.num_questions == 5

    def test_too_few_questions_rejected(self):
        from main import QuizRequest
        with pytest.raises(Exception):
            QuizRequest(prompt="test", num_questions=2)

    def test_too_many_questions_rejected(self):
        from main import QuizRequest
        with pytest.raises(Exception):
            QuizRequest(prompt="test", num_questions=25)


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

class TestExportImport:
    def test_export_quiz(self):
        qid = seed_quiz()
        res = client.get(f"/quiz/{qid}/export")
        assert res.status_code == 200
        assert res.json()["quiz"]["quiz_title"] == "Test Quiz"

    def test_export_nonexistent(self):
        res = client.get("/quiz/nonexistent/export")
        assert res.status_code == 404

    def test_import_quiz(self):
        quiz_data = {
            "quiz_title": "Imported Quiz",
            "questions": [
                {"id": 1, "text": "Q?", "options": ["A", "B", "C", "D"], "answer_index": 0},
            ],
        }
        res = client.post("/quiz/import", json={"quiz": quiz_data})
        assert res.status_code == 200
        assert res.json()["quiz"]["quiz_title"] == "Imported Quiz"
        # Verify it was stored
        qid = res.json()["quiz_id"]
        res2 = client.get(f"/quiz/{qid}")
        assert res2.status_code == 200

    def test_import_invalid_quiz(self):
        res = client.post("/quiz/import", json={"quiz": {"title": "bad"}})
        assert res.status_code == 422

    def test_roundtrip_export_import(self):
        """Export a quiz and re-import it."""
        qid = seed_quiz()
        exported = client.get(f"/quiz/{qid}/export").json()["quiz"]
        res = client.post("/quiz/import", json={"quiz": exported})
        assert res.status_code == 200
        new_qid = res.json()["quiz_id"]
        assert new_qid != qid  # Different ID
        assert res.json()["quiz"]["quiz_title"] == "Test Quiz"


# ---------------------------------------------------------------------------
# Game History
# ---------------------------------------------------------------------------

class TestGameHistory:
    def test_empty_history(self):
        res = client.get("/history")
        assert res.status_code == 200
        assert isinstance(res.json()["games"], list)

    def test_game_detail_not_found(self):
        res = client.get("/history/NONEXISTENT")
        assert res.status_code == 404
