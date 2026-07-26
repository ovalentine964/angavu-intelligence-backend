<p align="center">
  <img src=".github/banner.svg" alt="Angavu Intelligence Backend — Rust CFO Platform" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Rust-DEA584?style=flat-square&logo=rust&logoColor=white" alt="Rust">
  <img src="https://img.shields.io/badge/PostgreSQL-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Tools-26+-1B4965?style=flat-square" alt="26+ Tools">
  <img src="https://img.shields.io/badge/Federated_Learning-E8A838?style=flat-square" alt="Federated Learning">
  <img src="https://img.shields.io/badge/License-SSPL--1.0-blue?style=flat-square" alt="License">
</p>

> **Africa's Economic Nervous System.** Rust-powered backend that transforms anonymized worker data into economic intelligence — 26 tools, 6 superagent modules, 15 revenue engines, and a federated learning pipeline.

**Built by [Angavu Intelligence Ltd.](https://ovalentine964.github.io/angavu-intelligence/)** — Migori, Kenya

---

## Architecture

**Rust (Axum)** = Primary backend — API, business logic, security, OODA loop  
**Python** = LLM inference ONLY — DeepSeek, Qwen, XGBoost

```
OODAOrchestrator (Continuous Intelligence Loop)
├── 26 Rust Tools (analysis, privacy, infrastructure, monitoring)
├── 6 Superagent Modules (flywheel, guardrails, intelligence, memory, sync)
├── Billing Engine (4 tiers, API keys, invoicing)
└── REST API (Axum + WebSocket)
```

**Tech Stack:** Rust (Axum + Tokio) · PostgreSQL 16 + pgvector · ClickHouse 24 · Redis 7 · Docker · Nginx

---

## Tool Inventory — 26 Tools + 6 Superagent Modules

### Intelligence & Analysis
| Tool | Purpose |
|------|---------|
| `OODAOrchestrator` | Continuous Observe-Orient-Decide-Act intelligence loop |
| `MarketAnalyzer` | Aggregated demand pattern analysis across worker cohorts |
| `CreditScorer` | Alama Score (300–850) — credit scoring for informal economy |
| `DemandForecaster` | Time-series demand forecasting for products and markets |
| `EconomicAnalyzer` | Macro/micro economic indicator computation |
| `FMCGIntelligence` | Fast-moving consumer goods market intelligence |
| `CompositeIndexBuilder` | Multi-factor composite economic indices |
| `AnomalyDetector` | Statistical anomaly detection in transaction streams |
| `ScenarioModeler` | What-if scenario simulation and stress testing |
| `PolicyImpactAnalyzer` | Government policy impact measurement |
| `InequalityTracker` | Gini, Theil, and distributional inequality metrics |

### Privacy & Security
| Tool | Purpose |
|------|---------|
| `DifferentialPrivacyEngine` | ε-differential privacy with calibrated noise injection |
| `KAnonymityEnforcer` | k≥10 anonymity cohort enforcement |
| `FederatedAggregator` | Privacy-preserving federated model updates |
| `ModelDistributor` | Secure model distribution to edge devices |

### Infrastructure
| Tool | Purpose |
|------|---------|
| `ApiGateway` | REST API gateway with auth and routing |
| `CircuitBreaker` | Fault isolation and cascade failure prevention |
| `RateLimiter` | Token-bucket rate limiting per API key |
| `AuditLogger` | Immutable audit trail for all operations |
| `SyncReceiver` | Device data reception and conflict resolution |

### Monitoring & Reporting
| Tool | Purpose |
|------|---------|
| `HealthMetrics` | System health and performance metrics |
| `ReportEngine` | Automated business and intelligence reports |
| `AlertGenerator` | Threshold-based alerting and notification |
| `WhatsAppSender` | WhatsApp Business API integration for alerts |
| `MobileMoneySignalExtractor` | M-Pesa/mobile money transaction signal extraction |

### Superagent Modules
| Module | Purpose |
|--------|---------|
| `FlywheelEngine` | Data network effects — more data → better models → more users |
| `GuardrailsEngine` | Financial integrity checks, advice validation, compliance |
| `IntelligenceEngine` | LLM-powered insight generation and reasoning |
| `MemoryEngine` | 5-layer memory hierarchy (working → knowledge) |
| `SyncEngine` | Bidirectional device-cloud synchronization |

---

## Academic Formulas

The platform implements peer-reviewed statistical and econometric methods:

| Formula | Module | Application |
|---------|--------|-------------|
| **Bayesian Inference** | CreditScorer | Prior belief updating with transaction evidence |
| **Maximum Likelihood Estimation (MLE)** | CreditScorer | Parameter calibration for score model |
| **Gini Coefficient** | InequalityTracker | Income/expenditure concentration measurement |
| **Theil Index** | InequalityTracker | Decomposable inequality (within/between groups) |
| **Monte Carlo Simulation** | ScenarioModeler | Risk scenario generation and stress testing |
| **Ordinary Least Squares (OLS)** | PolicyImpactAnalyzer | Causal effect estimation for policy interventions |
| **Interrupted Time Series (ITS)** | PolicyImpactAnalyzer | Pre/post policy impact measurement |
| **Difference-in-Differences (DiD)** | PolicyImpactAnalyzer | Quasi-experimental treatment effect estimation |
| **Herfindahl-Hirschman Index (HHI)** | MarketAnalyzer | Market concentration and competition analysis |

---

## Billing System

| Tier | Price | Queries/mo | Reports/mo | Data Exports |
|------|-------|-----------|------------|--------------|
| **Free** | $0 | 100 | 2 | — |
| **Starter** | $299/mo | 5,000 | 20 | 5 |
| **Pro** | $1,499/mo | 50,000 | 100 | 50 |
| **Enterprise** | Custom | Unlimited | Unlimited | Unlimited |

Features: API key management, usage metering, invoice generation, subscription lifecycle.

---

## API Endpoints

### Tools (`/api/v1/tools`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tools` | List all available tools |
| GET | `/tools/health` | System health metrics |
| POST | `/tools/credit` | Compute Alama credit score |
| GET | `/tools/market` | Market analysis |
| GET | `/tools/market/demand` | Demand forecast |
| POST | `/tools/economic` | Economic indicators |
| GET | `/tools/distribution` | Distribution gap analysis |
| GET | `/tools/fmcg` | FMCG intelligence report |
| POST | `/tools/privacy/noise` | Inject differential privacy noise |
| POST | `/tools/anonymize` | Apply k-anonymity |
| GET | `/tools/federated` | Federated learning status |
| GET | `/tools/sync` | Sync status |
| GET | `/tools/model` | Model distribution status |
| POST | `/tools/report` | Generate report |
| POST | `/tools/alert` | Generate alert |
| POST | `/tools/whatsapp` | Send WhatsApp message |
| GET | `/tools/gateway` | API gateway status |
| GET | `/tools/audit` | Audit log status |
| GET | `/tools/circuit-breaker` | Circuit breaker status |
| GET | `/tools/rate-limiter` | Rate limiter status |

### Billing (`/api/v1/billing`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/billing/tiers` | List pricing tiers |
| POST | `/billing/subscriptions` | Create subscription |
| GET | `/billing/subscriptions/{org_id}` | Get subscription |
| PUT | `/billing/subscriptions/{id}/tier` | Change tier |
| POST | `/billing/subscriptions/{id}/cancel` | Cancel subscription |
| POST | `/billing/api-keys` | Create API key |
| GET | `/billing/api-keys/{org_id}` | List API keys |
| DELETE | `/billing/api-keys/{id}` | Revoke API key |
| GET | `/billing/usage/{org_id}` | Get usage metrics |
| GET | `/billing/invoices/{org_id}` | List invoices |
| GET | `/billing/invoices/detail/{id}` | Get invoice detail |
| POST | `/billing/invoices/{id}/finalize` | Finalize invoice |
| POST | `/billing/invoices/{id}/pay` | Pay invoice |

### Superagent (`/superagent`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/superagent/status` | Orchestrator status |
| POST | `/superagent/cycle` | Trigger OODA cycle |
| POST | `/superagent/invoke` | Invoke superagent |
| POST | `/superagent/alert/respond` | Respond to alert |
| GET | `/superagent/alerts` | List alerts |
| GET | `/superagent/history` | Cycle history |

### WebSocket
| Endpoint | Description |
|----------|-------------|
| `ws://host/ws` | Real-time data stream |

---

## 15 Revenue Engines

| Engine | Buyer | Price |
|--------|-------|-------|
| Soko Pulse | FMCG companies | $2K–$12K/month |
| Alama Score | Banks, MFIs | $0.05–$0.50/query |
| Angavu Pulse | Government | Contact for pricing |
| + 12 more | Various | Various |

---

## Infrastructure

- **Dockerfile** — Multi-stage build (Rust builder → Python LLM → minimal runtime)
- **docker-compose.yml** — Full stack: PostgreSQL 16, Redis 7, ClickHouse 24, Nginx, API
- **nginx/nginx.conf** — Reverse proxy with rate limiting, SSL termination, WebSocket support
- **.github/workflows/deploy.yml** — CI/CD: test → build → push GHCR → deploy to Oracle Cloud

---

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your API keys and secrets

# Start full stack
docker compose up -d

# Verify
curl http://localhost:8000/health
```

---

## Documentation

- [Superagent Architecture](docs/architecture/arch_superagent_design.md)
- [Tools Definition](docs/architecture/superagent_tools_definition.md)
- [Grand Synthesis](docs/architecture/grand_synthesis_architecture.md)
- [Revenue Models](docs/research/research_revenue_models.md)
- [Tech Stack](docs/architecture/arch_techstack_enterprise.md)
- [Federated Pipeline](docs/architecture/growth_federated_pipeline.md)

---

## Company

**Angavu Intelligence Ltd.** — Africa's Economic Nervous System

- 🌐 [Website](https://ovalentine964.github.io/angavu-intelligence/)
- 📧 hello@angavuintelligence.com
- 📍 Migori, Kenya
