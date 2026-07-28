"""Guards for socket_manager's derived game-type sets.

Before this, three places hand-listed ~20 game types each ("resettable to", "does NOT use quiz-style
NEXT_QUESTION", "does NOT use the generic ANSWER"). Nothing forced you to update all three when
adding a game, and a miss is a silent runtime gap found only by playing that game. These tests are
the forcing function that was missing.
"""
import socket_manager as sm
from game_catalog import GAME_CATALOG
from generic_prompt_engine import GENERIC_PROMPT_GAME_TYPES


def test_catalog_game_types_covers_every_launchable_game():
    """The reset path validates against this, so a launchable game missing from it can't be
    reset to — the room would silently keep its old game type."""
    derived = sm._catalog_game_types()
    for entry in GAME_CATALOG:
        if entry.get("launchable"):
            assert entry["game_type"] in derived, f"{entry['id']} launchable but not resettable"


def test_catalog_game_types_includes_the_generic_prompt_family():
    derived = sm._catalog_game_types()
    for game_type in GENERIC_PROMPT_GAME_TYPES:
        assert game_type in derived


def test_non_launchable_games_are_not_resettable_to():
    """Any catalog entry marked launchable=False (e.g. a future game mid-build) must not be
    resettable into — that would start a room that can never begin a round. Impostor used this
    guard while it was being wired; the property stays even though the catalog is currently
    all-launchable."""
    derived = sm._catalog_game_types()
    for entry in GAME_CATALOG:
        if not entry.get("launchable") and entry["game_type"] not in GENERIC_PROMPT_GAME_TYPES:
            assert entry["game_type"] not in derived, (
                f"{entry['id']} is not launchable but is resettable"
            )


def test_quiz_style_advance_is_a_small_explicit_opt_in():
    """Expressed as the small POSITIVE set on purpose: every other game — including every future
    one — falls through by default, which is the correct behaviour without an edit."""
    assert sm.QUIZ_STYLE_ADVANCE_TYPES == frozenset({"quiz", "wmlt", "drawing", "bluff"})
    # Sanity: the set must stay far smaller than the catalog, or the inversion has lost its point.
    assert len(sm.QUIZ_STYLE_ADVANCE_TYPES) < len(sm._catalog_game_types()) / 2


def test_shared_answer_types_is_a_small_explicit_opt_in():
    assert sm.SHARED_ANSWER_TYPES == frozenset({"quiz", "bluff"})
    assert sm.SHARED_ANSWER_TYPES <= sm.QUIZ_STYLE_ADVANCE_TYPES


def test_every_other_game_ignores_the_shared_quiz_messages():
    """The property that makes new games correct by construction: anything not explicitly opted in
    must be excluded from both shared-message paths."""
    for game_type in sm._catalog_game_types():
        if game_type not in sm.QUIZ_STYLE_ADVANCE_TYPES:
            assert game_type not in sm.SHARED_ANSWER_TYPES


def test_a_hypothetical_new_game_defaults_to_its_own_messages():
    """Simulates adding game #38 without touching socket_manager."""
    invented = "totally_new_game_38"
    assert invented not in sm.QUIZ_STYLE_ADVANCE_TYPES
    assert invented not in sm.SHARED_ANSWER_TYPES


def test_the_sets_match_what_the_hardcoded_lists_used_to_say():
    """Regression pin for the refactor itself. These were the exact memberships before the three
    hand-listed tuples were replaced (measured at commit d3da3fcb); if the inversion ever drifts,
    a game silently changes which shared messages it responds to."""
    all_types = sm._catalog_game_types()
    # Previously: NEXT_QUESTION returned early for everything EXCEPT these four.
    assert sorted(all_types - sm.QUIZ_STYLE_ADVANCE_TYPES) == sorted(
        t for t in all_types if t not in {"quiz", "wmlt", "drawing", "bluff"}
    )
    # Previously: ANSWER returned early for everything EXCEPT quiz and bluff.
    assert sorted(all_types - sm.SHARED_ANSWER_TYPES) == sorted(
        t for t in all_types if t not in {"quiz", "bluff"}
    )
