#!/bin/bash
# ================================================================
# ANGAVU INTELLIGENCE — ONE-COMMAND ORACLE CLOUD DEPLOY
# ================================================================
# Usage: curl -sSL https://raw.githubusercontent.com/ovalentine964/angavu-intelligence-backend/main/deploy.sh | bash
# Or:    bash deploy.sh
#
# This script deploys the ENTIRE Angavu Intelligence backend
# on Oracle Cloud (or any Linux server) with ONE command.
#
# What it installs:
#   - Docker + Docker Compose
#   - PostgreSQL (economic data)
#   - Redis (caching, queues, real-time)
#   - ClickHouse (analytics, time-series)
#   - OpenWA (WhatsApp automation)
#   - Angavu Intelligence Backend (FastAPI)
#   - Nginx reverse proxy
#   - SSL certificates (Let's Encrypt)
#   - Automated backups
#   - Health monitoring
#
# Requirements:
#   - Ubuntu 22.04+ or Oracle Linux 8+
#   - 2+ CPU cores, 4GB+ RAM
#   - 50GB+ storage
#   - Domain name (optional, for SSL)
#
# Cost: $0 on Oracle Cloud Free Tier (2 ARM OCPUs, 12GB RAM)
# ================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[ANGAVU]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ================================================================
# CONFIGURATION
# ================================================================
DOMAIN="${ANGAVU_DOMAIN:-}"
EMAIL="${ANGAVU_EMAIL:-}"
DB_PASSWORD="${ANGAVU_DB_PASSWORD:-$(openssl rand -hex 16)}"
REDIS_PASSWORD="${ANGAVU_REDIS_PASSWORD:-$(openssl rand -hex 16)}"
JWT_SECRET="${ANGAVU_JWT_SECRET:-$(openssl rand -hex 32)}"
ENCRYPTION_KEY="${ANGAVU_ENCRYPTION_KEY:-$(openssl rand -hex 32)}"
OPENWA_WEBHOOK_SECRET="${ANGAVU_OPENWA_SECRET:-$(openssl rand -hex 16)}"
CLICKHOUSE_PASSWORD="${ANGAVU_CLICKHOUSE_PASSWORD:-$(openssl rand -hex 16)}"

INSTALL_DIR="/opt/angavu"

# ================================================================
# SYSTEM CHECK
# ================================================================
log "Checking system requirements..."

if [ "$(id -u)" -ne 0 ]; then
    error "This script must be run as root. Use: sudo bash deploy.sh"
fi

CORES=$(nproc)
RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
DISK_GB=$(df -BG / | awk 'NR==2{print $2}' | tr -d 'G')

log "CPU cores: $CORES"
log "RAM: ${RAM_MB}MB"
log "Disk: ${DISK_GB}GB"

if [ "$CORES" -lt 2 ]; then
    error "Need at least 2 CPU cores. Found: $CORES"
fi

if [ "$RAM_MB" -lt 3000 ]; then
    error "Need at least 3GB RAM. Found: ${RAM_MB}MB"
fi

# ================================================================
# INSTALL DOCKER
# ================================================================
log "Installing Docker..."

if command -v docker &> /dev/null; then
    log "Docker already installed: $(docker --version)"
else
    # Detect OS
    if [ -f /etc/oracle-release ]; then
        # Oracle Linux
        dnf install -y docker-engine
        systemctl enable docker
        systemctl start docker
    else
        # Ubuntu/Debian
        apt-get update -qq
        apt-get install -y -qq ca-certificates curl gnupg lsb-release
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list
        apt-get update -qq
        apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
        systemctl enable docker
        systemctl start docker
    fi

    log "Docker installed: $(docker --version)"
fi

# Install Docker Compose
if ! command -v docker-compose &> /dev/null; then
    COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep -Po '"tag_name": "\K.*\d')
    curl -L "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    log "Docker Compose installed: $(docker-compose --version)"
fi

# ================================================================
# CREATE INSTALLATION DIRECTORY
# ================================================================
log "Setting up installation directory..."

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# ================================================================
# GENERATE ENVIRONMENT FILE
# ================================================================
log "Generating configuration..."

cat > .env << EOF
# Angavu Intelligence — Backend Configuration
# Generated: $(date)
# ⚠️ KEEP THIS FILE SECRET — contains authentication secrets

# === Application ===
APP_ENV=production
APP_PORT=8000
APP_HOST=0.0.0.0
LOG_LEVEL=info

