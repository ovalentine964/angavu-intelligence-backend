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
