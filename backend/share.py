"""Shareable result cards (SPEC-SHARE-CARD).

Mints short tokens for a minimal end-of-game result snapshot and renders an OG-unfurl HTML page.
v1: dynamic OG *text* (winner + score) + a static branded image; snapshots are in-memory with TTL +
max-count eviction (mirrors the quiz store). No PII beyond a chosen nickname (sanitized + escaped).
"""
import html
import re
import secrets
import time

import config

# token -> {game_type, winner, top_score, player_count, created_at}
_snapshots: dict[str, dict] = {}

_PRETTY_GAME = {
    "quiz": "AI Quiz", "wmlt": "Who's Most Likely To", "drawing": "Drawing",
}


def _sanitize(text: str, max_len: int = 40) -> str:
    """Strip HTML tags + control chars; clamp length. Output is still html.escaped at render time."""
    text = re.sub(r"<[^>]+>", "", str(text or ""))
    text = re.sub(r"[\x00-\x1f\x7f]", "", text)
    return text.strip()[:max_len]


def _evict() -> None:
    now = time.time()
    expired = [t for t, s in _snapshots.items() if now - s["created_at"] > config.SHARE_TTL_SECONDS]
    for t in expired:
        _snapshots.pop(t, None)
    if len(_snapshots) >= config.MAX_SHARE_SNAPSHOTS:
        # Drop oldest until under cap.
        for t, _ in sorted(_snapshots.items(), key=lambda kv: kv[1]["created_at"]):
            if len(_snapshots) < config.MAX_SHARE_SNAPSHOTS:
                break
            _snapshots.pop(t, None)


def create_snapshot(game_type: str, winner: str, top_score: int, player_count: int) -> str:
    """Store a result snapshot, return its share token."""
    _evict()
    token = secrets.token_urlsafe(9)
    _snapshots[token] = {
        "game_type": _sanitize(game_type, 24),
        "winner": _sanitize(winner, 24),
        "top_score": max(0, int(top_score or 0)),
        "player_count": max(0, int(player_count or 0)),
        "created_at": time.time(),
    }
    return token


def get_snapshot(token: str) -> dict | None:
    snap = _snapshots.get(token)
    if not snap:
        return None
    if time.time() - snap["created_at"] > config.SHARE_TTL_SECONDS:
        _snapshots.pop(token, None)
        return None
    return snap


def render_html(snap: dict | None) -> str:
    """Render a self-contained OG-unfurl page. Unknown/expired token → generic branded page."""
    app_url = config.PUBLIC_BASE_URL or "/"
    og_image = f"{config.PUBLIC_BASE_URL}/og-image.png" if config.PUBLIC_BASE_URL else ""

    if snap:
        pretty = _PRETTY_GAME.get(snap["game_type"], "party game")
        winner = snap["winner"] or "Someone"
        title = f"{winner} won with {snap['top_score']} in Revelry Games!"
        desc = f"{snap['player_count']} players • {pretty}. Start your own AI game night."
    else:
        title = "Revelry Games — AI party games"
        desc = "Spin up an AI quiz on any topic and play together — everyone joins from their phone."

    # Escape once, here, at the render boundary (winner/pretty are raw above by design).
    title_e = html.escape(title)
    desc_e = html.escape(desc)
    og_image_tag = f'<meta property="og:image" content="{html.escape(og_image)}">' if og_image else ""
    tw_image_tag = f'<meta name="twitter:image" content="{html.escape(og_image)}">' if og_image else ""
    app_url_e = html.escape(app_url)

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_e}</title>
<meta property="og:type" content="website">
<meta property="og:title" content="{title_e}">
<meta property="og:description" content="{desc_e}">
<meta property="og:url" content="{app_url_e}">
{og_image_tag}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_e}">
<meta name="twitter:description" content="{desc_e}">
{tw_image_tag}
<meta http-equiv="refresh" content="2;url={app_url_e}">
<style>body{{font-family:system-ui,sans-serif;background:#1a1120;color:#fff;display:flex;
min-height:100vh;align-items:center;justify-content:center;text-align:center;margin:0;padding:24px}}
a.btn{{display:inline-block;margin-top:16px;padding:12px 24px;border-radius:999px;
background:#ff2d95;color:#fff;text-decoration:none;font-weight:700}}</style>
</head><body><div>
<h1>{title_e}</h1><p>{desc_e}</p>
<a class="btn" href="{app_url_e}">Play Revelry Games →</a>
</div></body></html>"""
