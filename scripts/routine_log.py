#!/usr/bin/env python3
"""
Shared structured log for the trading routine.

All host-side scripts import this so one file captures the full picture:
  IBKR fetch  →  DB sync  →  Briefing  →  Git backup

Log file: ~/logs/routine.log
In Docker: /app/logs/routine.log  (same file via volume mount)

Format:
  [2026-06-24T20:05:01Z] [START  ] ══ RUN START  source=cron
  [2026-06-24T20:05:02Z] [PHASE  ] ── IBKR Fetch
  [2026-06-24T20:05:45Z] [OK     ] account_state.json + ibkr_positions.json ✓
  [2026-06-24T20:05:46Z] [OK     ] positions: 42 updated, 0 no IBKR match
  [2026-06-24T20:06:31Z] [END    ] ══ RUN END    status=OK  elapsed=90s
"""

from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path.home() / "logs" / "routine.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB — trim oldest half when exceeded


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(tag: str, msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_BYTES:
        lines = LOG_PATH.read_text(errors="replace").splitlines()
        LOG_PATH.write_text("\n".join(lines[len(lines) // 2:]) + "\n")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{_ts()}] [{tag:<7}] {msg}\n")


def run_start(source: str) -> None:
    _write("START  ", "══════════════════════════════════════════════════")
    _write("START  ", f"RUN START  source={source}")


def run_end(status: str, elapsed: float | None = None) -> None:
    dur = f"  elapsed={elapsed:.0f}s" if elapsed is not None else ""
    _write("END    ", f"RUN END    status={status}{dur}")
    _write("END    ", "══════════════════════════════════════════════════")


def phase(name: str) -> None:
    _write("PHASE  ", f"── {name}")


def ok(msg: str) -> None:
    _write("OK     ", msg)


def info(msg: str) -> None:
    _write("INFO   ", msg)


def warn(msg: str) -> None:
    _write("WARN   ", msg)


def error(msg: str) -> None:
    _write("ERROR  ", msg)
