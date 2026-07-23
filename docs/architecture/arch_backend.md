# Angavu Intelligence Backend — Rearchitecture Plan

## From 33+ Agents to Unified Intelligence Platform

**Date:** 2026-07-24  
**Constraint:** Oracle Cloud Free Tier (2 ARM OCPUs, 12GB RAM, 200GB storage)  
**Budget:** $0 until revenue  
**Stack:** FastAPI, PostgreSQL, Redis, ClickHouse, Flower  

---

## 1. CURRENT STATE ANALYSIS

### 1.1 Repository Metrics

| Metric | Value |
|---|---|
| Python files | 488 |
| Total lines | 197,496 |
| Agent classes (BiasharaAgent subclasses) | 33+ |
| API route files | 35+ |
| ORM models | 25+ |
| Intelligence services | 20+ |
| Statistical/ML modules | 30+ |

### 1.2 What Exists (Works)

**Core Data Pipeline (✅ Solid)**
- `app/models/user.py` — User model with privacy (phone encrypted, geohash-5)
- `app/models/transaction.py` — Transaction + Inventory models, well-indexed
- `app/api/sync.py` — Device-to-cloud sync with idempotency, checksums, dedup
- `app/services/pipeline.py` — Data processing pipeline
- `app/db/database.py` — Async SQLAlchemy with PostgreSQL/SQLite support
- `app/db/clickhouse.py` — ClickHouse client with schema migration tracking

**Intelligence Products (✅ Core Logic Works)**
- `app/services/intelligence/soko_pulse.py` — FMCG demand forecasting (Holt-Winters, ARIMA, VAR, elasticity, consumer surplus, cross-border trade, 800+ lines)
- `app/services/intelligence/alama_score.py` — Credit scoring with MLE logistic regression, Heckman correction, PCA, factor analysis
- `app/services/federated_learning.py` — FedAvg aggregation with DP, dialect clustering, quality validation
- `app/services/federated_learning_v2.py` — Enhanced FL with k-anonymity, multi-category data
- Intelligence product models: SokoPulseReport, BiasharaPulseReport, AlamaScore, JamiiInsightsReport, TaxBaseEstimation, DistributionGapReport

**Infrastructure (✅ Foundation Exists)**
- `app/infrastructure/redis_streams.py` — Producer/consumer with consumer groups
- `app/infrastructure/task_queue.py` — Priority queue (Redis sorted sets)
- `app/infrastructure/circuit_breaker.py` — Circuit breaker pattern
- `app/infrastructure/metrics.py` — Prometheus metrics
- `app/infrastructure/telemetry.py` — OpenTelemetry integration
- `app/config.py` — Pydantic settings with env vars

**Multi-Channel (✅ Working)**
- `app/channels/` — WhatsApp, Telegram, SMS, USSD, HTTP adapters with failover
- `app/channels/health_monitor.py` — Channel health monitoring
- `app/channels/failover.py` — Automatic channel failover

**Security (✅ Solid)**
- RS256 JWT with key pairs
- Input validation middleware (SQL injection, XSS, path traversal)
- Rate limiting (slowapi + Redis)
- Security headers (HSTS, CSP, X-Frame-Options)

### 1.3 What's Broken / Over-Engineered

**🔴 CRITICAL: Agent Proliferation (33+ agents for 2 OCPUs)**

The `AgentFactory.create_all()` starts ALL agents at boot:
- 4 Core agents (TransactionProcessor, IntelligenceGenerator, ReportGenerator, SelfEvolution)
- 6 Domain agents (Agriculture, Retail, Transport, Digital, Manufacturing, Service)
- 6 Utility agents (DataQuality, AnomalyDetector, Prediction, Communication, Learning, Sync)
- 5 New agents (VoicePipeline, Compliance, Security, Onboarding, SocialHandler)
- 3 Governance agents (Audit, Ethics, Privacy)
- 3 Research agents (MarketResearch, UserInsight, Innovation)
- 1 MetaAgent
- Loop-enhanced agents (4 more)
- Long-horizon orchestration agents
- DeerFlow agents (6 domain + 1 lead)
- Financial agents (templates)
- MCP/A2A protocol agents

**Total: 40+ agents instantiated at startup.** Each has event bus subscriptions, tracer, memory, and harness. On 2 OCPUs, this causes:
- Startup time: 30-60 seconds
- Memory: 2-4GB just for agent infrastructure
- CPU: Agents poll events even when idle

**🔴 CRITICAL: Resource Mismatch**

Current `deploy/oracle/docker-compose.yml` allocates:
- llama.cpp: 8GB (Qwen 2.5 7B Q4_K_M) — **consumes 67% of total RAM**
- PostgreSQL: 2GB
- Redis: 384MB
- App: 1GB
- Nginx: 128MB
- **Total: 11.5GB — exceeds 12GB with OS overhead**

Missing from Oracle deployment:
- ClickHouse (needed for analytics)
- Worker process (background tasks)
- No monitoring (Prometheus/Grafana)

**🟡 DUPLICATE: Federated Learning**

Two FL implementations:
- `app/services/federated_learning.py` — Original (in-memory state, SQLite persistence)
- `app/services/federated_learning_v2.py` — Enhanced (k-anonymity, multi-category)
- `app/api/fl_aggregator.py` — Third path (imports from external `msaidizi-language-pipeline`)

**🟡 DUPLICATE: Agent Implementations**

Same agent types exist in multiple places:
- `app/agents/implementations.py` — Core agents
- `app/agents/implementations_extra.py` — Extra agents (Voice, Compliance, Security, Onboarding, Social)
- `app/agents/loops/core.py` — Loop-enhanced versions of same agents
- `app/autonomous/agents/` — Yet another set (content_creator, invoicing, lead_qualifier, onboarding)
- `app/services/agents/` — Service-level domain agents

**🟡 OVER-ENGINEERED: Post-Quantum Cryptography**

`app/security/pqc/` has 8 files (ML-KEM, ML-DSA, hybrid key exchange, etc.) using `liboqs-python`. This is premature for an MVP targeting $0 revenue. Standard TLS 1.3 + AES-256 is sufficient.

**🟡 OVER-ENGINEERED: Agent Protocols**

- `app/agents/protocols/mcp.py` + `mcp_transport.py` — Model Context Protocol
- `app/agents/protocols/a2a.py` + `a2a_transport.py` — Agent-to-Agent protocol
- `app/mcp/` — Full MCP server/client

These add complexity without clear value for the current scale.

**🟡 MISSING: Unified Background Worker**

`app/worker.py` is minimal — just starts the task queue worker. There's no:
- Scheduled report generation cron
- FL aggregation scheduler
- Intelligence product pre-computation
- Data retention cleanup

---

## 2. SUPER AGENT BACKEND DESIGN

### 2.1 Design Principles

1. **Lazy Initialization** — Agents created on-demand, not at boot
2. **Single Process** — One FastAPI app + one worker process (2 OCPUs)
3. **Service-First** — Services are the real logic; agents are thin wrappers
4. **Event-Driven** — Redis Streams for async work, not in-process event bus
5. **Pre-Computed Intelligence** — Generate products on schedule, not on-request

### 2.2 Architecture: Unified Intelligence Platform

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVICE LAYER                              │
│  Msaidizi App (Android)  ──►  Sync API  ──►  PostgreSQL     │
│  FL Gradients  ──►  FL API  ──►  Aggregation                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  ANGAVU BACKEND (FastAPI)                     │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Sync API │  │ Intel API│  │  FL API  │  │ Buyer API│   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │          │
│  ┌────▼──────────────▼──────────────▼──────────────▼──────┐ │
│  │              SERVICE LAYER (no agents)                  │ │
│  │  TransactionService  ──►  IntelligenceEngine            │ │
│  │  FederatedAggregator ──►  ModelRegistry                 │ │
│  │  ReportScheduler     ──►  DeliveryService               │ │
│  └────────────────────────┬───────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────▼───────────────────────────────┐ │
│  │              DATA LAYER                                  │ │
│  │  PostgreSQL (users, txns, intel products, FL models)    │ │
│  │  Redis (cache, queues, FL round state)                  │ │
│  │  ClickHouse (analytics, time-series, aggregates)        │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               WORKER PROCESS (background)                     │
│  - Report generation (daily/weekly)                          │
│  - FL aggregation (when threshold met)                       │
│  - Intelligence pre-computation                              │
│  - Data retention / cleanup                                  │
│  - ClickHouse ETL                                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               MONITORING (lightweight)                        │
│  Prometheus (metrics) + Grafana (dashboards)                 │
│  — Runs as separate container, scrapes /metrics              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Collective Intelligence for Workers

**How it works:**

1. **Data Ingestion**: Worker records transactions via voice/text/M-Pesa → device syncs to cloud
2. **Intelligence Generation**: Background worker pre-computes intelligence products per region/product
3. **Delivery**: Intelligence pushed to devices via sync/pull endpoint, formatted in worker's language
4. **Feedback Loop**: Worker corrections (via FL) improve models over time

**Key insight**: The "collective intelligence" is NOT a chatbot agent. It's a **data pipeline** that:
- Aggregates anonymized transactions across workers
- Applies statistical methods (time series, elasticity, clustering)
- Generates actionable insights (price forecasts, credit scores, demand patterns)
- Delivers insights back to workers in their language

### 2.4 Federated Learning Aggregation

**Architecture:**

```
Device A ──[gradient Δ]──►┐
Device B ──[gradient Δ]──►┤──► FL Aggregator (server)
Device C ──[gradient Δ]──►┘         │
                                    ▼
                              FedAvg + DP noise
                                    │
                                    ▼
                              Global Model
                                    │
                        ┌───────────┼───────────┐
                        ▼           ▼           ▼
                    Device A    Device B    Device C
                    (pulls)     (pulls)     (pulls)
```

**Implementation (Flower-based):**

Replace the current in-memory `_FLState` with Flower federated learning framework:
- Flower server runs as part of the worker process
- Devices act as Flower clients (via REST API bridge)
- Aggregation uses FedAvg with differential privacy (ε=0.1)
- K-anonymity enforced (min 5 devices per round)
- Results persisted to PostgreSQL

### 2.5 Intelligence Product Generation

**Pre-computed, not on-demand:**

| Product | Schedule | Trigger |
|---|---|---|
| Soko Pulse | Daily 2 AM | Cron |
| Alama Score | On new transaction batch | Event-driven |
| Angavu Pulse | Weekly (Monday 3 AM) | Cron |
| Jamii Insights | Monthly (1st, 4 AM) | Cron |
| Tax Base | Monthly (1st, 5 AM) | Cron |
| Distribution Gap | Weekly (Wednesday 2 AM) | Cron |

**Flow:**
1. Scheduler triggers product generation
2. Service queries PostgreSQL + ClickHouse for data
3. Statistical computation (numpy/scipy, no agent overhead)
4. Result stored in `intelligence_products` table
5. Buyers query via API → served from pre-computed table

### 2.6 Sync from On-Device Agents

**Current sync protocol (keep, improve):**

```
Device ──[POST /api/v1/sync/upload]──► Backend
  ├── Validates JWT
  ├── Verifies worker_id_hash
  ├── Checks batch checksum
  ├── Deduplicates transactions
  ├── Detects vector clock conflicts (see §2.6.1)
  ├── Resolves conflicts per data type (see §2.6.2)
  ├── Stores in PostgreSQL
  └── Returns: {status, conflicts, intelligence_updates_available}

Device ──[GET /api/v1/sync/intelligence/{worker_id}]──► Backend
  └── Returns pre-computed intelligence for worker's region/products

Device ──[GET /api/v1/sync/pull?since_clock=...]──► Backend
  └── Returns server-side changes since device's last known clock
```

**Improvements:**
- Add `GET /api/v1/sync/fl-model/{dialect}` — Device pulls latest FL model
- Add `POST /api/v1/sync/fl-update` — Device pushes FL gradient
- Use Redis for FL round state (not in-memory `_FLState`)
- Add compression (gzip) for large intelligence payloads

#### 2.6.1 Vector Clock Conflict Detection

Every mutable entity in PostgreSQL stores a `vector_clock JSONB` column alongside the data. The backend and each device are distinct nodes in the vector clock.

```sql
-- Example vector_clock column
ALTER TABLE transactions ADD COLUMN vector_clock JSONB NOT NULL DEFAULT '{}';
ALTER TABLE inventory ADD COLUMN vector_clock JSONB NOT NULL DEFAULT '{}';
ALTER TABLE worker_preferences ADD COLUMN vector_clock JSONB NOT NULL DEFAULT '{}';
ALTER TABLE skills ADD COLUMN vector_clock JSONB NOT NULL DEFAULT '{}';

-- Index for clock lookups
CREATE INDEX idx_transactions_vc ON transactions USING GIN (vector_clock);
```

**Vector clock format:**
```json
{
  "device:<device_id_hash>": 7,
  "backend:primary": 3
}
```

**Conflict detection algorithm:**
```python
def is_conflicted(vc_local: dict, vc_remote: dict) -> bool:
    """Two vector clocks are conflicted (concurrent) if neither dominates."""
    all_keys = set(vc_local) | set(vc_remote)
    local_before_remote = True
    remote_before_local = True
    strictly_less = False
    strictly_greater = False

    for key in all_keys:
        a = vc_local.get(key, 0)
        b = vc_remote.get(key, 0)
        if a > b:
            remote_before_local = False
            strictly_greater = True
        if a < b:
            local_before_remote = False
            strictly_less = True

    # Concurrent if neither fully dominates the other
    return not (local_before_remote and strictly_less) and \
           not (remote_before_local and strictly_greater) and \
           vc_local != vc_remote
```

When a sync upload arrives, the backend compares the incoming entity's vector clock against the stored entity's clock:
- **No conflict**: One clock dominates → apply the newer version directly.
- **Conflict detected**: Clocks are concurrent → resolve per data type (§2.6.2).

#### 2.6.2 Conflict Resolution Per Data Type

| Data Type | Strategy | Rationale |
|---|---|---|
| **Transactions** | **Merge (additive)** | Both sides record independent financial events. Both transactions are kept with unique IDs. Summing is semantically correct — no transaction is lost. |
| **Inventory** | **Latest timestamp wins** | Stock is a physical quantity. The most recent observation is closest to ground truth. If delta > 20%, escalate to worker. |
| **Preferences** | **Merge (union)** | Union of non-conflicting settings. Same-key conflicts resolve by latest timestamp. |
| **Skills** | **Merge (union + confidence)** | Union of learned patterns. Same pattern on both sides → keep highest confidence score. |
| **Episodic Memory** | **Merge (union)** | Both sides recorded different episodes. Keep all unique episodes. No data loss. |
| **Goals / Loans** | **Latest timestamp wins** | Stateful objects (active/paid/completed). Latest state reflects reality. Contradictory states escalate. |

**Automatic resolution (no worker notification):**
- Transactions: always merge
- Episodic memory: always merge
- Skills: always merge
- Preferences: merge non-conflicting; same-key → latest timestamp

**Escalated to worker:**
- Inventory delta > 20% of expected stock (physical count mismatch)
- Goal/loan contradictory states (e.g., device: paid, backend: active)
- Tombstone conflicts (both sides deleted same entity)

