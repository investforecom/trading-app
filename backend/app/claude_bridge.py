"""
Client for the host-side Thesis bridge (scripts/thesis_bridge.py). Sends one
JSON request, waits for one JSON response. The bridge runs `claude -p` on the
host under the user's existing Claude Code subscription — this container
never talks to the billed Anthropic API directly.
"""

import json
import socket

SOCKET_PATH = "/tmp/trading-sockets/thesis-bridge.sock"
TIMEOUT = 170  # claude -p with web search can take a while; bridge itself times out at 150s


def call_bridge(task: str, **fields) -> dict:
    payload = json.dumps({"task": task, **fields}, default=str).encode()

    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(TIMEOUT)
    try:
        conn.connect(SOCKET_PATH)
    except FileNotFoundError:
        raise RuntimeError("Thesis bridge is not running — start scripts/thesis_bridge.py on the host")
    except ConnectionRefusedError:
        raise RuntimeError("Thesis bridge socket exists but nothing is listening")

    try:
        conn.sendall(payload)
        conn.shutdown(socket.SHUT_WR)

        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
    finally:
        conn.close()

    if not raw:
        raise RuntimeError("Thesis bridge closed the connection with no response")

    resp = json.loads(raw.decode())
    if "error" in resp:
        raise RuntimeError(resp["error"])
    return resp["result"]
