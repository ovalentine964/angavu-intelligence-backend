![Biashara Intelligence](docs/logo-banner.svg)

# Biashara Intelligence — Cloud Platform

**Africa's economic nervous system. Processing data from 600M+ informal workers into economic intelligence.**

## Mission

Provide economic intelligence to Africa's 600M+ informal workers. Make invisible workers visible. Fix market inefficiencies, information asymmetry, and coordination failures.

## Vision

The platform that forces good governance through data. The CFO for every informal worker in Africa.

## Architecture

```
Msaidizi (Android) → Voice/Transaction Data → Biashara Intelligence (Cloud) → Intelligence Products → Buyers
     ↓                                            ↓                                        ↓
  600M+ workers                            15 intelligence products              12 buyer segments
  13+ dialects                             6 multi-agentic swarms                $89M-$400M TAM
  Offline-first                            Degree-driven (42 units)              Outcome-based pricing
```

## Intelligence Products (15)

### Existing (6)
| Product | Description | Buyers |
|---------|-------------|--------|
| **Soko Pulse** | Market intelligence — prices, demand, forecasting | FMCG, traders |
| **Biashara Pulse** | Economy monitoring — GDP, inflation, employment | Government, IMF |
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

## Multi-Agentic Swarms (33 agents)

| Swarm | Agents | Role |
|-------|--------|------|
| 🔄 Data Processing | 7 | Transaction, voice, pattern, quality, geo, receipt + coordinator |
| 🧠 Intelligence | 7 | Market, credit, economic, community, tax, distribution + coordinator |
| 📋 Reports | 5 | Worker, buyer, formal, WhatsApp, insight narrator |
| 🧬 Self-Evolution | 6 | Feedback, feature design, training, dialect, quality, experiments |
| 🎓 Learning | 4 | Federated, active learner, model evaluator, knowledge distiller |
| 🛡️ Governance | 4 | Security, privacy, compliance, audit |

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

- **Python 3.12** + FastAPI 2.0
- **PostgreSQL 15** (production) / SQLite (development)
- **Redis** (caching, rate limiting)
- **Celery** (background tasks)
- **OpenWA** (WhatsApp — unlimited, not Meta API)
- **ONNX Runtime** (ML inference)
- **NVIDIA NIM** (free cloud LLM endpoints)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/sync/upload` | Transaction batch upload |
| GET | `/api/v1/sync/intelligence/{worker_id}` | Pull intelligence for worker |
| POST | `/api/v1/analysis/deep` | Deep analysis via cloud model |
| GET | `/api/v1/intelligence/gdp/{county}/{period}` | GDP estimation |
| GET | `/api/v1/intelligence/inflation/{county}/{period}` | Inflation tracking |
| POST | `/api/v1/onboarding/register` | Worker onboarding |
| GET | `/api/v1/dashboard/critical-mass` | Worker acquisition dashboard |
| GET | `/api/v1/pricing/outcome/{product}` | Outcome-based pricing |
| POST | `/api/v1/reports/formal/{user_id}/bank` | Bank-presentable report |
| POST | `/api/v1/fl/upload-update` | Federated learning update |
| GET | `/api/v1/fl/global-model/{dialect}` | Get aggregated model |

Full API documentation: [API.md](API.md)

## Security

- JWT + API key authentication
- k-anonymity (k≥10)
- Differential privacy (ε=1.0, δ=1e-5)
- AES-256-GCM encryption at rest
- HMAC-SHA256 for data anonymization
- Rate limiting (per-endpoint)
- CORS (localhost default, configurable)

## Deployment

### One-Command Setup (Oracle Cloud Free Tier)
```bash
curl -sSL https://raw.githubusercontent.com/ovalentine964/biashara-intelligence-backend/main/deploy.sh | bash
```

### Docker
```bash
docker-compose up -d
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

Proprietary — Biashara Intelligence
