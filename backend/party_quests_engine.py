import random
import re
import time
from typing import Any


PHASE_ACTIVE = "QUESTS_ACTIVE"
PHASE_FINAL_CALL = "QUESTS_FINAL_CALL"
PHASE_REVEAL = "QUESTS_REVEAL"
PHASE_PODIUM = "PODIUM"

POINTS_STANDARD = 100
POINTS_HARD = 150
POINTS_FIRST_BONUS = 50
POINTS_UNIQUE_PARTNER = 25
POINTS_COMPLETIONIST = 300

DEFAULT_QUESTS = [
    {"id": "quest_1", "display": "Talk to someone whose name starts with R.", "category": "name", "points": POINTS_STANDARD},
    {"id": "quest_2", "display": "Find someone born in the same month as you.", "category": "birthday_month", "points": POINTS_STANDARD},
    {"id": "quest_3", "display": "Find someone who plays a musical instrument.", "category": "hobby", "points": POINTS_STANDARD},
    {"id": "quest_4", "display": "Meet someone who shares one of your hobbies.", "category": "shared_interest", "points": POINTS_STANDARD},
    {"id": "quest_5", "display": "Find someone who has visited a city you want to visit.", "category": "travel", "points": POINTS_STANDARD},
    {"id": "quest_6", "display": "Find someone who likes the same snack as you.", "category": "food", "points": POINTS_STANDARD},
    {"id": "quest_7", "display": "Talk to someone who knows a good restaurant nearby.", "category": "food", "points": POINTS_STANDARD},
    {"id": "quest_8", "display": "Find someone wearing the same color as you.", "category": "custom", "points": POINTS_STANDARD},
    {"id": "quest_9", "display": "Find someone who has watched the same show as you recently.", "category": "shared_interest", "points": POINTS_STANDARD},
    {"id": "quest_10", "display": "Meet someone who has lived in another city.", "category": "travel", "points": POINTS_STANDARD},
    {"id": "quest_11", "display": "Find someone who can recommend a song.", "category": "hobby", "points": POINTS_STANDARD},
    {"id": "quest_12", "display": "Find someone who has tried a new hobby this year.", "category": "hobby", "points": POINTS_STANDARD},
    {"id": "quest_13", "display": "Talk to someone who has a funny travel story.", "category": "travel", "points": POINTS_HARD},
    {"id": "quest_14", "display": "Find someone who can teach you one word in another language.", "category": "custom", "points": POINTS_HARD},
    {"id": "quest_15", "display": "Find someone who has cooked something from scratch recently.", "category": "food", "points": POINTS_STANDARD},
    {"id": "quest_16", "display": "Meet someone who likes the same kind of movies as you.", "category": "shared_interest", "points": POINTS_STANDARD},
    {"id": "quest_17", "display": "Find someone who has been to a live concert.", "category": "hobby", "points": POINTS_STANDARD},
    {"id": "quest_18", "display": "Talk to someone who has solved an escape room.", "category": "custom", "points": POINTS_STANDARD},
    {"id": "quest_19", "display": "Find someone who has made a handmade gift.", "category": "custom", "points": POINTS_STANDARD},
    {"id": "quest_20", "display": "Meet someone who has a favorite dessert recipe.", "category": "food", "points": POINTS_STANDARD},
]


