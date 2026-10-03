"""Disposable browser stacks must never terminate an existing development server."""
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("script,prefix", [
    ("e2e-local-stack.sh", "E2E"),
    ("visual-regression.sh", "VISUAL"),
    ("dev-local.sh", "DEV"),
])
def test_occupied_port_refuses_stack_without_touching_listener(script, prefix):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        env = {**os.environ, f"{prefix}_BACKEND_PORT": str(port), "LOCALPLAY_PYTHON": sys.executable}
        argument = "start" if script == "dev-local.sh" else "true"
        result = subprocess.run(["bash", str(ROOT / "scripts" / script), argument],
                                env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "Existing processes were left running" in result.stderr
        # An actual TCP exchange proves the listener still works after refusal.
        with socket.create_connection(("127.0.0.1", port), timeout=1) as client:
            connection, _ = listener.accept()
            with connection:
                client.sendall(b"still-running")
                assert connection.recv(32) == b"still-running"


def test_dev_stop_refuses_a_reused_pid(tmp_path):
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (tmp_path / "backend.pid").write_text(str(process.pid))
        (tmp_path / "backend.started").write_text("an old process start time")
        result = subprocess.run(["bash", str(ROOT / "scripts/dev-local.sh"), "stop"],
                                env={**os.environ, "DEV_PID_DIR": str(tmp_path)},
                                capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PID is stale or unverified" in result.stdout
        assert process.poll() is None, "stop killed an unrelated process that reused a saved PID"
    finally:
        process.terminate()
        process.wait(timeout=5)
