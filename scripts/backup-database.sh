#!/bin/bash
# =============================================================================
# Angavu Intelligence — PostgreSQL Backup Script
# Creates compressed pg_dump, uploads to S3-compatible storage
# =============================================================================

set -euo pipefail

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/tmp/angavu-backups}"
DATABASE_URL="${DATABASE_URL:-postgresql://angavu:angavu_secret@localhost:5432/angavu}"
S3_BUCKET="${BACKUP_S3_BUCKET:-angavu-backups}"
S3_ENDPOINT="${BACKUP_S3_ENDPOINT:-}"  # e.g., https://s3.amazonaws.com or Oracle Object Storage
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="angavu-backup-${TIMESTAMP}.sql.gz"
CHECKSUM_FILE="${BACKUP_FILE}.sha256"

# Parse DATABASE_URL
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:]*\):.*|\1|p')
DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')
DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')

echo "=== Angavu Database Backup ==="
echo "Timestamp: ${TIMESTAMP}"
echo "Database:  ${DB_NAME}@${DB_HOST}:${DB_PORT}"
echo "Output:    ${BACKUP_DIR}/${BACKUP_FILE}"

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# ── Step 1: pg_dump with compression ─────────────────────────────────────────
echo "Creating backup..."
export PGPASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')

pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=custom \
    --compress=9 \
    --verbose \
    --no-owner \
    --no-privileges \
    --lock-wait-timeout=60000 \
    -f "${BACKUP_DIR}/${BACKUP_FILE}" 2>&1

unset PGPASSWORD

# ── Step 2: Generate checksum ─────────────────────────────────────────────────
echo "Generating checksum..."
sha256sum "${BACKUP_DIR}/${BACKUP_FILE}" > "${BACKUP_DIR}/${CHECKSUM_FILE}"

# ── Step 3: Verify backup integrity ───────────────────────────────────────────
echo "Verifying backup..."
BACKUP_SIZE=$(stat -c%s "${BACKUP_DIR}/${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_DIR}/${BACKUP_FILE}")
MIN_SIZE=1024  # Minimum 1KB

if [ "$BACKUP_SIZE" -lt "$MIN_SIZE" ]; then
    echo "ERROR: Backup file too small (${BACKUP_SIZE} bytes). Possible empty backup."
    exit 1
fi

echo "Backup size: $(numfmt --to=iec-i --suffix=B "$BACKUP_SIZE" 2>/dev/null || echo "${BACKUP_SIZE} bytes")"

# ── Step 4: Upload to S3-compatible storage ───────────────────────────────────
if [ -n "$S3_BUCKET" ]; then
    echo "Uploading to S3: s3://${S3_BUCKET}/"

    AWS_ARGS=""
    if [ -n "$S3_ENDPOINT" ]; then
        AWS_ARGS="--endpoint-url ${S3_ENDPOINT}"
    fi

    # Upload backup
    aws s3 cp \
        "${BACKUP_DIR}/${BACKUP_FILE}" \
        "s3://${S3_BUCKET}/postgres/${BACKUP_FILE}" \
        ${AWS_ARGS} \
        --storage-class STANDARD_IA \
        --only-show-errors

    # Upload checksum
    aws s3 cp \
        "${BACKUP_DIR}/${CHECKSUM_FILE}" \
        "s3://${S3_BUCKET}/postgres/${CHECKSUM_FILE}" \
        ${AWS_ARGS} \
        --only-show-errors

    echo "Upload complete."

    # ── Step 5: Clean up old backups ──────────────────────────────────────────
    echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
    CUTOFF_DATE=$(date -d "${RETENTION_DAYS} days ago" +%Y%m%d 2>/dev/null || \
                  date -v-${RETENTION_DAYS}d +%Y%m%d 2>/dev/null || \
                  echo "")

    if [ -n "$CUTOFF_DATE" ]; then
        aws s3 ls "s3://${S3_BUCKET}/postgres/" ${AWS_ARGS} | while read -r line; do
            FILE_DATE=$(echo "$line" | grep -oP 'angavu-backup-\K\d{8}' || true)
            if [ -n "$FILE_DATE" ] && [ "$FILE_DATE" -lt "$CUTOFF_DATE" ]; then
                FILE_NAME=$(echo "$line" | awk '{print $4}')
                if [ -n "$FILE_NAME" ]; then
                    echo "  Deleting old backup: ${FILE_NAME}"
                    aws s3 rm "s3://${S3_BUCKET}/postgres/${FILE_NAME}" ${AWS_ARGS} --only-show-errors
                fi
            fi
        done
    fi
fi

# ── Step 6: Clean up local files older than 7 days ────────────────────────────
echo "Cleaning up local backups older than 7 days..."
find "${BACKUP_DIR}" -name "angavu-backup-*.sql.gz*" -mtime +7 -delete 2>/dev/null || true

echo ""
echo "=== Backup Complete ==="
echo "File:     ${BACKUP_FILE}"
echo "Size:     $(numfmt --to=iec-i --suffix=B "$BACKUP_SIZE" 2>/dev/null || echo "${BACKUP_SIZE} bytes")"
echo "Checksum: $(cat "${BACKUP_DIR}/${CHECKSUM_FILE}")"
echo ""

# Output for CI
if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "backup_file=${BACKUP_FILE}" >> "$GITHUB_OUTPUT"
    echo "backup_size=${BACKUP_SIZE}" >> "$GITHUB_OUTPUT"
fi
