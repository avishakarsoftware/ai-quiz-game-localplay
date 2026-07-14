"""Pure Survey Says mechanics.

Survey Says is a host-adjudicated, Family-Feud-style party game. Players submit
free-text guesses from their phones, while the host reveals answer slots or
records strikes on the shared screen.
"""
from __future__ import annotations

import copy
import re
import time
import unicodedata
from typing import Any

from engine_common import clamp_int as _clamp_int, make_clean_text
_clean_text = make_clean_text(max_chars=180)

PHASE_ANSWERING = "SURVEY_ANSWERING"
PHASE_STEAL = "SURVEY_STEAL"
PHASE_REVEAL = "SURVEY_REVEAL"
PHASE_PODIUM = "PODIUM"

DEFAULT_ROUNDS = [
    {
        "id": "round_1",
        "question": "Name something people do right after arriving at a party.",
        "answers": [
            {"id": "a1", "text": "Say hello", "points": 36, "aliases": ["greet", "meet people"]},
            {"id": "a2", "text": "Look for food", "points": 25, "aliases": ["eat", "snacks"]},
            {"id": "a3", "text": "Find friends", "points": 18, "aliases": ["friends"]},
            {"id": "a4", "text": "Take photos", "points": 12, "aliases": ["pictures"]},
            {"id": "a5", "text": "Get a drink", "points": 9, "aliases": ["drink"]},
        ],
    },
    {
        "id": "round_2",
        "question": "Name something kids want at a birthday party.",
        "answers": [
            {"id": "a1", "text": "Cake", "points": 38, "aliases": ["birthday cake"]},
            {"id": "a2", "text": "Games", "points": 24, "aliases": ["party games"]},
            {"id": "a3", "text": "Presents", "points": 19, "aliases": ["gifts"]},
            {"id": "a4", "text": "Balloons", "points": 11, "aliases": []},
            {"id": "a5", "text": "Music", "points": 8, "aliases": ["songs"]},
        ],
    },
    {
        "id": "round_3",
        "question": "Name something people forget before leaving home.",
        "answers": [
            {"id": "a1", "text": "Keys", "points": 34, "aliases": []},
            {"id": "a2", "text": "Phone", "points": 28, "aliases": ["mobile"]},
            {"id": "a3", "text": "Wallet", "points": 17, "aliases": ["purse"]},
            {"id": "a4", "text": "Gift", "points": 12, "aliases": ["present"]},
            {"id": "a5", "text": "Charger", "points": 9, "aliases": []},
        ],
    },
]


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"^(a|an|the)\s+", "", text)


def _sanitize_answer(raw: dict, index: int) -> dict | None:
    text = _clean_text(raw.get("text") or raw.get("answer"), 80)
    if len(text) < 2:
        return None
    try:
        points = int(raw.get("points", max(5, 40 - (index * 6))))
    except (TypeError, ValueError):
        points = max(5, 40 - (index * 6))
    aliases = []
    seen = {_normalize(text)}
    for alias in raw.get("aliases") or []:
        clean = _clean_text(alias, 80)
        key = _normalize(clean)
        if clean and key and key not in seen:
            seen.add(key)
            aliases.append(clean)
    return {
        "id": _clean_text(raw.get("id") or f"a{index}", 40) or f"a{index}",
        "text": text,
        "points": max(1, min(100, points)),
        "aliases": aliases[:8],
    }


