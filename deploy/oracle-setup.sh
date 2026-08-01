#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Angavu Intelligence Backend — Oracle Free Tier One-Liner Deploy
# Usage: curl -sSL https://raw.githubusercontent.com/ovalentine964/angavu-intelligence-backend/main/deploy/oracle-setup.sh | bash
# 
# Oracle Free Tier: 4 ARM cores, 24GB RAM, 200GB storage
# This script sets up everything in one command.
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Angavu Intelligence Backend — Oracle Free Tier Deploy   ║"
echo "║  Africa's Economic Nervous System                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Configuration ──────────────────────────────────────────
REPO_URL="https://github.com/ovalentine964/angavu-intelligence-backend.git"
INSTALL_DIR="/opt/angavu"
DB_NAME="angavu"
DB_USER="angavu"
DB_PASS="$(openssl rand -hex 16)"
JWT_SECRET="$(openssl rand -hex 32)"
PORT=8080

# ── System Update ──────────────────────────────────────────
echo "[1/7] Updating system..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl git build-essential pkg-config libssl-dev \
  libpq-dev cmake clang llvm-dev libclang-dev >/dev/null 2>&1

# ── Install Rust ───────────────────────────────────────────
echo "[2/7] Installing Rust..."
if ! command -v rustc &>/dev/null; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y >/dev/null 2>&1
  source "$HOME/.cargo/env"
fi
rustc --version

# ── Install PostgreSQL 16 ──────────────────────────────────
echo "[3/7] Installing PostgreSQL 16..."
sudo apt-get install -y -qq postgresql postgresql-contrib >/dev/null 2>&1
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database and user
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true
sudo -u postgres psql -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || true
sudo -u postgres psql -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true

# ── Install Redis 7 ────────────────────────────────────────
echo "[4/7] Installing Redis 7..."
sudo apt-get install -y -qq redis-server >/dev/null 2>&1
sudo systemctl enable redis-server
sudo systemctl start redis-server

# ── Install ClickHouse (optional, for analytics) ───────────
echo "[5/7] Installing ClickHouse..."
if ! command -v clickhouse-server &>/dev/null; then
  sudo apt-get install -y -qq apt-transport-https ca-certificates gnupg 2>/dev/null
  curl -fsSL 'https://packages.clickhouse.com/rpm/lts/repodata/repomd.xml.key' | \
    sudo gpg --dearmor -o /usr/share/keyrings/clickhouse-keyring.gpg 2>/dev/null
  echo "deb [signed-by=/usr/share/keyrings/clickhouse-keyring.gpg] https://packages.clickhouse.com/deb stable main" | \
    sudo tee /etc/apt/sources.list.d/clickhouse.list >/dev/null
  sudo apt-get update -qq 2>/dev/null
  sudo apt-get install -y -qq clickhouse-server clickhouse-client 2>/dev/null || echo "ClickHouse install optional — skipping"
  sudo systemctl enable clickhouse-server 2>/dev/null || true
  sudo systemctl start clickhouse-server 2>/dev/null || true
fi

# ── Clone and Build ────────────────────────────────────────
echo "[6/7] Cloning and building Angavu Backend (this takes a few minutes)..."
sudo mkdir -p $INSTALL_DIR
sudo chown $USER:$USER $INSTALL_DIR
git clone $REPO_URL $INSTALL_DIR 2>/dev/null || (cd $INSTALL_DIR && git pull)
cd $INSTALL_DIR

# Build release
cargo build --release 2>&1 | tail -3

# ── Configure and Start ────────────────────────────────────
echo "[7/7] Configuring and starting service..."

# Create environment file
cat > $INSTALL_DIR/.env << EOF
DATABASE_URL=postgres://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
REDIS_URL=redis://localhost:6379
CLICKHOUSE_URL=http://localhost:8123/angavu
JWT_SECRET=$JWT_SECRET
BIND_ADDR=0.0.0.0:$PORT
RUST_LOG=info
ENVIRONMENT=production
EOF

# Run migrations
cd $INSTALL_DIR
cargo install sqlx-cli --no-default-features --features postgres 2>/dev/null || true
sqlx migrate run --source rust-api/migrations 2>/dev/null || echo "Migrations will run on first start"

# Create systemd service
sudo tee /etc/systemd/system/angavu-backend.service >/dev/null << EOF
[Unit]
Description=Angavu Intelligence Backend
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/target/release/angavu-intelligence-backend
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable angavu-backend
sudo systemctl start angavu-backend

# ── Verify ─────────────────────────────────────────────────
sleep 3
if curl -sf http://localhost:$PORT/health >/dev/null 2>&1; then
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║  ✅ Angavu Intelligence Backend is LIVE!                 ║"
  echo "╠══════════════════════════════════════════════════════════╣"
  echo "║                                                          ║"
  echo "║  API:     http://$(curl -sf ifconfig.me):$PORT             ║"
  echo "║  Health:  http://$(curl -sf ifconfig.me):$PORT/health      ║"
  echo "║  Docs:    http://$(curl -sf ifconfig.me):$PORT/docs        ║"
  echo "║                                                          ║"
  echo "║  DB:      $DB_NAME @ localhost:5432              ║"
  echo "║  Redis:   localhost:6379                                 ║"
  echo "║                                                          ║"
  echo "║  Config:  $INSTALL_DIR/.env                              ║"
  echo "║  Logs:    journalctl -u angavu-backend -f               ║"
  echo "║                                                          ║"
  echo "╚══════════════════════════════════════════════════════════╝"
else
  echo "⚠️  Service started but health check failed. Check logs:"
  echo "   journalctl -u angavu-backend -n 50"
fi
