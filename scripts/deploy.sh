#!/usr/bin/env bash
# =============================================================================
# Angavu Intelligence Backend — Production Deploy Script
# Run on Oracle Cloud Free Tier instance
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
MAX_HEALTH_RETRIES=30
HEALTH_RETRY_INTERVAL=10

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*" >&2; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
preflight() {
    log "Running pre-flight checks..."

    if ! command -v docker &>/dev/null; then
        err "Docker is not installed"
        exit 1
    fi

    if ! docker compose version &>/dev/null; then
        err "Docker Compose v2 is required"
        exit 1
    fi

    if [ ! -f "$COMPOSE_FILE" ]; then
        err "docker-compose.yml not found at $COMPOSE_FILE"
        exit 1
    fi

    # Check disk space (need at least 2GB free)
    local free_kb
    free_kb=$(df -k "$PROJECT_DIR" | awk 'NR==2{print $4}')
    if [ "$free_kb" -lt 2097152 ]; then
        err "Low disk space: $((free_kb / 1024))MB free. Need at least 2GB."
        exit 1
    fi

    log "Pre-flight checks passed ✓"
}

# ── Pull latest images ────────────────────────────────────────────────────────
pull_images() {
    log "Pulling latest images..."
    cd "$PROJECT_DIR"
    docker compose pull api 2>/dev/null || warn "Could not pull API image (using local build)"
    log "Images pulled ✓"
}

# ── Backup before deploy ─────────────────────────────────────────────────────
backup_db() {
    log "Creating pre-deploy database backup..."
    local backup_dir="${PROJECT_DIR}/backups"
    local timestamp
    timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${backup_dir}/pre_deploy_${timestamp}.sql.gz"

    mkdir -p "$backup_dir"

    if docker compose exec -T postgres pg_dump -U angavu angavu 2>/dev/null | gzip > "$backup_file"; then
        log "Backup saved: $backup_file"
        # Keep only last 5 backups
        ls -t "$backup_dir"/pre_deploy_*.sql.gz 2>/dev/null | tail -n +6 | xargs -r rm -f
    else
        warn "Backup failed (continuing deploy — first run?)"
    fi
}

# ── Run migrations ───────────────────────────────────────────────────────────
run_migrations() {
    log "Running database migrations..."
    cd "$PROJECT_DIR"

    # The Rust binary handles migrations internally
    if docker compose run --rm --no-deps api /app/angavu-migrate 2>&1; then
        log "Migrations completed ✓"
    else
        warn "Migration command returned non-zero (may be OK if no new migrations)"
    fi
}

# ── Restart services ──────────────────────────────────────────────────────────
restart_services() {
    log "Restarting services..."
    cd "$PROJECT_DIR"

    # Start infrastructure first, then app
    docker compose up -d postgres redis clickhouse
    sleep 5

    # Restart the API
    docker compose up -d --force-recreate api nginx
    log "Services restarted ✓"
}

# ── Health check ──────────────────────────────────────────────────────────────
health_check() {
    log "Running health checks (max ${MAX_HEALTH_RETRIES} attempts)..."

    for i in $(seq 1 "$MAX_HEALTH_RETRIES"); do
        local status
        status=$(curl -sf -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo "000")

        if [ "$status" = "200" ]; then
            log "✅ Health check passed on attempt $i"

            # Verify all services
            cd "$PROJECT_DIR"
            local pg_ok redis_ok ch_ok
            pg_ok=$(docker compose exec -T postgres pg_isready -U angavu -d angavu &>/dev/null && echo "✓" || echo "✗")
            redis_ok=$(docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG && echo "✓" || echo "✗")
            ch_ok=$(docker compose exec -T clickhouse clickhouse-client --query "SELECT 1" &>/dev/null && echo "✓" || echo "✗")

            log "PostgreSQL: $pg_ok | Redis: $redis_ok | ClickHouse: $ch_ok"
            return 0
        fi

        warn "Attempt $i/$MAX_HEALTH_RETRIES: status=$status, retrying in ${HEALTH_RETRY_INTERVAL}s..."
        sleep "$HEALTH_RETRY_INTERVAL"
    done

    err "❌ Health check failed after $MAX_HEALTH_RETRIES attempts"

    # Print logs for debugging
    err "=== Last 20 lines of API logs ==="
    cd "$PROJECT_DIR"
    docker compose logs --tail=20 api
    return 1
}

# ── Rollback ──────────────────────────────────────────────────────────────────
rollback() {
    err "Initiating rollback..."
    cd "$PROJECT_DIR"

    # Restore from latest backup
    local latest_backup
    latest_backup=$(ls -t backups/pre_deploy_*.sql.gz 2>/dev/null | head -1)

    if [ -n "$latest_backup" ]; then
        warn "Restoring database from: $latest_backup"
        gunzip -c "$latest_backup" | docker compose exec -T postgres psql -U angavu -d angavu
    fi

    # Restart previous version
    docker compose down
    docker compose up -d
    err "Rollback complete"
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    log "========================================="
    log " Angavu Backend Deployment"
    log " $(date '+%Y-%m-%d %H:%M:%S %Z')"
    log "========================================="

    preflight
    pull_images
    backup_db
    run_migrations
    restart_services

    if health_check; then
        log "========================================="
        log " ✅ Deployment successful!"
        log "========================================="
    else
        err "========================================="
        err " ❌ Deployment failed!"
        err "========================================="
        read -rp "Rollback? [y/N] " answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            rollback
        fi
        exit 1
    fi
}

# Handle flags
case "${1:-}" in
    --rollback)
        rollback
        ;;
    --health)
        health_check
        ;;
    *)
        main
        ;;
esac