def _sanitize_round(raw: dict, index: int) -> dict | None:
    question = _clean_text(raw.get("question") or raw.get("prompt"), 160)
    if len(question) < 6:
        return None
    answers = []
    seen = set()
    source = raw.get("answers") if isinstance(raw.get("answers"), list) else []
    for answer_index, item in enumerate(source, start=1):
        if not isinstance(item, dict):
            continue
        answer = _sanitize_answer(item, answer_index)
        if not answer:
            continue
        key = _normalize(answer["text"])
        if key in seen:
            continue
        seen.add(key)
        answers.append(answer)
        if len(answers) >= 8:
            break
    if len(answers) < 3:
        return None
    return {
        "id": _clean_text(raw.get("id") or f"round_{index}", 40) or f"round_{index}",
        "question": question,
        "answers": answers,
    }


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    source = raw.get("rounds") if isinstance(raw.get("rounds"), list) else DEFAULT_ROUNDS
    rounds = []
    for index, item in enumerate(source, start=1):
        if not isinstance(item, dict):
            continue
        round_item = _sanitize_round(item, index)
        if round_item:
            rounds.append(round_item)
        if len(rounds) >= 20:
            break
    if len(rounds) < 1:
        rounds = [_sanitize_round(item, index) for index, item in enumerate(DEFAULT_ROUNDS, start=1)]
        rounds = [item for item in rounds if item]
    round_count = _clamp_int(raw, "round_count", min(5, len(rounds)), 1, 20)
    return {
        "game_title": _clean_text(raw.get("game_title") or "Survey Says", 120) or "Survey Says",
        "team_count": 2,
        "round_count": min(round_count, len(rounds)),
        "max_strikes": _clamp_int(raw, "max_strikes", 3, 1, 5),
        "guess_time_seconds": _clamp_int(raw, "guess_time_seconds", 45, 10, 180),
        "allow_late_join": bool(raw.get("allow_late_join", True)),
        "rounds": rounds[:round_count],
    }


def _team_name(index: int) -> str:
    return ["Team A", "Team B"][index] if index < 2 else f"Team {index + 1}"


def create_initial_state(player_ids: list[str], config: dict, now: float | None = None) -> dict:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    if len(players) < 2:
        raise ValueError("Survey Says needs at least 2 players")
    setup = validate_config(config)
    teams = [{"id": f"team_{index + 1}", "name": _team_name(index), "player_ids": []} for index in range(setup["team_count"])]
    for index, player_id in enumerate(players):
        teams[index % len(teams)]["player_ids"].append(player_id)
    started_at = now or time.time()
    return {
        "phase": PHASE_ANSWERING,
        "config": setup,
        "players": players,
        "teams": teams,
        "round_index": 0,
        "starting_team_index": 0,
        "active_team_id": teams[0]["id"],
        "stealing_team_id": None,
        "revealed_answer_ids": [],
        "strikes": 0,
        "round_bank": 0,
        "scores": {team["id"]: 0 for team in teams},
        "guesses": {},
        "round_results": [],
        "deadline": started_at + setup["guess_time_seconds"],
        "completed_at": None,
    }


def current_round(state: dict) -> dict:
    rounds = state.get("config", {}).get("rounds") or []
    index = int(state.get("round_index", 0))
    if index < 0 or index >= len(rounds):
        raise ValueError("No active Survey Says round")
    return rounds[index]


def add_player(state: dict, player_id: str) -> dict:
    clean = str(player_id or "")
    if not clean:
        return _copy_state(state)
    next_state = _copy_state(state)
    if clean in next_state.get("players", []):
        return next_state
    next_state.setdefault("players", []).append(clean)
    teams = next_state.get("teams") or []
    if teams:
        target = min(teams, key=lambda team: (len(team.get("player_ids", [])), team.get("id", "")))
        target.setdefault("player_ids", []).append(clean)
    return next_state


def player_team_id(state: dict, player_id: str) -> str | None:
    for team in state.get("teams", []):
        if player_id in team.get("player_ids", []):
            return team.get("id")
    return None


def submit_guess(state: dict, player_id: str, guess: str, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_ANSWERING, PHASE_STEAL}:
        raise ValueError("This round is not accepting guesses")
    if player_id not in state.get("players", []):
        raise ValueError("Unknown player")
    clean = _clean_text(guess, 100)
    if len(clean) < 2:
        raise ValueError("Guess is required")
    team_id = player_team_id(state, player_id)
    next_state = _copy_state(state)
    round_guesses = dict(next_state.get("guesses") or {})
    round_guesses[player_id] = {
        "player_id": player_id,
        "team_id": team_id,
        "guess": clean,
        "normalized": _normalize(clean),
        "at": now or time.time(),
    }
    next_state["guesses"] = round_guesses
    return next_state


