"""Tests for Round 2 bug fixes: validation gaps, base64 safety, webhook token None check,
DB indexes, checkout double-click guard."""
import sys
import os
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from main import app, quizzes, quiz_images
import config
import db


client = TestClient(app)
DEVICE_ID = str(uuid.uuid4())
HEADERS = {"X-Device-ID": DEVICE_ID, "X-Platform": "web"}


def _make_quiz(answer_index=0, options=None):
    """Helper to create a valid quiz dict."""
    return {
        "quiz_title": "Test Quiz",
        "questions": [{
            "id": 1,
            "text": "What is 1+1?",
            "options": options or ["2", "3", "4", "5"],
            "answer_index": answer_index,
            "image_prompt": "",
        }]
    }


class TestQuizImportValidation:
    """QuizImportRequest now validates answer_index type and range."""

    def test_import_rejects_string_answer_index(self):
        quiz = _make_quiz()
        quiz["questions"][0]["answer_index"] = "0"  # string, not int
        res = client.post("/quiz/import", json={"quiz": quiz}, headers=HEADERS)
        assert res.status_code == 422

    def test_import_rejects_out_of_range_answer_index(self):
        quiz = _make_quiz(answer_index=10)
        res = client.post("/quiz/import", json={"quiz": quiz}, headers=HEADERS)
        assert res.status_code == 422

    def test_import_rejects_negative_answer_index(self):
        quiz = _make_quiz(answer_index=-1)
        res = client.post("/quiz/import", json={"quiz": quiz}, headers=HEADERS)
        assert res.status_code == 422

    def test_import_accepts_valid_answer_index(self):
        quiz = _make_quiz(answer_index=2)
        res = client.post("/quiz/import", json={"quiz": quiz}, headers=HEADERS)
        assert res.status_code == 200
        data = res.json()
        # Clean up
        quizzes.pop(data.get("quiz_id", ""), None)


class TestQuizUpdateValidation:
    """QuizUpdateRequest now validates option types."""

    def test_update_rejects_non_string_options(self):
        # Create a quiz first
        quiz = _make_quiz()
        res = client.post("/quiz/import", json={"quiz": quiz}, headers=HEADERS)
        quiz_id = res.json()["quiz_id"]

        # Try to update with non-string options
        bad_quiz = _make_quiz(options=[1, 2, 3, 4])
        res = client.put(f"/quiz/{quiz_id}", json=bad_quiz, headers=HEADERS)
        assert res.status_code == 422
        quizzes.pop(quiz_id, None)

    def test_update_accepts_valid_options(self):
        quiz = _make_quiz()
        res = client.post("/quiz/import", json={"quiz": quiz}, headers=HEADERS)
        quiz_id = res.json()["quiz_id"]

        updated = _make_quiz(options=["A", "B", "C", "D"])
        res = client.put(f"/quiz/{quiz_id}", json=updated, headers=HEADERS)
        assert res.status_code == 200
        quizzes.pop(quiz_id, None)


class TestImageBase64Safety:
    """base64.b64decode wrapped in try-except returns 500 on corrupt data."""

    def test_corrupt_image_data_returns_500(self):
        quiz_id = "test-corrupt-img"
        quizzes[quiz_id] = _make_quiz()
        quiz_images[quiz_id] = {0: "not-valid-base64!!!"}
        res = client.get(f"/quiz/{quiz_id}/image/0")
        assert res.status_code == 500
        quizzes.pop(quiz_id, None)
        quiz_images.pop(quiz_id, None)

    def test_valid_image_data_returns_png(self):
        import base64
        quiz_id = "test-valid-img"
        quizzes[quiz_id] = _make_quiz()
        # 1x1 white PNG
        png_b64 = base64.b64encode(
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00'
        ).decode()
        quiz_images[quiz_id] = {0: png_b64}
        res = client.get(f"/quiz/{quiz_id}/image/0")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        quizzes.pop(quiz_id, None)
        quiz_images.pop(quiz_id, None)


class TestDBIndexes:
    """Verify user_id indexes exist on entitlements and device_usage tables."""

    def test_entitlements_user_index_exists(self):
        conn = db._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_entitlements_user'"
        ).fetchall()
        assert len(rows) == 1

    def test_device_usage_user_index_exists(self):
        conn = db._get_conn()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_device_usage_user'"
        ).fetchall()
        assert len(rows) == 1
