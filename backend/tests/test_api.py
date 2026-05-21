"""API endpoint tests using FastAPI TestClient."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
import main
from main import app, quizzes
from media_store import media_store
import config


@pytest.fixture(autouse=True)
def clear_state():
    """Clear in-memory state before each test."""
    quizzes.clear()
    media_store.clear()
    yield
    quizzes.clear()
    media_store.clear()


client = TestClient(app)
AUTH_HEADERS = {"X-Device-Id": "11111111-1111-4111-8111-111111111111"}


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

    def test_system_info_requires_admin(self):
        res = client.get("/system/info")
        assert res.status_code in (403, 401)  # blocked without admin key


class TestFrontendStaticServing:
    def test_root_serves_api_status_without_frontend_build(self):
        res = client.get("/")
        assert res.status_code == 200
        assert "running" in res.json()["message"].lower()

    def test_root_serves_frontend_when_build_exists(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html><body>LocalPlay</body></html>")
        monkeypatch.setattr(main, "FRONTEND_DIST_DIR", tmp_path)

        res = client.get("/")

        assert res.status_code == 200
        assert "LocalPlay" in res.text
        assert res.headers["content-type"].startswith("text/html")

    def test_spa_route_serves_frontend_when_build_exists(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html><body>SPA</body></html>")
        monkeypatch.setattr(main, "FRONTEND_DIST_DIR", tmp_path)

        res = client.get("/join")

        assert res.status_code == 200
        assert "SPA" in res.text

    def test_unknown_api_route_stays_json_404(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html><body>SPA</body></html>")
        monkeypatch.setattr(main, "FRONTEND_DIST_DIR", tmp_path)

        res = client.get("/quiz/not-real/export")

        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/json")

    def test_missing_static_asset_returns_404(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html><body>SPA</body></html>")
        monkeypatch.setattr(main, "FRONTEND_DIST_DIR", tmp_path)

        res = client.get("/assets/missing.js")

        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/json")

    def test_media_route_stays_json_404_with_frontend_build(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html><body>SPA</body></html>")
        monkeypatch.setattr(main, "FRONTEND_DIST_DIR", tmp_path)

        res = client.get("/media/not-real")

        assert res.status_code == 404
        assert res.headers["content-type"].startswith("application/json")

    def test_static_file_path_traversal_falls_back_to_index(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<html><body>SPA</body></html>")
        monkeypatch.setattr(main, "FRONTEND_DIST_DIR", tmp_path)

        response = main._frontend_file_response("../../etc/passwd")

        assert response.path == tmp_path / "index.html"


class TestMediaEndpoints:
    def test_media_status(self, monkeypatch):
        async def available():
            return True

        monkeypatch.setattr(main.image_engine, "is_available", available)

        res = client.get("/media/status")

        assert res.status_code == 200
        body = res.json()
        assert body["generation_available"] is True
        assert body["storage_backend"] == "memory"
        assert body["providers"][0]["id"] == "stable_diffusion"

    def test_quiz_image_generation_creates_media_asset(self, monkeypatch):
        import base64

        async def available():
            return True

        async def generate_image(prompt, style="vibrant"):
            assert prompt
            return base64.b64encode(
                b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
                b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
            ).decode()

        monkeypatch.setattr(main.image_engine, "is_available", available)
        monkeypatch.setattr(main.image_engine, "generate_image", generate_image)
        qid = seed_quiz()

        res = client.post(
            "/quiz/generate-images",
            json={"quiz_id": qid, "question_id": 1},
            headers={"X-Device-Id": "media-test-wallet"},
        )

        assert res.status_code == 200
        asset = res.json()["asset"]
        assert asset["url"].startswith("/media/img_")
        assert main.quizzes[qid]["questions"][0]["image_url"] == asset["url"]

        media_res = client.get(asset["url"])
        assert media_res.status_code == 200
        assert media_res.headers["content-type"] == "image/png"


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


class TestQuizModes:
    def test_generate_accepts_quiz_variant_mode(self, monkeypatch):
        captured = {}

        async def fake_generate(prompt, difficulty, num_questions, provider, model_override=None, mode="classic"):
            captured["mode"] = mode
            return {
                "quiz_title": "Rebus Rush",
                "questions": [
                    {"id": 1, "text": "🌊 + 🐴", "options": ["Seahorse", "Ocean Pony", "Beach Ride", "Water Polo"], "answer_index": 0},
                ],
            }

        monkeypatch.setattr(main.quiz_engine, "generate_quiz", fake_generate)

        res = client.post(
            "/quiz/generate",
            json={"prompt": "animals", "difficulty": "easy", "num_questions": 5, "mode": "rebus", "provider": "gemini"},
            headers={"X-Device-Id": "11111111-1111-1111-1111-111111111111"},
        )

        assert res.status_code == 200
        assert captured["mode"] == "rebus"
        assert "answer_index" not in res.json()["quiz"]["questions"][0]

    def test_generate_rejects_invalid_quiz_variant_mode(self):
        res = client.post(
            "/quiz/generate",
            json={"prompt": "animals", "difficulty": "easy", "num_questions": 5, "mode": "nope"},
            headers={"X-Device-Id": "11111111-1111-1111-1111-111111111112"},
        )

        assert res.status_code == 422


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

    def test_import_quiz_preserves_allowed_image_url(self):
        quiz_data = {
            "quiz_title": "Imported Quiz",
            "questions": [
                {
                    "id": 1,
                    "text": "Who is pictured?",
                    "options": ["A", "B", "C", "D"],
                    "answer_index": 0,
                    "image_url": "https://media.revelryapp.me/apps/localplay/gamma/uploads/test.webp",
                    "image_alt": "A trophy photo",
                },
            ],
        }
        res = client.post("/quiz/import", json={"quiz": quiz_data})
        assert res.status_code == 200
        question = res.json()["quiz"]["questions"][0]
        assert question["image_url"] == quiz_data["questions"][0]["image_url"]
        assert question["image_alt"] == "A trophy photo"

    def test_import_quiz_strips_external_image_url(self):
        quiz_data = {
            "quiz_title": "Imported Quiz",
            "questions": [
                {
                    "id": 1,
                    "text": "Who is pictured?",
                    "options": ["A", "B", "C", "D"],
                    "answer_index": 0,
                    "image_url": "https://example.com/image.jpg",
                },
            ],
        }
        res = client.post("/quiz/import", json={"quiz": quiz_data})
        assert res.status_code == 200
        assert "image_url" not in res.json()["quiz"]["questions"][0]

    def test_import_invalid_quiz(self):
        res = client.post("/quiz/import", json={"quiz": {"title": "bad"}})
        assert res.status_code == 422

    def test_export_includes_answers_for_owner(self):
        """Exported quiz includes answer_index (owner-protected endpoint)."""
        qid = seed_quiz()
        exported = client.get(f"/quiz/{qid}/export").json()["quiz"]
        for q in exported["questions"]:
            assert "answer_index" in q

    def test_roundtrip_export_import_succeeds(self):
        """Exported quiz can be re-imported (answers included for owner)."""
        qid = seed_quiz()
        exported = client.get(f"/quiz/{qid}/export").json()["quiz"]
        res = client.post("/quiz/import", json={"quiz": exported})
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# Custom Quiz Packs
# ---------------------------------------------------------------------------

class TestCustomQuizPacks:
    def test_save_list_and_materialize_quiz_pack(self):
        quiz_data = {
            "quiz_title": "Saved Custom Quiz",
            "questions": [
                {
                    "id": 1,
                    "text": "Who is pictured?",
                    "options": ["A", "B", "C", "D"],
                    "answer_index": 0,
                    "image_url": "https://media.revelryapp.me/apps/localplay/gamma/uploads/test.webp",
                    "image_alt": "A trophy photo",
                },
            ],
        }
        save_res = client.post("/quiz-packs", json={"quiz": quiz_data}, headers=AUTH_HEADERS)
        assert save_res.status_code == 200
        pack = save_res.json()["pack"]
        assert pack["title"] == "Saved Custom Quiz"
        assert pack["question_count"] == 1

        list_res = client.get("/quiz-packs", headers=AUTH_HEADERS)
        assert list_res.status_code == 200
        assert any(p["id"] == pack["id"] for p in list_res.json()["packs"])

        materialize_res = client.post(f"/quiz-packs/{pack['id']}/materialize", headers=AUTH_HEADERS)
        assert materialize_res.status_code == 200
        assert materialize_res.json()["quiz"]["questions"][0]["image_url"] == quiz_data["questions"][0]["image_url"]

    def test_delete_quiz_pack(self):
        quiz_data = {
            "quiz_title": "Delete Me",
            "questions": [{"id": 1, "text": "Q?", "options": ["A", "B"], "answer_index": 0}],
        }
        pack = client.post("/quiz-packs", json={"quiz": quiz_data}, headers=AUTH_HEADERS).json()["pack"]
        res = client.delete(f"/quiz-packs/{pack['id']}", headers=AUTH_HEADERS)
        assert res.status_code == 200
        list_res = client.get("/quiz-packs", headers=AUTH_HEADERS)
        assert all(p["id"] != pack["id"] for p in list_res.json()["packs"])


# ---------------------------------------------------------------------------
# Media Uploads
# ---------------------------------------------------------------------------

class TestMediaUploads:
    def test_media_status_reports_upload_config(self, monkeypatch):
        monkeypatch.setattr(config, "MEDIA_UPLOAD_URL", "https://media.revelryapp.me/apps/localplay/upload.php")
        monkeypatch.setattr(config, "MEDIA_PUBLIC_BASE_URL", "https://media.revelryapp.me/apps/localplay")
        monkeypatch.setattr(config, "MEDIA_UPLOAD_SECRET", "super-secret")
        res = client.get("/media/status")
        assert res.status_code == 200
        assert res.json()["upload_available"] is True
        assert res.json()["storage_backend"] == "ionos"

    def test_create_media_upload_url_and_finalize(self, monkeypatch):
        monkeypatch.setattr(config, "MEDIA_UPLOAD_URL", "https://media.revelryapp.me/apps/localplay/upload.php")
        monkeypatch.setattr(config, "MEDIA_PUBLIC_BASE_URL", "https://media.revelryapp.me/apps/localplay")
        monkeypatch.setattr(config, "MEDIA_UPLOAD_SECRET", "super-secret")
        monkeypatch.setattr(config, "MEDIA_PATH_PREFIX", "gamma")
        res = client.post(
            "/media/upload-url",
            json={"filename": "pic.webp", "mime_type": "image/webp", "bytes": 1234},
            headers=AUTH_HEADERS,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["asset"]["public_url"].startswith("https://media.revelryapp.me/apps/localplay/gamma/uploads/")
        assert body["upload"]["fields"]["token"]

        finalize = client.post(
            f"/media/{body['asset']['id']}/finalize",
            json={"bytes": 1234, "alt_text": "Alt"},
            headers=AUTH_HEADERS,
        )
        assert finalize.status_code == 200
        assert finalize.json()["asset"]["status"] == "ready"


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
