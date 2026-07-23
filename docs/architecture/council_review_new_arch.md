# ANGAVU INTELLIGENCE — ENTERPRISE ARCHITECTURE COUNCIL REVIEW
## New Super Agent Architecture Design Review

**Date:** 2026-07-24  
**Reviewers:** 6-Member Enterprise Architecture Council  
**Scope:** NEW architecture design ONLY (existing code is out of scope — it will be deleted)  
**Documents Reviewed:** 8 architecture blueprints (~500KB total)

---

## COUNCIL MEMBER 1: Enterprise Architecture Reviewer

### Question: Is the SuperAgent pattern enterprise-grade?

**Assessment:**

The architecture proposes a **single cognitive loop agent** with a **tool registry** and **three-layer memory** — collapsing 33+ agents into 1 SuperAgent on Android and 0 agents (pure services) on the backend. This is evaluated against enterprise architecture principles.

**Strengths:**
- **Single responsibility at the right level.** The SuperAgent is a cognitive loop coordinator, not a god class. Business logic lives in 22 self-contained tools. This is the correct decomposition — enterprise systems separate *orchestration* from *capability*.
- **Clean dependency graph.** 10 constructor dependencies (down from 40+) with Hilt DI. This is manageable, testable, and doesn't create circular dependency risks.
- **Service-first backend.** Eliminating all 33+ backend agents in favor of direct service calls (`SokoPulseService`, `AlamaScoreService`) is architecturally sound. Agents are indirection layers; services are business logic. Enterprise backends should be service-oriented, not agent-oriented.
- **Clear separation of concerns.** Android = intelligence + interaction. Backend = aggregation + intelligence products + sync. Neither tries to be the other.
- **Event-driven backend.** Redis Streams for async work, task queues for background processing. This is standard enterprise architecture.

**Concerns:**
- **Single point of failure on Android.** If `SuperAgent.kt` has a bug, the entire agent is down. With 33 separate agents, a bug in one domain doesn't affect others. Mitigation: the cognitive loop phases are modular functions, and the tool registry isolates failures per-tool. But this needs rigorous testing.
- **No API versioning strategy.** The sync protocol (`SyncPayload`/`SyncResponse`) needs versioning from Day 1. Devices in the field may run old APK versions while the backend evolves.
- **No circuit breaker on the cognitive loop.** If L2 (EpisodicMemory) search takes 500ms instead of 10ms, the entire interaction is blocked. The architecture mentions `InferenceHarness` with circuit breakers but doesn't wire it into the SuperAgent's memory bridge.

**What's Missing:**
- **API contract specification.** No OpenAPI/Swagger spec for the sync protocol, intelligence API, or FL endpoints. Enterprise systems need interface contracts.
- **Deployment topology.** Single Oracle Free Tier instance is fine for MVP, but the architecture doesn't describe what happens when you need 2+ backend instances (session affinity, shared state, etc.).
- **Observability strategy.** Prometheus + Grafana is mentioned but not wired into the SuperAgent cognitive loop. Each phase (PERCEIVE, REMEMBER, REASON, ACT) should emit metrics.
- **Disaster recovery.** No backup strategy for PostgreSQL. No failover for Redis. What happens when the Oracle instance goes down?

**Scalability from 100 to 10M workers:**
- At 100 workers: Oracle Free Tier is sufficient. No concerns.
- At 10K workers: PostgreSQL will need connection pooling (PgBouncer). ClickHouse will need proper partitioning. The weekly flywheel cycle will need to process 10K×100 episodes = 1M episodes.
- At 1M workers: The single-backend architecture breaks. Need horizontal scaling, database sharding, and a proper message queue (Kafka, not Redis Streams).
- At 10M workers: Need a fundamentally different architecture (microservices, Kubernetes, managed databases). But this is a 3-5 year horizon.

### Verdict: ✅ APPROVE (with conditions)