def _clean_text(value: Any, max_chars: int = 180) -> str:
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
    confirmation_mode = str(raw.get("confirmation_mode") or "tap_confirm").strip().lower()
    if confirmation_mode not in {"tap_confirm", "honor", "pair_code"}:
        confirmation_mode = "tap_confirm"
    reveal_mode = str(raw.get("reveal_mode") or "host_paced").strip().lower()
    if reveal_mode not in {"host_paced", "auto"}:
        reveal_mode = "host_paced"
    theme = _clean_text(raw.get("theme") or "party", 60).lower() or "party"

    quests = []
    raw_quests = raw.get("quests") or DEFAULT_QUESTS
    for index, quest in enumerate(raw_quests, start=1):
        if isinstance(quest, str):
            display = _clean_text(quest)
            category = "custom"
            points = POINTS_STANDARD
        else:
            item = quest or {}
            display = _clean_text(item.get("display") or item.get("text"))
            category = _clean_text(item.get("category") or "custom", 40) or "custom"
            try:
                points = int(item.get("points", POINTS_STANDARD))
            except (TypeError, ValueError):
                points = POINTS_STANDARD
        points = POINTS_HARD if points > POINTS_STANDARD else POINTS_STANDARD
        if display:
            quests.append({
                "id": f"quest_{index}",
                "display": display,
                "category": category,
                "points": points,
                "requires_partner": True,
            })

    min_quests = _clamp_int(raw, "quests_per_player", 8, 3, 25)
    if len(quests) < min_quests:
        existing = {item["display"].lower() for item in quests}
        for quest in DEFAULT_QUESTS:
            if len(quests) >= min_quests:
                break
            if quest["display"].lower() not in existing:
                quests.append({**quest, "id": f"quest_{len(quests) + 1}", "requires_partner": True})
    quests = quests[:120]

    return {
        "game_title": _clean_text(raw.get("game_title") or "Party Quests", 120) or "Party Quests",
        "quests": quests,
        "quest_count": len(quests),
        "quests_per_player": min(min_quests, max(3, len(quests))),
        "duration_minutes": _clamp_int(raw, "duration_minutes", 90, 10, 240),
        "confirmation_mode": confirmation_mode,
        "allow_repeat_partner": bool(raw.get("allow_repeat_partner", False)),
        "max_completions_per_partner": _clamp_int(raw, "max_completions_per_partner", 2, 1, 10),
        "reveal_mode": reveal_mode,
        "theme": theme,
        "allow_late_join": bool(raw.get("allow_late_join", True)),
        "auto_start_on_first_checkin": bool(raw.get("auto_start_on_first_checkin", True)),
    }


def assign_quests(player_ids: list[str], config: dict, seed: str | int | None = None) -> dict[str, list[dict]]:
    setup = validate_config(config)
    assignments = {}
    for player_id in [str(item).strip() for item in player_ids if str(item).strip()]:
        rng = random.Random(f"{seed}:{player_id}")
        quests = [dict(item) for item in setup["quests"]]
        rng.shuffle(quests)
        board = []
        for quest in quests[:setup["quests_per_player"]]:
            board.append({
                "quest_id": quest["id"],
                "display": quest["display"],
                "category": quest.get("category", "custom"),
                "points": int(quest.get("points", POINTS_STANDARD)),
                "status": "open",
                "confirmed_by_player_id": "",
                "confirmed_by_name": "",
                "completed_at": None,
            })
        assignments[player_id] = board
    return assignments


def create_initial_state(player_ids: list[str], config: dict | None = None, now: float | None = None, seed: str | int | None = None) -> dict:
    setup = validate_config(config)
    started_at = now or time.time()
    clean_players = [str(player_id).strip() for player_id in player_ids if str(player_id).strip()]
    boards = assign_quests(clean_players, setup, seed=seed or started_at)
    return {
        "phase": PHASE_ACTIVE,
        "config": setup,
        "started_at": started_at,
        "ends_at": started_at + int(setup["duration_minutes"]) * 60,
        "quest_boards_by_player": boards,
        "pending_confirmations": {},
        "completed_confirmations": [],
        "denied_confirmations": [],
        "scores": calculate_scores({"quest_boards_by_player": boards, "completed_confirmations": []}),
        "reveal_started": False,
        "completed_at": None,
        "_seed": seed or started_at,
    }


