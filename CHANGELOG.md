# Changelog — Angavu Intelligence Backend

All notable changes to the Angavu Intelligence Backend are documented here.

---

## [v0.3.0] — 2026-08-01

### 🧠 Credit Scoring & Explainability
- **NEW: SHAP Explainer** (`credit/shap_explainer.rs`) — Replaces hand-crafted `ScoreFactor` heuristics with computed Shapley values. Linear exact formula for logistic regression, KernelSHAP fallback for non-linear models. EU AI Act compliance metadata in every explanation.
- **NEW: Fairness Testing** (`credit/fairness.rs`) — Demographic parity (≤20%), equalized odds (≤15%), predictive parity (≤10%) with Z-test for proportions. Disparate impact ratio (4/5ths rule). Minimum group size enforcement (n≥30).
- **NEW: Classical Credit Scorer** (`credit/classical_algorithms.rs`) — Full IRLS logistic regression with Ridge regularization, Gauss-Seidel solver, AUC-ROC computation, feature importance.
- **NEW: Simulated Annealing Optimizer** — Quantum-inspired optimization with configurable cooling schedule, QUBO-compatible, binary/integer/continuous variable support.
- **NEW: Classical Search Engine** — Cosine similarity + greedy bipartite matching for worker-job assignment.
- **NEW: Model Registry** (`credit/model_registry.rs`) — Model versioning, A/B testing framework, algorithm tier selection (Classical/QuantumInspired/Quantum).

### 🔒 Privacy & Security
- **ε-DP in demand forecasts** — Laplace mechanism on daily predictions (sensitivity=1, pure ε-DP). Confidence bounds expanded proportionally.
- **k-Anonymity enforcement** — Wired into `market_analysis` and `demand_forecast` endpoints. Counts distinct `worker_id` values for true k-anonymity. Returns 403 `K_ANONYMITY_VIOLATION` if cohort < 10.
- **Working privacy noise API** — `POST /api/v1/tools/privacy/noise` and `POST /api/v1/tools/anonymization` now return real noisy values with budget tracking (was 501 NOT_IMPLEMENTED).
- **Privacy budget tracking** — RDP composition with per-query-type budgets, time-windowed reset. Queries suppressed when global budget exhausted.
- **Data retention engine** (`gateway/data_retention.rs`) — 10 data categories with configurable retention periods. Right-to-erasure cascading deletion (Kenya DPA 2019). PostgreSQL migration for `data_retention_log` and `erasure_requests` tables.
- **JWT token revocation** — `jti` claim on all tokens, Redis blacklist, logout endpoint. Access token TTL reduced to 15 minutes (was 1 hour).
- **Request body size limits** — 10 MB global limit via `RequestBodyLimitLayer`.
- **Per-request timeouts** — 30 second global timeout via `TimeoutLayer`.
- **Security headers** — HSTS, X-Content-Type-Options, X-Frame-Options, CSP, Referrer-Policy, Permissions-Policy.
- **Client IP extraction** — X-Forwarded-For → X-Real-IP → ConnectInfo priority chain.
- **HMAC webhook verification** — SHA-256 signature verification with constant-time comparison.
- **Authorization fix** — Fixed bypass on `list_pending` endpoint (now requires self or admin).
- **Response compression** — gzip, brotli, deflate via `CompressionLayer`.
- **Vary: Origin header** — Proper CDN/proxy caching.
- **`#![deny(missing_docs)]`** — Compile-time documentation enforcement.

### 📊 Inequality & Economic Analysis
- **NEW: Inequality Tracker** (`orchestrator/modules/inequality.rs`) — Gini coefficient, Palma ratio, Theil index (GE(1)) with full decomposition (within/between groups), Theil L (GE(0)), D9/D1 ratio, median/mean income, trend analysis. 13 unit tests.

### 🔗 Market Intelligence (PostgreSQL-backed)
- **MarketAnalyzer** — Now PostgreSQL-backed with `with_pool()` + `load_state()` + `persist_state()`. 5 new tables: `market_windows`, `fmcg_signals`, `distribution_gaps`, `service_prices`, `service_price_broadcasts`.
- **ServicePriceDiscoveryEngine** — New module aggregating service price broadcasts into market signals. k-anonymity enforced (≥10 broadcasts before signal generation).
- **Data retention** — Automated cleanup: raw broadcasts (90d), market windows/FMCG/distribution (30d stale), service prices (90d). Scheduled via pg_cron.

