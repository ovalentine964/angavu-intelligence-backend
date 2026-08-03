# Angavu Intelligence Backend — Deep Architecture Analysis Report

**Prepared by:** Backend Council  
**Date:** 2026-08-03  
**Codebase:** `/angavu-intelligence-backend/`  
**Total Rust source:** 183 files, ~61,000 lines of Rust

---

## 1. Architecture Analysis

### 1.1 Workspace Structure

The project is a **single-crate Rust binary** (not a Cargo workspace with multiple members). The `Cargo.toml` defines:

- **Binary 1:** `angavu-server` → `rust-api/src/main.rs` (main HTTP server)
- **Binary 2:** `angavu-migrate` → `rust-api/src/migrate.rs` (database migration runner)
- **Edition:** Rust 2021, Apache-2.0 license

**Module tree** (18 public modules in `lib.rs`):

```
rust-api/src/
├── agent/          — Tool registry (26 tools), function calling engine, autonomous agent, memory
├── behavioral/     — Behavioral economics (segmentation, risk attitude, nudge effectiveness, reference price)
├── billing/        — Full billing engine (subscriptions, M-Pesa STK push, invoices, metering)
├── credit/         — Core credit scoring (logistic regression, SHAP, federated learning, fairness, 17 sector extractors)
│   └── extractors/ — 17 informal-sector feature extractors (farmer, boda_boda, mpesa_agent, jua_kali, etc.)
├── gateway/        — API gateway (JWT auth, rate limiting, k-anonymity, audit, security headers, data retention)
├── graph/          — Knowledge graph (algorithms, OODA, pgvector HNSW, federated graph, caching)
├── graphql/        — GraphQL schema (async-graphql, PageRank, communities, shortest path)
├── health/         — Health insurance scoring (location risk, occupation hazards)
├── llm/            — LLM provider abstraction (DeepSeek, Qwen)
├── loops/          — Loop engineering (OODA loop, drift detection, circuit breaker, pipeline feedback)
├── observability/  — Tracing, metrics, SLO, AGI training data capture
├── optimization/   — Operations research (simplex, network flow, dynamic programming, queuing, stochastic)
├── orchestrator/   — Multi-agent orchestrator (16 capability modules, message bus, supervisor)
│   └── modules/    — 16 domain modules (market, credit, distribution, fmcg, health, economic, inequality, trade_gravity, etc.)
├── rag/            — RAG pipeline (credit/health/market context retrieval)
├── routes/         — Route handlers (observability, OODA, trace analysis)
├── service_pricing/— Service price discovery
├── statistical/    — Statistical engines (differential privacy, 10 bridge modules for econometrics/distributions/time-series)
├── sync/           — Device sync (receiver, verification, freshness, version compatibility)
├── telemetry/      — Structured JSON logging, OpenTelemetry OTLP, correlation IDs, health checks
├── tests/          — Integration and unit tests (orchestrator, credit scoring, k-anonymity, sync, load)
└── webhook/        — Webhook handlers (M-Pesa, market feed, generic)
```

### 1.2 Tool Organization & Registration

**26 tools** defined in `agent/tool_registry.rs`, organized by category:

| Category | Count | Tools |
|---|---|---|
| **Credit** | 8 | `credit_score_compute`, `credit_score_history`, `credit_risk_assessment`, `credit_decision_recommend` ⚠️, `credit_batch_score`, `credit_cohort_analysis`, `credit_default_predict`, `credit_seasonality_adjust` |
| **Market** | 6 | `market_analysis`, `market_price_lookup`, `market_demand_forecast`, `market_trend_detect`, `market_opportunity_scan`, `market_competitor_analysis` |
| **Intelligence** | 4 | `intelligence_report_generate`, `intelligence_anomaly_detect`, `intelligence_pattern_mine`, `intelligence_knowledge_query` |
| **Data** | 4 | `data_transaction_query`, `data_cohort_lookup`, `data_aggregate`, `data_export` |
| **Federated** | 2 | `federated_status`, `federated_trigger_round` ⚠️ |
| **System** | 2 | `system_health_check`, `system_model_status` |

⚠️ = `requires_approval: true` (human-in-the-loop required before execution)

**Registration pattern:** `ToolRegistry` uses `DashMap<String, ToolDefinition>` + `DashMap<String, Arc<dyn ToolExecutor>>` for lock-free concurrent access. Each tool has:
- OpenAI function-calling compatible JSON Schema
- Risk level (Low/Medium/High/Critical)
- Timeout in seconds
- Read-only flag
- Approval requirement flag