The architecture is enterprise-grade for the current scale (0–10K workers) and has a clear evolution path. The SuperAgent pattern is sound — it's essentially a **service-oriented architecture with a cognitive loop facade** on the client side. The conditions are:

1. Add API versioning to the sync protocol
2. Wire circuit breakers into the memory bridge
3. Add per-phase metrics to the cognitive loop
4. Document the scaling path beyond Oracle Free Tier

---

## COUNCIL MEMBER 2: Super Agent Design Reviewer

### Question: Does this match Jensen Huang's super agent vision?

**Assessment:**

Jensen's vision: *"One unified intelligence. Harness (tools + memory + guardrails). Post-trained in the harness. Explore larger spaces at zero marginal cost."*

**Mapping to architecture:**

| Jensen's Principle | Architecture Implementation | Match? |
|---|---|---|
| ONE intelligence, not multi-agent | `SuperAgent.kt` — single class, cognitive loop | ✅ Perfect |
| Harness = tools + memory + guardrails | `ToolRegistry` + `UnifiedMemoryBridge` + `SafetyChecker` | ✅ Perfect |
| Post-trained in the harness | On-device LoRA fine-tuning from worker corrections | ✅ Perfect |
| Explore larger spaces at $0 marginal cost | On-device inference (Qwen 0.8B) = $0 per interaction | ✅ Perfect |
| Cognitive loop | INPUT→PERCEIVE→REMEMBER→REASON→ACT→LEARN→OUTPUT | ✅ Perfect |

**This is the closest implementation of Jensen's vision I've seen in any production architecture.** The cognitive loop is not just a label — it's a single `suspend fun processInput()` that flows through all 7 phases with clear data flow between them.

**Strengths:**
- **The 90/10 split is brilliant.** 90% of interactions handled by regex (IntentRouter) with 0ms latency and 0MB RAM. 10% escalated to Qwen 0.8B. This is exactly how you make a 0.8B model deliver "frontier-like" experience — you don't use it for everything.
- **Tool interface is clean.** `Tool.execute(args, language) → ToolResult` is simple, testable, and extensible. New capabilities = new tools, not new agents.
- **Memory bridge is the key innovation.** The `UnifiedMemoryBridge` that enriches context before every interaction (L2 episodes + L3 skills + L3 profile) and updates all layers after every interaction — this is what makes the agent *learn*, not just *respond*.
- **Dual flywheel is correctly designed.** Device flywheel (real-time, offline) + Cloud flywheel (weekly aggregation, model distribution). The connection point (sync protocol) is well-defined.

**Concerns:**
- **ReflexionLoop removal is risky.** The architecture deletes `ReflexionLoop.kt` and absorbs "inline critique" into the SuperAgent. But Reflexion is a distinct cognitive pattern (self-evaluate → identify failure → retry). Inlining it may lose the self-correction capability. Recommendation: keep ReflexionLoop as an optional phase in the cognitive loop for high-stakes decisions.
- **No explicit planning phase.** The cognitive loop goes REASON→ACT directly. For multi-step tasks (e.g., "Compare my sales this week to last week and suggest pricing changes"), the agent needs planning. `PlanExecuteLoop.kt` is being deleted. Recommendation: add a lightweight planning phase between REASON and ACT for complex intents.
- **SafetyChecker is too simple.** The inline `SafetyChecker` checks for 3 blocked patterns and injects financial disclaimers. The constitutional principles in the security architecture (12 principles, runtime enforcement) are far more sophisticated. These need to be integrated, not replaced.
- **The backend being "not the brain" is correct but incomplete.** The backend should still have *some* reasoning capability for collective intelligence — not just data pipelines. When a buyer asks "What's the demand forecast for tomatoes in Nairobi next month?", the backend needs to reason over aggregated data, not just return a pre-computed table.

