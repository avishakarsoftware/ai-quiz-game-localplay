"""Guard: e2e coverage of the game catalog cannot silently regress (SPEC-TESTING §5).

## Why this is pytest and not vitest

The catalog is **backend-authoritative** — `backend/game_catalog.py` is the source of truth, and
`frontend/src/gameModes.ts` is a mirror of it. A vitest guard could only read the mirror, so the
exact drift that shipped the occasion bingos broken (a game lands in the backend catalog, the
frontend lists don't know) would be invisible to it: the mirror and the guard would be wrong
together and agree with each other.

pytest imports `GAME_CATALOG` in-process, so the guard reads the same object the API serves. It also
runs in the same commit that adds a game — a new game is a `game_catalog.py` edit, and `pytest
backend/tests` is what you run after making one. The guard therefore fails at the moment the gap is
created rather than the next time somebody remembers to run Playwright.

## What "covered" means here

`frontend/e2e/all-games.spec.ts` enumerates `GET /catalog` at load time, so every game is *attempted*
automatically. That makes "no test was written" impossible, but it does not make coverage automatic:
a game can be structurally outside what the suite is able to drive (needs more players than the
suite will spin up, uses an interaction model the suite has never seen, has no picker tile to click,
cannot have a room created for its `game_type`). Those games would fail — or worse, be quietly
skipped — with nothing explaining why.

So this guard checks the *drivability preconditions*, per game, and requires anything that fails one
to carry an explicit waiver with a reason and a revisit condition. A waiver is a decision; an
omission is an accident.
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from game_catalog import GAME_CATALOG
from main import SUPPORTED_ROOM_GAME_TYPES

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
E2E_DIR = os.path.join(REPO_ROOT, 'frontend', 'e2e')
ALL_GAMES_SPEC = os.path.join(E2E_DIR, 'all-games.spec.ts')
COVERAGE_JSON = os.path.join(E2E_DIR, 'game-coverage.json')
GAME_MODES_TS = os.path.join(REPO_ROOT, 'frontend', 'src', 'gameModes.ts')
FRONTEND_PACKAGE_JSON = os.path.join(REPO_ROOT, 'frontend', 'package.json')

# Interaction models `all-games.spec.ts` knows how to drive. `None` is the default one-phone-per-
# player flow; "pass_and_play" is the host-typed seat roster (SPEC-PASS-AND-PLAY). A THIRD value
# appearing here without the suite being taught it is precisely how a game escapes coverage while
# looking covered, so this set is deliberately closed.
DRIVABLE_INTERACTIONS = {None, '', 'pass_and_play'}


@pytest.fixture(scope='module')
def coverage():
    with open(COVERAGE_JSON, encoding='utf-8') as handle:
        return json.load(handle)


@pytest.fixture(scope='module')
def spec_source():
    with open(ALL_GAMES_SPEC, encoding='utf-8') as handle:
        return handle.read()


@pytest.fixture(scope='module')
def frontend_game_ids():
    """Ids declared in `gameModes.ts`, which is what the picker renders tiles from.

    Regex rather than a parser: the alternative is running node from pytest, and the shape here
    (`id: 'quiz',`) is stable across the file's whole history.
    """
    with open(GAME_MODES_TS, encoding='utf-8') as handle:
        source = handle.read()
    return set(re.findall(r"\bid:\s*'([a-z0-9_]+)'", source))


def catalog_ids():
    return [game['id'] for game in GAME_CATALOG]


def min_players(game):
    return int(((game.get('config_schema') or {}).get('players') or {}).get('min') or 0)


# ---------------------------------------------------------------------------------------------
# The suite must stay catalog-driven
# ---------------------------------------------------------------------------------------------

def _strip_comments(source: str) -> str:
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.S)
    return re.sub(r'//[^\n]*', '', source)


def test_all_games_spec_exists_and_is_wired_to_an_npm_script():
    assert os.path.exists(ALL_GAMES_SPEC), (
        'frontend/e2e/all-games.spec.ts is missing — the canonical "every game is playable" suite'
    )
    with open(FRONTEND_PACKAGE_JSON, encoding='utf-8') as handle:
        scripts = json.load(handle)['scripts']
    wired = [name for name, command in scripts.items() if 'all-games.spec.ts' in command]
    assert wired, 'no npm script runs all-games.spec.ts — an unrunnable suite is not coverage'
    # One local (L3) and one gamma (L4) entry point, per SPEC-TESTING §1.
    assert any('gamma' in name for name in wired), 'no gamma (L4) entry point for all-games.spec.ts'


def test_all_games_spec_is_parameterised_over_the_catalog(spec_source):
    assert "'/catalog'" in spec_source or '"/catalog"' in spec_source, (
        'all-games.spec.ts must derive its game list from GET /catalog'
    )


def test_all_games_spec_names_no_game(spec_source):
    """The suite must not contain a hardcoded game list — that is the whole point of it.

    Any game named as a string literal in the spec body is a game whose coverage stopped being
    automatic. Per-game setup belongs in `game-coverage.json`, which is an exception list the guard
    below keeps honest.
    """
    body = _strip_comments(spec_source)
    named = sorted(
        game_id for game_id in catalog_ids()
        if re.search(rf"""['"]{re.escape(game_id)}['"]""", body)
    )
    assert not named, (
        f'all-games.spec.ts hardcodes catalog game ids {named}. Move per-game setup into '
        'game-coverage.json so a new game stays covered without editing the spec.'
    )


