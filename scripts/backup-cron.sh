#!/bin/bash
# ================================================================
# ANGAVU INTELLIGENCE — BACKUP CRON INSTALLER
# ================================================================
# Installs the daily backup cron job and log rotation.
# Usage: sudo bash backup-cron.sh
#
# What it does:
#   1. Installs cron job: daily backup at 2:00 AM
#   2. Sets up logrotate for /var/log/angavu-backup.log
#   3. Creates backup directory structure
#   4. Verifies cron service is running
# ================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup.sh"
LOG_FILE="${ANGAVU_BACKUP_LOG:-/var/log/angavu-backup.log}"
BACKUP_DIR="${ANGAVU_BACKUP_DIR:-/opt/backups/postgresql}"
CRON_SCHEDULE="${ANGAVU_BACKUP_CRON:-0 2 * * *}"

log() { echo -e "[\033[0;32mCRON\033[0m] $1"; }
error() { echo -e "[\033[0;31mERROR\033[0m] $1"; exit 1; }

# ── Pre-flight ───────────────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
    error "Must run as root. Use: sudo bash $0"
fi

if [ ! -x "$BACKUP_SCRIPT" ]; then
    error "Backup script not found or not executable: $BACKUP_SCRIPT"
fi

# ── Create directories ───────────────────────────────────────────
log "Creating backup directories..."
mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"
chmod 750 "$BACKUP_DIR"

# ── Install cron job ─────────────────────────────────────────────
log "Installing cron job: $CRON_SCHEDULE"

# Remove any existing angavu-backup cron entries
crontab -l 2>/dev/null | grep -v "angavu.*backup\.sh" | crontab - 2>/dev/null || true

# Add the new cron entry
CRON_LINE="$CRON_SCHEDULE $BACKUP_SCRIPT >> $LOG_FILE 2>&1"
(crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -

log "Cron entry installed:"
echo "  $CRON_LINE"

# ── Verify cron is running ───────────────────────────────────────
if systemctl is-active cron > /dev/null 2>&1; then
    log "✅ cron service is running"
elif systemctl is-active crond > /dev/null 2>&1; then
    log "✅ crond service is running"
else
    log "⚠️  cron service not detected — attempting to start..."
    systemctl start cron 2>/dev/null || systemctl start crond 2>/dev/null || true
    systemctl enable cron 2>/dev/null || systemctl enable crond 2>/dev/null || true
fi

# ── Install log rotation ─────────────────────────────────────────
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
    dateformat -%Y%m%d
}
LOGROTATE

log "Log rotation configured: /etc/logrotate.d/angavu-backup"
log "  Retention: 14 days of rotated logs"
log "  Compression: enabled (delayed one cycle)"

# ── Verify logrotate config ──────────────────────────────────────
if command -v logrotate > /dev/null 2>&1; then
    if logrotate -d /etc/logrotate.d/angavu-backup 2>&1 | grep -q "error"; then
        log "⚠️  logrotate config has issues — check /etc/logrotate.d/angavu-backup"
    else
        log "✅ logrotate config is valid"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────
echo ""
echo "========================================================"
echo "  BACKUP CRON INSTALLATION COMPLETE"
echo "========================================================"
echo ""
echo "  Schedule:    $CRON_SCHEDULE (daily at 2:00 AM)"
echo "  Script:      $BACKUP_SCRIPT"
echo "  Backup dir:  $BACKUP_DIR"
echo "  Log file:    $LOG_FILE"
echo "  Log rotate:  /etc/logrotate.d/angavu-backup"
echo ""
echo "  Manual run:  sudo bash $BACKUP_SCRIPT"
echo "  View cron:   crontab -l"
echo "  View logs:   tail -f $LOG_FILE"
echo "========================================================"
