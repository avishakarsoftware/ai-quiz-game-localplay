import uuid

import config
import db
from game_rules import validate_catalog_rules, validate_rules
from host_app_catalog_policy import clear_policy_cache, effective_catalog, is_game_allowed
from main import GAME_CATALOG


def setup_function():
    db.init_db()
    clear_policy_cache()


def test_local_missing_policy_uses_static_host_app_catalog():
    games = effective_catalog(GAME_CATALOG, host_app="revelry", environment="local")
    game_ids = {game["id"] for game in games}
    assert {
        "quiz",
        "wmlt",
        "drawing",
        "housie",
        "musical_chairs",
        "bluff",
        "find_someone",
        "chit_pull",
        "mafia",
        "party_quests",
        "would_you_rather",
        "never_have_i_ever",
        "word_association",
        "acronym",
        "photo_clue",
        "poker",
    }.issubset(game_ids)
    assert all(game.get("rules", {}).get("sections") for game in games)


def test_static_launchable_games_have_rules_metadata():
    missing = [
        game["id"]
        for game in GAME_CATALOG
        if game.get("launchable") and game.get("enabled", True) and not game.get("rules", {}).get("summary")
    ]
    assert missing == []
    validate_catalog_rules(GAME_CATALOG)


def test_rules_validator_reports_missing_required_fields():
    errors = validate_rules(
        {"version": 1, "title": "", "summary": "Missing useful bits", "sections": []},
        "broken_game",
    )

    assert "broken_game: rules.title is required" in errors
    assert "broken_game: rules.sections must be a non-empty list" in errors


def test_musical_chairs_is_host_app_quick_startable_in_gamma():
    env = f"test-musical-chairs-{uuid.uuid4().hex}"
    games = effective_catalog(GAME_CATALOG, host_app="revelry", environment=env)
    musical_chairs = next(game for game in games if game["id"] == "musical_chairs")

    assert musical_chairs["launchable"] is True
    assert musical_chairs["can_quick_start"] is True
    assert musical_chairs["can_create_content"] is False
    assert musical_chairs["supports_ai_generation"] is False
    assert musical_chairs["rules"]["title"] == "Musical Chairs Rules"


def test_party_quests_is_host_app_quick_startable_in_gamma():
    env = f"test-party-quests-{uuid.uuid4().hex}"
    games = effective_catalog(GAME_CATALOG, host_app="revelry", environment=env)
    party_quests = next(game for game in games if game["id"] == "party_quests")

    assert party_quests["launchable"] is True
    assert party_quests["can_quick_start"] is True
    assert party_quests["can_create_content"] is False
    assert party_quests["supports_custom_content"] is True
    assert party_quests["supports_ai_generation"] is False


def test_more_standalone_games_are_host_app_quick_startable_in_gamma():
    env = f"test-standalone-quick-start-{uuid.uuid4().hex}"
    games = {game["id"]: game for game in effective_catalog(GAME_CATALOG, host_app="revelry", environment=env)}

    for game_id in (
        "bluff",
        "find_someone",
        "mafia",
        "would_you_rather",
        "never_have_i_ever",
        "word_association",
        "acronym",
        "photo_clue",
        "poker",
    ):
        assert games[game_id]["launchable"] is True
        assert games[game_id]["can_quick_start"] is True
        assert games[game_id]["can_create_content"] is False
        assert games[game_id]["supports_ai_generation"] is False
        assert games[game_id]["rules"]["sections"]

    assert games["photo_clue"]["supports_images"] is True
    assert games["poker"]["supports_custom_content"] is False
    assert games["chit_pull"]["launchable"] is True
    assert games["chit_pull"]["can_quick_start"] is True
    assert games["chit_pull"]["can_create_content"] is True
    assert games["chit_pull"]["can_edit_content"] is True
    assert games["chit_pull"]["supports_ai_generation"] is True
    assert games["chit_pull"]["rules"]["sections"]
    assert games["find_someone"]["checkin_friendly"] is True
    assert games["find_someone"]["can_start_with_first_player"] is True
    assert games["find_someone"]["supports_late_join"] is True
    assert games["find_someone"]["default_for_checkin_supported"] is True
    assert games["find_someone"]["auto_start_on_first_checkin_default"] is True


def test_production_missing_policy_fails_closed():
    games = effective_catalog(
        GAME_CATALOG,
        host_app="revelry",
        environment="production",
        loader=lambda _environment, _host_app: [],
    )
    assert games == []


