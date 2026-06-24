#!/usr/bin/env python3
"""
CLI trigger for the IBKR bridge socket.

Connects to the running bridge daemon, waits for completion, and exits 0 on
success. Used by the daily cron so the routine doesn't need to manage the
bridge process itself.

Writes RUN START / RUN END markers to routine.log so the log captures the
full cron run including all phases handled inside the bridge.
"""

import json
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import routine_log as rlog

SOCKET_PATH = "/tmp/trading-sockets/ibkr-refresh.sock"


def main():
    source = os.environ.get("ROUTINE_SOURCE", "cron")
    rlog.run_start(source)
    t0 = time.monotonic()

    try:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.connect(SOCKET_PATH)
    except FileNotFoundError:
        rlog.error("bridge socket not found — is ibkr_bridge.py running?")
        rlog.run_end("ERROR", time.monotonic() - t0)
        sys.exit(1)
    except ConnectionRefusedError:
        rlog.error("bridge not listening on socket")
        rlog.run_end("ERROR", time.monotonic() - t0)
        sys.exit(1)

    buf = b""
    exit_code = 1
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
                        rlog.error(ev["error"])
                        print(f"ERROR: {ev['error']}", file=sys.stderr)
                        exit_code = 1
                    if ev.get("done"):
                        print("IBKR refresh complete ✓", flush=True)
                        exit_code = 0
                except json.JSONDecodeError:
                    if line:
                        print(line.decode("utf-8", errors="replace"), flush=True)
    finally:
        conn.close()

    # RUN END is written here only for the IBKR+DB-sync portion.
    # daily_routine.sh writes a second END after briefing+git complete.
    if source == "manual":
        rlog.run_end("OK" if exit_code == 0 else "ERROR", time.monotonic() - t0)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
