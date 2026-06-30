#!/usr/bin/env python3
"""
Host-side IBKR bridge — Unix socket server.

Listens on /tmp/trading-sockets/ibkr-refresh.sock (mounted into the
api container as the same path via docker-compose volume).

When a client connects:
  1. git stash + pull (sync CSVs from GitHub)
  2. claude -p (IBKR MCP) → writes account_state.json + ibkr_positions.json
  3. sync_positions.py (Python, deterministic) → rewrites open_positions.csv
  4. emits {"done": True}

The heavy LLM step is now only 4 MCP calls (~30-60s). Position matching
is deterministic Python (<1s).

AI notes (optional): spawned as a background daemon thread after "done"
is sent. They appear on the NEXT page reload (no blocking).
"""

import json
import os
import subprocess
import socket
import sys
import threading
from pathlib import Path

_refresh_lock = threading.Lock()

sys.path.insert(0, os.path.dirname(__file__))
import routine_log as rlog

SOCKET_DIR   = "/tmp/trading-sockets"
SOCKET_PATH  = f"{SOCKET_DIR}/ibkr-refresh.sock"
CLAUDE       = os.path.expanduser("~/.local/bin/claude")
WORK_DIR     = os.path.expanduser("~/workspace")
ROUTINE_DIR  = os.path.expanduser("~/workspace/trading-routine")
SCRIPTS_DIR  = os.path.expanduser("~/workspace/trading-app/scripts")
STATE_OUT    = f"{ROUTINE_DIR}/account_state.json"
IBKR_POS_OUT = f"{ROUTINE_DIR}/ibkr_positions.json"
AI_NOTES_OUT = f"{ROUTINE_DIR}/position_ai_notes.json"
CSV_PATH     = f"{ROUTINE_DIR}/open_positions.csv"

# ── STEP 1: IBKR MCP fetch (account data only) ────────────────────────────
# This is the ONLY job of claude -p now. 4 tool calls, done in ~60s.
PROMPT_STEP1 = f"""Account data sync agent. READ-ONLY — never place or modify orders.

Fetch all account data in parallel (all 4 calls at once):
  get_account_summary       → net_liquidation = nav, leverage
  get_account_balances      → total_cash_value = cash (can be negative); note exchange_rate per currency (GBP/USD etc)
  get_account_positions     → full position list; find SGOV market_value; sum daily_pnl in USD (convert GBP/EUR using exchange_rates)
  get_pa_performance_all_periods → 1D period → start_nav = prior_close_nav

Compute:
  deployed_pct  = (nav - cash - sgov) / nav × 100, rounded 2dp
  daily_pnl_pct = daily_pnl / (nav - daily_pnl) × 100, rounded 2dp
  fx_gbp        = GBP/USD exchange rate from get_account_balances (default 1.32 if not found)

Write {STATE_OUT}:
{{
  "date": "YYYY-MM-DD",
  "nav": <float>, "cash": <float>, "sgov": <float>,
  "deployed_pct": <float>, "leverage": <float>, "prior_close_nav": <float>,
  "daily_pnl": <float>, "daily_pnl_pct": <float>, "fx_gbp": <float>
}}

Write {IBKR_POS_OUT} — the raw list from get_account_positions, exactly as returned:
{{"positions": [<list of position objects>]}}

Print one line after each file is written. Done.
"""

# ── STEP 3: AI notes (runs in background after "done") ────────────────────
PROMPT_NOTES = f"""Position notes agent. READ-ONLY — never place or modify orders.

Read {CSV_PATH} (use Read tool). For every row (skip strategy=cash and SGOV):
Write one terse sentence (max 80 chars) adding context the CSV note alone doesn't give.
Focus on ONE of: hold / watch / harvest / trim / review + brief reason.

Rules:
- LDS: harvest if gain ≥70% or fwd_rr <1.5; flag if gain <-20% or fwd_rr <1.5
- LEAP: no stop; flag if gain <-30% or down >2 weeks
- 2x-ETF: flag if pct_nav >5%
- Thematic: flag if gain <-20%
- WheelSP/SC: note assignment proximity relative to strike

Examples: "LDS on track — R/R 2.55x, harvest above +70%" / "Approaching harvest — gain 68%"
          "2x-ETF oversized 6.0% NAV" / "LEAP recovering — thesis intact"

Write {AI_NOTES_OUT} as flat JSON: symbol → note string.
"""

ALLOWED_TOOLS_STEP1 = ",".join([
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_account_summary",
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_account_balances",
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_account_positions",
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_pa_performance_all_periods",
    "Write",
])

ALLOWED_TOOLS_NOTES = "Read,Write"


def emit(conn: socket.socket, obj: dict) -> bool:
    try:
        conn.sendall((json.dumps(obj) + "\n").encode())
        return True
    except (BrokenPipeError, ConnectionResetError):
        return False


