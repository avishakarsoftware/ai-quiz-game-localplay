"""Tests for engine_common — the single sanitization/clamp policy all engines share."""
import engine_common
from engine_common import GameEngine, clamp_int, clean_text, make_clean_text


class TestCleanText:
    def test_strips_control_chars(self):
        assert clean_text("a\x00b\x07c\x7fd") == "abcd"

    def test_strips_dangerous_tags(self):
        assert clean_text("<script>alert(1)</script>hello") == "alert(1)hello"
        assert clean_text("<IFRAME src=x>hi</IFRAME>") == "hi"

    def test_strips_all_html_tags(self):
        # The security baseline: not just script/style/iframe — ALL tags go.
        assert clean_text("<b>bold</b> <img src=x onerror=alert(1)> text") == "bold text"

    def test_collapses_whitespace_and_trims(self):
        assert clean_text("  a \n\n b\t c  ") == "a b c"

    def test_caps_length(self):
        assert clean_text("x" * 500, max_chars=10) == "x" * 10

    def test_none_and_junk(self):
        assert clean_text(None) == ""
        assert clean_text(12345) == "12345"

    def test_make_clean_text_binds_default(self):
        short = make_clean_text(max_chars=5)
        assert short("abcdefgh") == "abcde"
        assert short("abcdefgh", 3) == "abc"  # explicit arg still wins


class TestPreviouslyLaxEnginesNowStrict:
    """story_chain / common_ground / two_truths / find_someone used to skip the
    all-tag strip. They now share the strict body — user text with embedded
    markup must come out tag-free in every engine."""

    def test_all_engines_share_strict_sanitizer(self):
        import common_ground_engine
        import find_someone_engine
        import story_chain_engine
        import two_truths_engine
        payload = '<img src=x onerror=alert(1)>hi <b>there</b>'
        for mod in (story_chain_engine, common_ground_engine, two_truths_engine, find_someone_engine):
            assert mod._clean_text(payload) == "hi there", mod.__name__


class TestClampInt:
    def test_in_range(self):
        assert clamp_int({"n": 7}, "n", 5, 1, 10) == 7

    def test_clamps_low_high(self):
        assert clamp_int({"n": -5}, "n", 5, 1, 10) == 1
        assert clamp_int({"n": 99}, "n", 5, 1, 10) == 10

    def test_default_and_junk(self):
        assert clamp_int({}, "n", 5, 1, 10) == 5
        assert clamp_int({"n": "junk"}, "n", 5, 1, 10) == 5
        assert clamp_int({"n": None}, "n", 5, 1, 10) == 5

    def test_string_number_coerces(self):
        assert clamp_int({"n": "8"}, "n", 5, 1, 10) == 8


class TestGameEngineProtocol:
    def test_engine_modules_satisfy_protocol(self):
        import find_someone_engine
        import party_quests_engine
        import survey_says_engine
        # Modules satisfy the Protocol structurally (required surface present).
        # (quiz_engine is the LLM generation engine, not a runtime GameEngine.)
        for mod in (party_quests_engine, find_someone_engine, survey_says_engine):
            assert isinstance(mod, GameEngine), mod.__name__
        assert hasattr(engine_common, "GameEngine")
