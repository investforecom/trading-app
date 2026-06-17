#!/bin/bash
# Routine A — VPS runner.
# Runs the morning briefing via claude -p (IBKR MCP available headlessly),
# then immediately loads the output into Postgres so Metabase is live.
#
# Cron (5am AEST = 19:00 UTC, Tue–Sat):
#   0 19 * * 2-6 /home/char/workspace/dashboard/routine_a.sh >> /home/char/logs/routine_a.log 2>&1
#
# sync.sh remains at 19:30 UTC as a fallback (idempotent loader run — safe to double-run).
set -euo pipefail

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