**Does the dual flywheel work?**
Yes, with caveats. The device flywheel is well-designed (corrections → vocabulary → LoRA → better responses). The cloud flywheel is well-designed (aggregation → global model → all devices). But the **intelligence product feedback loop** (Soko Pulse outcomes → training signals) is acknowledged as missing and only has a design sketch. This is the critical gap — without it, the cloud flywheel only improves ASR/LLM, not the intelligence products themselves.

### Verdict: ✅ APPROVE

This IS a real super agent. It matches Jensen's vision more closely than any multi-agent system would. The cognitive loop, tool registry, memory bridge, and dual flywheel form a coherent super agent architecture. The concerns (Reflexion, planning, safety sophistication) are refinements, not fundamental flaws.

---

## COUNCIL MEMBER 3: Tech Stack Reviewer

### Question: Is the tech stack right?

**Assessment:**

| Layer | Stack | Enterprise Fit | Super Agent Fit |
|---|---|---|---|
| Android | Kotlin 2.0.21 + Hilt + Room + llama.cpp | ✅ Industry standard | ✅ Native performance for 2GB devices |
| Backend | Python 3.12 + FastAPI | ✅ Enterprise-ready | ✅ Async, type-safe, fast |
| Database | PostgreSQL + Redis + ClickHouse | ✅ Enterprise-grade | ✅ OLTP + cache + analytics |
| ML | Sherpa-ONNX + llama.cpp + Flower | ✅ Open-source, production-proven | ✅ On-device + federated |
| Infrastructure | Oracle Cloud Free Tier | ⚠️ Free tier limitations | ✅ Sufficient for MVP |

**Strengths:**
- **Kotlin + Hilt is the right choice for Android.** Type safety, null safety, coroutine support, and Hilt's compile-time DI verification prevent the constructor hell that plagued the old architecture.
- **Python + FastAPI is the right choice for backend.** The intelligence products (Soko Pulse, Alama Score) use numpy/scipy/statsmodels — Python is the only practical choice. FastAPI's async support handles concurrent sync requests well.
- **PostgreSQL + ClickHouse is the right dual-database strategy.** PostgreSQL for transactional data (users, transactions, FL models). ClickHouse for analytical data (market trends, aggregated patterns). This is standard in data-intensive companies.
- **SQLite FTS5 for on-device memory is brilliant.** Zero dependencies, sub-10ms search, works offline, excellent Unicode support for Swahili. This is better than any vector database for the use case.
- **Sherpa-ONNX is the right voice engine.** Unified API for VAD + ASR + TTS. Optimized ARM NEON paths. Active maintenance by k2-fsa team. Better than integrating raw ONNX Runtime.

**Concerns:**
- **Oracle Free Tier has no SLA.** The "Always Free" tier can be throttled or degraded without notice. For a production system serving real workers, this is risky. Recommendation: have a migration plan to a paid instance (even $50/month on Oracle/AWS/GCP) when revenue starts.
- **No message broker.** Redis Streams is used for async work, but it's not a proper message broker. At scale, you'll need Kafka or RabbitMQ. Redis Streams works for MVP but doesn't provide durability guarantees or consumer group rebalancing.
- **Flower for FL may be overkill.** Flower is a full FL framework with client/server abstractions. The actual FL logic is simple FedAvg with DP noise. A custom implementation (which already exists in `federated_learning.py`) may be simpler and more controllable.
- **ClickHouse on 1GB RAM is tight.** ClickHouse recommends 2GB+ for production. On 1GB, it will work for small datasets but may OOM under analytical query loads. Monitor memory usage carefully.

**Does the stack support super agent features?**
- FL: ✅ Flower + existing FedAvg implementation
- Voice: ✅ Sherpa-ONNX with Whisper + Piper + Kokoro
- Memory: ✅ SQLite FTS5 + PostgreSQL + Redis
- Tools: ✅ Kotlin interface + Hilt DI
- Learning: ✅ llama.cpp + LoRA training on-device

