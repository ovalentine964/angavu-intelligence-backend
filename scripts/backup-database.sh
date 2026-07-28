#!/usr/bin/env bash
# =============================================================================
# Database Backup Script for Angavu Intelligence Backend
# Creates compressed PostgreSQL backups with rotation
# =============================================================================

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/opt/angavu/backups}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-angavu}"
DB_USER="${DB_USER:-angavu}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date -u +"%Y%m%d-%H%M%S")
BACKUP_FILE="angavu-backup-${TIMESTAMP}.sql.gz"

# ── Functions ──────────────────────────────────────────────────────────────
log() {
    echo "[$(date -u +"%Y-%m-%d %H:%M:%S UTC")] $*"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

# ── Main ───────────────────────────────────────────────────────────────────
log "Starting database backup..."
log "Database: ${DB_NAME}@${DB_HOST}:${DB_PORT}"
log "Backup dir: ${BACKUP_DIR}"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Check connectivity
log "Checking database connectivity..."
PGPASSWORD="${DB_PASSWORD:-}" psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -c "SELECT 1" > /dev/null 2>&1 || die "Cannot connect to database"

# Create backup
log "Creating backup: ${BACKUP_FILE}"
PGPASSWORD="${DB_PASSWORD:-}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --format=custom \
    --compress=9 \
    --verbose \
    --no-owner \
    --no-privileges \
    --if-exists \
    --clean \
    > "${BACKUP_DIR}/${BACKUP_FILE}" 2>"${BACKUP_DIR}/backup-${TIMESTAMP}.log"

# Verify backup
BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
log "Backup size: ${BACKUP_SIZE}"

# Generate checksum
sha256sum "${BACKUP_DIR}/${BACKUP_FILE}" > "${BACKUP_DIR}/${BACKUP_FILE}.sha256"
log "Checksum: $(cat "${BACKUP_DIR}/${BACKUP_FILE}.sha256")"

# Record metadata
cat > "${BACKUP_DIR}/backup-${TIMESTAMP}.json" <<EOF
{
    "timestamp": "${TIMESTAMP}",
    "file": "${BACKUP_FILE}",
    "size": "${BACKUP_SIZE}",
    "database": "${DB_NAME}",
    "host": "${DB_HOST}",
    "port": ${DB_PORT},
    "format": "custom",
    "compression": 9,
    "checksum": "$(cut -d' ' -f1 "${BACKUP_DIR}/${BACKUP_FILE}.sha256")",
    "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

# Rotate old backups
log "Rotating backups older than ${RETENTION_DAYS} days..."
DELETED=0
find "${BACKUP_DIR}" -name "angavu-backup-*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete | while read -r f; do
    log "  Deleted: $f"
    DELETED=$((DELETED + 1))
done
# Also clean up associated files
find "${BACKUP_DIR}" -name "angavu-backup-*.sha256" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "backup-*.log" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
find "${BACKUP_DIR}" -name "backup-*.json" -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true

TOTAL_BACKUPS=$(find "${BACKUP_DIR}" -name "angavu-backup-*.sql.gz" | wc -l)
log "Total backups: ${TOTAL_BACKUPS}"

log "✅ Backup complete: ${BACKUP_DIR}/${BACKUP_FILE} (${BACKUP_SIZE})"

# ── Restore Instructions ──────────────────────────────────────────────────
cat <<'RESTORE'

═══════════════════════════════════════════════════════════════
  RESTORE INSTRUCTIONS
═══════════════════════════════════════════════════════════════

To restore this backup:

  # Full restore (drops and recreates objects):
  pg_restore -h <host> -p <port> -U <user> -d <database> \
    --no-owner --no-privileges --clean --if-exists \
    <backup-file.sql.gz>

  # Restore to a new database:
  createdb -h <host> -U <user> angavu_restored
  pg_restore -h <host> -U <user> -d angavu_restored \
    --no-owner --no-privileges \
    <backup-file.sql.gz>

  # List contents without restoring:
  pg_restore --list <backup-file.sql.gz>

  # Verify checksum:
  sha256sum -c <backup-file.sql.gz.sha256>

═══════════════════════════════════════════════════════════════
RESTORE
