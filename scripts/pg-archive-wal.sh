#!/bin/bash
# =============================================================================
# PostgreSQL WAL Archive Command
# Archives WAL segments to a local directory for point-in-time recovery.
# RPO target: < 1 hour (WAL segments ship continuously via archive_command)
#
# Usage as archive_command in postgresql.conf:
#   archive_command = '/scripts/pg-archive-wal.sh %p %f'
#
# In Docker Compose, mount this script and the archive volume.
# =============================================================================

set -euo pipefail

WAL_PATH="$1"
WAL_FILE="$2"
ARCHIVE_DIR="${PG_WAL_ARCHIVE_DIR:-/var/lib/postgresql/wal_archive}"

# Create archive directory if it doesn't exist
mkdir -p "$ARCHIVE_DIR"

# Copy the WAL segment atomically (write to tmp, then move)
cp "$WAL_PATH" "$ARCHIVE_DIR/$WAL_FILE.tmp"
mv "$ARCHIVE_DIR/$WAL_FILE.tmp" "$ARCHIVE_DIR/$WAL_FILE"

# Retain only last 7 days of WAL files (cleanup old archives)
find "$ARCHIVE_DIR" -name "0000*" -type f -mtime +7 -delete 2>/dev/null || true

exit 0
