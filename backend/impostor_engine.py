"""Impostor — the pass-and-play secret-word game (SPEC-PASS-AND-PLAY §2).

The teen-popular one. Everyone is shown the same secret word except one player, who is told they
are the impostor. The phone goes on the table and each player, in turn, says ONE word aloud that
relates to the secret word — vague enough not to hand it to the impostor, specific enough to prove
they know it. Then the table votes.

Two rules carry the whole game and are worth stating up front:

- **A caught impostor can still win** by naming the secret word. Without that comeback rule the
  impostor's best play once suspected is to go quiet, which is boring; with it, they stay engaged
  to the last second and the reveal has a real twist.
- **Conviction needs a strict majority, not a plurality** (see `pass_play_common.strict_majority`).

This engine holds NO per-viewer secrets: there is one device, so it returns full state and the UI's
privacy gate is what keeps the impostor's identity from being shoulder-surfed. That is a deliberate
architectural choice, documented in the spec — do not "fix" it by scoping payloads.
"""
from __future__ import annotations

import random
from typing import Any, Optional

from engine_common import clamp_int, clean_text
from pass_play_common import (
    MAX_SEATS,
    MIN_SEATS,
    advance_turn,
    create_turn_order,
    current_turn,
    find_seat,
    rounds_completed,
    seat_ids,
    strict_majority,
    tally_votes,
)

PHASE_REVEAL_ROLES = "IMP_REVEAL_ROLES"   # passing the phone around for secret role reveal
PHASE_CLUES = "IMP_CLUES"                 # phone face-up, players speak clues in turn
PHASE_VOTING = "IMP_VOTING"               # table votes on the shared screen
PHASE_ACCUSED_GUESS = "IMP_ACCUSED_GUESS" # caught impostor gets one shot at the word
PHASE_REVEAL = "IMP_REVEAL"               # outcome + scores
PHASE_PODIUM = "PODIUM"

MIN_PLAYERS = MIN_SEATS  # 3 — with 2, the impostor is a coin flip

DEFAULT_CLUE_ROUNDS = 2
MIN_CLUE_ROUNDS = 1
MAX_CLUE_ROUNDS = 4

POINTS_CAUGHT_IMPOSTOR = 2      # each knower, when the impostor is convicted
POINTS_IMPOSTOR_SURVIVED = 3    # impostor, when the table fails to convict them
POINTS_IMPOSTOR_GUESSED = 3     # impostor, when convicted but they name the word

MAX_WORD = 40

# Curated word pairs: (secret, decoy). The decoy is what the impostor sees in "hint" mode — a
# near-miss from the same category so their clues sound plausible instead of obviously random.
# AI generation comes later (SPEC-PASS-AND-PLAY §2); curated first keeps content safe by default.
DEFAULT_WORD_PACKS: dict[str, list[tuple[str, str]]] = {
    "everyday": [
        ("Toothbrush", "Hairbrush"), ("Umbrella", "Raincoat"), ("Pillow", "Blanket"),
        ("Kettle", "Toaster"), ("Backpack", "Suitcase"), ("Mirror", "Window"),
    ],
    "food": [
        ("Pizza", "Pasta"), ("Ice cream", "Milkshake"), ("Popcorn", "Crisps"),
        ("Pancake", "Waffle"), ("Burger", "Sandwich"), ("Sushi", "Dumplings"),
    ],
    "places": [
        ("Beach", "Swimming pool"), ("Airport", "Train station"), ("Library", "Bookshop"),
        ("Cinema", "Theatre"), ("Zoo", "Aquarium"), ("Playground", "Skate park"),
    ],
    "animals": [
        ("Penguin", "Seal"), ("Elephant", "Rhino"), ("Octopus", "Squid"),
        ("Owl", "Eagle"), ("Kangaroo", "Rabbit"), ("Camel", "Horse"),
    ],
}
DEFAULT_PACK = "everyday"


def _sanitize_pair(raw: Any) -> Optional[tuple[str, str]]:
    """Accept {secret, decoy} or [secret, decoy]; drop anything unusable."""
    if isinstance(raw, dict):
        secret = clean_text(raw.get("secret"), MAX_WORD)
        decoy = clean_text(raw.get("decoy"), MAX_WORD)
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        secret = clean_text(raw[0], MAX_WORD)
        decoy = clean_text(raw[1], MAX_WORD)
    else:
        return None
    if not secret:
        return None
    # A decoy identical to the secret would hand the impostor the answer.
    if decoy.strip().lower() == secret.strip().lower():
        decoy = ""
    return (secret, decoy)