def _answer_by_id(state: dict, answer_id: str) -> dict:
    for answer in current_round(state).get("answers", []):
        if answer.get("id") == answer_id:
            return answer
    raise ValueError("Unknown answer")


def _next_unrevealed_ids(state: dict) -> set[str]:
    revealed = set(state.get("revealed_answer_ids") or [])
    return {answer.get("id") for answer in current_round(state).get("answers", []) if answer.get("id") not in revealed}


def reveal_answer(state: dict, answer_id: str, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_ANSWERING, PHASE_STEAL}:
        raise ValueError("No active answer board")
    answer = _answer_by_id(state, answer_id)
    if answer_id in set(state.get("revealed_answer_ids") or []):
        raise ValueError("Answer is already revealed")
    next_state = _copy_state(state)
    next_state.setdefault("revealed_answer_ids", []).append(answer_id)
    next_state["round_bank"] = int(next_state.get("round_bank", 0)) + int(answer.get("points", 0))
    if state.get("phase") == PHASE_STEAL:
        return _finish_round(next_state, winner_team_id=str(state.get("stealing_team_id") or ""), outcome="steal_success", now=now)
    if not _next_unrevealed_ids(next_state):
        return _finish_round(next_state, winner_team_id=str(state.get("active_team_id") or ""), outcome="swept_board", now=now)
    return next_state


def add_strike(state: dict, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_ANSWERING, PHASE_STEAL}:
        raise ValueError("No active team to strike")
    next_state = _copy_state(state)
    if state.get("phase") == PHASE_STEAL:
        return _finish_round(next_state, winner_team_id=str(state.get("active_team_id") or ""), outcome="steal_failed", now=now)
    next_state["strikes"] = int(next_state.get("strikes", 0)) + 1
    if next_state["strikes"] >= int(next_state.get("config", {}).get("max_strikes", 3)) and _next_unrevealed_ids(next_state):
        teams = next_state.get("teams") or []
        active = next_state.get("active_team_id")
        stealing = next((team.get("id") for team in teams if team.get("id") != active), None)
        next_state["phase"] = PHASE_STEAL
        next_state["stealing_team_id"] = stealing
        next_state["deadline"] = (now or time.time()) + int(next_state["config"]["guess_time_seconds"])
    return next_state


def reveal_all(state: dict, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_ANSWERING, PHASE_STEAL, PHASE_REVEAL}:
        raise ValueError("No active round to reveal")
    next_state = _copy_state(state)
    next_state["revealed_answer_ids"] = [answer["id"] for answer in current_round(next_state).get("answers", [])]
    if next_state.get("phase") != PHASE_REVEAL:
        next_state = _finish_round(next_state, winner_team_id=str(next_state.get("active_team_id") or ""), outcome="host_reveal", now=now, award_bank=False)
        next_state["revealed_answer_ids"] = [answer["id"] for answer in current_round(next_state).get("answers", [])]
    return next_state


def _finish_round(state: dict, winner_team_id: str, outcome: str, now: float | None = None, award_bank: bool = True) -> dict:
    next_state = _copy_state(state)
    scores = dict(next_state.get("scores") or {})
    bank = int(next_state.get("round_bank", 0))
    if award_bank and winner_team_id:
        scores[winner_team_id] = int(scores.get(winner_team_id, 0)) + bank
    next_state["scores"] = scores
    next_state["phase"] = PHASE_REVEAL
    next_state["deadline"] = None
    next_state["round_results"].append({
        "round_number": int(next_state.get("round_index", 0)) + 1,
        "winner_team_id": winner_team_id,
        "outcome": outcome,
        "bank": bank if award_bank else 0,
        "revealed_answer_ids": list(next_state.get("revealed_answer_ids") or []),
        "scores": scores,
        "completed_at": now or time.time(),
    })
    return next_state