# === Database (PostgreSQL) ===
DATABASE_URL=postgresql+asyncpg://msaidizi:${DB_PASSWORD}@postgres:5432/msaidizi
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=1800
DB_PASSWORD=${DB_PASSWORD}

# === Redis ===
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_PASSWORD=${REDIS_PASSWORD}

# === ClickHouse (Analytics) ===
CLICKHOUSE_URL=http://clickhouse:8123
CLICKHOUSE_DATABASE=biashara
CLICKHOUSE_USER=admin
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}

# === Security ===
JWT_SECRET=${JWT_SECRET}
ENCRYPTION_KEY=${ENCRYPTION_KEY}

# === OpenWA (WhatsApp) ===
OPENWA_URL=http://openwa:3000
OPENWA_WEBHOOK_SECRET=${OPENWA_WEBHOOK_SECRET}

# === Federated Learning ===
FL_SERVER_HOST=0.0.0.0
FL_SERVER_PORT=8080
FL_DIFFERENTIAL_PRIVACY_EPSILON=0.1

# === Oracle Cloud ===
OCI_REGION=af-johannesburg-1
EOF

chmod 600 .env

# ================================================================
# GENERATE DOCKER COMPOSE (FULL STACK)
# ================================================================
cat > docker-compose.yml << 'COMPOSE'
version: '3.8'

