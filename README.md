![Angavu Intelligence](docs/logo-banner.svg)

# Angavu Intelligence — Backend

**Africa's operating system for the informal economy. Processing data from 600M+ informal workers into economic intelligence.**

**Version:** 0.2.0 | **Last Updated:** July 2026

---

## Quick Start

### One-Command Deploy (Oracle Cloud)
```bash
curl -sSL https://raw.githubusercontent.com/ovalentine964/angavu-intelligence-backend/main/deploy.sh | bash
```

This installs everything: PostgreSQL, Redis, ClickHouse, OpenWA (WhatsApp), Nginx, SSL, backups, health monitoring.

**Cost: $0 on Oracle Cloud Free Tier** (2 ARM OCPUs, 12GB RAM, 200GB storage)

### Manual Setup
```bash
docker-compose up -d
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Runtime                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Data     │  │Intelligence│  │ Report   │  │ Self-    │   │
│  │Processing│  │  Agents   │  │ Agents   │  │Evolution │   │
│  │ (7)      │  │  (7)      │  │  (5)     │  │  (6)     │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │          │
│  ┌────┴──────────────┴──────────────┴──────────────┴─────┐  │
│  │                    Event Bus (Redis Streams)            │  │
│  │   Pub/Sub · Consumer Groups · Dead Letter Queue        │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Learning │  │Governance│  │Infrastructure│               │
│  │  (4)     │  │  (4)     │  │  (4)        │               │
│  └──────────┘  └──────────┘  └──────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **API** | Python 3.12, FastAPI, Gunicorn (4 workers) | Async-first API server |
| **Database** | PostgreSQL 16 | Economic data, user accounts |
| **Cache** | Redis 7 | Caching, queues, real-time events |
| **Analytics** | ClickHouse | Time-series, price data, analytics |
| **WhatsApp** | OpenWA (self-hosted) | Report delivery via WhatsApp |
| **Agent Runtime** | Custom multi-agent system | 33+ agents across 6 swarms |
| **Security** | JWT RS256, AES-256-GCM, ML-KEM, ML-DSA | Bank-grade + quantum-ready |
| **Metrics** | Prometheus (30 metrics) | HTTP, agent, DB, Redis, queue |
| **Deploy** | Docker, Oracle Cloud, Nginx | One-command deploy |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (all services) |
| `/metrics` | GET | Prometheus metrics |
| `/api/v1/auth/*` | POST | Authentication (OTP, biometric) |
| `/api/v1/transactions/*` | CRUD | Transaction management |
| `/api/v1/reports/*` | GET | Report generation |
| `/api/v1/whatsapp/*` | POST | WhatsApp connection |
| `/webhooks/whatsapp` | POST | OpenWA webhook |
| `/fl/*` | POST | Federated learning |

---

## Infrastructure Modules

| Module | Lines | What It Does |
|--------|-------|-------------|
| `redis_streams.py` | 715 | Producer/consumer, consumer groups, dead letter |
| `task_queue.py` | 735 | Priority queues, delayed tasks, exponential backoff |
| `cache.py` | 476 | Cache-aside, namespace support, stampede prevention |
| `metrics.py` | 802 | 30 Prometheus metrics, auto-instrumented middleware |
| `connection_pool.py` | — | Health checks, retry, pool metrics |

---

## Agent System

| Swarm | Agents | Purpose |
|-------|--------|---------|
| Data Processing | 7 | Ingestion, voice, patterns, quality, geospatial |
| Intelligence | 7 | Market, credit, business, community, tax |
| Reports | 5 | Worker, buyer, formal, WhatsApp, insight narrator |
| Self-Evolution | 6 | Feedback, features, model training, dialect |
| Learning | 4 | Federated, active, model evaluator, knowledge distillation |
| Governance | 4 | Security, privacy, compliance, audit |

---

## ⚠️ Critical Risk: WhatsApp via Baileys (Unofficial Library)

### The Problem

WhatsApp integration uses **Baileys** (unofficial WhatsApp Web library). This is an **existential risk**:

- **Meta can ban the phone number at any time** — no warning, no appeal
- Baileys reverse-engineers WhatsApp Web protocol — violates ToS
- Ban is permanent for that number — cannot be undone
- All users on that number lose report delivery instantly

### Why We Accept This Risk (For Now)

- Official WhatsApp Business API costs $0.05-0.10 per conversation — prohibitive at scale
- Baileys is free, self-hosted, works today
- Our users (informal workers in Kenya) overwhelmingly prefer WhatsApp
- We mitigate risk until revenue justifies official API

### Safety Measures Implemented

The following measures reduce ban probability by mimicking human behavior:

| Measure | Config | Purpose |
|---------|--------|---------|
| **Human-like delays** | 2-8 seconds random between messages | Avoid bot detection |
| **Message queue** | FIFO with backpressure | Never flood the connection |
| **Rate limiting** | Max 10 msg/sec, 200 msg/min | Stay under detection thresholds |
| **Consecutive cap** | 50 messages, then 60s cooldown | Prevent burst patterns |
| **Ban detection** | 5 consecutive failures → auto-failover | Catch bans early |
| **Auto-failover** | WhatsApp → Telegram → SMS → HTTP | Keep delivering reports |
| **Delivery tracking** | Per-message receipt monitoring | Know what got through |

### If WhatsApp Gets Banned

1. OpenWA detects the ban (connection failure + auth error)
2. Calls `/api/v1/channels/ban-detected` on the backend
3. Backend marks WhatsApp as unhealthy
4. FailoverManager routes all messages to Telegram
5. Admin gets alerted via `WhatsAppHealthMonitor`
6. Users continue receiving reports on Telegram (if connected)

### Migration Path

- **Short term**: Baileys with safety measures (current)
- **Medium term**: WhatsApp Business API (when revenue > $5K/mo)
- **Long term**: Multi-channel default (WhatsApp + Telegram + SMS + App)

### Safety Configuration

Environment variables for the OpenWA service:

```env
WA_MAX_MSG_PER_SEC=10          # Max messages per second
WA_MIN_DELAY_MS=2000           # Min delay between messages (ms)
WA_MAX_DELAY_MS=8000           # Max delay between messages (ms)
WA_MAX_CONSECUTIVE=50          # Max consecutive messages before cooldown
WA_COOLDOWN_MS=60000           # Cooldown period (ms)
WA_MAX_MSG_PER_MIN=200         # Max messages per minute
WA_BAN_THRESHOLD=5             # Consecutive failures before ban declaration
WA_HEALTH_INTERVAL_MS=30000    # Health check interval (ms)
WA_DELIVERY_TIMEOUT_MS=30000   # Delivery confirmation timeout (ms)
```

---

## Security

- **JWT RS256** — RSA-4096 keys, JWKS endpoint, token family theft detection
- **AES-256-GCM** — Field-level encryption with unique IV per field
- **Post-Quantum** — ML-KEM (Kyber) + ML-DSA (Dilithium) ready
- **Differential Privacy** — ε=0.1 for federated learning
- **Rate Limiting** — Per-user + global on all endpoints
- **Input Validation** — SQL injection, XSS, prompt injection defense

---

## Scalability

| Users | Strategy | Cost |
|-------|----------|------|
| 1K | Oracle Cloud Free Tier | $0 |
| 10K | Multi-process + Redis | ~$50-100/mo |
| 100K | Redis Streams + pooling | ~$200-500/mo |
| 1M | Go gateway + Python ML | ~$500-1,000/mo |

---

## Founder

**Valentine Owuor** — BSc Economics & Statistics, Masinde Muliro University (December 2026)

---

## License

Proprietary — Angavu Intelligence Ltd.
