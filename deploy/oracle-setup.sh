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
echo "[1/8] Updating system..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl git build-essential pkg-config libssl-dev \
  libpq-dev cmake clang llvm-dev libclang-dev \
  python3-dev python3-pip openssl ufw >/dev/null 2>&1

# ── Install Rust ───────────────────────────────────────────
echo "[2/8] Installing Rust..."
if ! command -v rustc &>/dev/null; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y >/dev/null 2>&1
fi
# Source cargo env robustly (handles piped execution)
export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
export RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"
if [ -f "$CARGO_HOME/env" ]; then
  source "$CARGO_HOME/env"
elif [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi
export PATH="$CARGO_HOME/bin:$PATH"
rustc --version

# ── Install PostgreSQL + pgvector ──────────────────────────
echo "[3/8] Installing PostgreSQL and pgvector..."
# Add PGDG repo for latest PostgreSQL + pgvector on ARM64
sudo apt-get install -y -qq postgresql-common >/dev/null 2>&1
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y 2>/dev/null || true
sudo apt-get update -qq 2>/dev/null
sudo apt-get install -y -qq postgresql postgresql-contrib postgresql-16-pgvector >/dev/null 2>&1 || \
  sudo apt-get install -y -qq postgresql postgresql-contrib >/dev/null 2>&1
sudo systemctl enable postgresql
sudo systemctl start postgresql

# Create database and user
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true
# pgvector — try to install; if not available via apt, build from source
if ! sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null; then
  echo "  pgvector not found via apt, building from source..."
  cd /tmp
  git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git 2>/dev/null || true
  cd pgvector
  make -j"$(nproc)" 2>/dev/null
  sudo make install 2>/dev/null
  cd "$HOME"
  sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || echo "⚠️  pgvector install failed — vector features will be degraded"
fi
sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true

# ── Install Redis ──────────────────────────────────────────
echo "[4/8] Installing Redis..."
sudo apt-get install -y -qq redis-server >/dev/null 2>&1
sudo systemctl enable redis-server
sudo systemctl start redis-server

# ── Install ClickHouse (optional, for analytics) ───────────
echo "[5/8] Installing ClickHouse..."
if ! command -v clickhouse-server &>/dev/null; then
  sudo apt-get install -y -qq apt-transport-https ca-certificates gnupg 2>/dev/null
  # Use the official ClickHouse ARM64-compatible install script
  curl https://packages.clickhouse.com/rpm/lts/repodata/repomd.xml.key | \
    sudo gpg --dearmor -o /usr/share/keyrings/clickhouse-keyring.gpg 2>/dev/null || true
  ARCH=$(dpkg --print-architecture)
  echo "deb [signed-by=/usr/share/keyrings/clickhouse-keyring.gpg arch=$ARCH] https://packages.clickhouse.com/deb stable main" | \
    sudo tee /etc/apt/sources.list.d/clickhouse.list >/dev/null
  sudo apt-get update -qq 2>/dev/null
  sudo apt-get install -y -qq clickhouse-server clickhouse-client 2>/dev/null || \
    echo "⚠️  ClickHouse install optional — skipping (ARM64 may not have packages)"
  sudo systemctl enable clickhouse-server 2>/dev/null || true
  sudo systemctl start clickhouse-server 2>/dev/null || true
fi

# ── Clone and Build ────────────────────────────────────────
echo "[6/8] Cloning and building Angavu Backend (this takes 10-20 minutes on ARM)..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$USER:$USER" "$INSTALL_DIR"
git clone "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || (cd "$INSTALL_DIR" && git pull)
cd "$INSTALL_DIR"

# Set SQLX_OFFLINE=true — no .sqlx directory in repo, so compile-time query checks
# will use offline mode. Migrations run separately after build.
export SQLX_OFFLINE=true

# Build release (ARM64 — uses all 4 cores)
echo "  Building with cargo (this may take a while on first run)..."
cargo build --release --bin angavu-server 2>&1 | tail -5

# ── Configure and Start ────────────────────────────────────
echo "[7/8] Configuring and starting service..."

# Create environment file
# NOTE: main.rs reads ANGAVU_HOST and ANGAVU_PORT (not BIND_ADDR)
cat > "$INSTALL_DIR/.env" << EOF
DATABASE_URL=postgres://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
REDIS_URL=redis://localhost:6379/0
CLICKHOUSE_URL=http://localhost:8123/angavu
JWT_SECRET=$JWT_SECRET
ANGAVU_HOST=0.0.0.0
ANGAVU_PORT=$PORT
RUST_LOG=info
ENVIRONMENT=production
SQLX_OFFLINE=true
EOF

# Run migrations using the built-in migration binary
echo "  Running database migrations..."
"$INSTALL_DIR/target/release/angavu-migrate" 2>&1 || \
  echo "⚠️  Migration binary failed — tables will be auto-created on first start"

# Create systemd service
# NOTE: Binary name is "angavu-server" (from Cargo.toml [[bin]] name)
sudo tee /etc/systemd/system/angavu-backend.service >/dev/null << EOF
[Unit]
Description=Angavu Intelligence Backend
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/target/release/angavu-server
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable angavu-backend
sudo systemctl start angavu-backend

# ── Firewall ───────────────────────────────────────────────
echo "[8/8] Configuring firewall..."
sudo ufw allow 22/tcp >/dev/null 2>&1 || true
sudo ufw allow "$PORT/tcp" >/dev/null 2>&1 || true
sudo ufw --force enable >/dev/null 2>&1 || true

# ── Verify ─────────────────────────────────────────────────
sleep 3
if curl -sf "http://localhost:$PORT/health" >/dev/null 2>&1; then
  PUBLIC_IP=$(curl -sf --max-time 5 ifconfig.me 2>/dev/null || echo "<your-ip>")
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║  ✅ Angavu Intelligence Backend is LIVE!                 ║"
  echo "╠══════════════════════════════════════════════════════════╣"
  echo "║                                                          ║"
  printf "║  API:     http://%-20s:%-5s             ║\n" "$PUBLIC_IP" "$PORT"
  printf "║  Health:  http://%-20s:%-5s/health      ║\n" "$PUBLIC_IP" "$PORT"
  printf "║  Docs:    http://%-20s:%-5s/docs        ║\n" "$PUBLIC_IP" "$PORT"
  echo "║                                                          ║"
  echo "║  DB:      $DB_NAME @ localhost:5432              ║"
  echo "║  Redis:   localhost:6379                                 ║"
  echo "║                                                          ║"
  echo "║  Config:  $INSTALL_DIR/.env                              ║"
  echo "║  Logs:    journalctl -u angavu-backend -f               ║"
  echo "║                                                          ║"
  echo "║  ⚠️  HTTP only — add SSL with:                           ║"
  echo "║     sudo apt install certbot                             ║"
  echo "║     sudo certbot certonly --standalone -d yourdomain.com ║"
  echo "║                                                          ║"
  echo "╚══════════════════════════════════════════════════════════╝"
else
  echo ""
  echo "⚠️  Service started but health check failed. Check logs:"
  echo "   journalctl -u angavu-backend -n 50 --no-pager"
  echo ""
  echo "   Common fixes:"
  echo "   - Check DB: sudo -u postgres psql -d angavu"
  echo "   - Check Redis: redis-cli ping"
  echo "   - Check config: cat $INSTALL_DIR/.env"
fi
