import random
import re
import time
from typing import Any


PHASE_ROLE_REVEAL = "MAFIA_ROLE_REVEAL"
PHASE_NIGHT = "MAFIA_NIGHT"
PHASE_DAY_DISCUSSION = "MAFIA_DAY_DISCUSSION"
PHASE_DAY_VOTE = "MAFIA_DAY_VOTE"
PHASE_VOTE_RESULT = "MAFIA_VOTE_RESULT"
PHASE_PODIUM = "PODIUM"

ROLE_VILLAGER = "villager"
ROLE_DETECTIVE = "detective"
ROLE_DOCTOR = "doctor"
ROLE_MAFIA = "mafia"

TEAM_TOWN = "town"
TEAM_MAFIA = "mafia"
TARGET_SKIP = "skip"

NIGHT_READ_PROMPTS = [
    {
        "id": "suspect_mafia",
        "label": "Most suspected",
        "question": "Who do you most suspect is Mafia right now?",
    },
    {
        "id": "trusted_town",
        "label": "Most trusted",
        "question": "Who feels definitely Town right now?",
    },
    {
        "id": "best_social_game",
        "label": "Best social game",
        "question": "Who is playing the best social game so far?",
    },
    {
        "id": "changed_behavior",
        "label": "Changed behavior",
        "question": "Who changed their behavior this round?",
    },
    {
        "id": "discussion_leader",
        "label": "Listen to",
        "question": "Who should the town listen to during the next discussion?",
    },
]

ROLE_DISTRIBUTION = {
    6: {"mafia": 1, "detective": 1, "doctor": 1, "villager": 3},
    7: {"mafia": 2, "detective": 1, "doctor": 1, "villager": 3},
    8: {"mafia": 2, "detective": 1, "doctor": 1, "villager": 4},
    9: {"mafia": 2, "detective": 1, "doctor": 1, "villager": 5},
    10: {"mafia": 3, "detective": 1, "doctor": 1, "villager": 5},
    11: {"mafia": 3, "detective": 1, "doctor": 1, "villager": 6},
    12: {"mafia": 3, "detective": 1, "doctor": 1, "villager": 7},
    13: {"mafia": 4, "detective": 1, "doctor": 1, "villager": 7},
    14: {"mafia": 4, "detective": 1, "doctor": 1, "villager": 8},
    15: {"mafia": 4, "detective": 1, "doctor": 1, "villager": 9},
}