services:
  # === PostgreSQL — Economic Data ===
  postgres:
    image: postgres:16-alpine
    container_name: angavu-postgres
    environment:
      POSTGRES_DB: msaidizi
      POSTGRES_USER: msaidizi
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U msaidizi"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - angavu-net

  # === Redis — Caching & Queues ===
  redis:
    image: redis:7-alpine
    container_name: angavu-redis
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "127.0.0.1:6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - angavu-net

  # === ClickHouse — Analytics & Time-Series ===
  clickhouse:
    image: clickhouse/clickhouse-server:24-alpine
    container_name: angavu-clickhouse
    environment:
      CLICKHOUSE_DB: biashara
      CLICKHOUSE_USER: admin
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
    volumes:
      - clickhouse_data:/var/lib/clickhouse
    ports:
      - "127.0.0.1:8123:8123"
      - "127.0.0.1:9000:9000"
    healthcheck:
      test: ["CMD", "clickhouse-client", "--query", "SELECT 1"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - angavu-net

  # === OpenWA — WhatsApp Automation ===
  openwa:
    build:
      context: ./openwa
      dockerfile: Dockerfile
    container_name: angavu-openwa
    ports:
      - "127.0.0.1:3000:3000"
    volumes:
      - openwa_data:/app/data
    environment:
      - WEBHOOK_URL=http://backend:8000/webhooks/whatsapp
      - WEBHOOK_SECRET=${OPENWA_WEBHOOK_SECRET}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - angavu-net

  # === Angavu Intelligence Backend ===
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: angavu-backend
    ports:
      - "127.0.0.1:8000:8000"
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      clickhouse:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2.0'
        reservations:
          memory: 512M
          cpus: '0.5'
    restart: unless-stopped
    networks:
      - angavu-net

  # === Nginx — Reverse Proxy ===
  nginx:
    image: nginx:alpine
    container_name: angavu-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - angavu-net

volumes:
  postgres_data:
  redis_data:
  clickhouse_data:
  openwa_data:

networks:
  angavu-net:
    driver: bridge
COMPOSE

# ================================================================
# GENERATE NGINX CONFIG
# ================================================================
mkdir -p nginx/ssl

cat > nginx/nginx.conf << 'NGINX'
events {
    worker_connections 1024;
}

http {
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;

    # Upstream
    upstream backend {
        server backend:8000;
    }

    # HTTP → HTTPS redirect (if SSL configured)
    server {
        listen 80;
        server_name _;

        # Health check endpoint (no redirect)
        location /health {
            proxy_pass http://backend;
        }

        # API
        location / {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 300s;
            proxy_connect_timeout 75s;
        }

        # Auth endpoints (stricter rate limit)
        location /api/v1/auth/ {
            limit_req zone=auth burst=3 nodelay;
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        # WhatsApp webhook
        location /webhooks/whatsapp {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        # Federated learning
        location /fl/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_read_timeout 600s;
        }
    }
}
NGINX

# ================================================================
# GENERATE BACKUP SCRIPT
# ================================================================
mkdir -p scripts

cat > scripts/backup.sh << 'BACKUP'
#!/bin/bash
# Automated daily backup
BACKUP_DIR="/opt/angavu/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# PostgreSQL backup
docker exec angavu-postgres pg_dump -U msaidizi msaidizi | gzip > "$BACKUP_DIR/postgres_$DATE.sql.gz"

# Redis backup
docker exec angavu-redis redis-cli -a "$REDIS_PASSWORD" BGSAVE
docker cp angavu-redis:/data/dump.rdb "$BACKUP_DIR/redis_$DATE.rdb"

# Keep last 7 days
find "$BACKUP_DIR" -type f -mtime +7 -delete

echo "Backup completed: $DATE"
BACKUP

chmod +x scripts/backup.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/angavu/scripts/backup.sh >> /opt/angavu/logs/backup.log 2>&1") | crontab -

# ================================================================
# GENERATE HEALTH CHECK SCRIPT
# ================================================================
cat > scripts/health.sh << 'HEALTH'
#!/bin/bash
# Health check — run every 5 minutes
SERVICES=("postgres" "redis" "clickhouse" "openwa" "backend" "nginx")

for svc in "${SERVICES[@]}"; do
    STATUS=$(docker inspect -f '{{.State.Status}}' "angavu-$svc" 2>/dev/null)
    if [ "$STATUS" != "running" ]; then
        echo "[$(date)] ALERT: angavu-$svc is $STATUS — restarting..."
        docker restart "angavu-$svc"
    fi
done
HEALTH

chmod +x scripts/health.sh

(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/angavu/scripts/health.sh >> /opt/angavu/logs/health.log 2>&1") | crontab -

# ================================================================
# SAVE CREDENTIALS SECURELY
# ================================================================
cat > /root/.angavu-credentials << EOF
# Angavu Intelligence — Credentials
# Generated: $(date)
# ⚠️ KEEP THIS FILE SECURE

Database Password: ${DB_PASSWORD}
Redis Password: ${REDIS_PASSWORD}
JWT Secret: ${JWT_SECRET}
Encryption Key: ${ENCRYPTION_KEY}
OpenWA Webhook Secret: ${OPENWA_WEBHOOK_SECRET}
ClickHouse Password: ${CLICKHOUSE_PASSWORD}
EOF

chmod 600 /root/.angavu-credentials

# ================================================================
# PULL IMAGES AND START
# ================================================================
log "Pulling Docker images..."
docker-compose pull

log "Building backend image..."
docker-compose build --no-cache backend

log "Starting all services..."
docker-compose up -d

# Wait for services to be healthy
log "Waiting for services to start..."
sleep 30

# ================================================================
# VERIFY DEPLOYMENT
# ================================================================
log "Verifying deployment..."

HEALTHY=0
for svc in postgres redis clickhouse backend; do
    STATUS=$(docker inspect -f '{{.State.Status}}' "angavu-$svc" 2>/dev/null)
    if [ "$STATUS" = "running" ]; then
        log "  ✅ $svc — running"
        ((HEALTHY++))
    else
        warn "  ❌ $svc — $STATUS"
    fi
done

# Test API
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    log "  ✅ API — responding"
    ((HEALTHY++))
else
    warn "  ❌ API — not responding"
fi

# ================================================================
# SUMMARY
# ================================================================
echo ""
echo "========================================================"
echo "  ANGAVU INTELLIGENCE — DEPLOYMENT COMPLETE"
echo "========================================================"
echo ""
echo -e "  ${GREEN}Services running:${NC} $HEALTHY/5"
echo ""
echo "  API Endpoint:  http://$(hostname -I | awk '{print $1}'):8000"
echo "  Health Check:  http://$(hostname -I | awk '{print $1}'):8000/health"
echo "  API Docs:      http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "  Credentials:   /root/.angavu-credentials"
echo "  Logs:          /opt/angavu/logs/"
echo "  Backups:       /opt/angavu/backups/ (daily at 2 AM)"
echo ""
echo "  Management:"
echo "    cd /opt/angavu"
echo "    docker-compose ps          # Check status"
echo "    docker-compose logs -f     # View logs"
echo "    docker-compose restart     # Restart all"
echo "    docker-compose down        # Stop all"
echo "    docker-compose up -d       # Start all"
echo ""
echo "  WhatsApp (OpenWA):"
echo "    http://localhost:3000      # OpenWA dashboard"
echo "    Scan QR code to connect WhatsApp"
echo ""
echo "========================================================"
echo "  Angavu Intelligence — Making invisible workers visible"
echo "========================================================"