### 1.3 OODAOrchestrator Loop Design

The OODA (Observe-Orient-Decide-Act) loop is the system's central intelligence engine:

**Architecture:**
- **4 loop speeds:** Fast (1s/event-driven), Medium (1h), Slow (24h), Deep (7d)
- **Phase tracking:** Each cycle progresses through Observe → Orient → Decide → Act
- **Episodic memory:** Knowledge graph integration via `EpisodicMemory` with `MemoryConsolidator`
- **Drift detection:** Statistical drift monitoring triggers retraining alerts
- **Circuit breakers:** Per-module circuit breakers prevent cascade failures
- **Pipeline feedback:** 30-second feedback loop for pipeline metrics

**16 Capability Modules** (via `CapabilityModule` trait):
`market`, `credit`, `distribution`, `fmcg`, `health`, `economic`, `service_price_discovery`, `inequality`, `gender_inequality`, `occupation_hazard_matrix`, `health_economics`, `trade_gravity`, `fiscal_impact`, `market_concentration`, `property_rights`, `governance_quality`

Each module implements `process()` → `Option<ModuleMessage>` and supports state snapshots for persistence.

**Message Bus:** `ModuleMessageBus` with channel-based routing, audit buffering, and adaptive flush (60s timer fallback + event-driven flush at buffer capacity).

### 1.4 API Surface

**REST Endpoints (Axum):**

| Path | Method | Status |
|---|---|---|
| `/api/v1/auth/token` | POST | ✅ Implemented |
| `/api/v1/auth/refresh` | POST | ✅ Implemented |
| `/api/v1/auth/logout` | POST | ✅ Implemented |
| `/api/v1/tools` | GET | ✅ Static tool list |
| `/api/v1/tools/credit-scores` | POST | ✅ Implemented (D1) |
| `/api/v1/tools/market-analyses` | GET | ✅ Implemented (D1) |
| `/api/v1/tools/demand-forecasts` | GET | ✅ Implemented (D1) |
| `/api/v1/tools/credit/:id/explain` | GET | ✅ SHAP explanation |
| `/api/v1/tools/privacy/noise` | POST | ✅ Implemented |
| `/api/v1/tools/anonymization` | POST | ✅ Implemented |
| `/api/v1/tools/federated-learning/status` | GET | ✅ Implemented |
| `/api/v1/tools/economic-indicators` | POST | ❌ 501 Stub |
| `/api/v1/tools/distribution-gaps` | GET | ❌ 501 Stub |
| `/api/v1/tools/fmcg-reports` | GET | ❌ 501 Stub |
| `/api/v1/tools/reports` | POST | ❌ 501 Stub |
| `/api/v1/superagent/status` | GET | ❌ 501 Stub |
| `/api/v1/superagent/cycles` | POST | ❌ 501 Stub |
| `/api/v1/superagent/invocations` | POST | ❌ 501 Stub |
| `/api/v1/sync/anonymized` | POST | ✅ Bidirectional sync |
| `/api/v1/sync/graph` | POST | ✅ Graph sync |
| `/api/v1/billing/*` | Various | ✅ 11 billing endpoints |
| `/api/v1/approvals/*` | Various | ✅ Human-in-the-loop |
| `/graphql` | POST | ✅ GraphQL (async-graphql) |
| `/health`, `/health/ready`, `/health/detailed` | GET | ✅ Health checks |

**GraphQL Queries:** `node`, `nodes`, `edges`, `shortest_path`, `subgraph`, `pagerank`, `communities`, `degree_centrality`, `graph_stats`

**WebSocket:** Axum WS feature is enabled but no explicit WebSocket endpoints are registered in the current router.

### 1.5 Database Schema & Migrations

**16 migration files** spanning 2024-01 to 2026-08:

| Migration | Purpose |
|---|---|
| `20240101000001_init.sql` | Core schema: organizations, users, intelligence_tasks, knowledge graph tables |
| `20240101000002_webhook_events.sql` | Webhook event logging |
| `20240101000003_billing.sql` | Billing tables |
| `20240101000004_knowledge_graph_economic.sql` | Economic knowledge graph extensions |
| `20240101000005_ooda_loop_state.sql` | OODA loop state persistence |
| `20240101000006_occupation_hazards.sql` | Occupation hazard data |
| `20240101000007_occupation_type_column.sql` | Schema fix |
| `20260727000001_multi_agent_orchestration.sql` | Multi-agent orchestration tables |
| `20260728000001_cross_repo_sync.sql` | Cross-repo sync support |
| `20260801000001_kg_memory_system.sql` | Knowledge graph memory |
| `20260801000004_economic_analyzer_state.sql` | Economic analyzer persistence |
| `20260801000005_hnsw_matryoshka.sql` | pgvector HNSW + Matryoshka embeddings |
| `20260801000006_pgcrypto_encryption.sql` | pgcrypto column-level encryption |
| `20260801000007_performance_indices.sql` | Performance indices |
| `20260801000008_market_persistence.sql` | Market data persistence |
| `20260802000001_sync_events_and_hnsw_fixes.sql` | Sync events + HNSW fixes |

