#!/bin/bash
# Cron-safe loader wrapper.
# Pulls the latest trading-routine repo, then runs the loader.
#
# Add to crontab (runs at 5:30am Sydney AEST = 19:30 UTC, Mon–Fri):
#   30 19 * * 1-5 /home/char/dashboard/loader/sync.sh >> /home/char/logs/trading-loader.log 2>&1
#
# During AEDT (UTC+11, Oct–Apr) adjust to:
#   30 18 * * 1-5 /home/char/dashboard/loader/sync.sh >> /home/char/logs/trading-loader.log 2>&1
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/char/workspace/trading-routine}"
LOADER_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${ENV_FILE:-/home/char/workspace/dashboard/.env}"

echo "=== $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="

echo "→ Pulling trading-routine repo"
git -C "$REPO_DIR" pull --rebase origin main

# ---------------------------------------------------------------------------
# Optional: refresh IBKR Flex report (lots model).
# Requires FLEX_TOKEN and FLEX_QUERY_ID in .env (never commit these).
# Set FLEX_TOKEN= to disable. Runs weekly (Saturdays) to avoid hammering IBKR.
# ---------------------------------------------------------------------------
if [ -n "${FLEX_TOKEN:-}" ] && [ "$(date +%u)" -eq 6 ]; then
    echo "→ Downloading IBKR Flex report (query ${FLEX_QUERY_ID:-1357986})"
    FLEX_QUERY_ID="${FLEX_QUERY_ID:-1357986}"
    FLEX_DATE=$(date +%Y%m%d)
    FLEX_START=$(date -d '365 days ago' +%Y%m%d 2>/dev/null || date -v-365d +%Y%m%d)
    FLEX_OUT="$REPO_DIR/history/U${FLEX_ACCOUNT:-15760849}_${FLEX_START}_${FLEX_DATE}.csv"

    # Step 1: request the report
    REQUEST_URL="https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
    REQUEST_RESP=$(curl -s -G "$REQUEST_URL" \
        --data-urlencode "t=$FLEX_TOKEN" \
        --data-urlencode "q=$FLEX_QUERY_ID" \
        --data-urlencode "v=3")
    REFERENCE_CODE=$(echo "$REQUEST_RESP" | grep -oP '(?<=<ReferenceCode>)[^<]+' || true)

    if [ -z "$REFERENCE_CODE" ]; then
        echo "  Flex request failed: $REQUEST_RESP"
    else
        sleep 10  # IBKR needs time to generate the report
        # Step 2: download the report
        GET_URL="https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
        curl -s -G "$GET_URL" \
            --data-urlencode "t=$FLEX_TOKEN" \
            --data-urlencode "q=$REFERENCE_CODE" \
            --data-urlencode "v=3" \
            -o "$FLEX_OUT"
        echo "  Saved to $FLEX_OUT"
        git -C "$REPO_DIR" add "$FLEX_OUT" && \
            git -C "$REPO_DIR" commit -m "chore: weekly flex report $FLEX_DATE" && \
            git -C "$REPO_DIR" push origin main || true
    fi
fi

echo "→ Running loader"
# Source the .env file to get POSTGRES_PASSWORD and related vars
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

cd "$LOADER_DIR"
PGHOST=127.0.0.1 \
PGPORT=5432 \
PGDATABASE=trading \
PGUSER="$POSTGRES_USER" \
PGPASSWORD="$POSTGRES_PASSWORD" \
python3 run.py --repo "$REPO_DIR"

# Saturday only: run weekly portfolio behaviour analysis (Layer 2).
# Reads existing tables, writes to analysis_runs + insights.
# DISCORD_WEBHOOK_URL must be set in .env to enable the Discord post.
if [ "$(date +%u)" -eq 6 ]; then
    echo ""
    echo "→ Weekly analysis (Saturday)"
    PGHOST=127.0.0.1 \
    PGPORT=5432 \
    PGDATABASE=trading \
    PGUSER="$POSTGRES_USER" \
    PGPASSWORD="$POSTGRES_PASSWORD" \
    DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}" \
    METABASE_TOKEN="${METABASE_TOKEN:-}" \
    python3 run_analysis.py
fi

echo "=== done ==="
