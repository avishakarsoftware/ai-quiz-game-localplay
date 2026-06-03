"""Pure Musical Chairs game logic."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Dict, Iterable, List, Optional


MUSIC_STYLES = ("upbeat", "jazzy", "suspenseful", "retro", "tropical")
MUSIC_MODES = ("builtin", "external")
GAMEPLAY_MODES = ("digital", "physical")
DEFAULT_TRACK_BY_STYLE = {
    "upbeat": "upbeat-confetti",
    "jazzy": "jazzy-lounge",
    "suspenseful": "suspense-tiptoe",
    "retro": "retro-arcade",
    "tropical": "tropical-island",
}


@dataclass(frozen=True)
class MusicalChairsConfig:
    game_title: str = "Musical Chairs"
    gameplay_mode: str = "physical"
    music_mode: str = "builtin"
    music_style: str = "upbeat"
    music_track_id: str = "upbeat-confetti"
    min_music_seconds: int = 60
    max_music_seconds: int = 300
    grab_window_seconds: float = 5.0
    eliminations_per_round: int = 1
    auto_stop: bool = True
    intensity_ramp: bool = True

    def to_dict(self) -> dict:
        return {
            "game_title": self.game_title,
            "gameplay_mode": self.gameplay_mode,
            "music_mode": self.music_mode,
            "music_style": self.music_style,
            "music_track_id": self.music_track_id,
            "min_music_seconds": self.min_music_seconds,
            "max_music_seconds": self.max_music_seconds,
            "grab_window_seconds": self.grab_window_seconds,
            "eliminations_per_round": self.eliminations_per_round,
            "auto_stop": self.auto_stop,
            "intensity_ramp": self.intensity_ramp,
        }


def _clamp(value: int | float, minimum: int | float, maximum: int | float):
    return max(minimum, min(maximum, value))


def validate_config(raw: Optional[dict]) -> dict:
    raw = raw or {}
    title = str(raw.get("game_title") or raw.get("title") or "Musical Chairs").strip()[:120] or "Musical Chairs"
    gameplay_mode = str(raw.get("gameplay_mode") or "physical").strip().lower()
    if gameplay_mode not in GAMEPLAY_MODES:
        gameplay_mode = "physical"
    music_mode = str(raw.get("music_mode") or "builtin").strip().lower()
    if music_mode not in MUSIC_MODES:
        music_mode = "builtin"
    music_style = str(raw.get("music_style") or "upbeat").strip().lower()
    if music_style not in MUSIC_STYLES:
        music_style = "upbeat"
    music_track_id = str(raw.get("music_track_id") or "").strip().lower()[:80]
    if not music_track_id:
        music_track_id = DEFAULT_TRACK_BY_STYLE[music_style]

    try:
        min_music = int(raw.get("min_music_seconds", 60))
    except (TypeError, ValueError):
        min_music = 60
    min_music = int(_clamp(min_music, 5, 600))

    try:
        max_music = int(raw.get("max_music_seconds", 300))
    except (TypeError, ValueError):
        max_music = 300
    max_music = int(_clamp(max_music, min_music + 1, 900))

    try:
        grab_window = float(raw.get("grab_window_seconds", 5))
    except (TypeError, ValueError):
        grab_window = 5.0
    grab_window = float(_clamp(grab_window, 2, 10))

    try:
        eliminations = int(raw.get("eliminations_per_round", 1))
    except (TypeError, ValueError):
        eliminations = 1
    eliminations = int(_clamp(eliminations, 1, 10))

    return MusicalChairsConfig(
        game_title=title,
        gameplay_mode=gameplay_mode,
        music_mode=music_mode,
        music_style=music_style,
        music_track_id=music_track_id,
        min_music_seconds=min_music,
        max_music_seconds=max_music,
        grab_window_seconds=grab_window,
        eliminations_per_round=eliminations,
        auto_stop=bool(raw.get("auto_stop", True)),
        intensity_ramp=bool(raw.get("intensity_ramp", True)),
    ).to_dict()


def total_rounds(player_count: int, eliminations_per_round: int = 1) -> int:
    if player_count <= 1:
        return 0
    return ceil((player_count - 1) / max(1, eliminations_per_round))


def intensity_for_round(round_number: int, total: int, enabled: bool = True) -> float:
    if not enabled or total <= 1:
        return 0.35
    return round(_clamp(0.25 + ((round_number - 1) / max(1, total - 1)) * 0.65, 0.25, 0.95), 2)


def rank_grabs(active_players: Iterable[str], grabs: Dict[str, float], stop_time: float) -> List[dict]:
    ranked: List[dict] = []
    for nickname in active_players:
        grabbed_at = grabs.get(nickname)
        reaction_ms = None if grabbed_at is None else max(0, int(round((grabbed_at - stop_time) * 1000)))
        ranked.append({
            "nickname": nickname,
            "reaction_ms": reaction_ms,
        })
    ranked.sort(key=lambda item: (item["reaction_ms"] is None, item["reaction_ms"] if item["reaction_ms"] is not None else 10**12, item["nickname"].lower()))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def choose_eliminated(active_players: List[str], grabs: Dict[str, float], stop_time: float, eliminations_per_round: int) -> List[str]:
    ranked = rank_grabs(active_players, grabs, stop_time)
    max_eliminations = max(1, min(eliminations_per_round, len(active_players) - 1))
    return [item["nickname"] for item in ranked[-max_eliminations:]]
