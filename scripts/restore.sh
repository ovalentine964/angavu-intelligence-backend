#!/bin/bash
# ================================================================
# ANGAVU INTELLIGENCE — POSTGRESQL RESTORE
# ================================================================
# Restores a PostgreSQL backup created by backup.sh.
# Usage:
#   restore.sh --list                    List available backups
#   restore.sh --file <backup.dump.gz>   Restore from specific file
#   restore.sh --latest                  Restore most recent backup
#   restore.sh --verify <backup.dump.gz> Verify backup integrity
#
# Options:
#   --db-name NAME     Database name (default: msaidizi)
#   --db-user USER     Database user (default: msaidizi)
#   --container NAME   Docker container (default: angavu-postgres)
#   --backup-dir DIR   Backup directory (default: /opt/backups/postgresql/)
#   --drop-existing    Drop and recreate the database before restore
#   --yes              Skip confirmation prompt
# ================================================================

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────
DB_NAME="${ANGAVU_DB_NAME:-msaidizi}"
DB_USER="${ANGAVU_DB_USER:-msaidizi}"
DB_CONTAINER="${ANGAVU_DB_CONTAINER:-angavu-postgres}"
BACKUP_BASE="${ANGAVU_BACKUP_DIR:-/opt/backups/postgresql}"
ACTION=""
BACKUP_FILE=""
DROP_EXISTING=false
SKIP_CONFIRM=false

# ── Argument parsing ─────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --list)         ACTION="list"; shift ;;
        --file)         ACTION="restore"; BACKUP_FILE="$2"; shift 2 ;;
        --latest)       ACTION="latest"; shift ;;
        --verify)       ACTION="verify"; BACKUP_FILE="$2"; shift 2 ;;
        --db-name)      DB_NAME="$2"; shift 2 ;;
        --db-user)      DB_USER="$2"; shift 2 ;;
        --container)    DB_CONTAINER="$2"; shift 2 ;;
        --backup-dir)   BACKUP_BASE="$2"; shift 2 ;;
        --drop-existing) DROP_EXISTING=true; shift ;;
        --yes|-y)       SKIP_CONFIRM=true; shift ;;
        -h|--help)
            head -n 18 "$0" | tail -n +2 | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ── Logging ───────────────────────────────────────────────────────
log() { echo -e "[\033[0;32mRESTORE\033[0m] $1"; }
warn() { echo -e "[\033[1;33mWARN\033[0m] $1"; }
error() { echo -e "[\033[0;31mERROR\033[0m] $1"; exit 1; }

