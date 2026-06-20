#!/bin/bash
# Usage: bash scripts/set-auth.sh <username> <password>
# Generates a bcrypt hash via the Caddy container and writes credentials to .env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

USER="${1:-}"
PASS="${2:-}"

if [ -z "$USER" ] || [ -z "$PASS" ]; then
    echo "Usage: bash scripts/set-auth.sh <username> <password>"
    exit 1
fi

echo "Generating bcrypt hash..."
HASH=$(docker exec trading-app-caddy-1 caddy hash-password --plaintext "$PASS")

# Remove any existing auth lines from .env
sed -i '/^TRADING_APP_USER=/d' "$ENV_FILE"
sed -i '/^TRADING_APP_HASH=/d' "$ENV_FILE"

# Append new values
echo "TRADING_APP_USER=$USER" >> "$ENV_FILE"
echo "TRADING_APP_HASH=$HASH" >> "$ENV_FILE"

echo "Credentials written to .env"
echo "Restarting Caddy..."
cd "$SCRIPT_DIR" && docker compose up -d --no-deps caddy

echo "Done — $USER can now log in at http://139.99.197.93:8080"