def add_player(state: dict, player_id: str, now: float | None = None) -> dict:
    player_id = str(player_id or "").strip()
    if not player_id or player_id in state.get("quest_boards_by_player", {}):
        return state
    if state.get("phase") not in {PHASE_ACTIVE, PHASE_FINAL_CALL}:
        return state
    if not state.get("config", {}).get("allow_late_join", True):
        return state
    boards = dict(state.get("quest_boards_by_player", {}))
    boards[player_id] = assign_quests([player_id], state.get("config", {}), seed=state.get("_seed") or state.get("started_at")).get(player_id, [])
    return _with_scores({**state, "quest_boards_by_player": boards})


def _board_item(state: dict, player_id: str, quest_id: str) -> dict | None:
    for item in state.get("quest_boards_by_player", {}).get(player_id, []):
        if item.get("quest_id") == quest_id:
            return item
    return None


def _partner_completion_count(state: dict, player_id: str, partner_player_id: str) -> int:
    count = 0
    for item in state.get("quest_boards_by_player", {}).get(player_id, []):
        if item.get("status") == "confirmed" and item.get("confirmed_by_player_id") == partner_player_id:
            count += 1
    return count


def create_confirmation_request(state: dict, player_id: str, quest_id: str, partner_player_id: str, now: float | None = None) -> tuple[dict, dict | None]:
    if state.get("phase") not in {PHASE_ACTIVE, PHASE_FINAL_CALL}:
        raise ValueError("Party Quests is not accepting completions now")
    player_id = str(player_id or "").strip()
    partner_player_id = str(partner_player_id or "").strip()
    boards = state.get("quest_boards_by_player", {})
    if player_id not in boards:
        raise ValueError("You are not in this game")
    if partner_player_id not in boards:
        raise ValueError("Choose someone currently in the game")
    if player_id == partner_player_id:
        raise ValueError("Choose someone else for this quest")
    item = _board_item(state, player_id, quest_id)
    if not item:
        raise ValueError("Choose a valid quest")
    if item.get("status") == "confirmed":
        raise ValueError("That quest is already complete")

    setup = state.get("config", {})
    if not setup.get("allow_repeat_partner") and _partner_completion_count(state, player_id, partner_player_id) >= int(setup.get("max_completions_per_partner", 2)):
        raise ValueError("Find a different person for this quest")

    timestamp = now or time.time()
    next_boards = {pid: [dict(entry) for entry in board] for pid, board in boards.items()}
    next_item = _board_item({"quest_boards_by_player": next_boards}, player_id, quest_id)
    pending = dict(state.get("pending_confirmations", {}))
    request = None

    if setup.get("confirmation_mode") == "honor":
        next_item.update({
            "status": "confirmed",
            "confirmed_by_player_id": partner_player_id,
            "confirmed_by_name": partner_player_id,
            "completed_at": timestamp,
        })
        completions = list(state.get("completed_confirmations", [])) + [{
            "id": f"honor_{int(timestamp * 1000)}_{len(state.get('completed_confirmations', [])) + 1}",
            "requester_id": player_id,
            "partner_player_id": partner_player_id,
            "quest_id": quest_id,
            "display": next_item["display"],
            "accepted_at": timestamp,
            "honor": True,
        }]
        return _with_scores({**state, "quest_boards_by_player": next_boards, "completed_confirmations": completions}), None

    request_id = f"quest_req_{int(timestamp * 1000)}_{len(pending) + 1}"
    next_item.update({
        "status": "pending_confirmation",
        "confirmed_by_player_id": partner_player_id,
        "confirmed_by_name": partner_player_id,
        "request_id": request_id,
    })
    request = {
        "id": request_id,
        "requester_id": player_id,
        "partner_player_id": partner_player_id,
        "quest_id": quest_id,
        "display": next_item["display"],
        "points": int(next_item.get("points", POINTS_STANDARD)),
        "created_at": timestamp,
        "expires_at": timestamp + 600,
    }
    pending[request_id] = request
    return _with_scores({**state, "quest_boards_by_player": next_boards, "pending_confirmations": pending}), request