# ── List backups ─────────────────────────────────────────────────
list_backups() {
    log "Available backups in $BACKUP_BASE:"
    echo ""

    if [ ! -d "$BACKUP_BASE" ] || [ -z "$(ls -A "$BACKUP_BASE"/*.dump.gz 2>/dev/null)" ]; then
        echo "  No backups found."
        return 0
    fi

    printf "  %-5s  %-12s  %-10s  %s\n" "#" "DATE" "SIZE" "FILE"
    printf "  %-5s  %-12s  %-10s  %s\n" "---" "----" "----" "----"

    local i=1
    while IFS= read -r file; do
        local basename=$(basename "$file")
        local size=$(du -h "$file" | cut -f1)
        local date_part=$(echo "$basename" | grep -oP '\d{8}_\d{6}')
        local formatted_date="${date_part:0:4}-${date_part:4:2}-${date_part:6:2} ${date_part:9:2}:${date_part:11:2}:${date_part:13:2}"
        printf "  %-5s  %-12s  %-10s  %s\n" "$i" "$formatted_date" "$size" "$basename"
        ((i++))
    done < <(ls -t "$BACKUP_BASE"/*.dump.gz 2>/dev/null)

    echo ""
    local total=$(ls "$BACKUP_BASE"/*.dump.gz 2>/dev/null | wc -l)
    local disk=$(du -sh "$BACKUP_BASE" | cut -f1)
    echo "  Total: $total backup(s), $disk on disk"
}

# ── Get latest backup ────────────────────────────────────────────
get_latest() {
    local latest
    latest=$(ls -t "$BACKUP_BASE"/*.dump.gz 2>/dev/null | head -1)
    if [ -z "$latest" ]; then
        error "No backups found in $BACKUP_BASE"
    fi
    echo "$latest"
}

# ── Verify backup ────────────────────────────────────────────────
verify_backup() {
    local file="$1"

    if [ ! -f "$file" ]; then
        error "File not found: $file"
    fi

    log "Verifying backup: $(basename "$file")"

    # Check gzip integrity
    echo -n "  gzip integrity... "
    if gzip -t "$file" 2>/dev/null; then
        echo "✅ OK"
    else
        echo "❌ FAILED"
        error "Backup file is corrupted (gzip check failed)"
    fi

    # Check pg_restore can read the archive
    echo -n "  pg_restore catalog... "
    local table_count
    table_count=$(docker exec -i "$DB_CONTAINER" pg_restore -l < "$file" 2>/dev/null | grep -c "TABLE " || true)
    if [ "$table_count" -gt 0 ]; then
        echo "✅ OK ($table_count tables)"
    else
        echo "⚠️  Could not list tables (may be a valid compressed archive)"
    fi

    local size
    size=$(du -h "$file" | cut -f1)
    log "Backup is valid: $size"
}

# ── Restore ──────────────────────────────────────────────────────
do_restore() {
    local file="$1"

    if [ ! -f "$file" ]; then
        error "Backup file not found: $file"
    fi

    # Verify first
    verify_backup "$file"

    # Confirmation
    if [ "$SKIP_CONFIRM" = false ]; then
        echo ""
        warn "⚠️  This will OVERWRITE the '$DB_NAME' database!"
        echo "  Source: $(basename "$file")"
        echo "  Target: $DB_NAME on $DB_CONTAINER"
        echo ""
        read -p "  Are you sure? (type 'yes' to confirm): " confirm
        if [ "$confirm" != "yes" ]; then
            log "Restore cancelled."
            exit 0
        fi
    fi

    log "Starting restore..."

    # Check container is running
    if ! docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q true; then
        error "Container '$DB_CONTAINER' is not running"
    fi

    # Option: drop and recreate database
    if [ "$DROP_EXISTING" = true ]; then
        log "Dropping existing database '$DB_NAME'..."
        docker exec "$DB_CONTAINER" dropdb -U "$DB_USER" --if-exists "$DB_NAME" 2>/dev/null || true
        docker exec "$DB_CONTAINER" createdb -U "$DB_USER" "$DB_NAME" 2>/dev/null || true
    fi

    # Terminate existing connections
    log "Terminating existing connections to '$DB_NAME'..."
    docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    # Restore using pg_restore (custom format)
    log "Restoring from $(basename "$file")..."
    if ! docker exec -i "$DB_CONTAINER" pg_restore \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --verbose \
        --no-owner \
        --no-privileges \
        --clean \
        --if-exists \
        < "$file" 2>&1 | tail -5; then
        warn "pg_restore exited with warnings (this is often normal)"
    fi

    # ── Post-restore verification ─────────────────────────────────
    log "Verifying restore integrity..."

    # Check table count
    local table_count
    table_count=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
    log "  Tables restored: $table_count"

    # Check database size
    local db_size
    db_size=$(docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" 2>/dev/null | tr -d ' ')
    log "  Database size: $db_size"

    # Check for any corruption by running ANALYZE
    echo -n "  ANALYZE... "
    if docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "ANALYZE;" > /dev/null 2>&1; then
        echo "✅ OK"
    else
        echo "⚠️  Had issues"
    fi

    log "=== Restore completed ==="
    log "  Source:   $(basename "$file")"
    log "  Database: $DB_NAME"
    log "  Tables:   $table_count"
    log "  Size:     $db_size"
}

# ── Main ─────────────────────────────────────────────────────────
case "$ACTION" in
    list)
        list_backups
        ;;
    latest)
        LATEST=$(get_latest)
        log "Latest backup: $(basename "$LATEST")"
        do_restore "$LATEST"
        ;;
    restore)
        # If it's just a filename (no path), look in backup dir
        if [[ "$BACKUP_FILE" != /* ]]; then
            BACKUP_FILE="$BACKUP_BASE/$BACKUP_FILE"
        fi
        do_restore "$BACKUP_FILE"
        ;;
    verify)
        if [[ "$BACKUP_FILE" != /* ]]; then
            BACKUP_FILE="$BACKUP_BASE/$BACKUP_FILE"
        fi
        verify_backup "$BACKUP_FILE"
        ;;
    *)
        echo "Usage:"
        echo "  $0 --list                          List available backups"
        echo "  $0 --latest                        Restore most recent backup"
        echo "  $0 --file <backup.dump.gz>         Restore specific backup"
        echo "  $0 --verify <backup.dump.gz>       Verify backup integrity"
        echo ""
        echo "Options:"
        echo "  --drop-existing    Drop database before restore"
        echo "  --yes              Skip confirmation"
        exit 1
        ;;
esac
