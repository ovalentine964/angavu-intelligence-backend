#!/bin/bash
# ================================================================
# ANGAVU INTELLIGENCE — BACKUP CRON INSTALLER
# ================================================================
# Installs the daily backup cron job and log rotation.
# Usage: sudo bash scripts/backup-cron.sh
#
# What it does:
#   1. Creates /opt/backups/postgresql/ directory
#   2. Installs cron: daily backup at 2:00 AM
#   3. Sets up logrotate for /var/log/angavu-backup.log
#   4. Verifies cron service is running
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup.sh"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/postgresql}"
LOG_FILE="${LOG_FILE:-/var/log/angavu-backup.log}"
CRON_SCHEDULE="${ANGAVU_BACKUP_CRON:-0 2 * * *}"

log() { echo -e "[\033[0;32mCRON\033[0m] $1"; }
error() { echo -e "[\033[0;31mERROR\033[0m] $1"; exit 1; }

if [ "$(id -u)" -ne 0 ]; then
    error "Must run as root. Use: sudo bash $0"
fi

if [ ! -x "$BACKUP_SCRIPT" ]; then
    error "Backup script not found or not executable: $BACKUP_SCRIPT"
fi

# ── Create directories ──────────────────────────────────────
log "Creating backup directories..."
mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"
chmod 750 "$BACKUP_DIR"

# ── Install cron job ────────────────────────────────────────
log "Installing cron job: $CRON_SCHEDULE"

# Remove existing angavu-backup cron entries
crontab -l 2>/dev/null | grep -v "angavu.*backup\.sh" | crontab - 2>/dev/null || true

CRON_LINE="$CRON_SCHEDULE $BACKUP_SCRIPT >> $LOG_FILE 2>&1"
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

log "Cron entry installed:"
echo "  $CRON_LINE"

# ── Verify cron is running ──────────────────────────────────
if systemctl is-active cron > /dev/null 2>&1 || systemctl is-active crond > /dev/null 2>&1; then
    log "✅ cron service is running"
else
    log "⚠️  cron not detected — attempting to start..."
    systemctl start cron 2>/dev/null || systemctl start crond 2>/dev/null || true
    systemctl enable cron 2>/dev/null || systemctl enable crond 2>/dev/null || true
fi

# ── Install log rotation ────────────────────────────────────
log "Setting up log rotation..."

cat > /etc/logrotate.d/angavu-backup << LOGROTATE
$LOG_FILE {
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

log "Log rotation: /etc/logrotate.d/angavu-backup (14 days)"

if command -v logrotate > /dev/null 2>&1; then
    if logrotate -d /etc/logrotate.d/angavu-backup 2>&1 | grep -q "error"; then
        log "⚠️  logrotate config has issues"
    else
        log "✅ logrotate config is valid"
    fi
fi

echo ""
echo "========================================================"
echo "  BACKUP CRON INSTALLATION COMPLETE"
echo "========================================================"
echo "  Schedule:    $CRON_SCHEDULE (daily at 2:00 AM)"
echo "  Backup dir:  $BACKUP_DIR"
echo "  Log file:    $LOG_FILE"
echo "  Log rotate:  /etc/logrotate.d/angavu-backup"
echo "  Manual run:  sudo bash $BACKUP_SCRIPT"
echo "========================================================"
