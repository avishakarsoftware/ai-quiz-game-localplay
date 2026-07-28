"""Pure Impostor game mechanics (SPEC-GAME-IMPOSTOR).

Renamed from "Odd One Out" 2026-07-28: that id collided with the pre-existing quiz VARIANT
`odd_one_out` ("find the item that breaks the pattern"), which shipped in v3.1.3. Two different
games sharing one id meant the variant's rules modal showed this game's rules once the backend
catalog loaded. The standalone game was one day old and deployed nowhere, so it took the new name.

Asymmetric-prompt social deduction: everyone answers what looks like the same question, one player
secretly got a different one, and the group votes on who it was. Fills the gap between the catalog's
symmetric-prompt games and Mafia (which needs 6 players and a moderator-ish flow).

This module is pure: no I/O, no websockets, no clock beyond an injectable `now`. All state lives in
the returned dict so socket_manager can snapshot/restore it like every other engine.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from engine_common import clamp_int as _clamp_int, make_clean_text

_clean_text = make_clean_text(max_chars=120)

PHASE_ANSWERING = "ODDQ_ANSWERING"
PHASE_VOTING = "ODDQ_VOTING"
PHASE_REVEAL = "ODDQ_REVEAL"
PHASE_PODIUM = "PODIUM"

MIN_PLAYERS = 3

# Scoring (see SPEC §3). Deliberately asymmetric: catching the odd one is the group's job, and
# surviving is worth more than a single correct accusation so being the odd one feels like a prize.
POINTS_CORRECT_VOTE = 2
POINTS_ODD_SURVIVES = 3
POINTS_ODD_MISDIRECT = 1

# Prompt pairs must be CLOSE. "beach vs gym" is ambiguous enough that one answer doesn't give the
# odd one away; "beach vs tax return" ends the round instantly. The deck is the tuning surface.
DEFAULT_PROMPT_PAIRS: list[dict[str, str]] = [
    {"id": "oddq_1", "majority": "Name something you'd take to the beach.",
     "minority": "Name something you'd take to the gym."},
    {"id": "oddq_2", "majority": "Name something you'd find in a kitchen.",
     "minority": "Name something you'd find in a garage."},
    {"id": "oddq_3", "majority": "Name a good first-date activity.",
     "minority": "Name a good team-building activity."},
    {"id": "oddq_4", "majority": "Name something you'd pack for a camping trip.",
     "minority": "Name something you'd pack for a music festival."},
    {"id": "oddq_5", "majority": "Name something people do at a wedding.",
     "minority": "Name something people do at a birthday party."},
    {"id": "oddq_6", "majority": "Name something that's better cold.",
     "minority": "Name something that's better fresh."},
    {"id": "oddq_7", "majority": "Name a reason to leave a party early.",
     "minority": "Name a reason to leave work early."},
    {"id": "oddq_8", "majority": "Name something you'd bring to a picnic.",
     "minority": "Name something you'd bring to a road trip."},
    {"id": "oddq_9", "majority": "Name something a tourist does.",
     "minority": "Name something a new neighbour does."},
    {"id": "oddq_10", "majority": "Name something you'd never lend out.",
     "minority": "Name something you'd never buy used."},
]


def _sanitize_pair(raw: Any, index: int) -> Optional[dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    majority = _clean_text(raw.get("majority"))
    minority = _clean_text(raw.get("minority"))
    if not majority or not minority:
        return None
    pair_id = _clean_text(raw.get("id")) or f"oddq_custom_{index + 1}"
    return {"id": pair_id, "majority": majority, "minority": minority}


def validate_config(raw: dict | None) -> dict:
    """Normalize host setup. Falls back to the curated deck rather than erroring, so a malformed
    custom deck degrades to a playable game instead of a dead room."""
    raw = raw if isinstance(raw, dict) else {}
    pairs: list[dict[str, str]] = []
    for index, item in enumerate(raw.get("prompt_pairs") or []):
        pair = _sanitize_pair(item, index)
        if pair:
            pairs.append(pair)
    if not pairs:
        pairs = [dict(p) for p in DEFAULT_PROMPT_PAIRS]
    total_rounds = _clamp_int(raw, "total_rounds", default=min(5, len(pairs)), low=1, high=len(pairs))
    return {"prompt_pairs": pairs, "total_rounds": total_rounds}


def create_initial_state(player_ids: list[str], config: dict | None = None,
                         now: float | None = None) -> dict:
    cfg = validate_config(config)
    seats = [p for p in dict.fromkeys(player_ids) if p]
    return {
        "phase": PHASE_ANSWERING,
        "config": cfg,
        # Rotation order, NOT random per round: with random selection a player can plausibly never
        # be the odd one in a short game, which is the whole reason to play.
        "rotation": seats,
        "round_index": 0,
        "odd_player_id": seats[0] if seats else "",
        "answers": {},           # player_id -> text
        "votes": {},             # voter_id -> accused_id
        "scores": {p: 0 for p in seats},
        # First round each player may participate in. Late joiners get the NEXT round, so a
        # player who walked in mid-round can't answer or vote on answers they may have already
        # seen on the host screen. Without this they'd be accepted the moment they're seated.
        "seated_from_round": {p: 0 for p in seats},
        "round_result": None,
        "started_at": now if now is not None else time.time(),
    }


def can_start(player_ids: list[str]) -> bool:
    return len({p for p in player_ids if p}) >= MIN_PLAYERS


def current_pair(state: dict) -> dict[str, str]:
    pairs = state["config"]["prompt_pairs"]
    return pairs[state["round_index"] % len(pairs)]


def is_eligible(state: dict, player_id: str) -> bool:
    """Whether a player may act in the CURRENT round.

    A late joiner is seated (and in the rotation, so they get a turn as the odd one) but is not
    eligible until the next round — they may have seen this round's answers on the host screen.
    """
    if player_id not in state["scores"]:
        return False
    return state.get("seated_from_round", {}).get(player_id, 0) <= state["round_index"]


def eligible_voters(state: dict) -> list[str]:
    """Everyone who may act in this round. Late joiners are excluded until the next round."""
    return [p for p in state["rotation"] if is_eligible(state, p)]


def add_player(state: dict, player_id: str) -> dict:
    """Seat a late joiner for the NEXT round.

    They are appended to the rotation (so they still get a turn as the odd one) but deliberately
    cannot answer or vote in the round already underway — they may have seen the answers on the
    host screen, and letting them vote would be worse than making them wait one round.
    """
    if not player_id or player_id in state["scores"]:
        return state
    state["rotation"].append(player_id)
    state["scores"][player_id] = 0
    state.setdefault("seated_from_round", {})[player_id] = state["round_index"] + 1
    return state


def submit_answer(state: dict, player_id: str, text: str) -> dict:
    if state["phase"] != PHASE_ANSWERING or not is_eligible(state, player_id):
        return state
    cleaned = _clean_text(text)
    if not cleaned:
        return state
    # Overwrite rather than append: a double-tap must not become two answers.
    state["answers"][player_id] = cleaned
    return state


def all_answered(state: dict) -> bool:
    voters = eligible_voters(state)
    return bool(voters) and all(p in state["answers"] for p in voters)


def start_voting(state: dict) -> dict:
    if state["phase"] != PHASE_ANSWERING:
        return state
    state["phase"] = PHASE_VOTING
    return state


def submit_vote(state: dict, voter_id: str, accused_id: str) -> dict:
    if state["phase"] != PHASE_VOTING:
        return state
    if not is_eligible(state, voter_id) or accused_id not in state["scores"]:
        return state
    if voter_id == accused_id:
        return state          # self-votes rejected outright, never silently reassigned
    state["votes"][voter_id] = accused_id
    return state


def all_voted(state: dict) -> bool:
    voters = eligible_voters(state)
    return bool(voters) and all(p in state["votes"] for p in voters)


def _tally(state: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for accused in state["votes"].values():
        counts[accused] = counts.get(accused, 0) + 1
    return counts


def reveal_round(state: dict) -> dict:
    """Score the round and move to REVEAL. Idempotent — calling twice must not double-score,
    because both a host action and an all-voted auto-advance can reach here."""
    if state["phase"] == PHASE_REVEAL:
        return state
    odd = state["odd_player_id"]
    counts = _tally(state)
    voters = eligible_voters(state)

    # "Caught" requires a STRICT MAJORITY of eligible voters, not a plurality: at 5 players a
    # 2-vote plurality would catch the odd one almost every round and the game stops being fun.
    caught = counts.get(odd, 0) * 2 > len(voters)

    for voter, accused in state["votes"].items():
        if voter != odd and accused == odd:
            state["scores"][voter] = state["scores"].get(voter, 0) + POINTS_CORRECT_VOTE

    if not caught and odd in state["scores"]:
        state["scores"][odd] = state["scores"].get(odd, 0) + POINTS_ODD_SURVIVES

    # Misdirect bonus: the odd one gets something to do during the vote instead of waiting.
    odd_vote = state["votes"].get(odd)
    if odd_vote and odd_vote != odd and counts:
        top = max(counts.values())
        if counts.get(odd_vote, 0) == top and odd_vote != odd:
            state["scores"][odd] = state["scores"].get(odd, 0) + POINTS_ODD_MISDIRECT

    pair = current_pair(state)
    state["round_result"] = {
        "odd_player_id": odd,
        "caught": caught,
        "vote_counts": counts,
        "majority_prompt": pair["majority"],
        "minority_prompt": pair["minority"],
        "answers": dict(state["answers"]),
        "votes": dict(state["votes"]),
    }
    state["phase"] = PHASE_REVEAL
    return state


def is_final_round(state: dict) -> bool:
    return state["round_index"] + 1 >= state["config"]["total_rounds"]


def next_round(state: dict) -> dict:
    if state["phase"] != PHASE_REVEAL:
        return state
    if is_final_round(state):
        state["phase"] = PHASE_PODIUM
        return state
    state["round_index"] += 1
    state["answers"] = {}
    state["votes"] = {}
    state["round_result"] = None
    rotation = state["rotation"]
    eligible = [p for p in rotation if is_eligible(state, p)]
    pool = eligible or rotation
    state["odd_player_id"] = pool[state["round_index"] % len(pool)] if pool else ""
    state["phase"] = PHASE_ANSWERING
    return state


def standings(state: dict) -> list[dict]:
    """Ranked standings in the shape the simple-social family already uses.

    `rank` is included because the shared frontend helpers (`sortedStandings`) sort on it — this
    game conforms to the family contract rather than making the component special-case it.
    """
    ordered = sorted(state["scores"].items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        {"player_id": pid, "score": score, "rank": index + 1}
        for index, (pid, score) in enumerate(ordered)
    ]


def public_state(state: dict, viewer_id: str | None = None, host: bool = False) -> dict:
    """Viewer-scoped snapshot.

    THE critical invariant: a non-odd player must never see the minority prompt, and the odd one
    must never see the majority prompt. Leaking either destroys the game outright, so prompts are
    resolved per viewer here rather than broadcast and filtered downstream.

    The host screen shows neither prompt during play — the host is usually visible to the room, so
    putting the answer on their screen would leak it to everyone.
    """
    pair = current_pair(state)
    is_odd = viewer_id is not None and viewer_id == state["odd_player_id"]
    revealed = state["phase"] in (PHASE_REVEAL, PHASE_PODIUM)

    payload: dict[str, Any] = {
        "phase": state["phase"],
        # Family field names (current_round_index / round_count) so the shared frontend round
        # label and standings helpers work without a per-game branch. round_index/total_rounds
        # are kept as aliases because the engine's own tests and callers read them.
        "current_round_index": state["round_index"],
        "round_count": state["config"]["total_rounds"],
        "round_index": state["round_index"],
        "total_rounds": state["config"]["total_rounds"],
        "game_title": "Odd Question",
        "answer_count": len(state["answers"]),
        "vote_count": len(state["votes"]),
        "player_count": len(state["scores"]),
        "standings": standings(state),
    }

    if state["phase"] == PHASE_VOTING or revealed:
        payload["answers"] = [
            {"player_id": pid, "text": text} for pid, text in state["answers"].items()
        ]

    if revealed:
        payload["round_result"] = state["round_result"]
        payload["is_final_round"] = is_final_round(state)
    elif viewer_id is not None and viewer_id in state["scores"]:
        # Each player sees exactly one prompt: their own.
        payload["prompt"] = pair["minority"] if is_odd else pair["majority"]
        payload["you_are_odd"] = is_odd
        payload["your_answer"] = state["answers"].get(viewer_id, "")
        payload["your_vote"] = state["votes"].get(viewer_id, "")
    elif host:
        payload["awaiting"] = [p for p in eligible_voters(state) if p not in state["answers"]]

    return payload
