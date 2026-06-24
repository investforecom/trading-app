#!/usr/bin/env python3
"""
CLI trigger for the IBKR bridge socket.

Connects to the running bridge daemon, waits for completion, and exits 0 on
success. Used by the daily cron so the routine doesn't need to manage the bridge
process itself.
"""

import json
import socket
import sys

SOCKET_PATH = "/tmp/trading-sockets/ibkr-refresh.sock"


def main():
    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(SOCKET_PATH)
    except FileNotFoundError:
        print("ERROR: bridge socket not found — is ibkr_bridge.py running?", file=sys.stderr)
        sys.exit(1)
    except ConnectionRefusedError:
        print("ERROR: bridge not listening on socket", file=sys.stderr)
        sys.exit(1)

    buf = b""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
            lines = buf.split(b"\n")
            buf = lines[-1]
            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    if ev.get("phase"):
                        print(f"[{ev['phase']}]", flush=True)
                    if ev.get("log"):
                        print(ev["log"], flush=True)
                    if ev.get("error"):
                        print(f"ERROR: {ev['error']}", file=sys.stderr)
                        sys.exit(1)
                    if ev.get("done"):
                        print("Refresh complete ✓", flush=True)
                        sys.exit(0)
                except json.JSONDecodeError:
                    if line:
                        print(line.decode("utf-8", errors="replace"), flush=True)
    finally:
        conn.close()

    sys.exit(0)


if __name__ == "__main__":
    main()