**Extensions used:** `uuid-ossp`, `vector` (pgvector), `pgcrypto`

**Databases:** PostgreSQL 16 (primary), Redis 7 (cache/queues/blacklist), ClickHouse 24 (OLAP analytics)

**⚠️ Note:** Many tables are also created via inline SQL migration in `main.rs` (billing, audit, model registry, data retention). This dual-migration approach risks schema drift.

---

## 2. CI/CD Pipeline

### 2.1 GitHub Actions Workflows

**11 workflow files** in `.github/workflows/`:

| Workflow | Trigger | Jobs |
|---|---|---|
| `ci.yml` | push/PR to main/develop | **9 jobs:** fmt, clippy, build, test, coverage, cargo-audit, cargo-deny, docker-build, ci-passed gate |
| `deploy.yml` | push to main | test → build → push GHCR → deploy Oracle → health check → rollback-on-failure |
| `deploy-azure.yml` | Manual/dispatch | Azure Container Apps deployment |
| `staging.yml` | PR to main | Staging environment deploy |
| `security.yml` | Scheduled | Security scanning |
| `backup.yml` | Scheduled | Database backup |
| `db-backup.yml` | Scheduled | PostgreSQL backup with WAL archiving |
| `architecture-fitness.yml` | PR | Architecture validation |
| `docs-freshness.yml` | Scheduled | Documentation staleness check |
| `website.yml` | push to main | Website deployment |

### 2.2 CI Pipeline Health

**Current configuration is solid:**
- `RUSTFLAGS: "-D warnings"` — warnings treated as errors
- Cargo caching enabled for all jobs
- System deps properly installed (pkg-config, libssl-dev, libpq-dev, protobuf-compiler)
- Coverage threshold: 60% (tarpaulin, LLVM engine)
- Security: cargo-audit + cargo-deny (advisories + licenses)
- Docker build test on PRs
- Summary gate (`ci-passed`) requires all 6 core jobs

**⚠️ Potential issues:**
- Coverage only runs on PRs, not on push — could miss regressions on direct pushes
- No integration test environment (tests run without DB/Redis)
- `cargo audit` may fail if advisories are published between lock file updates

### 2.3 Docker Setup

**Multi-stage Dockerfile** (3 stages):
1. **rust-builder** — Rust 1.82-bookworm, dependency caching via dummy main.rs
2. **python-llm** — Python 3.12-slim for LLM inference sidecar
3. **runtime** — debian-bookworm-slim, non-root user (`angavu`), dumb-init for signal handling

**docker-compose.yml variants:**
- `docker-compose.yml` — Full stack (PostgreSQL+pgvector, Redis 7, ClickHouse 24, API, Nginx, Prometheus, Grafana, Alertmanager, exporters)
- `docker-compose.oracle.yml` — Oracle Cloud optimized
- `docker-compose.production.yml` — Production hardened
- `docker-compose.staging.yml` — Staging environment

**Resource limits** are well-configured: PostgreSQL 4GB, Redis 1.2GB, ClickHouse 2GB, API 3GB, total ~10.5GB for Oracle Free Tier (24GB available).

### 2.4 Deployment Configs

- **Oracle Cloud:** Primary deployment target (Free Tier), scripts in `deploy/oracle/`, `scripts/deploy-oracle.sh`
- **Azure:** Container Apps via Bicep IaC (`deploy/azure/main.bicep`), separate Dockerfile
- **Nginx:** 3 configs (dev, staging, production) with SSL termination
- **Monitoring:** Prometheus + Grafana + Alertmanager with pre-provisioned dashboards

---

## 3. Security & Privacy

### 3.1 Differential Privacy (ε-DP)

**Implementation:** `statistical/differential_privacy.rs`