def validate_config(raw: dict | None) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    pack = clean_text(raw.get("pack"), 40) or DEFAULT_PACK
    if pack not in DEFAULT_WORD_PACKS:
        pack = DEFAULT_PACK

    pairs: list[tuple[str, str]] = []
    for item in (raw.get("pairs") if isinstance(raw.get("pairs"), list) else []):
        cleaned = _sanitize_pair(item)
        if cleaned:
            pairs.append(cleaned)
    if not pairs:
        pairs = list(DEFAULT_WORD_PACKS[pack])

    return {
        "pack": pack,
        "pairs": [{"secret": s, "decoy": d} for s, d in pairs],
        "clue_rounds": clamp_int(raw, "clue_rounds", DEFAULT_CLUE_ROUNDS, MIN_CLUE_ROUNDS, MAX_CLUE_ROUNDS),
        # Hint mode gives the impostor the decoy word. Off = they know only that they're the
        # impostor, which is harder and better for experienced groups.
        "impostor_hint": bool(raw.get("impostor_hint", True)),
        "total_rounds": clamp_int(raw, "total_rounds", 3, 1, 10),
    }


def can_start(seats: list[dict]) -> bool:
    return isinstance(seats, list) and MIN_PLAYERS <= len(seats) <= MAX_SEATS


def create_initial_state(seats: list[dict], config: dict | None = None,
                         rng: random.Random | None = None) -> dict:
    cfg = validate_config(config)
    rng = rng or random.Random()
    state = {
        "phase": PHASE_REVEAL_ROLES,
        "config": cfg,
        "seats": list(seats),
        "round_number": 0,
        "scores": {sid: 0 for sid in seat_ids(seats)},
        "used_pair_indexes": [],
        "history": [],
    }
    return start_round(state, rng=rng)


def start_round(state: dict, rng: random.Random | None = None) -> dict:
    """Assign a fresh impostor + word pair and reset to the role-reveal pass."""
    rng = rng or random.Random()
    cfg = state["config"]
    ids = seat_ids(state.get("seats", []))
    pairs = cfg["pairs"]

    # Don't repeat a word pair until the deck is exhausted — a repeat is instantly recognisable
    # and hands the round to anyone who was paying attention.
    used = [i for i in state.get("used_pair_indexes", []) if 0 <= i < len(pairs)]
    if len(used) >= len(pairs):
        used = []
    available = [i for i in range(len(pairs)) if i not in used]
    idx = rng.choice(available) if available else 0
    used.append(idx)

    state["used_pair_indexes"] = used
    state["round_number"] = int(state.get("round_number", 0)) + 1
    state["impostor_id"] = rng.choice(ids) if ids else ""
    state["secret_word"] = pairs[idx]["secret"]
    state["decoy_word"] = pairs[idx]["decoy"]
    state["revealed_to"] = []
    state["clues"] = []
    state["votes"] = {}
    state["accused_id"] = ""
    state["accused_guess"] = ""
    state["outcome"] = ""
    state["turn"] = create_turn_order(state.get("seats", []))
    state["phase"] = PHASE_REVEAL_ROLES
    return state


# --- Phase 1: secret role reveal (pass the phone) ----------------------------------------------


def role_for(state: dict, sid: str) -> dict:
    """What this seat sees behind the privacy gate."""
    is_impostor = sid == state.get("impostor_id")
    if is_impostor:
        return {
            "is_impostor": True,
            "word": state.get("decoy_word", "") if state["config"]["impostor_hint"] else "",
            "hint_mode": bool(state["config"]["impostor_hint"]),
        }
    return {"is_impostor": False, "word": state.get("secret_word", ""), "hint_mode": False}


def mark_revealed(state: dict, sid: str) -> dict:
    """Record that a seat has seen their role and passed the phone on."""
    if sid and sid in seat_ids(state.get("seats", [])) and sid not in state["revealed_to"]:
        state["revealed_to"].append(sid)
    if all_revealed(state):
        state["phase"] = PHASE_CLUES
        state["turn"] = create_turn_order(state.get("seats", []))
    return state


def all_revealed(state: dict) -> bool:
    return set(state.get("revealed_to", [])) >= set(seat_ids(state.get("seats", [])))


def next_unrevealed(state: dict) -> str:
    for sid in seat_ids(state.get("seats", [])):
        if sid not in state.get("revealed_to", []):
            return sid
    return ""


# --- Phase 2: spoken clues (phone face-up) ----------------------------------------------------


def record_clue(state: dict, sid: str, word: str = "") -> dict:
    """Mark a seat's clue as spoken. `word` is optional — clues are said ALOUD, and typing them
    would both slow the game to a crawl and leak information to a later reader. We store it only
    when the host chooses to log it for the reveal recap."""
    if state.get("phase") != PHASE_CLUES:
        return state
    if sid != current_turn(state.get("turn", {})):
        return state
    state["clues"].append({
        "seat_id": sid,
        "word": clean_text(word, MAX_WORD),
        "round": rounds_completed(state["turn"]) + 1,
    })
    advance_turn(state["turn"])
    if rounds_completed(state["turn"]) >= state["config"]["clue_rounds"]:
        state["phase"] = PHASE_VOTING
    return state