```python
from enum import Enum
from dataclasses import dataclass
from typing import Any
import json


class EntityType(str, Enum):
    TRANSACTION = "transaction"
    INVENTORY = "inventory"
    PREFERENCE = "preference"
    SKILL = "skill"
    EPISODE = "episode"
    GOAL = "goal"
    LOAN = "loan"


class ResolutionAction(str, Enum):
    MERGE = "merge"            # Combine both versions
    KEEP_LATEST = "keep_latest" # Use the version with latest timestamp
    ESCALATE = "escalate"       # Notify worker for manual resolution


@dataclass
class ConflictResolution:
    action: ResolutionAction
    merged_data: dict | None = None   # For MERGE
    winner_data: dict | None = None   # For KEEP_LATEST
    escalate_reason: str | None = None  # For ESCALATE


class ConflictResolver:
    """Resolves sync conflicts based on entity type and vector clock state."""

    def resolve(
        self,
        entity_type: EntityType,
        local_data: dict,
        remote_data: dict,
        local_clock: dict,
        remote_clock: dict,
    ) -> ConflictResolution:
        """Resolve a conflict between local (device) and remote (backend) versions."""

        if entity_type == EntityType.TRANSACTION:
            return self._merge_transactions(local_data, remote_data)

        elif entity_type == EntityType.INVENTORY:
            return self._resolve_inventory(local_data, remote_data)

        elif entity_type == EntityType.PREFERENCE:
            return self._merge_preferences(local_data, remote_data)

        elif entity_type == EntityType.SKILL:
            return self._merge_skills(local_data, remote_data)

        elif entity_type == EntityType.EPISODE:
            return self._merge_episodes(local_data, remote_data)

        elif entity_type in (EntityType.GOAL, EntityType.LOAN):
            return self._resolve_stateful(local_data, remote_data, entity_type)

        # Default: latest timestamp wins
        return ConflictResolution(
            action=ResolutionAction.KEEP_LATEST,
            winner_data=local_data if local_data["timestamp"] > remote_data["timestamp"] else remote_data,
        )

    def _merge_transactions(self, local: dict, remote: dict) -> ConflictResolution:
        """Additive merge — both transactions are valid financial events."""
        # Both are kept with their unique IDs. No data loss.
        # The merge just ensures both exist in the canonical store.
        return ConflictResolution(
            action=ResolutionAction.MERGE,
            merged_data={
                "keep_both": True,
                "local_id": local["id"],
                "remote_id": remote["id"],
            },
        )

    def _resolve_inventory(self, local: dict, remote: dict) -> ConflictResolution:
        """Latest timestamp wins, but escalate if delta is too large."""
        local_qty = local.get("quantity", 0)
        remote_qty = remote.get("quantity", 0)
        expected = local.get("expected_stock", max(local_qty, remote_qty))

        delta = abs(local_qty - remote_qty)
        if expected > 0 and delta / expected > 0.20:
            # >20% mismatch — likely physical count discrepancy
            return ConflictResolution(
                action=ResolutionAction.ESCALATE,
                escalate_reason=f"Stock mismatch: device={local_qty}, cloud={remote_qty}, delta={delta}",
            )

        winner = local if local["timestamp"] > remote["timestamp"] else remote
        return ConflictResolution(
            action=ResolutionAction.KEEP_LATEST,
            winner_data=winner,
        )

    def _merge_preferences(self, local: dict, remote: dict) -> ConflictResolution:
        """Union of non-conflicting settings; same-key → latest timestamp."""
        merged = {}
        all_keys = set(local.get("settings", {}).keys()) | set(remote.get("settings", {}).keys())
        for key in all_keys:
            l_val = local.get("settings", {}).get(key)
            r_val = remote.get("settings", {}).get(key)
            if l_val is None:
                merged[key] = r_val
            elif r_val is None:
                merged[key] = l_val
            else:
                # Both have the key — use the one from the later timestamp
                merged[key] = l_val if local["timestamp"] > remote["timestamp"] else r_val
        return ConflictResolution(
            action=ResolutionAction.MERGE,
            merged_data={"settings": merged, "timestamp": max(local["timestamp"], remote["timestamp"])},
        )

    def _merge_skills(self, local: dict, remote: dict) -> ConflictResolution:
        """Union of patterns; same pattern → keep highest confidence."""
        merged_patterns = {}
        for p in local.get("patterns", []):
            merged_patterns[p["key"]] = p
        for p in remote.get("patterns", []):
            existing = merged_patterns.get(p["key"])
            if existing is None:
                merged_patterns[p["key"]] = p
            elif p["confidence"] > existing["confidence"]:
                merged_patterns[p["key"]] = p
            # else keep existing (higher confidence)
        return ConflictResolution(
            action=ResolutionAction.MERGE,
            merged_data={"patterns": list(merged_patterns.values()), "timestamp": max(local["timestamp"], remote["timestamp"])},
        )

    def _merge_episodes(self, local: dict, remote: dict) -> ConflictResolution:
        """Union — keep all unique episodes."""
        return ConflictResolution(
            action=ResolutionAction.MERGE,
            merged_data={"keep_both": True},
        )

    def _resolve_stateful(self, local: dict, remote: dict, entity_type: EntityType) -> ConflictResolution:
        """Latest timestamp wins. Escalate contradictory states."""
        terminal_states = {"paid", "completed", "cancelled"}
        local_state = local.get("state", "")
        remote_state = remote.get("state", "")

        # Contradictory: one says terminal, other says active
        if (local_state in terminal_states) != (remote_state in terminal_states):
            return ConflictResolution(
                action=ResolutionAction.ESCALATE,
                escalate_reason=f"{entity_type.value} state conflict: device={local_state}, cloud={remote_state}",
            )

        winner = local if local["timestamp"] > remote["timestamp"] else remote
        return ConflictResolution(
            action=ResolutionAction.KEEP_LATEST,
            winner_data=winner,
        )
```

**Sync response format (updated):**
```python
class SyncResponse(BaseModel):
    status: str  # "ok" | "partial" | "conflicts"
    synced_count: int
    conflicts: list[SyncConflict] = []  # Conflicts needing resolution
    intelligence_updates_available: bool
    backend_clock: dict[str, int]  # Backend's current vector clock


class SyncConflict(BaseModel):
    entity_type: EntityType
    entity_id: str
    local_data: dict      # What the device sent
    remote_data: dict     # What the backend has
    local_clock: dict
    remote_clock: dict
    auto_resolved: bool   # True if backend already applied resolution
    resolution: ConflictResolution | None = None
```

---

## 3. FREE RESOURCE STACK

### 3.1 Oracle Cloud Free Tier Allocation

**Available:** 2 ARM OCPUs, 12GB RAM, 200GB storage

| Service | CPU | RAM | Storage | Notes |
|---|---|---|---|---|
| PostgreSQL 16 | 0.5 | 1.5GB | 50GB | Main data store |
| Redis 7 | 0.25 | 256MB | — | Cache + queues + FL state |
| ClickHouse 24 | 0.25 | 1GB | 100GB | Analytics engine |
| FastAPI App | 0.5 | 512MB | — | API server |
| Worker Process | 0.25 | 512MB | — | Background tasks |
| Nginx | 0.1 | 64MB | — | Reverse proxy |
| Prometheus | 0.1 | 256MB | 10GB | Metrics |
| Grafana | 0.05 | 128MB | 5GB | Dashboards |
| **TOTAL** | **2.0** | **4.3GB** | **165GB** | **7.7GB headroom** |

**Decision: No llama.cpp on free tier.** The 7B model needs 6-8GB RAM alone. Use the free tier for data pipeline + intelligence products. LLM inference can be added later when revenue justifies a paid instance.

### 3.2 PostgreSQL Configuration

```yaml
# docker-compose.oracle.yml
postgres:
  image: postgres:16-alpine
  command: >
    postgres
    -c shared_buffers=384MB
    -c effective_cache_size=1GB
    -c work_mem=4MB
    -c maintenance_work_mem=128MB
    -c max_connections=50
    -c wal_level=replica
    -c max_wal_size=1GB
    -c random_page_cost=1.1  # SSD storage
  deploy:
    resources:
      limits:
        cpus: "0.5"
        memory: 1536M
```

### 3.3 Redis Configuration

```yaml
redis:
  image: redis:7-alpine
  command: >
    redis-server
    --maxmemory 200mb
    --maxmemory-policy allkeys-lru
    --save 60 1000
    --save 300 10
    --appendonly yes
    --appendfsync everysec
  deploy:
    resources:
      limits:
        cpus: "0.25"
        memory: 256M
```

**Redis usage:**
- Cache: Intelligence product cache (TTL 1 hour)
- Queues: Task queue (sorted sets), FL update queue
- State: FL round state, rate limiting counters
- Pub/Sub: Event notifications between app and worker

### 3.4 ClickHouse Configuration

```yaml
clickhouse:
  image: clickhouse/clickhouse-server:24-alpine
  environment:
    CLICKHOUSE_DB: biashara
    CLICKHOUSE_USER: admin
    CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
  volumes:
    - clickhouse-data:/var/lib/clickhouse
  deploy:
    resources:
      limits:
        cpus: "0.25"
        memory: 1024M
```

**ClickHouse tables:**
- `transactions_analytics` — Denormalized transaction data (600M+ rows target)
- `economic_indicators` — Aggregated economic metrics by region/period
- `market_data` — Price time-series by product/region
- `worker_activity` — Worker engagement metrics

### 3.5 Flower for Federated Learning

```python
# app/services/fl_server.py
import flwr as fl

class AngavuFedAvg(fl.server.strategy.FedAvg):
    """Custom FedAvg with differential privacy and k-anonymity."""
    
    def __init__(self, min_available_clients=5, min_fit_clients=5):
        super().__init__(
            min_available_clients=min_available_clients,
            min_fit_clients=min_fit_clients,
            fraction_fit=1.0,
        )
        self.dp_epsilon = 0.1
        self.dp_delta = 1e-6
    
    def aggregate_fit(self, rnd, results, failures):
        """Aggregate with DP noise injection."""
        # Standard FedAvg aggregation
        aggregated = super().aggregate_fit(rnd, results, failures)
        if aggregated is not None:
            # Add calibrated Gaussian noise for (ε,δ)-DP
            aggregated = self._add_dp_noise(aggregated)
        return aggregated
```

**Flower integration:**
- Flower server runs in the worker process
- Devices connect via REST API bridge (`/api/v1/fl/fit`)
- Each "fit" round: device trains locally, sends gradients
- Server aggregates with FedAvg + DP noise
- Global model stored in PostgreSQL, distributed via API

### 3.6 Prometheus + Grafana

```yaml
prometheus:
  image: prom/prometheus:v2.53.0
  volumes:
    - ./deploy/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus-data:/prometheus
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.retention.time=30d'
    - '--storage.tsdb.retention.size=5GB'
  deploy:
    resources:
      limits:
        cpus: "0.1"
        memory: 256M

grafana:
  image: grafana/grafana:11.1.0
  volumes:
    - grafana-data:/var/lib/grafana
  environment:
    GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
  deploy:
    resources:
      limits:
        cpus: "0.05"
        memory: 128M
```

**Metrics to track (see §3.7 for full cognitive loop metrics):**
- API latency (p50, p95, p99) per endpoint
- Cognitive loop phase latency, success rate, error count (per phase)
- Sync throughput (transactions/second)
- FL aggregation rounds and quality scores
- Intelligence product generation time
- Database connection pool utilization
- Redis memory usage
- ClickHouse query latency

---

### 3.7 Per-Phase Cognitive Loop Metrics (Prometheus)

The backend mirrors the Android cognitive loop phases for server-side observability. Each phase of the intelligence pipeline emits Prometheus metrics.

**Metrics Definition:**

| Phase | Latency (Histogram) | Success Rate (Gauge) | Error Count (Counter) | Labels |
|-------|--------------------|--------------------|----------------------|--------|
| `perceive` | `angavu_phase_latency_seconds{phase="perceive"}` | `angavu_phase_success_rate{phase="perceive"}` | `angavu_phase_errors_total{phase="perceive"}` | `endpoint`, `worker_region` |
| `remember` | `angavu_phase_latency_seconds{phase="remember"}` | `angavu_phase_success_rate{phase="remember"}` | `angavu_phase_errors_total{phase="remember"}` | `endpoint`, `cache_hit` |
| `reason` | `angavu_phase_latency_seconds{phase="reason"}` | `angavu_phase_success_rate{phase="reason"}` | `angavu_phase_errors_total{phase="reason"}` | `endpoint`, `model_used` |
| `act` | `angavu_phase_latency_seconds{phase="act"}` | `angavu_phase_success_rate{phase="act"}` | `angavu_phase_errors_total{phase="act"}` | `endpoint`, `tool_name` |
| `learn` | `angavu_phase_latency_seconds{phase="learn"}` | `angavu_phase_success_rate{phase="learn"}` | `angavu_phase_errors_total{phase="learn"}` | `endpoint`, `store_type` |

**Additional Pipeline Metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `angavu_sync_transactions_total` | Counter | Total transactions synced from devices |
| `angavu_sync_duration_seconds` | Histogram | Sync request processing time |
| `angavu_intelligence_generation_seconds` | Histogram | Intelligence product generation time |
| `angavu_fl_round_total` | Counter | Total FL aggregation rounds completed |
| `angavu_fl_clients_per_round` | Histogram | Number of clients per FL round |
| `angavu_fl_round_duration_seconds` | Histogram | FL round aggregation time |
| `angavu_db_query_duration_seconds` | Histogram | Database query latency by table |
| `angavu_redis_operation_duration_seconds` | Histogram | Redis operation latency |
| `angavu_active_workers` | Gauge | Currently active worker connections |
| `angavu_memory_usage_bytes` | Gauge | Process memory usage |
| `angavu_cpu_usage_ratio` | Gauge | CPU utilization (0.0-1.0) |

**Alerting Thresholds (Prometheus alerting rules):**

```yaml
# deploy/oracle/alert_rules.yml
groups:
  - name: cognitive_loop_alerts
    rules:
      # Perceive phase: intent classification + NLU
      - alert: PerceivePhaseHighLatency
        expr: histogram_quantile(0.95, rate(angavu_phase_latency_seconds_bucket{phase="perceive"}[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Perceive phase p95 latency > 500ms"
          description: "Intent classification is slow. Check regex complexity or NLU model."

      - alert: PerceivePhaseCriticalLatency
        expr: histogram_quantile(0.95, rate(angavu_phase_latency_seconds_bucket{phase="perceive"}[5m])) > 2.0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Perceive phase p95 latency > 2s (critical)"

      # Remember phase: cache/context retrieval
      - alert: RememberPhaseHighLatency
        expr: histogram_quantile(0.95, rate(angavu_phase_latency_seconds_bucket{phase="remember"}[5m])) > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Remember phase p95 latency > 200ms"
          description: "Context retrieval slow. Check Redis/DB hit rates."

      - alert: RememberPhaseLowSuccessRate
        expr: angavu_phase_success_rate{phase="remember"} < 0.90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Remember phase success rate < 90%"

      # Reason phase: LLM inference or rule engine
      - alert: ReasonPhaseHighLatency
        expr: histogram_quantile(0.95, rate(angavu_phase_latency_seconds_bucket{phase="reason"}[5m])) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Reason phase p95 latency > 1s"
          description: "Reasoning is slow. Check LLM model load or rule engine complexity."

      - alert: ReasonPhaseCriticalLatency
        expr: histogram_quantile(0.95, rate(angavu_phase_latency_seconds_bucket{phase="reason"}[5m])) > 5.0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Reason phase p95 latency > 5s (critical)"

      - alert: ReasonPhaseLowSuccessRate
        expr: angavu_phase_success_rate{phase="reason"} < 0.85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Reason phase success rate < 85%"

      # Act phase: tool/service execution
      - alert: ActPhaseHighLatency
        expr: histogram_quantile(0.95, rate(angavu_phase_latency_seconds_bucket{phase="act"}[5m])) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Act phase p95 latency > 1s"
          description: "Tool execution slow. Check DB writes and external service calls."

      - alert: ActPhaseLowSuccessRate
        expr: angavu_phase_success_rate{phase="act"} < 0.90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Act phase success rate < 90%"

      # Learn phase: memory update and learning signal processing
      - alert: LearnPhaseHighLatency
        expr: histogram_quantile(0.95, rate(angavu_phase_latency_seconds_bucket{phase="learn"}[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Learn phase p95 latency > 500ms"

      - alert: LearnPhaseLowSuccessRate
        expr: angavu_phase_success_rate{phase="learn"} < 0.90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Learn phase success rate < 90%"

      # System-level alerts
      - alert: HighErrorRate
        expr: sum(rate(angavu_phase_errors_total[5m])) > 10
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: "Phase error rate > 10/s across all phases"

      - alert: HighMemoryUsage
        expr: angavu_memory_usage_bytes / (1024*1024*1024) > 1.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "App memory usage > 1.5GB"

      - alert: HighCpuUsage
        expr: angavu_cpu_usage_ratio > 0.85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "CPU usage > 85% for 10 minutes"
```

**Implementation — `app/infrastructure/phase_metrics.py`:**

```python
"""
Per-phase cognitive loop metrics for Prometheus.

Instruments each phase of the intelligence pipeline with:
- Latency histogram (seconds)
- Success rate gauge (0.0-1.0)
- Error counter
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)

# ── Latency Histograms ──
PHASE_LATENCY = Histogram(
    "angavu_phase_latency_seconds",
    "Cognitive loop phase latency in seconds",
    ["phase"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── Success Rate Gauges ──
PHASE_SUCCESS_RATE = Gauge(
    "angavu_phase_success_rate",
    "Cognitive loop phase success rate (0.0-1.0)",
    ["phase"],
)

# ── Error Counters ──
PHASE_ERRORS = Counter(
    "angavu_phase_errors_total",
    "Total cognitive loop phase errors",
    ["phase"],
)

# ── Running totals for success rate calculation ──
_phase_totals: dict[str, dict] = {}

def _update_success_rate(phase: str, success: bool):
    """Update rolling success rate gauge."""
    if phase not in _phase_totals:
        _phase_totals[phase] = {"success": 0, "total": 0}

    _phase_totals[phase]["total"] += 1
    if success:
        _phase_totals[phase]["success"] += 1

    rate = _phase_totals[phase]["success"] / _phase_totals[phase]["total"]
    PHASE_SUCCESS_RATE.labels(phase=phase).set(rate)

    # Reset counters every 1000 entries to keep recent data
    if _phase_totals[phase]["total"] >= 1000:
        _phase_totals[phase] = {
            "success": _phase_totals[phase]["success"] // 2,
            "total": _phase_totals[phase]["total"] // 2,
        }


@contextmanager
def measure_phase(phase: str):
    """Context manager to measure a cognitive loop phase.

    Usage:
        with measure_phase("reason"):
            result = do_reasoning()
    """
    start = time.monotonic()
    success = True
    try:
        yield
    except Exception as e:
        success = False
        PHASE_ERRORS.labels(phase=phase).inc()
        logger.error("phase_error", phase=phase, error=str(e))
        raise
    finally:
        elapsed = time.monotonic() - start
        PHASE_LATENCY.labels(phase=phase).observe(elapsed)
        _update_success_rate(phase, success)

        # Log slow phases
        if elapsed > 1.0:
            logger.warning("slow_phase", phase=phase, duration_s=round(elapsed, 3))


def phase_timer(phase: str):
    """Decorator version of measure_phase for async functions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with measure_phase(phase):
                return await func(*args, **kwargs)
        return wrapper
    return decorator
```

---

## 3.8 Buyer Dashboard — Revenue API

### Overview

The buyer dashboard exposes intelligence products as B2B API endpoints. Buyers (FMCG companies, banks, government, NGOs) pay for access to aggregated, anonymized intelligence derived from worker data.

**Authentication:** Separate buyer auth (not worker auth). API key + JWT.
**Rate Limiting:** Per-tier rate limits for B2B API.
**Report Generation:** PDF/HTML reports on demand.

### Buyer API Endpoints

