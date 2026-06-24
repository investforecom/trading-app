#!/bin/bash
# Daily routine — runs after US market close (20:05 UTC = 6:05 AM AEST).
#
# Flow:
#   1. Trigger bridge → IBKR fetch → sync_positions.py → DB (port 5432)
#   2. Generate daily briefing via claude -p (reads DB, writes briefing_log/)
#   3. Git push trading-routine as backup (NO git pull — DB is source of truth)
#   4. Discord notification
#
# Cron: 5 20 * * 2-6 /home/char/workspace/trading-app/scripts/daily_routine.sh >> /home/char/logs/daily_routine.log 2>&1
set -euo pipefail
export PATH="/home/char/.local/bin:$PATH"
unset CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_EFFORT

SCRIPTS_DIR="/home/char/workspace/trading-app/scripts"
ROUTINE_DIR="/home/char/workspace/trading-routine"
LOG_PREFIX="=== $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
CLAUDE="/home/char/.local/bin/claude"

echo "$LOG_PREFIX START ==="

# ── Step 1: IBKR refresh via bridge → DB ────────────────────────────────────
echo "→ Triggering IBKR refresh"
if python3 "$SCRIPTS_DIR/refresh_trigger.py"; then
    echo "→ IBKR refresh complete"
else
    echo "ERROR: IBKR refresh failed — aborting routine" >&2
    exit 1
fi

# ── Step 2: Daily briefing via claude -p ─────────────────────────────────────
echo "→ Generating daily briefing"
cd "$ROUTINE_DIR"
"$CLAUDE" -p \
    "Read routine_instructions.md and follow it EXACTLY for this run.
The instruction file is the single source of truth — do not improvise
a different format, and do not use any older version of these instructions
from memory. Use the Discord webhook specified inside that file." \
    --allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_balances,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_positions,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_summary,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_orders,\
mcp__claude_ai_Interactive_Brokers_IBKR__get_account_trades" \
    --model claude-sonnet-4-6 \
    2>&1 || echo "WARNING: briefing generation failed (non-fatal)"

echo "→ Briefing step done"

# ── Step 3: Git backup push (no pull) ────────────────────────────────────────
echo "→ Git backup push"
cd "$ROUTINE_DIR"
git add -A
git diff --cached --quiet && echo "  nothing to commit" || \
    git commit -m "Auto-backup $(date -u +%Y-%m-%d)" 2>&1
git push origin main 2>&1 || echo "  git push failed (non-fatal)"

echo "$LOG_PREFIX END ==="
