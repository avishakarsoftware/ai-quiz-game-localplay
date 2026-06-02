import random
import re
import time
from typing import Any


PHASE_DISCUSSION = "COMMON_DISCUSSION"
PHASE_REVEAL = "COMMON_REVEAL"
PHASE_VOTING = "COMMON_VOTING"
PHASE_ROUND_RESULT = "COMMON_ROUND_RESULT"
PHASE_PODIUM = "PODIUM"

POINTS_SUBMISSION = 100
POINTS_FIRST_SUBMISSION = 50
POINTS_PER_VOTE = 100
POINTS_FULL_TEAM_VOTE = 25

DEFAULT_PROMPTS = [
    {"id": "prompt_1", "text": "Find one food everyone on your team likes.", "category": "food"},
    {"id": "prompt_2", "text": "Find one movie, show, or song everyone recognizes.", "category": "music"},
    {"id": "prompt_3", "text": "Find one place everyone on your team has visited.", "category": "travel"},
    {"id": "prompt_4", "text": "Find one hobby or activity everyone has tried.", "category": "hobbies"},
    {"id": "prompt_5", "text": "Find one thing everyone wanted to be as a kid.", "category": "childhood"},
]


def _clean_text(value: Any, max_chars: int = 220) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    mode = str(raw.get("mode") or "one_best_fact").strip().lower()
    if mode not in {"classic", "prompted", "one_best_fact"}:
        mode = "one_best_fact"
    vote_category = str(raw.get("vote_category") or "most_surprising").strip().lower()
    if vote_category not in {"funniest", "most_surprising", "most_specific"}:
        vote_category = "most_surprising"
    theme = str(raw.get("theme") or "work_safe").strip().lower()[:60] or "work_safe"

    prompts = []
    for index, prompt in enumerate(raw.get("prompts") or DEFAULT_PROMPTS, start=1):
        if isinstance(prompt, str):
            text = _clean_text(prompt, 180)
            category = "open"
        else:
            text = _clean_text((prompt or {}).get("text"), 180)
            category = _clean_text((prompt or {}).get("category") or "open", 40) or "open"
        if text:
            prompts.append({"id": f"prompt_{index}", "text": text, "category": category})
    if not prompts:
        prompts = list(DEFAULT_PROMPTS)

    rounds = _clamp_int(raw, "rounds", 5, 1, 10)
    while len(prompts) < rounds:
        prompts.extend(DEFAULT_PROMPTS[:rounds - len(prompts)])
    prompts = [{**prompt, "id": f"prompt_{index + 1}"} for index, prompt in enumerate(prompts[:rounds])]

    return {
        "game_title": _clean_text(raw.get("game_title") or "Common Ground", 120) or "Common Ground",
        "mode": mode,
        "team_size": _clamp_int(raw, "team_size", 3, 2, 6),
        "rounds": rounds,
        "discussion_time_seconds": _clamp_int(raw, "discussion_time_seconds", 90, 30, 300),
        "vote_time_seconds": _clamp_int(raw, "vote_time_seconds", 30, 10, 90),
        "facts_per_round": _clamp_int(raw, "facts_per_round", 1, 1, 1),
        "voting_enabled": bool(raw.get("voting_enabled", True)),
        "vote_category": vote_category,
        "theme": theme,
        "prompts": prompts,
    }


