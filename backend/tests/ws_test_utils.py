"""Shared websocket helpers for socket tests.

Starlette's `TestClient` websocket `receive_json()` blocks **forever** if the expected message
never arrives. A single missing broadcast therefore doesn't fail a test — it hangs the whole
pytest run until an outer timeout kills it, and the failure output points at the timeout rather
than at the message that never came.

`test_e2e.py` grew a threaded, wall-clock-bounded receive to fix exactly this (BACKLOG: "Legacy
sync E2E WebSocket timeout hardening"). It lived there privately, so the next socket suite hit the
same hang from scratch. This module is that helper, extracted, so no future suite pays for it again.
"""
import queue
import threading
import time

DEFAULT_WS_RECEIVE_TIMEOUT = 5.0


def receive_json_with_timeout(ws, *, timeout=DEFAULT_WS_RECEIVE_TIMEOUT, context="websocket"):
    """Receive one TestClient websocket message with a real wall-clock timeout.

    Runs the blocking receive on a daemon thread so a message that never arrives raises instead
    of wedging the run.
    """
    result_queue: queue.Queue = queue.Queue(maxsize=1)

    def _receive():
        try:
            result_queue.put(("ok", ws.receive_json()))
        except Exception as exc:  # noqa: BLE001 — surfaced as a TimeoutError below
            result_queue.put(("error", exc))

    threading.Thread(target=_receive, daemon=True).start()
    try:
        status, value = result_queue.get(timeout=timeout)
    except queue.Empty:
        # UNBLOCK THE READER BEFORE RAISING. The thread above is parked inside
        # `ws.receive_json()` and will stay there for the life of the process, which keeps the
        # websocket — and therefore its anyio blocking portal — alive. The next test then opens a
        # SECOND portal, and both instrumented captures of this flake (2026-08-09 and 2026-08-18 CI)
        # showed exactly that: two `asyncio-portal-*` threads coexisting at stall time. Closing the
        # socket makes receive_json raise, the thread exits, and the portal is released — so a single
        # timeout can no longer seed the condition for the next one.
        try:
            ws.close()
        except Exception:  # noqa: BLE001 — best effort; the caller's `with` will close again
            pass
        raise TimeoutError(
            f"Timed out after {timeout:.1f}s waiting for {context}. "
            f"live threads={threading.active_count()} "
            f"({', '.join(sorted(th.name for th in threading.enumerate()))})"
        )
    if status == "error":
        raise TimeoutError(f"Connection closed while waiting for {context}: {value}")
    return value


def recv_until(ws, msg_type, *, max_messages=50, timeout=DEFAULT_WS_RECEIVE_TIMEOUT):
    """Drain messages until `msg_type` arrives.

    The error names every message type actually seen. That list is the single most useful piece of
    debugging information for a socket test, because the usual cause of failure is a lifecycle
    message (PING, GAME_STARTING) arriving before the one being waited on.
    """
    deadline = time.monotonic() + timeout
    seen_types = []
    last_message = None
    while time.monotonic() < deadline and len(seen_types) < max_messages:
        remaining = deadline - time.monotonic()
        data = receive_json_with_timeout(
            ws,
            timeout=min(DEFAULT_WS_RECEIVE_TIMEOUT, max(0.1, remaining)),
            context=f"{msg_type} after {seen_types or 'no messages'}",
        )
        last_message = data
        seen_types.append(str(data.get("type")))
        if data.get("type") == msg_type:
            return data
    raise TimeoutError(
        f"Never received {msg_type} after {len(seen_types)} messages "
        f"within {timeout:.1f}s; seen={seen_types}; last={last_message}"
    )
