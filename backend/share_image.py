"""Per-result OG share image (SPEC-SHARE-CARD).

Renders a 1200x630 PNG naming the winner, so a shared link unfurls as *something that happened*
rather than a generic logo. In WhatsApp/iMessage the image is most of the tappable area, so this is
the difference between a preview that reads as an ad and one that reads as a result.

Design constraints that shaped this module:

- **Pillow only.** It is already in requirements.txt; cairosvg is not installed, and adding a
  system-library-backed dependency for one image would be a poor trade. So the card is drawn with
  primitives rather than rasterised from SVG.
- **No font files.** The prod container is python:3.12-slim with essentially no system fonts, and
  bundling a TTF means shipping a binary plus its licence. `ImageFont.load_default(size=...)`
  (Pillow >= 10.1) returns a real scalable FreeTypeFont from Pillow's own bundled face, so it works
  identically on macOS and in the container. A nicer system font is used when one exists.
- **Never raise.** Crawlers fetch OG images once, eagerly, and do not retry; a 500 means the link
  unfurls bare forever. Every entry point here is wrapped by the caller, and `render_card` itself
  avoids anything that can fail on odd input.
"""
from __future__ import annotations

import io
import logging
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Standard OG/Twitter summary_large_image canvas. Both platforms crop toward the centre, so
# nothing load-bearing goes near the edges.
WIDTH, HEIGHT = 1200, 630
MARGIN = 72

# Velvet theme (frontend/src/index.css) — kept in sync by hand; this is the only place the palette
# is duplicated outside the CSS, because the renderer can't read CSS variables.
BG = (10, 6, 18)            # --bg
PANEL = (26, 15, 42)        # --paper
INK = (248, 235, 217)       # --ink
INK_MUTE = (150, 140, 130)  # --ink-mute, flattened (no alpha compositing needed)
ACCENT = (255, 46, 122)     # --accent
MINT = (109, 255, 230)      # --olive

# Preferred faces if the host happens to have them; falls back to Pillow's bundled face.
_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Futura.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


@lru_cache(maxsize=8)
def _font(size: int) -> ImageFont.FreeTypeFont:
    """A scalable font at `size`. Cached because loading a face per draw call is wasteful."""
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001 — missing/unsupported face is expected, try the next
            continue
    # Pillow's own bundled scalable face. Present in the slim container, so this is the real
    # production path, not just a safety net.
    return ImageFont.load_default(size=size)


def _fit(draw: ImageDraw.ImageDraw, text: str, size: int, max_width: int) -> ImageFont.FreeTypeFont:
    """Shrink until `text` fits `max_width`.

    A long nickname is the one piece of user-controlled text on the card. Without this it would
    render off-canvas — and the crop would silently hide the winner's name, which is the whole point
    of the image.
    """
    while size > 20:
        font = _font(size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    return _font(20)


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_card(*, winner: str, top_score: int, player_count: int, game_label: str) -> bytes:
    """Render the result card and return PNG bytes.

    Inputs are already sanitized by share.py, but everything is defensively coerced because this
    output is public and must not depend on a caller getting it right.
    """
    winner = _truncate(winner, 24) or "Someone"
    game_label = _truncate(game_label, 28) or "party game"
    try:
        score = max(0, int(top_score))
    except (TypeError, ValueError):
        score = 0
    try:
        players = max(0, int(player_count))
    except (TypeError, ValueError):
        players = 0

    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # Inset panel + accent spine: cheap structure that reads as designed rather than as a
    # screenshot of text on black.
    draw.rounded_rectangle(
        (MARGIN // 2, MARGIN // 2, WIDTH - MARGIN // 2, HEIGHT - MARGIN // 2),
        radius=28, fill=PANEL,
    )
    draw.rectangle((MARGIN, MARGIN + 8, MARGIN + 8, HEIGHT - MARGIN - 8), fill=ACCENT)

    x = MARGIN + 44
    max_w = WIDTH - x - MARGIN

    draw.text((x, MARGIN + 14), game_label.upper(), font=_font(30), fill=MINT)

    winner_font = _fit(draw, winner, 108, max_w)
    draw.text((x, MARGIN + 74), winner, font=winner_font, fill=INK)

    draw.text((x, MARGIN + 216), "WON", font=_font(44), fill=ACCENT)

    score_text = f"{score:,} points"
    draw.text((x, MARGIN + 292), score_text, font=_fit(draw, score_text, 60, max_w), fill=INK)

    if players:
        detail = f"{players} player{'' if players == 1 else 's'}"
        draw.text((x, MARGIN + 372), detail, font=_font(34), fill=INK_MUTE)

    footer = "Revelry Games · start your own game night"
    draw.text((x, HEIGHT - MARGIN - 44), footer, font=_font(30), fill=INK_MUTE)

    buf = io.BytesIO()
    # optimize=True is worth it: OG images are fetched by crawlers over other people's networks,
    # and this keeps the card well under the ~1MB some clients quietly refuse.
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