```python
# app/api/v1/buyer.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.intelligence_engine import IntelligenceEngine
from app.services.buyer_auth import verify_buyer_api_key

router = APIRouter(prefix="/api/v1/buyer", tags=["Buyer Dashboard"])
security = HTTPBearer()


@router.get("/soko-pulse")
async def get_soko_pulse(
    product_category: str,
    region: str,
    period_start: str,
    period_end: str,
    buyer=Depends(verify_buyer_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Soko Pulse — FMCG Demand Forecasting.

    Returns demand forecasts, price elasticity, consumer surplus,
    and cross-border trade indicators for a product category/region.

    Pricing: $0.10-$1.00 per query (tier-dependent).
    """
    engine = IntelligenceEngine(db)
    result = await engine.generate_soko_pulse(
        product_category=product_category,
        region=region,
        period_start=period_start,
        period_end=period_end,
        tier=buyer.tier,
    )
    # Track usage for billing
    await track_usage(buyer.id, "soko_pulse", 1)
    return result


@router.get("/alama-score")
async def get_alama_score(
    worker_id_hash: str,
    buyer=Depends(verify_buyer_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Alama Score — Credit Scoring for Informal Workers.

    Returns creditworthiness score based on transaction patterns,
    business stability, and repayment history.

    Pricing: $0.05-$0.50 per score.
    """
    engine = IntelligenceEngine(db)
    result = await engine.generate_alama_score(
        worker_id_hash=worker_id_hash,
        tier=buyer.tier,
    )
    await track_usage(buyer.id, "alama_score", 1)
    return result


@router.get("/angavu-pulse")
async def get_angavu_pulse(
    region: str,
    period: str = "weekly",
    buyer=Depends(verify_buyer_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Angavu Pulse — MSME Activity Index.

    Returns aggregated MSME activity metrics: transaction volume,
    revenue trends, sector growth, employment indicators.

    Pricing: $500-$5,000/month subscription.
    """
    engine = IntelligenceEngine(db)
    result = await engine.generate_angavu_pulse(
        region=region,
        period=period,
        tier=buyer.tier,
    )
    await track_usage(buyer.id, "angavu_pulse", 1)
    return result


@router.get("/jamii-insights")
async def get_jamii_insights(
    region: str,
    insight_type: str = "financial_inclusion",
    buyer=Depends(verify_buyer_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Jamii Insights — Financial Inclusion Analytics.

    Returns financial inclusion metrics: savings rates, loan access,
    M-Pesa usage patterns, digital literacy indicators.

    Pricing: $100-$1,000 per report.
    """
    engine = IntelligenceEngine(db)
    result = await engine.generate_jamii_insights(
        region=region,
        insight_type=insight_type,
        tier=buyer.tier,
    )
    await track_usage(buyer.id, "jamii_insights", 1)
    return result


@router.get("/report/{report_type}")
async def generate_report(
    report_type: str,
    format: str = "pdf",  # pdf or html
    region: str = None,
    buyer=Depends(verify_buyer_api_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a formatted report (PDF/HTML).

    report_type: soko-pulse | alama-score | angavu-pulse | jamii-insights
    format: pdf | html
    """
    engine = IntelligenceEngine(db)
    report = await engine.generate_report(
        report_type=report_type,
        format=format,
        region=region,
        buyer_tier=buyer.tier,
    )
    await track_usage(buyer.id, f"report_{report_type}", 1)
    return report
```

### Buyer Authentication

```python
# app/services/buyer_auth.py
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

api_key_header = APIKeyHeader(name="X-API-Key")


async def verify_buyer_api_key(
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
):
    """Verify buyer API key and return buyer profile."""
    result = await db.execute(
        select(BuyerAccount).where(
            BuyerAccount.api_key == api_key,
            BuyerAccount.is_active == True,
        )
    )
    buyer = result.scalar_one_or_none()
    if not buyer:
        raise HTTPException(401, "Invalid API key")
    if buyer.rate_limit_remaining <= 0:
        raise HTTPException(429, "Rate limit exceeded")
    return buyer


BUYER_TIERS = {
    "starter": {"rate_limit": 100, "price_per_query": 0.10},     # $0.10/query, 100/day
    "professional": {"rate_limit": 1000, "price_per_query": 0.05},  # $0.05/query, 1K/day
    "enterprise": {"rate_limit": 10000, "price_per_query": 0.02},   # $0.02/query, 10K/day
}
```

### B2B Rate Limiting

```python
# app/services/buyer_rate_limiter.py
import redis.asyncio as redis
from datetime import UTC, datetime


class BuyerRateLimiter:
    """Per-buyer rate limiting using Redis sliding window."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def check_and_consume(self, buyer_id: str, tier: str) -> bool:
        """Check rate limit and consume one token. Returns True if allowed."""
        limits = BUYER_TIERS[tier]
        window_key = f"buyer_rate:{buyer_id}:{datetime.now(UTC).strftime('%Y%m%d')}"

        current = await self.redis.incr(window_key)
        if current == 1:
            await self.redis.expire(window_key, 86400)  # 24h window

        return current <= limits["rate_limit"]
```

### Buyer API Revenue Model

| Endpoint | Product | Pricing | Target Buyer |
|---|---|---|---|
| `GET /buyer/soko-pulse` | FMCG Demand Forecasting | $0.10-$1.00/query | FMCG companies (Unilever, P&G) |
| `GET /buyer/alama-score` | Credit Scoring | $0.05-$0.50/score | Banks, fintechs (M-Shwari, Tala) |
| `GET /buyer/angavu-pulse` | MSME Activity Index | $500-$5,000/month | Government (KNBS, Treasury) |
| `GET /buyer/jamii-insights` | Financial Inclusion | $100-$1,000/report | NGOs (World Bank, FSD Kenya) |
| `GET /buyer/report/{type}` | Formatted Reports | Included in tier | All buyers |

### Buyer Database Model

```python
# app/models/buyer.py
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Float
from sqlalchemy.orm import DeclarativeBase

class BuyerAccount(DeclarativeBase):
    __tablename__ = "buyer_accounts"

    id = Column(String, primary_key=True)
    company_name = Column(String, nullable=False)
    api_key = Column(String, unique=True, nullable=False, index=True)
    tier = Column(String, default="starter")  # starter | professional | enterprise
    is_active = Column(Boolean, default=True)
    rate_limit_remaining = Column(Integer, default=100)
    monthly_budget_usd = Column(Float, default=100.0)
    created_at = Column(DateTime)
    last_query_at = Column(DateTime)
    total_queries = Column(Integer, default=0)
    total_spend_usd = Column(Float, default=0.0)
```

---

## 4. FILE-BY-FILE CHANGES

### 4.1 Phase 1: Agent Consolidation (Week 1)

**Goal:** Reduce 33+ agents to 0 agents. Services-only architecture.

#### DELETE (agent files to remove):

```
# All agent infrastructure — replaced by direct service calls
app/agents/base.py                    # Re-export shim
app/agents/base_agent.py              # BiasharaAgent base class
app/agents/base_events.py             # AgentEvent, EventType
app/agents/base_protocols.py          # AgentMemory, AgentTools
app/agents/circuit_breaker_governance.py
app/agents/communication/__init__.py
app/agents/communication/broadcast.py
app/agents/communication/delegation.py
app/agents/communication/point_to_point.py
app/agents/context_manager.py
app/agents/cost_tracker.py
app/agents/domain/__init__.py
app/agents/domain/agriculture.py
app/agents/domain/base.py
app/agents/domain/digital.py
app/agents/domain/manufacturing.py
app/agents/domain/retail.py
app/agents/domain/service.py
app/agents/domain/transport.py
app/agents/error_compactor.py
app/agents/event_bus.py
app/agents/factory.py
app/agents/governance/__init__.py
app/agents/governance/audit.py
app/agents/governance/ethics.py
app/agents/governance/privacy.py
app/agents/harness/__init__.py
app/agents/harness/data_harness.py
app/agents/harness/execution.py
app/agents/hybrid_router.py
app/agents/implementations.py
app/agents/implementations_extra.py
app/agents/intelligence/alama_score_rag_agent.py
app/agents/intelligence/rag_engine.py
app/agents/intelligence/soko_pulse_rag_agent.py
app/agents/intelligence_pipeline.py
app/agents/knowledge_sharing.py
app/agents/long_horizon.py
app/agents/loop_implementations.py
app/agents/loops/__init__.py
app/agents/loops/core.py
app/agents/loops/feedback_loop.py
app/agents/loops/human_in_the_loop.py
app/agents/loops/llm_integration.py
app/agents/loops/ooda_loop.py
app/agents/loops/state_machine.py
app/agents/memory/__init__.py
app/agents/memory/tiered.py
app/agents/meta_agent.py
app/agents/observability.py
app/agents/orchestration/__init__.py
app/agents/orchestration/always_on_market_monitor.py
app/agents/orchestration/always_on_policy_monitor.py
app/agents/orchestration/mcp_swarm_router.py
app/agents/orchestration/self_improving_agent.py
app/agents/pipeline_agents.py
app/agents/pipeline_core.py
app/agents/pipeline_data.py
app/agents/pipeline_intelligence.py
app/agents/pipeline_planners.py
app/agents/progressive_autonomy.py
app/agents/protocols/__init__.py
app/agents/protocols/a2a.py
app/agents/protocols/a2a_transport.py
app/agents/protocols/mcp.py
app/agents/protocols/mcp_transport.py
app/agents/protocols/routes.py
app/agents/reflexion.py
app/agents/research/__init__.py
app/agents/research/innovation.py
app/agents/research/market_research.py
app/agents/research/user_insight.py
app/agents/research_flow.py
app/agents/self_evaluation.py
app/agents/self_evaluation_config.py
app/agents/skill_generator.py
app/agents/subagent.py
app/agents/task_decomposition.py
app/agents/templates/__init__.py
app/agents/templates/financial.py
app/agents/unified_state.py
app/agents/utility/__init__.py
app/agents/utility/anomaly_detector.py
app/agents/utility/communication_agent.py
app/agents/utility/data_quality.py
app/agents/utility/learning_agent.py
app/agents/utility/prediction_agent.py
app/agents/utility/sync_agent.py

# Duplicate autonomous agents
app/autonomous/agents/__init__.py
app/autonomous/agents/base.py
app/autonomous/agents/content_agent.py
app/autonomous/agents/content_creator.py
app/autonomous/agents/invoicing_agent.py
app/autonomous/agents/lead_qualifier.py
app/autonomous/agents/onboarding_agent.py
app/autonomous/agents/operations_agent.py
app/autonomous/agents/sales_agent.py

# Agent models (replaced by service-level models)
app/models/agent_models.py

# Agent-specific API routes (consolidate into services)
app/api/agent_loops.py
app/api/agent_router.py

# DeerFlow integration (over-engineered for current scale)
app/deerflow/__init__.py
app/deerflow/integration.py
app/deerflow/state/__init__.py
app/deerflow/state/persistence.py
app/deerflow/state/reducers.py
app/deerflow/state/thread_state.py

# MCP server/client (not needed without agents)
app/mcp/__init__.py
app/mcp/client.py
app/mcp/config.py
app/mcp/router.py
app/mcp/server.py
app/mcp/tools/__init__.py
app/mcp/tools/agent_communication.py
app/mcp/tools/intelligence.py
app/mcp/tools/worker_data.py

# Post-quantum cryptography (premature for MVP)
app/security/pqc/__init__.py
app/security/pqc/algorithm_registry.py
app/security/pqc/audit.py
app/security/pqc/config.py
app/security/pqc/crypto_provider.py
app/security/pqc/fl_encryption.py
app/security/pqc/hybrid_key_exchange.py
app/security/pqc/ml_dsa.py
app/security/pqc/ml_kem.py
app/security/pqc/tls_config.py

# Eval harness (not needed at this scale)
app/evals/__init__.py
app/evals/categories.py
app/evals/harness.py
app/evals/runner.py
```

**Total: 153 files deleted (~59,762 lines removed, 30% of codebase)**

#### MODIFY:

**`app/main.py`** — Strip agent infrastructure from lifespan:

```python
# BEFORE: 300+ lines of agent wiring in lifespan()
# AFTER: Minimal lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    cache = get_cache()
    await cache.connect()
    task_queue = get_task_queue()
    await task_queue.connect()
    
    if settings.has_clickhouse:
        await get_clickhouse()
    
    yield
    
    # Shutdown
    if settings.has_clickhouse:
        await close_clickhouse()
    await task_queue.close()
    await cache.close()
    await close_db()
```

**`app/api/v1/__init__.py`** — Remove agent-related routers:

```python
# Remove:
# from app.api.v1.agents import agents_router
# v1_router.include_router(agents_router)

# Keep: auth, intelligence, finance, channels, dashboard, infra, worker, users, transactions, ai_chat, market, social
```

**`app/api/v1/intelligence.py`** — Direct service calls, no agent indirection:

```python
# BEFORE: Routes delegate to IntelligenceGeneratorAgent
# AFTER: Routes call SokoPulseService, AlamaScoreService directly

@router.post("/soko-pulse")
async def generate_soko_pulse(
    request: SokoPulseRequest,
    db: AsyncSession = Depends(get_db),
):
    service = SokoPulseService(db)
    result = await service.generate_demand_forecast(
        product_category=request.product_category,
        region=request.region,
        period_start=request.period_start,
        period_end=request.period_end,
        tier=request.tier,
    )
    return result
```

#### CREATE:

**`app/services/scheduler.py`** — Background task scheduler:

```python
"""
Intelligence product scheduler.

Pre-computes intelligence products on schedule rather than on-demand.
This ensures consistent latency for buyers and reduces compute spikes.
"""

import asyncio
from datetime import UTC, datetime, time
import structlog

logger = structlog.get_logger(__name__)


class IntelligenceScheduler:
    """Cron-like scheduler for intelligence product generation."""
    
    def __init__(self, db_factory, task_queue):
        self.db_factory = db_factory
        self.task_queue = task_queue
        self._running = False
    
    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        while self._running:
            now = datetime.now(UTC)
            await self._check_and_run(now)
            await asyncio.sleep(60)  # Check every minute
    
    async def _check_and_run(self, now: datetime):
        """Check if any scheduled tasks should run."""
        # Daily at 2 AM: Soko Pulse for all active regions
        if now.hour == 2 and now.minute == 0:
            await self._enqueue_soko_pulse_batch()
        
        # Weekly Monday 3 AM: Angavu Pulse
        if now.weekday() == 0 and now.hour == 3 and now.minute == 0:
            await self._enqueue_angavu_pulse_batch()
        
        # Monthly 1st at 4 AM: Jamii Insights, Tax Base
        if now.day == 1 and now.hour == 4 and now.minute == 0:
            await self._enqueue_monthly_reports()
    
    async def _enqueue_soko_pulse_batch(self):
        """Generate Soko Pulse for all active regions."""
        from app.models.user import User
        from sqlalchemy import select, distinct
        
        async with self.db_factory() as db:
            result = await db.execute(
                select(distinct(User.location_geohash)).where(
                    User.is_active == True,
                    User.consent_data_sharing == True,
                )
            )
            regions = [row[0] for row in result.all() if row[0]]
        
        for region in regions:
            await self.task_queue.enqueue(
                "generate_soko_pulse",
                {"region": region, "tier": "standard"},
                priority=2,  # NORMAL
            )
        logger.info("soko_pulse_batch_enqueued", regions=len(regions))
```

**`app/services/fl_server.py`** — Flower-based FL server:

```python
"""
Federated Learning server using Flower.

Replaces the in-memory _FLState with a proper FL framework.
Runs as part of the worker process.
"""

import flwr as fl
from flwr.common import Parameters, FitRes, Code
from flwr.server.client_proxy import ClientProxy
import numpy as np
import structlog

logger = structlog.get_logger(__name__)


class AngavuStrategy(fl.server.strategy.FedAvg):
    """Custom FedAvg with DP and k-anonymity."""
    
    def __init__(self, min_clients=5, dp_epsilon=0.1):
        super().__init__(
            min_available_clients=min_clients,
            min_fit_clients=min_clients,
            fraction_fit=1.0,
            fraction_evaluate=0.0,
        )
        self.dp_epsilon = dp_epsilon
        self.round_count = 0
    
    def aggregate_fit(self, rnd, results, failures):
        """Aggregate with differential privacy noise."""
        aggregated = super().aggregate_fit(rnd, results, failures)
        if aggregated is not None:
            parameters, metrics = aggregated
            # Add calibrated Gaussian noise
            noisy_params = self._apply_dp_noise(parameters)
            self.round_count += 1
            logger.info(
                "fl_round_aggregated",
                round=rnd,
                clients=len(results),
                failures=len(failures),
            )
            return noisy_params, metrics
        return aggregated
    
    def _apply_dp_noise(self, parameters):
        """Add Gaussian noise for (ε,δ)-DP."""
        import math
        sigma = math.sqrt(2.0 * math.log(1.25 / 1e-6)) / self.dp_epsilon
        noisy_arrays = []
        for arr in parameters.tensors:
            noise = np.random.normal(0, sigma, size=len(arr))
            noisy_arrays.append(arr + noise.astype(arr.dtype))
        return Parameters(tensors=noisy_arrays, tensor_type=parameters.tensor_type)


def start_fl_server(host="0.0.0.0", port=8081):
    """Start Flower FL server."""
    strategy = AngavuStrategy(min_clients=5, dp_epsilon=0.1)
    fl.server.start_server(
        server_address=f"{host}:{port}",
        strategy=strategy,
        config=fl.server.ServerConfig(num_rounds=1),
    )
```

**`app/services/intelligence_engine.py`** — Unified intelligence generation:

