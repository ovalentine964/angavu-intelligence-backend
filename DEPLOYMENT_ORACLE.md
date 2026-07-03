# Angavu Intelligence — Oracle Cloud Deployment Guide

Deploy to Oracle Cloud Free Tier with one command.

---

## Free Tier Options

| Spec | VM | vCPU | RAM | Storage | Cost |
|------|-----|------|-----|---------|------|
| **Micro** | E2.Micro (AMD) | 1/8 OCPU | 1 GB | 200 GB block | **Free forever** |
| **ARM** | A1.Flex | 4 OCPU | 24 GB | 200 GB block | **Free forever** |

### Which profile to use?

- **Micro** — Low traffic, dev/staging, evaluation. SQLite backend, 1 worker, ~200MB RAM usage.
- **ARM** — Production, higher traffic. PostgreSQL, 4 workers, Redis cache, ~2GB RAM usage.

---

## One-Command Deploy

```bash
# Micro profile (1GB RAM — default)
curl -sSL https://raw.githubusercontent.com/ovalentine964/biashara-intelligence-backend/main/deploy.sh | bash

# ARM profile (24GB RAM)
PROFILE=arm curl -sSL https://raw.githubusercontent.com/ovalentine964/biashara-intelligence-backend/main/deploy.sh | bash

# With custom domain + auto-SSL
DOMAIN=api.biashara.ai EMAIL=you@example.com \
  curl -sSL https://raw.githubusercontent.com/ovalentine964/biashara-intelligence-backend/main/deploy.sh | bash
```

The script will:
1. Install Docker (if missing)
2. Clone the repository to `/opt/biashara`
3. Generate secure secrets and `.env`
4. Start the appropriate services
5. Wait for health check
6. Configure nginx + SSL (if DOMAIN is set)
7. Set up UFW firewall

---

## Manual Setup

### Step 1: Create Oracle Cloud VM

1. Go to [Oracle Cloud Console](https://cloud.oracle.com)
2. **Compute → Instances → Create Instance**
3. Choose:
   - **Image:** Ubuntu 22.04 or 24.04 (aarch64 for ARM, x86_64 for Micro)
   - **Shape:** `VM.Standard.A1.Flex` (ARM, 4 OCPU, 24GB) or `VM.Standard.E2.1.Micro` (AMD)
   - **Networking:** Create/select VCN, subnet with public IP
   - **SSH key:** Upload your public key
4. Open ports 22, 80, 443 in Security List

### Step 2: SSH in and deploy

```bash
ssh ubuntu@<your-instance-ip>

# Clone
git clone https://github.com/ovalentine964/biashara-intelligence-backend.git /opt/biashara
cd /opt/biashara

# Configure
cp .env.example .env
nano .env  # Edit secrets, DB URL, etc.

# Start (Micro)
docker compose -f docker-compose.oracle.yml up -d --build

# Start (ARM)
docker compose -f docker-compose.oracle.yml --profile arm up -d --build
```

### Step 3: Verify

```bash
# Health check
curl http://localhost:8000/health

# Logs
docker compose -f docker-compose.oracle.yml logs -f api

# Resource usage
docker stats
```

---

## Architecture

### Micro Profile (1GB RAM)

```
┌─────────────────────────────┐
│      nginx (reverse proxy)  │
│         :80 / :443          │
├─────────────────────────────┤
│  ┌───────────────────────┐  │
│  │   FastAPI + Gunicorn  │  │
│  │   1 worker, :8000     │  │
│  │   ~180MB RAM          │  │
│  └───────────┬───────────┘  │
│              │              │
│  ┌───────────┴───────────┐  │
│  │   SQLite (file)       │  │
│  │   ./data/biashara.db  │  │
│  └───────────────────────┘  │
│                             │
│  In-memory TTL cache        │
│  (no Redis needed)          │
└─────────────────────────────┘
```

### ARM Profile (24GB RAM)

```
┌─────────────────────────────────┐
│       nginx (reverse proxy)     │
│          :80 / :443             │
├─────────────────────────────────┤
│  ┌───────────────────────────┐  │
│  │   FastAPI + Gunicorn      │  │
│  │   4 workers, :8000        │  │
│  │   ~800MB RAM              │  │
│  └──────────┬────────────────┘  │
│             │                   │
│  ┌──────────┴──────────┐        │
│  │   PostgreSQL 16     │        │
│  │   ~256MB RAM        │        │
│  └─────────────────────┘        │
│                                 │
│  ┌─────────────────────┐        │
│  │   Redis 7           │        │
│  │   128MB cap         │        │
│  └─────────────────────┘        │
└─────────────────────────────────┘
```

---

## Memory Budget

### Micro (1GB total)

| Component | RAM |
|-----------|-----|
| OS + Docker daemon | ~300MB |
| Gunicorn (1 worker) | ~180MB |
| SQLite | ~10MB |
| In-memory cache | ~50MB |
| nginx | ~20MB |
| **Total** | **~560MB** |
| **Headroom** | **~440MB** |

### ARM (24GB total)

| Component | RAM |
|-----------|-----|
| OS + Docker daemon | ~500MB |
| Gunicorn (4 workers) | ~800MB |
| PostgreSQL | ~300MB |
| Redis (128MB cap) | ~150MB |
| nginx | ~30MB |
| **Total** | **~1.8GB** |
| **Headroom** | **~22GB** |

---

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | `sqlite+aiosqlite:///./data/biashara.db` (micro) or PostgreSQL URL (arm) |
| `SECRET_KEY` | Yes | Random 32+ char string |
| `JWT_SECRET_KEY` | Yes | Random 32+ char string |
| `ENCRYPTION_KEY` | Yes | Random 32+ char string |
| `REDIS_URL` | No | Empty = in-memory cache. `redis://redis:6379/0` for ARM |
| `DOMAIN` | No | For nginx/SSL setup |
| `EMAIL` | No | For Let's Encrypt |

---

## Useful Commands

```bash
cd /opt/biashara

# Logs
docker compose -f docker-compose.oracle.yml logs -f api

# Restart
docker compose -f docker-compose.oracle.yml restart

# Update
git pull origin main
docker compose -f docker-compose.oracle.yml up -d --build

# Stop
docker compose -f docker-compose.oracle.yml down

# Database backup (ARM)
docker compose -f docker-compose.oracle.yml exec postgres \
  pg_dump -U biashara biashara > backup_$(date +%Y%m%d).sql

# SQLite backup (Micro)
cp data/biashara.db data/biashara_backup_$(date +%Y%m%d).db
```

---

## Troubleshooting

**API not starting:**
```bash
docker compose -f docker-compose.oracle.yml logs api
```

**Out of memory (Micro):**
```bash
# Check what's using memory
docker stats --no-stream
free -h

# Reduce further: swap file
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

**Database locked (SQLite):**
```bash
# Check for stale lock
ls -la data/biashara.db*
# Restart API to release connections
docker compose -f docker-compose.oracle.yml restart api
```

---

*Angavu Intelligence — Deployed on Oracle Cloud Free Tier 🇰🇪*