CLAUDE_TIMEOUT = 600  # seconds before we kill a hung claude -p (normal runs take ~300-360s)


def _run_claude(prompt: str, allowed_tools: str, max_turns: str, conn: socket.socket | None = None) -> bool:
    """
    Spawn claude -p, stream assistant text back via conn (if provided).
    Returns True on success. Kills the process after CLAUDE_TIMEOUT seconds
    so a zombie/hung claude never holds the refresh lock indefinitely.
    """
    proc = subprocess.Popen(
        [CLAUDE, "--print", "--verbose", "--output-format", "stream-json",
         "--allowedTools", allowed_tools,
         "--max-turns", max_turns,
         prompt],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=WORK_DIR,
    )

    def _kill():
        rlog.error(f"claude -p exceeded {CLAUDE_TIMEOUT}s — killing")
        if conn:
            emit(conn, {"error": f"claude -p timed out after {CLAUDE_TIMEOUT}s"})
        proc.kill()

    timer = threading.Timer(CLAUDE_TIMEOUT, _kill)
    timer.start()
    try:
        done = False
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
                if ev.get("type") == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            text = block["text"].strip()
                            if text and conn and not emit(conn, {"log": text}):
                                proc.terminate()
                                return False
                elif ev.get("type") == "result":
                    done = True
            except json.JSONDecodeError:
                if conn and raw:
                    if not emit(conn, {"log": raw}):
                        proc.terminate()
                        return False

        proc.wait()
        return done or proc.returncode == 0
    finally:
        timer.cancel()


def _run_notes_background():
    """Runs STEP 3 (AI notes) in a background daemon thread — doesn't block refresh."""
    try:
        _run_claude(PROMPT_NOTES, ALLOWED_TOOLS_NOTES, "20", conn=None)
    except Exception:
        pass


def handle(conn: socket.socket):
    if not _refresh_lock.acquire(blocking=False):
        rlog.warn("Refresh already in progress — rejecting duplicate connection")
        emit(conn, {"error": "Refresh already in progress, please wait"})
        conn.close()
        return
    try:
        # ── STEP 1: claude -p → account_state.json + ibkr_positions.json ─
        rlog.phase("IBKR Fetch")
        emit(conn, {"log": "Fetching IBKR account data..."})
        rlog.info("Running claude -p (4 MCP calls)...")
        fetch_ok = _run_claude(PROMPT_STEP1, ALLOWED_TOOLS_STEP1, "10", conn)
        if not fetch_ok:
            rlog.error("IBKR fetch failed — claude -p returned error")
            emit(conn, {"error": "IBKR fetch failed — check claude output"})
            return

        if not Path(STATE_OUT).exists() or not Path(IBKR_POS_OUT).exists():
            rlog.error("claude ran but output files not found")
            emit(conn, {"error": "claude ran but output files not found"})
            return

        rlog.ok("account_state.json + ibkr_positions.json written ✓")
        emit(conn, {"log": "account_state.json + ibkr_positions.json written ✓"})

        # ── STEP 2: sync_positions.py → DB ──────────────────────────────
        rlog.phase("DB Sync")
        emit(conn, {"log": "Updating positions in DB..."})
        result = subprocess.run(
            ["python3", f"{SCRIPTS_DIR}/sync_positions.py"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            emit(conn, {"log": out or "DB updated ✓"})
        else:
            err = result.stderr.strip()[:200]
            rlog.error(f"sync_positions failed: {err}")
            emit(conn, {"log": f"DB sync warning: {err}"})

        # ── STEP 3: AI notes in background (non-blocking) ────────────────
        rlog.phase("AI Notes (background)")
        t = threading.Thread(target=_run_notes_background, daemon=True)
        t.start()
        rlog.info("AI notes spawned in background thread")
        emit(conn, {"log": "AI notes updating in background..."})

        emit(conn, {"log": "Data ready ✓", "done": True})

    except FileNotFoundError:
        rlog.error(f"claude not found at {CLAUDE}")
        emit(conn, {"error": f"claude not found at {CLAUDE}"})
    except Exception as exc:
        rlog.error(str(exc))
        emit(conn, {"error": str(exc)})
    finally:
        _refresh_lock.release()
        conn.close()


def main():
    os.makedirs(SOCKET_DIR, exist_ok=True)
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCKET_PATH)
    os.chmod(SOCKET_PATH, 0o666)
    srv.listen(1)
    print(f"IBKR bridge listening on {SOCKET_PATH}", flush=True)

    while True:
        conn, _ = srv.accept()
        t = threading.Thread(target=handle, args=(conn,), daemon=True)
        t.start()


if __name__ == "__main__":
    main()