- **Laplace mechanism:** Pure (ε,0)-DP for count/sum/mean queries
- **Gaussian mechanism:** (ε,δ)-DP with proper calibration: σ = Δf × √(2 × ln(1.25/δ)) / ε
- **Default:** ε=0.1 (strong privacy), δ=10⁻⁵
- **Budget tracking:** Cumulative ε consumption, max budget = 10.0, queries blocked when exhausted
- **API endpoint:** `POST /api/v1/tools/privacy/noise` — fully implemented
- **Tested:** 8 unit tests covering both mechanisms, budget exhaustion, noise scale calibration

### 3.2 k-Anonymity

**Implementation:** `gateway/k_anonymity.rs`

- **Threshold:** MIN_K = 10 (system-wide minimum, enforced everywhere)
- **Audit logging:** All decisions (allow + suppress) logged with endpoint, timestamp, reason
- **Alerting:** `tracing::warn` on violations
- **Cohort merging:** Small cohorts merged with nearest neighbors
- **API endpoint:** `POST /api/v1/tools/anonymization` — working (k-anonymity + DP combined)
- **Ring buffer:** Last 1000 audit records kept in memory

### 3.3 Federated Learning

**Implementation:** `credit/federated.rs`

- **Algorithm:** FedProx (proximal term μ penalizes deviation from global model)
- **DP integration:** Gaussian noise added per-dimension after gradient aggregation
  - `FedProxAggregator::credit_private(ε, δ)` — production-ready constructor
  - σ = noise_multiplier × clip_norm
- **Gradient clipping:** L2 norm clipping (sensitivity bound)
- **Byzantine robustness:** 4 aggregation strategies (WeightedAverage, TrimmedMean, CoordinateMedian, Krum)
- **Gradient sparsification:** Top-K, Threshold, RandomK for communication efficiency
- **Convergence monitoring:** Loss tracking, gradient explosion detection, max rounds guard
- **⚠️ Warning:** `credit_default()` sets `noise_multiplier=0.0` (NO DP) — logs a warning but doesn't fail

### 3.4 SHAP Explainability

**Implementation:** `credit/shap_explainer.rs`

- **Mathematical basis:** Shapley values via KernelSHAP approximation
- **Linear optimization:** For logistic regression, uses exact formula φᵢ = βᵢ × (xᵢ - x̄ᵢ) (O(n) instead of O(2ⁿ))
- **KernelSHAP fallback:** Weighted linear regression on coalitions (256 default samples)
- **EU AI Act compliance:** Produces `CreditExplanation` with per-feature Shapley values, human-readable descriptions, direction, and confidence
- **API endpoint:** `GET /api/v1/tools/credit/:score_id/explain` — implemented
- **Tested:** 5 unit tests including exact linear verification and reconstruction check

### 3.5 Fairness Testing

**Implementation:** `credit/fairness.rs`

Three fairness criteria with z-test significance testing:
1. **Demographic Parity:** Max 20% difference in positive prediction rate across worker types
2. **Equalized Odds:** Max 15% difference in TPR/FPR across regions
3. **Predictive Parity:** Max 10% difference in PPV across groups

Minimum group size: 30 for statistical validity. Aligned with EU AI Act "meaningful explanations" standard and US EEOC 4/5ths rule.

### 3.6 Privacy Budget (RDP Composition)

**Implementation:** `credit/privacy_budget.rs`

- **Rényi Differential Privacy** composition for tighter bounds than basic sequential
- **Per-query-type tracking:** 8 query types (CreditScore, MarketAnalysis, DemandForecast, etc.)
- **Time-windowed reset:** 24-hour default windows
- **Fail-closed:** Queries blocked when budget exhausted

### 3.7 JWT Authentication

**Implementation:** `gateway/auth.rs`

- **Token structure:** Access (15min TTL) + Refresh (30 days) with UUID v4 `jti` claims
- **Revocation:** Redis blacklist with TTL matching token expiry
- **Logout:** Token revoked on logout, refresh tokens are one-time-use
- **Client IP extraction:** X-Forwarded-For → X-Real-IP → ConnectInfo (proper proxy chain handling)
- **Tier-based access:** Free/Starter/Pro/Enterprise with rate limits (10-10,000 RPM) and query quotas

### 3.8 Rate Limiting

- **Authenticated routes:** Token-bucket per-buyer rate limiter
- **Unauthenticated routes:** Per-IP rate limiter (webhooks, approvals)
- **Tier-based:** Free=10 RPM, Enterprise=10,000 RPM

### 3.9 Security Headers

