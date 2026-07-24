# Angavu SUPERAGENT Backend Architecture

**Version:** 1.0.0
**Date:** 2026-07-24
**Author:** Chief Architect
**Status:** Architecture Design — Ready for Implementation

---

## Executive Summary

**The App-Backend Relationship:**

The **backend is the INTELLIGENCE ENGINE**. This is what makes the mission of building informal workers' economic intelligence come true.

The **Msaidizi app is the data collector on the ground**. Every voice transaction, every business pattern, every market activity feeds the backend.

```
┌─────────────────────┐         ┌─────────────────────────────────┐
│  MSAIDIZI APP       │         │  ANGAVU BACKEND                 │
│  (Data Collector)   │────────▶│  (Intelligence Engine)          │
│                     │  events │                                 │
│  • Voice transactions│         │  Transforms raw data into:      │
│  • Business patterns │         │  1. Soko Pulse (demand forecast)│
│  • Market activity   │◀────────│  2. Alama Score (credit score)  │
│  • Worker interactions│ intel  │  3. Distribution Intelligence   │
│                     │         │  4. Jamii Insights (inclusion)  │
│                     │         │  5. Federated Learning (global) │
└─────────────────────┘         └─────────────────────────────────┘
```

The Angavu backend transforms from a **33-agent multi-swarm system** into a **unified SUPERAGENT intelligence platform**. The mobile app is one agent; the backend is one platform. Internal modules replace separate agents. Every interaction is a learning event. Five intelligence products are outputs of a single reasoning engine, not isolated services.

**The M-KOPA Lesson — Why This Architecture Wins:**
M-KOPA proved the model: 10M customers, $2B in credit, 2M payments/day. Their secret? Daily micro-interactions at scale build an unstoppable data flywheel. Transaction history IS the credit score — no traditional credit bureau needed. They stacked services progressively: asset tracking → credit → insurance → financial services. The backend must be designed to replicate this at Angavu's scale.

**Growth Trajectory (Designed for Scale):**

| Year | Workers | Events/Day | Infrastructure Phase |
|------|---------|------------|---------------------|
| Today | 100 | 500 | Single server, SQLite |
| Year 1 | 1,000 | 5,000 | PostgreSQL + ClickHouse single |
| Year 3 | 100,000 | 500,000 | ClickHouse cluster, Redis cluster |
| Year 5 | 1,000,000 | 5,000,000 | Full sharded cluster, S3 cold storage |

**What changes:**
- 33 agents → 1 platform with internal modules
- Separate intelligence services → 5 unified product pipelines
- Ad-hoc federated learning → Structured LoRA adapter aggregation
- Scattered event handling → Event sourcing as the core data architecture
- Privacy as a service layer → Privacy by construction
- Static scaling → Growth-trajectory-aware architecture (500 → 5M events/day)

**The Data Flywheel is the Moat:**
More workers → more transactions → better patterns → better credit scoring → more workers. Every interaction is a proof point. The event store captures everything. The flywheel never stops spinning.

