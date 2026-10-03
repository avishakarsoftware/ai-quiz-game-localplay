"""Replay must stage a lobby for free and charge exactly once when the game starts."""
from contextlib import ExitStack
import uuid

import pytest
from fastapi.testclient import TestClient

import config
import db
import main
from socket_manager import socket_manager as manager
from ws_test_utils import recv_until


@pytest.fixture(autouse=True)
def fund_test_wallet():
    # Exercise the real economy, unlike the shared fixture's successful-spend stubs.
    yield


@pytest.fixture(autouse=True)
def rooms():
    manager.rooms.clear()
    old_origins = manager.allowed_origins
    original_quizzes = set(main.quizzes)
    manager.allowed_origins = []
    yield
    for room in manager.rooms.values():
        for task_name in ('timer_task', '_organizer_cleanup_task', 'mafia_timer_task'):
            task = getattr(room, task_name, None)
            if task:
                task.cancel()
    manager.rooms.clear()
    manager.allowed_origins = old_origins
    for content_id in set(main.quizzes) - original_quizzes:
        main.quizzes.pop(content_id, None)
        main.content_owners.pop(content_id, None)
        main.pending_generation_charges.pop(content_id, None)


def seed_quiz(wallet):
    content_id = str(uuid.uuid4())
    main.quizzes[content_id] = {
        'quiz_title': 'Replay billing',
        'questions': [{'id': 1, 'text': 'One?', 'options': ['A', 'B'], 'answer_index': 0}],
    }
    main.content_owners[content_id] = wallet
    return content_id


def set_balance(wallet, balance):
    db.get_or_create_wallet(wallet)
    current = db.get_wallet_balance(wallet)
    if current > balance:
        db.debit_tokens(wallet, current - balance, 'test_drain')
    elif current < balance:
        db.credit_tokens(wallet, balance - current, 'test_fund')


def open_game(stack, wallet):
    client = TestClient(main.app)
    response = client.post('/room/create', headers={'X-Device-ID': wallet},
                           json={'quiz_id': seed_quiz(wallet), 'time_limit': 30})
    assert response.status_code == 200, response.text
    code = response.json()['room_code']
    org = stack.enter_context(client.websocket_connect(f'/ws/{code}/org?organizer=true'))
    org.send_json({'type': 'AUTH', 'token': response.json()['organizer_token']})
    recv_until(org, 'ROOM_CREATED')
    player = stack.enter_context(client.websocket_connect(f'/ws/{code}/player'))
    player.send_json({'type': 'JOIN', 'nickname': 'Ada'})
    recv_until(player, 'JOINED_ROOM')
    return code, org, player


@pytest.mark.parametrize('grace', [False, True])
def test_replay_charges_once_per_started_game(monkeypatch, grace):
    monkeypatch.setattr(config, 'PARTY_GRACE_HOURS', 6 if grace else 0)
    monkeypatch.setattr(config, 'PARTY_GRACE_MAX_ROOMS', 2)
    wallet = str(uuid.uuid4())
    set_balance(wallet, 0 if grace else 2 * config.COST_ROOM)
    with ExitStack() as stack:
        code, org, player = open_game(stack, wallet)
        for game_number in (1, 2):
            org.send_json({'type': 'START_GAME'})
            recv_until(org, 'GAME_STARTING')
            recv_until(player, 'GAME_STARTING')
            assert db.get_wallet_balance(wallet) == (0 if grace else (2 - game_number) * config.COST_ROOM)
            assert db.party_grace_state(wallet)[1] == (game_number if grace else 0)
            org.send_json({'type': 'NEXT_QUESTION'})
            recv_until(org, 'QUESTION')
            recv_until(player, 'QUESTION')
            org.send_json({'type': 'END_QUIZ'})
            recv_until(org, 'PODIUM')
            recv_until(player, 'PODIUM')
            if game_number == 1:
                org.send_json({'type': 'RESET_ROOM', 'game_type': 'quiz', 'content_id': seed_quiz(wallet)})
                recv_until(org, 'ROOM_RESET')
                recv_until(player, 'ROOM_RESET')
                assert manager.rooms[code].state == 'LOBBY'
                assert db.get_wallet_balance(wallet) == (0 if grace else config.COST_ROOM)
                assert db.party_grace_state(wallet)[1] == (1 if grace else 0)


def test_reset_with_no_room_budget_stages_lobby_but_start_is_paywalled():
    wallet = str(uuid.uuid4())
    set_balance(wallet, 0)
    with ExitStack() as stack:
        code, org, player = open_game(stack, wallet)
        manager.rooms[code].state = 'PODIUM'
        org.send_json({'type': 'RESET_ROOM', 'game_type': 'quiz', 'content_id': seed_quiz(wallet)})
        recv_until(org, 'ROOM_RESET')
        recv_until(player, 'ROOM_RESET')
        org.send_json({'type': 'START_GAME'})
        recv_until(org, 'INSUFFICIENT_SPARKS')
        assert manager.rooms[code].state == 'LOBBY'
        assert manager.rooms[code].connected_player_count() == 1
        assert db.get_wallet_balance(wallet) == 0


def test_generated_reset_needs_only_generation_cost_during_grace(monkeypatch):
    monkeypatch.setattr(config, 'PARTY_GRACE_HOURS', 6)
    wallet = str(uuid.uuid4())
    set_balance(wallet, config.COST_GENERATE)
    with ExitStack() as stack:
        code, org, player = open_game(stack, wallet)
        manager.rooms[code].state = 'PODIUM'
        next_id = seed_quiz(wallet)
        main.pending_generation_charges[next_id] = wallet
        try:
            org.send_json({'type': 'RESET_ROOM', 'game_type': 'quiz', 'content_id': next_id})
            recv_until(org, 'ROOM_RESET')
            recv_until(player, 'ROOM_RESET')
            assert db.get_wallet_balance(wallet) == 0
            assert next_id not in main.pending_generation_charges
            assert db.party_grace_state(wallet) == (0, 0)
            org.send_json({'type': 'START_GAME'})
            recv_until(org, 'GAME_STARTING')
            assert db.party_grace_state(wallet)[1] == 1
        finally:
            main.pending_generation_charges.pop(next_id, None)


def test_odd_question_reset_keeps_guests_and_clears_old_content():
    wallet = str(uuid.uuid4())
    set_balance(wallet, config.COST_ROOM)
    with ExitStack() as stack:
        code, org, player = open_game(stack, wallet)
        for index in (2, 3):
            guest = stack.enter_context(TestClient(main.app).websocket_connect(f'/ws/{code}/p{index}'))
            guest.send_json({'type': 'JOIN', 'nickname': f'Guest {index}'})
            recv_until(guest, 'JOINED_ROOM')
        manager.rooms[code].state = 'PODIUM'
        org.send_json({'type': 'RESET_ROOM', 'game_type': 'odd_question'})
        assert recv_until(org, 'ROOM_RESET')['game_type'] == 'odd_question'
        recv_until(player, 'ROOM_RESET')
        assert manager.rooms[code].content_id == ''
        assert db.get_wallet_balance(wallet) == config.COST_ROOM
        org.send_json({'type': 'START_GAME'})
        assert recv_until(org, 'GAME_STARTING')['game_type'] == 'odd_question'
        assert db.get_wallet_balance(wallet) == 0
