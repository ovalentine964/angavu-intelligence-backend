# Msaidizi Backend — Deployment Guide

**Production deployment instructions for the Msaidizi cloud backend.**

---

## Prerequisites

- Docker 24+ and Docker Compose v2
- A server with minimum 2 vCPUs, 4GB RAM
- Domain name with DNS configured
- SSL certificate (or use the included nginx + Let's Encrypt setup)

---

## Quick Start (Development)

```bash
# Clone the repository
git clone https://github.com/ovalentine964/msaidizi-backend.git
cd msaidizi-backend

# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env

# Start all services
docker-compose up -d

# Verify
curl http://localhost:8000/api/v1/health
```

---

## Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
```

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@db:5432/msaidizi` |
| `REDIS_URL` | Redis connection string | `redis://redis:6379/0` |
| `JWT_SECRET` | JWT signing secret (min 32 chars) | Generate with `openssl rand -hex 32` |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_EXPIRY_HOURS` | Token validity period | `168` (7 days) |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SENTRY_DSN` | Sentry error tracking | None |
| `OPENAI_API_KEY` | For AI-powered advice generation | None |
| `WHATSAPP_API_TOKEN` | WhatsApp Business API token | None |
| `ENCRYPTION_KEY` | AES-256-GCM key for data at rest | Auto-generated |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `WORKERS` | Uvicorn worker count | `4` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |

---

## Docker Compose Architecture

The `docker-compose.yml` orchestrates 5 services:

```
┌─────────────────────────────────────────────────┐
│                   nginx (port 80/443)            │
│              Reverse proxy + SSL termination     │
├─────────────────────────────────────────────────┤
│                                                   │
│  ┌──────────────┐  ┌──────────────┐              │
│  │   FastAPI     │  │   Celery     │              │
│  │  (port 8000)  │  │   Worker     │              │
│  │  4 workers    │  │  Background  │              │
│  └──────┬───────┘  └──────┬───────┘              │
│         │                  │                      │
│  ┌──────┴──────────────────┴───────┐              │
│  │        PostgreSQL 15            │              │
│  │        (port 5432)              │              │
│  └─────────────────────────────────┘              │
│                                                   │
│  ┌─────────────────────────────────┐              │
│  │        Redis 7                  │              │
│  │   (cache + Celery broker)       │              │
│  └─────────────────────────────────┘              │
│                                                   │
└─────────────────────────────────────────────────┘
```

### Service Details

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `api` | Custom (Python 3.11) | 8000 | FastAPI application server |
| `celery` | Custom (Python 3.11) | — | Background task processing |
| `db` | postgres:15-alpine | 5432 | Primary database |
| `redis` | redis:7-alpine | 6379 | Cache + message broker |
| `nginx` | nginx:alpine | 80, 443 | Reverse proxy |

---

## Production Deployment

### Step 1: Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Verify
docker --version
docker compose version
```

### Step 2: Clone and Configure

```bash
# Clone to production directory
git clone https://github.com/ovalentine964/msaidizi-backend.git /opt/msaidizi
cd /opt/msaidizi

# Generate secure secrets
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env
echo "ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env
echo "DATABASE_URL=postgresql+asyncpg://msaidizi:$(openssl rand -hex 16)@db:5432/msaidizi" >> .env
echo "REDIS_URL=redis://redis:6379/0" >> .env
echo "JWT_ALGORITHM=HS256" >> .env
echo "JWT_EXPIRY_HOURS=168" >> .env
echo "LOG_LEVEL=WARNING" >> .env
echo "WORKERS=4" >> .env
echo "CORS_ORIGINS=https://msaidizi.biashara.ai" >> .env

# Review and edit
nano .env
```

### Step 3: SSL with Let's Encrypt

```bash
# Install certbot
sudo apt install certbot -y

# Get certificate
sudo certbot certonly --standalone -d api.msaidizi.biashara.ai

# Copy certs to nginx directory
mkdir -p nginx/ssl
sudo cp /etc/letsencrypt/live/api.msaidizi.biashara.ai/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/api.msaidizi.biashara.ai/privkey.pem nginx/ssl/
sudo chown -R $USER:$USER nginx/ssl/
```

### Step 4: Start Services

```bash
# Build and start
docker compose up -d --build

# Run database migrations
docker compose exec api alembic upgrade head

# Verify all services
docker compose ps
curl -f http://localhost:8000/api/v1/health
```

### Step 5: Set Up Auto-Renewal

```bash
# Add certbot renewal cron
echo "0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/api.msaidizi.biashara.ai/*.pem /opt/msaidizi/nginx/ssl/ && docker compose restart nginx" | sudo tee /etc/cron.d/msaidizi-ssl
```

---

## Database Management

### Run Migrations

```bash
# Apply all pending migrations
docker compose exec api alembic upgrade head

# Create a new migration
docker compose exec api alembic revision --autogenerate -m "description"

# Rollback one migration
docker compose exec api alembic downgrade -1
```

### Backup

```bash
# Manual backup
docker compose exec db pg_dump -U msaidizi msaidizi > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20260630.sql | docker compose exec -T db psql -U msaidizi msaidizi
```

### Automated Backups (Cron)

```bash
# Add to crontab
echo "0 2 * * * cd /opt/msaidizi && docker compose exec -T db pg_dump -U msaidizi msaidizi | gzip > /opt/msaidizi/backups/backup_\$(date +\%Y\%m\%d).sql.gz" | sudo tee /etc/cron.d/msaidizi-backup

# Create backup directory
mkdir -p /opt/msaidizi/backups
```

---

## Monitoring

### Health Checks

```bash
# API health
curl http://localhost:8000/api/v1/health

# Database
docker compose exec db pg_isready -U msaidizi

# Redis
docker compose exec redis redis-cli ping

# Celery
docker compose exec celery celery -A app.tasks inspect ping
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f celery

# Last 100 lines
docker compose logs --tail 100 api
```

### Resource Usage

```bash
docker stats --no-stream
```

---

## Scaling

### Horizontal Scaling (API Workers)

```bash
# Scale API to 3 instances
docker compose up -d --scale api=3
```

Update nginx upstream config to include all instances.

### Vertical Scaling

Edit `docker-compose.yml`:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

---

## Troubleshooting

### Common Issues

**Database connection refused:**

```bash
# Check if DB is running
docker compose ps db

# Check DB logs
docker compose logs db

# Restart DB
docker compose restart db
```

**API returns 502:**

```bash
# Check API is running
docker compose ps api

# Check API logs
docker compose logs api

# Restart API
docker compose restart api
```

**Celery tasks not processing:**

```bash
# Check Celery is running
docker compose ps celery

# Check Redis connection
docker compose exec redis redis-cli ping

# Restart Celery
docker compose restart celery
```

**Disk space full:**

```bash
# Clean Docker artifacts
docker system prune -af --volumes

# Check disk usage
df -h
du -sh /opt/msaidizi/backups/
```

---

## Updating

```bash
cd /opt/msaidizi

# Pull latest code
git pull origin main

# Rebuild and restart
docker compose up -d --build

# Run any new migrations
docker compose exec api alembic upgrade head

# Verify
curl -f http://localhost:8000/api/v1/health
```

---

## Security Checklist

- [ ] All secrets in `.env` (not in code)
- [ ] SSL/TLS enabled on nginx
- [ ] Database not exposed to public internet
- [ ] Redis password set
- [ ] Rate limiting enabled
- [ ] CORS restricted to known origins
- [ ] Regular security updates (`apt update`)
- [ ] Backups tested and verified
- [ ] Log rotation configured
- [ ] Firewall configured (allow only 80, 443, SSH)

---

*Biashara AI Ltd — Proprietary*
