#!/bin/bash
# =============================================================================
# Angavu Intelligence Backend — Azure Container Apps Entrypoint
# Runs migrations then starts the server
# =============================================================================

set -euo pipefail

echo "=== Angavu Intelligence Backend (Azure) ==="
echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Analytics backend: ${ANALYTICS_BACKEND:-postgresql}"

# ── Run database migrations ───────────────────────────────────────────────────
echo "Running database migrations..."
/app/angavu-migrate 2>&1 || {
    echo "⚠️  Migration failed or no migrations to run. Continuing..."
}

# ── Start the server ──────────────────────────────────────────────────────────
echo "Starting Angavu server on ${ANGAVU_HOST}:${ANGAVU_PORT}..."
exec /app/angavu-server --host "${ANGAVU_HOST}" --port "${ANGAVU_PORT}"