**$0 constraint: empowering or limiting?**
**Empowering.** The $0 constraint forces good engineering decisions:
- On-device inference (no cloud costs, works offline)
- SQLite FTS5 (no vector DB costs)
- Regex-first intent classification (no LLM costs for 90%)
- Open-source everything (no licensing)
- Oracle Free Tier (no infrastructure costs)

The constraint is only limiting for the backend's analytical capabilities — ClickHouse on 1GB RAM and no LLM on the server side. But the architecture correctly pushes intelligence to the device, making the backend a data aggregator rather than a reasoning engine.

### Verdict: ✅ APPROVE

The tech stack is well-chosen, enterprise-grade, and purpose-built for the constraints ($50 phones, $0 budget, offline-first, voice-only). The only real risk is Oracle Free Tier reliability — have a paid migration plan ready.

---

## COUNCIL MEMBER 4: Scalability Reviewer

### Question: Does it scale from $0 to enterprise?

**Current Capacity (Oracle Free Tier):**
- 2 ARM OCPUs, 12GB RAM, 200GB storage
- Architecture uses 4.3GB RAM, 2.0 OCPUs — 7.7GB headroom

**Scaling Analysis by Worker Count:**

#### 100 Workers (MVP)
- Backend: Oracle Free Tier is more than sufficient
- Database: PostgreSQL handles 100 workers × 10 transactions/day = 1K transactions/day easily
- FL: 100 workers × weekly sync = ~15 syncs/day. Trivial.
- **Bottleneck: None.** This is well within capacity.

#### 1,000 Workers (Early Growth)
- Backend: Oracle Free Tier still sufficient
- Database: 10K transactions/day, 1K weekly FL syncs
- ClickHouse: 1K workers × 1 year × 365 days × 10 txns = 3.65M rows. Fine.
- FL aggregation: 1K workers, min 5 per round = 200 rounds/week. Manageable.
- **Bottleneck: FL aggregation time.** Processing 1K LoRA deltas (~1MB each) = 1GB per cycle. Needs optimization (streaming aggregation).
- **Action needed:** Add connection pooling (PgBouncer), optimize FL aggregation.

#### 10,000 Workers (Growth Stage)
- Backend: Need to upgrade from Free Tier. 2 OCPUs won't handle 100K transactions/day + FL + intelligence products.
- Database: PostgreSQL needs read replicas. ClickHouse needs more RAM (2GB+).
- FL: 10K workers × 1MB deltas = 10GB per cycle. Need streaming aggregation + compression.
- Sync: 10K daily syncs × 10KB payload = 100MB/day. Manageable.
- **Bottleneck: Backend compute.** Intelligence product generation (Soko Pulse for 100+ regions) + FL aggregation + sync handling exceeds 2 OCPUs.
- **Action needed:** Upgrade to paid instance (4-8 OCPUs, 16-32GB RAM). Add PgBouncer. Partition ClickHouse tables.

#### 100,000 Workers (Scale Stage)
- Backend: Need horizontal scaling. Single instance won't work.
- Database: PostgreSQL needs sharding (by region or worker_id). ClickHouse needs a cluster.
- FL: 100K workers = massive aggregation. Need MapReduce-style FL or hierarchical aggregation.
- Sync: 100K daily syncs. Need a proper message queue (Kafka).
- **Bottleneck: Everything.** The monolithic FastAPI app needs to be decomposed into services.
- **Action needed:** Microservices architecture. Kubernetes. Managed databases. Kafka.

#### 10,000,000 Workers (Enterprise)
- Need: Multi-region deployment, database sharding, CDN for model distribution, dedicated FL cluster
- **This is a fundamentally different architecture.** The current design doesn't pretend to handle this, which is honest and correct.

**Is the modular monolith approach correct?**
**Yes, for the current phase.** The backend is a modular monolith — one FastAPI app with clear module boundaries (sync, intelligence, FL, governance). This is the right approach for 0–10K workers. The modules can be extracted into microservices when needed.