# ---------------------------------------------------------------------------------------------
# The waiver list must stay honest
# ---------------------------------------------------------------------------------------------

def test_no_stale_waivers(coverage):
    unknown = sorted(set(coverage['waivers']) - set(catalog_ids()))
    assert not unknown, (
        f'game-coverage.json waives games that are not in the catalog: {unknown}. '
        'A waiver for a deleted game hides the next game that needs one.'
    )


def test_no_stale_plans(coverage):
    unknown = sorted(set(coverage['plans']) - set(catalog_ids()))
    assert not unknown, f'game-coverage.json has plans for non-catalog games: {unknown}'


@pytest.mark.parametrize('game_id', sorted(json.load(open(COVERAGE_JSON, encoding='utf-8'))['waivers']))
def test_waiver_is_justified(coverage, game_id):
    waiver = coverage['waivers'][game_id]
    reason = waiver.get('reason', '')
    assert len(reason) >= 30, f'waiver for {game_id} needs a real reason, got {reason!r}'
    assert waiver.get('revisit_when'), (
        f'waiver for {game_id} has no revisit_when — a waiver with no exit condition is permanent '
        'by accident'
    )


# ---------------------------------------------------------------------------------------------
# Every catalog game must be drivable by the suite, or explicitly waived
# ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize('game', GAME_CATALOG, ids=catalog_ids())
def test_catalog_game_is_covered_by_the_e2e_suite(game, coverage, frontend_game_ids):
    game_id = game['id']
    waived = game_id in coverage['waivers']
    max_players = coverage['defaults']['max_players']
    problems = []

    # 1. A room can be created for it. Occasion bingos are variants whose game_type is the runtime
    #    ('bingo'), so this checks game_type — creating with the id is correctly rejected.
    if game.get('launchable', True) and game['game_type'] not in SUPPORTED_ROOM_GAME_TYPES:
        problems.append(
            f"game_type {game['game_type']!r} is not in SUPPORTED_ROOM_GAME_TYPES, so no room can "
            'be created for it'
        )

    # 2. Rules metadata resolves — the suite asserts the rendered modal against these values.
    rules = game.get('rules') or {}
    if not rules.get('title') or not rules.get('summary') or not rules.get('sections'):
        problems.append('rules metadata is missing title/summary/sections')
    if not ((rules.get('player_count') or {}).get('min')):
        problems.append('rules metadata has no minimum player count')

    # 3. The picker can show it. Without a gameModes entry there is no tile, so the catalog leg
    #    cannot pass — this is the occasion-bingo failure, caught statically.
    if game_id not in frontend_game_ids:
        problems.append(
            f'no GameModeConfig with id {game_id!r} in frontend/src/gameModes.ts, so the picker '
            'renders no tile for it'
        )

    # 4. The suite can field enough players.
    if min_players(game) > max_players:
        problems.append(
            f'needs {min_players(game)} players; the suite spins up at most {max_players} '
            "(raise game-coverage.json defaults.max_players, or waive it)"
        )

    # 5. The suite knows this interaction model.
    if game.get('interaction') not in DRIVABLE_INTERACTIONS:
        problems.append(
            f"interaction {game.get('interaction')!r} is not one all-games.spec.ts can drive "
            "(known: unset/default, 'pass_and_play') — teach the suite the new interaction model"
        )

    if waived:
        # A waived game must still be waived for a REASON that exists. If everything now passes, the
        # waiver is obsolete and should be deleted rather than left to rot.
        return

    assert not problems, (
        f'catalog game {game_id!r} has no usable e2e coverage:\n  - '
        + '\n  - '.join(problems)
        + '\n\nEither make it drivable by frontend/e2e/all-games.spec.ts, or add an explicit waiver '
        'with a reason and revisit_when to frontend/e2e/game-coverage.json.'
    )


def test_the_six_games_that_shipped_with_no_coverage_are_covered(coverage, frontend_game_ids):
    """Regression pin for the measured gap of 2026-07-28.

    SPEC-TESTING §0 recorded 32 of 38 catalog games referenced in some e2e spec. These six were the
    exceptions, and every one of them is a case the generic path gets wrong if nobody thinks about
    it: four are catalog variants sharing one runtime, one is pass-and-play with zero sockets, one
    needs three players. Naming them here is not a hardcoded game list — it is a pin on the specific
    historical gap this suite was built to close.
    """
    previously_uncovered = [
        'baby_bingo', 'wedding_bingo', 'holiday_bingo', 'road_trip_bingo', 'odd_question', 'impostor',
    ]
    catalog = {game['id']: game for game in GAME_CATALOG}
    for game_id in previously_uncovered:
        assert game_id in catalog, f'{game_id} vanished from the catalog'
        assert game_id not in coverage['waivers'], (
            f'{game_id} was one of the six uncovered games; waiving it re-opens the gap'
        )
        assert game_id in frontend_game_ids, f'{game_id} has no picker tile'
        assert catalog[game_id]['game_type'] in SUPPORTED_ROOM_GAME_TYPES
