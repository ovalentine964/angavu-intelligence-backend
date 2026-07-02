#!/usr/bin/env bash
# =============================================================
# Biashara Intelligence — One-Command Oracle Cloud Deploy
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ovalentine964/biashara-intelligence-backend/main/deploy.sh | bash
#
# Or with env vars:
#   DOMAIN=api.biashara.ai EMAIL=you@example.com PROFILE=arm bash deploy.sh
#
# Profiles:
#   micro  — E2.Micro (1GB RAM): SQLite, 1 worker, no Redis/Postgres
#   arm    — A1.Flex  (24GB RAM): PostgreSQL, 4 workers, Redis
# =============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; }
info() { echo -e "${BLUE}[i]${NC} $*"; }

# ─── Configuration ────────────────────────────────────────
REPO_URL="https://github.com/ovalentine964/biashara-intelligence-backend.git"
INSTALL_DIR="${INSTALL_DIR:-/opt/biashara}"
PROFILE="${PROFILE:-micro}"
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(openssl rand -hex 32)}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(openssl rand -hex 16)}"

# ─── Preflight checks ────────────────────────────────────
if [ "$(id -u)" -eq 0 ]; then
    err "Don't run as root. Run as a regular user with sudo access."
    exit 1
fi

ARCH=$(uname -m)
info "Architecture: ${ARCH}"
info "Profile: ${PROFILE}"
info "Install dir: ${INSTALL_DIR}"

# ─── Step 1: System packages ─────────────────────────────
log "Updating system packages..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

# ─── Step 2: Install Docker ──────────────────────────────
if ! command -v docker &>/dev/null; then
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    # Activate group in current shell
    newgrp docker || true
    log "Docker installed"
else
    log "Docker already installed ($(docker --version))"
fi

# Ensure Docker Compose plugin
if ! docker compose version &>/dev/null; then
    log "Installing Docker Compose plugin..."
    sudo apt-get install -y -qq docker-compose-plugin
fi

# ─── Step 3: Clone / update repo ─────────────────────────
if [ -d "${INSTALL_DIR}/.git" ]; then
    log "Updating existing installation..."
    cd "${INSTALL_DIR}"
    git pull --ff-only origin main
else
    log "Cloning repository..."
    sudo mkdir -p "${INSTALL_DIR}"
    sudo chown "$USER:$USER" "${INSTALL_DIR}"
    git clone --depth 1 "${REPO_URL}" "${INSTALL_DIR}"
    cd "${INSTALL_DIR}"
fi

# ─── Step 4: Generate .env ───────────────────────────────
if [ ! -f .env ]; then
    log "Generating .env file..."

    DB_URL="sqlite+aiosqlite:///./data/biashara.db"
    REDIS_URL=""

    if [ "${PROFILE}" = "arm" ]; then
        DB_URL="postgresql+asyncpg://biashara:${DB_PASSWORD}@postgres:5432/biashara"
        REDIS_URL="redis://redis:6379/0"
    fi

    cat > .env <<EOF
# ─── Biashara Intelligence — Oracle Cloud Config ─────────
# Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
# Profile: ${PROFILE}

# Application
APP_ENV=production
APP_NAME=Biashara Intelligence
DEBUG=false
LOG_LEVEL=WARNING
API_V1_PREFIX=/api/v1

# Database
DATABASE_URL=${DB_URL}
DATABASE_POOL_SIZE=$([ "${PROFILE}" = "arm" ] && echo "10" || echo "5")
DATABASE_MAX_OVERFLOW=$([ "${PROFILE}" = "arm" ] && echo "5" || echo "2")
DATABASE_ECHO=false

# Redis (empty = in-memory cache fallback)
REDIS_URL=${REDIS_URL}

# Security — DO NOT SHARE
SECRET_KEY=${JWT_SECRET}
JWT_SECRET_KEY=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30
ENCRYPTION_KEY=${ENCRYPTION_KEY}
DATA_ENCRYPTION_SALT=$(openssl rand -hex 8)
OPENWA_WEBHOOK_SECRET=${WEBHOOK_SECRET}

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_BURST=10