The key architectural decision that enables scaling: **intelligence is pre-computed, not on-demand.** Soko Pulse runs daily at 2 AM, not when a buyer requests it. This means the backend's compute needs are predictable and batch-friendly, not spiky.

**What breaks first?**
1. **PostgreSQL connection limits** at ~1K concurrent syncs (default max_connections=100). Fix: PgBouncer.
2. **FL aggregation time** at ~5K workers per dialect. Fix: streaming aggregation.
3. **ClickHouse memory** at ~10M rows of analytical data. Fix: more RAM or partitioning.
4. **Backend CPU** at ~10K daily syncs + intelligence generation. Fix: upgrade instance.

### Verdict: ✅ APPROVE

The architecture scales from $0 to ~10K workers on the current design. Beyond that, it needs horizontal scaling — but the modular monolith approach ensures the transition is service extraction, not rewriting. The scaling path is clear and incremental.

---

## COUNCIL MEMBER 5: Business Model Reviewer

### Question: Does the architecture enable the business?

**Business Model:**
- Free app for workers (B2C, zero cost)
- B2B intelligence products (Soko Pulse, Alama Score, Angavu Pulse, Jamii Insights)
- Revenue from FMCG companies, banks, government, NGOs

**Architecture Support for Business Model:**

| Business Need | Architecture Support | Status |
|---|---|---|
| Free app (zero cost to workers) | On-device inference = $0 marginal cost | ✅ Perfect |
| Soko Pulse (FMCG demand forecasting) | Pre-computed daily, served from PostgreSQL | ✅ Good |
| Alama Score (credit scoring) | Event-driven, computed on new transaction batch | ✅ Good |
| Angavu Pulse (government MSME index) | Weekly pre-computation | ✅ Good |
| Jamii Insights (NGO financial inclusion) | Monthly pre-computation | ✅ Good |
| FL model access (research institutions) | Flower-based aggregation, model versioning | ✅ Good |
| API for partners | FastAPI endpoints, JWT auth | ✅ Good |

**Architecture Support for Visibility Stack (7 layers):**

The "visibility stack" transforms raw worker data into policy-level intelligence:

| Layer | Description | Architecture Support |
|---|---|---|
| 1. Raw Data | Worker transactions, voice interactions | SQLite (device) + PostgreSQL (backend) ✅ |
| 2. Cleaned Data | Deduplicated, validated transactions | Sync engine with checksums + dedup ✅ |
| 3. Aggregated Data | Regional/sectoral aggregates | ClickHouse analytical queries ✅ |
| 4. Intelligence Products | Soko Pulse, Alama Score | IntelligenceEngine + pre-computation ✅ |
| 5. Dashboards | Buyer-facing analytics | API endpoints (no dashboard UI yet) ⚠️ |
| 6. Reports | PDF/HTML reports for buyers | Not yet designed ❌ |
| 7. Policy Voice | Government policy recommendations | Not yet designed ❌ |

**Architecture Support for 10 Business Flows:**

| Flow | Architecture Support | Status |
|---|---|---|
| 1. Worker records transaction (voice) | VoicePipeline → IntentRouter → Tool | ✅ |
| 2. Worker gets business advice | LLM escalation or code-based advice | ✅ |
| 3. Worker gets market prices | MarketTool (on-device or backend) | ✅ |
| 4. FL aggregation | Flower-based FL server | ✅ |
| 5. Buyer queries Soko Pulse | REST API, pre-computed results | ✅ |
| 6. Bank queries Alama Score | REST API, event-driven computation | ✅ |
| 7. Government gets Angavu Pulse | REST API, weekly pre-computation | ✅ |
| 8. Worker gets credit recommendation | Alama Score + progressive autonomy | ✅ |
| 9. Cross-worker skill distribution | Skill marketplace (design only) | ⚠️ |
| 10. Dialect expansion via flywheel | Device flywheel + cloud aggregation | ✅ |

