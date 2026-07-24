# Angavu Intelligence Backend — Superagent Platform

> **The intelligence engine behind Msaidizi. Python + Rust. Enterprise-grade from day one.**

## What Is This?

The backend platform that powers Msaidizi's collective intelligence. It processes anonymized business flow data from millions of informal workers to generate:
- **Market intelligence** for FMCG companies
- **Credit scores** (Alama Score) for banks and MFIs
- **Business reports** delivered via WhatsApp
- **Outcome-based pricing** for financial partners

## Architecture

```
┌─────────────────────────────────────────────────┐
│         ANGAVU INTELLIGENCE BACKEND              │
├─────────────────────────────────────────────────┤
│  RUST LAYER (Performance-Critical)               │
│  ├── Crypto (AES-256-GCM, Argon2, PQC)          │
│  ├── Transaction Processing (M-Pesa parser)      │
│  ├── Vector Operations (cosine similarity)       │
│  ├── Input Validation (SQL/XSS sanitization)     │
│  └── Sync Engine (conflict resolution)           │
├─────────────────────────────────────────────────┤
│  PYTHON LAYER (AI/ML + Business Logic)           │
│  ├── Superagent Engine (OODA loop)               │
│  ├── Alama Score (credit scoring)                │
│  ├── WhatsApp Reports (bank-ready PDFs)          │
│  ├── Worker Profiles (28 types)                  │
│  ├── Referral Commission Engine                  │
│  ├── Outcome Tracking Engine                     │
│  ├── Collective Intelligence                     │
│  └── Federated Learning                          │
├─────────────────────────────────────────────────┤
│  DATA LAYER                                      │
│  ├── PostgreSQL 16 + pgvector                    │
│  ├── TimescaleDB (time-series)                   │
│  ├── Redis (cache, pub/sub, sessions)            │
│  └── Rust bridge (PyO3)                          │
└─────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Primary Language** | Python 3.12 |
| **Performance Layer** | Rust (via PyO3) |
| **Web Framework** | FastAPI |
| **Database** | PostgreSQL 16 + pgvector + TimescaleDB |
| **Cache** | Redis 7 |
| **AI Inference** | llama.cpp (Qwen 2.5 7B) |
| **WhatsApp** | OpenWA (Baileys) |
| **Deployment** | Docker + Oracle Cloud Free Tier |

## Revenue Engines

| Engine | What It Does | Who Pays |
|--------|-------------|----------|
| **Alama Score** | Credit scoring from business data | Banks, MFIs |
| **WhatsApp Reports** | Bank-ready PDFs via WhatsApp | Workers (free), banks (per report) |
| **Outcome Engine** | Pay-for-results pricing | Financial partners |
| **Referral Engine** | Commission on loan/insurance | Banks, insurance |
| **Collective Intelligence** | Market data for FMCG | Unilever, Coca-Cola, Twiga |

## API Endpoints

```
/api/v1/auth          — Authentication
/api/v1/transactions  — Transaction CRUD
/api/v1/workers       — Worker profiles
/api/v1/credit        — Alama Score
/api/v1/outcomes      — Outcome tracking
/api/v1/health        — Health check
```

## Deployment

```bash
docker compose up -d
```

## License

Proprietary — Angavu Intelligence Ltd.
