#!/bin/bash
# Sets every secret the deployed manthan-api needs, pulled from the
# combined local .env (manthan-api/.env + agent/.env).
#
# Usage:
#   cd manthanv2/
#   ./scripts/set-fly-secrets.sh manthan-api
#
# Where `manthan-api` is the Fly app name you chose during `fly launch`.

set -euo pipefail

APP_NAME="${1:-manthan-api}"

cd "$(dirname "$0")/.."

# Merge both .env files into one (manthan-api/.env wins for overlap keys).
TMP_ENV=$(mktemp)
trap "rm -f $TMP_ENV" EXIT
cat agent/.env manthan-api/.env 2>/dev/null | grep -E '^[A-Z][A-Z0-9_]*=' | grep -v '^DATABASE_URL=' > "$TMP_ENV"

echo "Setting Fly secrets for app: $APP_NAME"
echo "(skipping DATABASE_URL - Fly Postgres attach sets it automatically)"
echo "---"
grep -c '=' "$TMP_ENV" | awk '{print $1 " secrets to set"}'

# Use fly secrets import (reads KEY=VALUE lines from stdin)
fly secrets import --app "$APP_NAME" < "$TMP_ENV"

echo "done."