```python
"""
Unified Intelligence Engine.

Replaces the agent-based intelligence generation with direct service calls.
All intelligence products are generated by calling the appropriate service
and storing results in the database.
"""

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.intelligence.soko_pulse import SokoPulseService
from app.services.intelligence.alama_score import AlamaScoreService

logger = structlog.get_logger(__name__)


class IntelligenceEngine:
    """
    Central intelligence generation engine.
    
    Replaces IntelligenceGeneratorAgent. Calls services directly
    without agent lifecycle overhead.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.soko_pulse = SokoPulseService(db)
        self.alama_score = AlamaScoreService(db)
    
    async def generate_soko_pulse(self, **kwargs):
        """Generate Soko Pulse demand forecast."""
        return await self.soko_pulse.generate_demand_forecast(**kwargs)
    
    async def generate_alama_score(self, **kwargs):
        """Generate Alama credit score."""
        return await self.alama_score.compute_score(**kwargs)
    
    async def generate_angavu_pulse(self, **kwargs):
        """Generate Angavu Pulse government MSME index."""
        # Implementation from existing services/intelligence/biashara_pulse.py
        pass
    
    async def generate_jamii_insights(self, **kwargs):
        """Generate Jamii Insights financial inclusion report."""
        pass
    
    async def generate_tax_base(self, **kwargs):
        """Generate tax base estimation."""
        pass
    
    async def generate_distribution_gap(self, **kwargs):
        """Generate distribution gap analysis."""
        pass
```

### 4.2 Phase 2: Resource Optimization (Week 2)

#### MODIFY:

**`deploy/oracle/docker-compose.yml`** — New resource allocation:

```yaml
version: "3.8"

services:
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/oracle/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./deploy/oracle/ssl:/etc/nginx/ssl:ro
    depends_on:
      - app
    deploy:
      resources:
        limits:
          cpus: "0.1"
          memory: 64M
    restart: unless-stopped

  app:
    build:
      context: .
      dockerfile: deploy/oracle/Dockerfile
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - REDIS_URL=redis://redis:6379/0
      - CLICKHOUSE_URL=http://clickhouse:8123
      - CLICKHOUSE_DATABASE=biashara
      - CLICKHOUSE_USER=admin
      - CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512M
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import httpx; httpx.get('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

  worker:
    build:
      context: .
      dockerfile: deploy/oracle/Dockerfile
    command: python -m app.worker
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
      - REDIS_URL=redis://redis:6379/0
      - CLICKHOUSE_URL=http://clickhouse:8123
      - CLICKHOUSE_DATABASE=biashara
      - CLICKHOUSE_USER=admin
      - CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 512M
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    command: >
      postgres
      -c shared_buffers=384MB
      -c effective_cache_size=1GB
      -c work_mem=4MB
      -c maintenance_work_mem=128MB
      -c max_connections=50
      -c random_page_cost=1.1
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-angavu}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-biashara}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 1536M
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-angavu}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: >
      redis-server
      --maxmemory 200mb
      --maxmemory-policy allkeys-lru
      --save 60 1000
      --save 300 10
      --appendonly yes
    volumes:
      - redis-data:/data
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 256M
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  clickhouse:
    image: clickhouse/clickhouse-server:24-alpine
    environment:
      CLICKHOUSE_DB: biashara
      CLICKHOUSE_USER: admin
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
    volumes:
      - clickhouse-data:/var/lib/clickhouse
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 1024M
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:8123/ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  prometheus:
    image: prom/prometheus:v2.53.0
    volumes:
      - ./deploy/oracle/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'
      - '--storage.tsdb.retention.size=5GB'
    deploy:
      resources:
        limits:
          cpus: "0.1"
          memory: 256M
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.1.0
    volumes:
      - grafana-data:/var/lib/grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD}
    deploy:
      resources:
        limits:
          cpus: "0.05"
          memory: 128M
    restart: unless-stopped

volumes:
  postgres-data:
  redis-data:
  clickhouse-data:
  prometheus-data:
  grafana-data:
```

**Resource total: 2.0 OCPUs, 4.3GB RAM, 165GB storage — fits comfortably in free tier.**

#### MODIFY:

**`app/worker.py`** — Enhanced worker with scheduler:

```python
"""
Background worker — enhanced with intelligence scheduler.

Runs:
1. Task queue worker (existing)
2. Intelligence scheduler (new)
3. FL aggregation server (new)
"""

import asyncio
import signal
import structlog

from app.config import get_settings
from app.db.database import close_db, init_db, async_session_factory
from app.services.task_queue import get_task_queue
from app.services.scheduler import IntelligenceScheduler

settings = get_settings()
logger = structlog.get_logger("worker")
_shutdown = asyncio.Event()


def _handle_signal(sig, frame):
    logger.info("signal_received", signal=sig)
    _shutdown.set()


async def main():
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    
    logger.info("worker_starting", env=settings.APP_ENV)
    await init_db()
    
    queue = get_task_queue()
    await queue.connect()
    
    # Import task handlers
    import app.services.task_handlers  # noqa: F401
    
    # Start intelligence scheduler
    scheduler = IntelligenceScheduler(
        db_factory=async_session_factory,
        task_queue=queue,
    )
    
    # Run worker and scheduler concurrently
    await asyncio.gather(
        queue.start_worker(),
        scheduler.start(),
        _shutdown.wait(),
        return_exceptions=True,
    )
    
    logger.info("worker_shutting_down")
    await queue.close()
    await close_db()
    logger.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
```

### 4.3 Phase 3: FL Consolidation (Week 2-3)

#### DELETE:

```
app/services/federated_learning.py     # Original (in-memory state)
app/services/federated_learning_v2.py  # V2 (duplicate)
app/api/fl_aggregator.py              # Third path (external import)
app/schemas/federated_learning.py      # Old schemas
app/services/fl_persistence.py        # SQLite persistence
```

#### CREATE:

**`app/api/v1/fl.py`** — Unified FL API:

```python
"""
Federated Learning API — Device-to-server gradient aggregation.

Endpoints:
- POST /fl/upload   — Submit gradient update from device
- GET  /fl/model/{dialect} — Get latest global model
- GET  /fl/status   — FL system status
- POST /fl/fit      — Flower client bridge (for Flower-based devices)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.fl_service import FLService

router = APIRouter(prefix="/fl", tags=["Federated Learning"])


@router.post("/upload")
async def upload_gradient(
    request: FLUploadRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit gradient update from device."""
    service = FLService(db)
    return await service.upload_update(request)


@router.get("/model/{dialect}")
async def get_global_model(dialect: str, db: AsyncSession = Depends(get_db)):
    """Get latest aggregated global model for a dialect."""
    service = FLService(db)
    model = await service.get_global_model(dialect)
    if model is None:
        raise HTTPException(404, f"No model available for dialect: {dialect}")
    return model


@router.get("/status")
async def fl_status(db: AsyncSession = Depends(get_db)):
    """Get FL system status."""
    service = FLService(db)
    return await service.get_status()
```

**`app/services/fl_service.py`** — Consolidated FL service:

```python
"""
Consolidated Federated Learning Service.

Merges federated_learning.py and federated_learning_v2.py into one service.
Uses PostgreSQL for persistence (not SQLite or in-memory).
Uses Redis for FL round state.
"""

import json
import math
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fl_model import FLGlobalModel, FLUpdate, FLRound

logger = structlog.get_logger(__name__)

DP_EPSILON = 0.1
DP_DELTA = 1e-6
MIN_UPDATES_FOR_AGGREGATION = 5


class FLService:
    """Privacy-preserving federated learning aggregation."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def upload_update(self, request) -> dict:
        """Process a gradient update from a device."""
        # Validate, store, check threshold, aggregate if met
        update = FLUpdate(
            device_id_hash=request.device_id_hash,
            dialect=request.dialect,
            calibration_params=request.calibration_params,
            correction_patterns=request.correction_patterns,
            adapter_deltas=request.adapter_deltas,
            metadata=request.metadata,
        )
        self.db.add(update)
        await self.db.flush()
        
        # Check if aggregation threshold met
        count = await self._pending_count(request.dialect)
        if count >= MIN_UPDATES_FOR_AGGREGATION:
            version = await self._aggregate(request.dialect)
            return {"status": "aggregated", "version": version}
        
        return {"status": "accepted", "pending": count}
    
    async def get_global_model(self, dialect: str) -> dict | None:
        """Get latest global model for a dialect."""
        result = await self.db.execute(
            select(FLGlobalModel)
            .where(FLGlobalModel.dialect == dialect)
            .order_by(FLGlobalModel.created_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return {
            "version": model.version,
            "dialect": model.dialect,
            "calibration_params": json.loads(model.calibration_params),
            "vocabulary_updates": json.loads(model.vocabulary_updates),
            "adapter_deltas": model.adapter_deltas,
        }
    
    async def get_status(self) -> dict:
        """Get FL system status."""
        result = await self.db.execute(
            select(
                FLUpdate.dialect,
                func.count(FLUpdate.id),
            ).group_by(FLUpdate.dialect)
        )
        dialect_counts = {row[0]: row[1] for row in result.all()}
        
        return {
            "status": "ok",
            "dialects": dialect_counts,
            "total_updates": sum(dialect_counts.values()),
        }
    
    async def _pending_count(self, dialect: str) -> int:
        result = await self.db.execute(
            select(func.count(FLUpdate.id))
            .where(FLUpdate.dialect == dialect, FLUpdate.processed == False)
        )
        return result.scalar() or 0
    
    async def _aggregate(self, dialect: str) -> str:
        """Run FedAvg aggregation for a dialect."""
        # Fetch pending updates
        result = await self.db.execute(
            select(FLUpdate)
            .where(FLUpdate.dialect == dialect, FLUpdate.processed == False)
            .order_by(FLUpdate.created_at)
            .limit(500)
        )
        updates = result.scalars().all()
        
        # FedAvg aggregation (same logic as current implementation)
        # ... (weighted average of calibration params, vocab, adapter deltas)
        
        # Apply DP noise
        # ... (Gaussian noise with sigma from epsilon)
        
        # Store global model
        version = f"v3.2.{int(datetime.now(UTC).timestamp())}"
        model = FLGlobalModel(
            dialect=dialect,
            version=version,
            calibration_params=json.dumps(agg_params),
            vocabulary_updates=json.dumps(agg_vocab),
            adapter_deltas=agg_adapter,
            updates_included=len(updates),
        )
        self.db.add(model)
        
        # Mark updates as processed
        for update in updates:
            update.processed = True
        
        await self.db.flush()
        logger.info("fl_aggregation_complete", dialect=dialect, version=version, updates=len(updates))
        return version
```

### 4.4 Phase 4: API Consolidation (Week 3)

#### DELETE:

```
app/api/agent_loops.py          # Agent loop management
app/api/agent_router.py         # Agent management routes
app/api/biashara_sync.py        # Duplicate of sync.py
app/api/evolution.py            # Self-evolution (agent concept)
app/api/explain.py              # Explainability (agent concept)
app/api/harness.py              # Agent harness management
app/api/infrastructure_v2.py    # Duplicate of infrastructure.py
app/api/long_horizon.py         # Long-horizon orchestration (agent concept)
app/api/model_router.py         # Agent model routing
app/api/phase1_intelligence.py  # Duplicate of intelligence.py
app/api/skills.py               # Agent skill management
app/api/stickiness.py           # Move to worker features
app/api/trigger_router.py       # Consolidate into channels
```

#### KEEP (consolidated):

```
app/api/v1/auth.py              # Authentication (JWT + OTP)
app/api/v1/intelligence.py      # Intelligence products (Soko Pulse, Alama, etc.)
app/api/v1/finance.py           # Biashara sync, reports
app/api/v1/channels.py          # WhatsApp, Telegram, SMS, triggers
app/api/v1/dashboard.py         # Dashboard, policymaker
app/api/v1/infra.py             # Deployment, infrastructure
app/api/v1/worker.py            # Onboarding, features, goals, loans
app/api/v1/users.py             # User management
app/api/v1/transactions.py      # Transaction CRUD
app/api/v1/ai_chat.py           # AI chat (direct LLM, no agents)
app/api/v1/market.py            # Market prices
app/api/v1/social.py            # Social features
app/api/v1/fl.py                # NEW: Federated learning
```

### 4.5 Phase 5: Dependency Cleanup (Week 3)

#### MODIFY:

**`requirements.txt`** — Remove unused dependencies:

```diff
# REMOVE:
- liboqs-python>=0.14.1         # Post-quantum crypto (premature)
- deerflow-harness>=0.0.1       # DeerFlow agents (removed)
- langgraph>=0.2.0              # DeerFlow dependency
- langgraph-sdk>=0.1.3          # DeerFlow dependency
- langchain>=0.3.0              # DeerFlow dependency
- lifelines>=0.27.0             # Survival analysis (unused in core pipeline)
- marshmallow==4.3.0            # Redundant with Pydantic
- aiohttp==3.14.1               # Redundant with httpx
- geopy==2.4.1                  # Not used in core

# ADD:
+ flwr>=1.10.0                  # Flower federated learning
+ apscheduler>=3.10.0           # Background task scheduling
```

---

## 5. MIGRATION PLAN

### Week 1: Agent Consolidation
1. Create `app/services/intelligence_engine.py` (unified entry point)
2. Create `app/services/scheduler.py` (background scheduling)
3. Modify `app/main.py` — remove all agent wiring from lifespan
4. Modify `app/api/v1/intelligence.py` — call services directly
5. Delete all `app/agents/` files (~80 files)
6. Delete `app/autonomous/agents/` files
7. Delete `app/deerflow/` files
8. Delete `app/mcp/` files
9. Delete `app/security/pqc/` files
10. Delete `app/evals/` files
11. Update imports throughout codebase
12. Run tests, fix breakage

### Week 2: Resource Optimization
1. Create new `deploy/oracle/docker-compose.yml`
2. Modify `app/worker.py` with scheduler integration
3. Create `app/services/fl_server.py` (Flower integration)
4. Set up ClickHouse on Oracle deployment
5. Set up Prometheus + Grafana
6. Test resource usage under load

### Week 3: FL Consolidation + API Cleanup
1. Create `app/services/fl_service.py` (consolidated)
2. Create `app/api/v1/fl.py` (unified FL API)
3. Delete old FL files
4. Consolidate API routes (remove duplicates)
5. Update `requirements.txt`
6. Full integration testing
7. Deploy to Oracle free tier

---

## 6. EXPECTED OUTCOMES

### Performance

| Metric | Before | After |
|---|---|---|
| Startup time | 30-60s | 3-5s |
| Memory (idle) | 3-4GB | 400-600MB |
| Memory (under load) | 6-8GB | 1.5-2GB |
| Python files | 488 | 335 |
| Lines of code | 197,496 | ~137,734 |
| Agent classes | 33+ | 0 |
| API endpoints | 200+ | ~80 |

### Resource Fit

| Component | RAM | CPU |
|---|---|---|
| PostgreSQL | 1.5GB | 0.5 |
| Redis | 256MB | 0.25 |
| ClickHouse | 1GB | 0.25 |
| FastAPI App | 512MB | 0.5 |
| Worker | 512MB | 0.25 |
| Nginx | 64MB | 0.1 |
| Prometheus | 256MB | 0.1 |
| Grafana | 128MB | 0.05 |
| **Total** | **4.3GB** | **2.0** |
| **Free Tier** | **12GB** | **2.0** |
| **Headroom** | **7.7GB** | **0** |

---

## 7. BUYER DASHBOARD & B2B API

### 7.1 Overview

The Buyer Dashboard is the revenue engine. It exposes pre-computed intelligence products as a paid B2B API with authentication, rate limiting, report generation, and billing. Buyers are organizations (FMCG companies, banks, government agencies, NGOs) that subscribe to intelligence products.

### 7.2 Buyer Authentication

Buyer auth is separate from worker auth. Workers use device-bound JWTs with OTP; buyers use API key + OAuth2 client credentials.

**Auth Flow:**

```
Buyer Org ──[register]──► Admin approves ──► API key + secret issued
Buyer App ──[POST /api/v1/buyer/auth/token]──► OAuth2 token (24h TTL)
Buyer App ──[GET /api/v1/buyer/soko-pulse?Bearer token]──► Intelligence API
```

**Implementation:**

```python
# app/api/v1/buyer/auth.py

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import UTC, datetime, timedelta
import hashlib
import secrets
import jwt

from app.db.database import get_db
from app.models.buyer import BuyerOrg, BuyerAPIKey, BuyerSubscription
from app.config import get_settings

router = APIRouter(prefix="/buyer/auth", tags=["Buyer Auth"])
settings = get_settings()

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/buyer/auth/token")


def _hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/token")
async def get_token(
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
):
    """Exchange API key for OAuth2 bearer token (24h TTL)."""
    if not api_key:
        raise HTTPException(401, "X-API-Key header required")
    
    key_hash = _hash_api_key(api_key)
    result = await db.execute(
        select(BuyerAPIKey).where(
            BuyerAPIKey.key_hash == key_hash,
            BuyerAPIKey.is_active == True,
        )
    )
    api_key_obj = result.scalar_one_or_none()
    if not api_key_obj:
        raise HTTPException(401, "Invalid API key")
    
    # Check subscription
    result = await db.execute(
        select(BuyerSubscription).where(
            BuyerSubscription.buyer_id == api_key_obj.buyer_id,
            BuyerSubscription.status == "active",
            BuyerSubscription.expires_at > datetime.now(UTC),
        )
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(403, "No active subscription")
    
    # Generate JWT
    token = jwt.encode(
        {
            "sub": str(api_key_obj.buyer_id),
            "org": api_key_obj.org_name,
            "tier": sub.tier,
            "products": sub.products,  # ["soko-pulse", "alama-score", ...]
            "exp": datetime.now(UTC) + timedelta(hours=24),
            "iss": "angavu-buyer",
        },
        settings.BUYER_JWT_SECRET,
        algorithm="HS256",
    )
    
    # Update last used
    api_key_obj.last_used_at = datetime.now(UTC)
    await db.flush()
    
    return {"access_token": token, "token_type": "bearer", "expires_in": 86400}


async def get_current_buyer(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Validate buyer JWT and return claims."""
    try:
        claims = jwt.decode(token, settings.BUYER_JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    
    return claims


async def require_product(product: str):
    """Dependency factory — checks buyer has access to a product."""
    async def _check(claims: dict = Depends(get_current_buyer)):
        if product not in claims.get("products", []):
            raise HTTPException(403, f"Not subscribed to {product}")
        return claims
    return _check
```

