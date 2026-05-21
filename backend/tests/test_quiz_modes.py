"""Quiz variant mode prompt tests."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from quiz_engine import _build_system_prompt, _shuffle_question_options, _validate_quiz


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


def test_shuffle_question_options_preserves_correct_answer(monkeypatch):
    quiz = {
        "quiz_title": "Emoji Charades",
        "questions": [
            {
                "id": 1,
                "text": "🎬 🦁 👑",
                "options": ["The Lion King", "Madagascar", "Zootopia", "Jumanji"],
                "answer_index": 0,
            },
        ],
    }

    def reverse_shuffle(items):
        items.reverse()

    monkeypatch.setattr("quiz_engine.random.shuffle", reverse_shuffle)
    shuffled = _shuffle_question_options(quiz, mode="emoji_charades")

    question = shuffled["questions"][0]
    assert question["options"] == ["Jumanji", "Zootopia", "Madagascar", "The Lion King"]
    assert question["answer_index"] == 3
    assert question["options"][question["answer_index"]] == "The Lion King"


def test_shuffle_question_options_keeps_true_false_order(monkeypatch):
    quiz = {
        "quiz_title": "Fact or Fiction",
        "questions": [
            {
                "id": 1,
                "text": "The Earth is round.",
                "options": ["True", "False"],
                "answer_index": 0,
            },
        ],
    }

    def fail_if_called(_items):
        raise AssertionError("fact_fiction options should not be shuffled")

    monkeypatch.setattr("quiz_engine.random.shuffle", fail_if_called)
    shuffled = _shuffle_question_options(quiz, mode="fact_fiction")

    question = shuffled["questions"][0]
    assert question["options"] == ["True", "False"]
    assert question["answer_index"] == 0


def test_shuffle_question_options_leaves_two_option_classic_questions_alone(monkeypatch):
    quiz = {
        "quiz_title": "Classic",
        "questions": [
            {
                "id": 1,
                "text": "The Earth is round.",
                "options": ["True", "False"],
                "answer_index": 1,
            },
        ],
    }

    def fail_if_called(_items):
        raise AssertionError("two-option questions should not be shuffled")

    monkeypatch.setattr("quiz_engine.random.shuffle", fail_if_called)
    shuffled = _shuffle_question_options(quiz, mode="classic")

    question = shuffled["questions"][0]
    assert question["options"] == ["True", "False"]
    assert question["answer_index"] == 1