def next_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_REVEAL:
        raise ValueError("Finish the current round first")
    next_state = _copy_state(state)
    next_index = int(next_state.get("round_index", 0)) + 1
    if next_index >= len(next_state.get("config", {}).get("rounds") or []):
        next_state["phase"] = PHASE_PODIUM
        next_state["completed_at"] = now or time.time()
        next_state["deadline"] = None
        return next_state
    teams = next_state.get("teams") or []
    starting = (int(next_state.get("starting_team_index", 0)) + 1) % max(1, len(teams))
    next_state.update({
        "phase": PHASE_ANSWERING,
        "round_index": next_index,
        "starting_team_index": starting,
        "active_team_id": teams[starting]["id"] if teams else "",
        "stealing_team_id": None,
        "revealed_answer_ids": [],
        "strikes": 0,
        "round_bank": 0,
        "guesses": {},
        "deadline": (now or time.time()) + int(next_state["config"]["guess_time_seconds"]),
    })
    return next_state


def force_complete(state: dict, now: float | None = None) -> dict:
    next_state = _copy_state(state)
    next_state["phase"] = PHASE_PODIUM
    next_state["deadline"] = None
    next_state["completed_at"] = now or time.time()
    return next_state


def standings(state: dict) -> list[dict]:
    scores = state.get("scores") or {}
    rows = []
    for team in state.get("teams", []):
        rows.append({
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "score": int(scores.get(team.get("id"), 0)),
            "members": list(team.get("player_ids") or []),
        })
    rows.sort(key=lambda row: (-row["score"], row["team_name"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def public_sync(state: dict, players: list[dict] | None = None, host: bool = False, viewer_id: str | None = None) -> dict:
    round_item = current_round(state) if state.get("phase") != PHASE_PODIUM else {}
    revealed = set(state.get("revealed_answer_ids") or [])
    answer_board = []
    for index, answer in enumerate(round_item.get("answers", []), start=1):
        is_revealed = answer.get("id") in revealed or state.get("phase") in {PHASE_REVEAL, PHASE_PODIUM} or host
        answer_board.append({
            "id": answer.get("id"),
            "rank": index,
            "revealed": bool(answer.get("id") in revealed) or state.get("phase") in {PHASE_REVEAL, PHASE_PODIUM},
            "text": answer.get("text") if is_revealed else "",
            "points": int(answer.get("points", 0)),
            "aliases": answer.get("aliases", []) if host else [],
        })
    guesses = list((state.get("guesses") or {}).values())
    if not host:
        guesses = [item for item in guesses if item.get("player_id") == viewer_id]
    return {
        "phase": state.get("phase"),
        "config": {
            "game_title": state.get("config", {}).get("game_title", "Survey Says"),
            "max_strikes": state.get("config", {}).get("max_strikes", 3),
            "guess_time_seconds": state.get("config", {}).get("guess_time_seconds", 45),
        },
        "players": players or [{"nickname": name, "avatar": ""} for name in state.get("players", [])],
        "teams": state.get("teams", []),
        "round_number": int(state.get("round_index", 0)) + 1,
        "total_rounds": len(state.get("config", {}).get("rounds") or []),
        "question": round_item.get("question", ""),
        "answers": answer_board,
        "active_team_id": state.get("active_team_id"),
        "stealing_team_id": state.get("stealing_team_id"),
        "strikes": int(state.get("strikes", 0)),
        "round_bank": int(state.get("round_bank", 0)),
        "scores": state.get("scores", {}),
        "standings": standings(state),
        "guesses": guesses,
        "round_results": state.get("round_results", []),
        "deadline": state.get("deadline"),
        "my_team_id": player_team_id(state, viewer_id) if viewer_id else None,
    }


def _copy_state(state: dict) -> dict:
    return copy.deepcopy(state)
