#!/usr/bin/env python3
"""
Host-side IBKR bridge — Unix socket server.

Listens on /tmp/trading-sockets/ibkr-refresh.sock (mounted into the
api container as the same path via docker-compose volume).

When a client connects, spawns `claude -p <prompt>` on the host (which
has IBKR MCP access), streams the agent output as newline-delimited JSON,
then closes the connection.

Start (run once; survives reboots via systemd ibkr-bridge.service):
    python3 /home/char/workspace/trading-app/scripts/ibkr_bridge.py
"""

import json
import os
import socket
import subprocess
import threading
from pathlib import Path

SOCKET_DIR   = "/tmp/trading-sockets"
SOCKET_PATH  = f"{SOCKET_DIR}/ibkr-refresh.sock"
CLAUDE       = os.path.expanduser("~/.local/bin/claude")
WORK_DIR     = os.path.expanduser("~/workspace")
ROUTINE_DIR  = os.path.expanduser("~/workspace/trading-routine")
STATE_OUT    = f"{ROUTINE_DIR}/account_state.json"
CSV_PATH     = f"{ROUTINE_DIR}/open_positions.csv"
AI_NOTES_OUT = f"{ROUTINE_DIR}/position_ai_notes.json"

PROMPT = f"""Data-sync agent. Fetch IBKR data, update positions CSV, write AI notes. READ-ONLY — never place or modify orders.

== STEP 1: Account snapshot ==
1a. get_account_summary  → nav = net_liquidation, leverage
1b. get_account_balances → cash = total_cash_value (can be negative); note exchange_rate per currency
1c. get_account_positions → save full list; find SGOV market_value; sum daily_pnl (convert GBP/EUR via exchange rates to USD)
1d. get_pa_performance_all_periods → 1D period → prior_close_nav = start_nav

Compute:
  deployed_pct = (nav - cash - sgov) / nav × 100, rounded 2dp
  daily_pnl_pct = daily_pnl / (nav - daily_pnl) × 100, rounded 2dp

Write {STATE_OUT} (Bash or Write tool, no extra text):
{{
  "date": "YYYY-MM-DD (today's date)",
  "nav": <float>, "cash": <float>, "sgov": <float>,
  "deployed_pct": <float>, "leverage": <float>, "prior_close_nav": <float>,
  "daily_pnl": <float>, "daily_pnl_pct": <float>
}}

== STEP 2: Update open_positions.csv with live prices ==
Read {CSV_PATH} using the Read tool. It has columns:
  date,account,symbol,underlying,strategy,theme,structure,qty,cost_basis,current_value,gain_pct,pct_nav,forward_rr,max_value,mgmt_tier,quality_rank,flags,notes

For each CSV row, find the matching IBKR position(s) from step 1c and recompute current_value:

MATCHING RULES (apply in order):
- Stocks (strategy=Thematic, 2x-ETF, or symbol ends in _STK):
    Match IBKR positions where underlying=<CSV underlying> and asset_class=STK.
    current_value = IBKR market_value
- Single-leg options (LEAP, WheelSP, WheelSC, single calls/puts):
    Match by underlying + look for expiry month/year + strike in contract_description.
    current_value = IBKR market_value of the matching leg
- Two-leg spreads (LDS, SWING, CDS — symbol contains two strikes, e.g. ORCL_DEC27_170C270C):
    Find BOTH option legs in IBKR with same underlying + same expiry month/year.
    The long leg has positive qty, short leg has negative qty.
    current_value = sum of both legs' market_values (net spread value)
- No IBKR match found: keep the existing current_value from the CSV (position may have just closed)

COMPUTE for each row (using today's nav from STEP 1):
  gain_pct = (current_value - cost_basis) / abs(cost_basis) × 100, rounded 1dp
  pct_nav  = current_value / nav × 100, rounded 2dp

Write back {CSV_PATH} with ALL original rows, same column order, but updated:
  - date: today's date (from account_state.json)
  - current_value, gain_pct, pct_nav: recomputed
  - ALL other columns: UNCHANGED from original CSV (cost_basis, strategy, theme, forward_rr, notes, flags, etc.)

Use the Write tool. Keep the header row exactly as-is.

== STEP 3: Position AI notes ==
For every position in {CSV_PATH} (skip cash/SGOV), write one terse sentence (max 80 chars) adding context the note alone doesn't give. Focus on ONE of: hold/watch/harvest/trim/review + brief reason.
Rules: LDS harvest ≥70% or fwd_rr <1.5 · LEAP no stop, flag if down >2wk · 2x-ETF flag if pct_nav >5% · Thematic flag if deeply underwater · WheelSP/SC: assignment proximity.
Good examples: "LDS on track — R/R 2.55x, harvest above +70%" / "Approaching harvest — gain 68%" / "2x-ETF oversized 6.0% NAV" / "LEAP recovering — thesis intact"

Write {AI_NOTES_OUT} as flat JSON: symbol → note string.

Print a brief status line after each step.
"""

ALLOWED_TOOLS = ",".join([
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_account_summary",
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_account_balances",
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_account_positions",
    "mcp__claude_ai_Interactive_Brokers_IBKR__get_pa_performance_all_periods",
    "Bash",
    "Write",
    "Read",
])


def emit(conn: socket.socket, obj: dict) -> bool:
    try:
        conn.sendall((json.dumps(obj) + "\n").encode())
        return True
    except (BrokenPipeError, ConnectionResetError):
        return False


def handle(conn: socket.socket):
    try:
        # Pull latest trading-routine repo before fetching IBKR data
        emit(conn, {"log": "Pulling trading-routine repo..."})
        subprocess.run(
            ["git", "-C", ROUTINE_DIR, "stash", "--include-untracked"],
            capture_output=True, timeout=15,
        )
        pull = subprocess.run(
            ["git", "-C", ROUTINE_DIR, "pull", "--rebase", "origin", "main"],
            capture_output=True, text=True, timeout=30,
        )
        if pull.returncode == 0:
            emit(conn, {"log": "Repo up to date ✓"})
        else:
            emit(conn, {"log": f"Git pull warning: {pull.stderr.strip()[:80]}"})

        emit(conn, {"log": "Connecting to IBKR via MCP..."})

        proc = subprocess.Popen(
            [CLAUDE, "--print", "--verbose", "--output-format", "stream-json",
             "--allowedTools", ALLOWED_TOOLS,
             "--max-turns", "30",
             PROMPT],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=WORK_DIR,
        )

        done = False
        for raw in proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
                ev_type = ev.get("type", "")
                if ev_type == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            text = block["text"].strip()
                            if text and not emit(conn, {"log": text}):
                                proc.terminate()
                                return
                elif ev_type == "result":
                    done = True
            except json.JSONDecodeError:
                if not emit(conn, {"log": raw}):
                    proc.terminate()
                    return

        proc.wait()
        if done or proc.returncode == 0:
            emit(conn, {"log": "account_state.json written ✓", "done": True})
        else:
            emit(conn, {"error": f"claude exited {proc.returncode}"})

    except FileNotFoundError:
        emit(conn, {"error": f"claude not found at {CLAUDE}"})
    except Exception as exc:
        emit(conn, {"error": str(exc)})
    finally:
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
