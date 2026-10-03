"""Fault injection for the harness: every created room/socket must reach cleanup."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

import pytest

spec = importlib.util.spec_from_file_location('load_room_smoke', Path(__file__).resolve().parents[2] / 'scripts/load-room-smoke.py')
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)


class Wire:
    def __init__(self, failure=''):
        self.failure = failure
        self.failed = False
        self.alive = set()
        self.sockets = []

    def fail(self, stage):
        if stage and stage == self.failure and not self.failed:
            self.failed = True
            raise RuntimeError(f'injected {stage}')

    async def create(self, client, api, index):
        self.fail('create' if index == 2 else '')
        code = f'ROOM{index}'
        self.alive.add(code)
        return code, 'token'

    async def connect(self, url, **kwargs):
        parts = urlparse(url).path.split('/')
        code, client_id = parts[-2:]
        if client_id.startswith('load-org'):
            self.fail('organizer_connect')
        socket = Socket(self, code, client_id)
        self.sockets.append(socket)
        return socket


class Socket:
    def __init__(self, wire, code, client_id):
        self.wire, self.code, self.client_id = wire, code, client_id
        self.closed = False
        self.pending = {'type': 'ERROR', 'message': 'Room not found'} if code not in wire.alive else {'type': 'CONNECTED'}
        self.recv_stage = ''

    async def send(self, raw):
        data = json.loads(raw)
        if data['type'] == 'AUTH':
            initial = self.client_id.startswith('load-org')
            self.wire.fail('auth_send' if initial else '')
            self.recv_stage = 'auth_ack' if initial else ''
            self.pending = {'type': 'ROOM_CREATED'}
        elif data['type'] == 'JOIN':
            reconnect = '-reconnect-' in self.client_id
            self.wire.fail('reconnect_send' if reconnect else 'join_send')
            self.recv_stage = 'reconnect_ack' if reconnect else 'join_ack'
            self.pending = {'type': 'RECONNECTED' if reconnect else 'JOINED_ROOM', 'state': 'LOBBY', 'session_token': 'player-token'}
        elif data['type'] == 'CANCEL_GAME':
            self.wire.fail('cancel_send')
            if self.wire.failure != 'cleanup_probe':
                self.wire.alive.discard(self.code)
            self.pending = {'type': 'ROOM_CLOSED'}
            self.recv_stage = ''

    async def recv(self):
        self.wire.fail(self.recv_stage)
        return json.dumps(self.pending)

    async def close(self):
        self.closed = True


@pytest.mark.parametrize('failure', [
    '', 'create', 'organizer_connect', 'auth_send', 'auth_ack', 'join_send', 'join_ack',
    'reconnect_send', 'reconnect_ack',
    'cancel_send',
])
def test_all_resources_are_cleaned_even_when_open_or_reconnect_fails(monkeypatch, capsys, failure):
    wire = Wire(failure)
    monkeypatch.setattr(smoke, 'create_room', wire.create)
    monkeypatch.setattr(smoke.websockets, 'connect', wire.connect)
    status = asyncio.run(smoke.run('http://test', 'http://test', 2, 1, 1, 0, True, 0))
    assert status == (0 if failure in ('', 'cancel_send') else 1)
    assert not wire.alive, 'even a room whose first socket failed must be cancelled'
    assert all(socket.closed for socket in wire.sockets), 'unacknowledged sockets must also close'
    assert 'cleaned up' in capsys.readouterr().out


def test_cleanup_failure_is_reported_alongside_original_failure(monkeypatch, capsys):
    wire = Wire('cleanup_probe')
    original_create = wire.create

    async def create(client, api, index):
        if index == 2:
            raise RuntimeError('room open failure')
        return await original_create(client, api, index)

    monkeypatch.setattr(smoke, 'create_room', create)
    monkeypatch.setattr(smoke.websockets, 'connect', wire.connect)
    status = asyncio.run(smoke.run('http://test', 'http://test', 2, 1, 1, 0, False, 0))
    assert status == 1
    output = capsys.readouterr().out
    assert 'FAIL room open failed' in output
    assert 'FAIL 1 room cleanup probe(s)' in output
    assert all(socket.closed for socket in wire.sockets)
