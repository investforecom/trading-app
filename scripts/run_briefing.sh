#!/bin/bash
# Run only the daily briefing — no IBKR refresh needed.
# Uses data already written by the last full routine run:
#   ~/workspace/trading-routine/account_state.json
#   ~/workspace/trading-routine/ibkr_positions.json
#   postgres position_snapshots (latest date)
#
# Usage:
#   ./run_briefing.sh              # uses date from account_state.json
#   ./run_briefing.sh 2026-06-25   # specific date
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
ROUTINE_DIR="$HOME/workspace/trading-routine"

DATE_ARG="${1:-}"

echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') Briefing only ==="

# Step 1: Generate markdown + post Discord
if python3 "$SCRIPTS_DIR/generate_briefing.py" ${DATE_ARG:+"$DATE_ARG"}; then
    echo "OK  briefing generated"
else
    echo "ERROR  generate_briefing.py failed" >&2
    exit 1
fi

# Step 2: Load into DB
BRIEFING_DATE="${DATE_ARG:-$(python3 -c "
import json, pathlib
p = pathlib.Path('$ROUTINE_DIR/account_state.json')
print(json.loads(p.read_text()).get('date','')) if p.exists() else print('')
" 2>/dev/null)}"
BRIEFING_DATE="${BRIEFING_DATE:-$(date -u +%Y-%m-%d)}"

if python3 "$SCRIPTS_DIR/load_briefing.py" "$BRIEFING_DATE"; then
    echo "OK  loaded into DB for $BRIEFING_DATE"
else
    echo "WARN  load_briefing.py failed" >&2
fi

echo "=== Done ==="