# --- Phase 3: the vote ------------------------------------------------------------------------


def submit_vote(state: dict, voter_id: str, accused_id: str) -> dict:
    if state.get("phase") != PHASE_VOTING:
        return state
    ids = seat_ids(state.get("seats", []))
    if voter_id not in ids or accused_id not in ids:
        return state
    if voter_id == accused_id:      # no self-votes; it's either a misclick or a joke
        return state
    state["votes"][voter_id] = accused_id
    return state


def all_voted(state: dict) -> bool:
    return len(state.get("votes", {})) >= len(seat_ids(state.get("seats", [])))


def close_vote(state: dict) -> dict:
    """Resolve the vote. A convicted impostor gets one shot at the word before scoring."""
    if state.get("phase") != PHASE_VOTING:
        return state
    counts = tally_votes(state.get("votes", {}))
    convicted = strict_majority(counts, len(seat_ids(state.get("seats", []))))
    state["accused_id"] = convicted
    if convicted and convicted == state.get("impostor_id"):
        state["phase"] = PHASE_ACCUSED_GUESS
    else:
        state["outcome"] = "impostor_survived"
        _score_round(state)
        state["phase"] = PHASE_REVEAL
    return state


def submit_accused_guess(state: dict, guess: str) -> dict:
    """The comeback rule: a caught impostor who names the secret word wins the round anyway."""
    if state.get("phase") != PHASE_ACCUSED_GUESS:
        return state
    state["accused_guess"] = clean_text(guess, MAX_WORD)
    correct = state["accused_guess"].strip().lower() == state.get("secret_word", "").strip().lower()
    state["outcome"] = "impostor_guessed" if correct else "impostor_caught"
    _score_round(state)
    state["phase"] = PHASE_REVEAL
    return state


def _score_round(state: dict) -> None:
    outcome = state.get("outcome")
    impostor = state.get("impostor_id", "")
    scores = state.setdefault("scores", {})
    if outcome == "impostor_caught":
        for sid in seat_ids(state.get("seats", [])):
            if sid != impostor:
                scores[sid] = scores.get(sid, 0) + POINTS_CAUGHT_IMPOSTOR
    elif outcome == "impostor_survived":
        scores[impostor] = scores.get(impostor, 0) + POINTS_IMPOSTOR_SURVIVED
    elif outcome == "impostor_guessed":
        scores[impostor] = scores.get(impostor, 0) + POINTS_IMPOSTOR_GUESSED
    state.setdefault("history", []).append({
        "round": state.get("round_number"),
        "secret_word": state.get("secret_word"),
        "impostor_id": impostor,
        "outcome": outcome,
        "accused_id": state.get("accused_id", ""),
    })


def next_round(state: dict, rng: random.Random | None = None) -> dict:
    if state.get("round_number", 0) >= state["config"]["total_rounds"]:
        state["phase"] = PHASE_PODIUM
        return state
    return start_round(state, rng=rng)


def standings(state: dict) -> list[dict]:
    seats = state.get("seats", [])
    scores = state.get("scores", {})
    rows = [
        {
            "seat_id": sid,
            "nickname": (find_seat(seats, sid) or {}).get("name", ""),
            "emoji": (find_seat(seats, sid) or {}).get("emoji", ""),
            "score": scores.get(sid, 0),
        }
        for sid in seat_ids(seats)
    ]
    rows.sort(key=lambda r: (-r["score"], r["nickname"]))
    return rows


def public_state(state: dict) -> dict:
    """Everything the single client needs. Includes the secret only once the round is resolved —
    the privacy gate handles in-round secrecy, but there's no reason to ship the answer to a
    face-up clue screen where it could be glimpsed in a network log or a screenshot."""
    resolved = state.get("phase") in (PHASE_REVEAL, PHASE_PODIUM)
    return {
        "phase": state.get("phase"),
        "round_number": state.get("round_number"),
        "total_rounds": state["config"]["total_rounds"],
        "clue_rounds": state["config"]["clue_rounds"],
        "seats": state.get("seats", []),
        "turn": state.get("turn", {}),
        "revealed_to": state.get("revealed_to", []),
        "next_unrevealed": next_unrevealed(state),
        "clues": state.get("clues", []),
        "votes": state.get("votes", {}),
        "accused_id": state.get("accused_id", ""),
        "outcome": state.get("outcome", ""),
        "standings": standings(state),
        "secret_word": state.get("secret_word", "") if resolved else "",
        "impostor_id": state.get("impostor_id", "") if resolved else "",
        "accused_guess": state.get("accused_guess", ""),
    }
