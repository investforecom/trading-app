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

SOCKET_DIR  = "/tmp/trading-sockets"
SOCKET_PATH = f"{SOCKET_DIR}/ibkr-refresh.sock"
CLAUDE      = os.path.expanduser("~/.local/bin/claude")
WORK_DIR    = os.path.expanduser("~/workspace")
STATE_OUT   = os.path.expanduser("~/workspace/trading-routine/account_state.json")

AI_NOTES_OUT = os.path.expanduser("~/workspace/trading-routine/position_ai_notes.json")

PROMPT = f"""You are a data-sync agent. Fetch current IBKR account data and write it to disk.

Steps:
1. Call get_account_summary     → capture net_liquidation (nav), leverage
2. Call get_account_balances    → capture total_cash_value (USD cash, can be negative).
   Also note exchange_rate for each non-USD currency.
3. Call get_account_positions   → find SGOV position market value (sgov).
   Also sum every position's daily_pnl converted to USD:
   - USD positions: daily_pnl as-is
   - GBP positions: daily_pnl × GBP exchange_rate from balances
   - EUR positions: daily_pnl × EUR exchange_rate from balances
   This sum is daily_pnl (what IBKR shows as "Daily P&L" in the portfolio view).
4. Call get_pa_performance_all_periods → read the 1D period:
   - prior_close_nav = start_nav (yesterday's closing NAV)

Compute:
  deployed_pct = (nav - cash - sgov) / nav * 100, rounded to 2 dp
  daily_pnl_pct = daily_pnl / (nav - daily_pnl) * 100, rounded to 2 dp
    (this matches IBKR's percentage formula exactly)

Write the file {STATE_OUT} with this JSON (no extra text before or after):
{{
  "date": "YYYY-MM-DD",
  "nav": <float>,
  "cash": <float>,
  "sgov": <float>,
  "deployed_pct": <float>,
  "leverage": <float>,
  "prior_close_nav": <float>,
  "daily_pnl": <float rounded to 2dp>,
  "daily_pnl_pct": <float rounded to 2dp>
}}

5. Read the file ~/workspace/trading-routine/open_positions.csv (use the Read tool).
   Cross-reference with live IBKR position data from step 3.
   For every position in the CSV (skip cash/SGOV rows), write one terse interpretation
   sentence (max 80 chars) that adds actionable context the csv_note alone doesn't give.
   Strategy rules to apply:
   - LDS: harvest trigger is gain_pct >= 70% OR fwd_rr < 1.5 → flag "harvest" if met
   - LEAP: single long call, no price stop — flag thesis concern if trending down >2 weeks
   - CDS: has a hard stop below support — flag if gain_pct is negative and falling
   - 2x-ETF: DCA/wheel strategy — flag if pct_nav > 5% (oversized)
   - Thematic: small conviction, flag if materially underwater vs cost
   - WheelSP/WheelSC: note assignment proximity and whether still OTM
   Focus the note on ONE of: hold / watch / harvest / trim / review — plus a brief reason.
   Examples of good notes:
     "LDS on track — R/R 2.55x solid, harvest above +70%"
     "Approaching harvest — gain 68%, watch for R/R flip"
     "2x-ETF oversized at 6.0% NAV — consider partial trim"
     "LEAP recovering — thesis intact, trend turning"
     "CDS stop in play — negative and falling, review"

   Write {AI_NOTES_OUT} as a flat JSON object mapping symbol → note string.
   Use the Write tool or Bash.

Use the Bash tool to write {STATE_OUT}. Print a brief status line for each step.
Do NOT place or modify any orders.
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
        emit(conn, {"log": "Connecting to IBKR via MCP..."})

        proc = subprocess.Popen(
            [CLAUDE, "--print", "--verbose", "--output-format", "stream-json",
             "--allowedTools", ALLOWED_TOOLS,
             "--max-turns", "15",
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