**Buyer Models:**

```python
# app/models/buyer.py

from sqlalchemy import Column, String, DateTime, Boolean, Integer, JSON, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.db.database import Base
import enum


class BuyerTier(str, enum.Enum):
    STARTER = "starter"       # $99/mo — 1000 queries/day, 2 products
    BUSINESS = "business"     # $499/mo — 10000 queries/day, 4 products
    ENTERPRISE = "enterprise" # $2499/mo — unlimited queries, all products


class BuyerOrg(Base):
    __tablename__ = "buyer_organizations"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    industry = Column(String(100))  # fmcg, banking, government, ngo, research
    country = Column(String(2))
    contact_email = Column(String(255), nullable=False)
    contact_name = Column(String(255))
    created_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    metadata_ = Column("metadata", JSON, default=dict)
    
    api_keys = relationship("BuyerAPIKey", back_populates="buyer")
    subscriptions = relationship("BuyerSubscription", back_populates="buyer")
    usage_records = relationship("BuyerUsageRecord", back_populates="buyer")


class BuyerAPIKey(Base):
    __tablename__ = "buyer_api_keys"
    
    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey("buyer_organizations.id"), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False)  # SHA-256 of raw key
    key_prefix = Column(String(8), nullable=False)  # First 8 chars for identification
    org_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    
    buyer = relationship("BuyerOrg", back_populates="api_keys")


class BuyerSubscription(Base):
    __tablename__ = "buyer_subscriptions"
    
    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey("buyer_organizations.id"), nullable=False)
    tier = Column(Enum(BuyerTier), nullable=False)
    products = Column(JSON, nullable=False)  # ["soko-pulse", "alama-score"]
    status = Column(String(20), default="active")  # active, suspended, cancelled
    starts_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    stripe_subscription_id = Column(String(255))
    
    buyer = relationship("BuyerOrg", back_populates="subscriptions")


class BuyerUsageRecord(Base):
    __tablename__ = "buyer_usage_records"
    
    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey("buyer_organizations.id"), nullable=False)
    product = Column(String(50), nullable=False)
    endpoint = Column(String(255))
    query_params = Column(JSON)
    response_size_bytes = Column(Integer)
    latency_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True))
    
    buyer = relationship("BuyerOrg", back_populates="usage_records")
```

### 7.3 Buyer API Endpoints

All buyer endpoints are under `/api/v1/buyer/` and require a valid buyer JWT with the appropriate product subscription.

#### 7.3.1 Soko Pulse — FMCG Demand Forecasting

```python
# app/api/v1/buyer/soko_pulse.py

router = APIRouter(prefix="/buyer/soko-pulse", tags=["Buyer — Soko Pulse"])


@router.get("")
async def get_soko_pulse(
    product_category: str = Query(..., description="Product category (e.g., cooking_oil, soap, flour)"),
    region: str = Query(..., description="Geohash-5 region code"),
    period_start: date = Query(...),
    period_end: date = Query(...),
    include_elasticity: bool = Query(False, description="Include price elasticity analysis"),
    include_cross_border: bool = Query(False, description="Include cross-border trade signals"),
    claims: dict = Depends(require_product("soko-pulse")),
    db: AsyncSession = Depends(get_db),
):
    """
    FMCG demand forecasting for a product category and region.
    
    Returns:
    - demand_forecast: 7/14/30-day demand predictions with confidence intervals
    - trend: upward/downward/stable with magnitude
    - seasonality: weekly/monthly patterns detected
    - consumer_surplus: estimated price sensitivity (if include_elasticity)
    - cross_border: trade flow indicators (if include_cross_border)
    
    Pricing: $0.10/query (starter), $0.05/query (business), $0.02/query (enterprise)
    """
    # Rate limit check
    await check_rate_limit(claims["sub"], "soko-pulse", claims["tier"])
    
    # Fetch pre-computed product
    result = await db.execute(
        select(IntelligenceProduct).where(
            IntelligenceProduct.product_type == "soko_pulse",
            IntelligenceProduct.region == region,
            IntelligenceProduct.category == product_category,
            IntelligenceProduct.period_start <= period_start,
            IntelligenceProduct.period_end >= period_end,
            IntelligenceProduct.status == "ready",
        ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "No data available for this region/category. Try a broader region.")
    
    response = {
        "product": "soko-pulse",
        "region": region,
        "category": product_category,
        "period": {"start": str(period_start), "end": str(period_end)},
        "generated_at": product.created_at.isoformat(),
        "demand_forecast": product.data["demand_forecast"],
        "trend": product.data["trend"],
        "seasonality": product.data["seasonality"],
    }
    
    if include_elasticity:
        response["elasticity"] = product.data.get("elasticity", {})
    if include_cross_border:
        response["cross_border"] = product.data.get("cross_border", {})
    
    # Log usage for billing
    await log_usage(db, claims["sub"], "soko-pulse", region, product_category)
    
    return response


@router.get("/regions")
async def list_available_regions(
    product_category: str = Query(...),
    claims: dict = Depends(require_product("soko-pulse")),
    db: AsyncSession = Depends(get_db),
):
    """List regions with available Soko Pulse data for a category."""
    result = await db.execute(
        select(IntelligenceProduct.region).where(
            IntelligenceProduct.product_type == "soko_pulse",
            IntelligenceProduct.category == product_category,
            IntelligenceProduct.status == "ready",
        ).distinct()
    )
    return {"regions": [row[0] for row in result.all()]}


@router.get("/timeseries")
async def get_soko_pulse_timeseries(
    product_category: str = Query(...),
    region: str = Query(...),
    months: int = Query(6, ge=1, le=24, description="Months of history"),
    claims: dict = Depends(require_product("soko-pulse")),
    db: AsyncSession = Depends(get_db),
):
    """Get historical demand time series for trend analysis."""
    # Query ClickHouse for time-series data
    ch = get_clickhouse_client()
    rows = ch.execute(
        """
        SELECT 
            toStartOfWeek(transaction_date) AS week,
            sum(amount) AS total_sales,
            count() AS transaction_count,
            uniq(worker_id_hash) AS active_workers
        FROM transactions_analytics
        WHERE geohash_5 = %(region)s
          AND product_category = %(category)s
          AND transaction_date >= today() - INTERVAL %(months)s MONTH
        GROUP BY week
        ORDER BY week
        """,
        {"region": region, "category": product_category, "months": months},
    )
    return {
        "product": "soko-pulse",
        "region": region,
        "category": product_category,
        "timeseries": [dict(row) for row in rows],
    }
```

#### 7.3.2 Alama Score — Credit Scoring

```python
# app/api/v1/buyer/alama_score.py

router = APIRouter(prefix="/buyer/alama-score", tags=["Buyer — Alama Score"])


@router.get("/{worker_id_hash}")
async def get_alama_score(
    worker_id_hash: str,
    include_factors: bool = Query(False, description="Include scoring factor breakdown"),
    include_history: bool = Query(False, description="Include 6-month score history"),
    claims: dict = Depends(require_product("alama-score")),
    db: AsyncSession = Depends(get_db),
):
    """
    Credit score for a worker (privacy-preserving: uses hashed ID, no PII).
    
    Returns:
    - score: 300-850 (FICO-like scale)
    - risk_band: A/B/C/D/E
    - confidence: model confidence (0-1)
    - factors: scoring factor breakdown (if requested)
    - history: 6-month score trajectory (if requested)
    
    Pricing: $0.05/query (starter), $0.03/query (business), $0.01/query (enterprise)
    """
    await check_rate_limit(claims["sub"], "alama-score", claims["tier"])
    
    # Validate hash format
    if not re.match(r'^[a-f0-9]{64}$', worker_id_hash):
        raise HTTPException(400, "Invalid worker_id_hash format")
    
    result = await db.execute(
        select(AlamaScore).where(
            AlamaScore.worker_id_hash == worker_id_hash,
        ).order_by(AlamaScore.created_at.desc()).limit(1)
    )
    score = result.scalar_one_or_none()
    if not score:
        raise HTTPException(404, "Insufficient data for this worker")
    
    response = {
        "product": "alama-score",
        "worker_id_hash": worker_id_hash,
        "score": score.score,
        "risk_band": score.risk_band,
        "confidence": score.confidence,
        "generated_at": score.created_at.isoformat(),
    }
    
    if include_factors:
        response["factors"] = {
            "transaction_volume": score.factor_transaction_volume,
            "consistency": score.factor_consistency,
            "diversity": score.factor_diversity,
            "growth_trend": score.factor_growth_trend,
            "peer_comparison": score.factor_peer_comparison,
        }
    
    if include_history:
        result = await db.execute(
            select(AlamaScore).where(
                AlamaScore.worker_id_hash == worker_id_hash,
            ).order_by(AlamaScore.created_at.desc()).limit(6)
        )
        history = result.scalars().all()
        response["history"] = [
            {"score": s.score, "date": s.created_at.isoformat(), "band": s.risk_band}
            for s in history
        ]
    
    await log_usage(db, claims["sub"], "alama-score", worker_id_hash=worker_id_hash)
    return response


@router.post("/batch")
async def batch_alama_scores(
    request: AlamaBatchRequest,
    claims: dict = Depends(require_product("alama-score")),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch credit scoring — up to 100 workers per request.
    Returns scores for all valid worker hashes.
    """
    if len(request.worker_hashes) > 100:
        raise HTTPException(400, "Maximum 100 workers per batch")
    
    await check_rate_limit(claims["sub"], "alama-score", claims["tier"], count=len(request.worker_hashes))
    
    result = await db.execute(
        select(AlamaScore).where(
            AlamaScore.worker_id_hash.in_(request.worker_hashes),
        ).distinct(AlamaScore.worker_id_hash).order_by(
            AlamaScore.worker_id_hash,
            AlamaScore.created_at.desc(),
        )
    )
    scores = {s.worker_id_hash: s for s in result.scalars().all()}
    
    response = {"product": "alama-score", "scores": {}, "missing": []}
    for h in request.worker_hashes:
        if h in scores:
            s = scores[h]
            response["scores"][h] = {"score": s.score, "band": s.risk_band, "confidence": s.confidence}
        else:
            response["missing"].append(h)
    
    await log_usage(db, claims["sub"], "alama-score", count=len(request.worker_hashes))
    return response
```

#### 7.3.3 Angavu Pulse — MSME Activity Index

```python
# app/api/v1/buyer/angavu_pulse.py

router = APIRouter(prefix="/buyer/angavu-pulse", tags=["Buyer — Angavu Pulse"])


@router.get("")
async def get_angavu_pulse(
    region: str = Query(..., description="Geohash-5 region or 'national' for country-level"),
    sector: str = Query(None, description="Business sector filter"),
    period: str = Query("weekly", description="weekly/monthly/quarterly"),
    claims: dict = Depends(require_product("angavu-pulse")),
    db: AsyncSession = Depends(get_db),
):
    """
    MSME economic activity index for a region.
    
    Returns:
    - activity_index: 0-100 scale (50 = baseline)
    - active_msme_count: estimated MSMEs in region
    - transaction_velocity: avg transactions per MSME per week
    - sector_breakdown: activity by business sector
    - growth_trajectory: trend direction and magnitude
    - employment_signal: estimated employment activity
    
    Pricing: $500/mo (starter), $2000/mo (business), $5000/mo (enterprise)
    """
    await check_rate_limit(claims["sub"], "angavu-pulse", claims["tier"])
    
    result = await db.execute(
        select(IntelligenceProduct).where(
            IntelligenceProduct.product_type == "angavu_pulse",
            IntelligenceProduct.region == region,
            IntelligenceProduct.status == "ready",
        ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "No Angavu Pulse data for this region")
    
    response = {
        "product": "angavu-pulse",
        "region": region,
        "period": period,
        "generated_at": product.created_at.isoformat(),
        "activity_index": product.data["activity_index"],
        "active_msme_count": product.data["active_msme_count"],
        "transaction_velocity": product.data["transaction_velocity"],
        "sector_breakdown": product.data.get("sector_breakdown", {}),
        "growth_trajectory": product.data["growth_trajectory"],
        "employment_signal": product.data.get("employment_signal"),
    }
    
    if sector:
        response["sector_detail"] = product.data.get("sector_breakdown", {}).get(sector)
    
    await log_usage(db, claims["sub"], "angavu-pulse", region=region)
    return response


@router.get("/compare")
async def compare_regions(
    regions: str = Query(..., description="Comma-separated geohash-5 codes, max 10"),
    sector: str = Query(None),
    claims: dict = Depends(require_product("angavu-pulse")),
    db: AsyncSession = Depends(get_db),
):
    """Compare MSME activity across multiple regions side by side."""
    region_list = [r.strip() for r in regions.split(",")][:10]
    if len(region_list) < 2:
        raise HTTPException(400, "At least 2 regions required for comparison")
    
    results = []
    for r in region_list:
        result = await db.execute(
            select(IntelligenceProduct).where(
                IntelligenceProduct.product_type == "angavu_pulse",
                IntelligenceProduct.region == r,
                IntelligenceProduct.status == "ready",
            ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
        )
        product = result.scalar_one_or_none()
        if product:
            results.append({
                "region": r,
                "activity_index": product.data["activity_index"],
                "active_msme_count": product.data["active_msme_count"],
                "growth": product.data["growth_trajectory"],
            })
    
    return {"product": "angavu-pulse", "comparison": results}
```

#### 7.3.4 Jamii Insights — Financial Inclusion

```python
# app/api/v1/buyer/jamii_insights.py

router = APIRouter(prefix="/buyer/jamii-insights", tags=["Buyer — Jamii Insights"])


@router.get("")
async def get_jamii_insights(
    region: str = Query(..., description="Geohash-5 or 'national'"),
    dimension: str = Query(None, description="Focus: savings, credit_access, digital_payments, insurance"),
    claims: dict = Depends(require_product("jamii-insights")),
    db: AsyncSession = Depends(get_db),
):
    """
    Financial inclusion metrics for a region.
    
    Returns:
    - inclusion_index: 0-100 composite score
    - dimensions: savings, credit_access, digital_payments, insurance penetration
    - underserved_segments: demographics with lowest inclusion
    - opportunity_score: market opportunity for financial products
    - gap_analysis: where financial services are missing
    
    Pricing: $100/report (starter), $500/mo (business), $2000/mo (enterprise)
    """
    await check_rate_limit(claims["sub"], "jamii-insights", claims["tier"])
    
    result = await db.execute(
        select(IntelligenceProduct).where(
            IntelligenceProduct.product_type == "jamii_insights",
            IntelligenceProduct.region == region,
            IntelligenceProduct.status == "ready",
        ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "No Jamii Insights data for this region")
    
    response = {
        "product": "jamii-insights",
        "region": region,
        "generated_at": product.created_at.isoformat(),
        "inclusion_index": product.data["inclusion_index"],
        "dimensions": product.data["dimensions"],
        "underserved_segments": product.data.get("underserved_segments", []),
        "opportunity_score": product.data.get("opportunity_score"),
        "gap_analysis": product.data.get("gap_analysis", {}),
    }
    
    if dimension:
        response["dimension_detail"] = product.data.get("dimensions", {}).get(dimension)
    
    await log_usage(db, claims["sub"], "jamii-insights", region=region)
    return response
```

#### 7.3.5 Distribution Gap — FMCG Coverage Analysis

```python
# app/api/v1/buyer/distribution_gap.py

router = APIRouter(prefix="/buyer/distribution-gap", tags=["Buyer — Distribution Gap"])


@router.get("")
async def get_distribution_gap(
    product_category: str = Query(..., description="Product category"),
    region: str = Query(..., description="Geohash-5 region"),
    claims: dict = Depends(require_product("distribution-gap")),
    db: AsyncSession = Depends(get_db),
):
    """
    FMCG distribution coverage analysis — where products are NOT reaching.
    
    Returns:
    - coverage_pct: % of sub-regions with active distribution
    - gap_areas: list of sub-regions with zero/low distribution
    - estimated_unserved_population: people in gap areas
    - nearest_distribution_points: closest active distributors
    - opportunity_value: estimated revenue opportunity in gap areas
    
    Pricing: $0.25/query (starter), $0.15/query (business), $0.08/query (enterprise)
    """
    await check_rate_limit(claims["sub"], "distribution-gap", claims["tier"])
    
    result = await db.execute(
        select(IntelligenceProduct).where(
            IntelligenceProduct.product_type == "distribution_gap",
            IntelligenceProduct.region == region,
            IntelligenceProduct.category == product_category,
            IntelligenceProduct.status == "ready",
        ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "No distribution gap data for this region/category")
    
    response = {
        "product": "distribution-gap",
        "region": region,
        "category": product_category,
        "generated_at": product.created_at.isoformat(),
        "coverage_pct": product.data["coverage_pct"],
        "gap_areas": product.data["gap_areas"],
        "estimated_unserved_population": product.data.get("estimated_unserved_population"),
        "nearest_distribution_points": product.data.get("nearest_distribution_points", []),
        "opportunity_value": product.data.get("opportunity_value"),
    }
    
    await log_usage(db, claims["sub"], "distribution-gap", region=region, category=product_category)
    return response


@router.get("/heatmap")
async def get_distribution_heatmap(
    product_category: str = Query(...),
    region: str = Query(..., description="Parent geohash (4 or 5 chars)"),
    claims: dict = Depends(require_product("distribution-gap")),
    db: AsyncSession = Depends(get_db),
):
    """Get distribution density heatmap data for visualization."""
    ch = get_clickhouse_client()
    rows = ch.execute(
        """
        SELECT 
            geohash_5 AS cell,
            count() AS transaction_count,
            uniq(worker_id_hash) AS active_distributors,
            sum(amount) AS total_volume
        FROM transactions_analytics
        WHERE geohash_5 LIKE %(prefix)s
          AND product_category = %(category)s
          AND transaction_date >= today() - INTERVAL 30 DAY
        GROUP BY geohash_5
        ORDER BY transaction_count DESC
        """,
        {"prefix": region + "%", "category": product_category},
    )
    return {
        "product": "distribution-gap",
        "region": region,
        "category": product_category,
        "heatmap": [dict(row) for row in rows],
    }
```