# CORS
CORS_ORIGINS=$([ -n "${DOMAIN}" ] && echo "https://${DOMAIN}" || echo "*")

# External APIs (optional — fill in later)
GROQ_API_KEY=
DEEPSEEK_API_KEY=

# Sentry (optional)
SENTRY_DSN=
EOF

    log ".env generated — secrets auto-created"
    warn "Save these credentials somewhere safe!"
    echo "  DB_PASSWORD=${DB_PASSWORD}"
    echo "  JWT_SECRET=${JWT_SECRET}"
    echo "  ENCRYPTION_KEY=${ENCRYPTION_KEY}"
else
    log ".env already exists — keeping existing config"
fi

# ─── Step 5: Create data directory ──────────────────────
mkdir -p data logs

# ─── Step 6: Start services ─────────────────────────────
log "Starting Biashara Intelligence (profile: ${PROFILE})..."

COMPOSE_FILE="docker-compose.oracle.yml"

if [ "${PROFILE}" = "arm" ]; then
    docker compose -f "${COMPOSE_FILE}" --profile arm up -d --build
else
    docker compose -f "${COMPOSE_FILE}" up -d --build api
fi

# ─── Step 7: Wait for health check ──────────────────────
info "Waiting for API to be ready..."
RETRIES=30
until [ $RETRIES -eq 0 ] || docker compose -f "${COMPOSE_FILE}" exec -T api curl -sf http://localhost:8000/health &>/dev/null; do
    RETRIES=$((RETRIES - 1))
    sleep 2
    echo -n "."
done
echo

if [ $RETRIES -eq 0 ]; then
    err "API failed to start. Check logs with:"
    echo "  cd ${INSTALL_DIR} && docker compose -f ${COMPOSE_FILE} logs api"
    exit 1
fi

log "API is healthy!"

# ─── Step 8: Nginx reverse proxy ────────────────────────
if [ -n "${DOMAIN}" ]; then
    log "Setting up nginx + SSL for ${DOMAIN}..."

    sudo apt-get install -y -qq nginx certbot python3-certbot-nginx

    # Nginx config
    sudo tee "/etc/nginx/sites-available/biashara" > /dev/null <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        proxy_connect_timeout 10s;
    }
}
NGINX

    sudo ln -sf /etc/nginx/sites-available/biashara /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo nginx -t && sudo systemctl reload nginx

    # SSL
    if [ -n "${EMAIL}" ]; then
        sudo certbot --nginx -d "${DOMAIN}" --email "${EMAIL}" --agree-tos --non-interactive --redirect
        log "SSL configured for ${DOMAIN}"
    else
        warn "Set EMAIL env var to enable auto-SSL with Let's Encrypt"
    fi
else
    warn "No DOMAIN set — skipping nginx/SSL. API available at http://$(curl -s ifconfig.me):8000"
fi

# ─── Step 9: UFW firewall ───────────────────────────────
if command -v ufw &>/dev/null; then
    sudo ufw allow 22/tcp 2>/dev/null || true
    sudo ufw allow 80/tcp 2>/dev/null || true
    sudo ufw allow 443/tcp 2>/dev/null || true
    sudo ufw --force enable 2>/dev/null || true
    log "Firewall configured (22, 80, 443)"
fi

# ─── Done ─────────────────────────────────────────────────
echo
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Biashara Intelligence — Deployed Successfully! 🇰🇪    ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC}  API:       http${DOMAIN:+s}://${DOMAIN:-localhost}:8000              ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Health:    http${DOMAIN:+s}://${DOMAIN:-localhost}:8000/health        ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Docs:      http${DOMAIN:+s}://${DOMAIN:-localhost}:8000/docs          ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Profile:   ${PROFILE}                                  ${GREEN}║${NC}"
echo -e "${GREEN}║${NC}  Install:   ${INSTALL_DIR}                             ${GREEN}║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo
echo "Manage:"
echo "  cd ${INSTALL_DIR}"
echo "  docker compose -f ${COMPOSE_FILE} logs -f      # View logs"
echo "  docker compose -f ${COMPOSE_FILE} restart       # Restart"
echo "  docker compose -f ${COMPOSE_FILE} down          # Stop"