def _clean_text(value: Any, max_chars: int = 120) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(value or ""))
    text = re.sub(r"<\s*/?\s*(script|style|iframe)[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]


def _clamp_int(raw: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    theme = str(raw.get("theme") or "classic").strip().lower()
    if theme not in {"classic", "werewolf", "none"}:
        theme = "classic"
    tie_behavior = str(raw.get("tie_behavior") or "no_elimination").strip().lower()
    if tie_behavior not in {"no_elimination", "revote_once"}:
        tie_behavior = "no_elimination"
    return {
        "game_title": _clean_text(raw.get("game_title") or "Mafia", 120) or "Mafia",
        "theme": theme,
        "include_detective": bool(raw.get("include_detective", True)),
        "include_doctor": bool(raw.get("include_doctor", True)),
        "doctor_self_protect": bool(raw.get("doctor_self_protect", True)),
        "night_timer_seconds": _clamp_int(raw, "night_timer_seconds", 30, 15, 60),
        "discussion_timer_seconds": _clamp_int(raw, "discussion_timer_seconds", 90, 30, 180),
        "vote_timer_seconds": _clamp_int(raw, "vote_timer_seconds", 30, 15, 60),
        "role_reveal_seconds": _clamp_int(raw, "role_reveal_seconds", 10, 5, 20),
        "tie_behavior": tie_behavior,
    }


def role_distribution(player_count: int, include_detective: bool = True, include_doctor: bool = True) -> dict:
    if player_count not in ROLE_DISTRIBUTION:
        raise ValueError("Mafia requires 6 to 15 players")
    distribution = dict(ROLE_DISTRIBUTION[player_count])
    if not include_detective:
        distribution["villager"] += distribution["detective"]
        distribution["detective"] = 0
    if not include_doctor:
        distribution["villager"] += distribution["doctor"]
        distribution["doctor"] = 0
    return distribution


def _rng(state: dict) -> random.Random:
    rng = random.Random()
    if state.get("_rng_state") is not None:
        rng.setstate(state["_rng_state"])
    return rng


def _save_rng(state: dict, rng: random.Random) -> dict:
    next_state = dict(state)
    next_state["_rng_state"] = rng.getstate()
    return next_state


def _role_team(role: str) -> str:
    return TEAM_MAFIA if role == ROLE_MAFIA else TEAM_TOWN


def _players_by_id(state: dict) -> dict[str, dict]:
    return {player["id"]: player for player in state.get("players", [])}


def _living_players(state: dict) -> list[dict]:
    return [player for player in state.get("players", []) if player.get("alive", True)]


def _living_ids(state: dict) -> list[str]:
    return [player["id"] for player in _living_players(state)]


def _living_mafia(state: dict) -> list[dict]:
    return [player for player in _living_players(state) if player.get("role") == ROLE_MAFIA]


def _living_town(state: dict) -> list[dict]:
    return [player for player in _living_players(state) if player.get("role") != ROLE_MAFIA]


def _check_win(state: dict) -> str | None:
    mafia_count = len(_living_mafia(state))
    town_count = len(_living_town(state))
    if mafia_count <= 0:
        return TEAM_TOWN
    if mafia_count >= town_count:
        return TEAM_MAFIA
    return None


def _public_player(player: dict, reveal_all: bool = False) -> dict:
    role = player.get("role") if reveal_all or not player.get("alive", True) else None
    return {
        "nickname": player["id"],
        "avatar": player.get("avatar", ""),
        "alive": bool(player.get("alive", True)),
        "role": role,
        "eliminated_round": player.get("eliminated_round"),
    }


def _safe_night_result(result: dict | None) -> dict | None:
    if not result:
        return None
    return {
        "round": result.get("round"),
        "killed": result.get("killed"),
        "killed_role": result.get("killed_role"),
        "narration": result.get("narration", ""),
        "night_read_highlights": list(result.get("night_read_highlights", [])),
    }


def _safe_vote_result(result: dict | None) -> dict | None:
    if not result:
        return None
    return {
        "round": result.get("round"),
        "tally": dict(result.get("tally", {})),
        "eliminated": result.get("eliminated"),
        "eliminated_role": result.get("eliminated_role"),
        "tied": bool(result.get("tied")),
    }


def _new_night_actions() -> dict:
    return {"mafia_votes": {}, "detective": {}, "doctor": {}}


def _deadline(now: float | None, seconds: int) -> float:
    return (now or time.time()) + seconds


def _template_narration(killed: str | None, killed_role: str | None, saved: bool, theme: str) -> str:
    if killed:
        if theme == "werewolf":
            return f"At dawn, the village found {killed} missing from the circle. They were a {killed_role}."
        return f"The town wakes up to grim news: {killed} was eliminated during the night. They were a {killed_role}."
    if saved:
        return "The town wakes up shaken, but everyone survived the night."
    return "The town wakes up uneasy, but everyone survived the night. The night passed without a clear target."


def _night_read_prompt_for_player(state: dict, player_id: str) -> dict:
    round_number = int(state.get("round", 1) or 1)
    return NIGHT_READ_PROMPTS[(round_number - 1) % len(NIGHT_READ_PROMPTS)]


def _night_read_prompt_by_id(prompt_id: str) -> dict | None:
    for prompt in NIGHT_READ_PROMPTS:
        if prompt["id"] == prompt_id:
            return prompt
    return None


def _night_read_answers_for_round(state: dict, round_number: int | None = None) -> list[dict]:
    current_round = int(round_number or state.get("round", 1) or 1)
    return [
        item for item in state.get("night_reads", [])
        if int(item.get("round", 0) or 0) == current_round
    ]


def _night_read_for_player(state: dict, player_id: str) -> dict | None:
    current_round = int(state.get("round", 1) or 1)
    for item in reversed(state.get("night_reads", [])):
        if int(item.get("round", 0) or 0) == current_round and item.get("respondent_id") == player_id:
            return item
    return None


def _night_read_highlights(state: dict, round_number: int | None = None) -> list[dict]:
    answers = _night_read_answers_for_round(state, round_number)
    living_at_resolution = {player["id"] for player in state.get("players", [])}
    grouped: dict[str, dict[str, int]] = {}
    for item in answers:
        prompt_id = str(item.get("prompt_id") or "")
        selected = str(item.get("selected_player_id") or "")
        if not prompt_id or selected not in living_at_resolution:
            continue
        grouped.setdefault(prompt_id, {})
        grouped[prompt_id][selected] = grouped[prompt_id].get(selected, 0) + 1

    highlights = []
    for prompt in NIGHT_READ_PROMPTS:
        counts = grouped.get(prompt["id"], {})
        total = sum(counts.values())
        if total < 3:
            continue
        high = max(counts.values(), default=0)
        if high <= 0:
            continue
        leaders = sorted([player_id for player_id, count in counts.items() if count == high])
        highlights.append({
            "prompt_id": prompt["id"],
            "label": prompt["label"],
            "player_id": leaders[0],
            "count": high,
            "total": total,
            "tied": len(leaders) > 1,
        })
    return highlights[:3]


def create_initial_state(player_ids: list[str], config: dict | None = None, seed: int | str | None = None, now: float | None = None) -> dict:
    setup = validate_config(config)
    players = [str(player_id).strip() for player_id in player_ids if str(player_id).strip()]
    if len(players) != len(set(players)):
        raise ValueError("Mafia player ids must be unique")
    if len(players) < 6 or len(players) > 15:
        raise ValueError("Mafia requires 6 to 15 players")

    distribution = role_distribution(
        len(players),
        include_detective=setup["include_detective"],
        include_doctor=setup["include_doctor"],
    )
    roles = (
        [ROLE_MAFIA] * distribution["mafia"]
        + [ROLE_DETECTIVE] * distribution["detective"]
        + [ROLE_DOCTOR] * distribution["doctor"]
        + [ROLE_VILLAGER] * distribution["villager"]
    )
    rng = random.Random(seed)
    rng.shuffle(roles)
    created_at = now or time.time()
    state = {
        "phase": PHASE_ROLE_REVEAL,
        "config": setup,
        "players": [
            {
                "id": player_id,
                "role": role,
                "team": _role_team(role),
                "alive": True,
                "eliminated_round": None,
                "eliminated_by": None,
            }
            for player_id, role in zip(players, roles)
        ],
        "round": 1,
        "night_actions": _new_night_actions(),
        "night_reads": [],
        "night_log": [],
        "vote_log": [],
        "votes": {},
        "winner": None,
        "deadline": _deadline(created_at, setup["role_reveal_seconds"]),
        "created_at": created_at,
        "completed_at": None,
        "_rng_state": rng.getstate(),
    }
    return state


def advance_after_role_reveal(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_ROLE_REVEAL:
        raise ValueError("Role reveal is not active")
    config = state.get("config", {})
    return {
        **state,
        "phase": PHASE_NIGHT,
        "night_actions": _new_night_actions(),
        "votes": {},
        "deadline": _deadline(now, int(config.get("night_timer_seconds", 30))),
    }


def _night_action_kind(role: str) -> str:
    if role == ROLE_MAFIA:
        return "mafia_kill"
    if role == ROLE_DETECTIVE:
        return "investigate"
    if role == ROLE_DOCTOR:
        return "protect"
    return "none"


def _eligible_night_targets(state: dict, actor_id: str) -> list[str]:
    players = _players_by_id(state)
    actor = players.get(actor_id)
    if not actor or not actor.get("alive", True):
        return []
    role = actor.get("role")
    living = _living_players(state)
    if role == ROLE_MAFIA:
        return [player["id"] for player in living if player.get("role") != ROLE_MAFIA]
    if role == ROLE_DETECTIVE:
        return [player["id"] for player in living if player["id"] != actor_id]
    if role == ROLE_DOCTOR:
        if bool(state.get("config", {}).get("doctor_self_protect", True)):
            return [player["id"] for player in living]
        return [player["id"] for player in living if player["id"] != actor_id]
    return []


def submit_night_action(state: dict, actor_id: str, target_id: str) -> dict:
    if state.get("phase") != PHASE_NIGHT:
        raise ValueError("Night actions are not open")
    players = _players_by_id(state)
    actor = players.get(actor_id)
    if not actor or not actor.get("alive", True):
        raise ValueError("Only living players can act at night")
    if _night_action_kind(actor.get("role")) == "none":
        raise ValueError("This role has no night action")
    if target_id not in _eligible_night_targets(state, actor_id):
        raise ValueError("Invalid night action target")

    actions = {
        "mafia_votes": dict(state.get("night_actions", {}).get("mafia_votes", {})),
        "detective": dict(state.get("night_actions", {}).get("detective", {})),
        "doctor": dict(state.get("night_actions", {}).get("doctor", {})),
    }
    if actor.get("role") == ROLE_MAFIA:
        actions["mafia_votes"][actor_id] = target_id
    elif actor.get("role") == ROLE_DETECTIVE:
        actions["detective"][actor_id] = target_id
    elif actor.get("role") == ROLE_DOCTOR:
        actions["doctor"][actor_id] = target_id
    return {**state, "night_actions": actions}


def submit_night_read(state: dict, actor_id: str, selected_player_id: str) -> dict:
    if state.get("phase") != PHASE_NIGHT:
        raise ValueError("Night reads are not open")
    players = _players_by_id(state)
    actor = players.get(actor_id)
    target = players.get(selected_player_id)
    if not actor or not actor.get("alive", True):
        raise ValueError("Only living players can submit a night read")
    if not target or not target.get("alive", True):
        raise ValueError("Night read target must be living")
    if selected_player_id == actor_id:
        raise ValueError("Choose another player")

    prompt = _night_read_prompt_for_player(state, actor_id)
    current_round = int(state.get("round", 1) or 1)
    reads = [
        item for item in state.get("night_reads", [])
        if not (int(item.get("round", 0) or 0) == current_round and item.get("respondent_id") == actor_id)
    ]
    reads.append({
        "round": current_round,
        "prompt_id": prompt["id"],
        "respondent_id": actor_id,
        "selected_player_id": selected_player_id,
    })
    return {**state, "night_reads": reads}


def _mafia_target_from_votes(state: dict, rng: random.Random) -> str | None:
    valid_targets = _eligible_targets_for_mafia_group(state)
    if not valid_targets:
        return None
    votes = [
        target
        for target in state.get("night_actions", {}).get("mafia_votes", {}).values()
        if target in valid_targets
    ]
    if not votes:
        return rng.choice(valid_targets)
    counts = {target: votes.count(target) for target in votes}
    high = max(counts.values())
    tied = {target for target, count in counts.items() if count == high}
    for target in votes:
        if target in tied:
            return target
    return None


def _eligible_targets_for_mafia_group(state: dict) -> list[str]:
    return [player["id"] for player in _living_town(state)]


def resolve_night(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_NIGHT:
        raise ValueError("Night is not active")
    rng = _rng(state)
    players_by_id = _players_by_id(state)
    actions = state.get("night_actions", {})
    mafia_target = _mafia_target_from_votes(state, rng)
    doctor_target = next(iter(actions.get("doctor", {}).values()), None)
    detective_target = next(iter(actions.get("detective", {}).values()), None)
    detective_id = next(iter(actions.get("detective", {}).keys()), None)
    saved = bool(mafia_target and doctor_target == mafia_target)
    killed = mafia_target if mafia_target and not saved else None

    next_players = [dict(player) for player in state.get("players", [])]
    killed_role = None
    if killed:
        for player in next_players:
            if player["id"] == killed and player.get("alive", True):
                player["alive"] = False
                player["eliminated_round"] = int(state.get("round", 1))
                player["eliminated_by"] = "night"
                killed_role = player.get("role")
                break

    detective_result = None
    if detective_id and detective_target in players_by_id:
        detective_result = TEAM_MAFIA if players_by_id[detective_target].get("role") == ROLE_MAFIA else TEAM_TOWN

    narration = _template_narration(killed, killed_role, saved, state.get("config", {}).get("theme", "classic"))
    night_result = {
        "round": int(state.get("round", 1)),
        "mafia_target": mafia_target,
        "doctor_target": doctor_target,
        "detective_target": detective_target,
        "detective_id": detective_id,
        "detective_result": detective_result,
        "killed": killed,
        "killed_role": killed_role,
        "saved": saved,
        "narration": narration,
        "night_read_highlights": _night_read_highlights(state),
    }
    next_state = {
        **state,
        "players": next_players,
        "night_log": list(state.get("night_log", [])) + [night_result],
        "phase": PHASE_DAY_DISCUSSION,
        "deadline": _deadline(now, int(state.get("config", {}).get("discussion_timer_seconds", 90))),
    }
    winner = _check_win(next_state)
    if winner:
        next_state["winner"] = winner
        next_state["phase"] = PHASE_PODIUM
        next_state["deadline"] = None
        next_state["completed_at"] = now or time.time()
    return _save_rng(next_state, rng)


def start_day_vote(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_DAY_DISCUSSION:
        raise ValueError("Day discussion is not active")
    return {
        **state,
        "phase": PHASE_DAY_VOTE,
        "votes": {},
        "deadline": _deadline(now, int(state.get("config", {}).get("vote_timer_seconds", 30))),
    }


def submit_vote(state: dict, voter_id: str, target_id: str) -> dict:
    if state.get("phase") != PHASE_DAY_VOTE:
        raise ValueError("Voting is not open")
    players = _players_by_id(state)
    voter = players.get(voter_id)
    if not voter or not voter.get("alive", True):
        raise ValueError("Only living players can vote")
    if target_id != TARGET_SKIP:
        target = players.get(target_id)
        if not target or not target.get("alive", True):
            raise ValueError("Vote target must be living")
        if target_id == voter_id:
            raise ValueError("Vote for another player or skip")
    votes = dict(state.get("votes", {}))
    votes[voter_id] = target_id
    return {**state, "votes": votes}


def resolve_vote(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_DAY_VOTE:
        raise ValueError("Voting is not open")
    living_ids = _living_ids(state)
    votes = {voter: target for voter, target in state.get("votes", {}).items() if voter in living_ids}
    for voter in living_ids:
        votes.setdefault(voter, TARGET_SKIP)

    tally: dict[str, int] = {}
    for target in votes.values():
        tally[target] = tally.get(target, 0) + 1
    max_votes = max(tally.values(), default=0)
    top_targets = sorted([target for target, count in tally.items() if count == max_votes])
    tied = len(top_targets) > 1
    eliminated = None
    eliminated_role = None
    next_players = [dict(player) for player in state.get("players", [])]
    if not tied and top_targets and top_targets[0] != TARGET_SKIP:
        eliminated = top_targets[0]
        for player in next_players:
            if player["id"] == eliminated and player.get("alive", True):
                player["alive"] = False
                player["eliminated_round"] = int(state.get("round", 1))
                player["eliminated_by"] = "vote"
                eliminated_role = player.get("role")
                break

    result = {
        "round": int(state.get("round", 1)),
        "votes": votes,
        "tally": tally,
        "eliminated": eliminated,
        "eliminated_role": eliminated_role,
        "tied": tied,
    }
    next_state = {
        **state,
        "players": next_players,
        "votes": votes,
        "vote_log": list(state.get("vote_log", [])) + [result],
        "phase": PHASE_VOTE_RESULT,
        "deadline": _deadline(now, 8),
    }
    winner = _check_win(next_state)
    if winner:
        next_state["winner"] = winner
        next_state["phase"] = PHASE_PODIUM
        next_state["deadline"] = None
        next_state["completed_at"] = now or time.time()
    return next_state


def advance_after_vote_result(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_VOTE_RESULT:
        raise ValueError("Vote result is not active")
    winner = _check_win(state)
    if winner:
        return force_complete(state, winner=winner, now=now)
    return {
        **state,
        "phase": PHASE_NIGHT,
        "round": int(state.get("round", 1)) + 1,
        "night_actions": _new_night_actions(),
        "votes": {},
        "deadline": _deadline(now, int(state.get("config", {}).get("night_timer_seconds", 30))),
    }


def force_complete(state: dict, winner: str | None = None, now: float | None = None) -> dict:
    resolved_winner = winner or state.get("winner") or _check_win(state)
    return {
        **state,
        "phase": PHASE_PODIUM,
        "winner": resolved_winner,
        "deadline": None,
        "completed_at": now or time.time(),
    }


def _vote_progress(state: dict) -> dict:
    eligible = len(_living_ids(state)) if state.get("phase") == PHASE_DAY_VOTE else 0
    submitted = len([voter for voter in state.get("votes", {}) if voter in _living_ids(state)])
    return {"submitted": submitted, "eligible": eligible}


def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    avatars = {item.get("nickname"): item.get("avatar", "") for item in players or []}
    reveal_all = state.get("phase") == PHASE_PODIUM
    public_players = []
    for player in state.get("players", []):
        row = _public_player({**player, "avatar": avatars.get(player["id"], player.get("avatar", ""))}, reveal_all=reveal_all)
        public_players.append(row)
    return {
        "phase": state.get("phase", PHASE_ROLE_REVEAL),
        "config": state.get("config", {}),
        "round": int(state.get("round", 1)),
        "players": public_players,
        "alive_count": len([player for player in state.get("players", []) if player.get("alive", True)]),
        "eliminated_count": len([player for player in state.get("players", []) if not player.get("alive", True)]),
        "deadline": state.get("deadline"),
        "vote_progress": _vote_progress(state),
        "last_night": _safe_night_result((state.get("night_log") or [None])[-1]),
        "last_vote": _safe_vote_result((state.get("vote_log") or [None])[-1]),
        "winner": state.get("winner"),
    }


def private_sync(state: dict, player_id: str, players: list[dict[str, str]] | None = None) -> dict:
    sync = public_sync(state, players)
    player = _players_by_id(state).get(player_id)
    if not player:
        return sync
    sync["my_role"] = player.get("role")
    sync["ghost"] = not bool(player.get("alive", True))
    action = {"kind": "none", "eligible_targets": []}
    if state.get("phase") == PHASE_NIGHT and player.get("alive", True):
        kind = _night_action_kind(player.get("role"))
        read_prompt = _night_read_prompt_for_player(state, player_id)
        read_answer = _night_read_for_player(state, player_id)
        action = {
            "kind": kind,
            "eligible_targets": _eligible_night_targets(state, player_id),
            "submitted_target": "",
            "night_read": {
                "prompt_id": read_prompt["id"],
                "label": read_prompt["label"],
                "question": read_prompt["question"],
                "eligible_targets": [pid for pid in _living_ids(state) if pid != player_id],
                "submitted_target": read_answer.get("selected_player_id") if read_answer else "",
            },
        }
        if kind == "mafia_kill":
            action["submitted_target"] = state.get("night_actions", {}).get("mafia_votes", {}).get(player_id, "")
            action["mafia_teammates"] = [p["id"] for p in _living_mafia(state) if p["id"] != player_id]
        elif kind == "investigate":
            action["submitted_target"] = state.get("night_actions", {}).get("detective", {}).get(player_id, "")
        elif kind == "protect":
            action["submitted_target"] = state.get("night_actions", {}).get("doctor", {}).get(player_id, "")
    sync["my_action"] = action
    sync["my_vote"] = state.get("votes", {}).get(player_id, "")
    if player.get("role") == ROLE_DETECTIVE:
        sync["my_investigations"] = [
            {
                "round": item.get("round"),
                "target": item.get("detective_target"),
                "result": item.get("detective_result"),
            }
            for item in state.get("night_log", [])
            if item.get("detective_id") == player_id and item.get("detective_target")
        ]
    return sync


def result_summary(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    avatars = {item.get("nickname"): item.get("avatar", "") for item in players or []}
    completed = state.get("completed_at") or time.time()
    rows = []
    for player in state.get("players", []):
        rows.append({
            "nickname": player["id"],
            "avatar": avatars.get(player["id"], player.get("avatar", "")),
            "role": player.get("role"),
            "survived": bool(player.get("alive", True)),
            "eliminated_round": player.get("eliminated_round"),
        })
    highlights = []
    for item in state.get("night_log", []):
        if item.get("saved"):
            highlights.append(f"Someone was saved during Night {item.get('round')}.")
    if state.get("winner"):
        highlights.insert(0, f"{state.get('winner').title()} won after {state.get('round', 1)} round(s).")
    return {
        "game_type": "mafia",
        "title": state.get("config", {}).get("game_title", "Mafia"),
        "status": "complete" if state.get("phase") == PHASE_PODIUM else "active",
        "theme": state.get("config", {}).get("theme", "classic"),
        "winner": state.get("winner"),
        "rounds_played": int(state.get("round", 1)),
        "player_count": len(state.get("players", [])),
        "duration_seconds": max(0, int(completed - float(state.get("created_at", completed)))),
        "players": rows,
        "highlights": highlights[:3],
    }


def required_night_actor_ids(state: dict) -> list[str]:
    return [
        player["id"]
        for player in _living_players(state)
        if _night_action_kind(player.get("role")) != "none" and _eligible_night_targets(state, player["id"])
    ]


def required_night_read_actor_ids(state: dict) -> list[str]:
    if state.get("phase") != PHASE_NIGHT:
        return []
    return _living_ids(state)


def all_required_night_actions_submitted(state: dict) -> bool:
    actions = state.get("night_actions", {})
    for player_id in required_night_actor_ids(state):
        role = _players_by_id(state)[player_id].get("role")
        if role == ROLE_MAFIA and player_id not in actions.get("mafia_votes", {}):
            return False
        if role == ROLE_DETECTIVE and player_id not in actions.get("detective", {}):
            return False
        if role == ROLE_DOCTOR and player_id not in actions.get("doctor", {}):
            return False
    read_submitters = {
        item.get("respondent_id")
        for item in _night_read_answers_for_round(state)
    }
    for player_id in required_night_read_actor_ids(state):
        if player_id not in read_submitters:
            return False
    return True


def all_living_votes_submitted(state: dict) -> bool:
    return all(player_id in state.get("votes", {}) for player_id in _living_ids(state))
