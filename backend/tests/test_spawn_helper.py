"""spawn() — the fire-and-forget task helper in socket_manager (REVIEW-2026-08 A3).

Before it, four call sites did a bare `asyncio.create_task(...)` and dropped the result:
the asyncio event loop holds tasks only weakly, so those could be garbage-collected
mid-flight, and any exception they raised surfaced only at GC time, if ever — a crashed
question timer or auto-caller loop just silently stopped its feature.
"""
import asyncio
import logging
import re

import pytest

import socket_manager


@pytest.mark.asyncio
async def test_spawn_logs_crash_with_task_name(caplog):
    async def boom():
        raise RuntimeError("timer exploded")

    with caplog.at_level(logging.ERROR, logger="socket_manager"):
        task = socket_manager.spawn(boom(), name="question-timer:TEST42")
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)  # let the done-callback run

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "question-timer:TEST42" in joined, "crash must be attributable to a named task"
    assert "timer exploded" in joined


@pytest.mark.asyncio
async def test_spawn_cancellation_is_not_an_error(caplog):
    async def sleeper():
        await asyncio.sleep(60)

    with caplog.at_level(logging.ERROR, logger="socket_manager"):
        task = socket_manager.spawn(sleeper(), name="cancelled-task")
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)

    assert not caplog.records, "cancellation is the normal stop path, never an ERROR"


@pytest.mark.asyncio
async def test_spawn_holds_a_strong_reference_until_done():
    started = asyncio.Event()
    release = asyncio.Event()

    async def worker():
        started.set()
        await release.wait()

    task = socket_manager.spawn(worker(), name="ref-test")
    await started.wait()
    assert task in socket_manager._background_tasks, (
        "pending task must be strongly referenced — bare create_task results can be "
        "garbage-collected mid-flight (the pre-fix state of the mc-complete sites)"
    )
    release.set()
    await task
    await asyncio.sleep(0)
    assert task not in socket_manager._background_tasks, "reference must be dropped when done"


def test_no_bare_create_task_left_in_socket_manager():
    """The guard that keeps the fix fixed: every background task in socket_manager goes
    through spawn(). A new bare asyncio.create_task reintroduces the silent-crash and
    GC-mid-flight hazards this file exists to prevent."""
    from pathlib import Path
    text = (Path(socket_manager.__file__)).read_text()
    bare = [
        (i, line.strip())
        for i, line in enumerate(text.splitlines(), 1)
        if re.search(r"asyncio\.create_task\(", line)
        # the one legitimate call is inside spawn() itself
        and "task = asyncio.create_task(coro, name=name)" not in line
        # prose mentions (spawn()'s own docstring backtick-quotes the phrase)
        and "`" not in line and not line.strip().startswith("#")
    ]
    assert not bare, (
        f"bare asyncio.create_task in socket_manager.py: {bare} — use spawn(coro, name=...) "
        "so the task is strongly referenced and its crash is logged."
    )
