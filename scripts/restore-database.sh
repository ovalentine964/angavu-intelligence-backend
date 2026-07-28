#!/bin/bash
# =============================================================================
# Angavu Intelligence — PostgreSQL Restore Script
# Restores from pg_dump backup (local file or S3)
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/tmp/angavu-backups}"
DATABASE_URL="${DATABASE_URL:-postgresql://angavu:angavu_secret@localhost:5432/angavu}"
S3_BUCKET="${BACKUP_S3_BUCKET:-angavu-backups}"
S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"
BACKUP_FILE="${1:-}"  # First argument: backup file path or S3 key

# Parse DATABASE_URL
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
export PGPASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')

usage() {
    echo "Usage: $0 <backup-file-or-s3-key>"
    echo ""
    echo "Examples:"
    echo "  $0 /tmp/angavu-backups/angavu-backup-20260728-120000.sql.gz"
    echo "  $0 postgres/angavu-backup-20260728-120000.sql.gz"
    echo ""
    echo "Environment variables:"
    echo "  DATABASE_URL         PostgreSQL connection string"
    echo "  BACKUP_S3_BUCKET     S3 bucket name (default: angavu-backups)"
    echo "  BACKUP_S3_ENDPOINT   S3 endpoint URL (for Oracle Object Storage, etc.)"
    echo "  BACKUP_DIR           Local backup directory (default: /tmp/angavu-backups)"
    echo "  FORCE_RESTORE        Set to 'yes' to skip confirmation"
    exit 1
}

if [ -z "$BACKUP_FILE" ]; then
    usage
fi

echo "=== Angavu Database Restore ==="
echo "Target:   ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo "Source:   ${BACKUP_FILE}"

# ── Step 1: Download from S3 if needed ────────────────────────────────────────
LOCAL_FILE="$BACKUP_FILE"
if [[ "$BACKUP_FILE" == s3://* ]] || [[ ! -f "$BACKUP_FILE" ]]; then
    echo "Downloading from S3..."
    mkdir -p "${BACKUP_DIR}"

    S3_KEY="$BACKUP_FILE"
    if [[ "$BACKUP_FILE" == s3://* ]]; then
        S3_KEY=$(echo "$BACKUP_FILE" | sed 's|s3://[^/]*/||')
    fi

    AWS_ARGS=""
    if [ -n "$S3_ENDPOINT" ]; then
        AWS_ARGS="--endpoint-url ${S3_ENDPOINT}"
    fi

    LOCAL_FILE="${BACKUP_DIR}/$(basename "$S3_KEY")"
    aws s3 cp "s3://${S3_BUCKET}/${S3_KEY}" "${LOCAL_FILE}" ${AWS_ARGS} --only-show-errors

    # Download and verify checksum
    CHECKSUM_KEY="${S3_KEY}.sha256"
    LOCAL_CHECKSUM="${LOCAL_FILE}.sha256"
    if aws s3 ls "s3://${S3_BUCKET}/${CHECKSUM_KEY}" ${AWS_ARGS} > /dev/null 2>&1; then
        aws s3 cp "s3://${S3_BUCKET}/${CHECKSUM_KEY}" "${LOCAL_CHECKSUM}" ${AWS_ARGS} --only-show-errors
        echo "Verifying checksum..."
        if ! sha256sum -c "${LOCAL_CHECKSUM}"; then
            echo "ERROR: Checksum verification failed!"
            exit 1
        fi
        echo "Checksum OK."
    else
        echo "WARNING: No checksum file found, skipping verification."
    fi
fi

if [ ! -f "$LOCAL_FILE" ]; then
    echo "ERROR: Backup file not found: ${LOCAL_FILE}"
    exit 1
fi

BACKUP_SIZE=$(stat -c%s "$LOCAL_FILE" 2>/dev/null || stat -f%z "$LOCAL_FILE")
echo "Backup size: $(numfmt --to=iec-i --suffix=B "$BACKUP_SIZE" 2>/dev/null || echo "${BACKUP_SIZE} bytes")"

# ── Step 2: Confirmation ──────────────────────────────────────────────────────
if [ "${FORCE_RESTORE:-}" != "yes" ]; then
    echo ""
    echo "⚠️  WARNING: This will REPLACE all data in '${DB_NAME}'!"
    echo "    A pre-restore backup will be created automatically."
    echo ""
    read -p "Continue? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "Restore cancelled."
        exit 0
    fi
fi

# ── Step 3: Create pre-restore backup ─────────────────────────────────────────
echo "Creating pre-restore safety backup..."
PRE_RESTORE_FILE="pre-restore-$(date +%Y%m%d-%H%M%S).sql.gz"
pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=custom \
    --compress=9 \
    --no-owner \
    -f "${BACKUP_DIR}/${PRE_RESTORE_FILE}" 2>&1 || echo "WARNING: Pre-restore backup failed (database may be empty)"

echo "Pre-restore backup: ${BACKUP_DIR}/${PRE_RESTORE_FILE}"

# ── Step 4: Terminate existing connections ─────────────────────────────────────
echo "Terminating existing connections..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "
    SELECT pg_terminate_backend(pid)
    FROM pg_stat_activity
    WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();
" 2>/dev/null || true

# ── Step 5: Drop and recreate database ────────────────────────────────────────
echo "Dropping and recreating database..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "
    DROP DATABASE IF EXISTS ${DB_NAME};
    CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
" 2>&1

# ── Step 6: Restore ───────────────────────────────────────────────────────────
echo "Restoring backup..."
pg_restore \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --verbose \
    --no-owner \
    --no-privileges \
    --single-transaction \
    "${LOCAL_FILE}" 2>&1

# ── Step 7: Verify ────────────────────────────────────────────────────────────
echo ""
echo "Verifying restore..."
TABLE_COUNT=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')

echo "Tables restored: ${TABLE_COUNT}"

unset PGPASSWORD

echo ""
echo "=== Restore Complete ==="
echo "Database:      ${DB_NAME}"
echo "Tables:        ${TABLE_COUNT}"
echo "Pre-restore:   ${BACKUP_DIR}/${PRE_RESTORE_FILE}"
echo ""
echo "Run migrations to ensure schema is up to date:"
echo "  docker compose run --rm api /app/angavu-migrate"