#### 7.3.6 Tax Base — Tax Revenue Estimation

```python
# app/api/v1/buyer/tax_base.py

router = APIRouter(prefix="/buyer/tax-base", tags=["Buyer — Tax Base"])


@router.get("")
async def get_tax_base(
    region: str = Query(..., description="Geohash-5 or 'national'"),
    period: str = Query("monthly", description="monthly/quarterly/annual"),
    sector: str = Query(None, description="Business sector filter"),
    claims: dict = Depends(require_product("tax-base")),
    db: AsyncSession = Depends(get_db),
):
    """
    Tax revenue estimation for a region based on economic activity.
    
    Returns:
    - estimated_tax_base: total taxable economic activity (USD)
    - estimated_revenue: projected tax collection at current rates
    - formalization_rate: % of MSMEs operating formally
    - collection_efficiency: actual vs potential collection
    - sector_breakdown: tax base by sector
    - growth_trend: YoY tax base trajectory
    
    Pricing: $200/report (starter), $1000/mo (business), $5000/mo (enterprise)
    """
    await check_rate_limit(claims["sub"], "tax-base", claims["tier"])
    
    result = await db.execute(
        select(IntelligenceProduct).where(
            IntelligenceProduct.product_type == "tax_base",
            IntelligenceProduct.region == region,
            IntelligenceProduct.status == "ready",
        ).order_by(IntelligenceProduct.created_at.desc()).limit(1)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "No tax base data for this region")
    
    response = {
        "product": "tax-base",
        "region": region,
        "period": period,
        "generated_at": product.created_at.isoformat(),
        "estimated_tax_base": product.data["estimated_tax_base"],
        "estimated_revenue": product.data["estimated_revenue"],
        "formalization_rate": product.data.get("formalization_rate"),
        "collection_efficiency": product.data.get("collection_efficiency"),
        "sector_breakdown": product.data.get("sector_breakdown", {}),
        "growth_trend": product.data.get("growth_trend"),
    }
    
    if sector:
        response["sector_detail"] = product.data.get("sector_breakdown", {}).get(sector)
    
    await log_usage(db, claims["sub"], "tax-base", region=region)
    return response
```

### 7.4 Rate Limiting (B2B)

Rate limits are per-buyer, per-product, tier-based. Uses Redis sliding window counters.

```python
# app/services/buyer_rate_limit.py

import time
from app.infrastructure.redis_cache import get_cache

TIER_LIMITS = {
    "starter": {
        "soko-pulse": {"daily": 1000, "per_second": 5},
        "alama-score": {"daily": 500, "per_second": 3},
        "angavu-pulse": {"daily": 100, "per_second": 2},
        "jamii-insights": {"daily": 100, "per_second": 2},
        "distribution-gap": {"daily": 500, "per_second": 3},
        "tax-base": {"daily": 50, "per_second": 1},
    },
    "business": {
        "soko-pulse": {"daily": 10000, "per_second": 20},
        "alama-score": {"daily": 5000, "per_second": 15},
        "angavu-pulse": {"daily": 1000, "per_second": 10},
        "jamii-insights": {"daily": 1000, "per_second": 10},
        "distribution-gap": {"daily": 5000, "per_second": 15},
        "tax-base": {"daily": 500, "per_second": 5},
    },
    "enterprise": {
        "soko-pulse": {"daily": 100000, "per_second": 100},
        "alama-score": {"daily": 50000, "per_second": 50},
        "angavu-pulse": {"daily": 10000, "per_second": 50},
        "jamii-insights": {"daily": 10000, "per_second": 50},
        "distribution-gap": {"daily": 50000, "per_second": 50},
        "tax-base": {"daily": 5000, "per_second": 20},
    },
}


class BuyerRateLimiter:
    """Sliding window rate limiter for buyer API."""
    
    def __init__(self):
        self.cache = get_cache()
    
    async def check(self, buyer_id: str, product: str, tier: str, count: int = 1) -> None:
        """Check rate limit. Raises 429 if exceeded."""
        limits = TIER_LIMITS.get(tier, {}).get(product)
        if not limits:
            raise HTTPException(403, "Product not available on your tier")
        
        # Per-second check (sliding window)
        now = time.time()
        second_key = f"rl:{buyer_id}:{product}:sec:{int(now)}"
        current = await self.cache.incr(second_key)
        if current == 1:
            await self.cache.expire(second_key, 2)
        if current > limits["per_second"] * count:
            raise HTTPException(
                429,
                detail={"error": "Rate limit exceeded", "limit": limits["per_second"], "window": "per_second"},
                headers={"Retry-After": "1"},
            )
        
        # Daily check
        day_key = f"rl:{buyer_id}:{product}:day:{datetime.now(UTC).strftime('%Y%m%d')}"
        daily_count = await self.cache.incr(day_key)
        if daily_count == 1:
            await self.cache.expire(day_key, 86400)
        if daily_count > limits["daily"]:
            raise HTTPException(
                429,
                detail={"error": "Daily limit exceeded", "limit": limits["daily"], "window": "daily"},
                headers={"Retry-After": str(86400 - int(now) % 86400)},
            )


rate_limiter = BuyerRateLimiter()


async def check_rate_limit(buyer_id: str, product: str, tier: str, count: int = 1):
    await rate_limiter.check(buyer_id, product, tier, count)
```

**Rate limit headers on every response:**

```python
# app/api/v1/buyer/middleware.py

from starlette.middleware.base import BaseHTTPMiddleware

class BuyerRateLimitMiddleware(BaseHTTPMiddleware):
    """Add rate limit headers to all buyer API responses."""
    
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/buyer/"):
            # Headers added by the rate limiter via request state
            if hasattr(request.state, "rate_limit_remaining"):
                response.headers["X-RateLimit-Remaining"] = str(request.state.rate_limit_remaining)
                response.headers["X-RateLimit-Limit"] = str(request.state.rate_limit_limit)
                response.headers["X-RateLimit-Reset"] = str(request.state.rate_limit_reset)
        return response
```

### 7.5 Report Generation (PDF/HTML)

Buyers can request generated reports as PDF or HTML, served asynchronously.

```python
# app/api/v1/buyer/reports.py

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse
from enum import Enum
import io

router = APIRouter(prefix="/buyer/reports", tags=["Buyer — Reports"])


class ReportFormat(str, Enum):
    PDF = "pdf"
    HTML = "html"


@router.post("/{product}")
async def generate_report(
    product: str,
    request: ReportRequest,
    format: ReportFormat = Query(ReportFormat.PDF),
    claims: dict = Depends(get_current_buyer),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a branded report for a specific intelligence product.
    
    Returns a report_id for polling, or inline HTML.
    PDF generation is async (poll /reports/{report_id}/status).
    HTML is returned inline.
    """
    if product not in claims.get("products", []):
        raise HTTPException(403, f"Not subscribed to {product}")
    
    # Fetch intelligence data
    intel_data = await _fetch_intelligence(db, product, request)
    
    if format == ReportFormat.HTML:
        html = _render_report_html(product, intel_data, request)
        return HTMLResponse(content=html)
    
    # PDF: async generation
    report_id = str(uuid.uuid4())
    report = BuyerReport(
        id=report_id,
        buyer_id=claims["sub"],
        product=product,
        format=format,
        status="pending",
        request_params=request.dict(),
    )
    db.add(report)
    await db.flush()
    
    background_tasks.add_task(_generate_pdf_report, report_id, product, intel_data)
    
    return {"report_id": report_id, "status": "pending", "poll_url": f"/api/v1/buyer/reports/{report_id}/status"}


@router.get("/{report_id}/status")
async def report_status(
    report_id: str,
    claims: dict = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    """Poll report generation status."""
    result = await db.execute(
        select(BuyerReport).where(
            BuyerReport.id == report_id,
            BuyerReport.buyer_id == claims["sub"],
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")
    
    if report.status == "ready":
        return {"status": "ready", "download_url": f"/api/v1/buyer/reports/{report_id}/download"}
    
    return {"status": report.status}


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    claims: dict = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    """Download a generated PDF report."""
    result = await db.execute(
        select(BuyerReport).where(
            BuyerReport.id == report_id,
            BuyerReport.buyer_id == claims["sub"],
            BuyerReport.status == "ready",
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found or not ready")
    
    return StreamingResponse(
        io.BytesIO(report.pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{report.product}_{report_id}.pdf"'},
    )


def _render_report_html(product: str, data: dict, request) -> str:
    """Render intelligence data as HTML report."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("app/templates/reports"))
    template = env.get_template(f"{product}.html")
    return template.render(
        data=data,
        org_name=request.org_name,
        generated_at=datetime.now(UTC).isoformat(),
        branding=request.branding or {},
    )


async def _generate_pdf_report(report_id: str, product: str, data: dict):
    """Background task: generate PDF from HTML."""
    from weasyprint import HTML
    from app.db.database import async_session_factory
    
    html = _render_report_html(product, data, SimpleNamespace(branding={}, org_name=""))
    pdf_bytes = HTML(string=html).write_pdf()
    
    async with async_session_factory() as db:
        result = await db.execute(select(BuyerReport).where(BuyerReport.id == report_id))
        report = result.scalar_one()
        report.pdf_bytes = pdf_bytes
        report.status = "ready"
        await db.commit()
```

**Report Templates:**

```
app/templates/reports/
├── base.html              # Shared layout (logo, header, footer)
├── soko_pulse.html        # FMCG demand forecast report
├── alama_score.html       # Credit scoring report
├── angavu_pulse.html      # MSME activity report
├── jamii_insights.html    # Financial inclusion report
├── distribution_gap.html  # Distribution coverage report
└── tax_base.html          # Tax revenue report
```

### 7.6 Billing & Payments Integration

Stripe-based billing with usage metering.

```python
# app/services/billing.py

import stripe
from app.config import get_settings
from app.models.buyer import BuyerOrg, BuyerSubscription, BuyerUsageRecord

settings = get_settings()
stripe.api_key = settings.STRIPE_SECRET_KEY


TIER_PRICES = {
    "starter": {
        "monthly": 99_00,       # $99.00 in cents
        "soko-pulse": 10,       # $0.10 per query
        "alama-score": 5,       # $0.05 per query
        "distribution-gap": 25, # $0.25 per query
    },
    "business": {
        "monthly": 499_00,
        "soko-pulse": 5,
        "alama-score": 3,
        "distribution-gap": 15,
    },
    "enterprise": {
        "monthly": 2499_00,
        "soko-pulse": 2,
        "alama-score": 1,
        "distribution-gap": 8,
    },
}

REPORT_PRODUCTS = {
    "angavu-pulse": {"starter": 500_00, "business": 2000_00, "enterprise": 5000_00},
    "jamii-insights": {"starter": 100_00, "business": 500_00, "enterprise": 2000_00},
    "tax-base": {"starter": 200_00, "business": 1000_00, "enterprise": 5000_00},
}


class BillingService:
    """Stripe billing for buyer subscriptions and usage."""
    
    async def create_buyer_subscription(
        self, buyer: BuyerOrg, tier: str, products: list[str]
    ) -> BuyerSubscription:
        """Create Stripe customer and subscription."""
        # Create Stripe customer
        customer = stripe.Customer.create(
            name=buyer.name,
            email=buyer.contact_email,
            metadata={"buyer_id": str(buyer.id), "industry": buyer.industry},
        )
        
        # Create subscription with usage-based pricing
        price_amount = TIER_PRICES[tier]["monthly"]
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": price_amount,
                    "recurring": {"interval": "month"},
                    "product_data": {"name": f"Angavu {tier.title()} Tier"},
                },
            }],
            metadata={"tier": tier, "products": ",".join(products)},
        )
        
        # Store subscription
        sub = BuyerSubscription(
            buyer_id=buyer.id,
            tier=tier,
            products=products,
            status="active",
            starts_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30),
            stripe_subscription_id=subscription.id,
        )
        return sub
    
    async def record_usage(self, buyer_id: int, product: str, count: int = 1):
        """Record usage for metered billing (Stripe Usage Records)."""
        # Find active subscription
        # Report usage to Stripe for metered products
        pass
    
    async def generate_invoice(self, buyer_id: int, period_start: date, period_end: date):
        """Generate detailed invoice with usage breakdown."""
        # Query BuyerUsageRecords for the period
        # Build line items per product
        # Create Stripe invoice
        pass
    
    async def handle_webhook(self, event: dict):
        """Handle Stripe webhooks (payment_intent.succeeded, invoice.paid, etc.)."""
        if event["type"] == "invoice.paid":
            # Extend subscription
            pass
        elif event["type"] == "customer.subscription.deleted":
            # Suspend access
            pass
        elif event["type"] == "invoice.payment_failed":
            # Send notification, grace period
            pass
```

**Stripe Webhook Endpoint:**

```python
# app/api/v1/buyer/webhooks.py

from fastapi import APIRouter, Request, HTTPException
import stripe

router = APIRouter(tags=["Buyer — Webhooks"])


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Invalid webhook")
    
    billing = BillingService()
    await billing.handle_webhook(event)
    return {"received": True}
```

### 7.7 Buyer Dashboard (Admin UI)

A lightweight admin dashboard for buyers to manage their account, view usage, and download reports.

```python
# app/api/v1/buyer/dashboard.py

router = APIRouter(prefix="/buyer/dashboard", tags=["Buyer — Dashboard"])


@router.get("/overview")
async def buyer_overview(
    claims: dict = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    """Buyer dashboard overview — usage, subscription, recent activity."""
    buyer_id = claims["sub"]
    
    # Current subscription
    result = await db.execute(
        select(BuyerSubscription).where(
            BuyerSubscription.buyer_id == buyer_id,
            BuyerSubscription.status == "active",
        ).order_by(BuyerSubscription.expires_at.desc()).limit(1)
    )
    sub = result.scalar_one_or_none()
    
    # Usage this month
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0)
    result = await db.execute(
        select(
            BuyerUsageRecord.product,
            func.count(BuyerUsageRecord.id),
        ).where(
            BuyerUsageRecord.buyer_id == buyer_id,
            BuyerUsageRecord.created_at >= month_start,
        ).group_by(BuyerUsageRecord.product)
    )
    usage = {row[0]: row[1] for row in result.all()}
    
    # Recent reports
    result = await db.execute(
        select(BuyerReport).where(
            BuyerReport.buyer_id == buyer_id,
        ).order_by(BuyerReport.created_at.desc()).limit(10)
    )
    recent_reports = result.scalars().all()
    
    return {
        "organization": claims.get("org"),
        "tier": sub.tier if sub else None,
        "subscription_expires": sub.expires_at.isoformat() if sub else None,
        "products": sub.products if sub else [],
        "usage_this_month": usage,
        "recent_reports": [
            {"id": r.id, "product": r.product, "status": r.status, "created_at": r.created_at.isoformat()}
            for r in recent_reports
        ],
    }


@router.get("/usage")
async def buyer_usage(
    start_date: date = Query(...),
    end_date: date = Query(...),
    claims: dict = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    """Detailed usage breakdown by product and day."""
    result = await db.execute(
        select(
            func.date(BuyerUsageRecord.created_at).label("day"),
            BuyerUsageRecord.product,
            func.count(BuyerUsageRecord.id),
        ).where(
            BuyerUsageRecord.buyer_id == claims["sub"],
            BuyerUsageRecord.created_at >= start_date,
            BuyerUsageRecord.created_at <= end_date,
        ).group_by("day", BuyerUsageRecord.product)
        .order_by("day")
    )
    
    usage_data = {}
    for row in result.all():
        day_str = str(row[0])
        if day_str not in usage_data:
            usage_data[day_str] = {}
        usage_data[day_str][row[1]] = row[2]
    
    return {"usage": usage_data, "period": {"start": str(start_date), "end": str(end_date)}}


@router.get("/api-keys")
async def list_api_keys(
    claims: dict = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    """List API keys (prefix only, never the full key)."""
    result = await db.execute(
        select(BuyerAPIKey).where(
            BuyerAPIKey.buyer_id == claims["sub"],
            BuyerAPIKey.is_active == True,
        )
    )
    keys = result.scalars().all()
    return {
        "keys": [
            {"prefix": k.key_prefix, "created_at": k.created_at.isoformat(), "last_used": k.last_used_at.isoformat() if k.last_used_at else None}
            for k in keys
        ]
    }


@router.post("/api-keys")
async def create_api_key(
    claims: dict = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key. Returns the raw key ONCE."""
    raw_key = f"angavu_{secrets.token_urlsafe(32)}"
    key = BuyerAPIKey(
        buyer_id=claims["sub"],
        key_hash=_hash_api_key(raw_key),
        key_prefix=raw_key[:12],
        org_name=claims.get("org"),
    )
    db.add(key)
    await db.flush()
    return {"api_key": raw_key, "prefix": key.key_prefix, "warning": "Store this key securely. It cannot be retrieved again."}


@router.delete("/api-keys/{key_prefix}")
async def revoke_api_key(
    key_prefix: str,
    claims: dict = Depends(get_current_buyer),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    result = await db.execute(
        select(BuyerAPIKey).where(
            BuyerAPIKey.buyer_id == claims["sub"],
            BuyerAPIKey.key_prefix == key_prefix,
        )
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(404, "API key not found")
    key.is_active = False
    await db.flush()
    return {"revoked": key_prefix}
```

### 7.8 Buyer API Router Registration

