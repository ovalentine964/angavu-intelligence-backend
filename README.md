![Angavu Intelligence](docs/logo-banner.svg)

# Angavu Intelligence — Cloud Platform

**Africa's operating system for the informal economy. Processing data from 600M+ informal workers into economic intelligence.**

**"The monopoly that serves 600M+ informal workers. Not competing. Just operating."**

**Version:** 0.1.0

---

## Vision

Angavu Intelligence is the vertically integrated AI platform for Africa's informal economy. We own the data, the models, and the infrastructure. Every informal worker has an AI CFO. Africa's answer to China's AI factories.

> *"What used to take months, we do in days."*

## Mission

Provide economic intelligence to Africa's 600M+ informal workers. Make invisible workers visible. Fix market inefficiencies, information asymmetry, and coordination failures.

## Architecture

```
Msaidizi (Android) → Voice/Transaction Data → Angavu Intelligence (Cloud) → Intelligence Products → Buyers
     ↓                                            ↓                                        ↓
  600M+ workers                            15 intelligence products              12 buyer segments
  14 dialects                              Multi-agent runtime                   $89M-$400M TAM
  Offline-first                            Degree-driven (42 units)              Outcome-based pricing
```

### Multi-Agent Architecture (33 Agents, 6 Swarms)

The platform uses a **multi-agent runtime** with an **event bus** for loose coupling between agents:

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
│  │                    Event Bus                           │  │
│  │   Pub/Sub · Message routing · Dead letter queue        │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌──────────┐  ┌──────────┐                                 │
│  │ Learning │  │Governance│                                 │
│  │  (4)     │  │  (4)     │                                 │
│  └──────────┘  └──────────┘                                 │
└─────────────────────────────────────────────────────────────┘
```

**Key components:**
- **Agent Runtime** — manages agent lifecycle, health monitoring, and orchestration
- **Event Bus** — pub/sub message passing between agents, with dead letter queue for failed events
- **Observability** — metrics, tracing, and health checks for all agents

### Multi-Agentic Swarms

| Swarm | Agents | Role |
|-------|--------|------|
| 🔄 Data Processing | 7 | Transaction, voice, pattern, quality, geo, receipt + coordinator |
| 🧠 Intelligence | 7 | Market, credit, economic, community, tax, distribution + coordinator |
| 📋 Reports | 5 | Worker, buyer, formal, WhatsApp, insight narrator |
| 🧬 Self-Evolution | 6 | Feedback, feature design, training, dialect, quality, experiments |
| 🎓 Learning | 4 | Federated, active learner, model evaluator, knowledge distiller |
| 🛡️ Governance | 4 | Security, privacy, compliance, audit |

## Intelligence Products (15)

### Existing (6)
| Product | Description | Buyers |
|---------|-------------|--------|
| **Soko Pulse** | Market intelligence — prices, demand, forecasting | FMCG, traders |
| **Angavu Pulse** | Economy monitoring — GDP, inflation, employment | Government, IMF |
| **Alama Score** | Credit scoring — transaction-based, 300-850 | Banks, insurance |
| **Jamii Insights** | Community intelligence — financial inclusion, poverty | NGOs, World Bank |
| **Tax Base** | Tax compliance estimation | KRA, government |
| **Distribution Gap** | Market coverage analysis | FMCG, logistics |

### New (9 — Phase 1)
| Product | Description | Buyers |
|---------|-------------|--------|
| **GDP Estimator** | Real-time informal GDP by county | KNBS, CBK |
| **Inflation Tracker** | Daily price indices (4 methods) | CBK, media |
| **Employment Monitor** | Real-time employment indicators | Ministry of Labour, ILO |
| **Insurance Risk** | Risk profiles for micro-insurance | Jubilee, Britam |
| **Market Entry** | Market sizing for new entrants | PE/VC, consultancies |
| **SDG Tracker** | SDG progress from real data | UNDP, World Bank |
| **Gender Intelligence** | Women's economic participation | UN Women, NGOs |
| **Supply Chain** | Agricultural supply optimization | Twiga, commodity traders |
| **Research Data** | Anonymized datasets for research | MIT, Oxford, J-PAL |

### FMCG Intelligence (Pwani Oil Pilot)
Dedicated FMCG intelligence service for tracking informal channel performance:
- **Brand tracking** across informal retail outlets
- **Demand signals** from mama mbogas and dukawallahs
- **Distribution gap analysis** for last-mile coverage
- **Price monitoring** at the informal retail level
- **Competitor intelligence** from transaction patterns

## Federated Learning v2

Privacy-preserving machine learning that improves models without seeing worker data.

### Privacy Guarantees

| Mechanism | Specification | Purpose |
|---|---|---|
| **Differential Privacy** | ε=0.1, δ=1e-5 | Mathematical guarantee that no one can reverse-engineer individual data |
| **K-Anonymity** | k≥10 | Data only used when at least 10 workers have similar patterns |
| **On-Device Training** | Local model updates | Data never leaves the worker's phone |
| **Secure Aggregation** | Encrypted model updates | Server cannot see individual contributions |
| **Data Sovereignty** | African data in Africa | Compliant with Kenya DPA, Nigeria NDPR, South Africa POPIA |

### How It Works

```
Worker's phone trains model locally
    → Anonymous model gradients computed
    → Encrypted update sent to server
    → Server aggregates across thousands of workers
    → Improved global model distributed
    → Worker gets better AI, data never exposed
