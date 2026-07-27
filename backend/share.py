"""Shareable result cards (SPEC-SHARE-CARD).

Mints short tokens for a minimal end-of-game result snapshot and renders an OG-unfurl HTML page.
Dynamic OG *text* (winner + score) + a static branded image. No PII beyond a chosen nickname
(sanitized + escaped).

Snapshots are persisted to the DB (`db.save/get_share_snapshot`) so a shared link survives a process
restart and works across instances, with an in-memory write-through cache for the hot path. DB access
is best-effort: if it fails (e.g. Supabase before the share_snapshots migration is applied), the module
degrades to memory-only — exactly the old behaviour — and never 500s a share.
"""
import html
import logging
import re
import secrets
import time

import config
import db

logger = logging.getLogger(__name__)

# token -> {game_type, winner, top_score, player_count, created_at} — hot-path cache over the DB.
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
    snap = {
        "game_type": _sanitize(game_type, 24),
        "winner": _sanitize(winner, 24),
        "top_score": max(0, int(top_score or 0)),
        "player_count": max(0, int(player_count or 0)),
        "created_at": int(time.time()),
    }
    _snapshots[token] = snap
    try:
        db.save_share_snapshot(token, snap["game_type"], snap["winner"],
                               snap["top_score"], snap["player_count"], snap["created_at"])
    except Exception:  # noqa: BLE001 — durability is a bonus; never fail a share on DB trouble
        logger.debug("share snapshot DB persist failed; using in-memory only", exc_info=True)
    return token


def get_snapshot(token: str) -> dict | None:
    snap = _snapshots.get(token)
    if snap is None:
        # Cache miss (e.g. after a restart or on another instance) — try the durable store.
        try:
            snap = db.get_share_snapshot(token)
        except Exception:  # noqa: BLE001 — degrade to "not found", never 500 a share
            logger.debug("share snapshot DB read failed", exc_info=True)
            snap = None
        if snap is not None:
            _snapshots[token] = snap
    if not snap:
        return None
    if int(time.time()) - int(snap["created_at"]) > config.SHARE_TTL_SECONDS:
        _snapshots.pop(token, None)
        return None
    # Stamp the token on so render_html can build the per-result image URL. The DB row doesn't
    # carry it back (it's the lookup key), and the memory cache is keyed by it too.
    if not snap.get("token"):
        snap = {**snap, "token": token}
    return snap


def render_html(snap: dict | None) -> str:
    """Render a self-contained OG-unfurl page. Unknown/expired token → generic branded page."""
    app_url = config.PUBLIC_BASE_URL or "/"
    # Per-result card when we know the result; the static brand image otherwise. The image is most
    # of the tappable area in WhatsApp/iMessage, so a generic logo reads as an ad while a card
    # naming the winner reads as something that happened.
    if snap and snap.get("token"):
        og_image = f"{config.PUBLIC_BASE_URL}/share/game/{snap['token']}/image.png" if config.PUBLIC_BASE_URL else ""
    else:
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
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
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