**Gaps:**
- **No buyer-facing dashboard.** The architecture has API endpoints but no UI for buyers (FMCG companies, banks). This is needed for revenue generation.
- **No report generation.** Buyers need PDF/HTML reports, not just API responses.
- **No billing/payments integration.** How do buyers pay for intelligence products?
- **No SLA or rate limiting for B2B API.** Enterprise buyers expect SLAs.

### Verdict: ✅ APPROVE

The architecture fully supports the core business model (free app + B2B intelligence). The gaps (dashboard, reports, billing) are business layer concerns, not architecture concerns — they can be built on top of the existing API without architectural changes.

---

## COUNCIL MEMBER 6: Future-Proofing Reviewer

### Question: Is the architecture future-proof?

#### Quantum Computing Readiness

**Assessment:**
- **PQC (Post-Quantum Cryptography): ✅ Already implemented.** ML-KEM-768 + ML-DSA-65 using real liboqs. Hybrid key exchange (X25519 + ML-KEM-768). 4-phase migration plan. This is production-grade PQC — ahead of most enterprise systems.
- **Quantum optimization: ⚠️ Interface designed, not implemented.** The architecture describes a `QuantumOptimizer` interface that can swap classical↔quantum solvers. This is the right approach — design the interface now, implement when quantum advantage is demonstrated.
- **Quantum FL: Not needed.** Federated learning aggregation (FedAvg) is a simple averaging operation. Quantum computing offers no advantage here.

**Honest assessment:** Quantum computing is a 5-10 year horizon for practical advantage in this domain. The architecture correctly focuses on PQC (immediate need) and quantum-ready interfaces (future-proofing).

#### AGI Readiness

**Assessment:**
- **Hybrid model stack: ✅ Well-designed.** On-device (Qwen 0.8B, 80%) + Cloud Tier 1 (DeepSeek V4 Flash, 15%) + Cloud Tier 2 (Claude Haiku 4.5, 5%). This allows the system to leverage frontier models when needed without depending on them.
- **Model-agnostic architecture: ✅ Correct.** The `LlmEngine` facade + `CloudEscalationRouter` allows swapping models without changing application logic. When GPT-5 or Claude Opus 4 becomes available, it's a configuration change, not a rewrite.
- **On-device inference: ✅ Future-proof.** As on-device models improve (Qwen 1B, Phi-3-mini, etc.), the architecture can upgrade without changing the cognitive loop or tool interface.

**Honest assessment:** The architecture is AGI-ready in the sense that it can leverage better models as they become available. It's not dependent on any specific model.

#### 100+ Dialect Readiness

**Assessment:**
- **Dialect learning flywheel: ✅ Excellent design.** Start with 14 known dialects, discover new ones from worker corrections, validate via cloud aggregation, deploy LoRA adapters. Target: 100+ dialects by month 24.
- **MMS-1B foundation: ✅ Strong.** Meta's MMS supports 1,107 ASR languages. The architecture uses Sherpa-ONNX which supports MMS models.
- **LoRA adapter layering: ✅ Scalable.** Base model (frozen) + Domain adapter (shared) + Dialect adapter (shared) + User adapter (personal). Each dialect = ~1MB adapter. 100 dialects = ~100MB total (downloaded on-demand).

**Concerns:**
- **TTS for 100+ dialects is the real challenge.** ASR can learn new dialects via LoRA adapters. TTS requires pre-trained voice models. The architecture's fallback chain (Swahili approximation → MMS → character-level) is pragmatic but may produce poor quality for distant dialects.
- **Dialect validation is under-specified.** How do you validate that a detected "new dialect" is actually a dialect and not just noise? The architecture mentions "20+ words, 50 audio samples" but doesn't specify linguistic validation criteria.

#### Other Future-Proofing Concerns

