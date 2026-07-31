#!/bin/bash
# =============================================================================
# PostgreSQL Automatic Failover Watchdog
# Monitors pg-primary health and promotes pg-replica if primary is unreachable.
#
# Strategy:
#   - Poll primary every 10s with pg_isready
#   - After 3 consecutive failures (30s), promote replica
#   - Write promotion marker to prevent re-promotion loops
#   - Alert via log output (picked up by monitoring)
#
# Mount this as a sidecar container in docker-compose.production.yml
# =============================================================================

set -euo pipefail

PRIMARY_HOST="${PG_PRIMARY_HOST:-pg-primary}"
REPLICA_HOST="${PG_REPLICA_HOST:-pg-replica}"
PRIMARY_PORT="${PG_PRIMARY_PORT:-5432}"
REPLICA_PORT="${PG_REPLICA_PORT:-5432}"
CHECK_INTERVAL="${PG_CHECK_INTERVAL:-10}"
FAILURE_THRESHOLD="${PG_FAILURE_THRESHOLD:-3}"
PROMOTION_MARKER="/tmp/pg_failover_promoted"

failure_count=0
promoted=false

log() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [failover-watcher] $*"
}

check_primary() {
    pg_isready -h "$PRIMARY_HOST" -p "$PRIMARY_PORT" -U angavu -d angavu -t 5 >/dev/null 2>&1
}

check_replica() {
    pg_isready -h "$REPLICA_HOST" -p "$REPLICA_PORT" -U angavu -d angavu -t 5 >/dev/null 2>&1
}

promote_replica() {
    if [ -f "$PROMOTION_MARKER" ]; then
        log "WARNING: Promotion marker exists — skipping (already promoted)"
        return 0
    fi

    log "CRITICAL: Promoting pg-replica to primary..."

    # Use docker exec to promote via pg_ctl, or connect and call pg_promote()
    # We connect to the replica and call pg_promote()
    PGPASSWORD="${POSTGRES_PASSWORD:-angavu_secret}" psql \
        -h "$REPLICA_HOST" -p "$REPLICA_PORT" -U angavu -d angavu \
        -c "SELECT pg_promote(true, 60);" 2>&1 || {
            log "ERROR: pg_promote() failed — manual intervention required"
            return 1
        }

    touch "$PROMOTION_MARKER"
    log "CRITICAL: Replica promoted successfully. Update DATABASE_URL to point to $REPLICA_HOST:$REPLICA_PORT"

    # TODO: Integrate with service discovery / DNS update / notification webhook
    # For now, log the required action
    log "ACTION REQUIRED: Redirect application connections to $REPLICA_HOST:$REPLICA_PORT"
}

# Main loop
log "Starting failover watcher (primary=$PRIMARY_HOST:$PRIMARY_PORT, interval=${CHECK_INTERVAL}s, threshold=$FAILURE_THRESHOLD)"

while true; do
    if check_primary; then
        if [ $failure_count -gt 0 ]; then
            log "Primary recovered after $failure_count failures"
        fi
        failure_count=0
    else
        failure_count=$((failure_count + 1))
        log "WARNING: Primary unreachable (failure $failure_count/$FAILURE_THRESHOLD)"

        if [ $failure_count -ge "$FAILURE_THRESHOLD" ] && [ "$promoted" = false ]; then
            if check_replica; then
                promote_replica
                promoted=true
            else
                log "CRITICAL: Both primary and replica unreachable — full outage"
            fi
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