def assign_teams(player_ids: list[str], team_size: int, seed: str | int | None = None) -> list[dict]:
    players = [str(player_id) for player_id in player_ids if str(player_id)]
    random.Random(seed).shuffle(players)
    if not players:
        return []
    size = max(2, min(6, int(team_size or 3)))
    team_count = max(1, round(len(players) / size))
    team_count = min(team_count, len(players) // 2) if len(players) > 1 else 1
    team_count = max(1, team_count)
    teams = [{"id": f"team_{index + 1}", "name": f"Team {chr(65 + index)}", "player_ids": []} for index in range(team_count)]
    for index, player_id in enumerate(players):
        teams[index % team_count]["player_ids"].append(player_id)
    return teams


def create_initial_state(player_ids: list[str], config: dict, now: float | None = None, seed: str | int | None = None) -> dict:
    setup = validate_config(config)
    started_at = now or time.time()
    teams = assign_teams(player_ids, setup["team_size"], seed=seed)
    return {
        "phase": PHASE_DISCUSSION,
        "config": setup,
        "teams": teams,
        "round_index": 0,
        "round_started_at": started_at,
        "deadline": started_at + setup["discussion_time_seconds"],
        "submissions": {},
        "votes_by_player": {},
        "round_results": [],
        "scores": {team["id"]: 0 for team in teams},
        "completed_at": None,
    }


def add_player_to_team(state: dict, player_id: str) -> dict:
    player_id = str(player_id or "").strip()
    if not player_id:
        return state
    if _team_for_player(state, player_id):
        return state
    teams = [dict(team) for team in state.get("teams", [])]
    scores = dict(state.get("scores", {}))
    if not teams:
        teams = [{"id": "team_1", "name": "Team A", "player_ids": []}]
        scores.setdefault("team_1", 0)
    target = min(
        teams,
        key=lambda team: (
            len(team.get("player_ids", [])),
            int(scores.get(team.get("id"), 0)),
            str(team.get("id", "")),
        ),
    )
    target["player_ids"] = list(target.get("player_ids", [])) + [player_id]
    scores.setdefault(target["id"], 0)
    return {**state, "teams": teams, "scores": scores}


def _current_prompt(state: dict) -> dict:
    prompts = state.get("config", {}).get("prompts", DEFAULT_PROMPTS)
    index = min(int(state.get("round_index", 0)), len(prompts) - 1)
    return prompts[index] if prompts else DEFAULT_PROMPTS[0]


def _team_for_player(state: dict, player_id: str) -> dict | None:
    for team in state.get("teams", []):
        if player_id in team.get("player_ids", []):
            return team
    return None


def _submission_list(state: dict, include_text: bool) -> list[dict]:
    submissions = state.get("submissions", {})
    result = []
    for team in state.get("teams", []):
        submission = submissions.get(team["id"])
        if submission:
            item = {
                "id": submission["id"],
                "team_id": team["id"],
                "team_name": team["name"],
                "submitted_by": submission["submitted_by"],
                "created_at": submission["created_at"],
                "updated_at": submission.get("updated_at", submission["created_at"]),
                "has_submission": True,
                "vote_count": _vote_count(state, submission["id"]) if include_text else 0,
            }
            if include_text:
                item["text"] = submission["text"]
            result.append(item)
        else:
            result.append({
                "id": "",
                "team_id": team["id"],
                "team_name": team["name"],
                "submitted_by": "",
                "created_at": None,
                "updated_at": None,
                "has_submission": False,
                "vote_count": 0,
            })
    return result


def _vote_count(state: dict, submission_id: str) -> int:
    return len([vote for vote in state.get("votes_by_player", {}).values() if vote == submission_id])


def _all_teams_submitted(state: dict) -> bool:
    return bool(state.get("teams")) and all(team["id"] in state.get("submissions", {}) for team in state.get("teams", []))


def submit_fact(state: dict, player_id: str, text: Any, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_DISCUSSION:
        raise ValueError("Common Ground is not accepting answers")
    team = _team_for_player(state, player_id)
    if not team:
        raise ValueError("You are not on a team")
    clean = _clean_text(text, 220)
    if len(clean) < 6 or clean.count(" ") < 1:
        raise ValueError("Write a shared fact before submitting")
    submitted_at = now or time.time()
    submissions = dict(state.get("submissions", {}))
    existing = submissions.get(team["id"])
    submissions[team["id"]] = {
        "id": existing["id"] if existing else f"submission_{state.get('round_index', 0) + 1}_{team['id']}",
        "team_id": team["id"],
        "text": clean,
        "submitted_by": player_id,
        "created_at": existing["created_at"] if existing else submitted_at,
        "updated_at": submitted_at,
    }
    next_state = {**state, "submissions": submissions}
    if _all_teams_submitted(next_state):
        return start_reveal(next_state, now=submitted_at)
    return next_state


def start_reveal(state: dict, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_DISCUSSION, PHASE_REVEAL}:
        raise ValueError("Cannot reveal from this phase")
    return {**state, "phase": PHASE_REVEAL, "deadline": None}


def start_voting(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_REVEAL:
        raise ValueError("Common Ground is not in reveal")
    if not state.get("config", {}).get("voting_enabled", True):
        return score_round(state, now=now)
    started_at = now or time.time()
    return {**state, "phase": PHASE_VOTING, "deadline": started_at + int(state.get("config", {}).get("vote_time_seconds", 30))}


def submit_vote(state: dict, player_id: str, submission_id: str) -> dict:
    if state.get("phase") != PHASE_VOTING:
        raise ValueError("Common Ground is not accepting votes")
    team = _team_for_player(state, player_id)
    if not team:
        raise ValueError("You are not on a team")
    submissions = state.get("submissions", {})
    target = next((submission for submission in submissions.values() if submission.get("id") == submission_id), None)
    if not target:
        raise ValueError("Choose a valid team answer")
    if target.get("team_id") == team["id"]:
        raise ValueError("Vote for another team")
    votes = dict(state.get("votes_by_player", {}))
    votes[player_id] = submission_id
    return {**state, "votes_by_player": votes}


def score_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_REVEAL, PHASE_VOTING, PHASE_ROUND_RESULT}:
        raise ValueError("Cannot score this phase")
    scores = dict(state.get("scores", {}))
    submissions = state.get("submissions", {})
    first_team = None
    if submissions:
        first_team = min(submissions.values(), key=lambda item: item.get("created_at", 0)).get("team_id")
    round_scores = {}
    for team in state.get("teams", []):
        team_id = team["id"]
        score = 0
        submission = submissions.get(team_id)
        if submission:
            score += POINTS_SUBMISSION
            if team_id == first_team:
                score += POINTS_FIRST_SUBMISSION
            score += _vote_count(state, submission["id"]) * POINTS_PER_VOTE
        team_votes = [player for player in team.get("player_ids", []) if player in state.get("votes_by_player", {})]
        if state.get("config", {}).get("voting_enabled", True) and len(team_votes) == len(team.get("player_ids", [])) and team_votes:
            score += POINTS_FULL_TEAM_VOTE
        scores[team_id] = int(scores.get(team_id, 0)) + score
        round_scores[team_id] = score
    result = {
        "round_number": int(state.get("round_index", 0)) + 1,
        "prompt": _current_prompt(state),
        "round_scores": round_scores,
        "scores": scores,
        "submissions": _submission_list(state, include_text=True),
    }
    results = list(state.get("round_results", []))
    results.append(result)
    return {**state, "phase": PHASE_ROUND_RESULT, "scores": scores, "round_results": results, "deadline": None}


def next_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_ROUND_RESULT:
        raise ValueError("Round results are not ready")
    next_index = int(state.get("round_index", 0)) + 1
    if next_index >= int(state.get("config", {}).get("rounds", 5)):
        return {**state, "phase": PHASE_PODIUM, "completed_at": now or time.time(), "deadline": None}
    started_at = now or time.time()
    return {
        **state,
        "phase": PHASE_DISCUSSION,
        "round_index": next_index,
        "round_started_at": started_at,
        "deadline": started_at + int(state.get("config", {}).get("discussion_time_seconds", 90)),
        "submissions": {},
        "votes_by_player": {},
    }


def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    phase = state.get("phase", PHASE_DISCUSSION)
    include_text = phase in {PHASE_REVEAL, PHASE_VOTING, PHASE_ROUND_RESULT, PHASE_PODIUM}
    return {
        "phase": phase,
        "config": state.get("config", {}),
        "players": players or [{"nickname": player_id, "avatar": ""} for team in state.get("teams", []) for player_id in team.get("player_ids", [])],
        "teams": list(state.get("teams", [])),
        "round_number": int(state.get("round_index", 0)) + 1,
        "total_rounds": int(state.get("config", {}).get("rounds", 5)),
        "prompt": _current_prompt(state),
        "deadline": state.get("deadline"),
        "submissions": _submission_list(state, include_text=include_text),
        "votes_count": len(state.get("votes_by_player", {})) if include_text else 0,
        "scores": dict(state.get("scores", {})),
        "round_results": list(state.get("round_results", [])),
    }


def private_sync(state: dict, player_id: str, players: list[dict[str, str]] | None = None) -> dict:
    sync = public_sync(state, players)
    team = _team_for_player(state, player_id)
    sync["my_team_id"] = team["id"] if team else ""
    sync["my_vote"] = state.get("votes_by_player", {}).get(player_id, "")
    if team and state.get("phase") == PHASE_DISCUSSION:
        submission = state.get("submissions", {}).get(team["id"])
        sync["my_submission"] = dict(submission) if submission else None
    else:
        sync["my_submission"] = None
    return sync


def final_standings(state: dict) -> list[dict[str, Any]]:
    scores = state.get("scores", {})
    valid_counts = {}
    last_times = {}
    for result in state.get("round_results", []):
        for submission in result.get("submissions", []):
            if submission.get("has_submission"):
                valid_counts[submission["team_id"]] = valid_counts.get(submission["team_id"], 0) + 1
                last_times[submission["team_id"]] = max(last_times.get(submission["team_id"], 0), submission.get("updated_at") or 0)
    team_names = {team["id"]: team["name"] for team in state.get("teams", [])}
    return [
        {
            "team_id": team_id,
            "team": team_names.get(team_id, team_id),
            "score": int(score),
            "valid_submissions": valid_counts.get(team_id, 0),
            "members": len(next((team.get("player_ids", []) for team in state.get("teams", []) if team["id"] == team_id), [])),
        }
        for team_id, score in sorted(scores.items(), key=lambda item: (-item[1], -valid_counts.get(item[0], 0), last_times.get(item[0], 999999999), item[0]))
    ]
