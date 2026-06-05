import re
import time
import unicodedata
from typing import Any


PHASE_ROUND = "WHOAMI_ROUND"
PHASE_REVEAL = "WHOAMI_REVEAL"
PHASE_PODIUM = "PODIUM"

DEFAULT_POINTS = [500, 400, 300, 200, 100, 50]

DEFAULT_ROUNDS = [
    {
        "id": "round_1",
        "answer": "Shah Rukh Khan",
        "aliases": ["SRK", "King Khan", "Shahrukh Khan"],
        "category": "Actor",
        "clues": [
            "I was born in New Delhi.",
            "I became famous on Indian television before films.",
            "I am closely associated with romantic films.",
            "I co-own a cricket team.",
            "Fans often call me King Khan.",
        ],
        "difficulty": "medium",
    },
    {
        "id": "round_2",
        "answer": "Sachin Tendulkar",
        "aliases": ["Sachin", "The Little Master"],
        "category": "Cricketer",
        "clues": [
            "I made my international debut as a teenager.",
            "I am associated with the number 10 jersey.",
            "I played for India for more than two decades.",
            "I scored 100 international centuries.",
            "I am often called the Little Master.",
        ],
        "difficulty": "medium",
    },
    {
        "id": "round_3",
        "answer": "Taylor Swift",
        "aliases": ["Taylor"],
        "category": "Musician",
        "clues": [
            "I grew up in Pennsylvania.",
            "My albums are often known as eras.",
            "I moved from country music into pop.",
            "My lucky number is famously 13.",
            "Fans call themselves Swifties.",
        ],
        "difficulty": "easy",
    },
    {
        "id": "round_4",
        "answer": "The Eiffel Tower",
        "aliases": ["Eiffel Tower"],
        "category": "Landmark",
        "clues": [
            "I was built for a world fair.",
            "I am made mostly of iron.",
            "I stand beside the Seine.",
            "I am one of Europe's most famous landmarks.",
            "You will find me in Paris.",
        ],
        "difficulty": "easy",
    },
    {
        "id": "round_5",
        "answer": "Spider-Man",
        "aliases": ["Spiderman", "Peter Parker"],
        "category": "Character",
        "clues": [
            "I first appeared in a comic book in the 1960s.",
            "I am known for quick jokes during fights.",
            "I live in New York City.",
            "My uncle taught me a famous lesson about responsibility.",
            "I swing between buildings using webs.",
        ],
        "difficulty": "easy",
    },
]


def _clean_text(value: Any, max_chars: int = 180) -> str:
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


