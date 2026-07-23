# Architecture Improvements Summary
## Enterprise Architecture Council — 6 Recommended Improvements

**Date:** 2026-07-24
**Status:** Implemented — All 6 improvements applied to architecture documents
**Documents Modified:** `arch_android.md`, `arch_backend.md`, `arch_chief.md`, `synthesize_all.md`

---

## Improvement 1: Reflexion as Optional Phase for High-Stakes Decisions

**Files:** `arch_android.md`

**What changed:**
- ReflexionLoop.kt is NO LONGER a standalone class — deleted from file list
- Integrated as `reflectOnDecision()` method in SuperAgent.kt
- Added to cognitive loop diagram as optional phase between REASON and ACT (marked with *)
- Added `shouldReflect()` method that determines when self-critique activates

**Activation criteria (not all requests — only high-stakes):**
- Financial transactions ≥ KSh 5,000
- Loan commitments (always)
- Multi-step planned intents (have a plan)
- High-value inventory changes

**Behavior:**
- Uses LLM to evaluate the decision: "Is this action safe and reasonable?"
- If critique returns CONCERN → inject caution disclaimer + force confirmation
- If critique returns SAFE → proceed normally
- Failure of reflexion is non-blocking (logs warning, proceeds with original decision)

**Impact on file counts:**
- PlanExecuteLoop.kt: DELETED (was in delete list → now explicitly noted as absorbed into `planSteps()`)
- ReflexionLoop.kt: DELETED (was in delete list → now explicitly noted as absorbed into `reflectOnDecision()`)

---

## Improvement 2: Lightweight Planning for Multi-Step Intents

**Files:** `arch_android.md`

**What changed:**
- PlanExecuteLoop.kt is NO LONGER a standalone class — deleted from file list
- Integrated as `planSteps()` method in SuperAgent.kt
- Added `isMultiStepIntent()` detection method
- Added `PlannedStep` data class for ordered tool calls with dependencies
- Planning only runs in the REASON phase when multi-step patterns detected

**Multi-step detection patterns:**
- "Compare my sales this week to last week and suggest pricing changes"
- "Check my stock, record any missing items, and set a reorder goal"
- "Show my profit and tell me if I should increase prices"
- Patterns: "compare...and suggest", "check...and record", "first...then", "analyze...and recommend"

**Behavior:**
- Breaks complex request into 2-4 ordered steps
- Each step is a tool call with dependencies (e.g., step 3 depends on steps 1+2)
- Uses LLM for plan generation, falls back to single-step on failure
- Plan stored in intent data for reflexion phase awareness

**Impact:**
- PlannedStep data class: NEW (added to supporting types)
- `planSteps()` method: NEW (integrated into REASON phase)
- `isMultiStepIntent()` method: NEW (pattern detection)

---

## Improvement 3: Per-Phase Metrics to Cognitive Loop

**Files:** `arch_android.md`, `arch_backend.md`

**Android side:**
- Added `PhaseMetrics` class with:
  - `recordPhase(phase, latencyMs, success)` — called by each cognitive loop phase
  - `exportPrometheus()` — exports metrics in Prometheus text format
  - `summary()` — returns per-phase stats (avg latency, p95, success rate)
- Each phase in `processInput()` now wrapped with timing:
  - perceive, remember, reason, reflect, act, learn
- Metrics included in AgentResponse data map
- `exportPrometheusMetrics()` added to SuperAgent public API

**Backend side:**
- `arch_backend.md` already had section 3.7 with detailed metrics
- Added section 3.6.1 for receiving device-side metrics
- Added `POST /api/v1/sync/metrics` endpoint to receive Android phase metrics
- Prometheus histograms: `msaidizi_device_phase_latency_ms{phase=...}`
- Prometheus gauges: `msaidizi_device_phase_success_rate{phase=...}`
- Prometheus counters: `msaidizi_device_phase_errors_total{phase=...}`
- Alerting rules for all phases (high latency, low success rate)

**Metrics exported per phase:**
| Phase | Latency | Success Rate | Errors |
|-------|---------|-------------|--------|
| perceive | ✅ | ✅ | ✅ |
| remember | ✅ | ✅ | ✅ |
| reason | ✅ | ✅ | ✅ |
| reflect | ✅ | ✅ | ✅ |
| act | ✅ | ✅ | ✅ |
| learn | ✅ | ✅ | ✅ |

---

## Improvement 4: Sync Conflict Resolution (Vector Clocks, Not Last-Write-Wins)

**Files:** `arch_android.md`, `arch_backend.md`

**What changed:**
- Replaced "last-write-wins with merge" with vector clocks for conflict detection
- Added `VectorClock` data class with `increment()`, `merge()`, `compare()` methods
- Added `ClockComparison` enum: BEFORE, AFTER, CONCURRENT, EQUAL
- Added `ConflictResolver` class with per-data-type resolution strategies

**Per-data-type resolution strategy:**
| Data Type | Strategy | Rationale |
|-----------|----------|-----------|
| Transactions | Merge (additive) | Both are real-world events. Keep both. |
| Inventory | Latest timestamp wins | Physical reality: only one count is correct. |
| Preferences | Merge (union) | Combine settings. Latest wins on key conflicts. |
| Skills | Merge (union + confidence) | Average confidence for overlapping skills. |

**Escalation triggers (notified to worker):**
- Inventory delta > 20% of expected stock
- Contradictory goal/loan states (e.g., device: paid, backend: active)
- Tombstone conflicts (both sides deleted same entity)

