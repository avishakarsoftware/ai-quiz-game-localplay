"""Per-result OG share image (SPEC-SHARE-CARD).

The governing constraint: crawlers fetch an OG image ONCE, eagerly, and never retry. A 500 means the
link unfurls bare forever, so most of these tests are about degrading rather than failing.
"""
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import share
import share_image
from main import app


client = TestClient(app)


def _mint(game_type="quiz", winner="Priya", top_score=980, players=4) -> str:
    return share.create_snapshot(game_type, winner, top_score, players)


# --- renderer ---

def test_renders_a_valid_png_at_the_og_canvas_size():
    png = share_image.render_card(winner="Priya", top_score=980, player_count=4, game_label="AI Quiz")
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.size == (share_image.WIDTH, share_image.HEIGHT) == (1200, 630)


def test_works_with_no_system_fonts_which_is_the_production_path(monkeypatch):
    """The prod container (python:3.12-slim) has essentially no system fonts. Pillow's bundled
    scalable face must carry it, or the card renders only on a developer's Mac."""
    monkeypatch.setattr(share_image, "_FONT_CANDIDATES", ())
    share_image._font.cache_clear()
    try:
        png = share_image.render_card(winner="Priya", top_score=10, player_count=3, game_label="Drawing")
        assert Image.open(io.BytesIO(png)).size == (1200, 630)
    finally:
        share_image._font.cache_clear()


def test_a_very_long_nickname_still_fits_the_canvas():
    """The nickname is the one piece of user-controlled text. If it overflows, the crop hides the
    winner's name — which is the entire point of the image."""
    png = share_image.render_card(
        winner="Bartholomew Fitzgerald The Third Of Somewhere",
        top_score=1234567, player_count=12, game_label="Who's Most Likely To",
    )
    assert Image.open(io.BytesIO(png)).size == (1200, 630)


@pytest.mark.parametrize("winner", ["", "   ", None])
def test_missing_winner_falls_back_to_someone(winner):
    png = share_image.render_card(winner=winner, top_score=0, player_count=0, game_label="AI Quiz")
    assert Image.open(io.BytesIO(png)).size == (1200, 630)


@pytest.mark.parametrize("score,players", [("not-a-number", "nope"), (-5, -2), (None, None)])
def test_garbage_numbers_do_not_raise(score, players):
    """Inputs are sanitized upstream, but this output is public and must not depend on that."""
    png = share_image.render_card(winner="Ada", top_score=score, player_count=players, game_label="Quiz")
    assert Image.open(io.BytesIO(png)).size == (1200, 630)


def test_card_stays_small_enough_for_chat_clients():
    """Some clients quietly refuse large OG images; keep well under ~1MB."""
    png = share_image.render_card(winner="Priya", top_score=980, player_count=4, game_label="Party Poker")
    assert len(png) < 500_000


def test_the_card_is_not_a_blank_rectangle():
    """A silent font failure would still produce a correctly-sized image. Compare against an
    empty canvas so 'renders' means 'has content drawn on it'."""
    png = share_image.render_card(winner="Priya", top_score=980, player_count=4, game_label="AI Quiz")
    rendered = Image.open(io.BytesIO(png)).convert("RGB")
    blank = Image.new("RGB", rendered.size, share_image.BG)
    assert rendered.tobytes() != blank.tobytes()
    # And it uses more than just the background + panel: text colours must be present.
    colours = {c for _, c in rendered.getcolors(maxcolors=100000)}
    assert share_image.ACCENT in colours, "accent spine/WON label missing"
    assert share_image.MINT in colours, "game label missing"


# --- endpoint ---

def test_endpoint_serves_a_png_for_a_live_token():
    token = _mint()
    res = client.get(f"/share/game/{token}/image.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(res.content)).size == (1200, 630)


def test_endpoint_sets_immutable_cache_headers():
    """A snapshot never changes once minted, and every recipient's chat client refetches this."""
    token = _mint()
    res = client.get(f"/share/game/{token}/image.png")
    assert "max-age=86400" in res.headers["cache-control"]
    assert "immutable" in res.headers["cache-control"]


def test_unknown_token_redirects_to_the_static_image_rather_than_404ing():
    res = client.get("/share/game/does-not-exist/image.png", follow_redirects=False)
    assert res.status_code == 302
    assert "og-image.png" in res.headers["location"]


def test_a_render_failure_degrades_to_the_static_image(monkeypatch):
    """The single most important behaviour here: a crawler gets one shot, so a broken renderer must
    not turn into a permanently bare unfurl."""
    token = _mint()

    def boom(**_kwargs):
        raise RuntimeError("Pillow exploded")

    monkeypatch.setattr(share_image, "render_card", boom)
    res = client.get(f"/share/game/{token}/image.png", follow_redirects=False)
    assert res.status_code == 302
    assert "og-image.png" in res.headers["location"]


def test_endpoint_never_returns_5xx_for_hostile_tokens():
    for token in ["../../etc/passwd", "%00", "a" * 500, "<script>"]:
        res = client.get(f"/share/game/{token}/image.png", follow_redirects=False)
        assert res.status_code < 500, f"{token!r} produced {res.status_code}"


# --- html integration ---

def test_html_points_og_image_at_the_per_result_card(monkeypatch):
    monkeypatch.setattr(share.config, "PUBLIC_BASE_URL", "https://gamesapi.revelryapp.me")
    token = _mint(winner="Ada", top_score=700)
    html_out = share.render_html(share.get_snapshot(token))
    assert f"/share/game/{token}/image.png" in html_out
    assert 'property="og:image:width" content="1200"' in html_out
    assert 'property="og:image:height" content="630"' in html_out


def test_html_falls_back_to_the_brand_image_for_an_unknown_token(monkeypatch):
    monkeypatch.setattr(share.config, "PUBLIC_BASE_URL", "https://gamesapi.revelryapp.me")
    html_out = share.render_html(None)
    assert "/og-image.png" in html_out
    assert "/image.png" not in html_out.replace("og-image.png", "")


def test_game_label_never_leaks_a_raw_game_type():
    """A card reading "would_you_rather" would look broken to a recipient."""
    token = _mint(game_type="would_you_rather")
    res = client.get(f"/share/game/{token}/image.png")
    assert res.status_code == 200  # rendered, not redirected — the label resolved