```

## Infrastructure Health Monitoring

Real-time monitoring of all platform components:

| Metric | Target | Alert Threshold |
|---|---|---|
| API Response Time | <200ms p95 | >500ms |
| Agent Health | 100% uptime | Any agent down |
| Event Bus Latency | <50ms | >200ms |
| Federated Learning Round | <30min | >60min |
| Data Pipeline Throughput | 10K transactions/min | <1K/min |
| ClickHouse Query Time | <1s | >5s |

## Data Center Roadmap

Infrastructure evolves based on worker value — each phase unlocks when workers generate enough data to justify the investment.

| Phase | Trigger | Infrastructure | Capacity |
|---|---|---|---|
| **Phase 1** | 1,000 workers | Single Oracle Cloud Free Tier server | 10K transactions/day |
| **Phase 2** | 10,000 workers | ARM server + solar panels + ClickHouse | 100K transactions/day |
| **Phase 3** | 100,000 workers | Mini DC (3-5 ARM servers, 10-20 kW solar array) | 1M transactions/day |
| **Phase 4** | 1,000,000 workers | Containerized pan-African DC network | 10M+ transactions/day |

### Why Solar + ARM?

- Kenya solar: $0.03-0.04/kWh (vs US $0.10-0.15/kWh)
- ARM servers: 3-5x better performance/watt, 70-80% lower cost
- Geothermal (Olkaria): $0.05/kWh — cheaper than China's coal
- Data sovereignty: African data processed in Africa, by African infrastructure

## API Endpoints

### Core
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Worker registration |
| POST | `/api/v1/auth/login` | Authentication |
| POST | `/api/v1/sync/upload` | Transaction batch upload |
| GET | `/api/v1/sync/intelligence/{worker_id}` | Pull intelligence for worker |
| POST | `/api/v1/analysis/deep` | Deep analysis via cloud model |

### Intelligence Products
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/intelligence/gdp/{county}/{period}` | GDP estimation |
| GET | `/api/v1/intelligence/inflation/{county}/{period}` | Inflation tracking |
| POST | `/api/v1/intelligence/alama/score` | Credit score calculation |
| GET | `/api/v1/intelligence/soko/pulse` | Market intelligence |
| GET | `/api/v1/intelligence/jamii/insights` | Community intelligence |
| GET | `/api/v1/intelligence/tax-base/{county}` | Tax compliance estimation |
| GET | `/api/v1/intelligence/distribution-gap` | Market coverage analysis |
| POST | `/api/v1/intelligence/fmcg/track` | FMCG brand tracking |

