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

echo "=== done ==="