**Backend:** `arch_backend.md` already had detailed vector clock implementation in section 2.6. Android document now mirrors the same approach.

**Sync protocol updated:**
- Device includes vector clock with each sync entry
- Backend compares clocks to detect CONCURRENT (conflict)
- Auto-resolves most conflicts per data type
- Escalates ambiguous conflicts to worker

---

## Improvement 5: Buyer Dashboard for Revenue

**Files:** `arch_backend.md` (new section 3.8)

**New API endpoints:**
| Endpoint | Product | Pricing | Target Buyer |
|----------|---------|---------|--------------|
| `GET /api/v1/buyer/soko-pulse` | FMCG Demand Forecasting | $0.10-$1.00/query | FMCG companies |
| `GET /api/v1/buyer/alama-score` | Credit Scoring | $0.05-$0.50/score | Banks, fintechs |
| `GET /api/v1/buyer/angavu-pulse` | MSME Activity Index | $500-$5,000/month | Government |
| `GET /api/v1/buyer/jamii-insights` | Financial Inclusion | $100-$1,000/report | NGOs |
| `GET /api/v1/buyer/report/{type}` | Formatted Reports | Included in tier | All buyers |

**Authentication:**
- Separate buyer auth (not worker auth)
- API key via `X-API-Key` header
- JWT for session management
- `BuyerAccount` model with company_name, tier, budget, usage tracking

**Rate limiting:**
- Starter: 100 queries/day, $0.10/query
- Professional: 1,000 queries/day, $0.05/query
- Enterprise: 10,000 queries/day, $0.02/query
- Redis sliding window implementation

**Report generation:**
- PDF and HTML formats
- Available for all intelligence products
- On-demand generation from pre-computed data

---

## Improvement 6: Scaling Playbook (Decision Tree)

**Files:** `arch_backend.md` (section 7 — already existed, verified complete)

**Scaling thresholds:**
| Workers | Key Action | Monthly Cost |
|---------|-----------|-------------|
| <1K | Default Oracle Free Tier | $0 |
| 1K | Add PgBouncer + Redis caching | $0 |
| 2K | Upgrade Oracle instance (4 OCPU) | ~$50 |
| 5K | PG read replicas + ClickHouse partitioning | ~$100 |
| 10K | 2+ read replicas, ClickHouse MViews, Redis Cluster | ~$150-300 |
| 25K | 8 OCPUs | ~$150 |
| 50K | Kafka + separate processes | ~$560 |
| 100K | Microservices + K8s + ClickHouse cluster | ~$1,600 |
| 250K | PG sharding by region | ~$1,600 |
| 1M | Hash-based PG sharding, self-hosted LLM, multi-region | ~$1,600 |
| 10M | Managed everything, CQRS, event sourcing | ~$11,500 |

**Decision tree:**
```
< 1K → Default stack (Oracle Free Tier)
1K-10K → Optimize (PgBouncer, caching, read replicas)
10K-100K → Scale (Kafka, microservices, K8s)
100K-1M → Shard (PG sharding, multi-region, dedicated FL)
10M+ → Re-architecture (managed everything, CQRS, TiDB)
```

**Anti-patterns documented:**
1. Don't scale before you need to
2. Don't add microservices at 1K workers
3. Don't shard PostgreSQL before 1M workers
4. Don't go multi-region before 100K workers
5. Don't self-manage databases at 100K+ workers

---

## Cross-Document Consistency

All improvements are consistent across documents:

| Improvement | arch_android.md | arch_backend.md | arch_chief.md | synthesize_all.md |
|-------------|----------------|-----------------|---------------|-------------------|
| 1. Reflexion optional | ✅ Method in SuperAgent | — | ✅ Updated refs | ✅ Documented |
| 2. Planning | ✅ Method in SuperAgent | — | ✅ Updated refs | ✅ Documented |
| 3. Per-phase metrics | ✅ PhaseMetrics class | ✅ Prometheus endpoint | — | ✅ Documented |
| 4. Vector clocks | ✅ VectorClock + ConflictResolver | ✅ Section 2.6 (existing) | ✅ Updated refs | ✅ Documented |
| 5. Buyer dashboard | — | ✅ Section 3.8 (new) | — | ✅ Documented |
| 6. Scaling playbook | — | ✅ Section 7 (existing) | — | ✅ Documented |

---

## New Files/Classes Added

### Android (arch_android.md)
- `PlannedStep` data class — multi-step plan representation
- `PhaseMetrics` class — per-phase Prometheus metrics
- `PhaseStats` data class — phase statistics summary
- `VectorClock` data class — causality tracking
- `ClockComparison` enum — clock comparison result
- `ConflictResolver` class — per-data-type conflict resolution
- `DataType` enum — TRANSACTION, INVENTORY, PREFERENCES, SKILLS

### Backend (arch_backend.md)
- Section 3.8: Buyer Dashboard API (buyer.py, buyer_auth.py, buyer_rate_limiter.py)
- `BuyerAccount` model — buyer database model
- Buyer tiers: starter, professional, enterprise

---

## Files NOT Changed (Already Complete)

- `arch_backend.md` §2.6: Vector clocks already implemented in detail
- `arch_backend.md` §3.7: Per-phase metrics already implemented in detail
- `arch_backend.md` §7: Scaling playbook already implemented in detail (7.1-7.8)

---

*Improvements implemented: 2026-07-24*
*Lead Architecture Improvement Engineer*
