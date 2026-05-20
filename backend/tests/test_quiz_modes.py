"""Quiz variant mode prompt tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from quiz_engine import _build_system_prompt, _validate_quiz


def test_fact_fiction_prompt_requires_true_false_options():
    prompt = _build_system_prompt("medium", 5, mode="fact_fiction")

    assert "Fact or Fiction" in prompt
    assert '["True", "False"]' in prompt


def test_fact_fiction_validation_rejects_multiple_choice_options():
    quiz = {
        "quiz_title": "Bad Fact/Fiction",
        "questions": [
            {"id": 1, "text": "A claim", "options": ["A", "B", "C", "D"], "answer_index": 0},
        ],
    }

    assert _validate_quiz(quiz, attempt=1, mode="fact_fiction") is False


def test_rebus_prompt_contains_rebus_instructions():
    prompt = _build_system_prompt("easy", 5, mode="rebus")

    assert "Rebus Rush" in prompt
    assert "emoji/symbol rebus clues" in prompt
