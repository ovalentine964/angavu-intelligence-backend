#!/bin/bash
# ================================================================
# ANGAVU INTELLIGENCE — ONE-COMMAND DEPLOY
# ================================================================
# Usage: sudo bash deploy.sh
#
# Deploys the full Angavu Intelligence stack on Oracle Cloud
# Free Tier (or any Linux server with 4GB+ RAM).
#
# What it does:
#   1. Checks prerequisites (Docker, Docker Compose, git)
#   2. Creates .env from .env.example with real secrets
#   3. Starts services in correct dependency order
#   4. Runs database migrations
#   5. Sets up automated backups and health monitoring
#   6. Rolls back on failure
#
# Requirements:
#   - Ubuntu 22.04+ or Oracle Linux 8+
#   - 2+ CPU cores, 4GB+ RAM, 50GB+ disk
#   - Run as root
# ================================================================

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${GREEN}[ANGAVU]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()  { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

# ── Script directory (where the repo lives) ─────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Compose file selection ──────────────────────────────────
# Use oracle compose on ARM/free-tier, fall back to main compose
if [ -f "docker-compose.oracle.yml" ]; then
    COMPOSE_FILE="docker-compose.oracle.yml"
else
    COMPOSE_FILE="docker-compose.yml"
fi
COMPOSE_CMD="docker compose -f $COMPOSE_FILE"

# ── Rollback trap ───────────────────────────────────────────
DEPLOY_STARTED=0
rollback() {
    if [ "$DEPLOY_STARTED" -eq 1 ]; then
        warn "Deployment failed — rolling back..."
        $COMPOSE_CMD down --remove-orphans 2>/dev/null || true
        warn "Services stopped. Check logs above for the error."
    fi
}
trap rollback ERR

# ================================================================
# STEP 1: PREREQUISITES CHECK
# ================================================================
step "Step 1/7: Checking prerequisites"

if [ "$(id -u)" -ne 0 ]; then
    error "This script must be run as root. Use: sudo bash deploy.sh"
fi

CORES=$(nproc)
RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
DISK_GB=$(df -BG / | awk 'NR==2{print $2}' | tr -d 'G')

log "CPU cores: $CORES | RAM: ${RAM_MB}MB | Disk: ${DISK_GB}GB"

if [ "$CORES" -lt 2 ]; then
    error "Need at least 2 CPU cores. Found: $CORES"
fi
if [ "$RAM_MB" -lt 3800 ]; then
    error "Need at least 4GB RAM. Found: ${RAM_MB}MB"
fi

# ── Install Docker ──────────────────────────────────────────
if command -v docker &>/dev/null; then
    log "Docker already installed: $(docker --version)"
else
    log "Installing Docker..."
    if [ -f /etc/oracle-release ]; then
        # Oracle Linux
        dnf install -y docker-engine
    elif command -v apt-get &>/dev/null; then
        # Ubuntu/Debian
        apt-get update -qq
        apt-get install -y -qq ca-certificates curl gnupg lsb-release
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
            > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    else
        error "Unsupported OS. Install Docker manually: https://docs.docker.com/engine/install/"
    fi
    systemctl enable docker
    systemctl start docker
    log "Docker installed: $(docker --version)"
fi

# ── Check Docker Compose (plugin or standalone) ─────────────
if docker compose version &>/dev/null; then
    log "Docker Compose plugin: $(docker compose version --short)"
elif command -v docker-compose &>/dev/null; then
    log "Docker Compose standalone: $(docker-compose --version)"
    # Alias for consistency
    COMPOSE_CMD="docker-compose -f $COMPOSE_FILE"
else
    log "Installing Docker Compose plugin..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq
        apt-get install -y -qq docker-compose-plugin
    elif command -v dnf &>/dev/null; then
        dnf install -y docker-compose-plugin
    else
        # Fallback: install standalone binary
        COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -Po '"tag_name": "\K.*\d')
        curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
            -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        COMPOSE_CMD="docker-compose -f $COMPOSE_FILE"
    fi
    log "Docker Compose installed"
