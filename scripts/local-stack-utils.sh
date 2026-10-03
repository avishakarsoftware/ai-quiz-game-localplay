#!/usr/bin/env bash
# Shared safety checks for disposable browser-test stacks. Caller supplies PY and ports.
assert_stack_ports_available() {
    "$PY" - "$BACKEND_PORT" "$FRONTEND_PORT" <<'PY'
import errno
import socket
import sys

probes = []
try:
    for raw_port in sys.argv[1:]:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError(f"invalid port: {raw_port}")
        probe = socket.socket()
        probes.append(probe)
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
            probe.listen(1)
        except OSError as error:
            if error.errno == errno.EADDRINUSE:
                message = f"port {port} is in use; choose different test-stack ports"
            else:
                message = f"cannot probe port {port}: {error.strerror}"
            raise ValueError(message) from None
except ValueError as error:
    print(f"[stack] {error}. Existing processes were left running.", file=sys.stderr)
    sys.exit(1)
finally:
    for probe in probes:
        probe.close()
PY
}

cleanup_stack() {
    # Both server jobs exec their final process, so these are the PIDs we own.
    for pid in "$FRONTEND_PID" "$BACKEND_PID"; do
        if [[ -n "$pid" ]]; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
    rm -rf "$WORK_DIR"
}