### Worker & Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/onboarding/register` | Worker onboarding |
| GET | `/api/v1/dashboard/critical-mass` | Worker acquisition dashboard |
| POST | `/api/v1/reports/formal/{user_id}/bank` | Bank-presentable report |
| POST | `/api/v1/reports/formal/{user_id}/government` | Government report |
| POST | `/api/v1/reports/formal/{user_id}/insurance` | Insurance report |

### Federated Learning
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/fl/upload-update` | Federated learning update |
| GET | `/api/v1/fl/global-model/{dialect}` | Get aggregated model |

### Infrastructure
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/infrastructure/roadmap` | Data center roadmap status |
| GET | `/api/v1/infrastructure/worker-value` | Worker value metrics |
| GET | `/api/v1/pricing/outcome/{product}` | Outcome-based pricing |

### WhatsApp
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/whatsapp/connect` | Connect WhatsApp number |
| POST | `/api/v1/whatsapp/verify` | Verify WhatsApp connection |
| POST | `/api/v1/whatsapp/send-report` | Send report via WhatsApp |
| POST | `/api/v1/whatsapp/webhook` | Incoming message webhook |

Full API documentation: [API.md](API.md)

## Degree Integration (42 units)

Every intelligence product is driven by Valentine's BSc Economics & Statistics from Masinde Muliro University:

| Unit | Application |
|------|-------------|
| ECO 201 | Price elasticity, consumer surplus → Soko Pulse |
| STA 341 | MLE, Bayesian estimation → Alama Score |
| STA 244 | ARIMA, VAR, cointegration → price forecasting |
| ECO 421 | Laffer curve, Ramsey rule → Tax Base |
| STA 442 | PCA, factor analysis, LDA → credit scoring |
| STA 444 | KDE, bootstrap, LOESS → non-parametric methods |

Full mapping: [ARCHITECTURE_MAPPING.md](ARCHITECTURE_MAPPING.md)

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | **Python 3.12** | Backend development |
| Framework | **FastAPI** | Async REST API |
| Data Processing | **Polars** | High-performance DataFrames (replaces pandas) |
| Analytics DB | **ClickHouse** | OLAP queries on 600M+ records |
| Production DB | PostgreSQL 15 | Transactional data |
| Development DB | SQLite | Local development |
| Cache | Redis | Caching, rate limiting, session store |
| Task Queue | Celery | Background task processing |
| WhatsApp | OpenWA | WhatsApp integration (unlimited, not Meta API) |
| ML Inference | ONNX Runtime | Statistical models |
| LLM | NVIDIA NIM | Free cloud LLM endpoints |
| Containers | Docker + Docker Compose | Deployment |
| Reverse Proxy | Nginx | SSL termination, rate limiting |
| Logging | structlog | Structured logging |
| Monitoring | Sentry | Error tracking |

## Security

- JWT + API key authentication
- k-anonymity (k≥10)
- Differential privacy (ε=1.0, δ=1e-5)
- AES-256-GCM encryption at rest
- HMAC-SHA256 for data anonymization
- Rate limiting (per-endpoint)
- CORS (localhost default, configurable)
- Path traversal protection
- Input validation on all endpoints

## Deployment

### One-Command Setup (Oracle Cloud Free Tier)
```bash
curl -sSL https://raw.githubusercontent.com/ovalentine964/biashara-intelligence-backend/main/deploy.sh | bash
```

### Docker
```bash
# Standard deployment
docker-compose up -d

# Oracle Cloud optimized
docker-compose -f docker-compose.oracle.yml up -d
```

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run with hot reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v
```

See [DEPLOYMENT.md](DEPLOYMENT.md) and [DEPLOYMENT_ORACLE.md](DEPLOYMENT_ORACLE.md) for details.

## Reports Delivered via WhatsApp

| Report | Frequency | Content |
|--------|-----------|---------|
| Daily | 7 PM | P&L, restock alerts, tomorrow forecast |
| Weekly | Mon 8 AM | Trends, customer insights, business health |
| Monthly | 1st 9 AM | Revenue growth, supplier comparison, credit readiness |
| 6-Month | Jun 30 & Dec 31 | Business review, seasonal patterns, formalization |
| Yearly | Dec 31 | Annual review, tax summary, next year goals |

## License

Proprietary — Angavu Intelligence
