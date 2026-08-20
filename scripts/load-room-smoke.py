#!/usr/bin/env python3
"""Bounded LocalPlay room-load smoke.

Creates N rooms, connects one organizer and M players per room, holds the sockets briefly, then
cancels every room through the organizer socket. It is intentionally a smoke harness, not a soak
test: it answers "can this target accept a burst of live rooms and clean them up?" without spending
sparks or leaving runtime rooms behind.

Examples:
    backend/venv/bin/python scripts/load-room-smoke.py --target local --rooms 8 --players 3
    backend/venv/bin/python scripts/load-room-smoke.py --api https://gamesapi-gamma.revelryapp.me --rooms 12 --players 4
    backend/venv/bin/python scripts/load-room-smoke.py --target gamma --rooms 4 --players 3 --reconnect-check
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx
import websockets
from websockets.exceptions import ConnectionClosed


TARGETS = {
    "local": "http://127.0.0.1:9100",
    "gamma": "https://gamesapi-gamma.revelryapp.me",
    "prod": "https://gamesapi.revelryapp.me",
}

DEFAULT_ORIGINS = {
    "local": "http://127.0.0.1:9200",
    "gamma": "https://gamesapi-gamma.revelryapp.me",
    "prod": "https://games.revelryapp.me",
}


@dataclass
class PlayerHandle:
    nickname: str
    client_id: str
    session_token: str
    socket: Any


@dataclass
class RoomHandle:
    code: str
    token: str
    organizer: Any
    players: list[PlayerHandle]


def ws_base(api_base: str) -> str:
    parsed = urlparse(api_base)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "", "", "", ""))


async def recv_until(ws: Any, msg_type: str, *, timeout: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while time.monotonic() < deadline:
        remaining = max(0.1, deadline - time.monotonic())
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        data = json.loads(raw)
        seen.append(str(data.get("type")))
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(f"never received {msg_type}; seen={seen}")


async def verify_room_gone(api: str, origin: str, code: str) -> bool:
    """Probe a cancelled room code. Missing rooms send an ERROR before closing."""
    base = ws_base(api)
    probe_id = f"load-probe-{uuid.uuid4().hex[:8]}"
    probe = await websockets.connect(f"{base}/ws/{code}/{probe_id}", origin=origin)
    try:
        raw = await asyncio.wait_for(probe.recv(), timeout=5.0)
        data = json.loads(raw)
        if data.get("type") == "ERROR" and "room not found" in str(data.get("message", "")).lower():
            return True
        print(f"WARN cleanup probe for {code} saw unexpected message: {data}")
        return False
    except asyncio.TimeoutError:
        print(f"WARN cleanup probe for {code} was accepted without Room not found")
        return False
    except ConnectionClosed as exc:
        print(f"WARN cleanup probe for {code} closed before Room not found: {exc!r}")
        return False
    finally:
        await probe.close()


async def create_room(client: httpx.AsyncClient, api: str, index: int) -> tuple[str, str]:
    device_id = str(uuid.uuid4())
    response = await client.post(
        f"{api}/room/create",
        json={
            "game_type": "two_truths",
            "time_limit": 30,
            "two_truths_config": {"game_title": f"QA Load Room {index}"},
        },
        headers={"X-Device-ID": device_id},
    )
    response.raise_for_status()
    data = response.json()
    return data["room_code"], data["organizer_token"]


async def open_room(api: str, origin: str, code: str, token: str, players: int, index: int) -> RoomHandle:
    base = ws_base(api)
    organizer = await websockets.connect(f"{base}/ws/{code}/load-org-{index}?organizer=true", origin=origin)
    await organizer.send(json.dumps({"type": "AUTH", "token": token}))
    await recv_until(organizer, "ROOM_CREATED")

    player_sockets = []
    try:
        for player_idx in range(players):
            ws = await websockets.connect(f"{base}/ws/{code}/load-p{index}-{player_idx}", origin=origin)
            await ws.send(json.dumps({
                "type": "JOIN",
                "nickname": f"QA-{index}-{player_idx}",
                "avatar": "🙂",
            }))
            joined = await recv_until(ws, "JOINED_ROOM")
            player_sockets.append(PlayerHandle(
                nickname=f"QA-{index}-{player_idx}",
                client_id=f"load-p{index}-{player_idx}",
                session_token=str(joined.get("session_token", "")),
                socket=ws,
            ))
        return RoomHandle(code=code, token=token, organizer=organizer, players=player_sockets)
    except Exception:
        try:
            await organizer.send(json.dumps({"type": "CANCEL_GAME"}))
            await recv_until(organizer, "ROOM_CLOSED", timeout=5.0)
        except Exception as exc:  # noqa: BLE001 - preserve the original smoke failure
            print(f"WARN cleanup cancel failed for partially opened room {code}: {exc}")
        for player in player_sockets:
            await player.socket.close()
        await organizer.close()
        raise


async def reconnect_one_player(api: str, origin: str, room: RoomHandle, delay: float) -> bool:
    if not room.players:
        return True
    player = room.players[0]
    if not player.session_token:
        print(f"WARN {room.code} player {player.nickname} did not receive a session token; skipping reconnect probe")
        return False

    await player.socket.close()
    await asyncio.sleep(max(0.0, delay))

    base = ws_base(api)
    reconnect_id = f"{player.client_id}-reconnect-{uuid.uuid4().hex[:6]}"
    ws = await websockets.connect(f"{base}/ws/{room.code}/{reconnect_id}", origin=origin)
    await ws.send(json.dumps({
        "type": "JOIN",
        "nickname": player.nickname,
        "avatar": "🙂",
        "session_token": player.session_token,
    }))
    reconnected = await recv_until(ws, "RECONNECTED", timeout=8.0)
    if reconnected.get("state") != "LOBBY":
        print(f"WARN {room.code} reconnect returned state={reconnected.get('state')!r}, expected LOBBY")
        await ws.close()
        return False

    room.players[0] = PlayerHandle(
        nickname=player.nickname,
        client_id=reconnect_id,
        session_token=str(reconnected.get("session_token") or player.session_token),
        socket=ws,
    )
    return True


async def cancel_room(api: str, origin: str, room: RoomHandle) -> bool:
    acked_or_closed = False
    try:
        await room.organizer.send(json.dumps({"type": "CANCEL_GAME"}))
        try:
            await recv_until(room.organizer, "ROOM_CLOSED", timeout=5.0)
            acked_or_closed = True
        except ConnectionClosed:
            acked_or_closed = True
        except Exception as exc:  # noqa: BLE001 - followed by an explicit cleanup probe
            print(f"WARN cancel ack failed for {room.code}: {exc!r}")
    except Exception as exc:  # noqa: BLE001 - cleanup is best effort, reported by caller
        print(f"WARN cancel send failed for {room.code}: {exc!r}")
    finally:
        for player in room.players:
            await player.socket.close()
        await room.organizer.close()

    gone = await verify_room_gone(api, origin, room.code)
    if not gone:
        return False
    if not acked_or_closed:
        print(f"WARN {room.code} was cleaned up but no ROOM_CLOSED ack reached the organizer")
    return True


async def run(
    api: str,
    origin: str,
    rooms: int,
    players: int,
    concurrency: int,
    dwell: float,
    reconnect_check: bool,
    reconnect_delay: float,
) -> int:
    started = time.monotonic()
    handles: list[RoomHandle] = []
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=20.0) as client:
        async def one(index: int) -> RoomHandle:
            async with sem:
                code, token = await create_room(client, api, index)
                return await open_room(api, origin, code, token, players, index)

        try:
            results = await asyncio.gather(*(one(i + 1) for i in range(rooms)), return_exceptions=True)
            failures = [result for result in results if isinstance(result, Exception)]
            handles = [result for result in results if isinstance(result, RoomHandle)]
            if failures:
                for failure in failures[:5]:
                    print(f"FAIL room open failed: {failure}")
                if len(failures) > 5:
                    print(f"FAIL plus {len(failures) - 5} more room open failures")
                return 1

            total_clients = rooms * (players + 1)
            print(f"PASS opened {rooms} rooms / {total_clients} sockets against {api} (origin {origin})")
            if reconnect_check:
                reconnect_results = await asyncio.gather(
                    *(reconnect_one_player(api, origin, handle, reconnect_delay) for handle in handles),
                    return_exceptions=True,
                )
                reconnect_failures = [
                    result
                    for result in reconnect_results
                    if isinstance(result, Exception) or result is not True
                ]
                if reconnect_failures:
                    for failure in reconnect_failures[:5]:
                        print(f"FAIL reconnect probe failed: {failure!r}")
                    return 1
                print(f"PASS reconnected one lobby player in each of {len(handles)} room(s)")
            await asyncio.sleep(dwell)
        finally:
            cleanup_results = await asyncio.gather(
                *(cancel_room(api, origin, handle) for handle in handles),
                return_exceptions=True,
            )

    elapsed = time.monotonic() - started
    cleanup_failures = [
        result
        for result in cleanup_results
        if isinstance(result, Exception) or result is not True
    ] if handles else []
    if len(handles) == rooms and not cleanup_failures:
        print(f"PASS cleaned up {len(handles)} rooms in {elapsed:.1f}s")
        return 0

    if cleanup_failures:
        print(f"FAIL {len(cleanup_failures)} room cleanup probe(s) failed in {elapsed:.1f}s")
        return 1

    print(f"FAIL cleaned up {len(handles)} opened rooms after a partial run in {elapsed:.1f}s")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="LocalPlay bounded room-load smoke")
    parser.add_argument("--target", choices=sorted(TARGETS), default="local")
    parser.add_argument("--api", default="", help="Override API base URL")
    parser.add_argument("--origin", default="", help="WebSocket Origin header; defaults to the target frontend")
    parser.add_argument("--rooms", type=int, default=8)
    parser.add_argument("--players", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--dwell", type=float, default=2.0)
    parser.add_argument(
        "--reconnect-check",
        action="store_true",
        help="Close and reconnect one lobby player per room before cleanup.",
    )
    parser.add_argument("--reconnect-delay", type=float, default=0.2)
    args = parser.parse_args()

    api = (args.api or TARGETS[args.target]).rstrip("/")
    if args.origin:
        origin = args.origin.rstrip("/")
    elif args.api and api == "http://127.0.0.1:9100":
        origin = DEFAULT_ORIGINS["local"]
    else:
        origin = DEFAULT_ORIGINS.get(args.target, api).rstrip("/")
    rooms = max(1, args.rooms)
    players = max(0, args.players)
    concurrency = max(1, min(args.concurrency, rooms))
    return asyncio.run(run(
        api,
        origin,
        rooms,
        players,
        concurrency,
        max(0.0, args.dwell),
        args.reconnect_check,
        max(0.0, args.reconnect_delay),
    ))


if __name__ == "__main__":
    raise SystemExit(main())