```python
# app/api/v1/buyer/__init__.py

from fastapi import APIRouter
from app.api.v1.buyer.auth import router as auth_router
from app.api.v1.buyer.soko_pulse import router as soko_pulse_router
from app.api.v1.buyer.alama_score import router as alama_score_router
from app.api.v1.buyer.angavu_pulse import router as angavu_pulse_router
from app.api.v1.buyer.jamii_insights import router as jamii_insights_router
from app.api.v1.buyer.distribution_gap import router as distribution_gap_router
from app.api.v1.buyer.tax_base import router as tax_base_router
from app.api.v1.buyer.reports import router as reports_router
from app.api.v1.buyer.dashboard import router as dashboard_router
from app.api.v1.buyer.webhooks import router as webhooks_router

buyer_router = APIRouter(prefix="/api/v1/buyer")

buyer_router.include_router(auth_router)
buyer_router.include_router(soko_pulse_router)
buyer_router.include_router(alama_score_router)
buyer_router.include_router(angavu_pulse_router)
buyer_router.include_router(jamii_insights_router)
buyer_router.include_router(distribution_gap_router)
buyer_router.include_router(tax_base_router)
buyer_router.include_router(reports_router)
buyer_router.include_router(dashboard_router)
buyer_router.include_router(webhooks_router)
```

**Register in main app:**

```python
# app/main.py (addition)
from app.api.v1.buyer import buyer_router
app.include_router(buyer_router)
```

### 7.9 Buyer API — Files to Create

| File | Purpose |
|---|---|
| `app/models/buyer.py` | BuyerOrg, BuyerAPIKey, BuyerSubscription, BuyerUsageRecord models |
| `app/api/v1/buyer/__init__.py` | Router registration |
| `app/api/v1/buyer/auth.py` | API key → OAuth2 token exchange |
| `app/api/v1/buyer/soko_pulse.py` | FMCG demand forecasting endpoints |
| `app/api/v1/buyer/alama_score.py` | Credit scoring endpoints + batch |
| `app/api/v1/buyer/angavu_pulse.py` | MSME activity index + comparison |
| `app/api/v1/buyer/jamii_insights.py` | Financial inclusion metrics |
| `app/api/v1/buyer/distribution_gap.py` | FMCG coverage + heatmap |
| `app/api/v1/buyer/tax_base.py` | Tax revenue estimation |
| `app/api/v1/buyer/reports.py` | PDF/HTML report generation |
| `app/api/v1/buyer/dashboard.py` | Buyer self-service dashboard |
| `app/api/v1/buyer/webhooks.py` | Stripe webhook handler |
| `app/services/buyer_rate_limit.py` | Per-buyer per-product rate limiting |
| `app/services/billing.py` | Stripe billing integration |
| `app/templates/reports/*.html` | Jinja2 report templates (6 products) |

**Total: 15 new files, ~2,500 lines**

### 7.10 Buyer API — Database Migration

```sql
-- New tables for buyer system

CREATE TABLE buyer_organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    industry VARCHAR(100),
    country VARCHAR(2),
    contact_email VARCHAR(255) NOT NULL,
    contact_name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE buyer_api_keys (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER REFERENCES buyer_organizations(id) NOT NULL,
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    key_prefix VARCHAR(8) NOT NULL,
    org_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ
);
CREATE INDEX idx_buyer_api_keys_hash ON buyer_api_keys(key_hash);

CREATE TABLE buyer_subscriptions (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER REFERENCES buyer_organizations(id) NOT NULL,
    tier VARCHAR(20) NOT NULL,
    products JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    starts_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    stripe_subscription_id VARCHAR(255)
);
CREATE INDEX idx_buyer_subscriptions_buyer ON buyer_subscriptions(buyer_id, status);

CREATE TABLE buyer_usage_records (
    id SERIAL PRIMARY KEY,
    buyer_id INTEGER REFERENCES buyer_organizations(id) NOT NULL,
    product VARCHAR(50) NOT NULL,
    endpoint VARCHAR(255),
    query_params JSONB,
    response_size_bytes INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_buyer_usage_buyer_date ON buyer_usage_records(buyer_id, created_at);
CREATE INDEX idx_buyer_usage_product ON buyer_usage_records(product, created_at);

CREATE TABLE buyer_reports (
    id UUID PRIMARY KEY,
    buyer_id INTEGER REFERENCES buyer_organizations(id) NOT NULL,
    product VARCHAR(50) NOT NULL,
    format VARCHAR(10) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    request_params JSONB,
    pdf_bytes BYTEA,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_buyer_reports_buyer ON buyer_reports(buyer_id, created_at);
```

---

### Revenue Path

The simplified architecture enables:
1. **Soko Pulse API** — FMCG companies pay per query ($0.10-$1.00)
2. **Alama Score API** — Banks/fintech pay per score ($0.05-$0.50)
3. **Angavu Pulse** — Government pays monthly subscription ($500-$5000)
4. **Jamii Insights** — NGOs pay per report ($100-$1000)
5. **Distribution Gap** — FMCG companies pay per analysis ($0.08-$0.25)
6. **Tax Base** — Government/donors pay per report ($200-$5000)
7. **FL Model Access** — Research institutions pay for model access

All revenue goes to scaling: more OCPUs, more RAM, eventually adding llama.cpp for LLM features.

---

## 7. SCALING PLAYBOOK — Decision Tree by Worker Count

**Purpose:** At what worker count do you make each infrastructure decision. No guessing, no premature optimization. Each threshold has concrete triggers, costs, and migration steps.

### 7.0 Monitoring Triggers — When You've Hit the Next Threshold

Before detailing each tier, here are the Prometheus/Grafana alerts that tell you it's time to scale:

| Signal | Metric | Threshold | Indicates |
|---|---|---|---|
| API latency spike | `http_request_duration_seconds{quantile="0.95"}` | > 500ms sustained 15min | App CPU/memory saturated |
| DB connection exhaustion | `pg_stat_activity_count` / `max_connections` | > 80% | Need PgBouncer or more connections |
| Redis memory pressure | `redis_memory_used_bytes / redis_memory_max_bytes` | > 85% | Need more Redis RAM or sharding |
| ClickHouse query slowdown | `clickhouse_query_duration_seconds{quantile="0.95"}` | > 2s | Need partitioning or more CPU |
| Sync queue backlog | `task_queue_depth` (Redis sorted set length) | > 10,000 sustained | Worker process saturated |
| FL aggregation delay | Time from upload to aggregation | > 1 hour | FL aggregator bottlenecked |
| Disk I/O wait | `node_disk_io_time_seconds_total` rate | > 30% of wall time | Storage bottleneck |
| OOM kills | `container_oom_events_total` | > 0 in 1 hour | Hard memory limit hit |

**Rule: Don't scale until you see 2+ of these signals sustained for > 15 minutes.** Transient spikes are normal.

---

### 7.1 Tier 1: 100 Workers — Oracle Free Tier (Current)

**Infrastructure:** As designed in Section 3. Single Oracle instance, **2 OCPUs, 12GB RAM**.

> ⚠️ **CRITICAL UPDATE (June 2026):** Oracle reduced the Always Free Ampere A1 allowance from **4 OCPUs / 24GB RAM** to **2 OCPUs / 12GB RAM**. The architecture in Section 3 was designed for this reduced limit. All resource allocations in §3.1 (4.3GB total) fit within the 12GB envelope with 7.7GB headroom.
>
> **Source:** [InfoQ, July 2026](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/) + Oracle docs confirming 1,500 OCPU hours / 9,000 GB hours per month.

```
┌─────────────────────────────────────────┐
│         Oracle Free Tier                 │
│  ┌─────────┐  ┌───────┐  ┌──────────┐ │
│  │ FastAPI  │  │ PG 16 │  │ClickHouse│ │
│  │ 512MB   │  │ 1.5GB │  │  1GB     │ │
│  └────┬────┘  └───────┘  └──────────┘ │
│       │                                 │
│  ┌────┴────┐  ┌───────┐  ┌──────────┐ │
│  │ Worker  │  │ Redis │  │Prometheus│ │
│  │ 512MB   │  │ 256MB │  │ + Grafana│ │
│  └─────────┘  └───────┘  └──────────┘ │
└─────────────────────────────────────────┘
```

**What works fine:**
- Sync API handles ~50 req/s easily on 0.5 OCPU
- PostgreSQL at 50 max_connections serves 100 workers with headroom
- ClickHouse analytics queries complete in <500ms
- FL aggregation (5-device threshold) completes in minutes
- Redis comfortably holds all cache + queue state

**What might break:**
- If 100 workers all sync simultaneously (e.g., morning rush), API latency spikes to 200-300ms (still acceptable)
- ClickHouse `transactions_analytics` table grows ~30K rows/day — no issue at this scale

**Cost:** $0/month

**Migration required:** None. This is the starting point.

---

### 7.2 Tier 2: 1K Workers — Add PgBouncer + Optimize FL Aggregation

**Trigger signals:**
- `pg_stat_activity_count` > 40 (of 50 max) during peak hours
- API p95 latency > 300ms sustained
- FL aggregation rounds taking > 30 minutes

**What breaks:**
- PostgreSQL `max_connections=50` gets exhausted when sync + intelligence + FL all compete
- FL aggregation processes 500+ gradient updates per round — single-threaded aggregation becomes slow
- ClickHouse `transactions_analytics` hits ~10M rows — queries still fast but INSERT batching matters
- Redis sorted set for task queue grows to 5K+ items — worker polling becomes a bottleneck

**What to add:**

| Component | Change | Why |
|---|---|---|
| **PgBouncer** | Add as sidecar container (16MB RAM, 0.05 CPU) | Connection pooling: 500 app connections → 50 PG connections |
| **FL batch aggregation** | Aggregate in batches of 50, async via task queue | Single-threaded aggregation can't keep up with 1K devices |
| **ClickHouse batch INSERT** | Buffer inserts, flush every 1000 rows or 5s | Reduce INSERT overhead from per-transaction to batched |
| **Redis Streams** | Replace sorted set polling with XREADGROUP | Eliminates polling overhead, true push-based consumption |

**Docker Compose additions:**

```yaml
pgbouncer:
  image: edoburu/pgbouncer:latest
  environment:
    DATABASE_URL: postgres://user:pass@postgres:5432/biashara
    POOL_MODE: transaction
    MAX_CLIENT_CONN: 500
    DEFAULT_POOL_SIZE: 50
    MIN_POOL_SIZE: 10
  deploy:
    resources:
      limits:
        cpus: "0.05"
        memory: 16M
  depends_on:
    - postgres
```

**Config changes:**
- `app/main.py`: Point `DATABASE_URL` to `pgbouncer:6432` instead of `postgres:5432`
- `app/services/fl_service.py`: Change `MIN_UPDATES_FOR_AGGREGATION` from 5 to 50, add batch processing
- `deploy/oracle/docker-compose.yml`: Increase `max_connections` to 100 (PgBouncer handles fan-out)

**Cost delta:** $0 (still free tier, just better resource utilization)

**Migration steps:**
1. Add PgBouncer container to docker-compose (zero downtime — new container)
2. Update app DATABASE_URL to point to PgBouncer
3. Restart app container
4. Deploy FL batch aggregation code update
5. Migrate task queue from sorted sets to Redis Streams (requires worker restart)

**Estimated capacity:** 1K workers generating ~5K transactions/day, ~50 concurrent API requests at peak.

---

### 7.3 Tier 3: 10K Workers — Upgrade Instance + Read Replicas + Partition ClickHouse

**Trigger signals:**
- CPU utilization > 70% sustained across both OCPUs
- PostgreSQL disk > 150GB (of 200GB free tier)
- ClickHouse query p95 > 2s
- Worker backlog > 5K tasks sustained
- API p95 > 500ms

**What breaks:**
- **CPU:** 2 OCPUs maxed out. Sync + intelligence + FL + ClickHouse ETL all compete
- **Disk:** PostgreSQL at 10K workers stores ~500K transactions/day → 180M/year. 200GB fills in ~18 months
- **ClickHouse:** `transactions_analytics` at ~100M rows — full table scans for analytics become slow
- **Write throughput:** PostgreSQL write IOPS saturated with sync writes + intelligence reads

