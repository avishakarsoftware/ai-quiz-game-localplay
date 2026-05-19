"""Tests for thinking-leak defense in quiz/mlt engines."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from quiz_engine import _strip_thinking_leaks, _extract_gemini_text


class TestStripThinkingLeaks:
    def test_removes_think_tags(self):
        text = '<think>I should generate a quiz about colors</think>{"quiz_title": "Colors"}'
        assert _strip_thinking_leaks(text) == '{"quiz_title": "Colors"}'

    def test_removes_thinking_tags(self):
        text = '<thinking>Let me think about this...</thinking>\n{"quiz_title": "Test"}'
        assert _strip_thinking_leaks(text) == '{"quiz_title": "Test"}'

    def test_removes_multiline_thinking(self):
        text = '<think>\nStep 1: consider the topic\nStep 2: generate questions\n</think>\n{"quiz_title": "Test"}'
        result = _strip_thinking_leaks(text)
        assert "<think>" not in result
        assert "quiz_title" in result

    def test_no_thinking_passthrough(self):
        text = '{"quiz_title": "No thinking here"}'
        assert _strip_thinking_leaks(text) == text

    def test_empty_string(self):
        assert _strip_thinking_leaks("") == ""


class TestExtractGeminiText:
    def test_normal_response(self):
        result = {
            "candidates": [{"content": {"parts": [
                {"text": '{"quiz_title": "Test"}'}
            ]}}]
        }
        assert _extract_gemini_text(result) == '{"quiz_title": "Test"}'

    def test_filters_thought_parts(self):
        result = {
            "candidates": [{"content": {"parts": [
                {"text": "I need to think about colors...", "thought": True},
                {"text": '{"quiz_title": "Colors Quiz"}'}
            ]}}]
        }
        text = _extract_gemini_text(result)
        assert "I need to think" not in text
        assert "Colors Quiz" in text

    def test_filters_thought_and_strips_leaks(self):
        """Both layers: structural filter + regex strip."""
        result = {
            "candidates": [{"content": {"parts": [
                {"text": "Deep reasoning here", "thought": True},
                {"text": '<think>more reasoning</think>{"quiz_title": "Test"}'}
            ]}}]
        }
        text = _extract_gemini_text(result)
        assert "Deep reasoning" not in text
        assert "more reasoning" not in text
        assert "quiz_title" in text

    def test_all_thought_parts_returns_none(self):
        result = {
            "candidates": [{"content": {"parts": [
                {"text": "Only thinking", "thought": True},
            ]}}]
        }
        assert _extract_gemini_text(result) is None

    def test_missing_candidates_returns_none(self):
        assert _extract_gemini_text({}) is None
        assert _extract_gemini_text({"candidates": []}) is None

    def test_thought_false_is_kept(self):
        result = {
            "candidates": [{"content": {"parts": [
                {"text": "kept", "thought": False},
            ]}}]
        }
        assert _extract_gemini_text(result) == "kept"
