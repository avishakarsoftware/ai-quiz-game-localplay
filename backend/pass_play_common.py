"""Shared mechanics for pass-and-play games (SPEC-PASS-AND-PLAY).

Pass-and-play inverts LocalPlay's usual model: instead of one phone per player, the ROOM has one
phone (the host's) and it is handed person to person. That changes two things fundamentally, and
everything in this module exists because of them:

1. **A seat is not a connection.** Players are typed in by the host at setup and have no device,
   no socket, no session token. Do NOT try to reuse the per-device `players` dict keyed by
   client_id — that is the one-phone-per-player model and it will fight you at every turn.
2. **Privacy is phase-scoped and physical.** There is a single viewer, so per-seat payload scoping
   is meaningless, but secrets still only travel during the private reveal phase. The UI's reveal
   gate stops shoulder-surfing while that phase is active; face-up table phases should not carry
   secrets at all.

The turn engine is deliberately index-free in its public surface: callers pass the seat list and
get seat ids back, so a seat leaving mid-game can't silently shift whose turn it is.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from engine_common import clean_text

# A pass-and-play game needs enough people that passing is meaningful.
MIN_SEATS = 3
MAX_SEATS = 12
MAX_SEAT_NAME = 24

# Seat ids are generated, never client-supplied: the host types names, and two guests are allowed
# to share one (families do). Names are therefore NOT unique keys — ids are.
_SEAT_ID_RE = re.compile(r"^s[0-9]+$")


def seat_id(index: int) -> str:
    return f"s{index}"


def sanitize_seat_name(raw: Any, fallback_index: int) -> str:
    """Clean a host-typed name, falling back to a positional label rather than empty.

    An empty seat label would render a pass screen reading "Pass the phone to" with nothing after
    it — the one screen in the whole game that must be unambiguous.
    """
    name = clean_text(raw, MAX_SEAT_NAME)
    return name or f"Player {fallback_index + 1}"


def build_seats(raw_names: Any, raw_emojis: Any = None) -> list[dict]:
    """Turn host-typed names into seats. Truncates at MAX_SEATS; never raises on junk input."""
    names = raw_names if isinstance(raw_names, list) else []
    emojis = raw_emojis if isinstance(raw_emojis, list) else []
    seats: list[dict] = []
    for i, raw in enumerate(names[:MAX_SEATS]):
        emoji = ""
        if i < len(emojis):
            emoji = clean_text(emojis[i], 8)
        seats.append({"id": seat_id(i), "name": sanitize_seat_name(raw, i), "emoji": emoji})
    return seats


def can_start(seats: list[dict], min_seats: int = MIN_SEATS) -> bool:
    return isinstance(seats, list) and min_seats <= len(seats) <= MAX_SEATS


def seat_ids(seats: list[dict]) -> list[str]:
    return [s["id"] for s in seats if isinstance(s, dict) and "id" in s]


def find_seat(seats: list[dict], sid: str) -> Optional[dict]:
    return next((s for s in seats if s.get("id") == sid), None)


def seat_name(seats: list[dict], sid: str) -> str:
    seat = find_seat(seats, sid)
    return seat.get("name", "") if seat else ""


# --- Turn order -------------------------------------------------------------------------------
#
# Turn order is stored as an explicit list of seat ids plus the id whose turn it is — NOT an
# integer index into the seat list. With an index, removing a seat silently changes whose turn it
# is (everyone after the removed seat shifts by one), which in a game built on "pass to the named
# person" is a correctness bug that looks like a UI glitch.


def create_turn_order(seats: list[dict]) -> dict:
    order = seat_ids(seats)
    return {"order": order, "current": order[0] if order else "", "completed_rounds": 0}


def current_turn(turn: dict) -> str:
    return turn.get("current", "")


def advance_turn(turn: dict) -> dict:
    """Move to the next seat, counting a completed round when we wrap."""
    order = turn.get("order") or []
    if not order:
        turn["current"] = ""
        return turn
    try:
        pos = order.index(turn.get("current", ""))
    except ValueError:
        # Current seat vanished (removed mid-round) — restart at the top rather than stall.
        turn["current"] = order[0]
        return turn
    nxt = pos + 1
    if nxt >= len(order):
        turn["completed_rounds"] = int(turn.get("completed_rounds", 0)) + 1
        turn["current"] = order[0]
    else:
        turn["current"] = order[nxt]
    return turn


def remove_from_turn_order(turn: dict, sid: str) -> dict:
    """Drop a seat mid-game (someone left the table) without disturbing whose turn it is."""
    order = turn.get("order") or []
    if sid not in order:
        return turn
    was_current = turn.get("current") == sid
    pos = order.index(sid)
    order.remove(sid)
    turn["order"] = order
    if not order:
        turn["current"] = ""
    elif was_current:
        # The removed seat held the turn: hand it to whoever now occupies that position,
        # wrapping to the start. Advancing instead would skip a player.
        turn["current"] = order[pos % len(order)]
    return turn


def insert_into_turn_order(turn: dict, sid: str) -> dict:
    """Add a latecomer to the end of the rotation."""
    order = turn.get("order") or []
    if sid not in order:
        order.append(sid)
        turn["order"] = order
        if not turn.get("current"):
            turn["current"] = sid
    return turn


def rounds_completed(turn: dict) -> int:
    return int(turn.get("completed_rounds", 0))


# --- Vote tallying ----------------------------------------------------------------------------


def tally_votes(votes: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for accused in votes.values():
        if accused:
            counts[accused] = counts.get(accused, 0) + 1
    return counts


def strict_majority(counts: dict[str, int], voter_count: int) -> str:
    """Seat id with a STRICT majority (> half the voters), else "".

    Strict majority, not plurality, on purpose: in a hidden-role game a plurality means the table
    was genuinely split, and convicting on a 2-of-5 plurality feels arbitrary to everyone who
    didn't vote for it. A tie or a split returns "" so the caller can treat it as "nobody caught".
    """
    if not counts or voter_count <= 0:
        return ""
    leader, top = max(counts.items(), key=lambda kv: (kv[1], kv[0]))
    return leader if top * 2 > voter_count else ""