**Oracle Ampere A1 Pricing (verified July 2026):**
- On-demand: **$0.01/OCPU/hour** (source: [Oracle Price List](https://www.oracle.com/cloud/price-list/))
- 4 OCPUs × 730 hrs/month = **$29.20/month**
- 8 OCPUs × 730 hrs/month = **$58.40/month**
- Memory: included with OCPU (6GB per OCPU on A1.Flex)
- Paid tenancies also get 3,000 OCPU hours + 18,000 GB hours free (effectively ~4 OCPUs free if running 24/7)

**What to add:**

| Component | Change | Cost |
|---|---|---|
| **Oracle A1.Flex upgrade** | 4 OCPUs, 24GB RAM | **~$29/month** (or $0 within paid free allowance of 3,000 OCPU hrs/mo) |
| **PG read replica** | Async replica for intelligence/analytics queries | $0 (same instance, separate PG process) |
| **ClickHouse partitioning** | Partition `transactions_analytics` by month, TTL 2 years | $0 (schema change only) |
| **Separate ClickHouse node** | Dedicated ClickHouse on second ARM instance | **~$29/month** (4 OCPUs) |
| **Redis upgrade** | 512MB → 1GB, enable Redis Cluster mode | $0 (config change on larger instance) |

> **Note on paid free allowance:** Oracle paid tenancies (PAYG) receive 3,000 OCPU hours/month free for Ampere A1. Running a 4-OCPU instance 24/7 uses 2,920 hours — within the free allowance. This means **the first upgrade from 2→4 OCPUs may still be $0** if you convert to PAYG. The 8-OCPU instance uses 5,840 hours, so you'd pay for ~2,840 excess hours = **~$28.40/month**. Check your tenancy's current usage in the OCI console before paying.

**PostgreSQL read replica setup:**

```yaml
postgres-primary:
  image: postgres:16-alpine
  command: >
    postgres
    -c shared_buffers=1GB
    -c effective_cache_size=4GB
    -c work_mem=8MB
    -c max_connections=100
    -c wal_level=replica
    -c max_wal_senders=3
    -c max_replication_slots=3
  deploy:
    resources:
      limits:
        cpus: "1.0"
        memory: 4G

postgres-replica:
  image: postgres:16-alpine
  command: >
    postgres
    -c shared_buffers=512MB
    -c effective_cache_size=2GB
    -c hot_standby=on
    -c max_connections=50
  environment:
    PRIMARY_HOST: postgres-primary
  deploy:
    resources:
      limits:
        cpus: "0.5"
        memory: 2G
```

**ClickHouse partitioning migration:**

```sql
-- Create partitioned table
CREATE TABLE transactions_analytics_v2 (
    worker_id_hash String,
    timestamp DateTime,
    product_category LowCardinality(String),
    region LowCardinality(String),
    amount Decimal(12,2),
    quantity UInt32,
    -- ... other columns
    INDEX idx_region region TYPE bloom_filter GRANULARITY 4,
    INDEX idx_category product_category TYPE bloom_filter GRANULARITY 4
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (region, product_category, timestamp)
TTL timestamp + INTERVAL 2 YEAR;

-- Migrate data (background, non-blocking)
INSERT INTO transactions_analytics_v2 SELECT * FROM transactions_analytics;

-- Swap tables
RENAME TABLE transactions_analytics TO transactions_analytics_old;
RENAME TABLE transactions_analytics_v2 TO transactions_analytics;
```

**App-level changes:**
- `app/services/intelligence/`: Route read queries to replica via separate `get_read_db()` dependency
- `app/services/fl_service.py`: Increase `MIN_UPDATES_FOR_AGGREGATION` to 500, add distributed aggregation
- `app/worker.py`: Scale to 2 worker processes (one for tasks, one for FL + ETL)

**Cost delta:** **~$29-58/month** (Oracle A1.Flex at $0.01/OCPU/hr). May be $0 within paid free allowance.

**Migration steps:**
1. **Week 1:** Convert tenancy to PAYG (if not already). Provision Oracle A1.Flex (4 OCPUs, 24GB RAM). Migrate docker-compose. Test.
2. **Week 2:** Set up PG streaming replication. Route read queries to replica.
3. **Week 3:** Partition ClickHouse table. Run migration in background.
4. **Week 4:** (Optional) Provision second instance for dedicated ClickHouse (~$29/month additional).
5. Monitor for 2 weeks. If stable, decommission old free-tier instance.

**Estimated capacity:** 10K workers, ~50K transactions/day, ~200 concurrent API requests, FL aggregation every 15 minutes.

---

### 7.4 Tier 4: 100K Workers — Microservices + Kafka + Managed Databases

**Trigger signals:**
- API p95 > 1s even with 4 OCPUs
- PostgreSQL replication lag > 5s
- ClickHouse cluster maxed out on single node
- Redis memory > 80% of 1GB
- Deployment time > 10 minutes (monolith too big to restart quickly)
- Team growing beyond 3 developers (need independent deployments)

**What breaks:**
- **Monolith ceiling:** Single FastAPI process can't handle 100K workers' concurrent sync + intelligence queries. Even with 8 OCPUs, Python's GIL limits concurrent CPU-bound work
- **PostgreSQL write throughput:** 100K workers generate ~500K transactions/day. Single-primary PG write-ahead log becomes bottleneck
- **ClickHouse:** Single node at ~1B rows — queries still work but aggregation over full dataset takes 10-30s
- **Operational complexity:** One docker-compose file can't manage this. Need orchestration
- **Redis:** Single Redis instance at 1GB handles ~100K keys for FL state, but becomes SPOF

**What to add:**

| Component | Change | Cost |
|---|---|---|
| **Kubernetes (K3s)** | Move from docker-compose to K3s on Oracle | $0 (self-managed) |
| **Apache Kafka** | Event streaming between services | $0 (self-managed, ~500MB RAM) |
| **Managed PostgreSQL** | Oracle Autonomous DB or Supabase | ~$100-200/month |
| **ClickHouse Cloud** | Or 3-node self-managed cluster | ~$100-300/month |
| **Redis Sentinel** | HA Redis with automatic failover | $0 (self-managed) |
| **Separate services** | Split into: sync-service, intel-service, fl-service, api-gateway | Deployment complexity, not cost |

**Microservices decomposition:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway (Nginx/Kong)                      │
│                    Rate limiting, auth, routing                  │
└──────────┬──────────────┬──────────────┬───────────────────────┘
           │              │              │
           ▼              ▼              ▼
    ┌─────────────┐ ┌──────────┐ ┌─────────────┐
    │ Sync Service│ │Intel Svc │ │ FL Service  │
    │ 2 replicas  │ │2 replicas│ │ 1 replica   │
    │ Handles:    │ │ Handles: │ │ Handles:    │
    │ - Device    │ │ - Soko   │ │ - Gradient  │
    │   sync      │ │   Pulse  │ │   upload    │
    │ - Transaction│ │ - Alama │ │ - Aggregation│
    │   ingest    │ │   Score  │ │ - Model dist│
    └──────┬──────┘ │ - Reports│ └──────┬──────┘
           │        └────┬─────┘        │
           │             │              │
           ▼             ▼              ▼
    ┌─────────────────────────────────────────┐
    │              Kafka Cluster               │
    │  Topics: transactions, intelligence, fl  │
    └──────────┬──────────────┬───────────────┘
               │              │
               ▼              ▼
    ┌──────────────┐ ┌──────────────┐
    │ PostgreSQL   │ │ ClickHouse   │
    │ (Managed)    │ │ (Cluster)    │
    └──────────────┘ └──────────────┘
```

**Kafka topic design:**

```yaml
topics:
  transactions:
    partitions: 12
    replication: 3
    retention: 7d
    # Producers: sync-service
    # Consumers: intel-service (for real-time features), clickhouse-etl

  intelligence:
    partitions: 6
    replication: 3
    retention: 30d
    # Producers: intel-service
    # Consumers: sync-service (to notify devices of new products)

  fl-updates:
    partitions: 6
    replication: 3
    retention: 1d
    # Producers: sync-service (device gradient uploads)
    # Consumers: fl-service
```

**Why Kafka instead of Redis Streams:**
- Redis Streams: in-memory, limited by RAM. At 100K workers, stream backlog could exhaust memory
- Kafka: disk-persistent, handles TB-scale backlogs, true consumer groups with offset tracking
- Kafka survives restarts without data loss (Redis AOF can lose last second)

**Cost breakdown (verified Oracle A1.Flex at $0.01/OCPU/hr):**

| Item | Spec | Monthly Cost |
|---|---|---|
| Oracle A1.Flex (API + Sync + Intel) | 8 OCPUs, 48GB RAM | **$58.40** (8 × $0.01 × 730 hrs) |
| Oracle A1.Flex (Kafka + Redis) | 4 OCPUs, 24GB RAM | **$29.20** (4 × $0.01 × 730 hrs) |
| Managed PostgreSQL (Oracle Autonomous DB) | 2 OCPUs, 16GB | **~$100-150** (Oracle Autonomous pricing) |
| ClickHouse (3-node self-managed on A1) | 3 × 2 OCPUs | **$43.80** (6 × $0.01 × 730) |
| Domain + SSL | — | ~$10 |
| **Total** | | **~$240-290/month** |

> **Note:** Oracle paid free allowance (3,000 OCPU hrs/mo) covers ~4 OCPUs running 24/7. Actual cost depends on how much free allowance remains after the primary instance. Check OCI Cost Analysis dashboard.

**Migration steps:**
1. **Month 1:** Set up K3s cluster on Oracle. Deploy existing monolith as single pod. Test.
2. **Month 2:** Extract sync-service. Kafka topic `transactions` replaces direct PG writes. Deploy as separate pod.
3. **Month 3:** Extract fl-service. Kafka topic `fl-updates` replaces Redis queue for gradients.
4. **Month 4:** Extract intel-service. Reads from PG replica + ClickHouse. Writes to Kafka `intelligence` topic.
5. **Month 5:** Migrate PG to managed instance. Set up replication from self-managed to managed, then cutover.
6. **Month 6:** Migrate ClickHouse to cluster. Re-partition data across nodes.

**Estimated capacity:** 100K workers, ~500K transactions/day, ~1K concurrent API requests, FL aggregation every 5 minutes.

---

### 7.5 Tier 5: 1M Workers — Shard PostgreSQL + Multi-Region + Dedicated FL Cluster

**Trigger signals:**
- PostgreSQL write throughput > 10K TPS (single primary saturated)
- Cross-region latency > 500ms for African users (if serving continent-wide)
- Kafka throughput > 100MB/s sustained
- FL aggregation taking > 30 minutes with 100K+ gradient updates per round
- ClickHouse cluster at > 10B rows, queries taking > 30s

**What breaks:**
- **PostgreSQL single-primary:** At 1M workers × 5 transactions/day = 5M transactions/day. Single PG primary write throughput maxes at ~10K TPS
- **Single-region latency:** If serving workers across Africa (Kenya, Nigeria, Tanzania, etc.), single-region deployment adds 200-500ms latency
- **FL aggregation:** 1M devices × 1% participation = 10K gradient updates per round. Single FL server processes ~1K/min
- **ClickHouse:** 10B+ rows across 3 nodes — cross-shard queries become expensive

**What to add:**

| Component | Change | Cost |
|---|---|---|
| **Citus (PG sharding)** | Shard PostgreSQL by `worker_id_hash` | ~$300/month (managed) or $0 (self-managed extension) |
| **Multi-region deployment** | Oracle regions: eu-frankfurt + af-johannesburg + me-jeddah | ~$500-800/month (3 regions) |
| **Dedicated FL cluster** | 3-node FL aggregation with hierarchical aggregation | ~$150/month |
| **ClickHouse distributed tables** | Distributed queries across regional ClickHouse clusters | Included in multi-region cost |
| **Global load balancer** | Oracle Global LB or Cloudflare | ~$20/month |

**PostgreSQL sharding with Citus:**

```sql
-- Enable Citus
CREATE EXTENSION citus;

-- Add worker node
SELECT citus_add_node('pg-shard-1', 5432);
SELECT citus_add_node('pg-shard-2', 5432);

-- Shard transactions table by worker_id_hash
SELECT create_distributed_table('transactions', 'worker_id_hash');

-- Shard users table (co-located with transactions)
SELECT create_distributed_table('users', 'worker_id_hash', colocate_with => 'transactions');

-- Reference tables (small, replicated to all nodes)
SELECT create_reference_table('intelligence_products');
SELECT create_reference_table('fl_global_models');
```

**Hierarchical FL aggregation:**

```
Region: East Africa        Region: West Africa       Region: Southern Africa
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ FL Aggregator   │       │ FL Aggregator   │       │ FL Aggregator   │
│ (per-region)    │       │ (per-region)    │       │ (per-region)    │
│ Aggregates:     │       │ Aggregates:     │       │ Aggregates:     │
│ 333K devices    │       │ 333K devices    │       │ 333K devices    │
│ 3.3K gradients  │       │ 3.3K gradients  │       │ 3.3K gradients  │
│ per round       │       │ per round       │       │ per round       │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                         │                         │
         ▼                         ▼                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Global FL Aggregator                           │
│                    Merges 3 regional models                      │n│                    Applies global DP noise                       │
│                    Publishes global model                        │
└──────────────────────────────────────────────────────────────────┘
```

**Multi-region Kubernetes:**

```yaml
# Region: af-johannesburg (primary)
k8s-cluster:
  nodes:
    - 4 OCPUs, 16GB RAM (API + Sync)
    - 4 OCPUs, 16GB RAM (Intel + FL)
    - 2 OCPUs, 8GB RAM (Kafka + Redis)

# Region: eu-frankfurt (secondary, EU compliance)
k8s-cluster:
  nodes:
    - 2 OCPUs, 8GB RAM (API + Sync)
    - 2 OCPUs, 8GB RAM (Intel + ClickHouse replica)

# Region: me-jeddah (Middle East expansion)
k8s-cluster:
  nodes:
    - 2 OCPUs, 8GB RAM (API + Sync)
    - 2 OCPUs, 8GB RAM (Intel)
```

**Cost breakdown (verified Oracle A1.Flex at $0.01/OCPU/hr):**

| Item | Spec | Monthly Cost |
|---|---|---|
| Oracle A1.Flex primary region | 10 OCPUs, 60GB RAM | **$73.00** (10 × $0.01 × 730) |
| Oracle A1.Flex EU region | 4 OCPUs, 24GB RAM | **$29.20** |
| Oracle A1.Flex ME region | 4 OCPUs, 24GB RAM | **$29.20** |
| Citus (self-managed extension on PG) | — | **$0** (open-source extension) |
| ClickHouse cluster (3 × 2 OCPUs per region) | 18 OCPUs total | **$131.40** |
| Global load balancer (Oracle LB) | — | ~$20 |
| Domain + SSL + misc | — | ~$30 |
| **Total** | | **~$310-340/month** |

> **Note:** Citus is an open-source PostgreSQL extension — $0 if self-managed. If using Azure Cosmos DB for PostgreSQL (managed Citus), cost is ~$300/month extra. For Oracle Cloud, self-managed Citus on A1.Flex is the cost-effective choice.

**Migration steps:**
1. **Month 1-2:** Deploy Citus. Migrate from single PG to distributed. Use `create_distributed_table` with zero-downtime migration.
2. **Month 3-4:** Deploy secondary region (EU). Set up cross-region PG replication. Route EU traffic.
3. **Month 5:** Deploy third region (ME). Set up hierarchical FL aggregation.
4. **Month 6:** Global load balancer. Route by geo-proximity.

**Estimated capacity:** 1M workers, ~5M transactions/day, ~10K concurrent API requests, FL aggregation every 5 minutes per region.

---

### 7.6 Tier 6: 10M Workers — Fundamentally Different Architecture

**Trigger signals:**
- Kafka throughput > 1GB/s
- Citus cluster > 100 shards, cross-shard queries > 10s
- ClickHouse > 100B rows
- Operational cost > $5K/month
- Need > 5 regions

**What breaks:**
- **Everything at single-vendor scale:** Oracle Cloud may not have regions in all needed locations
- **Citus sharding limits:** Beyond 100 shards, rebalancing becomes painful
- **Kafka:** Single Kafka cluster can handle this, but operational complexity explodes
- **Cost:** Self-managed infrastructure at this scale costs $10K+/month in engineering time alone

**What to add (architectural shift):**

| Component | Change | Cost |
|---|---|---|
| **Managed Kubernetes** | GKE/EKS/AKS instead of self-managed K3s | ~$500-1K/month |
| **Managed Kafka** | Confluent Cloud or AWS MSK | ~$500-1K/month |
| **Managed ClickHouse** | ClickHouse Cloud | ~$1K-2K/month |
| **TiDB or Yugabyte** | Distributed SQL replacing Citus for simpler ops | ~$1K-2K/month |
| **Global CDN** | Cloudflare for static + API edge caching | ~$100/month |
| **Observability stack** | Datadog or Grafana Cloud (managed) | ~$500/month |
| **Dedicated FL infra** | Separate compute cluster for FL (GPU optional) | ~$500-2K/month |

**Architecture at 10M:**

```
┌──────────────────────────────────────────────────────────────────────┐
│                    Global Edge Layer (Cloudflare)                     │
│  CDN, DDoS protection, edge caching, geo-routing                     │
└──────────┬─────────────────────┬─────────────────────┬───────────────┘
           │                     │                     │
           ▼                     ▼                     ▼
    ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
    │ Africa      │      │ Europe      │      │ Middle East │
    │ Region      │      │ Region      │      │ Region      │
    │ (Primary)   │      │             │      │             │
    │ ┌─────────┐│      │ ┌─────────┐│      │ ┌─────────┐│
    │ │  K8s    ││      │ │  K8s    ││      │ │  K8s    ││
    │ │ Cluster ││      │ │ Cluster ││      │ │ Cluster ││
    │ └─────────┘│      │ └─────────┘│      │ └─────────┘│
    │ ┌─────────┐│      │ ┌─────────┐│      │ ┌─────────┐│
    │ │ TiDB    ││      │ │ TiDB    ││      │ │ TiDB    ││
    │ │ (shard) ││      │ │ (shard) ││      │ │ (shard) ││
    │ └─────────┘│      │ └─────────┘│      │ └─────────┘│
    │ ┌─────────┐│      │ ┌─────────┐│      │ ┌─────────┐│
    │ │ClickHouse│      │ │ClickHouse│      │ │ClickHouse│
    │ │ Cluster ││      │ │ Cluster ││      │ │ Cluster ││
    │ └─────────┘│      │ └─────────┘│      │ └─────────┘│
    └─────────────┘      └─────────────┘      └─────────────┘
           │                     │                     │
           ▼                     ▼                     ▼
    ┌──────────────────────────────────────────────────────────────┐
    │                    Global FL Aggregation Cluster              │
    │                    (Dedicated compute, GPU optional)          │
    │                    Hierarchical: Regional → Continental →     │
    │                    Global                                     │
    └──────────────────────────────────────────────────────────────┘
```

**Key architectural changes at 10M:**

1. **Event sourcing:** Transaction writes become events in Kafka. Materialized views in TiDB serve reads. This decouples write throughput from read queries.
2. **CQRS pattern:** Separate write path (sync → Kafka → TiDB) from read path (ClickHouse for analytics, TiDB for user queries).
3. **FL moves to dedicated cluster:** At 10M devices, FL aggregation needs dedicated GPU compute for matrix operations. Use hierarchical aggregation: device → region → continent → global.
4. **Intelligence products become streaming:** Instead of batch cron jobs, use Kafka Streams for real-time intelligence (e.g., Soko Pulse updates every hour, not daily).
5. **API versioning + canary deployments:** Multiple API versions running simultaneously. New features rolled out to 1% of traffic first.

**Cost breakdown (verified with Oracle A1.Flex base):**

| Item | Spec | Monthly Cost |
|---|---|---|
| Managed K8s (Oracle OKE, 3 regions) | 3 × 10 OCPUs | **$219** (30 × $0.01 × 730) |
| TiDB Cloud (3 regions, dedicated) | 6 nodes | **~$2,000** (TiDB Cloud pricing) |
| ClickHouse Cloud (3 regions) | 3 × 4 OCPUs | **~$900** (ClickHouse Cloud pricing) |
| Confluent Kafka (Basic) | 3 regions | **~$500** |
| Cloudflare Enterprise | — | **~$500** |
| Grafana Cloud Pro | — | **~$500** |
| FL compute cluster (Oracle A1) | 8 OCPUs | **$58.40** |
| **Total** | | **~$4,700-5,200/month** |

> **Note:** At 10M workers, Oracle A1.Flex compute is the cheapest component (~$0.01/OCPU/hr). The cost driver is managed services (TiDB, Kafka, ClickHouse Cloud). Self-managing these on Oracle A1.Flex could reduce cost by 60-70% but requires dedicated DevOps engineering.

**Migration path:** This is a re-architecture, not a migration. At 10M workers, you should have revenue justifying a small engineering team (3-5 people). Plan a 6-month migration:
1. Month 1-2: Set up managed K8s + TiDB. Dual-write to both old and new systems.
2. Month 3-4: Migrate ClickHouse to cloud. Set up Kafka Streams for real-time intelligence.
3. Month 5-6: Cutover traffic. Decommission old infrastructure.

---

### 7.7 Scaling Summary Table

| Workers | Infrastructure | Key Additions | Monthly Cost (verified) | What Breaks |
|---|---|---|---|---|
| **100** | Oracle Free Tier (2 OCPUs, 12GB) | Nothing | **$0** | Nothing (designed for this) |
| **1K** | Oracle Free Tier + PgBouncer | PgBouncer, FL batching, Redis Streams | **$0** | PG connections, FL latency |
| **10K** | Oracle A1.Flex + Read Replica | 4 OCPUs, PG replica, ClickHouse partitioning | **~$29-58** | CPU, disk, query latency |
| **100K** | K3s + Kafka + Managed DB | Microservices, Kafka, managed PG/CH | **~$240-290** | Monolith ceiling, write throughput |
| **1M** | Multi-region + Citus + Hierarchical FL | Sharding, 3 regions, dedicated FL | **~$310-340** | Single-region latency, PG writes |
| **10M** | Managed everything + CQRS | TiDB, managed K8s/Kafka/CH, streaming intel | **~$4,700-5,200** | Everything. Re-architecture needed |

> **Oracle A1.Flex pricing source:** $0.01/OCPU/hour — [Oracle Cloud Price List](https://www.oracle.com/cloud/price-list/), verified July 2026.
> **Paid free allowance:** 3,000 OCPU hours + 18,000 GB hours per month. A 4-OCPU instance running 24/7 uses 2,920 hours — within free allowance.
> **Always Free (no payment):** 1,500 OCPU hours + 9,000 GB hours per month. A 2-OCPU instance running 24/7 uses 1,460 hours — within free allowance.

### 7.8 Anti-Patterns to Avoid

1. **Don't scale before you need to.** Running Kafka for 100 workers is waste. PgBouncer for 100 workers is fine.
2. **Don't add microservices at 1K workers.** A monolith is faster to develop, debug, and deploy at small scale.
3. **Don't shard PostgreSQL before 1M workers.** Read replicas handle most read scaling. Sharding adds operational complexity that isn't justified until write throughput is the bottleneck.
4. **Don't go multi-region before 100K workers.** If all your workers are in East Africa, a single region is fine. Multi-region is for latency, not capacity.
5. **Don't self-manage databases at 100K+ workers.** Managed databases cost more but save engineering time. At 100K workers, your time is better spent on product than database operations.
6. **Don't skip monitoring.** Every scaling decision should be data-driven. If you can't measure it, you can't scale it.