fi

# ── Check git ───────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    log "Installing git..."
    if command -v apt-get &>/dev/null; then
        apt-get install -y -qq git
    else
        dnf install -y git
    fi
fi

# ── Verify we're in the repo ────────────────────────────────
if [ ! -f "Dockerfile" ] || [ ! -f "app/main.py" ]; then
    error "Run this script from the angavu-intelligence-backend repo root. Missing Dockerfile or app/main.py."
fi

log "All prerequisites satisfied ✓"

# ================================================================
# STEP 2: GENERATE .ENV FROM .env.example
# ================================================================
step "Step 2/7: Generating environment configuration"

if [ -f ".env" ]; then
    log ".env already exists — keeping existing configuration"
    # Source it to get passwords for compose
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
else
    if [ ! -f ".env.example" ]; then
        error "Missing .env.example — cannot generate .env"
    fi

    log "Creating .env from .env.example with generated secrets..."

    # Generate secrets (64 hex chars = 128 bits for keys, 32 hex chars = 64 bits for passwords)
    DB_PASSWORD=$(openssl rand -hex 16)
    REDIS_PASSWORD=$(openssl rand -hex 16)
    CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)
    JWT_SECRET_KEY=$(openssl rand -hex 32)
    ENCRYPTION_KEY=$(openssl rand -hex 32)
    SECRET_KEY=$(openssl rand -hex 32)
    OPENWA_WEBHOOK_SECRET=$(openssl rand -hex 16)

    # Copy example and replace placeholder values
    cp .env.example .env

    # Replace all CHANGE_ME values with real secrets
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://msaidizi:${DB_PASSWORD}@postgres:5432/msaidizi|" .env
    sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=${DB_PASSWORD}|" .env
    sed -i "s|^REDIS_URL=.*|REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0|" .env
    sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" .env
    sed -i "s|^CLICKHOUSE_PASSWORD=.*|CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}|" .env
    sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET_KEY}|" .env
    sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${ENCRYPTION_KEY}|" .env
    sed -i "s|^OPENWA_WEBHOOK_SECRET=.*|OPENWA_WEBHOOK_SECRET=${OPENWA_WEBHOOK_SECRET}|" .env

    # Set ENABLE_WHATSAPP (default: false — WhatsApp is optional)
    if grep -q "^ENABLE_WHATSAPP=" .env; then
        sed -i "s|^ENABLE_WHATSAPP=.*|ENABLE_WHATSAPP=${ENABLE_WHATSAPP:-false}|" .env
    else
        echo "ENABLE_WHATSAPP=${ENABLE_WHATSAPP:-false}" >> .env
    fi

    # Add SECRET_KEY if not in example
    if ! grep -q "^SECRET_KEY=" .env; then
        echo "SECRET_KEY=${SECRET_KEY}" >> .env
    else
        sed -i "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env
    fi

    chmod 600 .env
    log ".env created with secure random secrets ✓"

    # Save credentials securely
    mkdir -p /root/.angavu
    cat > /root/.angavu/credentials << CREDS
# Angavu Intelligence — Credentials
# Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')
# ⚠️  KEEP THIS FILE SECURE — delete after noting passwords

Database Password:    ${DB_PASSWORD}
Redis Password:       ${REDIS_PASSWORD}
ClickHouse Password:  ${CLICKHOUSE_PASSWORD}
JWT Secret Key:       ${JWT_SECRET_KEY}
Encryption Key:       ${ENCRYPTION_KEY}
Secret Key:           ${SECRET_KEY}
OpenWA Webhook:       ${OPENWA_WEBHOOK_SECRET}
CREDS
    chmod 600 /root/.angavu/credentials
    log "Credentials saved to /root/.angavu/credentials"
fi

# ================================================================
# STEP 3: SSL CERTIFICATES
# ================================================================
step "Step 3/7: Setting up SSL certificates"

mkdir -p nginx/ssl nginx/certbot

