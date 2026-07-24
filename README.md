<div align="center">

# ⚙️ Angavu Intelligence Backend

### AI-Powered CFO for Informal Workers — Backend Platform

**Rust-primary backend powering Msaidizi, the CFO for 600 million informal workers.** 15 revenue intelligence engines with superagent orchestration, post-quantum cryptography, and privacy-first data processing.

> Msaidizi is not an assistant — it's a **CFO** that delivers daily briefings, cash flow forecasting, savings advice, and credit building for workers who never had one.

[![Rust](https://img.shields.io/badge/Rust-1.75%2B-orange.svg)](https://www.rust-lang.org)
[![Axum](https://img.shields.io/badge/Axum-Web_Framework-blue.svg)](https://github.com/tokio-rs/axum)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%2B-blue.svg)](https://www.postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](Dockerfile)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)
[![PQC](https://img.shields.io/badge/PQC-ML--KEM--768-brightgreen.svg)](#security)
[![Privacy](https://img.shields.io/badge/Privacy-k--Anonymity-green.svg)](#security)

[API Docs](#api-documentation) · [Quick Start](#quick-start) · [Deployment](#deployment) · [Security](#security)

</div>

---

> Rust-primary backend for the Angavu superagent-powered CFO platform for informal workers.
> Python is used **only** for LLM inference — all business logic, APIs, and data processing run in Rust.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Nginx (TLS + Rate Limit)                 │
├─────────────────────────────────────────────────────────────────┤
│                    Axum HTTP Server (Rust)                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │  REST API    │ │  WebSocket   │ │  Superagent  │            │
│  │  /api/v1/*   │ │  /ws         │ │  /superagent │            │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘            │
│         │                │                │                     │
│  ┌──────┴────────────────┴────────────────┴───────┐            │
│  │              OODA Orchestrator                   │            │
│  │  Observe → Orient → Decide → Act               │            │
│  └────────────────────┬───────────────────────────┘            │
│                       │                                         │
│  ┌────────────────────┴───────────────────────────┐            │
│  │           Capability Modules (Rust)              │            │
│  │  Market Research │ Credit Scoring │ FMCG Intel   │            │
│  │  Distribution    │ Health Metrics │ Economic     │            │
│  └────────────────────┬───────────────────────────┘            │
│                       │                                         │
│  ┌─────────┐  ┌──────┴──────┐  ┌────────────┐                 │
│  │PyO3/FFI │  │  5-Layer    │  │ Guardrails │                 │
│  │→ Python │  │  Memory     │  │ k-anon/DP  │                 │
│  │  LLM    │  │  Hierarchy  │  │ PQC crypto │                 │
│  └─────────┘  └─────────────┘  └────────────┘                 │
├─────────────────────────────────────────────────────────────────┤
│  Data Layer                                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │ PostgreSQL │  │  Redis 7   │  │ ClickHouse │               │
│  │ 16+pgvector│  │  (cache)   │  │ 24 (OLAP)  │               │
│  └────────────┘  └────────────┘  └────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

- **Rust-primary**: All API handling, business logic, crypto, and data processing in Rust (Axum)
- **Python for LLM only**: Python runs as a subprocess for DeepSeek/Qwen inference via PyO3
- **Memory-safe crypto**: Post-quantum cryptography (ML-KEM-768, Ed25519, X25519)
- **Privacy-first**: k-anonymity (k≥10), differential privacy (ε=0.1), PII never stored
- **Free-tier optimized**: Fits within Oracle Cloud Always Free (4 OCPUs, 24GB RAM)

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API Server | Rust + Axum | HTTP/WebSocket server |
| Async Runtime | Tokio | Async I/O |
| LLM Inference | Python 3.12 + PyO3 | DeepSeek, Qwen models |
| Primary DB | PostgreSQL 16 + pgvector | Structured data + vectors |
| Cache | Redis 7 | Sessions, rate limiting, cache |
| OLAP | ClickHouse 24 | Analytics, time-series |
| Reverse Proxy | Nginx | TLS, rate limiting, compression |
| Crypto | AES-256-GCM, ML-KEM-768, Ed25519 | Encryption, PQC |
| Container | Docker + Docker Compose | Deployment |

---

## Revenue Engines (15 CFO Capabilities)

Msaidizi's backend powers 15 intelligence engines that work together as a complete CFO system for informal workers:

| Engine | CFO Capability | Description |
|--------|-------------|
| **Soko Pulse** | Market Intelligence | FMCG demand forecasting |
| **Alama Score** | Credit Management | Credit scoring (300-850) |
| **Angavu Pulse** | Economic Intelligence | Government economic intelligence |
| **Distribution Intel** | Supply Chain CFO | Supply chain optimization |
| **FMCG Intelligence** | Consumer Insights | Consumer goods analytics |
| **Market Heat Maps** | Market Visualization | Geographic demand visualization |
| **Price Index** | Pricing Intelligence | Real-time pricing intelligence |
| **Trade Routes** | Logistics Optimization | Logistics optimization |
| **Vendor Score** | Supplier Management | Supplier reliability metrics |
| **Consumer Pulse** | Demand Forecasting | Demand pattern analysis |
| **Inventory Optimizer** | Working Capital | Stock level intelligence |
| **Cash Flow Predictor** | Cash Flow Forecasting | Working capital forecasting |
| **Risk Radar** | Risk Assessment | Business risk assessment |
| **Growth Atlas** | Strategic Planning | Market expansion intelligence |
| **Sector Benchmark** | Performance Benchmarking | Industry comparison metrics |

---

## API Documentation

### Health & Status

```
GET  /health              — Liveness check
GET  /ready               — Readiness check (DB + Redis)
GET  /metrics             — Prometheus metrics
```

### Authentication (`/api/v1/auth`)

```
POST /api/v1/auth/login       — Login (returns JWT)
POST /api/v1/auth/register    — Register new user
POST /api/v1/auth/refresh     — Refresh access token
```

### Intelligence (`/api/v1/intelligence`)

```
POST /api/v1/intelligence/market-research   — Market analysis
POST /api/v1/intelligence/credit-score      — Generate credit score
POST /api/v1/intelligence/fmcg              — FMCG demand intel
POST /api/v1/intelligence/distribution      — Supply chain analysis
POST /api/v1/intelligence/economic          — Economic indicators
POST /api/v1/intelligence/heat-map          — Geographic heat map
```

### Users (`/api/v1/users`)

```
GET    /api/v1/users/me        — Current user profile
PUT    /api/v1/users/me        — Update profile
DELETE /api/v1/users/me        — Delete account
GET    /api/v1/users/{id}      — Get user (admin)
```

### Memory (`/api/v1/memory`)

```
GET    /api/v1/memory          — List memory entries
POST   /api/v1/memory          — Create memory entry
GET    /api/v1/memory/{id}     — Get specific memory
DELETE /api/v1/memory/{id}     — Delete memory
```

### Sync (`/api/v1/sync`)

```
POST /api/v1/sync/push        — Push local data
POST /api/v1/sync/pull        — Pull remote data
GET  /api/v1/sync/status      — Sync status
```

### Superagent (`/superagent`)

```
POST /superagent/query        — Send query to OODA orchestrator
GET  /superagent/status       — Orchestrator status
GET  /superagent/capabilities — List available capabilities
```

### WebSocket

```
GET /ws                       — Real-time updates (JWT required)
```

---

## Quick Start

### Prerequisites

- Docker 24+ and Docker Compose v2
- 4GB+ RAM available for Docker
- Ports 80, 443, 8000 available

### Local Development

```bash
# Clone
git clone <repo-url>
cd angavu-intelligence-backend

# Create .env file
cat > .env << 'EOF'
POSTGRES_PASSWORD=dev_password
JWT_SECRET=dev-jwt-secret-change-in-production
ENCRYPTION_KEY=dev-32-bytes-encryption-key!!
DEEPSEEK_API_KEY=sk-your-key
QWEN_API_KEY=sk-your-key
EOF

# Start all services
docker compose up -d

# Check health
curl http://localhost:8000/health

# View logs
docker compose logs -f api
```

### Build Locally (without Docker)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Build
cargo build --release

# Run (requires PostgreSQL, Redis, ClickHouse running)
DATABASE_URL=postgres://angavu:dev@localhost:5432/angavu \
REDIS_URL=redis://localhost:6379 \
./target/release/angavu-server --port 8000
```

---

## Deployment

### Oracle Cloud Free Tier

The stack is optimized for Oracle Cloud Always Free Tier:
- **Shape**: VM.Standard.E2.1.Micro (4 OCPUs, 24GB RAM) or Ampere A1 (4 OCPUs, 24GB RAM)
- **OS**: Ubuntu 22.04/24.04 aarch64 (ARM) or amd64

#### Memory Budget

| Service | Memory Limit |
|---------|-------------|
| PostgreSQL 16 | 4 GB |
| ClickHouse 24 | 2 GB |
| Redis 7 | 1.2 GB |
| Rust API Server | 3 GB |
| Nginx | 256 MB |
| OS + overhead | ~3 GB |
| **Total** | **~13.5 GB / 24 GB** |

#### Deploy Steps

1. **Set up Oracle Cloud instance** (Ubuntu 22.04+, ARM64 or x86_64)

2. **Install Docker**:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER
   # Log out and back in
   ```

3. **Clone and configure**:
   ```bash
   git clone <repo-url> /opt/angavu
   cd /opt/angavu
   cp .env.example .env
   # Edit .env with production values
   nano .env
   ```

4. **Generate SSL certificates** (Let's Encrypt):
   ```bash
   sudo apt install certbot
   sudo certbot certonly --standalone -d your-domain.com
   mkdir -p nginx/ssl
   sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/
   sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/
   ```

5. **Deploy**:
   ```bash
   chmod +x scripts/deploy.sh
   ./scripts/deploy.sh
   ```

### GitHub Actions CI/CD

Push to `main` triggers automatic deployment. Configure these secrets in GitHub:

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | Oracle Cloud instance IP/hostname |
| `DEPLOY_USER` | SSH user (e.g., `ubuntu`) |
| `DEPLOY_SSH_KEY` | SSH private key for deployment |

### Manual Deploy

```bash
# On the server
cd /opt/angavu
git pull
./scripts/deploy.sh
```

### Rollback

```bash
./scripts/deploy.sh --rollback
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string |
| `CLICKHOUSE_URL` | Yes | — | ClickHouse HTTP endpoint |
| `JWT_SECRET` | Yes | — | JWT signing secret (32+ chars) |
| `ENCRYPTION_KEY` | Yes | — | AES-256 encryption key (32 bytes) |
| `DEEPSEEK_API_KEY` | No | — | DeepSeek API key for LLM inference |
| `QWEN_API_KEY` | No | — | Qwen API key for LLM inference |
| `RUST_LOG` | No | `info` | Log level (trace/debug/info/warn/error) |
| `ANGAVU_HOST` | No | `0.0.0.0` | Server bind address |
| `ANGAVU_PORT` | No | `8000` | Server port |
| `POSTGRES_PASSWORD` | Yes | — | PostgreSQL password |

---

## Project Structure

```
angavu-intelligence-backend/
├── src/                        # Rust source code
│   ├── main.rs                 # Server entrypoint (Axum)
│   ├── api/                    # REST + WebSocket handlers
│   │   ├── v1/                 # API v1 routes
│   │   ├── ws.rs               # WebSocket handler
│   │   └── middleware.rs       # Auth, rate limiting
│   ├── db/                     # Database connections
│   │   ├── postgres.rs         # PostgreSQL (sqlx)
│   │   ├── redis.rs            # Redis
│   │   └── clickhouse.rs       # ClickHouse
│   ├── models/                 # Data models
│   │   ├── config.rs           # Configuration structs
│   │   ├── user.rs             # User models
│   │   ├── intelligence.rs     # Intelligence models
│   │   ├── memory.rs           # Memory hierarchy models
│   │   ├── agent.rs            # Agent/orchestrator models
│   │   └── sync.rs             # Sync models
│   ├── security/               # Cryptography
│   │   ├── crypto.rs           # AES-256-GCM encryption
│   │   ├── jwt.rs              # JWT handling
│   │   └── pqc.rs              # Post-quantum crypto
│   ├── superagent/             # OODA orchestrator
│   ├── intelligence/           # 15 revenue engines
│   ├── memory/                 # 5-layer memory hierarchy
│   ├── guardrails/             # Privacy & anonymization
│   ├── flywheel/               # Collective intelligence
│   └── sync/                   # Device sync, federated learning
├── python/                     # LLM inference ONLY
│   ├── llm/inference.py        # DeepSeek/Qwen calls
│   └── requirements.txt        # Minimal Python deps
├── scripts/                    # Deployment & operations
│   ├── deploy.sh               # Production deploy script
│   ├── backup.sh               # Database backup
│   ├── restore.sh              # Database restore
│   └── health.sh               # Health check script
├── nginx/
│   └── nginx.conf              # Nginx reverse proxy config
├── Dockerfile                  # Multi-stage build
├── docker-compose.yml          # Full stack orchestration
├── Cargo.toml                  # Rust dependencies
└── .github/workflows/
    └── deploy.yml              # CI/CD pipeline
```

---

## Development

```bash
# Run tests
cargo test

# Run with debug logging
RUST_LOG=debug cargo run

# Format code
cargo fmt

# Lint
cargo clippy

# Check for security vulnerabilities
cargo audit
```

---

## Security

- **Post-Quantum Crypto**: ML-KEM-768 key exchange, Ed25519 signatures
- **Encryption**: AES-256-GCM for data at rest
- **Authentication**: JWT with RS256
- **Rate Limiting**: Per-IP via Nginx (30 req/s API, 5 req/s auth)
- **Privacy**: k-anonymity (k≥10), differential privacy (ε=0.1)
- **Network**: All internal services bound to localhost only
- **TLS**: TLS 1.2/1.3 with Mozilla Intermediate config

---

## 🔒 Security Policy

Please see [SECURITY.md](SECURITY.md) for our security policy and vulnerability reporting process.

## 📬 Contact

- **GitHub**: [@ovalentine964](https://github.com/ovalentine964)
- **Issues**: [GitHub Issues](../../issues)
- **Website**: [angavu-intelligence](https://ovalentine964.github.io/angavu-intelligence/)

## 📄 License

Proprietary — Angavu Intelligence Team

---

<div align="center">

**Built with ❤️ for Africa's informal economy**

*Free CFO for 600 million informal workers. Intelligence infrastructure for the continent's $1.2 trillion informal sector.*

</div>