def apply_confirmation(state: dict, request_id: str, confirmer_id: str, accepted: bool, now: float | None = None) -> tuple[dict, dict]:
    request_id = str(request_id or "")
    confirmer_id = str(confirmer_id or "").strip()
    pending = dict(state.get("pending_confirmations", {}))
    request = pending.get(request_id)
    if not request:
        raise ValueError("That confirmation is no longer available")
    if request.get("partner_player_id") != confirmer_id:
        raise ValueError("Only the selected person can confirm this quest")
    pending.pop(request_id, None)

    timestamp = now or time.time()
    boards = {pid: [dict(entry) for entry in board] for pid, board in state.get("quest_boards_by_player", {}).items()}
    item = _board_item({"quest_boards_by_player": boards}, request["requester_id"], request["quest_id"])
    if not item:
        raise ValueError("Quest was not found")

    if accepted:
        item.update({
            "status": "confirmed",
            "confirmed_by_player_id": confirmer_id,
            "confirmed_by_name": confirmer_id,
            "completed_at": timestamp,
        })
        completions = list(state.get("completed_confirmations", [])) + [{**request, "accepted_at": timestamp}]
        next_state = {**state, "quest_boards_by_player": boards, "pending_confirmations": pending, "completed_confirmations": completions}
        return _with_scores(next_state), {**request, "accepted": True}

    item.update({
        "status": "open",
        "confirmed_by_player_id": "",
        "confirmed_by_name": "",
        "request_id": "",
    })
    denied = list(state.get("denied_confirmations", [])) + [{**request, "denied_at": timestamp}]
    next_state = {**state, "quest_boards_by_player": boards, "pending_confirmations": pending, "denied_confirmations": denied}
    return _with_scores(next_state), {**request, "accepted": False}


