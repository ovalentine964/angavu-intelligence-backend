<p align="center">
  <img src=".github/banner.svg" alt="Angavu Intelligence Backend — Rust CFO Platform" width="100%">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Rust-DEA584?style=flat-square&logo=rust&logoColor=white" alt="Rust">
  <img src="https://img.shields.io/badge/PostgreSQL-336791?style=flat-square&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker">
  <img src="https://img.shields.io/badge/Tools-26+-1B4965?style=flat-square" alt="26+ Tools">
  <img src="https://img.shields.io/badge/Federated_Learning-E8A838?style=flat-square" alt="Federated Learning">
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square" alt="License">
</p>

> **Africa's Economic Nervous System.** Rust-powered backend that transforms anonymized worker data into economic intelligence — 26 tools, 6 superagent modules, 15 revenue engines, a federated learning pipeline, and a unified knowledge graph.
>
> **Key claims (with citations):**
> - Kenya's informal sector employs **83.4% of the workforce** (Kenya National Bureau of Statistics, 2023 Economic Survey) [1]
> - Mobile money (M-Pesa) processed **KES 35.5 trillion** in 2023 (Central Bank of Kenya, 2023) [2]
> - k-Anonymity (k≥10) prevents re-identification in cohort-level data releases (Sweeney, 2002) [3]
> - Federated learning enables privacy-preserving model training across devices (McMahan et al., 2017) [4]
> - HNSW indexes achieve 95-99% recall@10 vs 85-95% for IVFFlat (Malkov & Yashunin, 2018) [5]
> - Brandes' algorithm computes betweenness centrality in O(VE) time (Brandes, 2001) [6]

