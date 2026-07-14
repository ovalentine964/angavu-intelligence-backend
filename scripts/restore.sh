#!/bin/bash
# ================================================================
# ANGAVU INTELLIGENCE — POSTGRESQL RESTORE
# ================================================================
# Restores pg_dump -Fc custom-format backups created by backup.sh.
#
# Usage:
#   restore.sh --list                    List available backups
#   restore.sh --latest                  Restore most recent backup
#   restore.sh --file <backup.dump.gz>   Restore specific backup
#   restore.sh --verify <backup.dump.gz> Verify backup integrity
#
# Options:
#   --drop-existing    Drop and recreate the database before restore
#   --yes              Skip confirmation prompt
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Source .env
if [ -f "${PROJECT_DIR}/.env" ]; then
    set -a
    source "${PROJECT_DIR}/.env"
    set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/postgresql}"
DB_USER="${POSTGRES_USER:-msaidizi}"
DB_NAME="${POSTGRES_DB:-msaidizi}"

ACTION=""
BACKUP_FILE=""
DROP_EXISTING=false
SKIP_CONFIRM=false

# ── Argument parsing ─────────────────────────────────────────
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
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

log() { echo -e "[\033[0;32mRESTORE\033[0m] $1"; }
warn() { echo -e "[\033[1;33mWARN\033[0m] $1"; }
error() { echo -e "[\033[0;31mERROR\033[0m] $1"; exit 1; }

# ── Find PostgreSQL container ───────────────────────────────
find_pg() {
    for name in biashara-postgres angavu-postgres msaidizi-postgres postgres; do
        if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
            echo "$name"
            return
        fi
    done
    error "PostgreSQL container not found"
}

# ── List backups ────────────────────────────────────────────
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
        printf "  %-5s  %-14s  %-10s  %s\n" "$i" "${bn#angavu_${DB_NAME}_}" "$sz" "$bn"
        ((i++))
    done < <(ls -t "$BACKUP_DIR"/*.dump.gz 2>/dev/null)
    echo ""
    local total=$(ls "$BACKUP_DIR"/*.dump.gz 2>/dev/null | wc -l)
    local disk=$(du -sh "$BACKUP_DIR" | cut -f1)
    echo "  Total: $total backup(s), $disk on disk"
}

# ── Verify backup ───────────────────────────────────────────
verify_backup() {
    local file="$1"
    [ ! -f "$file" ] && error "File not found: $file"
    log "Verifying: $(basename "$file")"
    echo -n "  gzip integrity... "
    gzip -t "$file" 2>/dev/null && echo "✅ OK" || { echo "❌ FAILED"; error "Corrupted"; }
    local size=$(du -h "$file" | cut -f1)
    log "Backup is valid ($size)"
}

# ── Restore ─────────────────────────────────────────────────
do_restore() {
    local file="$1"
    [ ! -f "$file" ] && error "Backup file not found: $file"
    verify_backup "$file"

    local PG_CONTAINER
    PG_CONTAINER=$(find_pg)

    if [ "$SKIP_CONFIRM" = false ]; then
        echo ""
        warn "⚠️  This will OVERWRITE the '$DB_NAME' database!"
        echo "  Source: $(basename "$file")"
        echo "  Target: $DB_NAME on $PG_CONTAINER"
        echo ""
        read -p "  Type 'yes' to confirm: " confirm
        [ "$confirm" != "yes" ] && { log "Cancelled."; exit 0; }
    fi

    # Terminate existing connections
    log "Terminating active connections to '$DB_NAME'..."
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

    # ── Post-restore verification ─────────────────────────────
    log "Verifying restore integrity..."
    local table_count
    table_count=$(docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ')
    local db_size
    db_size=$(docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c \
        "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" 2>/dev/null | tr -d ' ')

    echo -n "  ANALYZE... "
    docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "ANALYZE;" >/dev/null 2>&1 && echo "✅ OK" || echo "⚠️  Had issues"

    log "=== Restore completed ==="
    log "  Database: $DB_NAME"
    log "  Tables:   $table_count"
    log "  Size:     $db_size"
}

# ── Main ─────────────────────────────────────────────────────
case "$ACTION" in
    list)
        list_backups
        ;;
    latest)
        LATEST=$(ls -t "$BACKUP_DIR"/*.dump.gz 2>/dev/null | head -1)
        [ -z "$LATEST" ] && error "No backups found"
        log "Latest: $(basename "$LATEST")"
        do_restore "$LATEST"
        ;;
    restore)
        [[ "$BACKUP_FILE" != /* ]] && BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
        do_restore "$BACKUP_FILE"
        ;;
    verify)
        [[ "$BACKUP_FILE" != /* ]] && BACKUP_FILE="$BACKUP_DIR/$BACKUP_FILE"
        verify_backup "$BACKUP_FILE"
        ;;
    *)
        echo "Usage: $0 --list | --latest | --file <file> | --verify <file>"
        echo "  --drop-existing   Drop database before restore"
        echo "  --yes             Skip confirmation"
        exit 1
        ;;
esac
