#!/usr/bin/env bash
# =============================================================================
# ClickHouse Schema Migration Script
# =============================================================================
# Runs the ClickHouse schema SQL against the target instance.
# Idempotent: all CREATE statements use IF NOT EXISTS.
#
# Usage:
#   ./scripts/run_clickhouse_schema.sh                          # defaults
#   CLICKHOUSE_HOST=clickhouse CLICKHOUSE_PORT=8123 \
#     CLICKHOUSE_USER=admin CLICKHOUSE_PASSWORD=secret \
#     ./scripts/run_clickhouse_schema.sh
#
# Can also be used as a Docker entrypoint wrapper:
#   /app/scripts/run_clickhouse_schema.sh && exec "$@"
# =============================================================================

set -euo pipefail

CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-clickhouse}"
CLICKHOUSE_PORT="${CLICKHOUSE_PORT:-8123}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-admin}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-}"
SCHEMA_FILE="${1:-/app/database/schema/clickhouse.sql}"

MAX_RETRIES=30
RETRY_INTERVAL=2

echo "=== Angavu ClickHouse Schema Migration ==="
echo "Host:     ${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}"
echo "User:     ${CLICKHOUSE_USER}"
echo "Schema:   ${SCHEMA_FILE}"

# Wait for ClickHouse to be ready
echo ""
echo "--- Waiting for ClickHouse to be ready ---"
for i in $(seq 1 $MAX_RETRIES); do
    if wget --no-verbose --tries=1 --spider \
        "http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/ping" 2>/dev/null; then
        echo "ClickHouse is ready (attempt ${i}/${MAX_RETRIES})"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "ERROR: ClickHouse not ready after ${MAX_RETRIES} attempts. Exiting."
        exit 1
    fi
    echo "  Attempt ${i}/${MAX_RETRIES} — waiting ${RETRY_INTERVAL}s..."
    sleep "$RETRY_INTERVAL"
done

# Run the schema
echo ""
echo "--- Applying schema ---"
if [ -z "$CLICKHOUSE_PASSWORD" ]; then
    wget --no-verbose --post-file="$SCHEMA_FILE" \
        "http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/?user=${CLICKHOUSE_USER}&multiquery=true" \
        -O - 2>&1
else
    wget --no-verbose --post-file="$SCHEMA_FILE" \
        "http://${CLICKHOUSE_HOST}:${CLICKHOUSE_PORT}/?user=${CLICKHOUSE_USER}&password=${CLICKHOUSE_PASSWORD}&multiquery=true" \
        -O - 2>&1
fi

echo ""
echo "=== Schema migration complete ==="