def normalize_guess(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(a|an|the)\s+", "", text)
    return text


def _edit_distance_at_most_one(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        if (
            len(a) == len(b)
            and i + 1 < len(a)
            and j + 1 < len(b)
            and a[i] == b[j + 1]
            and a[i + 1] == b[j]
        ):
            edits += 1
            if edits > 1:
                return False
            i += 2
            j += 2
            continue
        edits += 1
        if edits > 1:
            return False
        if len(a) == len(b):
            i += 1
        j += 1
    return True


def _accepted_answers(round_item: dict) -> set[str]:
    values = [round_item.get("answer"), *list(round_item.get("aliases") or [])]
    return {normalized for value in values if (normalized := normalize_guess(value))}


def is_correct_guess(guess: Any, round_item: dict, fuzzy: bool = True) -> bool:
    normalized = normalize_guess(guess)
    if len(normalized) < 2:
        return False
    accepted = _accepted_answers(round_item)
    if normalized in accepted:
        return True
    if not fuzzy or len(normalized) < 5:
        return False
    return any(len(answer) >= 5 and _edit_distance_at_most_one(normalized, answer) for answer in accepted)


def _sanitize_round(raw: dict, index: int, clue_count: int) -> dict | None:
    answer = _clean_text(raw.get("answer"), 80)
    if len(answer) < 2:
        return None
    aliases = []
    for alias in raw.get("aliases") or []:
        clean = _clean_text(alias, 80)
        if clean and normalize_guess(clean) != normalize_guess(answer) and clean not in aliases:
            aliases.append(clean)
    clues = []
    answer_norm = normalize_guess(answer)
    for clue in raw.get("clues") or []:
        clean = _clean_text(clue, 180)
        if len(clean) >= 8 and answer_norm not in normalize_guess(clean):
            clues.append(clean)
    if len(clues) < 3:
        return None
    while len(clues) < clue_count:
        clues.append(clues[-1])
    return {
        "id": _clean_text(raw.get("id") or f"round_{index}", 40) or f"round_{index}",
        "answer": answer,
        "aliases": aliases[:8],
        "category": _clean_text(raw.get("category") or "Mystery", 60) or "Mystery",
        "clues": clues[:clue_count],
        "difficulty": _clean_text(raw.get("difficulty") or "medium", 20) or "medium",
    }


def validate_config(raw: dict | None) -> dict:
    raw = raw or {}
    clue_count = _clamp_int(raw, "clues_per_round", 5, 3, 6)
    rounds = []
    seen_answers = set()
    source_rounds = raw.get("rounds") if isinstance(raw.get("rounds"), list) else DEFAULT_ROUNDS
    for index, item in enumerate(source_rounds, start=1):
        if not isinstance(item, dict):
            continue
        sanitized = _sanitize_round(item, index, clue_count)
        if not sanitized:
            continue
        answer_key = normalize_guess(sanitized["answer"])
        if answer_key in seen_answers:
            continue
        seen_answers.add(answer_key)
        rounds.append(sanitized)
    if len(rounds) < 3:
        rounds = [_sanitize_round(item, index, clue_count) for index, item in enumerate(DEFAULT_ROUNDS, start=1)]
        rounds = [item for item in rounds if item]

    points = []
    for value in raw.get("points_by_clue") or DEFAULT_POINTS:
        try:
            points.append(max(0, int(value)))
        except (TypeError, ValueError):
            continue
    points = (points + DEFAULT_POINTS)[:clue_count]
    for index in range(1, len(points)):
        if points[index] > points[index - 1]:
            points[index] = points[index - 1]

    round_count = _clamp_int(raw, "round_count", min(10, len(rounds)), 3, 25)
    return {
        "game_title": _clean_text(raw.get("game_title") or "Who Am I?", 120) or "Who Am I?",
        "theme": _clean_text(raw.get("theme") or "", 80),
        "round_count": min(round_count, len(rounds)),
        "clues_per_round": clue_count,
        "guess_time_seconds": _clamp_int(raw, "guess_time_seconds", 25, 10, 90),
        "clue_reveal_mode": "manual",
        "allow_multiple_guesses_per_clue": bool(raw.get("allow_multiple_guesses_per_clue", True)),
        "max_guesses_per_player_per_clue": _clamp_int(raw, "max_guesses_per_player_per_clue", 3, 1, 10),
        "fuzzy_match_enabled": bool(raw.get("fuzzy_match_enabled", True)),
        "points_by_clue": points,
        "rounds": rounds[:round_count],
    }


def create_initial_state(player_ids: list[str], config: dict, now: float | None = None) -> dict:
    setup = validate_config(config)
    started_at = now or time.time()
    return {
        "phase": PHASE_ROUND,
        "config": setup,
        "players": [str(player_id) for player_id in player_ids if str(player_id)],
        "current_round_index": 0,
        "current_clue_index": 0,
        "correct_by_player": {},
        "guesses_by_player": {},
        "scores": {str(player_id): 0 for player_id in player_ids if str(player_id)},
        "round_revealed": False,
        "deadline": started_at + setup["guess_time_seconds"],
        "completed_at": None,
    }


def _current_round(state: dict) -> dict:
    rounds = state.get("config", {}).get("rounds", [])
    index = min(int(state.get("current_round_index", 0)), max(0, len(rounds) - 1))
    return rounds[index] if rounds else DEFAULT_ROUNDS[0]


def score_for_clue(points: list[int], clue_index: int) -> int:
    if not points:
        return 0
    index = max(0, min(int(clue_index), len(points) - 1))
    return int(points[index])


def public_sync(state: dict, players: list[dict[str, str]] | None = None) -> dict:
    round_item = _current_round(state)
    clue_index = int(state.get("current_clue_index", 0))
    all_clues = list(round_item.get("clues", []))
    clues = [
        {"index": index, "text": text if index <= clue_index else "", "revealed": index <= clue_index}
        for index, text in enumerate(all_clues)
    ]
    revealed = all_clues[:clue_index + 1]
    phase = state.get("phase", PHASE_ROUND)
    correct_items = list(state.get("correct_by_player", {}).values())
    guess_count = sum(len(value) for value in state.get("guesses_by_player", {}).values())
    config_payload = {k: v for k, v in state.get("config", {}).items() if k != "rounds"}
    config_payload["clue_count"] = int(config_payload.get("clues_per_round", len(all_clues)))
    config_payload["max_guesses_per_clue"] = int(config_payload.get("max_guesses_per_player_per_clue", 3))
    payload = {
        "phase": phase,
        "config": config_payload,
        "players": players or [{"nickname": player_id, "avatar": ""} for player_id in state.get("players", [])],
        "round_number": int(state.get("current_round_index", 0)) + 1,
        "total_rounds": len(state.get("config", {}).get("rounds", [])),
        "clue_index": clue_index,
        "clues": clues,
        "current_clue_index": clue_index,
        "revealed_clues": revealed,
        "category": round_item.get("category", ""),
        "correct_count": len(correct_items),
        "correct_players": [item.get("player_id", "") for item in correct_items if item.get("player_id")],
        "correct_guessers": correct_items,
        "guesses_count": guess_count,
        "scores": dict(state.get("scores", {})),
        "deadline": state.get("deadline"),
        "round_revealed": bool(state.get("round_revealed")),
    }
    if phase in {PHASE_REVEAL, PHASE_PODIUM} or state.get("round_revealed"):
        payload["answer"] = round_item.get("answer", "")
        payload["aliases"] = list(round_item.get("aliases", []))
    return payload


def private_sync(state: dict, player_id: str, players: list[dict[str, str]] | None = None) -> dict:
    sync = public_sync(state, players)
    guesses = state.get("guesses_by_player", {}).get(player_id, [])
    sync["my_guesses"] = guesses
    sync["my_correct"] = player_id in state.get("correct_by_player", {})
    return sync


def submit_guess(state: dict, player_id: str, guess: Any, now: float | None = None) -> tuple[dict, dict]:
    if state.get("phase") != PHASE_ROUND:
        raise ValueError("This round is not accepting guesses")
    clean = _clean_text(guess, 80)
    if len(normalize_guess(clean)) < 2:
        raise ValueError("Type a guess first")
    if player_id in state.get("correct_by_player", {}):
        return state, {"correct": True, "points": 0, "message": "You already got this one."}

    clue_index = int(state.get("current_clue_index", 0))
    guesses_by_player = {key: list(value) for key, value in state.get("guesses_by_player", {}).items()}
    guesses = guesses_by_player.get(player_id, [])
    used_this_clue = len([item for item in guesses if int(item.get("clue_index", -1)) == clue_index])
    max_guesses = int(state.get("config", {}).get("max_guesses_per_player_per_clue", 3))
    if used_this_clue >= max_guesses:
        raise ValueError("Wait for the next clue before guessing again")

    round_item = _current_round(state)
    correct = is_correct_guess(clean, round_item, bool(state.get("config", {}).get("fuzzy_match_enabled", True)))
    submitted_at = now or time.time()
    guess_item = {
        "player_id": player_id,
        "guess": clean,
        "clue_index": clue_index,
        "correct": correct,
        "created_at": submitted_at,
    }
    guesses_by_player[player_id] = guesses + [guess_item]
    next_state = {**state, "guesses_by_player": guesses_by_player}
    points = 0
    if correct:
        points = score_for_clue(list(state.get("config", {}).get("points_by_clue", DEFAULT_POINTS)), clue_index)
        scores = dict(state.get("scores", {}))
        scores[player_id] = int(scores.get(player_id, 0)) + points
        correct_by_player = dict(state.get("correct_by_player", {}))
        correct_by_player[player_id] = {
            "player_id": player_id,
            "clue_index": clue_index,
            "points": points,
            "guess": clean,
            "created_at": submitted_at,
        }
        next_state = {**next_state, "scores": scores, "correct_by_player": correct_by_player}

    return next_state, {
        "correct": correct,
        "points": points,
        "message": f"Correct! You got it after clue {clue_index + 1}." if correct else "Not quite. Try again after another clue.",
    }


def next_clue(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_ROUND:
        raise ValueError("Cannot reveal a clue now")
    clue_index = int(state.get("current_clue_index", 0))
    max_index = len(_current_round(state).get("clues", [])) - 1
    if clue_index >= max_index:
        return reveal_answer(state)
    started_at = now or time.time()
    return {**state, "current_clue_index": clue_index + 1, "deadline": started_at + int(state.get("config", {}).get("guess_time_seconds", 25))}


def reveal_answer(state: dict, now: float | None = None) -> dict:
    if state.get("phase") not in {PHASE_ROUND, PHASE_REVEAL}:
        raise ValueError("Cannot reveal the answer now")
    return {**state, "phase": PHASE_REVEAL, "round_revealed": True, "deadline": None}


def next_round(state: dict, now: float | None = None) -> dict:
    if state.get("phase") != PHASE_REVEAL:
        raise ValueError("Reveal the answer before the next round")
    next_index = int(state.get("current_round_index", 0)) + 1
    if next_index >= len(state.get("config", {}).get("rounds", [])):
        return {**state, "phase": PHASE_PODIUM, "round_revealed": True, "deadline": None, "completed_at": now or time.time()}
    started_at = now or time.time()
    return {
        **state,
        "phase": PHASE_ROUND,
        "current_round_index": next_index,
        "current_clue_index": 0,
        "correct_by_player": {},
        "guesses_by_player": {},
        "round_revealed": False,
        "deadline": started_at + int(state.get("config", {}).get("guess_time_seconds", 25)),
    }


def final_standings(state: dict) -> list[dict[str, Any]]:
    scores = state.get("scores", {})
    return [
        {"nickname": player_id, "score": score}
        for player_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0].lower()))
    ]


def sanitize_generated_game(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return validate_config(raw)


def validate_generated_game(raw: dict) -> bool:
    try:
        game = sanitize_generated_game(raw)
    except Exception:
        return False
    return len(game.get("rounds", [])) >= 3