def start_final_call(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_ACTIVE:
        return state
    timestamp = now or time.time()
    return {**state, "phase": PHASE_FINAL_CALL, "ends_at": timestamp + 60}


def reveal(state: dict, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_ACTIVE, PHASE_FINAL_CALL, PHASE_REVEAL}:
        return state
    return _with_scores({**state, "phase": PHASE_REVEAL, "reveal_started": True, "ends_at": None})


def complete(state: dict, now: float | None = None) -> dict:
    timestamp = now or time.time()
    return _with_scores({**state, "phase": PHASE_PODIUM, "reveal_started": True, "completed_at": timestamp, "ends_at": None})


def calculate_scores(state: dict) -> dict:
    scores = {}
    for player_id, board in state.get("quest_boards_by_player", {}).items():
        confirmed = [item for item in board if item.get("status") == "confirmed"]
        score = sum(int(item.get("points", POINTS_STANDARD)) for item in confirmed)
        unique_partners = {item.get("confirmed_by_player_id") for item in confirmed if item.get("confirmed_by_player_id")}
        score += len(unique_partners) * POINTS_UNIQUE_PARTNER
        if len(confirmed) >= len(board) and board:
            score += POINTS_COMPLETIONIST
        scores[player_id] = score
    completion_order = sorted(
        [
            (item.get("accepted_at") or item.get("completed_at") or 0, item.get("requester_id"))
            for item in state.get("completed_confirmations", [])
            if item.get("requester_id")
        ],
        key=lambda pair: pair[0],
    )
    for _, player_id in completion_order[:3]:
        scores[player_id] = scores.get(player_id, 0) + POINTS_FIRST_BONUS
    return scores


def _with_scores(state: dict) -> dict:
    return {**state, "scores": calculate_scores(state)}


def standings(state: dict) -> list[dict]:
    scores = calculate_scores(state)
    rows = []
    for player_id, board in state.get("quest_boards_by_player", {}).items():
        confirmed = [item for item in board if item.get("status") == "confirmed"]
        unique_partners = {item.get("confirmed_by_player_id") for item in confirmed if item.get("confirmed_by_player_id")}
        last_completed = max([float(item.get("completed_at") or 0) for item in confirmed] or [0])
        rows.append({
            "player_id": player_id,
            "score": int(scores.get(player_id, 0)),
            "completed": len(confirmed),
            "total": len(board),
            "unique_partners": len(unique_partners),
            "last_completed_at": last_completed,
        })
    rows.sort(key=lambda row: (-row["score"], -row["completed"], -row["unique_partners"], row["last_completed_at"] or float("inf"), row["player_id"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def awards(state: dict) -> list[dict]:
    rows = standings(state)
    if not rows:
        return []
    awards_list = [{"id": "winner", "label": "Quest Champion", "player_id": rows[0]["player_id"]}]
    social = max(rows, key=lambda row: (row["unique_partners"], row["completed"], row["score"], row["player_id"]))
    awards_list.append({"id": "social_butterfly", "label": "Social Butterfly", "player_id": social["player_id"]})
    completionists = [row for row in rows if row["completed"] >= row["total"] and row["total"]]
    if completionists:
        awards_list.append({"id": "completionist", "label": "Completionist", "player_id": completionists[0]["player_id"]})
    return awards_list


def _incoming_requests(state: dict, player_id: str) -> list[dict]:
    return [
        dict(request)
        for request in state.get("pending_confirmations", {}).values()
        if request.get("partner_player_id") == player_id
    ]


def _outgoing_requests(state: dict, player_id: str) -> list[dict]:
    return [
        dict(request)
        for request in state.get("pending_confirmations", {}).values()
        if request.get("requester_id") == player_id
    ]


def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    avatars = {item.get("nickname"): item.get("avatar", "") for item in players or []}
    rows = standings(state)
    player_list = [
        {"nickname": item.get("nickname", ""), "avatar": item.get("avatar", "")}
        for item in players or []
    ]
    return {
        "phase": state.get("phase", PHASE_ACTIVE),
        "config": state.get("config", {}),
        "players": player_list,
        "started_at": state.get("started_at"),
        "ends_at": state.get("ends_at"),
        "player_count": len(state.get("quest_boards_by_player", {})),
        "completed_count": len(state.get("completed_confirmations", [])),
        "pending_count": len(state.get("pending_confirmations", {})),
        "leaderboard": [
            {**row, "nickname": row["player_id"], "avatar": avatars.get(row["player_id"], "")}
            for row in rows[:10]
        ],
        "standings": [
            {**row, "nickname": row["player_id"], "avatar": avatars.get(row["player_id"], "")}
            for row in rows
        ] if state.get("phase") in {PHASE_REVEAL, PHASE_PODIUM} else [],
        "awards": awards(state) if state.get("phase") in {PHASE_REVEAL, PHASE_PODIUM} else [],
    }


def private_sync(state: dict, player_id: str, players: list[dict[str, str]] | None = None) -> dict:
    sync = public_sync(state, players)
    board = state.get("quest_boards_by_player", {}).get(player_id, [])
    sync["my_board"] = [dict(item) for item in board]
    sync["my_score"] = int(state.get("scores", calculate_scores(state)).get(player_id, 0))
    sync["incoming_requests"] = _incoming_requests(state, player_id)
    sync["outgoing_requests"] = _outgoing_requests(state, player_id)
    return sync


def result_summary(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    completed = state.get("completed_at") or time.time()
    top_rows = standings(state)[:5]
    return {
        "game_type": "party_quests",
        "title": state.get("config", {}).get("game_title", "Party Quests"),
        "status": "complete" if state.get("phase") == PHASE_PODIUM else "active",
        "duration_minutes": int(max(0, completed - float(state.get("started_at", completed))) // 60),
        "completed_quests": len(state.get("completed_confirmations", [])),
        "unique_confirmed_pairs": len({
            (item.get("requester_id"), item.get("partner_player_id"))
            for item in state.get("completed_confirmations", [])
        }),
        "top_players": top_rows,
        "awards": awards(state),
    }
