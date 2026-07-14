#!/bin/bash
# ================================================================
# ANGAVU INTELLIGENCE — AUTOMATED BACKUP
# ================================================================
# Creates pg_dump -Fc (custom format) backups with gzip compression.
# Backs up PostgreSQL, Redis, and ClickHouse. Retains 7 daily backups.
#
# Usage: bash scripts/backup.sh
# Cron:  0 2 * * * /opt/angavu/scripts/backup.sh
#
# Environment overrides:
#   POSTGRES_USER, POSTGRES_DB, REDIS_PASSWORD
#   BACKUP_DIR  (default: /opt/backups/postgresql)
#   LOG_FILE    (default: /var/log/angavu-backup.log)
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source .env for credentials
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/postgresql}"
LOG_FILE="${LOG_FILE:-/var/log/angavu-backup.log}"
DATE="$(date +%Y%m%d_%H%M%S)"

mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }
error_exit() { log "ERROR: $1"; exit 1; }

# Cleanup partial files on failure
cleanup() {
    local rc=$?
    if [ $rc -ne 0 ]; then
        log "Backup FAILED (exit code: $rc)"
        rm -f "${BACKUP_DIR}/angavu_*_${DATE}.dump" "${BACKUP_DIR}/angavu_*_${DATE}.dump.gz"
    fi
    return $rc
}
trap cleanup EXIT

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
    error_exit "PostgreSQL container not found"
fi

DB_USER="${POSTGRES_USER:-msaidizi}"
DB_NAME="${POSTGRES_DB:-msaidizi}"

log "Database: $DB_NAME | User: $DB_USER | Container: $PG_CONTAINER"

# Verify database is accepting connections
if ! docker exec "$PG_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" > /dev/null 2>&1; then
    error_exit "Database '$DB_NAME' is not accepting connections"
fi

# ── pg_dump -Fc (custom format) ────────────────────────────
DUMP_FILE="${BACKUP_DIR}/angavu_${DB_NAME}_${DATE}.dump"
BACKUP_FILE="${DUMP_FILE}.gz"

log "Creating pg_dump (custom format)..."

if ! docker exec "$PG_CONTAINER" pg_dump \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -Fc \
    --no-owner \
    --no-privileges \
    > "$DUMP_FILE" 2>>"$LOG_FILE"; then
    error_exit "pg_dump failed"
fi

# ── Compress ────────────────────────────────────────────────
log "Compressing with gzip..."
gzip -f "$DUMP_FILE"

if [ ! -s "$BACKUP_FILE" ]; then
    error_exit "Backup file is empty after compression"
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)

# ── Verify integrity ────────────────────────────────────────
log "Verifying backup integrity..."
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    error_exit "Backup file is corrupted (gzip check failed)"
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
log "=== Backup complete === ($TOTAL pg backups on disk, $TOTAL_SIZE total)"

exit 0