**What stays:**
- FastAPI, PostgreSQL, ClickHouse, Redis stack
- PQC encryption (ML-KEM-768, ML-DSA-65)
- Existing intelligence algorithms (the math is correct)
- Multi-channel delivery (WhatsApp, Telegram, SMS, voice)

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [New Architecture Overview](#2-new-architecture-overview)
3. [Directory Structure](#3-directory-structure)
4. [Core Reasoning Engine](#4-core-reasoning-engine)
5. [Federated Learning Architecture](#5-federated-learning-architecture)
6. [Intelligence Products Pipeline](#6-intelligence-products-pipeline)
   - 6.1 Shared Feature Extraction
   - 6.2 Soko Pulse (FMCG Demand Forecasting)
   - 6.3 Alama Score (Credit Intelligence)
   - 6.4 Distribution Intelligence
   - 6.5 Jamii Insights (Financial Inclusion)
7. [Event Sourcing Architecture](#7-event-sourcing-architecture)
   - 7.6 Data Flywheel (M-KOPA Model)
   - 7.7 Progressive Service Stacking
   - 7.8 Progressive Unlocking Logic
8. [Data Pipeline & Privacy](#8-data-pipeline--privacy)
   - 8.1 Ingestion Layer (500 → 5M events/day growth trajectory)
9. [Device Sync Service](#9-device-sync-service)
10. [API Design](#10-api-design)
11. [Infrastructure & Scaling](#11-infrastructure--scaling)
    - 11.4 Growth Trajectory Scaling (500 → 5M events/day)
12. [Migration Map](#12-migration-map)
13. [Implementation Phases](#13-implementation-phases)

---

## 1. Current State Analysis

### 1.1 Repository Stats

| Metric | Value |
|--------|-------|
| Python files | 488 |
| Agent classes | 33+ |
| Swarms | 6 (Core, Domain, Utility, Governance, Research, Autonomous) |
| API endpoints | 80+ across 14 domain routers |
| Intelligence services | 15+ (Soko Pulse, Alama Score, FMCG, Distribution Gap, etc.) |
| Database tables | 30+ (PostgreSQL) + ClickHouse OLAP |
| Event types | 60+ (EventType enum) |

### 1.2 Current Architecture Problems

**Problem 1: Agent Explosion**
The `AgentFactory` (`app/agents/factory.py`) creates and wires 33+ agents across 6 tiers:
- Tier 1: TransactionProcessor, IntelligenceGenerator, ReportGenerator, SelfEvolution, MetaAgent
- Tier 2: 6 domain agents (Agriculture, Retail, Transport, Digital, Manufacturing, Service)
- Tier 3: 6 utility agents (DataQuality, AnomalyDetector, Prediction, Communication, Learning, Sync)
- Swarm 5: 3 governance agents (Audit, Ethics, Privacy)
- Swarm 6: 3 research agents (MarketResearch, UserInsight, Innovation)
- Additional: VoicePipeline, Compliance, Security, Onboarding, SocialHandler, 6 DeerFlow agents, 6+ financial template agents, loop-enhanced duplicates

Each agent has its own event subscription, memory, and lifecycle. The MetaAgent tries to coordinate them all, but the coordination overhead exceeds the value of decomposition.

**Problem 2: Intelligence Silos**
Soko Pulse (`app/services/intelligence/soko_pulse.py`), Alama Score (`app/services/intelligence/alama_score.py`), Distribution Gap (`app/services/intelligence/distribution_gap.py`), and FMCG Intelligence (`app/services/intelligence/fmcg_intelligence.py`) share the same underlying data but have separate service classes, separate caching, separate anonymization calls, and no shared feature engineering.

**Problem 3: Federated Learning is Bolted On**
`FederatedLearningService` (`app/services/federated_learning.py`) and `FederatedLearningV2` (`app/services/federated_learning_v2.py`) handle speech model updates. They don't handle LoRA adapters for the mobile SUPERAGENT's reasoning model. The FL pipeline is disconnected from the intelligence pipeline.

**Problem 4: Events Are Messages, Not Sourced**
The `EventBus` (`app/agents/event_bus.py`) uses Redis Streams for pub/sub between agents. Events are consumed and discarded. There's no event store for replay, no CQRS, no ability to reconstruct state from events.

### 1.3 What's Valuable (Keep & Refactor)

| Current Component | Location | Keep? | Refactor Into |
|---|---|---|---|
| Soko Pulse algorithms | `app/services/intelligence/soko_pulse.py` | ✅ | `app/superagent/financial/soko_pulse.py` |
| Alama Score MLE/PCA | `app/services/intelligence/alama_score.py` | ✅ | `app/superagent/credit/alama_score.py` |
| Distribution Gap HHI | `app/services/intelligence/distribution_gap.py` | ✅ | `app/superagent/financial/distribution.py` |
| FMCG Intelligence | `app/services/intelligence/fmcg_intelligence.py` | ✅ | `app/superagent/financial/fmcg.py` |
| Anonymizer (k-anon, DP) | `app/services/anonymizer.py` | ✅ | `app/data/anonymization/` |
| FL v2 with PQC | `app/services/federated_learning_v2.py` | ✅ | `app/superagent/learning/` |
| Event Bus (Redis Streams) | `app/agents/event_bus.py` | ✅ | `app/infrastructure/event_store.py` |
| PQC encryption | `app/security/pqc/` | ✅ | Keep as-is |
| XGBoost ML layer | `app/services/ml/` | ✅ | `app/models/` |
| Econometric engine | `app/services/econometric_engine.py` | ✅ | `app/superagent/financial/engines/` |
| Statistical foundation | `app/services/statistical_foundation.py` | ✅ | `app/superagent/core/math/` |
| ClickHouse schema | `app/db/clickhouse.py` | ✅ | Expand for event store |
| Channel adapters | `app/channels/` | ✅ | Keep as-is |
| Auth (JWT + OTP) | `app/api/auth.py`, `app/api/otp_auth.py` | ✅ | Keep as-is |

---

## 2. New Architecture Overview

### 2.1 Design Principles

1. **Backend = Intelligence Engine**: The backend's job is to transform raw data from the Msaidizi app into actionable intelligence. The app collects; the backend thinks. Five intelligence products (Soko Pulse, Alama Score, Distribution Intelligence, Jamii Insights, Federated Learning) are the outputs.

2. **One Platform, Not Many Agents**: The backend is a single intelligence platform. Internal modules handle specialization. No inter-agent coordination overhead.

3. **Event Sourcing as Foundation**: Every interaction (voice, transaction, learning moment) is an immutable event. State is derived from events. The event log IS the flywheel. Each event is a proof point in the worker's financial story.

4. **Federated Learning is First-Class**: The mobile SUPERAGENT trains LoRA adapters locally. The backend aggregates gradients, never raw data. The global model improves for all workers.

5. **Privacy by Construction**: k-anonymity and differential privacy aren't applied after the fact — they're baked into the data pipeline from ingestion to output.

6. **Intelligence Products are Pipelines**: Soko Pulse, Alama Score, Distribution Intelligence, and Jamii Insights share a common feature extraction layer. Each product is a pipeline that reads from the event store, applies domain-specific models, and produces structured outputs.

7. **The Data Flywheel is the Moat** (M-KOPA lesson): More workers → more transactions → better patterns → better credit scoring → more workers. The architecture must capture every micro-interaction and turn it into intelligence. Daily interactions at scale build unstoppable momentum.

8. **Progressive Service Stacking** (M-KOPA lesson): Start with free transaction tracking. Build credit history over time. Unlock premium intelligence at scale. Each layer depends on the one below it, and each layer adds value that justifies the next.

9. **Transaction History IS the Credit Score** (M-KOPA lesson): No traditional credit bureau needed. Frequency, consistency, growth, and margins from transaction patterns are sufficient to assess creditworthiness. The Alama Score pipeline must be built on this insight.

10. **Growth-Trajectory-Aware Architecture**: Design for Year 5 (5M events/day) from day one, but deploy for today (500 events/day). The same codebase scales from single-server to sharded cluster without rewrites.

### 2.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MOBILE SUPERAGENT                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ Personal  │  │ Voice    │  │ Trans-   │  │ LoRA Adapter     │   │
│  │ Reasoning │  │ Interface│  │ action   │  │ (local training) │   │
│  │ Engine    │  │          │  │ Capture  │  │                  │   │
│  └─────┬─────┘  └────┬─────┘  └────┬─────┘  └────────┬─────────┘   │
│        └──────────────┴──────────────┴────────────────┘             │
│                              │                                      │
│                    Device Sync Protocol                              │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   SYNC SERVICE      │
                    │   (app/sync/)       │
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         │                     │                     │
┌────────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
│  EVENT STORE    │  │  FL AGGREGATOR  │  │  SYNC QUEUE     │
│  (ClickHouse)   │  │  (gradients     │  │  (Redis Streams)│
│                 │  │   only)         │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                     │                     │
         └─────────────────────┼─────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │     SUPERAGENT PLATFORM         │
              │     (app/superagent/)           │
              │                                 │
              │  ┌─────────┐  ┌──────────────┐ │
              │  │  Core   │  │  Knowledge   │ │
              │  │ Reasoning│  │  Graph       │ │
              │  │ Engine  │  │              │ │
              │  └────┬────┘  └──────┬───────┘ │
              │       │              │          │
              │  ┌────▼──────────────▼───────┐ │
              │  │   Feature Extraction      │ │
              │  │   (shared across products)│ │
              │  └────┬──────────┬───────────┘ │
              │       │          │              │
              │  ┌────▼────┐ ┌──▼──────┐ ┌────▼────┐ │
              │  │Financial│ │ Credit  │ │Distribu-│ │
              │  │(Soko    │ │(Alama   │ │tion     │ │
              │  │ Pulse)  │ │ Score)  │ │Intel    │ │
              │  └─────────┘ └─────────┘ └─────────┘ │
              │                                 │
              │  ┌─────────┐  ┌──────────────┐ │
              │  │Learning │ │  Evolution   │ │
              │  │(Federat-│ │  (Self-      │ │
              │  │ ed)     │ │   Improve)   │ │
              │  └─────────┘  └──────────────┘ │
              └─────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │       DATA PIPELINE             │
              │       (app/data/)               │
              │                                 │
              │  ┌──────────┐  ┌──────────────┐ │
              │  │Ingestion │  │Anonymization │ │
              │  │(Events)  │  │(k-anon, DP)  │ │
              │  └──────────┘  └──────────────┘ │
              │  ┌──────────────────────────┐   │
              │  │  Aggregation             │   │
              │  │  (Privacy-Preserving)    │   │
              │  └──────────────────────────┘   │
              └─────────────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │       INFRASTRUCTURE            │
              │       (app/infrastructure/)     │
              │                                 │
              │  PostgreSQL │ ClickHouse │ Redis│
              │  Event Store│ OLAP       │Cache │
              └─────────────────────────────────┘
```

### 2.3 Module Responsibilities

| Module | Responsibility | Replaces |
|--------|---------------|----------|
| `app/superagent/core/` | Central reasoning, routing, context management | MetaAgent + all agent coordination |
| `app/superagent/financial/` | Soko Pulse, FMCG intelligence, demand forecasting, Distribution Intelligence | SokoPulseService + FMCGIntelligenceService + DistributionGapService |
| `app/superagent/credit/` | Alama Score, credit scoring, financial readiness | AlamaScoreService |
| `app/superagent/inclusion/` | Jamii Insights — financial inclusion metrics for government/NGOs | JamiiInsightsService + giving_insights |
| `app/superagent/learning/` | Federated learning aggregation, LoRA management | FederatedLearningService + FL v2 |
| `app/superagent/knowledge/` | Knowledge graph, market data, causal inference | MarketResearchAgent + econometric engine |
| `app/superagent/evolution/` | Self-improvement, drift detection, model retraining | SelfEvolutionAgent + drift detector |
| `app/data/` | Ingestion, anonymization, aggregation pipeline | TransactionProcessor + Anonymizer |
| `app/sync/` | Device sync protocol, conflict resolution | SyncAgent + sync_service |

**The 5 Intelligence Products:**

| # | Product | Input | Output | Buyer |
|---|---------|-------|--------|-------|
| 1 | **Soko Pulse** | Aggregated transactions | FMCG demand forecasts, price indices | FMCG companies (Unilever, Coca-Cola, EABL) |
| 2 | **Alama Score** | Worker transaction patterns | Credit score (300-850), risk factors | Banks, MFIs, fintech |
| 3 | **Distribution Intelligence** | Market activity, transaction locations | Route optimization, coverage gaps | FMCG distributors |
| 4 | **Jamii Insights** | Aggregated anonymized data | Financial inclusion metrics, poverty indicators | Government, NGOs, World Bank |
| 5 | **Federated Learning** | Device gradient updates | Improved global model for all workers | All workers (internal) |

---

## 3. Directory Structure

```
app/
├── main.py                          # FastAPI app (refactored lifespan)
├── config.py                        # Settings (unchanged)
├── exceptions.py                    # Custom exceptions (unchanged)
│
├── api/                             # API Layer
│   ├── __init__.py
│   ├── v1/                          # API v1 (domain-organized)
│   │   ├── __init__.py              # v1_router aggregator
│   │   ├── auth.py                  # JWT + OTP auth (keep)
│   │   ├── superagent.py            # NEW: Unified superagent endpoints
│   │   ├── intelligence.py          # Refactored: delegates to superagent
│   │   ├── sync.py                  # Device sync endpoints
│   │   ├── events.py                # NEW: Event query/replay API
│   │   ├── federated_learning.py    # Refactored: LoRA FL endpoints
│   │   ├── channels.py              # WhatsApp, Telegram, SMS (keep)
│   │   ├── dashboard.py             # Dashboard (keep)
│   │   ├── users.py                 # User management (keep)
│   │   ├── transactions.py          # Transaction CRUD (keep)
│   │   └── market.py                # Market prices (keep)
│   └── webhooks/                    # NEW: Webhook handlers
│       ├── __init__.py
│       ├── mpesa.py                 # M-Pesa STK push & callbacks
│       └── whatsapp.py              # WhatsApp webhook handler
│
├── superagent/                      # THE Unified Intelligence Platform
│   ├── __init__.py
│   │
│   ├── core/                        # Core Reasoning Engine
│   │   ├── __init__.py
│   │   ├── engine.py                # Central reasoning engine
│   │   ├── context.py               # Worker context management
│   │   ├── router.py                # Intent classification & routing
│   │   ├── planner.py               # Task planning & decomposition
│   │   ├── memory.py                # Tiered memory (short/long-term)
│   │   └── math/                    # Mathematical foundations
│   │       ├── __init__.py
│   │       ├── statistical.py       # From app/services/statistical_foundation.py
│   │       ├── econometric.py       # From app/services/econometric_engine.py
│   │       ├── causal.py            # From app/services/causal_inference.py
│   │       └── optimization.py      # From app/services/game_theory.py
│   │
│   ├── financial/                   # Financial Intelligence (Soko Pulse)
│   │   ├── __init__.py
│   │   ├── soko_pulse.py            # FMCG demand forecasting (refactored)
│   │   ├── distribution.py          # Distribution gap analysis (refactored)
│   │   ├── fmcg.py                  # FMCG intelligence (refactored)
│   │   ├── pricing.py               # Price intelligence & indices
│   │   ├── engines/                 # Computational engines
│   │   │   ├── __init__.py
│   │   │   ├── time_series.py       # ARIMA/SARIMA from econometric_engine
│   │   │   ├── demand_model.py      # Demand estimation models
│   │   │   └── market_structure.py  # HHI, concentration ratios
│   │   └── pipelines/               # Product pipelines
│   │       ├── __init__.py
│   │       ├── demand_forecast.py   # Soko Pulse pipeline
│   │       └── distribution_gaps.py # Distribution Intelligence pipeline
│   │
│   ├── credit/                      # Credit Intelligence (Alama Score)
│   │   ├── __init__.py
│   │   ├── alama_score_engine.py    # Real-time scoring engine (6 signals)
│   │   ├── device_engine.py         # On-device offline-first engine
│   │   ├── readiness.py             # Financial readiness assessment
│   │   ├── risk_profiling.py        # KDE-based risk profiling
│   │   ├── progressive.py           # Progressive service unlocking
│   │   └── pipelines/
│   │       ├── __init__.py
│   │       └── credit_pipeline.py   # Alama Score pipeline
│   │
│   ├── learning/                    # Federated Learning Engine
│   │   ├── __init__.py
│   │   ├── aggregator.py            # Gradient aggregation (FedAvg)
│   │   ├── lora_manager.py          # LoRA adapter management
│   │   ├── privacy.py               # DP + secure aggregation
│   │   ├── dialect_federation.py    # Per-dialect model federation
│   │   └── round_coordinator.py     # FL round management
│   │
│   ├── knowledge/                   # Knowledge Graph & Market Data
│   │   ├── __init__.py
│   │   ├── graph.py                 # Knowledge graph (entities, relations)
│   │   ├── market_data.py           # Market data ingestion & normalization
│   │   ├── causal_graph.py          # Causal inference graph
│   │   └── embeddings.py            # Entity embeddings for similarity
│   │
│   └── evolution/                   # Self-Improvement Engine
│       ├── __init__.py
│       ├── drift_detector.py        # From app/services/drift_detector.py
│       ├── retrain_trigger.py       # From app/services/drift_retrain_trigger.py
│       ├── performance_tracker.py   # Model performance over time
│       └── feedback_loop.py         # User feedback → model improvement
│
├── data/                            # Data Pipeline
│   ├── __init__.py
│   ├── ingestion/                   # Transaction Ingestion
│   │   ├── __init__.py
│   │   ├── transaction_ingester.py  # Transaction event creation
│   │   ├── voice_ingester.py        # Voice → text → event
│   │   ├── mpesa_parser.py          # From app/services/mpesa_sms_parser.py
│   │   └── batch_processor.py       # Batch transaction processing
│   ├── aggregation/                 # Privacy-Preserving Aggregation
│   │   ├── __init__.py
│   │   ├── private_aggregator.py    # k-anonymity + DP aggregation
│   │   ├── cohort_builder.py        # Worker cohort construction
│   │   └── statistics.py            # Aggregate statistics computation
│   └── anonymization/               # Privacy Layer
│       ├── __init__.py
│       ├── anonymizer.py            # From app/services/anonymizer.py (refactored)
│       ├── k_anonymity.py           # k-anonymity enforcement
│       ├── differential_privacy.py  # Gaussian mechanism
│       └── pseudonymizer.py         # ID pseudonymization
│
├── sync/                            # Device Sync Service
│   ├── __init__.py
│   ├── sync_service.py              # Sync protocol implementation
│   ├── conflict_resolver.py         # CRDT-based conflict resolution
│   ├── delta_sync.py                # Delta-based sync (only changes)
│   └── offline_queue.py             # Offline-first queue management
│
├── models/                          # ML Models & Database Models
│   ├── __init__.py
│   ├── ml/                          # Machine Learning
│   │   ├── __init__.py
│   │   ├── feature_engineering.py   # From app/services/ml/feature_engineering.py
│   │   ├── xgboost_service.py       # From app/services/ml/xgboost_service.py
│   │   ├── inference.py             # Model inference harness
│   │   └── registry.py              # Model version registry
│   ├── orm/                         # Database ORM Models
│   │   ├── __init__.py
│   │   ├── user.py                  # User model
│   │   ├── transaction.py           # Transaction model
│   │   ├── event.py                 # NEW: Event store model
│   │   ├── intelligence.py          # Intelligence product models
│   │   ├── fl_round.py              # NEW: FL round tracking
│   │   └── sync_state.py            # NEW: Device sync state
│   └── schemas/                     # Pydantic schemas
│       ├── __init__.py
│       ├── events.py                # NEW: Event schemas
│       ├── intelligence.py          # Intelligence schemas
│       ├── sync.py                  # Sync schemas
│       └── federated_learning.py    # FL schemas
│
├── infrastructure/                  # Infrastructure Layer
│   ├── __init__.py
│   ├── event_store.py               # NEW: Event sourcing store (ClickHouse)
│   ├── event_bus.py                 # Refactored from app/agents/event_bus.py
│   ├── cache.py                     # Redis cache (keep)
│   ├── task_queue.py                # Task queue (keep)
│   ├── circuit_breaker.py           # Circuit breaker (keep)
│   ├── connection_pool.py           # Connection pool (keep)
│   ├── metrics.py                   # Prometheus metrics (keep)
│   ├── telemetry.py                 # OpenTelemetry (keep)
│   └── redis_streams.py             # Redis Streams (keep)
│
├── security/                        # Security Layer
│   ├── __init__.py
│   ├── pqc/                         # Post-Quantum Cryptography (keep)
│   ├── rate_limiter.py              # Rate limiting (keep)
│   ├── security_middleware.py       # Input validation (keep)
│   └── auth/                        # Authentication
│       ├── __init__.py
│       ├── jwt_service.py           # JWT token service
│       └── otp_service.py           # OTP verification
│
├── channels/                        # Communication Channels (keep)
│   ├── __init__.py
│   ├── adapters/
│   │   ├── whatsapp_adapter.py
│   │   ├── telegram_adapter.py
│   │   ├── sms_adapter.py
│   │   ├── voice_adapter.py
│   │   └── http_api_adapter.py
│   ├── gateway.py
│   ├── failover.py
│   └── health_monitor.py
│
└── db/                              # Database Layer
    ├── __init__.py
    ├── database.py                  # PostgreSQL (keep)
    ├── clickhouse.py                # ClickHouse (keep, expand)
    └── migrations/                  # Alembic migrations
```

---

## 4. Core Reasoning Engine

### 4.1 Design

The core reasoning engine replaces the MetaAgent and all agent coordination. It's a single module that:

1. **Classifies intent** from incoming requests (voice, text, transaction)
2. **Routes to the appropriate pipeline** (financial, credit, learning, general)
3. **Manages context** across interactions (worker profile, history, preferences)
4. **Plans multi-step tasks** when a single interaction requires multiple intelligence products

### 4.2 Engine Architecture

```python
# app/superagent/core/engine.py

class SuperagentEngine:
    """
    Central reasoning engine for the Angavu SUPERAGENT platform.

    Replaces the MetaAgent + 33 separate agents with a single
    reasoning loop that routes to internal modules.
    """

    def __init__(
        self,
        event_store: EventStore,
        context_manager: ContextManager,
        router: IntentRouter,
        planner: TaskPlanner,
        financial_pipeline: FinancialPipeline,
        credit_pipeline: CreditPipeline,
        learning_engine: FederatedLearningEngine,
        knowledge_graph: KnowledgeGraph,
    ):
        self.event_store = event_store
        self.context = context_manager
        self.router = router
        self.planner = planner
        self.financial = financial_pipeline
        self.credit = credit_pipeline
        self.learning = learning_engine
        self.knowledge = knowledge_graph

    async def process(self, event: DomainEvent) -> Response:
        """
        Main processing loop.

        1. Record event to event store
        2. Load worker context
        3. Classify intent
        4. Route to appropriate pipeline
        5. Generate response
        6. Record outcome event
        """
        # 1. Event sourcing — every interaction is persisted
        await self.event_store.append(event)

        # 2. Load context (recent transactions, preferences, history)
        worker_ctx = await self.context.load(event.worker_id)

        # 3. Classify intent
        intent = await self.router.classify(event, worker_ctx)

        # 4. Route to pipeline
        if intent.domain == "financial":
            result = await self.financial.process(intent, worker_ctx)
        elif intent.domain == "credit":
            result = await self.credit.process(intent, worker_ctx)
        elif intent.domain == "learning":
            result = await self.learning.process(intent, worker_ctx)
        else:
            result = await self._general_response(intent, worker_ctx)

        # 5. Generate response (voice, text, or structured data)
        response = await self._format_response(result, event.channel)

        # 6. Record outcome
        await self.event_store.append(DomainEvent(
            type="response.generated",
            worker_id=event.worker_id,
            payload={"intent": intent.dict(), "result_summary": result.summary},
        ))

        return response
```

### 4.3 Intent Classification

```python
# app/superagent/core/router.py

class IntentDomain(StrEnum):
    FINANCIAL = "financial"          # Soko Pulse, pricing, demand
    CREDIT = "credit"                # Alama Score, readiness
    TRANSACTION = "transaction"      # Record sale, record purchase
    LEARNING = "learning"            # Training feedback, correction
    GENERAL = "general"              # Chitchat, FAQ, onboarding

class IntentRouter:
    """
    Classifies incoming interactions into domains.

    Uses a lightweight classifier (keyword matching + small model)
    to route without expensive LLM calls for every message.
    """

    async def classify(
        self, event: DomainEvent, context: WorkerContext
    ) -> Intent:
        # Fast path: keyword matching for common intents
        if self._is_transaction(event):
            return Intent(domain="transaction", action="record")
        if self._is_financial_query(event):
            return Intent(domain="financial", action="query")

        # Slow path: LLM-based classification for ambiguous inputs
        return await self._llm_classify(event, context)
```

### 4.4 Context Management

```python
# app/superagent/core/context.py

class WorkerContext:
    """
    Per-worker context that persists across interactions.

    Stored in Redis (hot) + PostgreSQL (warm).
    Includes:
    - Worker profile (business type, location, language)
    - Recent transactions (last 30 days)
    - Intelligence product history
    - Preferences and personalization
    - LoRA adapter version (for personalized responses)
    """

    worker_id: str
    business_type: str
    location: GeoPoint
    language: str
    recent_transactions: list[Transaction]
    intelligence_history: list[IntelligenceResult]
    preferences: dict[str, Any]
    lora_version: str
```

---

## 5. Federated Learning Architecture

### 5.1 Overview

The federated learning system enables the mobile SUPERAGENT to learn personally while contributing to a global model that benefits all workers. **Raw data never leaves the device.**

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVICE (Mobile SUPERAGENT)                │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Transaction  │───▶│ Local        │───▶│ LoRA Adapter │  │
│  │ History      │    │ Training     │    │ (personal)   │  │
│  └──────────────┘    └──────────────┘    └──────┬───────┘  │
│                                                 │          │
│  ┌──────────────┐    ┌──────────────┐          │          │
│  │ Voice        │───▶│ Correction   │──────────┘          │
│  │ Interactions │    │ Signals      │                     │
│  └──────────────┘    └──────────────┘                     │
│                                                 │          │
│                              Gradient Deltas    │          │
│                              (NOT raw data)     │          │
│                                                 ▼          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              PQC Encryption Layer                     │  │
│  │  ML-KEM-768 key exchange + AES-256-GCM encryption    │  │
│  └──────────────────────────┬───────────────────────────┘  │
└─────────────────────────────┼──────────────────────────────┘
                              │
                    Encrypted Gradient Upload
                              │
┌─────────────────────────────▼──────────────────────────────┐
│                    BACKEND FL AGGREGATOR                     │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ PQC          │───▶│ K-Anonymity  │───▶│ FedAvg       │  │
│  │ Decryption   │    │ Check (k≥5)  │    │ Aggregation  │  │
│  └──────────────┘    └──────────────┘    └──────┬───────┘  │
│                                                 │          │
│                              ┌───────────────────┘          │
│                              ▼                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Differential │───▶│ Global Model │───▶│ Push to      │  │
│  │ Privacy      │    │ Update       │    │ Devices      │  │
│  │ (ε=0.1)      │    │              │    │              │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Dialect Federation                       │  │
│  │  Per-dialect models: sw, en, luo, kik, kal, kam, ... │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 LoRA Adapter Architecture

The mobile SUPERAGENT uses LoRA (Low-Rank Adaptation) adapters to personalize the base model:

```python
# app/superagent/learning/lora_manager.py

class LoRAAdapterManager:
    """
    Manages LoRA adapters for federated learning.

    Architecture:
    - Base model: Shared across all devices (frozen)
    - LoRA adapters: Per-device, trained locally on device
    - Global LoRA: Aggregated from device gradients (FedAvg)
    - Personal LoRA: Stays on device, never uploaded

    The device has TWO LoRA adapters:
    1. Personal adapter (rank=8): Trained on this worker's data only
    2. Global adapter (rank=16): Downloaded from backend, improves for all

    Inference: base_model + personal_adapter + global_adapter
    """

    # LoRA configuration
    PERSONAL_RANK = 8       # Small — fast local training
    GLOBAL_RANK = 16        # Larger — captures population patterns
    TARGET_MODULES = ["q_proj", "v_proj", "k_proj", "o_proj"]
    LEARNING_RATE = 1e-4
    BATCH_SIZE = 4          # Small batch for mobile training

    async def get_global_adapter(self, dialect: str) -> AdapterWeights:
        """Download the latest global adapter for a dialect."""
        ...

    async def submit_gradients(
        self,
        device_id_hash: str,
        dialect: str,
        gradient_deltas: bytes,  # PQC-encrypted
        metadata: GradientMetadata,
    ) -> AggregationReceipt:
        """Submit gradient deltas for aggregation."""
        ...
```

### 5.3 Aggregation Protocol

```python
# app/superagent/learning/aggregator.py

class FedAvgAggregator:
    """
    Federated Averaging with privacy guarantees.

    Protocol:
    1. Devices train locally for E epochs
    2. Devices compute gradient deltas (new_weights - old_weights)
    3. Devices encrypt deltas with ML-KEM-768
    4. Backend decrypts, checks k-anonymity (k≥5 per cohort)
    5. Backend aggregates: w_global = Σ(n_k/n * w_k) for k cohorts
    6. Backend adds DP noise: w_global += N(0, σ²I) where σ = Δf·√(2ln(1.25/δ))/ε
    7. Backend publishes new global adapter
    8. Devices download and merge with personal adapter

    Privacy guarantees:
    - ε=0.1 differential privacy (financial-grade)
    - k≥5 anonymity (no individual gradients visible)
    - ML-KEM-768 encryption (post-quantum secure)
    - One-way hashed device IDs (server cannot identify users)
    """

    DP_EPSILON = 0.1
    DP_DELTA = 1e-6
    K_ANONYMITY_MIN = 5

    async def aggregate_round(
        self,
        dialect: str,
        gradients: list[EncryptedGradient],
    ) -> GlobalModelUpdate:
        """Run one aggregation round for a dialect."""
        # 1. Decrypt gradients
        decrypted = [self._decrypt(g) for g in gradients]

        # 2. k-anonymity check
        if len(decrypted) < self.K_ANONYMITY_MIN:
            raise InsufficientParticipantsError(
                f"Need ≥{self.K_ANONYMITY_MIN} participants, got {len(decrypted)}"
            )

        # 3. FedAvg aggregation
        weights = [g.metadata.num_samples for g in decrypted]
        total = sum(weights)
        aggregated = {}
        for layer_name in decrypted[0].deltas:
            aggregated[layer_name] = sum(
                g.deltas[layer_name] * (w / total)
                for g, w in zip(decrypted, weights)
            )

        # 4. Add differential privacy noise
        noise_scale = self._compute_noise_scale()
        for layer_name in aggregated:
            noise = np.random.normal(0, noise_scale, aggregated[layer_name].shape)
            aggregated[layer_name] += noise

        # 5. Publish
        return GlobalModelUpdate(
            dialect=dialect,
            version=self._next_version(dialect),
            adapter_weights=aggregated,
            metadata=AggregationMetadata(
                num_participants=len(decrypted),
                total_samples=total,
                dp_epsilon=self.DP_EPSILON,
                noise_scale=noise_scale,
            ),
        )
```

### 5.4 Dialect Federation

Kenya has 9+ dialect regions. Each gets its own federated model:

```python
# app/superagent/learning/dialect_federation.py

DIALECT_REGIONS = {
    "sw": {"name": "Swahili", "center": [-1.29, 36.82]},    # Nairobi
    "en": {"name": "English", "center": [-1.29, 36.82]},
    "luo": {"name": "Luo", "center": [-0.10, 34.76]},       # Kisumu
    "kik": {"name": "Kikuyu", "center": [-0.72, 36.98]},    # Nyeri
    "kal": {"name": "Kalenjin", "center": [0.31, 35.28]},   # Eldoret
    "kam": {"name": "Kamba", "center": [-1.52, 37.26]},      # Machakos
    "luh": {"name": "Luhya", "center": [0.28, 34.75]},      # Kakamega
    "mer": {"name": "Meru", "center": [0.05, 37.65]},        # Meru
    "mij": {"name": "Mijikenda", "center": [-3.95, 39.66]}, # Mombasa
}

class DialectFederation:
    """
    Per-dialect federated learning coordinator.

    Each dialect has:
    - Its own aggregation round schedule
    - Its own global adapter weights
    - Its own participant cohort

    Cross-dialect knowledge transfer happens through the base model
    (shared) and the knowledge graph (shared market intelligence).
    """
```

### 5.5 What Gets Federated

| Component | Trained On | Aggregated | Stays on Device |
|-----------|-----------|------------|-----------------|
| Voice recognition (ASR) | Device speech data | ✅ (existing FL) | ❌ |
| Transaction parsing | Device transaction patterns | ✅ | ❌ |
| Business reasoning | Device interaction history | ✅ (LoRA gradients) | ❌ |
| **Alama Score signals** | **Device transaction patterns** | **✅ (gradient deltas)** | **❌** |
| Personal preferences | Device usage patterns | ❌ | ✅ (personal LoRA) |
| Worker profile | Device profile data | ❌ | ✅ |

**Alama Score Federated Learning:** The 6 credit signals (frequency, revenue trend, margins, diversity, regularity, growth) are computed on-device. The gradient deltas (how the signals map to creditworthiness) are federated — improving the global scoring model for ALL workers without sharing individual transaction data.

---

## 6. Intelligence Products Pipeline

### 6.1 Shared Feature Extraction

All intelligence products share a common feature extraction layer. This eliminates the current duplication where Soko Pulse, Alama Score, and FMCG Intelligence each compute the same features independently.

```python
# app/superagent/financial/pipelines/shared.py

class SharedFeatureExtractor:
    """
    Extracts features shared across all intelligence products.

    Input: Event store (transactions, voice interactions, market data)
    Output: Feature vectors for financial, credit, and distribution analysis

    Features extracted:
    - Transaction volume (daily, weekly, monthly)
    - Transaction frequency patterns
    - Revenue trends (growth rate, volatility)
    - Product mix (category distribution)
    - Geographic patterns (market coverage)
    - Temporal patterns (hour-of-day, day-of-week distributions)
    - Seasonal indicators
    - Customer concentration (HHI of customer base)
    """

    async def extract(
        self,
        worker_id: str,
        lookback_days: int = 90,
    ) -> FeatureVector:
        """Extract shared features from event store."""
        events = await self.event_store.query(
            worker_id=worker_id,
            event_types=["transaction.recorded", "transaction.processed"],
            since=days_ago(lookback_days),
        )

        return FeatureVector(
            volume_features=self._extract_volume(events),
            frequency_features=self._extract_frequency(events),
            revenue_features=self._extract_revenue(events),
            product_mix=self._extract_product_mix(events),
            geographic_features=self._extract_geographic(events),
            temporal_features=self._extract_temporal(events),
            seasonal_features=self._extract_seasonal(events),
            concentration_features=self._extract_concentration(events),
        )
```

### 6.2 Soko Pulse Pipeline

**What it does:** FMCG demand forecasting for informal markets.

**Input:** Transaction events from the event store (anonymized, aggregated across cohorts).

**Output:** Demand forecasts, price indices, seasonal patterns, market alerts.

**Buyers:** FMCG companies (Unilever, Coca-Cola, P&G, EABL, Bidco, Pwani Oil).

```python
# app/superagent/financial/pipelines/demand_forecast.py

class SokoPulsePipeline:
    """
    Soko Pulse — FMCG Demand Forecasting Pipeline.

    Pipeline stages:
    1. Market Data Ingestion: Pull transaction events from event store
    2. Price Distribution: KDE estimation of price distributions per product
    3. Seasonal Decomposition: Y = T + S + C + I (additive) or Y = T × S × C × I
    4. Time Series Forecasting: ARIMA/SARIMA + XGBoost ensemble
    5. Elasticity Estimation: Price elasticity (PED), cross-price elasticity (XED)
    6. Price Index Computation: Laspeyres, Paasche, Fisher ideal indices
    7. Demand Forecast: Volume forecast with confidence intervals

    Refactored from:
    - app/services/intelligence/soko_pulse.py (core algorithms)
    - app/services/econometric_engine.py (ARIMA, VAR, cointegration)
    - app/services/statistical_foundation.py (KDE, bootstrap, PCA)
    - app/services/ml/xgboost_service.py (ML demand model)
    """

    async def generate_forecast(
        self,
        region: str,
        product_category: str,
        horizon_days: int = 30,
    ) -> SokoPulseForecast:
        """Generate demand forecast for a product category in a region."""
        # 1. Pull anonymized transaction events
        events = await self.event_store.query_aggregated(
            region=region,
            category=product_category,
            since=days_ago(180),
        )

        # 2. Price distribution analysis (KDE)
        price_dist = self.stats_engine.kde_estimate(events.prices)

        # 3. Seasonal decomposition
        decomposition = self.time_series.decompose(
            events.daily_volumes, model="additive"
        )

        # 4. ARIMA forecast
        arima_forecast = self.time_series.arima_forecast(
            decomposition.trend_residual,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, 7),
            horizon=horizon_days,
        )

        # 5. XGBoost ensemble
        features = self.feature_engineer.create_features(events)
        xgb_forecast = self.xgb_service.predict(features, horizon=horizon_days)

        # 6. Ensemble (weighted average)
        ensemble_forecast = 0.6 * arima_forecast + 0.4 * xgb_forecast


        # 7. Confidence intervals (bootstrap)
        ci = self.stats_engine.bootstrap_ci(ensemble_forecast, alpha=0.05)

        return SokoPulseForecast(
            region=region,
            category=product_category,
            forecast=ensemble_forecast,
            confidence_interval=ci,
            price_index=self._compute_price_index(events),
            elasticity=self._compute_elasticity(events),
            seasonal_pattern=decomposition.seasonal,
            alerts=self._generate_alerts(ensemble_forecast, events),
        )
```

### 6.3 Alama Score Pipeline — Real-Time, Offline-First Credit Scoring

**What it does:** Transaction-based credit scoring (300-850) for informal businesses, computed IN REAL TIME from voice transactions, OFFLINE-FIRST on the device.

**Why Alama Score Beats M-KOPA:**

| | M-KOPA Credit | Alama Score |
|---|---|---|
| **Data source** | Phone repayment history | Actual business transactions |
| **What it proves** | Can make daily payments | Can RUN A BUSINESS |
| **APR** | 150-390% (expensive) | 18-24% (formal rates) |
| **Credit basis** | Repayment discipline | Profitability + consistency + growth |
| **Update frequency** | Monthly | Every voice transaction (real-time) |
| **Works offline** | No | Yes — computed on device |

**The 90-Day Proof:** When a worker has 90 days of consistent voice transactions showing profitability, they have BETTER credit proof than a payslip. A payslip shows you have a job. Transaction history shows you can RUN A BUSINESS.

**Input:** Voice transactions recorded by the Msaidizi app (real-time, on-device).

**Output:** Credit score (300-850), risk factors, financial readiness, loan eligibility.

**Buyers:** Banks, microfinance institutions, fintech companies.

**The 6 Credit Proof Points (from voice transactions):**

| # | Signal | What Voice Transactions Prove | Credit Weight |
|---|--------|------------------------------|---------------|
| 1 | **Transaction frequency** | "I sold 12 items today" — daily activity = business consistency | 20% |
| 2 | **Revenue trends** | "Today's sales: KSh 3,200" — growing or declining? | 20% |
| 3 | **Profit margins** | "Bought for 500, sold for 800" — is the business profitable? | 25% |
| 4 | **Product diversity** | "Sold maize, beans, cooking oil" — not dependent on one product | 10% |
| 5 | **Regularity** | Same time, same place, every day = reliability | 15% |
| 6 | **Growth trajectory** | Month-over-month improvement = capacity to repay | 10% |

**Architecture: Device-First, Backend-Enhanced:**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ALAMA SCORE ARCHITECTURE                         │
│                    (Real-Time, Offline-First)                       │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    DEVICE (Offline-First)                    │   │
│  │                                                             │   │
│  │  Worker says: "Sold 50 items today, revenue 3000"           │   │
│  │         │                                                   │   │
│  │         ▼                                                   │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │   │
│  │  │ Voice ASR    │───▶│ Transaction  │───▶│ Local Event  │  │   │
│  │  │ (on-device)  │    │ Parser       │    │ Store        │  │   │
│  │  └──────────────┘    └──────────────┘    └──────┬───────┘  │   │
│  │                                                 │          │   │
│  │                                                 ▼          │   │
│  │  ┌──────────────────────────────────────────────────────┐  │   │
│  │  │              LOCAL ALAMA SCORE ENGINE                 │  │   │
│  │  │                                                      │  │   │
│  │  │  Computes score from local transaction history:      │  │   │
│  │  │  • Frequency: 12 transactions/day → +15 points       │  │   │
│  │  │  • Revenue trend: +5% month-over-month → +20 points  │  │   │
│  │  │  • Margins: 37% gross margin → +25 points            │  │   │
│  │  │  • Diversity: 8 product categories → +10 points      │  │   │
│  │  │  • Regularity: 6/7 days active → +15 points          │  │   │
│  │  │  • Growth: improving 3 months straight → +10 points  │  │   │
│  │  │                                                      │  │   │
│  │  │  → Current Score: 720 / 850                          │  │   │
│  │  │  → Eligible for: KSh 50,000 at 20% APR              │  │   │
│  │  └──────────────────────────────────────────────────────┘  │   │
│  │         │                                                   │   │
│  │         │  When connected: sync score + gradients           │   │
│  │         ▼                                                   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                          │                                          │
│                    Sync Protocol                                    │
│                          │                                          │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    BACKEND (When Connected)                  │   │
│  │                                                             │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │   │
│  │  │ Receive      │───▶│ Validate &   │───▶│ Global Model │  │   │
│  │  │ Score +      │    │ Recalibrate  │    │ Update       │  │   │
│  │  │ Gradients    │    │              │    │              │  │   │
│  │  └──────────────┘    └──────────────┘    └──────────────┘  │   │
│  │                                                             │   │
│  │  Backend adds:                                              │   │
│  │  • Cohort comparison (how does this worker compare?)        │   │
│  │  • Regional benchmarks (average margins in this region)     │   │
│  │  • Industry risk adjustment (agriculture vs retail risk)    │   │
│  │  • Loan product matching (which lenders serve this tier?)   │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

```python
# app/superagent/credit/alama_score_engine.py

class AlamaScoreEngine:
    """
    Alama Score — Real-Time, Offline-First Credit Scoring Engine.

    DIFFERENT FROM M-KOPA:
    - M-KOPA scores based on phone repayment (150-390% APR)
    - Alama Score scores based on BUSINESS PROFITABILITY (18-24% APR)
    - Computed IN REAL TIME from every voice transaction
    - Works OFFLINE on the device, syncs when connected

    The 90-Day Proof:
    When a worker has 90 days of consistent voice transactions
    showing profitability, they have BETTER credit proof than a
    payslip. A payslip shows you have a job. Transaction history
    shows you can RUN A BUSINESS.

    Score is computed from 6 signals extracted from voice transactions:
    1. Transaction frequency (20%) — daily activity = consistency
    2. Revenue trends (20%) — growing or declining?
    3. Profit margins (25%) — is the business actually profitable?
    4. Product diversity (10%) — not dependent on one product
    5. Regularity (15%) — same time, same place = reliability
    6. Growth trajectory (10%) — improving over time
    """

    SCORE_MIN = 300
    SCORE_MAX = 850

    # Signal weights (sum to 1.0)
    WEIGHTS = {
        "frequency": 0.20,
        "revenue_trend": 0.20,
        "margins": 0.25,
        "diversity": 0.10,
        "regularity": 0.15,
        "growth": 0.10,
    }

    # Progressive unlocking thresholds
    TIERS = {
        "insufficient": {"min_days": 0, "min_txns": 0},
        "emerging": {"min_days": 14, "min_txns": 30},
        "building": {"min_days": 30, "min_txns": 90},
        "established": {"min_days": 60, "min_txns": 180},
        "strong": {"min_days": 90, "min_txns": 300},
        "exceptional": {"min_days": 180, "min_txns": 500},
    }

    # Credit eligibility by tier
    CREDIT_TIERS = {
        "insufficient": {"max_loan": 0, "apr": None},
        "emerging": {"max_loan": 5_000, "apr": 0.24},      # KSh 5K at 24%
        "building": {"max_loan": 20_000, "apr": 0.22},     # KSh 20K at 22%
        "established": {"max_loan": 50_000, "apr": 0.20},  # KSh 50K at 20%
        "strong": {"max_loan": 100_000, "apr": 0.18},      # KSh 100K at 18%
        "exceptional": {"max_loan": 250_000, "apr": 0.18}, # KSh 250K at 18%
    }

    def compute_score_from_transactions(
        self,
        transactions: list[Transaction],
    ) -> AlamaScoreResult:
        """
        Compute credit score from a list of transactions.

        This runs ON THE DEVICE (offline). No network needed.
        Transactions are the worker's own voice-recorded data.
        """
        if len(transactions) < 10:
            return AlamaScoreResult(
                score=self.SCORE_MIN,
                tier="insufficient",
                message="Keep recording transactions to build your score",
            )

        # Extract the 6 signals from transactions
        signals = self._extract_signals(transactions)

        # Compute weighted score (0-550 range, then add base 300)
        raw = sum(
            self._normalize_signal(signals[name]) * weight
            for name, weight in self.WEIGHTS.items()
        )
        score = int(self.SCORE_MIN + raw * (self.SCORE_MAX - self.SCORE_MIN))
        score = max(self.SCORE_MIN, min(self.SCORE_MAX, score))

        # Determine tier
        tier = self._compute_tier(transactions)

        # Credit eligibility
        credit = self.CREDIT_TIERS[tier]

        return AlamaScoreResult(
            score=score,
            tier=tier,
            signals=signals,
            max_loan=credit["max_loan"],
            apr=credit["apr"],
            transaction_count=len(transactions),
            history_days=self._history_days(transactions),
            message=self._tier_message(tier, score),
        )

    def _extract_signals(
        self, transactions: list[Transaction]
    ) -> dict[str, float]:
        """
        Extract the 6 credit proof signals from voice transactions.

        Each signal is normalized to 0.0-1.0 range.
        """
        dates = [t.date for t in transactions]
        amounts = [t.amount for t in transactions]
        categories = [t.category for t in transactions]
        margins = [t.selling_price - t.cost_price for t in transactions
                   if t.cost_price > 0]

        history_days = (max(dates) - min(dates)).days or 1
        active_days = len(set(dates))

        return {
            # 1. Frequency: transactions per day (target: 5+/day = 1.0)
            "frequency": min(1.0, len(transactions) / history_days / 5.0),

            # 2. Revenue trend: month-over-month growth (positive = 1.0)
            "revenue_trend": self._compute_revenue_trend(transactions),

            # 3. Margins: gross margin percentage (target: 30%+ = 1.0)
            "margins": min(1.0, np.mean(margins) / np.mean(amounts) / 0.30)
                if margins and amounts else 0.0,

            # 4. Diversity: unique categories (target: 5+ = 1.0)
            "diversity": min(1.0, len(set(categories)) / 5.0),

            # 5. Regularity: active days / total days (target: 80%+ = 1.0)
            "regularity": min(1.0, active_days / history_days / 0.80),

            # 6. Growth: 3-month improvement trend
            "growth": self._compute_growth_trajectory(transactions),
        }

    def _compute_tier(self, transactions: list[Transaction]) -> str:
        """Determine credit tier based on transaction history."""
        history_days = self._history_days(transactions)
        txn_count = len(transactions)

        for tier_name in reversed(list(self.TIERS.keys())):
            threshold = self.TIERS[tier_name]
            if (history_days >= threshold["min_days"] and
                txn_count >= threshold["min_txns"]):
                return tier_name
        return "insufficient"

    def _tier_message(self, tier: str, score: int) -> str:
        """Human-readable message for the worker's tier."""
        messages = {
            "insufficient": "Keep recording transactions to build your score!",
            "emerging": f"Your score is {score}. You're building credit history.",
            "building": f"Score: {score}. You qualify for small loans.",
            "established": f"Score: {score}. You qualify for KSh 50,000 at 20% APR.",
            "strong": f"Score: {score}. Excellent! You qualify for KSh 100,000 at 18% APR.",
            "exceptional": f"Score: {score}. Outstanding! You qualify for KSh 250,000 at 18% APR.",
        }
        return messages.get(tier, "")
```

```python
# app/superagent/credit/device_engine.py

class DeviceAlamaEngine:
    """
    On-device Alama Score engine for the mobile SUPERAGENT.

    Runs entirely offline. Uses the local SQLite event store.
    Syncs score + gradients to backend when connected.

    Architecture:
    1. Worker speaks: "Sold 50 items today, revenue 3000"
    2. On-device ASR transcribes
    3. Transaction parser extracts structured data
    4. Local event store records the transaction
    5. Alama Score recomputes INSTANTLY from local history
    6. Worker sees their updated score immediately
    7. When connected: score + gradients sync to backend
    """

    def __init__(self, local_event_store: LocalEventStore):
        self.store = local_event_store
        self.engine = AlamaScoreEngine()

    def on_transaction_recorded(self, transaction: Transaction) -> AlamaScoreResult:
        """
        Called every time a voice transaction is recorded.
        Recomputes the score instantly from local history.
        """
        # 1. Store transaction locally
        self.store.append(transaction)

        # 2. Get all local transactions
        all_transactions = self.store.get_all()

        # 3. Recompute score (instant, no network)
        score = self.engine.compute_score_from_transactions(all_transactions)

        # 4. Cache the score locally
        self.store.set_cached_score(score)

        return score

    def get_current_score(self) -> AlamaScoreResult:
        """Get the current cached score (instant, no recomputation)."""
        cached = self.store.get_cached_score()
        if cached:
            return cached
        # Fallback: recompute from history
        all_transactions = self.store.get_all()
        return self.engine.compute_score_from_transactions(all_transactions)

    def get_score_breakdown(self) -> dict:
        """
        Get detailed breakdown of what's affecting the score.
        Shown to the worker as actionable feedback.
        """
        score = self.get_current_score()
        return {
            "score": score.score,
            "tier": score.tier,
            "signals": {
                "frequency": {
                    "value": score.signals["frequency"],
                    "weight": "20%",
                    "tip": "Record transactions every day for a higher score",
                },
                "revenue_trend": {
                    "value": score.signals["revenue_trend"],
                    "weight": "20%",
                    "tip": "Growing sales over time improves your score",
                },
                "margins": {
                    "value": score.signals["margins"],
                    "weight": "25%",
                    "tip": "Higher profit margins = better score",
                },
                "diversity": {
                    "value": score.signals["diversity"],
                    "weight": "10%",
                    "tip": "Selling different products reduces risk",
                },
                "regularity": {
                    "value": score.signals["regularity"],
                    "weight": "15%",
                    "tip": "Consistent daily activity builds trust",
                },
                "growth": {
                    "value": score.signals["growth"],
                    "weight": "10%",
                    "tip": "Month-over-month improvement shows potential",
                },
            },
            "max_loan": score.max_loan,
            "apr": score.apr,
            "next_tier": self._next_tier_hint(score.tier),
        }
```

### 6.4 Distribution Intelligence Pipeline

**What it does:** Identifies where FMCG products are NOT reaching — market coverage gaps.

**Input:** Aggregated transaction events, geographic data.

**Output:** Coverage maps, expansion recommendations, ROI projections.

**Buyers:** FMCG distribution companies.

```python
# app/superagent/financial/pipelines/distribution_gaps.py

class DistributionIntelligencePipeline:
    """
    Distribution Intelligence — Market Coverage Gap Analysis.

    Pipeline stages:
    1. Market Mapping: Identify all active markets from event data
    2. Coverage Analysis: Product presence vs. market potential
    3. HHI Concentration: Market structure analysis
    4. Gap Identification: Underserved markets with demand signals
    5. Route Optimization: Efficient distribution paths
    6. ROI Projection: Expected return on distribution expansion

    Refactored from:
    - app/services/intelligence/distribution_gap.py (core analysis)
    - app/services/intelligence/fmcg_intelligence.py (FMCG tracking)
    """

    async def analyze(
        self,
        company: str,
        region: str,
        product_category: str,
    ) -> DistributionReport:
        """Analyze distribution gaps for a product category in a region."""
        # 1. Map active markets from event store
        markets = await self._map_active_markets(region, product_category)

        # 2. Coverage analysis
        coverage = self._analyze_coverage(markets, product_category)

        # 3. HHI concentration
        hhi = self._compute_hhi(markets)

        # 4. Gap identification
        gaps = self._identify_gaps(markets, coverage)

        # 5. Route optimization
        routes = self._optimize_routes(gaps, markets)

        # 6. ROI projection
        roi = self._project_roi(gaps, routes)

        return DistributionReport(
            region=region,
            category=product_category,
            active_markets=len(markets),
            coverage_pct=coverage.coverage_percentage,
            hhi=hhi,
            gaps=gaps,
            recommended_routes=routes,
            roi_projection=roi,
        )
```

### 6.5 Jamii Insights Pipeline (NEW)

**What it does:** Financial inclusion metrics for government and NGOs. Aggregates anonymized transaction data across regions to measure economic activity, financial inclusion, and poverty indicators.

**Input:** Aggregated anonymized transaction events from the event store (k-anonymity enforced, no individual data).

**Output:** Regional financial inclusion indices, economic activity metrics, poverty headcount estimates, giving/tithe patterns.

**Buyers:** Government (Treasury, Central Bank), NGOs (World Bank, FSD Kenya, CGAP), development finance institutions.

```python
# app/superagent/inclusion/jamii_insights.py

class JamiiInsightsPipeline:
    """
    Jamii Insights — Financial Inclusion Intelligence.

    Pipeline stages:
    1. Regional Aggregation: Aggregate transactions by region (k-anonymity enforced)
    2. Financial Inclusion Index: % of population with active transaction history
    3. Economic Activity Index: Transaction volume, frequency, diversity per region
    4. Poverty Headcount Proxy: Based on transaction size distributions
    5. Giving/Tithe Patterns: Charitable and religious giving trends
    6. Gender Gap Analysis: Male vs female business activity (where identifiable)
    7. Trend Analysis: Month-over-month changes in inclusion metrics

    Refactored from:
    - app/services/intelligence/jamii_insights.py
    - app/services/intelligence/giving_insights.py
    - app/services/intelligence/health_economics.py
    """

    async def generate_regional_report(
        self,
        region: str,
        period_months: int = 12,
    ) -> JamiiInsightsReport:
        """Generate financial inclusion report for a region."""
        # 1. Pull aggregated events (k-anonymity enforced)
        aggregates = await self.private_aggregator.aggregate_for_region(
            region=region,
            metrics=["transaction_count", "total_volume", "unique_workers"],
            time_window=timedelta(days=period_months * 30),
        )

        # 2. Financial inclusion index
        inclusion_index = self._compute_inclusion_index(aggregates)

        # 3. Economic activity index
        activity_index = self._compute_activity_index(aggregates)

        # 4. Poverty headcount proxy
        poverty_proxy = self._estimate_poverty_headcount(aggregates)

        # 5. Giving/tithe patterns
        giving_patterns = self._analyze_giving_patterns(aggregates)

        # 6. Trend analysis
        trends = await self._compute_trends(region, period_months)

        return JamiiInsightsReport(
            region=region,
            period_months=period_months,
            inclusion_index=inclusion_index,
            economic_activity_index=activity_index,
            poverty_headcount_proxy=poverty_proxy,
            giving_patterns=giving_patterns,
            trends=trends,
            privacy_params=aggregates.privacy_params,
            report_version="1.0",
        )
```

### 6.6 How Products Feed Back to Mobile SUPERAGENT

```
Backend Intelligence Products
         │
         ▼
┌─────────────────────────────────────────────────┐
│              RESPONSE FORMATTER                   │
│                                                   │
│  Soko Pulse ──▶ "Unga prices will rise 12%       │
│                  next week. Stock up now."         │
│                                                   │
│  Alama Score ──▶ "Your biashara score is 720.     │
│                   You qualify for KSh 50,000 loan." │
│                                                   │
│  Distribution ──▶ "3 markets near you need        │
│                    cooking oil. Supplier X has      │
│                    the best price."                 │
└───────────────────────┬─────────────────────────┘
                        │
              Voice / Text Response
                        │
┌───────────────────────▼─────────────────────────┐
│           MOBILE SUPERAGENT                       │
│                                                   │
│  Receives structured intelligence                 │
│  Presents to worker in their language             │
│  Logs interaction as learning event               │
│  Trains personal LoRA adapter on the interaction  │
└─────────────────────────────────────────────────┘
```

---

## 7. Event Sourcing Architecture

### 7.1 Why Event Sourcing (M-KOPA Lesson)

M-KOPA's breakthrough insight: **every micro-interaction is a proof point**. A daily payment of KSh 50 isn't just a transaction — it's evidence of consistency, reliability, and financial discipline. Over 365 days, those 365 proof points become a credit score more accurate than any bureau report.

The current system uses events as messages — consumed and forgotten. Event sourcing makes events the **source of truth**:

1. **Every interaction is a proof point**: Voice commands, transactions, corrections, questions — each one builds the worker's financial story
2. **Replay**: Reconstruct any worker's state by replaying their events
3. **Audit**: Full history of every decision (critical for financial products)
4. **Learning**: Every interaction becomes a training signal for the global model
5. **Debugging**: Trace any intelligence product back to its source events
6. **Analytics**: ClickHouse OLAP queries over the full event history
7. **Credit building**: Transaction history IS the credit score — the event store IS the credit bureau
8. **Scale**: M-KOPA handles 2M payments/day — the event store must handle 2M+ events/day

**Event Store Growth Trajectory:**

| Year | Events/Day | Events/Month | ClickHouse Storage | Strategy |
|------|-----------|--------------|-------------------|----------|
| Today | 500 | 15K | ~1 MB | Single ClickHouse, no sharding |
| Year 1 | 5,000 | 150K | ~10 MB | Single ClickHouse, daily partitions |
| Year 3 | 500,000 | 15M | ~1 GB | 3-shard cluster, region sharding |
| Year 5 | 5,000,000 | 150M | ~10 GB | 6-shard cluster, S3 cold storage |

**Key Design Decision:** The event schema and query patterns are identical at every scale. A query that works on 500 events today works on 5M events in Year 5. ClickHouse's MergeTree engine handles this natively — same table definition, same queries, different infrastructure.

### 7.2 Event Schema

```python
# app/models/orm/event.py

class DomainEvent(Base):
    """
    Immutable event in the event store.

    Stored in ClickHouse for OLAP analytics.
    Every event has:
    - Unique ID (UUIDv7 for time-ordered uniqueness)
    - Type (what happened)
    - Aggregate ID (which worker/entity)
    - Payload (what data)
    - Metadata (who, when, how)
    - Version (for optimistic concurrency)
    """
    __tablename__ = "domain_events"

    # Primary key
    event_id = Column(String(36), primary_key=True)  # UUIDv7

    # Event classification
    event_type = Column(String(100), nullable=False, index=True)
    event_category = Column(String(50), nullable=False, index=True)

    # Aggregate
    aggregate_type = Column(String(50), nullable=False)  # "worker", "market", "product"
    aggregate_id = Column(String(100), nullable=False, index=True)

    # Payload
    payload = Column(JSON, nullable=False)

    # Metadata
    worker_id = Column(String(100), nullable=True, index=True)
    device_id_hash = Column(String(64), nullable=True)
    channel = Column(String(20), nullable=True)  # "voice", "text", "transaction"
    region = Column(String(50), nullable=True, index=True)
    language = Column(String(10), nullable=True)

    # Timestamps
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    recorded_at = Column(DateTime(timezone=True), nullable=False)

    # Event sourcing
    version = Column(Integer, nullable=False, default=1)
    causation_id = Column(String(36), nullable=True)   # What caused this event
    correlation_id = Column(String(36), nullable=True)  # Request correlation
```

### 7.3 Event Types (Taxonomy)

```python
# app/superagent/core/events.py

class EventCategory(StrEnum):
    TRANSACTION = "transaction"      # Financial transactions
    INTERACTION = "interaction"      # Voice/text interactions
    INTELLIGENCE = "intelligence"    # Intelligence product generation
    LEARNING = "learning"           # FL updates, corrections
    SYNC = "sync"                   # Device sync events
    SYSTEM = "system"               # System events (startup, errors)

# Transaction Events
"transaction.recorded"       # New sale/purchase recorded
"transaction.processed"      # Transaction validated and categorized
"transaction.batch_synced"   # Batch of transactions synced from device

# Interaction Events
"interaction.voice_received" # Voice message from worker
"interaction.voice_transcribed" # ASR transcription complete
"interaction.text_received"  # Text message from worker
"interaction.response_sent"  # Response delivered to worker

# Intelligence Events
"intelligence.soko_pulse.generated"    # Soko Pulse forecast created
"intelligence.alama_score.computed"    # Alama Score computed
"intelligence.distribution.analyzed"   # Distribution gap analysis done
"intelligence.alert.triggered"         # Market alert generated

# Learning Events
"learning.gradient_submitted"   # Device submitted gradient update
"learning.gradient_aggregated"  # Round aggregation complete
"learning.model_updated"        # Global model version bumped
"learning.correction_received"  # Worker corrected a mistake

# Sync Events
"sync.device_connected"     # Device came online
"sync.delta_applied"        # Delta sync completed
"sync.conflict_resolved"    # Sync conflict resolved
```

### 7.4 Event Store Implementation

```python
# app/infrastructure/event_store.py

class EventStore:
    """
    Event sourcing store backed by ClickHouse.

    ClickHouse is ideal for event sourcing because:
    - Column-oriented: Fast analytics over event history
    - Append-only: Events are immutable by design
    - Time-partitioned: Natural time-series partitioning
    - Compression: ~10x compression on event payloads

    Storage strategy:
    - Hot events (last 7 days): ClickHouse memory buffer
    - Warm events (7-90 days): ClickHouse disk
    - Cold events (90+ days): ClickHouse + S3 tiered storage

    Query patterns:
    - By worker: WHERE worker_id = ? ORDER BY occurred_at
    - By type: WHERE event_type = ? ORDER BY occurred_at
    - By region: WHERE region = ? AND occurred_at BETWEEN ? AND ?
    - Aggregate: GROUP BY event_type, region, date
    """

    async def append(self, event: DomainEvent) -> None:
        """Append an immutable event to the store."""
        ...

    async def query(
        self,
        worker_id: str | None = None,
        event_types: list[str] | None = None,
        region: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1000,
    ) -> list[DomainEvent]:
        """Query events with filters."""
        ...

    async def query_aggregated(
        self,
        region: str,
        category: str,
        since: datetime,
        aggregation: str = "daily",
    ) -> AggregatedEvents:
        """Query pre-aggregated events for intelligence pipelines."""
        ...

    async def get_worker_timeline(
        self,
        worker_id: str,
        limit: int = 100,
    ) -> list[DomainEvent]:
        """Get chronological event timeline for a worker."""
        ...

    async def replay(
        self,
        aggregate_id: str,
        aggregate_type: str,
        up_to: datetime | None = None,
    ) -> list[DomainEvent]:
        """Replay all events for an aggregate to reconstruct state."""
        ...
```

### 7.5 ClickHouse Schema for Events

```sql
-- ClickHouse event store table
CREATE TABLE IF NOT EXISTS domain_events (
    event_id String,
    event_type LowCardinality(String),
    event_category LowCardinality(String),
    aggregate_type LowCardinality(String),
    aggregate_id String,
    payload String,  -- JSON-encoded
    worker_id String,
    device_id_hash String,
    channel LowCardinality(String),
    region LowCardinality(String),
    language LowCardinality(String),
    occurred_at DateTime64(3, 'UTC'),
    recorded_at DateTime64(3, 'UTC'),
    version UInt32,
    causation_id String,
    correlation_id String
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (event_type, region, occurred_at, aggregate_id)
TTL occurred_at + INTERVAL 2 YEAR
SETTINGS index_granularity = 8192;

-- Materialized view for daily aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS domain_events_daily
ENGINE = SummingMergeTree()
PARTITION BY toYYYYMM(day)
ORDER BY (event_type, region, day)
AS SELECT
    event_type,
    region,
    toDate(occurred_at) AS day,
    count() AS event_count,
    uniqState(worker_id) AS unique_workers
FROM domain_events
GROUP BY event_type, region, day;
```

### 7.6 Event-Driven Flywheel (M-KOPA Model)

M-KOPA proved: daily micro-interactions at scale build an unstoppable data flywheel. Each interaction is a proof point. More proof points → better intelligence → more users → more proof points.

```
┌─────────────────────────────────────────────────────────────────┐
│                THE ANGAVU DATA FLYWHEEL                         │
│                (M-KOPA Model: 10M customers, 2M payments/day)   │
│                                                                 │
│  WORKER USES SUPERAGENT (daily interaction)                     │
│         │                                                       │
│         ▼                                                       │
│  EVENT RECORDED (transaction, voice, question)                  │
│  Each transaction is a proof point:                             │
│  "I sold 50 items" / "Revenue was KSh 3,000" / "90 days active"│
│         │                                                       │
│         ▼                                                       │
│  INTELLIGENCE GENERATED (Alama Score, Soko Pulse)               │
│  Transaction history IS the credit score:                       │
│  Frequency→consistency / Trend→growth / Margins→health          │
│         │                                                       │
│         ▼                                                       │
│  VALUE DELIVERED (loan offer, price alert, score update)        │
│  "Your score is 720 — qualify for KSh 50K loan"                │
│         │                                                       │
│         ▼                                                       │
│  WORKER STAYS ENGAGED (daily usage continues)                   │
│  More transactions = higher score = better terms = more usage   │
│         │                                                       │
│         └──────────────────▶ FLYWHEEL SPINS FASTER              │
│                              More workers → more data           │
│                              → better models → better scores    │
│                              → more workers (repeat)            │
│                                                                 │
│  Angavu Target: 1M workers, 2M+ daily interactions              │
└─────────────────────────────────────────────────────────────────┘
```

### 7.7 Progressive Service Stacking (M-KOPA Model)

M-KOPA stacked services: asset tracking → credit → insurance → financial services. Each layer depends on the one below. Angavu does the same:

```
LAYER 4: MARKET INTELLIGENCE (Premium)
├── Soko Pulse demand forecasting for FMCG companies
├── Distribution gap analysis for manufacturers
├── Requires: 1000+ workers in region, 6+ months data
└── Revenue: B2B SaaS licensing
       ▲ depends on
LAYER 3: CREDIT INTELLIGENCE (Alama Score)
├── Transaction-based credit scoring (300-850)
├── Loan recommendations and offers
├── Requires: 30+ transactions, 14+ days history
└── Revenue: Per-score licensing to banks/MFIs
       ▲ depends on
LAYER 2: FINANCIAL TRACKING (Free + Premium)
├── Daily transaction recording (voice, M-Pesa, manual)
├── Revenue/expense summaries
├── Requires: Active SUPERAGENT usage
└── Revenue: Freemium (basic free, advanced paid)
       ▲ depends on
LAYER 1: ONBOARDING & ENGAGEMENT (Free)
├── Voice-first interaction in local language
├── M-Pesa integration
├── Requires: Nothing — entry point
└── Revenue: None (acquisition cost — generates the data flywheel)

Key Insight (M-KOPA): Layer 1 is FREE because it generates the
data that makes Layers 2-4 valuable. The flywheel starts here.
```

### 7.8 Progressive Unlocking Logic

```python
# app/superagent/credit/progressive.py

class ProgressiveServiceUnlocker:
    """
    M-KOPA-style progressive service unlocking.

    Workers unlock higher-value services as their transaction
    history grows. This incentivizes continued usage and builds
    the data flywheel.
    """

    UNLOCK_THRESHOLDS = {
        "financial_insights": {"min_transactions": 0, "min_days": 7, "min_consistency": 0.0},
        "credit_score": {"min_transactions": 30, "min_days": 14, "min_consistency": 0.3},
        "loan_offers": {"min_transactions": 90, "min_days": 60, "min_consistency": 0.5},
        "premium_intelligence": {"min_transactions": 180, "min_days": 90, "min_consistency": 0.6},
    }

    async def get_unlocked_services(self, worker_id: str) -> dict[str, bool]:
        """Check which services are unlocked for a worker."""
        patterns = await self.event_store.get_transaction_patterns(worker_id)
        unlocked = {"basic_tracking": True}  # Always available
        for service, thresholds in self.UNLOCK_THRESHOLDS.items():
            unlocked[service] = (
                patterns.transaction_count >= thresholds["min_transactions"]
                and patterns.history_days >= thresholds["min_days"]
                and patterns.regularity >= thresholds["min_consistency"]
            )
        return unlocked
```

---

## 8. Data Pipeline & Privacy

### 8.1 Ingestion Layer (Growth Trajectory: 500 → 5M Events/Day)

The ingestion layer must handle the full growth trajectory. Today: 500 events/day on a single server. Year 5: 5M events/day on a sharded cluster. Same codebase, different infrastructure.

**Growth-Aware Design:**
- **Today (500/day)**: Direct ClickHouse insert, no buffering needed
- **Year 1 (5K/day)**: Redis Streams buffer with 5-second batch window
- **Year 3 (500K/day)**: Redis Streams buffer with 1-second batch window, ClickHouse 3-shard
- **Year 5 (5M/day)**: Redis Streams buffer with 500ms batch window, ClickHouse 6-shard, S3 cold storage

The batch window shrinks as volume grows, but the code path is identical.

**Ingestion Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    INGESTION PIPELINE                           │
│                    (Designed for 2M+ events/day)                │
│                                                                 │
│  Sources:                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ M-Pesa   │ │ Voice    │ │ Text     │ │ Device   │          │
│  │ Callbacks│ │ Transcr. │ │ Messages │ │ Sync     │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
│       └─────────────┴─────────────┴─────────────┘               │
│                          │                                      │
│                          ▼                                      │
│              ┌───────────────────────┐                          │
│              │  Redis Stream Buffer  │  (1-second batch window) │
│              │  biashara:ingest:*    │                          │
│              └───────────┬───────────┘                          │
│                          │                                      │
│                          ▼                                      │
│              ┌───────────────────────┐                          │
│              │  Batch Inserter       │  (ClickHouse batch INSERT)│
│              │  1000 events/batch    │  ~25K events/sec          │
│              └───────────┬───────────┘                          │
│                          │                                      │
│                          ▼                                      │
│              ┌───────────────────────┐                          │
│              │  ClickHouse Event     │                          │
│              │  Store                │                          │
│              └───────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

```python
# app/data/ingestion/transaction_ingester.py

class TransactionIngester:
    """
    Ingests transactions from multiple sources into the event store.

    M-KOPA scale design: Events are buffered in Redis Streams
    and batch-inserted into ClickHouse every 1 second.
    This achieves ~25K writes/sec vs ~500/sec for row-by-row.

    Sources:
    - M-Pesa STK push callbacks (real-time)
    - M-Pesa SMS parsing (batch)
    - Voice transcription (real-time)
    - Manual entry via SUPERAGENT (real-time)
    - Batch sync from device (delta sync)

    Every ingested transaction becomes an immutable event.
    Every event is a proof point in the worker's financial story.
    """

    async def ingest_mpesa_callback(self, callback: MpesaCallback) -> DomainEvent:
        """Ingest M-Pesa STK push callback."""
        event = DomainEvent(
            event_type="transaction.recorded",
            event_category="transaction",
            aggregate_type="worker",
            aggregate_id=callback.account_reference,
            payload={
                "amount": callback.amount,
                "phone_hash": self._hash_phone(callback.phone),
                "mpesa_receipt": callback.receipt,
                "transaction_type": "mpesa_stk",
                "direction": "incoming" if callback.amount > 0 else "outgoing",
            },
            channel="mpesa",
            occurred_at=callback.timestamp,
        )
        await self.event_store.append(event)
        return event

    async def ingest_voice_transaction(
        self, transcription: Transcription
    ) -> DomainEvent:
        """Ingest transaction parsed from voice input."""
        parsed = await self._parse_transaction(transcription.text)
        event = DomainEvent(
            event_type="transaction.recorded",
            event_category="transaction",
            aggregate_type="worker",
            aggregate_id=transcription.worker_id,
            payload={
                "amount": parsed.amount,
                "product": parsed.product,
                "category": parsed.category,
                "customer_type": parsed.customer_type,
                "source": "voice",
                "transcription_confidence": transcription.confidence,
            },
            channel="voice",
            language=transcription.language,
            occurred_at=transcription.timestamp,
        )
        await self.event_store.append(event)
        return event
```

### 8.2 Privacy-Preserving Aggregation

```python
# app/data/aggregation/private_aggregator.py

class PrivateAggregator:
    """
    Privacy-preserving aggregation for intelligence products.

    Ensures k-anonymity (k≥10) and differential privacy (ε=0.1)
    before any data is used in intelligence products.

    Aggregation pipeline:
    1. Group workers into cohorts (by region, business type, size)
    2. Check k-anonymity: each cohort must have ≥k members
    3. Compute aggregate statistics (mean, variance, percentiles)
    4. Add calibrated Gaussian noise for differential privacy
    5. Return noisy aggregates to intelligence pipelines
    """

    K_ANONYMITY_THRESHOLD = 10
    DP_EPSILON = 0.1
    DP_DELTA = 1e-5

    async def aggregate_for_region(
        self,
        region: str,
        metric: str,
        time_window: timedelta,
    ) -> NoisyAggregate:
        """Aggregate a metric across a region with privacy guarantees."""
        # 1. Get cohort
        cohort = await self._build_cohort(region, time_window)

        # 2. k-anonymity check
        if len(cohort) < self.K_ANONYMITY_THRESHOLD:
            raise PrivacyError(
                f"Cohort size {len(cohort)} < k={self.K_ANONYMITY_THRESHOLD}"
            )

        # 3. Compute aggregate
        values = [getattr(w, metric) for w in cohort]
        aggregate = {
            "mean": np.mean(values),
            "std": np.std(values),
            "median": np.median(values),
            "count": len(values),
        }

        # 4. Add DP noise
        sensitivity = (max(values) - min(values)) / len(values)
        noise_scale = sensitivity * np.sqrt(2 * np.log(1.25 / self.DP_DELTA)) / self.DP_EPSILON
        for key in ["mean", "std", "median"]:
            aggregate[key] += np.random.normal(0, noise_scale)

        return NoisyAggregate(
            region=region,
            metric=metric,
            values=aggregate,
            privacy_params={
                "k": self.K_ANONYMITY_THRESHOLD,
                "epsilon": self.DP_EPSILON,
                "delta": self.DP_DELTA,
                "noise_scale": noise_scale,
            },
        )
```

### 8.3 Privacy Layers

| Layer | Access Level | Description |
|-------|-------------|-------------|
| Layer 1 (Raw) | User + System only | Full data with PII, encrypted at rest |
| Layer 2 (Internal) | Backend services | Pseudonymized (hashed IDs) |
| Layer 3 (Licensed) | Intelligence buyers | k-anonymity (k≥10) enforced |
| Layer 4 (Public) | Everyone | Aggregated statistics only |

---

## 9. Device Sync Service

### 9.1 Sync Protocol (Including Alama Score Sync)

The SUPERAGENT mobile app works offline-first. The sync service handles bidirectional data flow. **Alama Score is computed on-device and synced to the backend for validation and cohort comparison.**

```python
# app/sync/sync_service.py

class DeviceSyncService:
    """
    Bidirectional sync between mobile SUPERAGENT and backend.

    Protocol:
    1. Device connects and sends sync checkpoint (last synced event ID)
    2. Backend sends delta (events since checkpoint)
    3. Device sends its delta (new transactions, Alama Score, gradients)
    4. Backend applies device events to event store
    5. Backend validates device Alama Score, adds cohort comparison
    6. Conflicts resolved via CRDT (last-write-wins with vector clocks)

    Sync types:
    - Transaction sync: Device → Backend (new transactions)
    - Alama Score sync: Device → Backend (computed score + signal data)
    - Intelligence sync: Backend → Device (forecasts, cohort benchmarks)
    - Model sync: Backend → Device (global LoRA adapter)
    - Feedback sync: Device → Backend (corrections, ratings)
    """

    async def sync(
        self,
        device_id_hash: str,
        checkpoint: SyncCheckpoint,
        device_events: list[DomainEvent],
        device_alama_score: AlamaScoreResult | None = None,
    ) -> SyncResponse:
        """Execute a sync cycle."""
        # 1. Get events since checkpoint
        backend_events = await self.event_store.query(
            since_event_id=checkpoint.last_event_id,
            worker_id=checkpoint.worker_id,
            limit=1000,
        )

        # 2. Apply device events
        conflicts = []
        for event in device_events:
            conflict = await self._apply_device_event(event)
            if conflict:
                conflicts.append(conflict)

        # 3. Resolve conflicts
        resolved = [self.conflict_resolver.resolve(c) for c in conflicts]

        # 4. Validate device Alama Score (if provided)
        alama_validation = None
        if device_alama_score:
            alama_validation = await self._validate_alama_score(
                worker_id=checkpoint.worker_id,
                device_score=device_alama_score,
            )

        # 5. Build response
        return SyncResponse(
            events=backend_events,
            conflicts_resolved=resolved,
            new_checkpoint=SyncCheckpoint(
                last_event_id=backend_events[-1].event_id if backend_events else checkpoint.last_event_id,
                timestamp=datetime.now(UTC),
            ),
            model_update=await self._get_model_update(device_id_hash),
            alama_validation=alama_validation,
            cohort_benchmarks=await self._get_cohort_benchmarks(checkpoint.worker_id),
        )

    async def _validate_alama_score(
        self,
        worker_id: str,

        device_score: AlamaScoreResult,
    ) -> AlamaValidation:
        """
        Validate the device-computed Alama Score against backend data.

        Backend adds value by:
        1. Comparing to cohort (how does this worker compare to peers?)
        2. Regional benchmarks (average margins in this region)
        3. Industry risk adjustment (agriculture vs retail risk)
        4. Loan product matching (which lenders serve this tier?)
        """
        # Recompute from backend event store
        backend_score = await self.alama_engine.compute_score(worker_id)

        # Compare device vs backend scores
        score_diff = abs(device_score.score - backend_score.score)

        # Get cohort comparison
        cohort = await self._get_cohort_stats(worker_id, device_score.tier)

        return AlamaValidation(
            device_score=device_score.score,
            backend_score=backend_score.score,
            score_diff=score_diff,
            is_valid=score_diff <= 50,  # Allow 50-point tolerance
            cohort_percentile=cohort.percentile,
            regional_benchmarks=cohort.benchmarks,
            recommended_lenders=await self._match_lenders(device_score),
        )
```

### 9.2 Delta Sync

```python
# app/sync/delta_sync.py

class DeltaSyncEngine:
    """
    Efficient delta-based sync — only send what changed.

    Uses event IDs as cursors. The device sends its last known
    event ID, and the backend sends only newer events.

    For large datasets, uses pagination:
    - First sync: Stream events in batches of 100
    - Subsequent syncs: Only new events (typically <10 per sync)
    - Compression: gzip on the wire
    """
```

---

## 10. API Design

### 10.1 API v1 Endpoints (Refactored)

```yaml
# Authentication (keep)
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/otp/request
POST   /api/v1/auth/otp/verify

# Superagent (NEW — unified intelligence)
POST   /api/v1/superagent/process          # Process any interaction
POST   /api/v1/superagent/voice             # Voice input endpoint
POST   /api/v1/superagent/text              # Text input endpoint
GET    /api/v1/superagent/context/{worker_id}  # Get worker context
POST   /api/v1/superagent/feedback          # Submit feedback

# Intelligence Products (refactored)
GET    /api/v1/intelligence/soko-pulse/{region}/{category}  # Soko Pulse forecast
GET    /api/v1/intelligence/alama-score/{worker_id}         # Alama Score
GET    /api/v1/intelligence/distribution/{company}/{region}  # Distribution gaps
GET    /api/v1/intelligence/fmcg/{company}/{region}          # FMCG intelligence
GET    /api/v1/intelligence/explain/{product_id}             # SHAP explainability

# Federated Learning (refactored for LoRA)
GET    /api/v1/fl/status                   # FL system status
GET    /api/v1/fl/pqc-public-key           # PQC public key for devices
POST   /api/v1/fl/upload-update            # Submit gradient update
GET    /api/v1/fl/global-model/{dialect}   # Download global adapter
GET    /api/v1/fl/rounds                   # FL round history

# Device Sync (refactored)
POST   /api/v1/sync/delta                  # Delta sync
GET    /api/v1/sync/status                 # Sync status
POST   /api/v1/sync/conflict/resolve       # Manual conflict resolution

# Events (NEW — event sourcing API)
GET    /api/v1/events/query                # Query events
GET    /api/v1/events/timeline/{worker_id} # Worker event timeline
GET    /api/v1/events/aggregate            # Aggregated event stats
POST   /api/v1/events/replay               # Replay events for state reconstruction

# Transactions (keep)
GET    /api/v1/transactions/{worker_id}
POST   /api/v1/transactions
GET    /api/v1/transactions/summary/{worker_id}

# Users (keep)
GET    /api/v1/users/{worker_id}
PUT    /api/v1/users/{worker_id}

# Market Data (keep)
GET    /api/v1/market/prices/{region}
GET    /api/v1/market/products

# Webhooks (NEW)
POST   /api/v1/webhooks/mpesa             # M-Pesa callback
POST   /api/v1/webhooks/whatsapp          # WhatsApp webhook
```

### 10.2 Superagent Process Endpoint

```python
# app/api/v1/superagent.py

@router.post("/superagent/process")
async def process_interaction(
    request: ProcessRequest,
    engine: SuperagentEngine = Depends(get_engine),
    current_user: User = Depends(get_current_user),
) -> ProcessResponse:
    """
    Process any interaction through the SUPERAGENT platform.

    This is the unified entry point for all worker interactions.
    The engine classifies intent, routes to the appropriate pipeline,
    and returns an intelligence-enhanced response.

    Accepts:
    - Voice messages (audio URL or base64)
    - Text messages
    - Transaction data
    - Feedback/corrections
    """
    event = DomainEvent(
        event_type=f"interaction.{request.channel}_received",
        event_category="interaction",
        aggregate_type="worker",
        aggregate_id=current_user.id,
        payload=request.dict(),
        channel=request.channel,
        worker_id=current_user.id,
    )

    response = await engine.process(event)

    return ProcessResponse(
        response_text=response.text,
        response_voice_url=response.voice_url,
        intelligence=response.intelligence,
        suggestions=response.suggestions,
    )
```

---

## 11. Infrastructure & Scaling

### 11.1 Database Architecture

| Store | Technology | Purpose | Data |
|-------|-----------|---------|------|
| Primary | PostgreSQL | OLTP, user data, transactions | Users, transactions, intelligence products |
| Analytics | ClickHouse | OLAP, event store, aggregations | Domain events, aggregated stats, time series |
| Cache | Redis | Hot data, session, rate limiting | Worker context, FL state, rate limits |
| Queue | Redis Streams | Async processing, event bus | Task queue, event bus, FL updates |
| Object | S3/MinIO | File storage | Audio files, model weights, reports |

### 11.2 ClickHouse Expansion

The existing ClickHouse setup (`app/db/clickhouse.py`) needs expansion for event sourcing:

```python
# New ClickHouse tables:
# - domain_events (core event store)
# - domain_events_daily (materialized aggregate view)
# - fl_rounds (federated learning round tracking)
# - intelligence_outputs (intelligence product outputs)
# - sync_checkpoints (device sync state)
```

### 11.3 Redis Usage

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `worker:{id}:context` | Worker context cache | 1 hour |
| `fl:round:{dialect}:status` | Current FL round status | Until round complete |
| `fl:gradients:{round_id}` | Pending gradients for aggregation | 24 hours |
| `sync:checkpoint:{device_id}` | Last sync checkpoint | None |
| `rate:{ip}:count` | Rate limiting counter | 1 minute |
| `session:{token}` | Active session | 30 minutes |

### 11.4 Scaling Strategy (Growth Trajectory: 500 → 5M Events/Day)

M-KOPA processed 2M payments/day → built credit scores for 10M people. Msaidizi processes voice transactions → builds business intelligence for informal workers. The data pipeline must be designed for this growth trajectory:

**Growth Trajectory:**

| Phase | Workers | Events/Worker/Day | Total Events/Day | Events/Sec (peak) |
|-------|---------|-------------------|------------------|-------------------|
| **Today** | 100 | 5 | 500 | ~0.01 |
| **Year 1** | 1,000 | 5 | 5,000 | ~0.1 |
| **Year 3** | 100,000 | 5 | 500,000 | ~10 |
| **Year 5** | 1,000,000 | 5 | 5,000,000 | ~100 |

**Infrastructure Phases:**

| Phase | PostgreSQL | ClickHouse | Redis | Cost/Month |
|-------|-----------|------------|-------|------------|
| **Today** | SQLite | None | In-memory | ~$0 |
| **Year 1** | Single PostgreSQL | Single ClickHouse | Single Redis | ~$50 |
| **Year 3** | Primary + 2 replicas | 3-shard cluster | 6-node cluster | ~$500 |
| **Year 5** | Sharded + read replicas | 6-shard cluster | 12-node cluster | ~$3,000 |

**Key Insight:** The same codebase runs at every phase. The architecture is designed for Year 5 but deploys for today. Scaling is a configuration change, not a rewrite.

**Architecture at Each Phase:**

```
TODAY (500 events/day)          YEAR 1 (5K events/day)
┌──────────────────┐            ┌──────────────────┐
│  Single Server   │            │  nginx + 1 API   │
│  FastAPI + SQLite│            │  PostgreSQL      │
│  In-memory cache │            │  ClickHouse single│
│                  │            │  Redis single    │
└──────────────────┘            └──────────────────┘
        │                               │
        │ Grows to →                    │ Grows to →
        ▼                               ▼
YEAR 3 (500K events/day)        YEAR 5 (5M events/day)
┌──────────────────┐            ┌──────────────────────────┐
│  nginx LB        │            │  nginx LB (geo-distributed)│
│  3 API servers   │            │  10+ API servers          │
│  PG primary+2    │            │  PG sharded + replicas    │
│  CH 3-shard      │            │  CH 6-shard cluster       │
│  Redis 6-node    │            │  Redis 12-node cluster    │
│                  │            │  S3 cold storage          │
└──────────────────┘            └──────────────────────────┘
```

**Year 5 Architecture (Target State):**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    NGINX LOAD BALANCER                              │
│                    (rate limiting, SSL termination)                 │
└──────────┬──────────────┬──────────────┬────────────────────────────┘
           │              │              │
   ┌───────▼───────┐ ┌────▼──────┐ ┌────▼──────┐
   │  API Server   │ │ API Server│ │ API Server│  (10+ instances)
   │  (FastAPI +   │ │           │ │           │  Auto-scaled on
   │   uvicorn)    │ │           │ │           │  CPU/request count
   └───────┬───────┘ └────┬──────┘ └────┬──────┘
           │              │              │
   ┌───────▼──────────────▼──────────────▼───────┐
   │              Redis Cluster (12 nodes)        │
   │  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
   │  │ Cache   │ │ Streams  │ │ Session      │  │
   │  │ (hot    │ │ (event   │ │ Store        │  │
   │  │  data)  │ │  bus +   │ │ (JWT + OTP)  │  │
   │  │         │ │  FL)     │ │              │  │
   │  └─────────┘ └──────────┘ └──────────────┘  │
   └──────────┬──────────────────────┬────────────┘
              │                      │
   ┌──────────▼──────────┐ ┌────────▼────────────┐
   │  PostgreSQL         │ │  ClickHouse Cluster  │
   │  Sharded +          │ │  (6 shards,          │
   │  Read Replicas      │ │   2 replicas each)   │
   │                     │ │                      │
   │  Users, Auth,       │ │  Event Store (5M/day)│
   │  Intelligence       │ │  Aggregations,       │
   │  Products           │ │  Time Series         │
   └─────────────────────┘ └──────────────────────┘
```

**Key Scaling Decisions:**

1. **ClickHouse batch inserts**: Events are buffered in Redis Streams (1-second window) and batch-inserted into ClickHouse. This achieves ~25K writes/sec vs ~500/sec for row-by-row inserts.

2. **Async everything**: All event processing, intelligence generation, and FL aggregation is async. No blocking calls in the request path.

3. **Read replicas**: PostgreSQL read replicas for intelligence queries. Primary handles writes only.

4. **ClickHouse sharding**: Events are sharded by `region` for parallel query execution. Each shard handles ~1/3 of Kenya's regions.

5. **Redis cluster mode**: Scales from single node (Year 1) to 12-node cluster (Year 5).

6. **Event store TTL**: Events older than 2 years move to S3 cold storage. ClickHouse TTL handles this automatically.

7. **Same codebase at every phase**: The architecture is designed for Year 5 but deploys for today. Scaling is a configuration change, not a rewrite.

---

## 12. Migration Map

### 12.1 What Gets Deleted

| Current Component | Location | Reason |
|---|---|---|
| 33 agent classes | `app/agents/` | Replaced by superagent modules |
| AgentFactory | `app/agents/factory.py` | No more multi-agent wiring |
| MetaAgent | `app/agents/meta_agent.py` | Replaced by core engine |
| Domain agents (6) | `app/agents/domain/` | Merged into intelligence pipelines |
| Utility agents (6) | `app/agents/utility/` | Merged into infrastructure |
| Governance agents (3) | `app/agents/governance/` | Merged into security layer |
| Research agents (3) | `app/agents/research/` | Merged into knowledge module |
| Communication protocols | `app/agents/communication/` | Direct function calls |
| DeerFlow integration | `app/deerflow/` | Not needed in unified architecture |
| Autonomous orchestrator | `app/autonomous/` | Merged into evolution module |
| Agent loops (ReAct, etc.) | `app/agents/loops/` | Core engine handles reasoning |

### 12.2 What Gets Refactored

| Current | New | Changes |
|---------|-----|---------|
| `app/services/intelligence/soko_pulse.py` | `app/superagent/financial/soko_pulse.py` | Remove SQLAlchemy session dependency, read from event store |
| `app/services/intelligence/alama_score.py` | `app/superagent/credit/alama_score.py` | Remove SQLAlchemy session dependency, read from event store |
| `app/services/intelligence/distribution_gap.py` | `app/superagent/financial/distribution.py` | Same pattern |
| `app/services/intelligence/fmcg_intelligence.py` | `app/superagent/financial/fmcg.py` | Same pattern |
| `app/services/federated_learning_v2.py` | `app/superagent/learning/aggregator.py` | Add LoRA support, keep PQC |
| `app/services/anonymizer.py` | `app/data/anonymization/anonymizer.py` | Extract into separate modules |
| `app/agents/event_bus.py` | `app/infrastructure/event_bus.py` | Add event store persistence |
| `app/services/statistical_foundation.py` | `app/superagent/core/math/statistical.py` | Keep algorithms, update interfaces |
| `app/services/econometric_engine.py` | `app/superagent/financial/engines/time_series.py` | Keep algorithms, update interfaces |
| `app/services/causal_inference.py` | `app/superagent/core/math/causal.py` | Keep algorithms |
| `app/services/ml/` | `app/models/ml/` | Keep as-is, update imports |
| `app/main.py` | `app/main.py` | Remove AgentFactory, simplify lifespan |

### 12.3 What Gets Kept As-Is

| Component | Location | Reason |
|---|---|---|
| Auth (JWT + OTP) | `app/api/auth.py`, `app/api/otp_auth.py` | Works fine |
| PQC encryption | `app/security/pqc/` | Critical security, no changes needed |
| Channel adapters | `app/channels/` | Multi-channel delivery is independent |
| ClickHouse client | `app/db/clickhouse.py` | Expand, don't replace |
| Redis cache | `app/infrastructure/cache.py` | Works fine |
| Circuit breaker | `app/infrastructure/circuit_breaker.py` | Works fine |
| Prometheus metrics | `app/infrastructure/metrics.py` | Works fine |
| OpenTelemetry | `app/infrastructure/telemetry.py` | Works fine |
| Rate limiter | `app/security/rate_limiter.py` | Works fine |
| Security middleware | `app/security/security_middleware.py` | Works fine |

### 12.4 Import Migration Table

```python
# OLD → NEW import paths

# Agents
from app.agents.base import BiasharaAgent           # DELETE (no more agents)
from app.agents.factory import AgentFactory          # DELETE
from app.agents.meta_agent import MetaAgent          # DELETE
from app.agents.event_bus import EventBus            # → from app.infrastructure.event_bus import EventBus

# Intelligence services
from app.services.intelligence.soko_pulse import SokoPulseService
# → from app.superagent.financial.soko_pulse import SokoPulseEngine

from app.services.intelligence.alama_score import AlamaScoreService
# → from app.superagent.credit.alama_score import AlamaScoreEngine

from app.services.intelligence.distribution_gap import DistributionGapService
# → from app.superagent.financial.distribution import DistributionEngine

from app.services.intelligence.fmcg_intelligence import FMCGIntelligenceService
# → from app.superagent.financial.fmcg import FMCGEngine

# Federated learning
from app.services.federated_learning import FederatedLearningService
# → from app.superagent.learning.aggregator import FedAvgAggregator

from app.services.federated_learning_v2 import AnonymizedUpdate
# → from app.superagent.learning.aggregator import EncryptedGradient

# Anonymization
from app.services.anonymizer import Anonymizer
# → from app.data.anonymization.anonymizer import Anonymizer

# Statistical
from app.services.statistical_foundation import bootstrap, kde_estimator
# → from app.superagent.core.math.statistical import bootstrap, kde_estimator

from app.services.econometric_engine import ARIMAModel
# → from app.superagent.financial.engines.time_series import ARIMAModel
```

---

## 13. Implementation Phases

### Phase 1: Foundation (Weeks 1-3)

**Goal:** Event store + core engine skeleton + refactored main.py

1. Create `app/infrastructure/event_store.py` with ClickHouse backend
2. Create ClickHouse event tables and materialized views
3. Create `app/superagent/core/engine.py` skeleton
4. Create `app/superagent/core/router.py` (intent classification)
5. Create `app/superagent/core/context.py` (worker context)
6. Refactor `app/main.py` — remove AgentFactory, wire superagent engine
7. Create `app/api/v1/superagent.py` endpoints
8. Create `app/api/v1/events.py` endpoints
9. Write tests for event store and core engine

**Deliverable:** Backend starts without agents. Event store records events. Superagent engine processes basic interactions.

### Phase 2: Intelligence Pipelines (Weeks 4-6)

**Goal:** Migrate intelligence services to pipeline architecture

1. Create `app/superagent/financial/soko_pulse.py` (refactored from service)
2. Create `app/superagent/credit/alama_score.py` (refactored from service)
3. Create `app/superagent/financial/distribution.py` (refactored from service)
4. Create shared feature extraction layer
5. Wire pipelines to event store (read from events, not SQL)
6. Update API endpoints to use pipelines
7. Write integration tests

**Deliverable:** Soko Pulse, Alama Score, and Distribution Intelligence work through the new pipeline architecture, reading from the event store.

### Phase 3: Federated Learning (Weeks 7-9)

**Goal:** LoRA-based federated learning with device sync

1. Create `app/superagent/learning/lora_manager.py`
2. Create `app/superagent/learning/aggregator.py` (refactored FL v2)
3. Create `app/superagent/learning/dialect_federation.py`
4. Create `app/superagent/learning/round_coordinator.py`
5. Create `app/sync/` module (sync service, conflict resolver, delta sync)
6. Update FL API endpoints for LoRA uploads/downloads
7. Write FL integration tests

**Deliverable:** Devices can submit LoRA gradients, backend aggregates with FedAvg + DP, global adapter is distributed.

### Phase 4: Data Pipeline & Privacy (Weeks 10-11)

**Goal:** Complete data pipeline with privacy by construction

1. Refactor `app/data/ingestion/` (transaction ingester, voice ingester, M-Pesa parser)
2. Refactor `app/data/anonymization/` (split anonymizer into focused modules)
3. Create `app/data/aggregation/` (private aggregator, cohort builder)
4. Wire ingestion → event store → anonymization → aggregation
5. Update all intelligence pipelines to use privacy-preserving aggregation
6. Write privacy compliance tests

**Deliverable:** Full data pipeline from ingestion through privacy-preserving aggregation to intelligence products.

### Phase 5: Cleanup & Optimization (Weeks 12-13)

**Goal:** Remove dead code, optimize, document

1. Delete all unused agent code (`app/agents/`, `app/autonomous/`, `app/deerflow/`)
2. Delete unused services that were fully migrated
3. Optimize ClickHouse queries (materialized views, indexes)
4. Optimize Redis caching strategy
5. Update all tests
6. Update documentation
7. Performance testing and optimization

**Deliverable:** Clean codebase, no dead code, all tests passing, performance benchmarks met.

---

## Appendix A: File Count Comparison

| Metric | Current | New | Change |
|--------|---------|-----|--------|
| Python files | 488 | ~180 | -63% |
| Agent classes | 33+ | 0 | -100% |
| Service classes | 80+ | ~25 | -69% |
| API endpoints | 80+ | ~30 | -63% |
| Event types | 60+ | ~25 | -58% |
| Lines of code (est.) | ~45,000 | ~15,000 | -67% |

## Appendix B: Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| ClickHouse for event store | Column-oriented, append-only, time-partitioned, excellent compression. Perfect for immutable events. |
| LoRA over full fine-tuning | Mobile devices can't fine-tune 7B models. LoRA adapters are 10-100x smaller and train in minutes. |
| FedAvg over FedProx | Simpler, well-understood, sufficient for our convergence requirements. FedProx adds complexity for heterogeneous data which we handle via dialect federation. |
| ε=0.1 for DP | Financial-grade privacy. Standard ε=1.0 is too weak for financial data from vulnerable populations. |
| k≥10 for k-anonymity | Higher than the minimum k≥5 in FL v2. Better privacy for intelligence products that buyers access. |
| Event sourcing over CQRS | We need replay and audit, not separate read/write models. Event sourcing gives us both without CQRS complexity. |
| Single engine over multi-agent | The coordination overhead of 33 agents exceeds their specialization value. One engine with modules is simpler and faster. |
| Transaction patterns as credit score | M-KOPA proved: frequency, consistency, growth, and margins are sufficient. No traditional credit bureau needed. |
| Progressive service stacking | M-KOPA model: free Layer 1 generates data that makes Layers 2-4 valuable. The flywheel starts at onboarding. |
| Batch event ingestion | M-KOPA scale (2M/day): Redis Streams buffer + ClickHouse batch inserts achieves ~25K writes/sec. |

## Appendix C: Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Migration breaks existing API consumers | Keep v1 API endpoints stable during migration. New endpoints are additive. |
| Event store grows unbounded | ClickHouse TTL (2 years), S3 tiered storage for cold data. |
| FL aggregation latency | Async aggregation via Redis Streams. Devices don't wait for aggregation. |
| Privacy breach in intelligence products | k-anonymity + DP enforced at pipeline level, not as an afterthought. Audit logs for all data access. |
| Single engine becomes bottleneck | Stateless engine instances behind load balancer. State in Redis + ClickHouse. |
| LoRA adapter size on mobile | Personal rank=8 (~4MB), Global rank=16 (~16MB). Both fit comfortably on any modern phone. |
| 2M+ daily events overwhelm ClickHouse | Batch inserts via Redis Streams buffer. ClickHouse sharding by region. Materialized views for fast queries. |
| Thin-file workers get bad Alama Scores | Progressive unlocking: don't score until 30+ transactions. Return "insufficient data" with guidance to record more. |
| Data flywheel stalls (not enough workers) | Layer 1 is free. Voice-first UX lowers barrier. M-Pesa integration is seamless. Value is immediate (tracking). |
| Progressive stacking confuses workers | Clear messaging: "Record 30 transactions to unlock your credit score." Gamification of milestones. |

---

## 14. Deep Research Additions

This section captures 15 backend-side additions identified during deep research. Each service leverages the data flywheel — aggregating intelligence across all workers to produce insights no single worker could generate alone.

### 14.1 cuOpt Route Optimization Service

**Purpose:** Optimize routes for transport and delivery workers using NVIDIA cuOpt.

**Integration Point:** Distribution Intelligence pipeline (Section 6.4).

```python
# app/superagent/financial/route_optimization.py

class CuOptRouteService:
    """
    NVIDIA cuOpt integration for route optimization.

    Sends route optimization requests to cuOpt and receives
    optimized routes for transport/delivery workers.

    Use cases:
    - Delivery route optimization (minimize distance/time)
    - Multi-stop route planning (sales visits)
    - Distribution route planning (FMCG distributors)
    - Dynamic re-routing based on traffic/demand

    Data flywheel: More workers → more route data → better
    traffic/demand models → better routes for all workers.
    """

    async def optimize_route(
        self,
        worker_id: str,
        stops: list[RouteStop],
        vehicle_type: str,
        constraints: RouteConstraints | None = None,
    ) -> OptimizedRoute:
        """Send route optimization request to cuOpt."""
        # 1. Enrich stops with demand data from event store
        enriched_stops = await self._enrich_with_demand(stops)

        # 2. Build cuOpt request
        cuopt_request = {
            "cost_matrix": self._build_cost_matrix(enriched_stops),
            "fleet": [{"vehicle_type": vehicle_type}],
            "constraints": constraints.dict() if constraints else {},
        }

        # 3. Call cuOpt API
        result = await self.cuopt_client.solve(cuopt_request)

        # 4. Record optimization event
        await self.event_store.append(DomainEvent(
            event_type="intelligence.route.optimized",
            event_category="intelligence",
            worker_id=worker_id,
            payload={"num_stops": len(stops), "distance_saved_km": result.savings},
        ))

        return result
```

**Endpoint:**
```yaml
POST /api/v1/optimize/route
```

---

### 14.2 Market Price Aggregation Service

**Purpose:** Enhance Soko Pulse to aggregate real-time prices from all workers, compare across markets, and alert workers to better prices.

**Integration Point:** Soko Pulse pipeline (Section 6.2).

```python
# app/superagent/financial/price_aggregation.py

class MarketPriceAggregator:
    """
    Aggregates real-time market prices from all workers' transactions.

    Every transaction recorded by a worker includes price data.
    This service aggregates those prices to:
    1. Build real-time price maps per product per market
    2. Compare prices across markets (same product, different locations)
    3. Alert workers when better prices are available nearby
    4. Feed price data into Soko Pulse demand forecasting

    Privacy: Prices are aggregated with k-anonymity (k≥10).
    Individual worker prices are never exposed.
    """

    async def get_price_comparison(
        self,
        product: str,
        region: str,
    ) -> PriceComparison:
        """Compare prices for a product across markets in a region."""
        # Query aggregated price data from event store
        prices = await self.event_store.query_aggregated(
            region=region,
            category=product,
            aggregation="daily",
            since=days_ago(7),
        )
        return PriceComparison(
            product=product,
            region=region,
            markets=prices,
            cheapest_market=min(prices, key=lambda p: p.median_price),
            price_spread=max(p.median_price for p in prices) - min(p.median_price for p in prices),
        )

    async def alert_workers_to_better_prices(
        self,
        product: str,
        region: str,
    ) -> list[PriceAlert]:
        """Identify workers paying above-median prices and alert them."""
        comparison = await self.get_price_comparison(product, region)
        # Find workers who recently bought above the regional median
        # Push alerts via their preferred channel
        ...
```

---

### 14.3 Harvest Timing Intelligence

**Purpose:** Add to agricultural intelligence: weather data integration, crop growth models, market price forecasting, and optimal harvest/sell timing recommendations.

**Integration Point:** Soko Pulse pipeline (Section 6.2), Knowledge module.

```python
# app/superagent/financial/harvest_timing.py

class HarvestTimingEngine:
    """
    Harvest Timing Intelligence for agricultural workers.

    Combines:
    1. Weather data integration (rainfall, temperature, drought indices)
    2. Crop growth models (planting → harvest timelines per crop)
    3. Market price forecasting (seasonal price patterns)
    4. Optimal harvest/sell timing recommendations

    Example insight:
    "Maize prices typically peak 3 weeks after harvest season.
     Current weather suggests early harvest this year.
     Recommendation: Store maize for 2-3 weeks for 15-20% higher prices."

    Data flywheel: More farmers → more harvest data → better crop
    models → better timing advice → higher farmer income.
    """

    async def get_timing_recommendation(
        self,
        worker_id: str,
        crop: str,
        location: GeoPoint,
    ) -> HarvestTimingRecommendation:
        """Get optimal harvest and sell timing for a crop."""
        # 1. Get weather forecast for location
        weather = await self.weather_service.get_forecast(location, days=30)

        # 2. Get crop growth model
        growth_model = self.crop_models.get(crop)
        days_to_harvest = growth_model.estimate_harvest_days(weather)

        # 3. Get price forecast from Soko Pulse
        price_forecast = await self.soko_pulse.generate_forecast(
            region=location.region,
            product_category=crop,
            horizon_days=60,
        )

        # 4. Find optimal sell window
        optimal_window = self._find_optimal_sell_window(
            days_to_harvest=days_to_harvest,
            price_forecast=price_forecast,
            storage_cost_per_day=growth_model.storage_cost(crop),
        )

        return HarvestTimingRecommendation(
            crop=crop,
            estimated_harvest_date=date.today() + timedelta(days=days_to_harvest),
            optimal_sell_date=optimal_window.best_date,
            expected_price_at_sell=optimal_window.expected_price,
            price_vs_immediate_sell=optimal_window.price_premium_pct,
            storage_cost=optimal_window.storage_cost,
            net_benefit=optimal_window.net_benefit,
            weather_risks=weather.risks,
        )
```

---

### 14.4 Skill Verification Service

**Purpose:** Backend verifies worker skills by aggregating job completion data, customer ratings, and peer comparison. Issues skill badges.

```python
# app/superagent/credit/skill_verification.py

class SkillVerificationService:
    """
    Verifies worker skills using aggregated backend data.

    Verification signals:
    1. Job completion data (completed vs started, quality metrics)
    2. Customer ratings (aggregated across all clients)
    3. Peer comparison (how does this worker compare to others with same skill?)
    4. Consistency (how long has the worker been performing this skill?)

    Issues skill badges at levels: Bronze (emerging), Silver (competent),
    Gold (expert), Platinum (master).
    """

    async def verify_skill(
        self,
        worker_id: str,
        skill: str,
    ) -> SkillVerification:
        """Verify a worker's skill and issue badge if qualified."""
        # Aggregate job data
        jobs = await self.event_store.query(
            worker_id=worker_id,
            event_types=["job.completed", "job.rated"],
        )

        skill_jobs = [j for j in jobs if j.payload.get("skill") == skill]
        if len(skill_jobs) < 5:
            return SkillVerification(skill=skill, level=None, status="insufficient_data")

        # Compute metrics
        completion_rate = self._completion_rate(skill_jobs)
        avg_rating = self._avg_rating(skill_jobs)
        peer_percentile = await self._peer_comparison(worker_id, skill)

        # Determine badge level
        level = self._determine_level(completion_rate, avg_rating, peer_percentile)

        return SkillVerification(
            skill=skill,
            level=level,
            completion_rate=completion_rate,
            avg_rating=avg_rating,
            peer_percentile=peer_percentile,
            jobs_completed=len(skill_jobs),
            status="verified",
        )
```

**Endpoint:**
```yaml
GET /api/v1/workers/{id}/skills
```

---

### 14.5 Portfolio Verification Service

**Purpose:** Backend verifies creative portfolios by aggregating project data, client testimonials, and peer comparison. Issues portfolio scores.

```python
# app/superagent/credit/portfolio_verification.py

class PortfolioVerificationService:
    """
    Verifies creative worker portfolios using aggregated backend data.

    For creative professionals (designers, photographers, writers, etc.):
    1. Project data (number of projects, complexity, completion rate)
    2. Client testimonials (aggregated ratings and feedback)
    3. Peer comparison (how does this worker compare to similar creatives?)
    4. Consistency and growth (improving quality over time?)

    Issues portfolio scores (0-100) and quality tiers.
    """

    async def verify_portfolio(
        self,
        worker_id: str,
    ) -> PortfolioScore:
        """Score and verify a creative worker's portfolio."""
        projects = await self.event_store.query(
            worker_id=worker_id,
            event_types=["job.completed"],
        )
        creative_jobs = [j for j in projects if j.payload.get("category") in CREATIVE_CATEGORIES]

        if len(creative_jobs) < 3:
            return PortfolioScore(score=None, status="insufficient_projects")

        project_score = self._score_projects(creative_jobs)
        client_score = self._score_client_feedback(creative_jobs)
        peer_score = await self._peer_comparison(worker_id, creative_jobs)
        growth_score = self._score_growth_trajectory(creative_jobs)

        total = 0.35 * project_score + 0.30 * client_score + 0.20 * peer_score + 0.15 * growth_score

        return PortfolioScore(
            score=round(total),
            tier=self._tier(total),
            project_score=project_score,
            client_score=client_score,
            peer_percentile=peer_score,
            growth_score=growth_score,
            status="verified",
        )
```

**Endpoint:**
```yaml
GET /api/v1/workers/{id}/portfolio
```

---

### 14.6 Supplier Comparison Service

**Purpose:** Aggregate supplier prices from all workers. Identify cheapest suppliers per product per region.

```python
# app/superagent/financial/supplier_comparison.py

class SupplierComparisonService:
    """
    Aggregates supplier pricing data from all workers' purchase transactions.

    When workers record purchases ("Bought maize from Supplier X at KSh 50/kg"),
    this service aggregates that data to:
    1. Build a supplier price database per product per region
    2. Identify cheapest suppliers
    3. Track price trends by supplier
    4. Recommend suppliers to workers

    Data flywheel: More workers recording purchases → more supplier
    data → better price comparisons → workers save money.
    """

    async def compare_suppliers(
        self,
        product: str,
        region: str,
    ) -> SupplierComparison:
        """Compare suppliers for a product in a region."""
        purchases = await self.event_store.query_aggregated(
            region=region,
            category=product,
            event_types=["transaction.recorded"],
            aggregation="weekly",
            since=days_ago(90),
        )

        suppliers = self._aggregate_by_supplier(purchases)
        ranked = sorted(suppliers, key=lambda s: s.median_price)

        return SupplierComparison(
            product=product,
            region=region,
            suppliers=ranked,
            cheapest=ranked[0] if ranked else None,
            price_spread=ranked[-1].median_price - ranked[0].median_price if len(ranked) > 1 else 0,
        )
```

**Endpoint:**
```yaml
GET /api/v1/suppliers/compare/{product}/{region}
```

---

### 14.7 Pricing Advisor Service

**Purpose:** Aggregate pricing data from all workers. Recommend optimal pricing per skill/product per region.

```python
# app/superagent/financial/pricing_advisor.py

class PricingAdvisorService:
    """
    Recommends optimal pricing for workers based on aggregated market data.

    Aggregates pricing data from all workers to answer:
    - "What should I charge for plumbing in Nairobi?"
    - "What's the market rate for maize in Eldoret?"
    - "Am I undercharging for my design services?"

    Uses:
    - Regional price distributions (median, percentiles)
    - Skill level adjustment (beginner vs expert pricing)
    - Demand signals (high demand → can charge more)
    - Seasonal adjustments (prices vary by season)
    """

    async def recommend_price(
        self,
        skill_or_product: str,
        location: str,
        worker_id: str | None = None,
    ) -> PricingRecommendation:
        """Get recommended pricing for a skill/product in a location."""
        transactions = await self.event_store.query_aggregated(
            region=location,
            category=skill_or_product,
            since=days_ago(90),
        )

        prices = [t.payload["amount"] for t in transactions]
        dist = self.stats_engine.kde_estimate(prices)

        recommendation = PricingRecommendation(
            skill_or_product=skill_or_product,
            location=location,
            market_median=float(np.median(prices)),
            market_p25=float(np.percentile(prices, 25)),
            market_p75=float(np.percentile(prices, 75)),
            suggested_range=(float(np.percentile(prices, 25)), float(np.percentile(prices, 75))),
            data_points=len(prices),
        )

        # If worker_id provided, compare their current pricing
        if worker_id:
            worker_prices = await self._get_worker_prices(worker_id, skill_or_product)
            if worker_prices:
                recommendation.worker_avg = float(np.mean(worker_prices))
                recommendation.position_vs_market = self._percentile_position(
                    recommendation.worker_avg, prices
                )
                if recommendation.position_vs_market < 25:
                    recommendation.insight = "You're charging below market rate. Consider increasing prices."
                elif recommendation.position_vs_market > 75:
                    recommendation.insight = "You're above market median. Ensure quality justifies premium."

        return recommendation
```

**Endpoint:**
```yaml
GET /api/v1/pricing/recommend/{skill}/{location}
```

---

### 14.8 Seasonal Alama Score

**Purpose:** Update Alama Score computation to handle different work patterns.

**Integration Point:** Alama Score pipeline (Section 6.3).

```python
# app/superagent/credit/seasonal_scoring.py

class WorkPattern(StrEnum):
    SEASONAL = "seasonal"           # Agriculture, tourism
    PROJECT_BASED = "project_based" # Construction, events
    ON_DEMAND = "on_demand"         # Gig workers, freelancers
    CONTINUOUS = "continuous"       # Retail, services (default)

class SeasonalAlamaScorer:
    """
    Alama Score variant that handles non-continuous work patterns.

    Standard Alama Score assumes daily transactions.
    But many informal workers have irregular patterns:
    - Seasonal: Farmers plant/harvest in seasons, not daily
    - Project-based: Construction workers have gaps between projects
    - On-demand: Gig workers have variable activity

    Solution: Normalize scoring by work pattern.

    SEASONAL:
    - Normalize by season (not by calendar days)
    - Compare to same season last year
    - Score based on seasonal revenue, not daily averages

    PROJECT_BASED:
    - Use project completion rate as primary signal
    - Track: projects quoted → started → completed → paid
    - Score based on completion rate + average project value

    ON_DEMAND:
    - Use client retention rate as primary signal
    - Track: unique clients, repeat clients, client satisfaction
    - Score based on demand consistency + client loyalty
    """

    def compute_score(
        self,
        worker_id: str,
        transactions: list[Transaction],
        work_pattern: WorkPattern,
    ) -> AlamaScoreResult:
        """Compute Alama Score adjusted for work pattern."""
        if work_pattern == WorkPattern.SEASONAL:
            return self._score_seasonal(worker_id, transactions)
        elif work_pattern == WorkPattern.PROJECT_BASED:
            return self._score_project_based(worker_id, transactions)
        elif work_pattern == WorkPattern.ON_DEMAND:
            return self._score_on_demand(worker_id, transactions)
        else:
            # Default: continuous scoring (existing Alama Score)
            return self.base_engine.compute_score_from_transactions(transactions)

    def _score_seasonal(self, worker_id: str, transactions: list[Transaction]) -> AlamaScoreResult:
        """Score seasonal workers by comparing to same season last year."""
        # Group transactions by season
        seasons = self._group_by_season(transactions)
        # Compare current season to previous season
        # Reward growth year-over-year
        ...

    def _score_project_based(self, worker_id: str, transactions: list[Transaction]) -> AlamaScoreResult:
        """Score project-based workers by completion rate."""
        # Track project lifecycle: quoted → started → completed → paid
        projects = self._extract_projects(transactions)
        completion_rate = sum(1 for p in projects if p.status == "completed") / len(projects) if projects else 0
        avg_project_value = np.mean([p.value for p in projects if p.status == "completed"]) if projects else 0
        # Score: completion_rate (60%) + value_growth (20%) + consistency (20%)
        ...

    def _score_on_demand(self, worker_id: str, transactions: list[Transaction]) -> AlamaScoreResult:
        """Score on-demand workers by client retention."""
        # Track unique clients, repeat rate, client lifetime value
        clients = self._extract_clients(transactions)
        retention_rate = len([c for c in clients if c.visit_count > 1]) / len(clients) if clients else 0
        # Score: retention_rate (50%) + demand_frequency (30%) + growth (20%)
        ...
```

---

### 14.9 Fraud Detection Service

**Purpose:** Aggregate transaction patterns across workers, detect anomalies and coordinated fraud, flag suspicious patterns.

```python
# app/superagent/credit/fraud_detection.py

class FraudDetectionService:
    """
    Detects fraud by analyzing patterns across ALL workers.

    Single-worker fraud is hard to detect from one data source.
    But when you aggregate across thousands of workers, patterns emerge:
   
    1. Coordinated fraud: Multiple workers suddenly inflating transactions
       in the same region at the same time (pump attempt)
    2. Sybil attacks: One person creating multiple worker accounts
       to game the Alama Score system
    3. Transaction anomalies: Impossible patterns (e.g., 500 transactions
       in one day for a small kiosk)
    4. Collusion: Workers artificially inflating each other's ratings

    This service runs periodically (hourly) and flags anomalies.
    """

    async def analyze_fraud_signals(
        self,
        region: str | None = None,
        time_window_hours: int = 24,
    ) -> FraudReport:
        """Run fraud analysis across all workers."""
        # Get recent transactions across all workers
        events = await self.event_store.query(
            region=region,
            event_types=["transaction.recorded"],
            since=hours_ago(time_window_hours),
        )

        anomalies = []

        # 1. Check for coordinated activity spikes
        spikes = self._detect_coordinated_spikes(events)
        anomalies.extend(spikes)

        # 2. Check for sybil patterns (similar devices, locations, timing)
        sybils = self._detect_sybil_patterns(events)
        anomalies.extend(sybils)

        # 3. Check for impossible transaction volumes
        volume_anomalies = self._detect_volume_anomalies(events)
        anomalies.extend(volume_anomalies)

        # 4. Check for rating collusion
        collusion = self._detect_rating_collusion(events)
        anomalies.extend(collusion)

        return FraudReport(
            region=region,
            time_window_hours=time_window_hours,
            total_events=len(events),
            anomalies=anomalies,
            risk_level=self._aggregate_risk_level(anomalies),
            flagged_worker_ids=[a.worker_id for a in anomalies],
        )
```

**Endpoint:**
```yaml
POST /api/v1/fraud/analyze
```

---

### 14.10 Client Management Backend

**Purpose:** Store client profiles aggregated from workers. Identify repeat customers. Build client reliability scores.

```python
# app/superagent/financial/client_management.py

class ClientManagementService:
    """
    Manages client profiles aggregated from worker transactions.

    When workers record transactions ("Sold to Mama Njeri"),
    the backend aggregates client data across all workers to:
    1. Build client profiles (purchasing patterns, reliability)
    2. Identify repeat customers across workers
    3. Score client reliability (pays on time? returns frequently?)
    4. Help workers identify their best clients

    Privacy: Client data is pseudonymized. Workers see their own
    clients; cross-worker client data is aggregated only.
    """

    async def get_worker_clients(
        self,
        worker_id: str,
    ) -> ClientProfile:
        """Get client profiles for a specific worker."""
        transactions = await self.event_store.query(
            worker_id=worker_id,
            event_types=["transaction.recorded"],
        )

        clients = self._aggregate_clients(transactions)
        return ClientProfile(
            worker_id=worker_id,
            total_clients=len(clients),
            repeat_clients=len([c for c in clients if c.visit_count > 1]),
            top_clients=sorted(clients, key=lambda c: c.total_spent, reverse=True)[:10],
            client_retention_rate=self._retention_rate(clients),
            avg_client_value=float(np.mean([c.total_spent for c in clients])),
        )
```

**Endpoint:**
```yaml
GET /api/v1/clients/{worker_id}
```

---

### 14.11 Job Lifecycle Backend

**Purpose:** Track jobs across workers through the full lifecycle: quoted → in-progress → completed → paid. Build job completion rates, average job values, profit margins by skill type.

```python
# app/superagent/financial/job_lifecycle.py

class JobLifecycleTracker:
    """
    Tracks the full lifecycle of jobs across all workers.

    Lifecycle stages:
    quoted → accepted → in_progress → completed → paid

    Aggregated metrics (per skill type, per region):
    - Job completion rate (completed / quoted)
    - Average job value
    - Average time to completion
    - Profit margins (revenue - material costs)
    - Client satisfaction (if rated)

    These metrics feed into:
    - Skill Verification (Section 14.4): completion rate as quality signal
    - Alama Score (Section 6.3): job data as credit signal
    - Pricing Advisor (Section 14.7): job values as pricing data
    """

    async def track_job_event(
        self,
        worker_id: str,
        job_id: str,
        stage: str,  # quoted, accepted, in_progress, completed, paid
        metadata: dict,
    ) -> None:
        """Record a job lifecycle event."""
        await self.event_store.append(DomainEvent(
            event_type=f"job.{stage}",
            event_category="transaction",
            worker_id=worker_id,
            payload={"job_id": job_id, "stage": stage, **metadata},
        ))

    async def get_job_metrics(
        self,
        worker_id: str,
        skill_type: str | None = None,
    ) -> JobMetrics:
        """Get aggregated job lifecycle metrics."""
        jobs = await self.event_store.query(
            worker_id=worker_id,
            event_types=["job.queried", "job.completed", "job.paid"],
        )
        return JobMetrics(
            completion_rate=self._completion_rate(jobs),
            avg_job_value=self._avg_value(jobs),
            avg_completion_days=self._avg_days(jobs),
            profit_margin=self._profit_margin(jobs),
            total_jobs=len(set(j.payload["job_id"] for j in jobs)),
        )
```

---

### 14.12 Tool Depreciation Backend

**Purpose:** Track tool purchases across workers. Aggregate tool lifespans by brand/type. Recommend replacement timing.

```python
# app/superagent/financial/tool_depreciation.py

class ToolDepreciationService:
    """
    Tracks tool purchases and lifespans across all workers.

    When workers buy tools ("Bought a Bosch drill for KSh 15,000"),
    the backend aggregates tool data to:
    1. Track tool purchases and costs per worker
    2. Estimate tool lifespan by brand/type (from aggregated data)
    3. Calculate depreciation schedules
    4. Recommend replacement timing
    5. Identify best value tools (lifespan/cost ratio)

    Data flywheel: More workers → more tool data → better lifespan
    estimates → better recommendations for all workers.
    """

    async def get_worker_tools(
        self,
        worker_id: str,
    ) -> ToolInventory:
        """Get tool inventory and depreciation for a worker."""
        purchases = await self.event_store.query(
            worker_id=worker_id,
            event_types=["transaction.recorded"],
        )
        tool_purchases = [t for t in purchases if t.payload.get("category") == "tools"]

        tools = []
        for t in tool_purchases:
            expected_lifespan = await self._get_expected_lifespan(
                t.payload["product"], t.payload.get("brand")
            )
            age_days = (date.today() - t.occurred_at.date()).days
            tools.append(ToolItem(
                name=t.payload["product"],
                brand=t.payload.get("brand"),
                purchase_price=t.payload["amount"],
                purchase_date=t.occurred_at.date(),
                expected_lifespan_days=expected_lifespan,
                age_days=age_days,
                depreciation_pct=min(1.0, age_days / expected_lifespan) if expected_lifespan else None,
                replacement_recommended=age_days > expected_lifespan * 0.8 if expected_lifespan else False,
            ))

        return ToolInventory(worker_id=worker_id, tools=tools, total_investment=sum(t.purchase_price for t in tools))
```

**Endpoint:**
```yaml
GET /api/v1/tools/{worker_id}
```

---

### 14.13 Material Inventory Backend

**Purpose:** Aggregate material prices from all workers. Identify bulk buying opportunities. Connect workers to suppliers.

```python
# app/superagent/financial/material_inventory.py

class MaterialInventoryService:
    """
    Aggregates material pricing and inventory data across workers.

    For workers who buy materials (construction, manufacturing, food prep):
    1. Track material purchases and prices
    2. Aggregate prices across all workers in a region
    3. Identify bulk buying opportunities (multiple workers buying same material)
    4. Connect workers to form buying groups
    5. Alert to price changes

    Example insight:
    "5 workers in your area buy cement weekly. Bulk order of 50 bags
     saves KSh 200/bag. Want to form a buying group?"
    """

    async def get_material_prices(
        self,
        region: str,
    ) -> MaterialPrices:
        """Get aggregated material prices for a region."""
        purchases = await self.event_store.query_aggregated(
            region=region,
            event_types=["transaction.recorded"],
            since=days_ago(30),
        )
        materials = [t for t in purchases if t.payload.get("category") in MATERIAL_CATEGORIES]
        aggregated = self._aggregate_material_prices(materials)

        return MaterialPrices(
            region=region,
            materials=aggregated,
            bulk_opportunities=self._find_bulk_opportunities(materials),
        )
```

**Endpoint:**
```yaml
GET /api/v1/materials/prices/{region}
```

---

### 14.14 Tax Intelligence Backend

**Purpose:** Aggregate expense categories across workers. Provide tax-ready reports. KRA compliance templates.

```python
# app/superagent/financial/tax_intelligence.py

class TaxIntelligenceService:
    """
    Tax intelligence for informal workers.

    Most informal workers have never filed taxes.
    This service:
    1. Aggregates expense categories from transaction data
    2. Auto-categorizes expenses for tax purposes
    3. Generates tax-ready reports (P&L, expense summaries)
    4. Provides KRA compliance templates
    5. Estimates tax liability
    6. Identifies deductible expenses

    Makes tax compliance accessible for workers who
    have never interacted with the tax system.
    """

    async def generate_tax_report(
        self,
        worker_id: str,
        tax_year: int,
    ) -> TaxReport:
        """Generate a tax-ready report for a worker."""
        transactions = await self.event_store.query(
            worker_id=worker_id,
            event_types=["transaction.recorded"],
            since=datetime(tax_year, 1, 1),
            until=datetime(tax_year, 12, 31),
        )

        income = self._categorize_income(transactions)
        expenses = self._categorize_expenses(transactions)
        deductions = self._identify_deductions(expenses)

        revenue = sum(income.values())
        total_expenses = sum(expenses.values())
        net_income = revenue - total_expenses

        return TaxReport(
            worker_id=worker_id,
            tax_year=tax_year,
            revenue=revenue,
            expenses_by_category=expenses,
            total_expenses=total_expenses,
            net_income=net_income,
            deductible_expenses=deductions,
            estimated_tax=self._estimate_tax(net_income),
            kra_template=self._generate_kra_template(income, expenses, deductions),
            compliance_status=self._check_compliance(worker_id, tax_year),
        )
```

**Endpoint:**
```yaml
GET /api/v1/tax/report/{worker_id}
```

---

### 14.15 Waste/Spoilage Analytics

**Purpose:** Aggregate spoilage data across workers. Identify waste patterns. Recommend buy quantities to minimize waste.

```python
# app/superagent/financial/spoilage_analytics.py

class SpoilageAnalyticsService:
    """
    Aggregates waste and spoilage data across all workers.

    For perishable goods sellers (food, flowers, etc.):
    1. Track spoilage events ("Threw away 5kg of tomatoes")
    2. Aggregate spoilage rates by product, region, season
    3. Identify waste patterns (which products spoil most? when?)
    4. Recommend optimal buy quantities to minimize waste
    5. Alert workers to spoilage risk based on weather/season

    Example insight:
    "Workers in your area waste 15% of tomatoes bought on Monday.
     Recommendation: Buy 30kg instead of 40kg on Mondays.
     Expected savings: KSh 500/week."
    """

    async def get_spoilage_analysis(
        self,
        product: str,
        region: str | None = None,
    ) -> SpoilageAnalysis:
        """Analyze spoilage patterns for a product."""
        # Get spoilage events from event store
        events = await self.event_store.query(
            region=region,
            event_types=["transaction.spoilage"],
            since=days_ago(90),
        )
        product_events = [e for e in events if e.payload.get("product") == product]

        spoilage_rate = self._compute_spoilage_rate(product_events)
        patterns = self._identify_patterns(product_events)
        recommendations = self._generate_recommendations(spoilage_rate, patterns)

        return SpoilageAnalysis(
            product=product,
            region=region,
            spoilage_rate_pct=spoilage_rate,
            avg_waste_value=self._avg_waste_value(product_events),
            patterns=patterns,
            optimal_buy_quantity=recommendations.optimal_quantity,
            expected_savings_per_week=recommendations.weekly_savings,
            seasonal_risk=patterns.seasonal_risk,
        )
```

**Endpoint:**
```yaml
GET /api/v1/analytics/spoilage/{product}
```

---

### 14.16 New API Endpoints Summary

| # | Service | Endpoint | Method |
|---|---------|----------|--------|
| 1 | cuOpt Route Optimization | `/api/v1/optimize/route` | POST |
| 2 | Market Price Aggregation | (integrated into Soko Pulse) | — |
| 3 | Harvest Timing Intelligence | (integrated into Soko Pulse) | — |
| 4 | Skill Verification | `/api/v1/workers/{id}/skills` | GET |
| 5 | Portfolio Verification | `/api/v1/workers/{id}/portfolio` | GET |
| 6 | Supplier Comparison | `/api/v1/suppliers/compare/{product}/{region}` | GET |
| 7 | Pricing Advisor | `/api/v1/pricing/recommend/{skill}/{location}` | GET |
| 8 | Seasonal Alama Score | (integrated into Alama Score engine) | — |
| 9 | Fraud Detection | `/api/v1/fraud/analyze` | POST |
| 10 | Client Management | `/api/v1/clients/{worker_id}` | GET |
| 11 | Job Lifecycle | (event-driven, no dedicated endpoint) | — |
| 12 | Tool Depreciation | `/api/v1/tools/{worker_id}` | GET |
| 13 | Material Inventory | `/api/v1/materials/prices/{region}` | GET |
| 14 | Tax Intelligence | `/api/v1/tax/report/{worker_id}` | GET |
| 15 | Waste/Spoilage Analytics | `/api/v1/analytics/spoilage/{product}` | GET |

### 14.17 New Directory Additions

These modules integrate into the existing directory structure:

```
app/superagent/financial/
├── ... (existing files)
├── route_optimization.py      # cuOpt integration
├── price_aggregation.py       # Market price aggregation
├── harvest_timing.py          # Harvest timing intelligence
├── supplier_comparison.py     # Supplier comparison
├── pricing_advisor.py         # Pricing advisor
├── client_management.py       # Client management
├── job_lifecycle.py           # Job lifecycle tracking
├── tool_depreciation.py       # Tool depreciation
├── material_inventory.py      # Material inventory
├── tax_intelligence.py        # Tax intelligence
└── spoilage_analytics.py      # Waste/spoilage analytics

app/superagent/credit/
├── ... (existing files)
├── skill_verification.py      # Skill verification
├── portfolio_verification.py  # Portfolio verification
├── seasonal_scoring.py        # Seasonal Alama Score
└── fraud_detection.py         # Fraud detection
```

### 14.18 Data Flywheel Impact

Each addition strengthens the data flywheel:

| Service | Data In | Intelligence Out | Flywheel Effect |
|---------|---------|-----------------|------------------|
| cuOpt Routes | Worker routes + locations | Optimized routes | More workers → better traffic data → better routes |
| Price Aggregation | Transaction prices | Market price maps | More workers → more prices → better comparisons |
| Harvest Timing | Farm transactions + weather | Sell timing advice | More farmers → better crop models → better timing |
| Skill Verification | Job completions + ratings | Skill badges | More jobs → better verification → more trust |
| Portfolio Verification | Project data + feedback | Portfolio scores | More projects → better scoring → more credibility |
| Supplier Comparison | Purchase transactions | Supplier rankings | More buyers → more supplier data → better deals |
| Pricing Advisor | Transaction amounts | Price recommendations | More transactions → better pricing → more revenue |
| Seasonal Alama Score | Seasonal patterns | Fair credit scores | More seasonal workers → better models → fairer scores |
| Fraud Detection | Cross-worker patterns | Fraud alerts | More workers → better anomaly detection → safer system |
| Client Management | Client transactions | Client profiles | More workers → more client data → better insights |
| Job Lifecycle | Job stage events | Completion metrics | More jobs → better benchmarks → better planning |
| Tool Depreciation | Tool purchases | Lifespan estimates | More workers → better lifespan data → better advice |
| Material Inventory | Material purchases | Bulk opportunities | More buyers → more data → bigger bulk discounts |
| Tax Intelligence | Expense/income data | Tax reports | More transactions → better categorization → easier taxes |
| Spoilage Analytics | Spoilage events | Waste reduction | More sellers → better spoilage models → less waste |