if [ ! -f "nginx/ssl/fullchain.pem" ] || [ ! -f "nginx/ssl/privkey.pem" ]; then
    DOMAIN="${ANGAVU_DOMAIN:-}"
    EMAIL="${ANGAVU_EMAIL:-}"

    if [ -n "$DOMAIN" ] && [ -n "$EMAIL" ]; then
        log "Requesting Let's Encrypt certificate for $DOMAIN..."

        # Install certbot
        if command -v apt-get &>/dev/null; then
            apt-get install -y -qq certbot 2>/dev/null || true
        else
            dnf install -y certbot 2>/dev/null || true
        fi

        # Generate self-signed first so nginx can start
        openssl req -x509 -nodes -days 7 -newkey rsa:2048 \
            -keyout nginx/ssl/privkey.pem \
            -out nginx/ssl/fullchain.pem \
            -subj "/CN=$DOMAIN" 2>/dev/null

        # Start nginx for ACME challenge
        $COMPOSE_CMD up -d nginx 2>/dev/null || true
        sleep 3

        # Get real cert
        certbot certonly --webroot -w /var/www/certbot \
            -d "$DOMAIN" --email "$EMAIL" --agree-tos --non-interactive \
            --deploy-hook "cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $SCRIPT_DIR/nginx/ssl/fullchain.pem && cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $SCRIPT_DIR/nginx/ssl/privkey.pem && $COMPOSE_CMD restart nginx" \
            2>/dev/null || warn "Certbot failed — using self-signed certificate"

        # Auto-renew
        (crontab -l 2>/dev/null | grep -v certbot; echo "0 3 * * * certbot renew --quiet") | crontab -
    else
        log "No domain configured — generating self-signed certificate..."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/privkey.pem \
            -out nginx/ssl/fullchain.pem \
            -subj "/CN=localhost" 2>/dev/null
    fi

    chmod 600 nginx/ssl/*.pem
    log "SSL certificates ready ✓"
else
    log "SSL certificates already exist — skipping"
fi

# ================================================================
# STEP 4: CREATE REQUIRED DIRECTORIES
# ================================================================
step "Step 4/7: Preparing directories"

mkdir -p logs backups scripts
log "Directories created ✓"

# ================================================================
# STEP 5: START SERVICES IN ORDER
# ================================================================
step "Step 5/7: Starting services"

DEPLOY_STARTED=1

# Pull images first (parallel, faster)
log "Pulling Docker images..."
$COMPOSE_CMD pull --ignore-buildable 2>/dev/null || $COMPOSE_CMD pull 2>/dev/null || true

# Build application images
log "Building application images..."
$COMPOSE_CMD build --no-cache api 2>/dev/null || $COMPOSE_CMD build --no-cache backend 2>/dev/null || true

# Build OpenWA only if WhatsApp is enabled
if [ "${ENABLE_WHATSAPP:-false}" = "true" ]; then
    log "Building OpenWA image (WhatsApp enabled)..."
    $COMPOSE_CMD build --no-cache openwa 2>/dev/null || warn "OpenWA build failed"
else
    log "WhatsApp disabled — skipping OpenWA build"
fi

# ── Start PostgreSQL first ──────────────────────────────────
log "Starting PostgreSQL..."
$COMPOSE_CMD up -d postgres
log "Waiting for PostgreSQL to be healthy..."
TRIES=0
MAX_TRIES=30
until $COMPOSE_CMD exec -T postgres pg_isready -U msaidizi -d msaidizi 2>/dev/null || \
      $COMPOSE_CMD exec -T postgres pg_isready -U biashara -d biashara 2>/dev/null; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge "$MAX_TRIES" ]; then
        error "PostgreSQL failed to start after ${MAX_TRIES} attempts"
    fi
    echo -n "."
    sleep 2
done
echo ""
log "PostgreSQL is healthy ✓"

# ── Start Redis ─────────────────────────────────────────────
log "Starting Redis..."
$COMPOSE_CMD up -d redis
log "Waiting for Redis to be healthy..."
TRIES=0
until $COMPOSE_CMD exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge "$MAX_TRIES" ]; then
        error "Redis failed to start after ${MAX_TRIES} attempts"
    fi
    echo -n "."
    sleep 2
done
echo ""
log "Redis is healthy ✓"

# ── Start ClickHouse (if in compose file) ───────────────────
if grep -q "clickhouse:" "$COMPOSE_FILE" 2>/dev/null; then
    log "Starting ClickHouse..."
    $COMPOSE_CMD up -d clickhouse 2>/dev/null || true
    TRIES=0
    until $COMPOSE_CMD exec -T clickhouse clickhouse-client --query "SELECT 1" 2>/dev/null | grep -q 1; do
        TRIES=$((TRIES + 1))
        if [ "$TRIES" -ge "$MAX_TRIES" ]; then
            warn "ClickHouse not ready — continuing without it"
            break
        fi
        echo -n "."
        sleep 2
    done
    echo ""
    log "ClickHouse is healthy ✓"
fi

# ── Start Backend / API ─────────────────────────────────────
log "Starting backend..."
$COMPOSE_CMD up -d api 2>/dev/null || $COMPOSE_CMD up -d backend 2>/dev/null
log "Waiting for backend to be healthy..."
TRIES=0
MAX_TRIES=60  # Backend takes longer (image build + startup)
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do
    TRIES=$((TRIES + 1))
    if [ "$TRIES" -ge "$MAX_TRIES" ]; then
        # Show last few lines of logs for debugging
        warn "Backend logs:"
        $COMPOSE_CMD logs --tail=20 api 2>/dev/null || $COMPOSE_CMD logs --tail=20 backend 2>/dev/null || true
        error "Backend failed to start after ${MAX_TRIES} attempts"
    fi
    echo -n "."
    sleep 3
done
echo ""
log "Backend is healthy ✓"

# ── Start optional services (non-blocking) ──────────────────
# Worker, Nginx — start but don't fail deploy if unhealthy
OPTIONAL_SERVICES="worker nginx"

# Add OpenWA only if WhatsApp is enabled
if [ "${ENABLE_WHATSAPP:-false}" = "true" ]; then
    OPTIONAL_SERVICES="$OPTIONAL_SERVICES openwa whisper"
    log "WhatsApp enabled — starting OpenWA + Whisper as optional services"
else
    log "WhatsApp disabled — skipping OpenWA (set ENABLE_WHATSAPP=true to enable)"
fi

for svc in $OPTIONAL_SERVICES; do
    if grep -q "^\s*${svc}:" "$COMPOSE_FILE" 2>/dev/null; then
        log "Starting $svc..."
        $COMPOSE_CMD up -d "$svc" 2>/dev/null || warn "Failed to start $svc (non-critical)"
    fi
done

log "All services started ✓"

# ================================================================
# STEP 6: DATABASE MIGRATIONS
# ================================================================
step "Step 6/7: Running database migrations"

MIGRATION_DONE=0
for i in 1 2 3 4 5; do
    if $COMPOSE_CMD exec -T api alembic upgrade head 2>/dev/null || \
       $COMPOSE_CMD exec -T backend alembic upgrade head 2>/dev/null; then
        MIGRATION_DONE=1
        break
    fi
    log "  Waiting for database to accept connections (attempt $i/5)..."
    sleep 10
done

if [ "$MIGRATION_DONE" -eq 1 ]; then
    log "Migrations complete ✓"

    # ── Run initial backup after schema is ready ──────────────
    log "Running initial backup..."
    if bash scripts/backup.sh; then
        log "Initial backup complete ✓"
    else
        warn "Initial backup failed (non-fatal — cron will retry daily)"
    fi
else
    warn "Migrations skipped — run manually: $COMPOSE_CMD exec api alembic upgrade head"
fi

# ================================================================
# STEP 7: BACKUPS & HEALTH MONITORING
# ================================================================
step "Step 7/7: Setting up backups and health monitoring"

# ── Create backup directories ───────────────────────────────
BACKUP_DIR="/opt/backups/postgresql"
mkdir -p "$BACKUP_DIR"
chmod 750 "$BACKUP_DIR"
mkdir -p /var/log

# ── Backup script (pg_dump -Fc custom format) ──────────────
cat > scripts/backup.sh << 'BACKUP_SCRIPT'
#!/bin/bash
# =============================================================
# Angavu Intelligence — Automated PostgreSQL Backup
# pg_dump custom format, compressed, 7-day retention.
# =============================================================
set -euo pipefail

BACKUP_DIR="/opt/backups/postgresql"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/var/log/angavu-backup.log"

# Source .env for credentials
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

log "=== Backup started ==="

# ── Find PostgreSQL container ───────────────────────────────
PG_CONTAINER=""
for name in biashara-postgres angavu-postgres msaidizi-postgres postgres; do
    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        PG_CONTAINER="$name"
        break
    fi
done

if [ -z "$PG_CONTAINER" ]; then
    log "ERROR: PostgreSQL container not found"
    exit 1
fi

DB_USER="${POSTGRES_USER:-msaidizi}"
DB_NAME="${POSTGRES_DB:-msaidizi}"
BACKUP_FILE="${BACKUP_DIR}/angavu_${DB_NAME}_${DATE}.dump.gz"

# ── pg_dump with custom format (-Fc) ───────────────────────
log "Dumping database '$DB_NAME' from container '$PG_CONTAINER' (pg_dump -Fc)..."

DUMP_TMP="${BACKUP_DIR}/angavu_${DB_NAME}_${DATE}.dump"
if ! docker exec "$PG_CONTAINER" pg_dump \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -Fc \
    --no-owner \
    --no-privileges \
    > "$DUMP_TMP" 2>>"$LOG_FILE"; then
    log "ERROR: pg_dump failed"
    rm -f "$DUMP_TMP"
    exit 1
fi

# ── Compress ────────────────────────────────────────────────
gzip -f "$DUMP_TMP"

if [ ! -s "$BACKUP_FILE" ]; then
    log "ERROR: Backup file is empty after compression"
    rm -f "$BACKUP_FILE"
    exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)

# ── Verify integrity ────────────────────────────────────────
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    log "ERROR: Backup file is corrupted (gzip check failed)"
    rm -f "$BACKUP_FILE"
    exit 1
fi

log "PostgreSQL backup: $BACKUP_FILE ($SIZE) ✓"

# ── Redis snapshot ──────────────────────────────────────────
REDIS_CONTAINER=""
for name in biashara-redis angavu-redis msaidizi-redis redis; do
    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        REDIS_CONTAINER="$name"
        break
    fi
done

if [ -n "$REDIS_CONTAINER" ]; then
    REDIS_BACKUP="${BACKUP_DIR}/redis_${DATE}.rdb"
    docker exec "$REDIS_CONTAINER" redis-cli -a "${REDIS_PASSWORD:-}" BGSAVE >/dev/null 2>&1 || true
    sleep 2
    docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "$REDIS_BACKUP" 2>/dev/null || true

    if [ -s "$REDIS_BACKUP" ]; then
        gzip "$REDIS_BACKUP"
        log "Redis snapshot: ${REDIS_BACKUP}.gz ✓"
    fi
fi

# ── ClickHouse backup (if running) ─────────────────────────
CH_CONTAINER=""
for name in biashara-clickhouse angavu-clickhouse clickhouse; do
    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        CH_CONTAINER="$name"
        break
    fi
done

if [ -n "$CH_CONTAINER" ]; then
    CH_BACKUP="${BACKUP_DIR}/clickhouse_${DATE}.tar.gz"
    docker exec "$CH_CONTAINER" clickhouse-client \
        --query "BACKUP DATABASE biashara TO File('/tmp/ch_backup')" 2>/dev/null || true
    docker cp "${CH_CONTAINER}:/tmp/ch_backup" - 2>/dev/null | gzip > "$CH_BACKUP" 2>/dev/null || true
    if [ -s "$CH_BACKUP" ]; then
        log "ClickHouse backup: $CH_BACKUP ✓"
    else
        rm -f "$CH_BACKUP"
    fi
fi

# ── Retention: delete backups older than 7 days ─────────────
DELETED=$(find "$BACKUP_DIR" -type f \( -name "*.dump.gz" -o -name "*.rdb.gz" -o -name "*.tar.gz" \) -mtime +7 -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    log "Cleaned up $DELETED old backup(s)"
fi

TOTAL=$(find "$BACKUP_DIR" -type f -name "*.dump.gz" | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
log "=== Backup complete === ($TOTAL backups on disk, $TOTAL_SIZE total)"

exit 0
BACKUP_SCRIPT

chmod +x scripts/backup.sh

# ── Restore script ──────────────────────────────────────────
cat > scripts/restore.sh << 'RESTORE_SCRIPT'
#!/bin/bash
# =============================================================
# Angavu Intelligence — PostgreSQL Restore
# Restores pg_dump -Fc custom-format backups.
# =============================================================
set -euo pipefail

BACKUP_DIR="/opt/backups/postgresql"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source .env
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

log() { echo -e "[\033[0;32mRESTORE\033[0m] $1"; }
warn() { echo -e "[\033[1;33mWARN\033[0m] $1"; }
error() { echo -e "[\033[0;31mERROR\033[0m] $1"; exit 1; }

ACTION=""
BACKUP_FILE=""
DROP_EXISTING=false
SKIP_CONFIRM=false
DB_USER="${POSTGRES_USER:-msaidizi}"
DB_NAME="${POSTGRES_DB:-msaidizi}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --list)         ACTION="list"; shift ;;
        --file)         ACTION="restore"; BACKUP_FILE="$2"; shift 2 ;;
        --latest)       ACTION="latest"; shift ;;
        --verify)       ACTION="verify"; BACKUP_FILE="$2"; shift 2 ;;
        --drop-existing) DROP_EXISTING=true; shift ;;
        --yes|-y)       SKIP_CONFIRM=true; shift ;;
        -h|--help)
            echo "Usage: $0 --list | --latest | --file <file> | --verify <file>"
            echo "  --drop-existing   Drop database before restore"
            echo "  --yes             Skip confirmation"
            exit 0 ;;
        *) error "Unknown option: $1" ;;
esac
done

# Find PostgreSQL container
find_pg() {
    for name in biashara-postgres angavu-postgres msaidizi-postgres postgres; do
        if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
            echo "$name"
            return
        fi
    done
    error "PostgreSQL container not found"
}

list_backups() {
    log "Available backups in $BACKUP_DIR:"
    echo ""
    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR"/*.dump.gz 2>/dev/null)" ]; then
        echo "  No backups found."
        return 0
    fi
    printf "  %-5s  %-14s  %-10s  %s\n" "#" "DATE" "SIZE" "FILE"
    printf "  %-5s  %-14s  %-10s  %s\n" "---" "----" "----" "----"
    local i=1
    while IFS= read -r file; do
        local sz=$(du -h "$file" | cut -f1)
        local bn=$(basename "$file")
        printf "  %-5s  %-14s  %-10s  %s\n" "$i" "${bn#angavu_${DB_NAME}_}" "${sz}" "$bn"
        ((i++))
    done < <(ls -t "$BACKUP_DIR"/*.dump.gz 2>/dev/null)
    echo ""
}

verify_backup() {
    local file="$1"
    [ ! -f "$file" ] && error "File not found: $file"
    log "Verifying: $(basename "$file")"
    echo -n "  gzip integrity... "
    gzip -t "$file" 2>/dev/null && echo "✅ OK" || { echo "❌ FAILED"; error "Corrupted"; }
    local size=$(du -h "$file" | cut -f1)
    log "Backup is valid ($size)"
}

do_restore() {
    local file="$1"
    [ ! -f "$file" ] && error "Backup file not found: $file"
    verify_backup "$file"

    local PG_CONTAINER
    PG_CONTAINER=$(find_pg)

    if [ "$SKIP_CONFIRM" = false ]; then
        echo ""
        warn "This will OVERWRITE the '$DB_NAME' database!"
        echo "  Source: $(basename "$file")"
        echo "  Target: $DB_NAME on $PG_CONTAINER"
        echo ""
        read -p "  Type 'yes' to confirm: " confirm
        [ "$confirm" != "yes" ] && { log "Cancelled."; exit 0; }
    fi

    # Terminate existing connections
    docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" \
        >/dev/null 2>&1 || true

    if [ "$DROP_EXISTING" = true ]; then
        log "Dropping and recreating database '$DB_NAME'..."
        docker exec "$PG_CONTAINER" dropdb -U "$DB_USER" --if-exists "$DB_NAME" 2>/dev/null || true
        docker exec "$PG_CONTAINER" createdb -U "$DB_USER" "$DB_NAME" 2>/dev/null || true
    fi

    log "Restoring from $(basename "$file")..."
    docker exec -i "$PG_CONTAINER" pg_restore \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --no-owner \
        --no-privileges \
        --clean \
        --if-exists \
        < "$file" 2>&1 | tail -5 || warn "pg_restore exited with warnings (often normal)"

    # Verify
    local table_count
    table_count=$(docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
    local db_size
    db_size=$(docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" 2>/dev/null | tr -d ' ')

    log "=== Restore completed ==="
    log "  Tables: $table_count | Size: $db_size"
}

case "$ACTION" in
    list) list_backups ;;
    latest)
        LATEST=$(ls -t "$BACKUP_DIR"/*.dump.gz 2>/dev/null | head -1)
        [ -z "$LATEST" ] && error "No backups found"
        log "Latest: $(basename "$LATEST")"
        do_restore "$LATEST" ;;
    restore)
        [[ "$BACKUP_FILE" != /* ]] && BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
        do_restore "$BACKUP_FILE" ;;
    verify)
        [[ "$BACKUP_FILE" != /* ]] && BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
        verify_backup "$BACKUP_FILE" ;;
    *)
        echo "Usage: $0 --list | --latest | --file <file> | --verify <file>"
        exit 1 ;;
esac
RESTORE_SCRIPT

chmod +x scripts/restore.sh

# ── Log rotation for backup logs ────────────────────────────
cat > /etc/logrotate.d/angavu-backup << 'LOGROTATE'
/var/log/angavu-backup.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 640 root root
    dateext
}
LOGROTATE

log "Backup scripts installed ✓"
log "  - scripts/backup.sh  (pg_dump -Fc, gzip, 7-day retention)"
log "  - scripts/restore.sh (--list, --latest, --file, --verify)"
log "  - Log rotation: /etc/logrotate.d/angavu-backup (14 days)"

# ── Health check script ─────────────────────────────────────
cat > scripts/health.sh << 'HEALTH_SCRIPT'
#!/bin/bash
# =============================================================
# Angavu Intelligence — Health Check
# Runs every 5 minutes via cron. Restarts unhealthy containers.
# =============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Determine compose command
if [ -f "${PROJECT_DIR}/docker-compose.oracle.yml" ]; then
    COMPOSE="docker compose -f ${PROJECT_DIR}/docker-compose.oracle.yml"
else
    COMPOSE="docker compose -f ${PROJECT_DIR}/docker-compose.yml"
fi

cd "$PROJECT_DIR"

# Expected services (check whichever are running)
SERVICES=("postgres" "redis" "clickhouse" "api" "backend" "openwa" "nginx" "worker")

for svc in "${SERVICES[@]}"; do
    CONTAINER=$(docker ps --filter "name=${svc}" --format '{{.Names}}' 2>/dev/null | head -1)
    if [ -z "$CONTAINER" ]; then
        continue  # Service not running (might not be configured)
    fi

    STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "missing")
    HEALTH=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CONTAINER" 2>/dev/null || echo "unknown")

    if [ "$STATUS" != "running" ]; then
        echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] ALERT: $CONTAINER is $STATUS — restarting..."
        $COMPOSE restart "$svc" 2>/dev/null || docker restart "$CONTAINER" 2>/dev/null || true
    elif [ "$HEALTH" = "unhealthy" ]; then
        echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] WARN: $CONTAINER is unhealthy — restarting..."
        docker restart "$CONTAINER" 2>/dev/null || true
    fi
done
HEALTH_SCRIPT

chmod +x scripts/health.sh

# ── Install cron jobs ───────────────────────────────────────
log "Installing cron jobs..."

# Remove old angavu cron entries, keep others
(crontab -l 2>/dev/null | grep -v "angavu\|/opt/angavu") | crontab - 2>/dev/null || true

# Add new entries
{
    crontab -l 2>/dev/null || true
    echo "# Angavu Intelligence — daily backup at 2:00 AM"
    echo "0 2 * * * ${SCRIPT_DIR}/scripts/backup.sh"
    echo "# Angavu Intelligence — health check every 5 minutes"
    echo "*/5 * * * * ${SCRIPT_DIR}/scripts/health.sh"
} | crontab -