**Built by [Angavu Intelligence Ltd.](https://ovalentine964.github.io/angavu-intelligence/)** — Migori, Kenya

---

## Architecture

**Rust (Axum)** = Primary backend — API, business logic, security, OODA loop  
**Python** = LLM inference ONLY — DeepSeek, Qwen, XGBoost

```
OODAOrchestrator (Continuous Intelligence Loop)
├── 26 Rust Tools (analysis, privacy, infrastructure, monitoring)
├── 6 Superagent Modules (flywheel, guardrails, intelligence, memory, sync)
├── UnifiedKnowledgeLayer (in-memory + PostgreSQL + Harness graph bridge)
├── Billing Engine (4 tiers, API keys, invoicing)
├── REST API (Axum + WebSocket + GraphQL)
└── OpenTelemetry Distributed Tracing (4 OODA cycle spans)
```

**Tech Stack:** Rust (Axum + Tokio) · PostgreSQL 16 + pgvector (HNSW) · ClickHouse 24 · Redis 7 · Docker · Nginx · OpenTelemetry

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
| `DifferentialPrivacyEngine` | ε-differential privacy with Laplace mechanism (ε=0.1 default), privacy budget tracking |
| `KAnonymityEnforcer` | k≥10 anonymity cohort enforcement (MIN_K_ANONYMITY constant) |
| `FederatedAggregator` | Privacy-preserving FedProx gradient aggregation (μ=0.01 proximal term) |
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
| `UnifiedKnowledgeLayer` | Bridges 3 disconnected knowledge graphs (in-memory, PostgreSQL, Harness) into single interface with cross-reference indices |

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

### Superagent (`/api/v1/superagent`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/superagent/status` | Orchestrator status |
| POST | `/api/v1/superagent/cycles` | Trigger OODA cycle |
| POST | `/api/v1/superagent/invocations` | Invoke superagent |
| POST | `/api/v1/superagent/alert/respond` | Respond to alert |
| GET | `/api/v1/superagent/alerts` | List alerts |
| GET | `/api/v1/superagent/history` | Cycle history |

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
- **Dockerfile.oracle** — ARM64-optimized for Oracle Free Tier (4 OCPU, 24GB RAM). No Python/ClickHouse/monitoring.
- **docker-compose.yml** — Full stack: PostgreSQL 16, Redis 7, ClickHouse 24, Nginx, API
- **docker-compose.oracle.yml** — Resource-constrained for Oracle Free Tier (PG 8GB, Redis 1GB, API 4GB)
- **docker-compose.production.yml** — Production with WAL archiving, automated failover, replication
- **nginx/nginx.conf** — Reverse proxy with rate limiting, SSL termination, WebSocket support
- **.github/workflows/deploy.yml** — CI/CD: test → build → push GHCR → deploy to Oracle Cloud
- **OpenTelemetry** — Distributed tracing for OODA loops (OTLP exporter, Jaeger/Tempo compatible)

### Oracle Free Tier Deployment

```bash
# SSH into Oracle ARM Ampere A1 instance
ssh ubuntu@your-oracle-ip

# Clone and configure
git clone https://github.com/ovalentine964/angavu-intelligence-backend.git
cd angavu-intelligence-backend
cp .env.oracle.example .env.oracle
nano .env.oracle  # set passwords and secrets

# Deploy
chmod +x scripts/deploy-oracle.sh
./scripts/deploy-oracle.sh

# Verify
./scripts/deploy-oracle.sh --status
curl http://localhost:8000/health
```

See [`scripts/deploy-oracle.sh`](scripts/deploy-oracle.sh) for full deployment automation with health checks, backup rotation, and zero-downtime updates.

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
- [API Documentation](docs/API.md)
- [OpenAPI Spec](docs/openapi.yaml)
- [DPIA (Kenya DPA Compliance)](docs/compliance/DPIA.md)
- [SLO Definitions](docs/slo-definitions.md)

---

## Company

**Angavu Intelligence Ltd.** — Africa's Economic Nervous System

- 🌐 [Website](https://ovalentine964.github.io/angavu-intelligence/)
- 📧 hello@angavuintelligence.com
- 📍 Migori, Kenya

---

## References

[1] Kenya National Bureau of Statistics. (2023). *Economic Survey 2023*. Nairobi: KNBS. The informal sector accounts for 83.4% of total employment.

[2] Central Bank of Kenya. (2023). *Mobile Payments Statistics — Annual Report 2023*. M-Pesa processed KES 35.5 trillion across 1.6 billion transactions.

[3] Sweeney, L. (2002). k-Anonymity: A Model for Protecting Privacy. *International Journal of Uncertainty, Fuzziness and Knowledge-Based Systems*, 10(5), 557-570. https://doi.org/10.1142/S0218488502001648

[4] McMahan, B., Moore, E., Ramage, D., Hampson, S., & y Arcas, B. A. (2017). Communication-Efficient Learning of Deep Networks from Decentralized Data. *Proceedings of the 20th International Conference on Artificial Intelligence and Statistics (AISTATS)*. arXiv:1602.05629

[5] Malkov, Y. A., & Yashunin, D. A. (2018). Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 42(4), 824-836. arXiv:1603.09320

[6] Brandes, U. (2001). A faster algorithm for betweenness centrality. *Journal of Mathematical Sociology*, 25(2), 163-177. https://doi.org/10.1080/0022250X.2001.9990249

[7] Dwork, C., & Roth, A. (2014). The Algorithmic Foundations of Differential Privacy. *Foundations and Trends in Theoretical Computer Science*, 9(3-4), 211-407. https://doi.org/10.1561/0400000042

[8] Kairouz, P., et al. (2021). Advances and Open Problems in Federated Learning. *Foundations and Trends in Machine Learning*, 14(1-2), 1-210. arXiv:1912.04977

[9] Brier, G. W. (1950). Verification of Forecasts Expressed in Terms of Probability. *Monthly Weather Review*, 78(1), 1-3. https://doi.org/10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2

[10] Banerjee, A., Duflo, E., Glennerster, R., & Kinnan, C. (2015). The Miracle of Microfinance? Evidence from a Randomized Evaluation. *American Economic Journal: Applied Economics*, 7(1), 22-53. https://doi.org/10.1257/app.20130533