### 🔬 Federated Learning
- **Gradient sparsification** — Top-k, random-k, threshold-based strategies. Configurable sparsity ratio.
- **Robust aggregation** — TrimmedMean (discard top/bottom β=10%), CoordinateMedian, Krum strategies.
- **Convergence monitoring** — Tracks loss, gradient norms, cohort counts per round. Moving average convergence detection.
- **Usage alerts** — Normal (0-80%), Warning (80-95%), Critical (95-100%), Exceeded (100%+). Redis-based deduplication.

### 📡 Infrastructure & Observability
- **OpenTelemetry integration** — 26 `#[tracing::instrument]` attributes across all critical async paths (OODA loop, orchestrator, sync, webhook, graphql, pipeline, drift).
- **Structured JSON logging** — JSON tracing subscriber with correlation IDs.
- **X-Request-ID middleware** — UUID generation and span injection.
- **Request tracing middleware** — OTel spans for HTTP requests.
- **DB/Redis/ClickHouse tracing** — Wrapper functions with OTel spans.
- **Health endpoints** — 3-tier: `/health` (liveness), `/health/ready` (DB+Redis+ClickHouse), `/health/detailed` (pool stats, memory, CPU, uptime).
- **CI/CD pipeline** — 8-job GitHub Actions: fmt, clippy, build, test, coverage, audit, deny, docker.
- **Adaptive audit flush timer** — `MissedTickBehavior::Delay` for adaptive timer.

### 🏛️ Superagent Modules
- **ServicePriceDiscoveryEngine** added as 7th module to OODAOrchestrator.
- **Module count**: 6 → 7.
- **New API endpoints**: Auth (token/refresh/logout), credit explainability, fairness audit, health checks, privacy noise, anonymization, data retention.

### 📦 New Files
- `rust-api/src/credit/shap_explainer.rs` — SHAP explainability
- `rust-api/src/credit/fairness.rs` — Fairness testing
- `rust-api/src/credit/classical_algorithms.rs` — Classical algorithm implementations (688 lines)
- `rust-api/src/credit/model_registry.rs` — Model versioning & A/B testing (519 lines)
- `rust-api/src/orchestrator/modules/inequality.rs` — Inequality tracker (448 lines)
- `rust-api/src/orchestrator/modules/service_price_discovery.rs` — Service price discovery
- `rust-api/src/gateway/data_retention.rs` — Data retention & right-to-erasure (306 lines)
- `rust-api/src/gateway/security_headers.rs` — Security headers middleware
- `rust-api/src/telemetry/mod.rs` — Telemetry module root
- `rust-api/src/telemetry/correlation.rs` — X-Request-ID middleware
- `rust-api/src/telemetry/json_logging.rs` — Structured JSON logging
- `rust-api/src/telemetry/request_trace.rs` — Request tracing middleware
- `rust-api/src/telemetry/db_tracing.rs` — DB/Redis/CH span wrappers
- `rust-api/src/telemetry/health.rs` — Health check endpoints
- `.github/workflows/ci.yml` — CI/CD pipeline
- `migrations/20260801000008_market_persistence.sql` — Market module persistence tables

---

## [v0.2.0] — 2026-07-01

- 26 tools + 6 superagent modules
- OODA orchestrator (continuous intelligence loop)
- Billing engine (4 tiers, API keys, invoicing)
- REST API (Axum + WebSocket + GraphQL)
- Federated learning pipeline (FedProx aggregation)
- k-Anonymity enforcement (k≥10)
- Differential privacy engine (Laplace + Gaussian)
- Unified knowledge layer
- OpenTelemetry (basic setup)
- Docker + Oracle Free Tier deployment

---

## [v0.1.0] — 2026-06-01

- Initial release
- Basic API framework (Axum)
- PostgreSQL + pgvector setup
- Credit scoring (Alama Score)
- Market analysis
- Demand forecasting
- Economic indicators
- WhatsApp integration
- M-Pesa signal extraction

---

*Built by [Angavu Intelligence Ltd.](https://ovalentine964.github.io/angavu-intelligence/) — Africa's Economic Nervous System*
