# Angavu Intelligence Backend

## Architecture Overview

Angavu Intelligence Backend is a cloud intelligence engine that processes anonymized data from millions of informal workers to generate market intelligence, credit scores, and business reports.

### Superagent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    OODA Orchestrator                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Observe  │→│  Orient  │→│  Decide  │→│   Act    │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
├─────────────────────────────────────────────────────────────┤
│  Capability Modules                                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │  Market    │ │  Credit    │ │Distribution│              │
│  │  Research  │ │  Scoring   │ │ Analysis   │              │
│  └────────────┘ └────────────┘ └────────────┘              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │   FMCG    │ │  Health    │ │  Economic  │              │
│  │Intelligence│ │  Metrics   │ │  Analysis  │              │
│  └────────────┘ └────────────┘ └────────────┘              │
├─────────────────────────────────────────────────────────────┤
│  5-Layer Memory                                              │
│  Request → Session → Daily → Market Patterns → Knowledge    │
├─────────────────────────────────────────────────────────────┤
│  Guardrails                                                  │
│  k-anonymity (≥10) │ Differential Privacy (ε=0.1) │ Audit  │
└─────────────────────────────────────────────────────────────┘
```

### Revenue Engines (15 Products)

| Engine | Description |
|--------|-------------|
| Soko Pulse | FMCG demand forecasting |
| Alama Score | Credit scoring (300-850) |
| Angavu Pulse | Government economic intelligence |
| Distribution Intel | Supply chain optimization |
| FMCG Intelligence | Consumer goods analytics |
| Market Heat Maps | Geographic demand visualization |
| Price Index | Real-time pricing intelligence |
| Trade Routes | Logistics optimization |
| Vendor Score | Supplier reliability metrics |
| Consumer Pulse | Demand pattern analysis |
| Inventory Optimizer | Stock level intelligence |
| Cash Flow Predictor | Working capital forecasting |
| Risk Radar | Business risk assessment |
| Growth Atlas | Market expansion intelligence |
| Sector Benchmark | Industry comparison metrics |

### Tech Stack

- **API**: Python 3.12 + FastAPI
- **Crypto**: Rust (PyO3) for crypto and vector ops
- **Primary DB**: PostgreSQL 16 + pgvector + TimescaleDB
- **OLAP**: ClickHouse 24
- **Cache**: Redis 7
- **Graph Patterns**: DeerFlow/LangGraph adapted
- **Containerization**: Docker + Docker Compose

### Memory Budget (Oracle Cloud Free Tier: 11.6GB)

| Service | Memory |
|---------|--------|
| PostgreSQL | 4 GB |
| ClickHouse | 2 GB |
| Redis | 1.2 GB |
| API Server | 3 GB |
| Worker | 1.5 GB |
| PgBouncer | 128 MB |
| **Total** | **~11.8 GB** |

### Quick Start

```bash
# Clone and start
git clone <repo>
cd angavu-intelligence-backend
docker compose up -d

# Run migrations
docker compose exec api alembic upgrade head

# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs
```

### Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# Lint
ruff check app/ tests/

# Type check
mypy app/
```

### Project Structure

```
angavu-intelligence-backend/
├── app/
│   ├── api/v1/           # REST endpoints
│   ├── superagent/        # OODA orchestrator + capability modules
│   ├── memory/            # 5-layer memory hierarchy
│   ├── guardrails/        # Anonymization, k-anonymity, DP
│   ├── flywheel/          # Collective intelligence loops
│   ├── intelligence/      # 15 revenue engines
│   ├── sync/              # Device sync, federated learning
│   ├── models/            # SQLAlchemy + Pydantic models
│   ├── services/          # Business logic
│   ├── security/          # PQC, encryption
│   └── core/              # Config, logging, dependencies
├── rust/                  # PyO3 crypto extensions
├── config/                # Service configs
├── database/migrations/   # Alembic migrations
├── scripts/               # Deployment, backup, health
└── tests/                 # Test suite
```
