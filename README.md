# Msaidizi — Backend & Cloud Intelligence

**The brain behind Africa's first economic intelligence platform.**

## Overview

FastAPI backend that powers Msaidizi's cloud intelligence layer. Receives transaction data from Android devices, generates economic intelligence for buyers (FMCG companies, government, banks, NGOs).

## Stack

- Python 3.11 + FastAPI
- PostgreSQL 15
- Redis (caching)
- Celery (background tasks)
- OpenWA (WhatsApp integration)

## Quick Start

```bash
docker-compose up -d
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/sync` | Device data upload |
| GET | `/api/v1/reports/{user_id}` | Business reports |
| GET | `/api/v1/intelligence/{buyer_type}` | Economic intelligence |
| POST | `/api/v1/auth/register` | User registration |
| POST | `/api/v1/whatsapp/connect` | WhatsApp connection |

Full API documentation: [API.md](API.md)

## Security

- JWT authentication
- k-anonymity (k≥10)
- Differential privacy
- AES-256-GCM encryption
- Rate limiting

## Project Structure

```
msaidizi-backend/
├── app/
│   ├── api/v1/         # API route handlers
│   ├── core/           # Config, security, database setup
│   ├── models/         # SQLAlchemy ORM models
│   ├── schemas/        # Pydantic request/response schemas
│   ├── services/       # Business logic layer
│   └── tasks/          # Celery background tasks
├── src/                # Intelligence engine modules
├── tests/              # Pytest test suite
├── database/           # Alembic migrations
├── nginx/              # Reverse proxy configs
├── openwa/             # WhatsApp bridge integration
├── docker-compose.yml  # Full stack orchestration
└── Dockerfile          # Production container
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for production setup.

## License

Proprietary — Biashara Intelligence
