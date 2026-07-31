#!/usr/bin/env bash
# =============================================================================
# deploy-oracle.sh — Deploy Angavu Intelligence Backend on Oracle Free Tier
#
# Prerequisites:
#   - Oracle Cloud ARM Ampere A1 instance (4 OCPU, 24GB RAM)
#   - Docker 24+ with buildx plugin
#   - .env.oracle configured (see .env.oracle.example)
#
# Usage:
#   ./scripts/deploy-oracle.sh              # build + deploy
#   ./scripts/deploy-oracle.sh --pull       # pull pre-built image + deploy
#   ./scripts/deploy-oracle.sh --update     # rebuild + redeploy (zero-downtime)
#   ./scripts/deploy-oracle.sh --logs       # tail logs
#   ./scripts/deploy-oracle.sh --status     # show service status
#   ./scripts/deploy-oracle.sh --backup     # backup PostgreSQL
#   ./scripts/deploy-oracle.sh --stop       # stop all services
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.oracle.yml"
ENV_FILE="$PROJECT_ROOT/.env.oracle"
BACKUP_DIR="$PROJECT_ROOT/backups"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[oracle]${NC} $*"; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }

check_prerequisites() {
    # Check Docker
    if ! command -v docker &>/dev/null; then
        err "Docker not found. Install: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi

    # Check buildx
    if ! docker buildx version &>/dev/null; then
        warn "Docker buildx not found. Installing..."
        docker buildx install 2>/dev/null || {
            err "Failed to install buildx. Install manually."
            exit 1
        }
    fi

    # Check .env.oracle
    if [ ! -f "$ENV_FILE" ]; then
        err ".env.oracle not found. Copy from .env.oracle.example:"
        err "  cp .env.oracle.example .env.oracle"
        err "  nano .env.oracle"
        exit 1
    fi

    # Verify required vars
    source "$ENV_FILE"
    local missing=0
    for var in POSTGRES_PASSWORD JWT_SECRET ENCRYPTION_KEY; do
        if [ -z "${!var:-}" ] || [[ "${!var}" == *"CHANGE_ME"* ]]; then
            err "Set $var in .env.oracle"
            missing=1
        fi
    done
    if [ "$missing" -eq 1 ]; then
        exit 1
    fi

    # Check architecture
    local arch
    arch=$(uname -m)
    if [ "$arch" != "aarch64" ] && [ "$arch" != "arm64" ]; then
        warn "Expected ARM64 (aarch64), got $arch. Build will use emulation."
    fi

    ok "Prerequisites checked"
}

build_image() {
    log "Building ARM64 image..."
    docker buildx build \
        --platform linux/arm64 \
        -f "$PROJECT_ROOT/Dockerfile.oracle" \
        -t angavu-backend:latest \
        --load \
        "$PROJECT_ROOT"
    ok "Image built"
}

deploy() {
    log "Deploying services..."
    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
    ok "Services started"

    log "Waiting for health checks..."
    sleep 10

    # Check service health
    local all_healthy=true
    for svc in postgres redis api nginx; do
        local status
        status=$(docker compose -f "$COMPOSE_FILE" ps --format json "$svc" 2>/dev/null | grep -o '"State":"[^"]*"' | head -1 || echo "unknown")
        if [[ "$status" == *"running"* ]]; then
            ok "$svc: running"
        else
            warn "$svc: $status"
            all_healthy=false
        fi
    done

    if [ "$all_healthy" = true ]; then
        echo ""
        ok "All services running on Oracle Free Tier"
        log "API: http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):8000"
        log "Health: http://localhost:8000/health"
    fi
}

update() {
    log "Zero-downtime update..."
    build_image
    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --no-deps api
    ok "API updated"
}

backup() {
    log "Backing up PostgreSQL..."
    mkdir -p "$BACKUP_DIR"
    local ts
    ts=$(date +%Y%m%d_%H%M%S)
    local backup_file="$BACKUP_DIR/angavu_${ts}.sql.gz"

    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" exec -T postgres \
        pg_dump -U angavu -d angavu --format=custom | gzip > "$backup_file"

    ok "Backup saved: $backup_file ($(du -h "$backup_file" | cut -f1))"

    # Cleanup old backups (keep last 7)
    ls -t "$BACKUP_DIR"/angavu_*.sql.gz 2>/dev/null | tail -n +8 | xargs -r rm
}

show_status() {
    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    log "Resource usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
        $(docker compose -f "$COMPOSE_FILE" ps -q 2>/dev/null) 2>/dev/null || true
}

show_logs() {
    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" logs -f --tail=100
}

stop_services() {
    log "Stopping services..."
    cd "$PROJECT_ROOT"
    docker compose -f "$COMPOSE_FILE" down
    ok "Services stopped"
}

# ── Main ─────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --pull)
        check_prerequisites
        deploy
        ;;
    --update)
        check_prerequisites
        update
        ;;
    --logs)
        show_logs
        ;;
    --status)
        show_status
        ;;
    --backup)
        backup
        ;;
    --stop)
        stop_services
        ;;
    *)
        check_prerequisites
        build_image
        deploy
        ;;
esac
