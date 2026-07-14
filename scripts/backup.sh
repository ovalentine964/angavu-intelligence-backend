#!/bin/bash
# =============================================================
# Angavu Intelligence — Automated Backup
# Backs up PostgreSQL, compresses, retains 7 days.
#
# Install via cron:
#   0 2 * * * /path/to/scripts/backup.sh
# =============================================================
set -euo pipefail

BACKUP_DIR="${ANGAVU_BACKUP_DIR:-/opt/angavu/backups}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATE=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${PROJECT_DIR}/logs/backup.log"

# Source .env for credentials
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG_FILE")"

log() { echo "[$(date -u '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"; }

log "Starting backup..."

# ── PostgreSQL dump ─────────────────────────────────────────
PG_CONTAINER=""
for name in biashara-postgres angavu-postgres msaidizi-postgres postgres; do
    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        PG_CONTAINER="$name"
        break
    fi
done

if [ -n "$PG_CONTAINER" ]; then
    # Try both possible DB users/names
    DB_USER=""
    DB_NAME=""
    for user in biashara msaidizi postgres; do
        if docker exec "$PG_CONTAINER" psql -U "$user" -c "SELECT 1" >/dev/null 2>&1; then
            DB_USER="$user"
            break
        fi
    done
    DB_USER="${DB_USER:-${POSTGRES_USER:-msaidizi}}"
    DB_NAME="${POSTGRES_DB:-msaidizi}"

    BACKUP_FILE="${BACKUP_DIR}/postgres_${DATE}.sql.gz"
    docker exec "$PG_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" 2>/dev/null | gzip > "$BACKUP_FILE"

    if [ -s "$BACKUP_FILE" ]; then
        SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        log "PostgreSQL backup: ${BACKUP_FILE} (${SIZE})"
    else
        log "WARNING: PostgreSQL backup is empty!"
        rm -f "$BACKUP_FILE"
    fi
else
    log "WARNING: PostgreSQL container not found — skipping DB backup"
fi

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
        log "Redis backup: ${REDIS_BACKUP}.gz"
    fi
fi

# ── Retention: delete backups older than 7 days ─────────────
DELETED=$(find "$BACKUP_DIR" -type f \( -name "*.sql.gz" -o -name "*.rdb.gz" -o -name "*.tar.gz" \) -mtime +7 -delete -print 2>/dev/null | wc -l)
if [ "$DELETED" -gt 0 ]; then
    log "Cleaned up $DELETED old backup(s)"
fi

log "Backup complete"