log "Cron jobs installed ✓"
log "  - Daily backup: 0 2 * * *"
log "  - Health check: */5 * * * *"

# ================================================================
# VERIFICATION
# ================================================================
echo ""
echo "========================================================"
echo "  ANGAVU INTELLIGENCE — DEPLOYMENT VERIFICATION"
echo "========================================================"
echo ""

HEALTHY=0
TOTAL=0

# Check each expected service
VERIFY_SERVICES="postgres redis clickhouse api backend worker nginx"
if [ "${ENABLE_WHATSAPP:-false}" = "true" ]; then
    VERIFY_SERVICES="$VERIFY_SERVICES openwa whisper"
fi

for svc in $VERIFY_SERVICES; do
    CONTAINER=$(docker ps --filter "name=${svc}" --format '{{.Names}}' 2>/dev/null | head -1)
    if [ -z "$CONTAINER" ]; then
        continue
    fi
    TOTAL=$((TOTAL + 1))
    STATUS=$(docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "running" ]; then
        echo -e "  ${GREEN}✅${NC} $CONTAINER — running"
        HEALTHY=$((HEALTHY + 1))
    else
        echo -e "  ${RED}❌${NC} $CONTAINER — $STATUS"
    fi
done

# Test API endpoint
if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo -e "  ${GREEN}✅${NC} API endpoint — responding"
    HEALTHY=$((HEALTHY + 1))
