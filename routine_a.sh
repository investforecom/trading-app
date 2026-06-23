#!/bin/bash
# Routine A — VPS runner.
# Runs the morning briefing via claude -p (IBKR MCP available headlessly),
# then immediately loads the output into Postgres so Metabase is live.
#
# Cron (6:05am AEST = 20:05 UTC, Tue–Sat — 5 min after US EDT market close):
#   5 20 * * 2-6 /home/char/workspace/dashboard/routine_a.sh >> /home/char/logs/routine_a.log 2>&1
#
# Seasonal adjustment needed when clocks change:
#   US EST (Nov–Mar): US close shifts to 21:00 UTC → change to: 5 21 * * 2-6
#   AEDT (Oct–Apr, UTC+11): 6:05 AM AEDT = 19:05 UTC → change to: 5 19 * * 2-6
#
# sync.sh fallback at 20:30 UTC (idempotent — safe to double-run).
set -euo pipefail
export PATH="/home/char/.local/bin:$PATH"
# Unset Claude Code session vars so claude -p runs as a standalone process,
# not a child of any interactive session (avoids hanging when triggered manually).
unset CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_EFFORT

REPO_DIR="/home/char/workspace/trading-routine"
LOADER_DIR="/home/char/workspace/dashboard/loader"
ENV_FILE="/home/char/workspace/dashboard/.env"
LOG_PREFIX="=== $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

echo "$LOG_PREFIX START ==="

# --- Load env vars (POSTGRES_USER, POSTGRES_PASSWORD, etc.) ---
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export PGHOST=127.0.0.1
export PGPORT=5432
export PGDATABASE=trading
export PGUSER="$POSTGRES_USER"
export PGPASSWORD="$POSTGRES_PASSWORD"

# --- Step 1: Pull latest repo ---
echo "→ Pulling trading-routine"
git -C "$REPO_DIR" checkout main
# Stash any local changes (account_state.json written by previous claude -p run,
# position_ai_notes.json etc.) — the routine regenerates them fresh each run.
git -C "$REPO_DIR" stash --include-untracked 2>/dev/null || true
git -C "$REPO_DIR" pull --rebase origin main

# --- Step 2: Run Routine A via claude -p ---
# Allowed tools: read-only IBKR MCP + file tools + web search for market data.
# Order-creation IBKR tools are intentionally excluded.
echo "→ Running Routine A (claude -p)"
cd "$REPO_DIR"

claude -p \
  "Read routine_instructions.md and follow it EXACTLY for this run. \
The instruction file is the single source of truth — do not improvise \
a different format, and do not use any older version of these instructions \
from memory. Use the Discord webhook specified inside that file." \
  --allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_balances,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_positions,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_summary,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_orders,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_trades" \
  --model claude-sonnet-4-6 \
  2>&1

echo "→ claude -p finished (rc=$?)"

# --- Step 3: Load output into Postgres ---
echo "→ Running loader"
cd "$LOADER_DIR"
python3 run.py --repo "$REPO_DIR"

echo "$LOG_PREFIX END ==="
