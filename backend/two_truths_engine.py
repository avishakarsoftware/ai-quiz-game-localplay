import random
import re
import time
from typing import Any


PHASE_SUBMISSION = "TT_SUBMISSION"
PHASE_VOTING = "TT_VOTING"
PHASE_RESULT = "TT_RESULT"
PHASE_PODIUM = "PODIUM"

POINTS_CORRECT_GUESS = 500
POINTS_FOOLED_VOTER = 250
POINTS_FOOLED_EVERYONE_BONUS = 500
MIN_STATEMENT_CHARS = 3


def _clean_text(value: Any, max_chars: int = 180) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}

    def clamp_int(key: str, default: int, low: int, high: int) -> int:
        try:
            value = int(raw.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(low, min(high, value))

    reveal_mode = str(raw.get("reveal_mode") or "host_paced").strip().lower()
    if reveal_mode not in ("host_paced", "auto_paced"):
        reveal_mode = "host_paced"

    return {
        "game_title": _clean_text(raw.get("game_title") or "Two Truths and a Lie", 120) or "Two Truths and a Lie",
        "submission_time_seconds": clamp_int("submission_time_seconds", 180, 60, 600),
        "vote_time_seconds": clamp_int("vote_time_seconds", 30, 10, 90),
        "reveal_mode": reveal_mode,
        "shuffle_statement_order": bool(raw.get("shuffle_statement_order", True)),
        "allow_ai_inspiration": bool(raw.get("allow_ai_inspiration", True)),
    }


def validate_submission(raw_statements: list[dict[str, Any]], max_chars: int = 180) -> list[dict[str, Any]]:
    if not isinstance(raw_statements, list) or len(raw_statements) != 3:
        raise ValueError("Submit exactly three statements")

    statements: list[dict[str, Any]] = []
    seen: set[str] = set()
    lie_count = 0
    for index, item in enumerate(raw_statements):
        text = _clean_text(item.get("text") if isinstance(item, dict) else "", max_chars)
        if len(text) < MIN_STATEMENT_CHARS:
            raise ValueError(f"Each statement needs at least {MIN_STATEMENT_CHARS} characters")
        normalized = _norm(text)
        if normalized in seen:
            raise ValueError("Statements must be unique")
        seen.add(normalized)
        is_lie = bool(item.get("is_lie")) if isinstance(item, dict) else False
        if is_lie:
            lie_count += 1
        statements.append({
            "id": f"stmt_{index + 1}",
            "text": text,
            "is_lie": is_lie,
            "display_order": index,
        })

    if lie_count != 1:
        raise ValueError("Mark exactly one statement as the lie")
    return statements


def create_initial_state(player_ids: list[str], config: dict, seed: int | None = None) -> dict:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    rng = random.Random(seed)
    reveal_order = list(players)
    rng.shuffle(reveal_order)
    return {
        "phase": PHASE_SUBMISSION,
        "config": validate_config(config),
        "players": players,
        "submissions_by_player": {},
        "reveal_order": reveal_order,
        "current_index": -1,
        "current_author_id": "",
        "votes_by_round": {},
        "scores": {player_id: 0 for player_id in players},
        "score_breakdown": {player_id: {"correct_guesses": 0, "fooled_points": 0} for player_id in players},
        "round_result": None,
    }


def submit_statements(state: dict, player_id: str, raw_statements: list[dict[str, Any]], now: float | None = None) -> dict:
    if state.get("phase") != PHASE_SUBMISSION:
        raise ValueError("Submissions are closed")
    if player_id not in state.get("players", []):
        raise ValueError("Player is not in this game")
    statements = validate_submission(raw_statements)
    next_state = {**state, "submissions_by_player": dict(state.get("submissions_by_player", {}))}
    existing_order = next_state["submissions_by_player"].get(player_id, {}).get("display_order")
    if state.get("config", {}).get("shuffle_statement_order", True):
        order = list(range(3)) if existing_order is None else list(existing_order)
        if existing_order is None:
            random.Random(f"{player_id}:{now or time.time()}").shuffle(order)
    else:
        order = list(range(3))
    for display_order, original_index in enumerate(order):
        statements[original_index]["display_order"] = display_order
    next_state["submissions_by_player"][player_id] = {
        "player_id": player_id,
        "statements": statements,
        "display_order": order,
        "submitted_at": now or time.time(),
        "updated_at": now or time.time(),
    }
    return next_state


def start_reveal(state: dict) -> dict:
    submissions = state.get("submissions_by_player", {})
    order = [player_id for player_id in state.get("reveal_order", []) if player_id in submissions]
    if not order:
        raise ValueError("No players have submitted yet")
    next_state = {**state, "reveal_order": order, "current_index": 0, "current_author_id": order[0], "phase": PHASE_VOTING, "round_result": None}
    return next_state


def next_author(state: dict) -> dict:
    index = int(state.get("current_index", -1)) + 1
    order = state.get("reveal_order", [])
    if index >= len(order):
        return {**state, "phase": PHASE_PODIUM, "current_author_id": "", "round_result": None}
    return {**state, "phase": PHASE_VOTING, "current_index": index, "current_author_id": order[index], "round_result": None}


def current_submission(state: dict) -> dict | None:
    author = state.get("current_author_id")
    if not author:
        return None
    return state.get("submissions_by_player", {}).get(author)


def reveal_payload(submission: dict | None, include_answer: bool = False) -> list[dict[str, Any]]:
    if not submission:
        return []
    statements = sorted(submission.get("statements", []), key=lambda item: int(item.get("display_order", 0)))
    payload = []
    for item in statements:
        row = {"id": item["id"], "text": item["text"], "display_order": item.get("display_order", 0)}
        if include_answer:
            row["is_lie"] = bool(item.get("is_lie"))
        payload.append(row)
    return payload


def submit_vote(state: dict, voter_id: str, statement_id: str) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("Voting is not open")
    author_id = state.get("current_author_id")
    if not author_id or voter_id == author_id:
        raise ValueError("Author cannot vote")
    if voter_id not in state.get("players", []):
        raise ValueError("Player is not in this game")
    submission = current_submission(state)
    valid_statement_ids = {item["id"] for item in (submission or {}).get("statements", [])}
    if statement_id not in valid_statement_ids:
        raise ValueError("Invalid statement")
    votes_by_round = {k: dict(v) for k, v in state.get("votes_by_round", {}).items()}
    votes_by_round.setdefault(author_id, {})[voter_id] = statement_id
    return {**state, "votes_by_round": votes_by_round}


def score_current_round(state: dict) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("Voting is not open")
    author_id = state.get("current_author_id")
    submission = current_submission(state)
    if not author_id or not submission:
        raise ValueError("No current author")

    lie_statement = next((item for item in submission.get("statements", []) if item.get("is_lie")), None)
    lie_id = lie_statement["id"] if lie_statement else ""
    votes = dict(state.get("votes_by_round", {}).get(author_id, {}))
    eligible_voters = [player_id for player_id in state.get("players", []) if player_id != author_id]
    correct_voters = sorted(voter for voter, statement_id in votes.items() if statement_id == lie_id)
    fooled_voters = sorted(voter for voter, statement_id in votes.items() if statement_id and statement_id != lie_id)

    scores = dict(state.get("scores", {}))
    breakdown = {player_id: dict(data) for player_id, data in state.get("score_breakdown", {}).items()}
    for voter in correct_voters:
        scores[voter] = scores.get(voter, 0) + POINTS_CORRECT_GUESS
        breakdown.setdefault(voter, {"correct_guesses": 0, "fooled_points": 0})["correct_guesses"] += 1
    fooled_points = len(fooled_voters) * POINTS_FOOLED_VOTER
    if eligible_voters and len(fooled_voters) == len(eligible_voters):
        fooled_points += POINTS_FOOLED_EVERYONE_BONUS
    scores[author_id] = scores.get(author_id, 0) + fooled_points
    breakdown.setdefault(author_id, {"correct_guesses": 0, "fooled_points": 0})["fooled_points"] += fooled_points

    tally: dict[str, int] = {item["id"]: 0 for item in submission.get("statements", [])}
    for statement_id in votes.values():
        if statement_id in tally:
            tally[statement_id] += 1

    result = {
        "author_id": author_id,
        "lie_statement_id": lie_id,
        "votes": votes,
        "vote_tally": tally,
        "correct_voters": correct_voters,
        "fooled_voters": fooled_voters,
        "author_points": fooled_points,
    }
    return {**state, "phase": PHASE_RESULT, "scores": scores, "score_breakdown": breakdown, "round_result": result}


def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    submission = current_submission(state)
    include_answer = state.get("phase") in (PHASE_RESULT, PHASE_PODIUM)
    submissions = state.get("submissions_by_player", {})
    return {
        "phase": state.get("phase", PHASE_SUBMISSION),
        "config": state.get("config", {}),
        "players": players or [{"nickname": player_id, "avatar": ""} for player_id in state.get("players", [])],
        "submitted_players": sorted(submissions.keys()),
        "submitted_count": len(submissions),
        "total_players": len(state.get("players", [])),
        "current_author_id": state.get("current_author_id", ""),
        "current_round": max(0, int(state.get("current_index", -1)) + 1),
        "total_rounds": len(state.get("reveal_order", [])) or len(submissions),
        "statements": reveal_payload(submission, include_answer=include_answer),
        "votes_count": len(state.get("votes_by_round", {}).get(state.get("current_author_id", ""), {})),
        "scores": dict(state.get("scores", {})),
        "round_result": state.get("round_result"),
    }


def private_sync(state: dict, player_id: str, players: list[dict[str, str]] | None = None) -> dict:
    sync = public_sync(state, players)
    sync["my_submission"] = state.get("submissions_by_player", {}).get(player_id)
    sync["my_vote"] = state.get("votes_by_round", {}).get(state.get("current_author_id", ""), {}).get(player_id, "")
    sync["is_author"] = player_id == state.get("current_author_id")
    return sync


def final_standings(state: dict) -> list[dict[str, Any]]:
    breakdown = state.get("score_breakdown", {})
    return [
        {
            "nickname": player_id,
            "score": score,
            "correct_guesses": breakdown.get(player_id, {}).get("correct_guesses", 0),
            "fooled_points": breakdown.get(player_id, {}).get("fooled_points", 0),
        }
        for player_id, score in sorted(state.get("scores", {}).items(), key=lambda item: (-item[1], item[0].lower()))
    ]
