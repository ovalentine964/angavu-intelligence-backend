# Msaidizi / Biashara AI — Cloud Backend

> Intelligence platform for Kenya's informal economy.
> Transforms raw transaction data from dukawallahs and mama mbogas
> into actionable economic intelligence.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  2GB Android    │     │  Cloud Backend  │     │  Intelligence   │
│  (On-Device)    │────▶│  (FastAPI)      │────▶│  Buyers         │
│                 │     │                 │     │                 │
│  • Voice input  │     │  • Sync API     │     │  • FMCG (API)   │
│  • SQLite       │     │  • Pipeline     │     │  • Govt (Dash)  │
│  • Offline-first│     │  • Anonymizer   │     │  • Banks (API)  │
│  • zstd+AES     │     │  • Reports      │     │  • NGOs (Data)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local development)
- Node.js 18+ (for OpenWA service)

### 1. Clone and configure

```bash
cp .env.example .env
# Edit .env with your settings
```

### 2. Start with Docker Compose

```bash
docker-compose up -d
```

This starts:
- **PostgreSQL** (port 5432) — primary database
- **Redis** (port 6379) — caching and rate limiting
- **Backend** (port 8000) — FastAPI application
- **Nginx** (port 80) — reverse proxy
- **OpenWA** (port 3000) — WhatsApp bot

### 3. Run migrations

```bash
docker-compose exec backend alembic upgrade head
```

### 4. Access the API

- Health check: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs` (development only)
- Sync API: `POST http://localhost:8000/api/v1/sync`
- Reports: `GET http://localhost:8000/api/v1/reports/{user_id}/daily`
- Intelligence: `GET http://localhost:8000/api/v1/intelligence/market/{market_id}`

## API Endpoints

### Authentication (`/api/v1/auth`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register device / authenticate |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/consent` | Update data sharing consent |

### Data Sync (`/api/v1/sync`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sync` | Accept batched transaction data |
| GET | `/sync/status` | Get sync status |

### Business Reports (`/api/v1/reports`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reports/{user_id}/daily` | Daily business summary |
| GET | `/reports/{user_id}/weekly` | Weekly trends |
| GET | `/reports/{user_id}/advice` | AI-generated advice |
| GET | `/reports/{user_id}/summary` | Quick one-line summary |

### Intelligence API (`/api/v1/intelligence`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/intelligence/market/{market_id}` | Market-level data |
| GET | `/intelligence/demand/{product}` | Demand patterns |
| GET | `/intelligence/economic-activity/{region}` | Economic heatmaps |
| GET | `/intelligence/credit-signal/{business_id}` | Credit scoring |

### Webhooks (`/api/v1/webhooks`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhooks/whatsapp` | Incoming WhatsApp messages |
| GET | `/webhooks/whatsapp/health` | WhatsApp webhook health |

## Project Structure

```
msaidizi-backend/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py             # Settings from environment
│   ├── models/               # SQLAlchemy ORM models
│   │   ├── user.py           # Users (dukawallahs, mama mbogas)
│   │   ├── transaction.py    # Transactions & inventory
│   │   ├── intelligence.py   # Intelligence products & audit logs
│   │   └── buyer.py          # Buyers & API keys
│   ├── schemas/              # Pydantic request/response models
│   │   ├── sync.py           # Sync API contracts
│   │   ├── report.py         # Report structures
│   │   └── intelligence.py   # Intelligence API contracts
│   ├── api/                  # FastAPI routers
│   │   ├── auth.py           # Authentication endpoints
│   │   ├── sync.py           # Data sync endpoints
│   │   ├── reports.py        # Business report endpoints
│   │   ├── intelligence.py   # Buyer intelligence endpoints
│   │   └── whatsapp.py       # WhatsApp webhook
│   ├── services/             # Business logic
│   │   ├── sync_service.py   # Device sync processing
│   │   ├── pipeline.py       # Data cleaning & aggregation
│   │   ├── anonymizer.py     # Privacy & anonymization
│   │   ├── report_gen.py     # Report generation
│   │   └── whatsapp_bot.py   # WhatsApp message handling
│   ├── db/                   # Database setup
│   │   ├── database.py       # SQLAlchemy async engine
│   │   └── migrations/       # Alembic migrations
│   └── utils/                # Utilities
│       ├── crypto.py         # AES-256 encryption
│       └── compression.py    # zstd compression
├── openwa/                   # WhatsApp bot (Node.js/Baileys)
│   ├── index.js              # WhatsApp connection & message routing
│   ├── package.json
│   └── Dockerfile
├── tests/                    # Test suite
├── docker-compose.yml        # Full stack orchestration
├── Dockerfile                # Backend container
└── requirements.txt          # Python dependencies
```

## Data Privacy & Security

### Privacy Architecture (4 Layers)

| Layer | Data | Access |
|-------|------|--------|
| 1 (Raw) | Full data with PII | User + system only |
| 2 (Internal) | Pseudonymized | Internal analytics |
| 3 (Licensed) | k-anonymity (k≥10) | Buyer API |
| 4 (Public) | Aggregated stats | Dashboards |

### Key Privacy Features

- **AES-256 encryption** for all PII at rest
- **SHA-256 hashing** for phone number lookups without decryption
- **k-anonymity (k≥10)** on all buyer-facing queries
- **Differential privacy** noise on aggregate statistics
- **Geohash-5 coarsening** (~5km²) for location data
- **Full audit logging** of all data access
- **Kenya Data Protection Act 2019** compliance

### What Buyers See vs. Don't See

| Data | Buyer Can See? |
|------|---------------|
| Individual transaction | ❌ Never |
| User's name/phone | ❌ Never |
| Exact GPS location | ❌ Never |
| Market-level aggregates | ✅ (k≥10) |
| Regional activity indices | ✅ |
| Product demand patterns | ✅ |
| Credit scoring signals | ✅ (anonymized) |

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_sync.py -v

# Run specific test
pytest tests/test_pipeline.py::TestProductNormalization::test_swahili_to_english
```

## Development

### Local setup (without Docker)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up database (requires PostgreSQL running locally)
export DATABASE_URL=postgresql+asyncpg://msaidizi:msaidizi_pass@localhost:5432/msaidizi

# Run the application
uvicorn app.main:app --reload --port 8000
```

### Database migrations

```bash
# Generate a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Deployment

### Docker (recommended)

```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f backend

# Scale backend workers
docker-compose up -d --scale backend=3
```

### Environment Variables

See `.env.example` for all configuration options. Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `JWT_SECRET_KEY` | JWT signing secret | Required |
| `ENCRYPTION_KEY` | AES-256 encryption key | Required |
| `K_ANONYMITY_THRESHOLD` | Minimum users per aggregation | 10 |
| `CORS_ORIGINS` | Allowed CORS origins | localhost |

## Cost Estimates

| Users | Monthly Cloud Cost | Cost/User |
|-------|-------------------|-----------|
| 100 | ~$17 | $0.17 |
| 1,000 | ~$120 | $0.12 |
| 10,000 | ~$800 | $0.08 |
| 50,000 | ~$3,500 | $0.07 |

## License

Proprietary — Msaidizi / Biashara AI

---

Built for Kenya's informal economy. 🇰🇪
