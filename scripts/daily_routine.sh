#!/bin/bash
# Daily routine — runs after US market close.
#
# ── Schedule ──────────────────────────────────────────────────────────────────
# Cron entry (update when clocks change — see table below):
#   5 20 * * 2-6 /home/char/workspace/trading-app/scripts/daily_routine.sh >> /home/char/logs/daily_routine.log 2>&1
#
# Day-of-week note: cron days are UTC. "2-6" = Tue–Sat UTC, which maps to
# Wed–Sun 6:05 AM Sydney — covering the Mon–Fri US market close each week.
#
# ── DST adjustment table ──────────────────────────────────────────────────────
# Period          Sydney     US market close   6:05 AM Sydney    Cron setting
# Apr–Oct         AEST+10    20:00 UTC (EDT)   20:05 UTC         5 20 * * 2-6  ← NOW
# Oct–Nov         AEDT+11    20:00 UTC (EDT)   19:05 UTC         5 19 * * 2-6
# Nov–Apr         AEDT+11    21:00 UTC (EST)   19:05 UTC*        5 19 * * 2-6
#
# * Nov–Apr: 19:05 UTC = 6:05 AM AEDT but US market hasn't closed yet (closes
#   21:00 UTC in EST). Data will be from previous day's close. To get same-day
#   data, change to "5 21 * * 2-6" and accept a later wake-up (8:05 AM AEDT).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
export PATH="/home/char/.local/bin:$PATH"
unset CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_SESSION_ID CLAUDECODE CLAUDE_CODE_ENTRYPOINT CLAUDE_EFFORT
export ROUTINE_SOURCE=cron

SCRIPTS_DIR="/home/char/workspace/trading-app/scripts"
ROUTINE_DIR="/home/char/workspace/trading-routine"
ROUTINE_LOG="/home/char/logs/routine.log"
CLAUDE="/home/char/.local/bin/claude"

# Bash log helper — writes the same structured format as routine_log.py
# so the single routine.log file captures every phase.
rlog() {
    local tag="$1"; shift
    printf "[%s] [%-7s] %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$tag" "$*" | tee -a "$ROUTINE_LOG"
}

T_START=$(date +%s)
echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') START ==="

# ── Step 1: IBKR refresh + DB sync (via bridge socket) ───────────────────────
# refresh_trigger.py writes RUN START + PHASE/OK/ERROR entries to routine.log
if python3 "$SCRIPTS_DIR/refresh_trigger.py"; then
    rlog "OK     " "IBKR refresh + DB sync complete"
else
    rlog "ERROR  " "IBKR refresh failed — aborting routine"
    rlog "END    " "RUN END    status=ERROR  elapsed=$(( $(date +%s) - T_START ))s"
    rlog "END    " "══════════════════════════════════════════════════"
    exit 1
fi

# ── Step 2: Daily briefing ────────────────────────────────────────────────────
rlog "PHASE  " "── Briefing"
cd "$ROUTINE_DIR"
if "$CLAUDE" -p \
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
    2>&1; then
    rlog "OK     " "Briefing generated ✓"
else
    rlog "WARN   " "Briefing generation failed (non-fatal — routine continues)"
fi

# ── Step 3: Git backup push (no pull — DB is source of truth) ────────────────
rlog "PHASE  " "── Git Backup"
cd "$ROUTINE_DIR"
if git diff --quiet && git diff --cached --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    rlog "INFO   " "Nothing to commit — git up to date"
else
    git add -A
    COMMIT_MSG="Auto-backup $(date -u +%Y-%m-%d)"
    if git commit -m "$COMMIT_MSG" 2>&1; then
        rlog "OK     " "git commit: $COMMIT_MSG"
    else
        rlog "WARN   " "git commit failed (non-fatal)"
    fi
fi

if git push origin main 2>&1; then
    rlog "OK     " "git push origin main ✓"
else
    rlog "WARN   " "git push failed (non-fatal — data is safe in DB)"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
ELAPSED=$(( $(date +%s) - T_START ))
rlog "END    " "RUN END    status=OK  elapsed=${ELAPSED}s"
rlog "END    " "══════════════════════════════════════════════════"
echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') END (${ELAPSED}s) ==="