**All responses include:** HSTS (1 year), X-Content-Type-Options (nosniff), X-Frame-Options (DENY), CSP (default-src 'self'), Referrer-Policy, Permissions-Policy (camera/microphone/geolocation/payment disabled)

### 3.10 Human-in-the-Loop Approval

**5 approval workflows:** Credit decisions, sensitive financial actions, low-confidence escalation, CFO report review, Chama majority governance. All requests verified against JWT claims for ownership.

---

## 4. Code Quality

### 4.1 Build & Lint Configuration

- **Clippy:** `-D warnings` in CI — zero tolerance for warnings
- **Rustfmt:** Checked in CI
- **`#![deny(missing_docs)]`** in lib.rs — documentation enforced
- **Release profile:** `opt-level=3, lto="fat", codegen-units=1, strip=true, panic="abort"` — maximum optimization

### 4.2 Test Coverage

- **Tarpaulin config:** LLVM engine, 60% threshold, excludes tests/main/migrate
- **Test files:**
  - `tests/unit/` — circuit_breaker, credit_scoring, k_anonymity, message_bus, sync_verification
  - `tests/integration/` — orchestrator_test
  - `tests/load/` — api_load_test, concurrent_streams
  - Inline `#[cfg(test)]` modules in most source files
- **Known gap:** No integration tests with actual database (tests use mocks)

### 4.3 Dependency Audit (deny.toml)

- **License allowlist:** MIT, Apache-2.0, BSD-2/3-Clause, ISC, Unicode, Zlib, 0BSD, OpenSSL
- **Advisories:** warn on unmaintained/yanked, no current ignores
- **Bans:** warn on multiple versions, deny wildcards
- **Sources:** deny unknown registries/git, crates.io only

### 4.4 Code Debt Indicators

1. **501 stubs:** 7 endpoints return "Coming Soon" (economic_indicators, distribution_gaps, fmcg_reports, reports, superagent status/cycle/invoke)
2. **Dual migration system:** Inline SQL in main.rs + formal migration files — risk of schema drift
3. **`main_council.rs`:** Extra binary present, unclear purpose
4. **ClickHouse:** URL loaded from env but no schema/migrations visible — integration appears incomplete
5. **Python sidecar:** LLM inference environment included but integration path unclear (no Rust→Python bridge visible in main.rs)

---

## 5. Integration Points

### 5.1 Android App Communication

The Android app (Msaidizi) communicates via **bidirectional sync protocol:**

**Endpoint:** `POST /api/v1/sync/anonymized`

**Request flow:**
1. Device sends `SyncRequest` containing:
   - `device_id`, `business_category`, `ward`
   - Anonymized transactions (amount buckets, categories, payment methods — NO raw amounts)
   - Learned patterns with confidence scores
   - Anomaly statistics
   - Protocol version & model version
2. Server processes:
   - Protocol version compatibility check (rejects outdated apps)
   - Boundary verification (data validation at sync edge)
   - Deduplication (1000-key sliding window per device)
   - Alama Score computation (300-850 range)
   - Model delta preparation (if device model is outdated)
   - Market intelligence injection (ward-specific price trends)
   - Alert delivery (pending alerts per device)
3. Response includes:
   - Sync status (ok/partial/error)
   - Alama Score update with factor breakdown
   - Model delta for on-device update
   - Market intelligence
   - Freshness metadata
   - Verification results (accepted/rejected/duplicate counts)

**Privacy design:** All transactions are anonymized at the device boundary — no raw transaction data reaches the server. Only amount buckets, categories, and temporal features are transmitted.

### 5.2 SyncReceiver

**Implementation:** `sync/receiver.rs` — ~300 lines

- **State management:** Per-device `DeviceState` tracking (dedup keys, model version, last score, sync counts)
- **Verification:** `SyncVerifier` validates incoming data at the boundary
- **Version compatibility:** `VersionCompatibilityChecker` handles model versioning
- **Freshness:** `FreshnessChecker` tracks staleness of server data

### 5.3 API Versioning

- **Current strategy:** URL path prefix `/api/v1/`
- **Protocol versioning:** `sync_protocol_version` field in sync requests, `MIN_SUPPORTED_PROTOCOL_VERSION` constant
- **No explicit API version negotiation** beyond v1 prefix

### 5.4 M-Pesa Integration

**Full STK Push implementation** in `billing/mpesa.rs` and `webhook/mpesa.rs`:
- Initiates payments via Safaricom M-Pesa API
- Receives callback webhooks (HMAC signature validation)
- Payment status tracking in PostgreSQL

### 5.5 GraphQL

