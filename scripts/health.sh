#!/bin/bash
# =============================================================
# Angavu Intelligence — Health Check
# Restarts unhealthy containers. Run via cron every 5 minutes.
#
# Install via cron:
#   */5 * * * * /path/to/scripts/health.sh
# =============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="${PROJECT_DIR}/logs/health.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"; }

# Determine compose command
if [ -f "${PROJECT_DIR}/docker-compose.oracle.yml" ]; then
    COMPOSE="docker compose -f ${PROJECT_DIR}/docker-compose.oracle.yml"
elif [ -f "${PROJECT_DIR}/docker-compose.yml" ]; then
    COMPOSE="docker compose -f ${PROJECT_DIR}/docker-compose.yml"
else
    log "ERROR: No compose file found"
    exit 1
fi

cd "$PROJECT_DIR"

# Services to monitor
SERVICES=("postgres" "redis" "clickhouse" "api" "backend" "worker" "openwa" "nginx")

RESTARTED=0

for svc in "${SERVICES[@]}"; do
    # Find matching container
    CONTAINER=$(docker ps -a --filter "label=com.docker.compose.service=${svc}" --format '{{.Names}}' 2>/dev/null | head -1)
    if [ -z "$CONTAINER" ]; then
        CONTAINER=$(docker ps -a --filter "name=${svc}" --format '{{.Names}}' 2>/dev/null | head -1)
    fi
    if [ -z "$CONTAINER" ]; then
        continue  # Service not configured
    fi

    STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "missing")
    HEALTH=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER" 2>/dev/null || echo "unknown")

    if [ "$STATUS" != "running" ]; then
        log "ALERT: $CONTAINER is $STATUS — restarting..."
        $COMPOSE restart "$svc" 2>/dev/null || docker restart "$CONTAINER" 2>/dev/null || true
        RESTARTED=$((RESTARTED + 1))
    elif [ "$HEALTH" = "unhealthy" ]; then
        log "WARN: $CONTAINER is unhealthy — restarting..."
        docker restart "$CONTAINER" 2>/dev/null || true
        RESTARTED=$((RESTARTED + 1))
    fi
done

if [ "$RESTARTED" -gt 0 ]; then
    log "Restarted $RESTARTED service(s)"
fi