else
    echo -e "  ${YELLOW}⚠️${NC}  API endpoint — not responding (may still be starting)"
fi
TOTAL=$((TOTAL + 1))

echo ""
echo "  Services healthy: $HEALTHY / $TOTAL"
echo ""

# ── Summary ─────────────────────────────────────────────────
IP=$(hostname -I | awk '{print $1}')
echo "========================================================"
echo "  DEPLOYMENT COMPLETE"
echo "========================================================"
echo ""
echo "  API:         http://${IP}:8000"
echo "  Health:      http://${IP}:8000/health"
echo "  Docs:        http://${IP}:8000/docs"
echo ""
echo "  Compose:     $COMPOSE_FILE"
echo "  Credentials: /root/.angavu/credentials"
echo "  Backups:     ${SCRIPT_DIR}/backups/ (daily at 2:00 AM)"
echo "  Logs:        ${SCRIPT_DIR}/logs/"
echo ""
echo "  Management:"
echo "    cd ${SCRIPT_DIR}"
echo "    $COMPOSE_CMD ps            # Status"
echo "    $COMPOSE_CMD logs -f       # Logs"
echo "    $COMPOSE_CMD restart       # Restart all"
echo "    $COMPOSE_CMD down          # Stop all"
echo "    $COMPOSE_CMD up -d         # Start all"
echo ""
echo "  WhatsApp (OpenWA):"
echo "    http://localhost:3000      # Dashboard — scan QR to connect"
echo ""
echo "========================================================"
