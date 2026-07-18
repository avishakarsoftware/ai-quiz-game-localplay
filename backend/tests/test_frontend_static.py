"""Static-page resolution for the backend-served SPA.

The app stores require a working Privacy Policy URL and Support URL, and review actually
visits them. Those pages are static files in `frontend/public/` (shipped to `dist/`), reached
as extensionless paths: /privacy and /support.

The IONOS frontend resolves those via Apache MultiViews. The backend-served SPA previously did
not: it matched exact files only, so /privacy fell through to the SPA catch-all and returned
**200 with index.html** -- a healthy-looking response that renders an empty shell. These tests
pin the MultiViews-style fallback added to `_frontend_file_response`, and the traversal guard.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def spa_client(tmp_path, monkeypatch):
    """A TestClient whose frontend dist is a temp dir we control."""
    import main

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><body>SPA SHELL</body></html>")
    (dist / "privacy.html").write_text("<html><body>PRIVACY POLICY CONTENT</body></html>")
    (dist / "support.html").write_text("<html><body>SUPPORT PAGE CONTENT</body></html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")

    # A file outside the dist root, for the traversal test.
    (tmp_path / "secret.html").write_text("TOP SECRET")

    monkeypatch.setattr(main, "FRONTEND_DIST_DIR", dist)
    monkeypatch.setattr(main, "_has_frontend_build", lambda: True)
    return TestClient(main.app)


def test_extensionless_privacy_serves_the_real_page(spa_client):
    res = spa_client.get("/privacy")
    assert res.status_code == 200
    assert "PRIVACY POLICY CONTENT" in res.text
    assert "SPA SHELL" not in res.text  # the bug: a 200 that was really index.html


def test_extensionless_support_serves_the_real_page(spa_client):
    res = spa_client.get("/support")
    assert res.status_code == 200
    assert "SUPPORT PAGE CONTENT" in res.text
    assert "SPA SHELL" not in res.text


def test_explicit_html_extension_still_works(spa_client):
    # The native apps link to privacy.html relatively; that path must keep working.
    res = spa_client.get("/privacy.html")
    assert res.status_code == 200
    assert "PRIVACY POLICY CONTENT" in res.text


def test_unknown_route_still_falls_back_to_the_spa(spa_client):
    res = spa_client.get("/some/app/route")
    assert res.status_code == 200
    assert "SPA SHELL" in res.text


def test_missing_asset_still_404s(spa_client):
    res = spa_client.get("/assets/nope.js")
    assert res.status_code == 404


def test_dotdot_traversal_is_rejected_before_the_html_lookup(spa_client):
    """`../secret` never reaches the .html branch -- the pre-existing root check returns first."""
    import main

    response = main._frontend_file_response("../secret")
    assert getattr(response, "path", None) == main._frontend_index_path()


def test_symlinked_html_page_outside_the_root_is_not_served(spa_client, tmp_path):
    """The reachable traversal case for the .html lookup: a symlink inside dist.

    A `../` path is already rejected by the root check that runs before this branch, so the
    only way to reach it with an escaping target is a symlink in dist whose name resolves
    outside the root. `.resolve()` follows the link, so the guard is what stops it.
    """
    import main

    dist = main.FRONTEND_DIST_DIR
    try:
        (dist / "leak.html").symlink_to(tmp_path / "secret.html")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")

    response = main._frontend_file_response("leak")
    assert getattr(response, "path", None) == main._frontend_index_path(), (
        "a symlinked .html resolving outside the frontend root must not be served"
    )


def test_extensionless_lookup_does_not_invent_pages(spa_client):
    # Only serves <path>.html when that file actually exists.
    res = spa_client.get("/not-a-real-page")
    assert res.status_code == 200
    assert "SPA SHELL" in res.text