def test_policy_can_disable_static_game_without_affecting_others():
    env = f"test-disable-{uuid.uuid4().hex}"
    db.upsert_host_app_catalog_flag(env, "revelry", "drawing", {
        "enabled": False,
        "status": "disabled",
    })
    clear_policy_cache()

    games = effective_catalog(GAME_CATALOG, host_app="revelry", environment=env)
    game_ids = {game["id"] for game in games}

    assert "drawing" not in game_ids
    assert {"quiz", "wmlt"}.issubset(game_ids)


def test_policy_intersects_capability_overrides_with_static_catalog():
    env = f"test-capability-{uuid.uuid4().hex}"
    db.upsert_host_app_catalog_flag(env, "revelry", "drawing", {
        "enabled": True,
        "status": "live",
        "capability_overrides": {
            "supports_ai_generation": False,
            "supports_images": True,
        },
    })
    clear_policy_cache()

    drawing = next(
        game for game in effective_catalog(GAME_CATALOG, host_app="revelry", environment=env)
        if game["id"] == "drawing"
    )

    assert drawing["supports_ai_generation"] is False
    assert drawing["supports_images"] is False
    assert drawing["launchable"] is True


def test_policy_allowlists_party_exposure():
    env = f"test-allowlist-{uuid.uuid4().hex}"
    db.upsert_host_app_catalog_flag(env, "revelry", "drawing", {
        "enabled": True,
        "status": "live",
        "allowlist_party_ids": ["party-allowed"],
    })
    clear_policy_cache()

    hidden = effective_catalog(
        GAME_CATALOG,
        host_app="revelry",
        external_container_id="party-blocked",
        environment=env,
    )
    visible = effective_catalog(
        GAME_CATALOG,
        host_app="revelry",
        external_container_id="party-allowed",
        environment=env,
    )

    assert "drawing" not in {game["id"] for game in hidden}
    assert "drawing" in {game["id"] for game in visible}


def test_policy_never_enables_static_unsupported_game():
    env = f"test-unsupported-{uuid.uuid4().hex}"
    db.upsert_host_app_catalog_flag(env, "revelry", "bingo", {
        "enabled": True,
        "status": "live",
    })
    clear_policy_cache()

    games = effective_catalog(GAME_CATALOG, host_app="revelry", environment=env)

    assert "bingo" not in {game["id"] for game in games}
    assert not is_game_allowed(GAME_CATALOG, "bingo", host_app="revelry", environment=env)


def test_route_catalog_uses_policy(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    env = f"test-route-{uuid.uuid4().hex}"
    monkeypatch.setattr(config, "ENVIRONMENT", env)
    db.upsert_host_app_catalog_flag(env, "revelry", "drawing", {
        "enabled": False,
        "status": "disabled",
    })
    clear_policy_cache()

    client = TestClient(app)
    res = client.get("/catalog?host_app=revelry")

    assert res.status_code == 200
    assert "drawing" not in {game["id"] for game in res.json()["games"]}


def test_action_time_policy_rejects_disabled_ai_generation(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    env = f"test-action-{uuid.uuid4().hex}"
    monkeypatch.setattr(config, "ENVIRONMENT", env)
    monkeypatch.setattr(config, "REVELRY_INTEGRATION_SECRET", "test-revelry-secret")
    db.upsert_host_app_catalog_flag(env, "revelry", "drawing", {
        "enabled": True,
        "status": "live",
        "capability_overrides": {"supports_ai_generation": False},
    })
    clear_policy_cache()

    client = TestClient(app)
    link = client.post(
        "/integrations/revelry/party-games-link",
        headers={"Authorization": "Bearer test-revelry-secret"},
        json={
            "external_context": {
                "host_app": "revelry",
                "external_container_type": "party",
                "external_container_id": f"party-{uuid.uuid4().hex}",
                "external_container_title": "Ava Birthday",
            },
            "actor": {
                "external_user_id": "host-1",
                "display_name": "Ava",
                "role": "host",
                "capabilities": ["author_content", "operate_game", "manage_games"],
            },
        },
    )
    assert link.status_code == 200
    token = link.json()["party_games_url"].split("party_games_token=", 1)[1]

    res = client.post(
        "/integrations/revelry/party-games/prompts/generate",
        json={
            "party_games_token": token,
            "game_type": "drawing",
            "prompt": "birthday",
            "difficulty": "medium",
            "num_prompts": 5,
        },
    )

    assert res.status_code == 422