- **No plugin architecture.** The tool registry is a good start, but there's no mechanism for third-party tools or plugins. If a partner wants to integrate their own tool (e.g., a specific M-Pesa API), they'd need to modify the source code.
- **No multi-tenancy on the backend.** The backend serves all workers from one database. If the company expands to multiple countries, each country may need data sovereignty (data stays in-country). The architecture doesn't address this.
- **No offline sync conflict resolution.** The sync protocol uses "last-write-wins" for conflict resolution. For transaction data, this can cause data loss if two devices modify the same record. The architecture acknowledges this but doesn't solve it.

### Verdict: ✅ APPROVE

The architecture is future-proof in the dimensions that matter: quantum-safe cryptography (already done), model-agnostic AI (facade pattern), and dialect scalability (flywheel + LoRA). The gaps (TTS for 100+ dialects, multi-tenancy, sync conflicts) are solvable within the current architectural patterns.

---

## CONSOLIDATED COUNCIL VERDICT

| Council Member | Verdict | Key Condition |
|---|---|---|
| Enterprise Architecture | ✅ APPROVE | Add API versioning, wire circuit breakers into memory bridge |
| Super Agent Design | ✅ APPROVE | Keep Reflexion for high-stakes decisions, add lightweight planning |
| Tech Stack | ✅ APPROVE | Have Oracle paid-tier migration plan ready |
| Scalability | ✅ APPROVE | Add PgBouncer at 1K workers, plan microservices at 10K |
| Business Model | ✅ APPROVE | Build buyer dashboard and report generation on top of APIs |
| Future-Proofing | ✅ APPROVE | Specify dialect validation criteria, plan multi-tenancy |

### FINAL VERDICT: ✅ UNANIMOUS APPROVE

**The architecture is sound.** It correctly implements Jensen Huang's super agent vision for the specific context of Africa's 600M+ informal workers on $50 phones with $0 infrastructure budget. The cognitive loop, tool registry, unified memory bridge, dual flywheel, and offline-first voice pipeline form a coherent, enterprise-grade architecture.

**This is not a chatbot. This is not a multi-agent system. This is one intelligence, specialized for a world that no one else is building for, designed to get smarter with every interaction.**

### Critical Success Factors (Must-Have for Launch)

1. **UnifiedMemoryBridge must work.** Without L2/L3 context enrichment, the agent is just a fancy intent router. The bridge is the single most important new component.
2. **Voice pipeline must work on 2GB devices.** Mutual exclusion (Whisper ↔ Kokoro), Piper TTS fallback, wake word detection. If voice doesn't work, the app doesn't work.
3. **Sync protocol must be reliable.** Workers will lose data if sync fails silently. Need retry logic, checksums, and conflict resolution.
4. **FL privacy must be airtight.** ε=0.1 differential privacy, k-anonymity (k≥5), gradient clipping. One privacy breach destroys trust with 600M+ potential users.

### Recommended Architectural Improvements (Non-Blocking)

1. **Add Reflexion as optional phase.** For financial transactions and high-stakes decisions, the agent should self-evaluate before acting. Keep `ReflexionLoop.kt` as an optional phase between REASON and ACT.
2. **Add lightweight planning.** For multi-step intents (compare + suggest), add a planning phase. Don't restore `PlanExecuteLoop.kt` — instead, add a `planSteps()` method to the REASON phase.
3. **Add per-phase metrics.** Each cognitive loop phase should emit latency, success rate, and error count to Prometheus. This is critical for debugging production issues.
4. **Specify the sync conflict resolution strategy.** "Last-write-wins" is insufficient for transaction data. Use vector clocks or CRDTs for conflict-free replication.
5. **Design the buyer dashboard.** Revenue depends on buyers being able to consume intelligence products. The API is ready; the UI is not.
6. **Document the scaling playbook.** At what worker count do you add PgBouncer? When do you upgrade Oracle? When do you shard PostgreSQL? Write this down now, before you need it.

---

*Reviewed by the Enterprise Architecture Council — 2026-07-24*
*All 6 members voted APPROVE.*
*Architecture is approved for implementation.*