**Full knowledge graph API** via `async-graphql`:
- Node/edge queries with filters
- Graph algorithms (PageRank, community detection, shortest path, degree centrality)
- Subgraph extraction
- Protected by JWT auth layer

---

## 6. Recommendations

### 6.1 Critical (P0) — Blockers & Risks

| # | Issue | Risk | Recommendation |
|---|---|---|---|
| 1 | **No integration test environment** | Unit tests pass but real DB/Redis interactions are untested | Add `docker-compose.test.yml` with test containers, add integration tests to CI |
| 2 | **Dual migration system** | Schema drift between inline SQL in main.rs and migration files | Consolidate all DDL into migration files, remove inline migrations from main.rs |
| 3 | **FedProx default has no DP** | `credit_default()` sets noise_multiplier=0, only logs warning | Make `credit_private()` the default or add compile-time feature gate |
| 4 | **ClickHouse integration incomplete** | URL configured but no schema/migrations, unclear usage | Either implement ClickHouse analytics pipeline or remove the dependency |

### 6.2 High (P1) — Important Improvements

| # | Issue | Recommendation |
|---|---|---|
| 5 | **7 stub endpoints (501)** | Implement or remove stubs — dead routes confuse API consumers |
| 6 | **Python sidecar integration unclear** | Document the Rust→Python bridge for LLM inference, add health checks |
| 7 | **WebSocket endpoints unused** | WS feature enabled in Axum but no endpoints — either implement real-time streaming or remove |
| 8 | **`main_council.rs` orphan binary** | Remove or document — unclear purpose, adds build time |
| 9 | **No API rate limit documentation** | Document tier limits, add rate limit headers to all responses |
| 10 | **Missing database connection pooling config** | sqlx PgPool uses defaults — tune max_connections, min_connections, acquire_timeout for production |

### 6.3 Medium (P2) — Quality of Life

| # | Issue | Recommendation |
|---|---|---|
| 11 | **Coverage threshold at 60%** | Gradually increase to 75%+ as codebase stabilizes |
| 12 | **No OpenAPI/Swagger spec** | Add `utoipa` or similar for auto-generated API documentation |
| 13 | **Monitoring dashboards are provisioned but untested** | Add Grafana dashboard smoke tests to CI |
| 14 | **`cargo-deny` has empty skip lists** | Review if any transitive dependency conflicts need explicit handling |
| 15 | **No load testing in CI** | Add k6 or similar load test to staging workflow |

### 6.4 Performance Considerations

- **Release profile is aggressive:** `lto="fat", codegen-units=1, strip=true` — excellent for production binary size and performance, but increases build time significantly
- **Cache warming on startup:** Graph stats pre-populated in Redis — good cold-start mitigation
- **Audit buffer batching:** Adaptive flush (event-driven + 60s timer) with `MissedTickBehavior::Delay` — prevents flush storms
- **Connection pooling:** Redis uses `ConnectionManager` (single connection) — consider `redis::cluster` for horizontal scaling
- **DashMap usage:** Lock-free concurrent maps for tool registry, rate limiters, k-anonymity tracking — appropriate for high-concurrency workloads

### 6.5 Architecture Strengths

1. **Privacy-first design:** DP + k-anonymity + federated learning + SHAP explainability — comprehensive privacy stack
2. **Graceful degradation:** Circuit breakers, drift detection, human-in-the-loop escalation
3. **Full billing engine:** M-Pesa integration, subscription lifecycle, invoice PDF generation — production-ready monetization
4. **Multi-deployment support:** Oracle, Azure, staging, production with proper IaC
5. **Observability:** OpenTelemetry OTLP, structured JSON logging, correlation IDs, Prometheus metrics, Grafana dashboards
6. **17 sector-specific feature extractors:** Deep domain coverage for East African informal economy

---

## Summary

The Angavu Intelligence Backend is a **well-architected, production-grade Rust platform** with strong privacy guarantees and deep domain modeling of East African informal economies. The codebase is ~61K lines across 183 files with comprehensive security, observability, and billing infrastructure.

**Key strengths:** Privacy stack (DP + k-anonymity + FL + SHAP), full M-Pesa billing, 26 LLM-callable tools, 16-domain orchestrator, and multi-cloud deployment.

**Key risks:** Schema drift from dual migrations, incomplete ClickHouse integration, 7 stub endpoints, and no integration test coverage against real databases.

**Overall assessment:** Ready for staging deployment with the P0 fixes above. Production-ready after addressing integration testing and schema consolidation.
