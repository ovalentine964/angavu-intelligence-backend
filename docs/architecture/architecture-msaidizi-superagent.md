# Msaidizi Superagent Architecture

**Version:** 1.1.0
**Date:** 2026-07-24
**Author:** Chief Architect
**Status:** Architecture Blueprint — Ready for Implementation
**Update:** v1.1.0 — Incorporated M-KOPA proof accumulation model

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
1.5. [The App-Backend Relationship](#15-the-app-backend-relationship-critical-architecture-boundary)
2. [Current State Analysis](#2-current-state-analysis)
3. [Architecture Philosophy: Why Superagent](#3-architecture-philosophy-why-superagent)
4. [New Module Structure](#4-new-module-structure)
5. [Detailed Module Design](#5-detailed-module-design)
6. [File Migration Map: What Moves Where](#6-file-migration-map-what-moves-where)
7. [What Gets DELETED](#7-what-gets-deleted)
8. [The Superagent Reasoning Flow](#8-the-superagent-reasoning-flow)
9. [Bootstrap & Onboarding Flow](#9-bootstrap--onboarding-flow)
10. [The Proof Flywheel (M-KOPA Model)](#10-the-proof-flywheel-m-kopa-model)
11. [Progressive Service Stacking & Alama Score](#11-progressive-service-stacking--alama-score)
12. [Shared Context Engine](#12-shared-context-engine)
13. [Dependency Graph](#13-dependency-graph)
14. [Build Configuration](#14-build-configuration)
15. [Migration Strategy](#15-migration-strategy)
16. [Testing Strategy](#16-testing-strategy)

---

## 1. Executive Summary

Msaidizi today is a **400-file, 127,602-line single-module Android app** with a multi-agent architecture: an Orchestrator dispatches to IntentRouter, which routes to domain-specific Agents (BusinessAgent, AnalysisAgent, AdvisorAgent, LearningAgent) and Handlers (TransactionHandler, QueryHandler, AdviceHandler, GamificationHandler), communicating via an A2A (Agent-to-Agent) protocol and AgentEventBus.

**The problem:** This is a committee, not a brain. Each "agent" is really just a handler with delusions of grandeur. The A2A protocol adds latency and complexity for zero benefit — these agents share a process, a database, and a memory. They're not distributed. They're not independent. They're functions wearing agent costumes.

**The solution:** SUPERAGENT architecture. One unified reasoning engine with internal capability modules. No inter-agent messaging. No orchestration overhead. One brain, many skills.

**The business model lesson from M-KOPA:** M-KOPA (10M customers, $2B credit deployed) proves the thesis for informal economies. Their model:
- **Daily small interactions build proof over time** — every payment is evidence of reliability
- **Proof unlocks credit, insurance, market intelligence** — trust is the currency
- **Stack services on trust, not features** — don't sell a bundle, earn access
- **Patience: 8 years for first million, then acceleration** — the flywheel compounds

For Msaidizi, this means every voice-recorded transaction is proof. Every day of tracking is evidence. The Alama Score (credit readiness) is the unlock. The architecture must be designed around **proof accumulation**, not feature delivery.

**Key metrics:**
- Current: 1 module (`:app`), 400 files, ~127K lines
- Target: 14 modules, same files reorganized, ~127K lines (net reduction after deletions: ~115K)
- Deleted: ~12K lines of multi-agent infrastructure (A2A, Orchestrator, AgentEventBus, MoE router, agent registration)
- **Proof model:** Every transaction = 1 proof point. 30 days = credit readiness assessment. 90 days = formal finance eligibility.

---

## 1.5 The App-Backend Relationship (Critical Architecture Boundary)

### The M-KOPA Parallel

```
┌─────────────────────────────────────────────────────────────────┐
│                    M-KOPA MODEL                                 │
│                                                                 │
│  PHONE (Data Collector)          BACKEND (Intelligence Engine)  │
│  ┌─────────────────┐            ┌─────────────────────────┐    │
│  │ Daily payments  │───────────▶│ Payment behavior        │    │
│  │ Usage patterns  │            │ Credit scoring          │    │
│  │ Location data   │            │ Risk assessment         │    │
│  │ Device info     │            │ Product recommendations │    │
│  └─────────────────┘            └─────────────────────────┘    │
│         │                              │                        │
│         ▼                              ▼                        │
│  Phone gives access to    Backend builds intelligence           │
│  products → more usage    products → unlocks credit,            │
│  → more data → better     insurance, market data                │
│  scores → more products   → more users → more data              │
│                                                                 │
│  ★ THE PHONE IS A DATA COLLECTION DEVICE ★                     │
│  ★ THE BACKEND IS THE VALUE CREATION ENGINE ★                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    MSAIDIZI MODEL                               │
│                                                                 │
│  APP (Data Collector)          BACKEND (Intelligence Engine)    │
│  ┌─────────────────┐            ┌─────────────────────────┐    │
│  │ Voice trans-    │───────────▶│ Alama Score             │    │
│  │ actions         │            │ (credit readiness)      │    │
│  │ Business        │            │                         │    │
│  │ patterns        │            │ Soko Pulse              │    │
│  │ Market prices   │            │ (market intelligence)   │    │
│  │ Supply chain    │            │                         │    │
│  │ Location/freq   │            │ Distribution Intel      │    │
│  └─────────────────┘            │ (supply chain insights) │    │
│         │                       └─────────────────────────┘    │
│         ▼                              │                        │
│  App gives voice financial    Backend transforms raw data       │
│  assistant → more usage       into intelligence products →      │
│  → more transaction data      unlocks credit, insurance,        │
│  → better Alama Score         market access → more users →      │
│  → more services              more data → flywheel accelerates  │
│                                                                 │
│  ★ THE APP IS A DATA COLLECTION DEVICE ★                       │
│  ★ EVERY VOICE INTERACTION IS A DATA POINT ★                   │
│  ★ THE BACKEND IS THE VALUE CREATION ENGINE ★                   │
└─────────────────────────────────────────────────────────────────┘
```

### What the Backend Needs from the App

The backend's intelligence products require specific data. The app must be designed to collect this data through natural voice interactions:

| Backend Product | Required Data | How App Collects It |
|---|---|---|
| **Alama Score** (credit readiness) | Transaction history, consistency, margins, payment patterns | Every "Nimeuziwa..." voice recording |
| **Soko Pulse** (market intelligence) | Product prices, volumes, timing, location | Transaction amounts + GPS + timestamps |
| **Distribution Intel** (supply chain) | Supplier relationships, restock patterns, product flow | "Nimenunua..." recordings + inventory tracking |
| **Risk Assessment** | Business volatility, seasonal patterns, customer concentration | Historical transaction analysis |
| **Insurance Eligibility** | Business type, location risk, revenue stability | Worker profile + transaction patterns |

### The Data Contract

The app and backend have an implicit contract:

```
APP PROMISES TO COLLECT:          BACKEND PROMISES TO DELIVER:
─────────────────────────          ──────────────────────────────
• Every sale transaction           • Alama Score (credit readiness)
• Every purchase transaction       • Soko Pulse (market prices)
• Every expense                    • Distribution Intelligence
• Product names & categories       • Credit readiness assessment
• Prices (unit & total)            • Insurance eligibility
• Payment methods                  • Business optimization advice
• Timing (when)                    • Market price alerts
• Location (where)                 • Peer comparison data
• Frequency (how often)            • Supply chain insights
• Margins (profit per item)        • Tax estimation
```

### Critical Design Implication

**The app's voice interaction design MUST prioritize data completeness over conversational naturalness.**

This means:
- When a worker says "Nimeuziwa mandazi", the app should ask "Bei ngapi?" (not just record "mandazi")
- When a worker says "Nimenunua vitu", the app should ask "Vitu gani? Bei ngapi?" (not just record "purchase")
- Every voice interaction should extract: WHAT, HOW MANY, HOW MUCH, WHEN (implicitly from timestamp), WHERE (implicitly from GPS)

**The data model below is designed around what the backend needs, not what the app displays.**

### Backend-Optimized Data Model

The current Transaction model captures basic fields. The backend needs richer data. Here's the enhanced model:

```kotlin
// core/common/model/Transaction.kt — BACKEND-OPTIMIZED
data class Transaction(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,

    // ═══ WHAT: Product identification ═══
    val type: TransactionType,           // SALE, PURCHASE, EXPENSE
    val item: String,                    // "mandazi", "nyanya", "unga"
    val category: String = "",           // "food", "grains", "produce" (auto-classified)
    val subcategory: String = "",        // "street_food", "vegetables", "staples"
    val productCode: String = "",        // Backend product ID (for cross-worker analysis)

    // ═══ HOW MANY: Quantity ═══
    val quantity: Double = 1.0,
    val unit: String = "pieces",          // "pieces", "kg", "liters", "bundles"

    // ═══ HOW MUCH: Pricing ═══
    val unitPrice: Double = 0.0,         // Price per unit in KSh
    val totalAmount: Double,             // Total amount in KSh
    val costBasis: Double = 0.0,         // Cost for profit calculation
    val margin: Double = 0.0,            // Calculated: totalAmount - costBasis
    val marginPercent: Double = 0.0,     // Calculated: margin / totalAmount
    val currency: String = "KSh",        // For multi-country support

    // ═══ WHEN: Temporal data ═══
    val createdAt: Long = System.currentTimeMillis() / 1000,  // Unix timestamp
    val timeOfDay: String = "",          // "morning", "afternoon", "evening" (auto)
    val dayOfWeek: Int = 0,              // 1-7 (auto from timestamp)
    val isWeekend: Boolean = false,      // Auto-calculated
    val month: Int = 0,                  // 1-12 (auto from timestamp)

    // ═══ WHERE: Location data ═══
    val locationLat: Double? = null,     // GPS latitude (if available)
    val locationLng: Double? = null,     // GPS longitude (if available)
    val locationName: String = "",       // "Gikomba", "Kenyatta Market"
    val marketId: String = "",           // Backend market ID (for Soko Pulse)

    // ═══ WHO: Customer/Supplier ═══
    val customer: String = "",           // Customer name (if known)
    val supplier: String = "",           // Supplier name (for purchases)
    val isRecurringCustomer: Boolean = false,  // Auto-detected from patterns

    // ═══ HOW: Payment & context ═══
    val paymentMethod: String = "cash",  // "cash", "mpesa", "credit"
    val mpesaCode: String = "",          // M-Pesa transaction code
    val isOnCredit: Boolean = false,     // Whether this was a credit sale
    val creditDueDate: Long? = null,     // When credit is due

    // ═══ PROOF: Verification data ═══
    val confidence: Float = 1.0f,        // ASR confidence (0.0-1.0)
    val language: String = "sw",         // Language used
    val dialect: String = "",            // Dialect detected
    val hasReceipt: Boolean = false,     // Whether receipt was scanned
    val receiptImageUrl: String = "",    // Receipt image URL (if scanned)
    val verificationSource: String = "voice",  // "voice", "receipt", "mpesa", "manual"

    // ═══ SYNC: Cloud sync ═══
    val syncedAt: Long? = null,          // When synced to backend
    val syncBatchId: String = "",        // Batch ID for efficient sync
    val backendTransactionId: String = "", // Backend's ID after sync

    // ═══ NOTES ═══
    val notes: String = ""
)
```

### How Voice Maps to Data Points

Every voice interaction should extract maximum data. Here's how:

```
WORKER SAYS: "Nimeuziwa mandazi kumi, mia mbili"

VOICE PIPELINE EXTRACTS:
├── type: SALE
├── item: "mandazi"
├── category: "food" (auto-classified)
├── subcategory: "street_food" (auto-classified)
├── quantity: 10
├── unit: "pieces"
├── unitPrice: 20.0
├── totalAmount: 200.0
├── createdAt: <current timestamp>
├── timeOfDay: "morning" (auto from timestamp)
├── dayOfWeek: 3 (auto from timestamp)
├── locationLat: -1.2921 (auto from GPS)
├── locationLng: 36.8219 (auto from GPS)
├── locationName: "Gikomba" (from WorkerProfile)
├── marketId: "gikomba-main" (from backend market DB)
├── language: "sw"
├── dialect: "sheng-influenced"
├── confidence: 0.95
├── verificationSource: "voice"
└── syncedAt: null (will sync when online)

BACKEND RECEIVES:
├── All above fields
├── + productCode: "mandazi-001" (backend maps "mandazi" to product code)
├── + marketId: "gikomba-main" (backend maps location to market)
├── + backendTransactionId: "txn-abc123" (backend assigns ID)
└── + Alama Score updated with 1 more proof point
```

### Data Completeness Scoring

The app should track how complete each transaction's data is:

```kotlin
// core/common/model/DataCompleteness.kt
data class DataCompleteness(
    val hasItem: Boolean,        // "mandazi" — 99% of voice transactions
    val hasQuantity: Boolean,    // "kumi" — 85% (worker often omits)
    val hasPrice: Boolean,       // "mia mbili" — 90%
    val hasCategory: Boolean,    // Auto-classified — 95%
    val hasLocation: Boolean,    // GPS — 70% (depends on permissions)
    val hasPaymentMethod: Boolean, // "cash"/"mpesa" — 60%
    val hasCustomer: Boolean,    // Customer name — 20%
    val score: Float             // Weighted average 0.0-1.0
)
```

**Design rule:** If the worker omits price, Msaidizi should ask "Bei ngapi?" before confirming. The backend needs prices for Alama Score and Soko Pulse. Data completeness > conversational speed.

---

## 2. Current State Analysis

### 2.1 Current Package Structure

```
com.msaidizi.app/
├── agent/                          # 29 files — THE MULTI-AGENT PROBLEM
│   ├── Orchestrator.kt             # 400+ lines god-coordinator
│   ├── IntentRouter.kt             # Intent classification (KEEP — core logic)
│   ├── BusinessAgent.kt            # DELETE — just a handler wrapper
│   ├── AnalysisAgent.kt            # DELETE — just a handler wrapper
│   ├── AdvisorAgent.kt             # DELETE — just a handler wrapper
│   ├── LearningAgent.kt            # DELETE — just a handler wrapper
│   ├── TransactionHandler.kt       # MOVE → superagent:financial
│   ├── QueryHandler.kt             # MOVE → superagent:financial
│   ├── AdviceHandler.kt            # MOVE → superagent:education
│   ├── GamificationHandler.kt      # MOVE → superagent:gamification
│   ├── DomainRouter.kt             # MOVE → superagent (unified routing)
│   ├── ConversationManager.kt      # MOVE → superagent (context engine)
│   ├── ConversationMemory.kt       # MOVE → superagent (context engine)
│   ├── ContextManager.kt           # MOVE → superagent (context engine)
│   ├── AdaptiveLearningEngine.kt   # MOVE → superagent (flywheel)
│   ├── PreferenceLearner.kt        # MOVE → superagent (flywheel)
│   ├── BusinessPatternTracker.kt   # MOVE → superagent:financial
│   ├── WorkerClassifier.kt         # MOVE → superagent (context)
│   ├── VoicePersonality.kt         # MOVE → superagent:communication
│   ├── OutputSanitizer.kt          # MOVE → superagent (safety)
│   ├── ModelRouter.kt              # MOVE → core:model
│   ├── IntentPatternConfig.kt      # MOVE → superagent (reasoning)
│   ├── IntentPatternLoader.kt      # MOVE → superagent (reasoning)
│   ├── ReasoningTemplates.kt       # MOVE → superagent (reasoning)
│   ├── ErrorCompactor.kt           # MOVE → core:common
│   ├── AgentEvent.kt               # DELETE — multi-agent event system
│   ├── AgentEventBus.kt            # DELETE — multi-agent event bus
│   ├── AcademicFramework.kt        # MOVE → superagent:education
│   ├── a2a/A2AProtocol.kt          # DELETE — inter-agent protocol
│   ├── agi/AGIReadyLayer.kt        # MOVE → superagent (safety)
│   ├── agi/ReasoningModelManager.kt# MOVE → core:model
│   ├── autonomy/ProgressiveAutonomy.kt # MOVE → superagent (safety)
│   ├── cost/CostBudgetManager.kt   # MOVE → core:model
│   ├── cost/InferenceCostTracker.kt# MOVE → core:model
│   ├── credit/CreditScoringLogic.kt# MOVE → superagent:credit
│   ├── dataanalysis/               # MOVE → superagent:financial
│   ├── harness/InferenceHarness.kt # MOVE → core:model
│   ├── harness/LearningHarness.kt  # MOVE → superagent (flywheel)
│   ├── hermes/HermesSessionManager.kt # MOVE → superagent (context)
│   ├── knowledge/CrossDomainKnowledgeGraph.kt # MOVE → superagent (context)
│   ├── loops/                      # MOVE → superagent (reasoning loops)
│   ├── moe/ExpertRegistry.kt       # DELETE — multi-agent routing
│   ├── moe/MoERouter.kt           # DELETE — multi-agent routing
│   ├── multimodal/MultimodalPipeline.kt # MOVE → core:voice
│   ├── proactive/                  # MOVE → superagent:financial
│   ├── recovery/                   # MOVE → core:common
│   └── version/ModelVersionManager.kt # MOVE → core:model
│
├── core/                           # 82 files — FOUNDATION (mostly KEEP)
│   ├── ai/                         # MOVE → core:model
│   ├── database/                   # MOVE → core:database
│   ├── di/                         # RESTRUCTURE per module
│   ├── dialect/                    # 39 files! MOVE → core:common (shared)
│   ├── language/                   # MOVE → core:voice (ASR learning)
│   ├── model/                      # MOVE → core:common
│   ├── network/                    # MOVE → data
│   ├── security/                   # MOVE → core:security
│   ├── util/                       # MOVE → core:common
│   └── validation/                 # MOVE → core:common
│
├── voice/                          # 15 files — VOICE PIPELINE (KEEP)
│   ├── VoicePipeline.kt            # MOVE → core:voice
│   ├── SherpaVoiceEngine.kt        # MOVE → core:voice
│   ├── LlmEngine.kt                # MOVE → core:model
│   ├── LlamaCppEngine.kt           # MOVE → core:model
│   ├── KokoroTtsEngine.kt          # MOVE → core:voice
│   ├── SpeechRecognizer.kt         # MOVE → core:voice
│   ├── TextToSpeech.kt             # MOVE → core:voice
│   ├── AudioRecorder.kt            # MOVE → core:voice
│   ├── VoiceActivityDetector.kt    # MOVE → core:voice
│   ├── DialectLearningEngine.kt    # MOVE → core:voice
│   ├── ModelRegistry.kt            # MOVE → core:model
│   ├── VoicePipelineHarness.kt     # MOVE → core:voice
│   ├── WhisperTokenizer.kt         # MOVE → core:voice
│   └── ... (sts, streaming, etc.)  # MOVE → core:voice
│
├── cfo/                            # 7 files — FINANCIAL REASONING
│   ├── CFOEngine.kt                # MOVE → superagent:financial
│   ├── FinancialCoachOrchestrator.kt # DELETE — another orchestrator
│   ├── BudgetAnalyzerAgent.kt      # MOVE → superagent:financial (as module)
│   ├── DebtAdvisorAgent.kt         # MOVE → superagent:credit
│   ├── SavingsStrategistAgent.kt   # MOVE → superagent:financial
│   ├── BriefingDelivery.kt         # MOVE → superagent:communication
│   └── FinancialCoachIntent.kt     # MOVE → superagent:financial
│
├── finance/                        # 3 files — MOVE → superagent:goals
├── gamification/                   # 5 files — MOVE → superagent:gamification
├── mindset/                        # 2 files — MOVE → superagent:education
├── loops/                          # 7 files — MOVE → superagent (reasoning)
├── memory/                         # 1 file  — MOVE → superagent (context)
├── evolution/                      # 4 files — MOVE → superagent (flywheel)
├── social/                         # 7 files — MOVE → superagent:gamification
├── briefing/                       # 5 files — MOVE → superagent:communication
├── vision/                         # 6 files — MOVE → core:model (multimodal)
├── scanner/                        # 5 files — MOVE → superagent:financial
├── mpesa/                          # 3 files — MOVE → data
├── sync/                           # 5 files — MOVE → data
├── data/                           # 4 files — MOVE → data
├── onboarding/                     # 24 files — MOVE → onboarding
├── skills/                         # 1 file  — MOVE → superagent
├── value/                          # 1 file  — MOVE → superagent
├── update/                         # 2 files — MOVE → core:common
├── security/                       # 17 files — MOVE → core:security
└── ui/                             # 35 files — MOVE → app (UI stays in app)
```

### 2.2 Current Dependency Flow (PROBLEMATIC)

```
Voice Input
    ↓
Orchestrator (400+ lines, 40+ constructor params!)
    ↓
IntentRouter → classify intent
    ↓
AgentEventBus ←→ A2AProtocol ←→ Agent Registry
    ↓
BusinessAgent / AnalysisAgent / AdvisorAgent / LearningAgent
    ↓
TransactionHandler / QueryHandler / AdviceHandler / GamificationHandler
    ↓
DomainRouter → domain-specific handling
    ↓
ConversationManager → memory, context, LLM escalation
    ↓
OutputSanitizer → VoicePersonality → Response
```

**Problems:**
1. Orchestrator has 40+ constructor parameters (many wrapped in `Lazy<T>` to avoid cascade failures)
2. A2A Protocol adds latency for in-process communication (agents share a JVM!)
3. AgentEventBus is an unnecessary pub/sub layer for what are just function calls
4. Each "Agent" (BusinessAgent, AnalysisAgent, etc.) is a thin wrapper that delegates to handlers
5. MoE (Mixture of Experts) router duplicates IntentRouter's job
6. FinancialCoachOrchestrator duplicates Orchestrator's job for the CFO domain

---

## 3. Architecture Philosophy: Why Superagent

### 3.1 The Multi-Agent Illusion

The current codebase pretends to be multi-agent. It's not. Real multi-agent systems have:
- Agents running on separate machines/processes
- Independent state and memory
- Communication over a network
- Failure isolation

Msaidizi's "agents" share:
- The same JVM process
- The same Room database
- The same memory space
- The same failure domain

**The A2A protocol is a network protocol for in-process function calls.** This is architectural cosplay.

### 3.2 The Superagent Principle

A superagent is ONE agent with MANY capabilities:

```
┌─────────────────────────────────────────────────────┐
│                 SUPERAGENT                           │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │         Unified Reasoning Engine              │   │
│  │  (IntentRouter + Context + Confidence)        │   │
│  └──────────────────────────────────────────────┘   │
│           │           │           │          │       │
│  ┌────────┴──┐ ┌──────┴────┐ ┌───┴────┐ ┌───┴────┐ │
│  │ Financial │ │  Credit   │ │ Goals  │ │ Edu    │ │
│  │ Reasoning │ │  Analysis │ │ Module │ │ Module │ │
│  └───────────┘ └───────────┘ └────────┘ └────────┘ │
│           │           │           │          │       │
│  ┌──────────────────────────────────────────────┐   │
│  │          Shared Context Engine                │   │
│  │  (Worker Profile + Memory + Patterns)         │   │
│  └──────────────────────────────────────────────┘   │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │          Flywheel Learning Engine              │   │
│  │  (Use → Learn → Improve → Use More)           │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 3.3 What Changes

| Aspect | Multi-Agent (Current) | Superagent (New) |
|--------|----------------------|-------------------|
| Identity | 4 agents + handlers | 1 agent, 4 capability modules |
| Communication | A2A protocol + EventBus | Direct function calls |
| Routing | Orchestrator → IntentRouter → Agent → Handler | ReasoningEngine → Module |
| State | Distributed across agents | Shared Context Engine |
| Learning | Per-agent learning | Unified Flywheel |
| Constructor | 40+ params (Orchestrator) | ~10 params (ReasoningEngine) |
| Latency | Event bus + A2A overhead | Direct calls (0 overhead) |
| Complexity | O(n²) agent interactions | O(n) module capabilities |

---

## 4. New Module Structure

```
msaidizi/
├── settings.gradle.kts              # Module declarations
├── build.gradle.kts                 # Root build config
│
├── app/                             # APPLICATION SHELL (minimal)
│   └── src/main/java/com/msaidizi/app/
│       ├── MsaidiziApp.kt           # Hilt application
│       ├── MainActivity.kt          # Single activity
│       ├── navigation/              # Nav graph
│       └── ui/                      # ALL UI screens (unchanged)
│
├── core/                            # CORE MODULES (shared foundations)
│   ├── common/                      # :core:common
│   │   └── src/main/java/com/msaidizi/core/common/
│   │       ├── model/               # Data classes, enums, value objects
│   │       ├── util/                # SwahiliParser, CrashLogger, DeviceTier
│   │       ├── validation/          # FinancialValidator, CurrencyFormatter
│   │       └── error/               # ErrorCompactor, Result types
│   │
│   ├── database/                    # :core:database
│   │   └── src/main/java/com/msaidizi/core/database/
│   │       ├── AppDatabase.kt       # Room database (single source of truth)
│   │       ├── entity/              # All Room entities
│   │       ├── dao/                 # All DAOs
│   │       └── converter/           # Type converters
│   │
│   ├── voice/                       # :core:voice
│   │   └── src/main/java/com/msaidizi/core/voice/
│   │       ├── stt/                 # Speech-to-Text (Sherpa-ONNX)
│   │       ├── tts/                 # Text-to-Speech (Kokoro, Piper, MMS)
│   │       ├── vad/                 # Voice Activity Detection
│   │       ├── pipeline/            # VoicePipeline, StreamingPipeline
│   │       ├── dialect/             # DialectDetectionEngine
│   │       ├── emotion/             # VoiceEmotionDetector
│   │       └── recorder/            # AudioRecorder, VoiceForegroundService
│   │
│   ├── model/                       # :core:model
│   │   └── src/main/java/com/msaidizi/core/model/
│   │       ├── llm/                 # LlmEngine, LlamaCppEngine
│   │       ├── manager/             # ModelManager, BundledModelManager
│   │       ├── downloader/          # ModelDownloader, DownloadProgressTracker
│   │       ├── registry/            # ModelRegistry, VoiceModelRegistry
│   │       ├── inference/           # InferenceHarness, CostBudgetManager
│   │       └── version/             # ModelVersionManager
│   │
│   └── security/                    # :core:security
│       └── src/main/java/com/msaidizi/core/security/
│           ├── auth/                # BiometricAuth, JWT, OTP, Session
│           ├── crypto/              # CryptoService, EncryptedStorage, TLS
│           ├── pqc/                 # Post-Quantum Crypto (ML-KEM, ML-DSA)
│           ├── privacy/             # Consent, DataMinimizer, DifferentialPrivacy
│           ├── validation/          # InputSanitizer, ApiValidator
│           └── simswap/             # DeviceBinder, SuspiciousLoginDetector
│
├── superagent/                      # THE UNIFIED AGENT
│   ├── engine/                      # :superagent:engine
│   │   └── src/main/java/com/msaidizi/superagent/engine/
│   │       ├── ReasoningEngine.kt   # THE unified brain (replaces Orchestrator)
│   │       ├── IntentClassifier.kt  # Renamed from IntentRouter (same logic)
│   │       ├── ConfidenceRouter.kt  # Confidence-based routing
│   │       ├── DataCompletenessChecker.kt # NEW: ensures backend gets complete data
│   │       ├── OutputSanitizer.kt   # Defense-in-depth output filtering
│   │       ├── SafetyGuard.kt       # AGI safety boundaries
│   │       └── AutonomyManager.kt   # Progressive autonomy
│   │
│   ├── context/                     # :superagent:context
│   │   └── src/main/java/com/msaidizi/superagent/context/
│   │       ├── ContextEngine.kt     # THE shared context (replaces ContextManager)
│   │       ├── WorkerProfile.kt     # Worker identity, business, patterns
│   │       ├── ConversationMemory.kt# L1: in-session memory
│   │       ├── EpisodicMemory.kt    # L2: cross-session memory
│   │       ├── KnowledgeGraph.kt    # L3: cross-domain knowledge
│   │       ├── ProofIdentity.kt     # L5: M-KOPA proof accumulation
│   │       └── HermesSession.kt     # Session management
│   │
│   ├── flywheel/                    # :superagent:flywheel
│   │   └── src/main/java/com/msaidizi/superagent/flywheel/
│   │       ├── FlywheelEngine.kt    # THE proof + learning flywheel
│   │       ├── AlamaScoreEngine.kt  # Alama Score calculator (M-KOPA model)
│   │       ├── ProofPointModels.kt  # ProofPoint, ProofType, AlamaTier
│   │       ├── AdaptiveLearning.kt  # Intent learning from corrections
│   │       ├── PreferenceLearner.kt # User preference tracking
│   │       ├── PatternTracker.kt    # Business pattern detection
│   │       ├── SelfEvolution.kt     # Self-improvement cycle
│   │       └── FeedbackCollector.kt # User feedback ingestion
│   │
│   ├── financial/                   # :superagent:financial
│   │   └── src/main/java/com/msaidizi/superagent/financial/
│   │       ├── FinancialModule.kt   # Module entry point
│   │       ├── TransactionEngine.kt # Sale, purchase, expense recording
│   │       ├── QueryEngine.kt       # Balance, profit, stock queries
│   │       ├── CFOEngine.kt         # Proactive financial management
│   │       ├── BudgetAnalyzer.kt    # Budget analysis
│   │       ├── SavingsStrategist.kt # Savings recommendations
│   │       ├── CashFlowPredictor.kt # Cash flow forecasting
│   │       ├── AnomalyDetector.kt   # Financial anomaly detection
│   │       ├── StockOutPredictor.kt # Inventory prediction
│   │       ├── ProactiveAlerts.kt   # Proactive alert engine
│   │       ├── ReceiptScanner.kt    # Receipt scanning pipeline
│   │       ├── DataAnalysis.kt      # Safe query execution, summarization
│   │       └── MpesaIntegration.kt  # M-Pesa SMS parsing, Daraja API
│   │
│   ├── credit/                      # :superagent:credit
│   │   └── src/main/java/com/msaidizi/superagent/credit/
│   │       ├── CreditModule.kt      # Module entry point
│   │       ├── CreditScorer.kt      # Credit scoring logic
│   │       ├── DebtAdvisor.kt       # Debt management advice
│   │       ├── LoanManager.kt       # Loan tracking and management
│   │       └── CreditReadiness.kt   # Credit readiness assessment
│   │
│   ├── goals/                       # :superagent:goals
│   │   └── src/main/java/com/msaidizi/superagent/goals/
│   │       ├── GoalsModule.kt       # Module entry point
│   │       ├── GoalPlanner.kt       # Goal creation and tracking
│   │       ├── GoalEngine.kt        # Goal progress, forecasting, adjustment
│   │       ├── TitheTracker.kt      # Tithe/giving tracking
│   │       └── GoalModels.kt        # Goal-specific data classes
│   │
│   ├── education/                   # :superagent:education
│   │   └── src/main/java/com/msaidizi/superagent/education/
│   │       ├── EducationModule.kt   # Module entry point
│   │       ├── MindsetAcademy.kt    # Financial literacy lessons
│   │       ├── RichHabitsScore.kt   # Daily habits scoring
│   │       ├── AcademicFramework.kt # Educational content framework
│   │       └── AdviceEngine.kt      # Financial advice generation
│   │
│   ├── gamification/                # :superagent:gamification
│   │   └── src/main/java/com/msaidizi/superagent/gamification/
│   │       ├── GamificationModule.kt# Module entry point
│   │       ├── GamificationEngine.kt# Points, badges, levels
│   │       ├── StreakEngine.kt      # Streak tracking and protection
│   │       ├── RewardEngine.kt      # Micro-rewards, variable rewards
│   │       ├── SocialFeatures.kt    # Leaderboard, peer comparison
│   │       └── CommunityTips.kt     # Community-driven tips
│   │
│   └── communication/               # :superagent:communication
│       └── src/main/java/com/msaidizi/superagent/communication/
│           ├── CommunicationModule.kt # Module entry point
│           ├── VoicePersonality.kt  # Warmth, proverbs, cultural flavor
│           ├── BriefingEngine.kt    # Daily briefing generation
│           ├── BriefingDelivery.kt  # Audio briefing delivery
│           ├── DialectAdapter.kt    # Dialect-specific output formatting
│           └── OutputFormatter.kt   # Response formatting for voice
│
├── data/                            # :data (API, sync, repositories)
│   └── src/main/java/com/msaidizi/data/
│       ├── api/                     # MsaidiziApi, network layer
│       ├── sync/                    # SyncManager, SyncQueue, OfflineManager
│       ├── repository/              # Repository implementations
│       └── model/                   # API models, WhatsApp models
│
└── onboarding/                      # :onboarding (bootstrap experience)
    └── src/main/java/com/msaidizi/onboarding/
        ├── OnboardingActivity.kt    # Onboarding entry point
        ├── BootstrapConversation.kt # Voice-guided introduction
        ├── WorkerProfileSetup.kt    # Name, business, location capture
        ├── LanguageSelection.kt     # Language/dialect selection
        ├── VoiceSetup.kt            # Voice calibration
        ├── ModelDownload.kt         # Model download management
        ├── AhaMomentFlow.kt         # First "wow" moment
        └── fragments/               # UI fragments for onboarding
```

---

## 5. Detailed Module Design

### 5.1 `:superagent:engine` — The Unified Brain

**Replaces:** Orchestrator, IntentRouter, DomainRouter, Agent routing

**The ReasoningEngine is the ONLY entry point for user input.** It has ~10 constructor parameters, not 40+.

```kotlin
class ReasoningEngine(
    // Core reasoning
    private val intentClassifier: IntentClassifier,      // from IntentRouter
    private val confidenceRouter: ConfidenceRouter,       // from ConversationManager
    private val dataCompletenessChecker: DataCompletenessChecker, // NEW: backend data quality
    private val safetyGuard: SafetyGuard,                 // from AGIReadyLayer
    private val autonomyManager: AutonomyManager,         // from ProgressiveAutonomy
    private val outputSanitizer: OutputSanitizer,         // from OutputSanitizer
    // Capability modules (direct references, no event bus)
    private val financialModule: FinancialModule,
    private val creditModule: CreditModule,
    private val goalsModule: GoalsModule,
    private val educationModule: EducationModule,
    private val gamificationModule: GamificationModule,
    private val communicationModule: CommunicationModule,
    // Shared systems
    private val contextEngine: ContextEngine,
    private val flywheel: FlywheelEngine
) {
    suspend fun processInput(text: String, language: String = "sw"): AgentResponse {
        // 1. Classify intent (code-first, 90% no LLM)
        val intent = intentClassifier.classify(text)

        // 2. Resolve context (follow-ups, references, L2/L3 memory)
        val resolved = contextEngine.resolve(text, intent)

        // 3. Check data completeness (M-KOPA: collect RIGHT data for backend)
        val completeness = dataCompletenessChecker.check(resolved)
        if (completeness.needsFollowUp()) {
            // Ask for missing data before processing
            // "Bei ngapi?" or "Uko wapi?"
            val followUp = dataCompletenessChecker.generateFollowUp(completeness, language)
            return AgentResponse(
                text = followUp,
                type = ResponseType.CLARIFICATION,
                shouldSpeak = true,
                data = mapOf("needsData" to "true", "missing" to completeness.missingFields.joinToString(","))
            )
        }

        // 4. Route to capability module (direct call, no event bus)
        val response = when (resolved.intent.domain) {
            Domain.FINANCIAL -> financialModule.handle(resolved)
            Domain.CREDIT -> creditModule.handle(resolved)
            Domain.GOALS -> goalsModule.handle(resolved)
            Domain.EDUCATION -> educationModule.handle(resolved)
            Domain.GAMIFICATION -> gamificationModule.handle(resolved)
        }

        // 5. Safety check
        val safe = safetyGuard.check(response, text, language)

        // 6. Autonomy check
        val approved = autonomyManager.check(safe, resolved)

        // 7. Apply personality (warmth, proverbs)
        val personalized = communicationModule.personalize(approved, language)

        // 8. Learn from this interaction
        flywheel.record(text, resolved, personalized)

        // 9. Store in context
        contextEngine.store(text, resolved, personalized)

        return personalized
    }
}
```

**Key differences from Orchestrator:**
- No AgentEventBus dependency
- No A2AProtocol dependency
- No separate Agent classes (BusinessAgent, AnalysisAgent, etc.)
- Direct module calls instead of event-driven routing
- Context engine is shared, not per-agent
- Learning is unified in the flywheel

### 5.2 `:superagent:context` — Shared Context Engine

**Replaces:** ContextManager, ConversationManager, ConversationMemory, EpisodicMemory, HermesSessionManager, CrossDomainKnowledgeGraph

One context engine, shared by all modules. Every module reads from and writes to the same context.

```
┌─────────────────────────────────────────┐
│           ContextEngine                  │
│                                         │
│  L1: ConversationMemory (in-session)    │
│      - Last N turns                     │
│      - Current topic                    │
│      - Pending corrections              │
│                                         │
│  L2: EpisodicMemory (cross-session)     │
│      - Past interactions                │
│      - Outcome tracking                 │
│      - Relevance scoring                │
│                                         │
│  L3: WorkerProfile (persistent)         │
│      - Name, business, location         │
│      - Frequent topics                  │
│      - Dialect preferences              │
│      - Financial patterns               │
│      - Learning progress                │
│                                         │
│  L4: KnowledgeGraph (cross-domain)      │
│      - Business relationships           │
│      - Market patterns                  │
│      - Cross-module insights            │
└─────────────────────────────────────────┘
```

### 5.3 `:superagent:flywheel` — Learning Engine

**Replaces:** AdaptiveLearningEngine, PreferenceLearner, BusinessPatternTracker, SelfEvolutionManager, FeedbackCollector, LearningHarness

```
Use → Learn → Improve → Use More
  ↑                        │
  └────────────────────────┘
```

The flywheel is a single engine that:
1. **Records** every interaction (intent, confidence, outcome)
2. **Learns** from corrections and confirmations
3. **Improves** intent classification, response quality, personalization
4. **Measures** improvement via metrics

```kotlin
class FlywheelEngine(
    private val adaptiveLearning: AdaptiveLearning,
    private val preferenceLearner: PreferenceLearner,
    private val patternTracker: PatternTracker,
    private val selfEvolution: SelfEvolution,
    private val feedbackCollector: FeedbackCollector
) {
    fun record(input: String, intent: IntentResult, response: AgentResponse) {
        adaptiveLearning.record(input, intent)
        preferenceLearner.update(input, response)
        patternTracker.track(intent)
        feedbackCollector.ingest(input, response)
    }

    fun improve() {
        adaptiveLearning.retrain()
        preferenceLearner.consolidate()
        patternTracker.updatePatterns()
        selfEvolution.evolve()
    }
}
```

### 5.4 `:superagent:financial` — Financial Reasoning Module

**Replaces:** TransactionHandler, QueryHandler, CFOEngine, BudgetAnalyzerAgent, SavingsStrategistAgent, CashFlowPredictor, StockOutPredictor, ProactiveAlertEngine, ReceiptScanner, DataAnalysis (SwahiliQueryParser, SafeQueryExecutor, ResultSummarizer)

This is the largest capability module. It handles:
- Transaction recording (sale, purchase, expense)
- Financial queries (balance, profit, stock, summaries)
- Proactive financial management (CFO engine)
- Cash flow prediction and anomaly detection
- Receipt scanning and M-Pesa integration

```kotlin
class FinancialModule(
    private val transactionEngine: TransactionEngine,
    private val queryEngine: QueryEngine,
    private val cfoEngine: CFOEngine,
    private val proactiveAlerts: ProactiveAlerts,
    private val receiptScanner: ReceiptScanner,
    private val contextEngine: ContextEngine
) {
    suspend fun handle(resolved: ResolvedIntent): AgentResponse {
        return when (resolved.intent) {
            IntentType.SALE -> transactionEngine.recordSale(resolved)
            IntentType.PURCHASE -> transactionEngine.recordPurchase(resolved)
            IntentType.EXPENSE -> transactionEngine.recordExpense(resolved)
            IntentType.PROFIT_QUERY -> queryEngine.getProfit(resolved)
            IntentType.CHECK_BALANCE -> queryEngine.getBalance(resolved)
            IntentType.STOCK_QUERY -> queryEngine.getStock(resolved)
            IntentType.DAILY_SUMMARY -> queryEngine.getDailySummary(resolved)
            IntentType.WEEKLY_SUMMARY -> queryEngine.getWeeklySummary(resolved)
            IntentType.RECEIPT_SCAN -> receiptScanner.prompt(resolved)
            else -> throw UnsupportedIntentException(resolved.intent)
        }
    }
}
```

### 5.5 `:superagent:credit` — Credit Analysis Module

**Replaces:** CreditScoringLogic, DebtAdvisorAgent, LoanManager

```kotlin
class CreditModule(
    private val creditScorer: CreditScorer,
    private val debtAdvisor: DebtAdvisor,
    private val loanManager: LoanManager,
    private val contextEngine: ContextEngine
) {
    suspend fun handle(resolved: ResolvedIntent): AgentResponse {
        return when (resolved.intent) {
            IntentType.LOAN_RECORD -> loanManager.record(resolved)
            IntentType.LOAN_QUERY -> loanManager.query(resolved)
            IntentType.LOAN_REPORT -> loanManager.report(resolved)
            IntentType.LOAN_DEADLINE -> loanManager.deadline(resolved)
            IntentType.CREDIT_SCORE -> creditScorer.assess(resolved)
            IntentType.DEBT_ADVICE -> debtAdvisor.advise(resolved)
            else -> throw UnsupportedIntentException(resolved.intent)
        }
    }
}
```

### 5.6 `:superagent:goals` — Goals, Loans, Tithe

**Replaces:** GoalPlanner, GoalEngine (from GamificationHandler), TitheTracker

```kotlin
class GoalsModule(
    private val goalPlanner: GoalPlanner,
    private val goalEngine: GoalEngine,
    private val titheTracker: TitheTracker,
    private val contextEngine: ContextEngine
) {
    suspend fun handle(resolved: ResolvedIntent): AgentResponse {
        return when (resolved.intent) {
            IntentType.GOAL_CREATE -> goalPlanner.create(resolved)
            IntentType.GOAL_PROGRESS -> goalEngine.progress(resolved)
            IntentType.GOAL_REPORT -> goalEngine.report(resolved)
            IntentType.GOAL_TIME_FORECAST -> goalEngine.forecast(resolved)
            IntentType.GOAL_ADJUST -> goalEngine.adjust(resolved)
            IntentType.GOAL_ENCOURAGEMENT -> goalEngine.encourage(resolved)
            IntentType.GIVING_RECORD -> titheTracker.record(resolved)
            IntentType.GIVING_QUERY -> titheTracker.query(resolved)
            IntentType.GIVING_GOAL -> titheTracker.goal(resolved)
            else -> throw UnsupportedIntentException(resolved.intent)
        }
    }
}
```

### 5.7 `:superagent:education` — Financial Literacy

**Replaces:** MindsetAcademy, RichHabitsScore, AcademicFramework, AdviceHandler

```kotlin
class EducationModule(
    private val mindsetAcademy: MindsetAcademy,
    private val richHabits: RichHabitsScore,
    private val adviceEngine: AdviceEngine,
    private val contextEngine: ContextEngine
) {
    suspend fun handle(resolved: ResolvedIntent): AgentResponse {
        return when (resolved.intent) {
            IntentType.ASK_ADVICE -> adviceEngine.advise(resolved)
            IntentType.GREETING -> adviceEngine.greet(resolved)
            IntentType.HELP -> adviceEngine.help(resolved)
            IntentType.MINDSET_LESSON -> mindsetAcademy.teach(resolved)
            IntentType.HABITS_CHECK -> richHabits.assess(resolved)
            else -> throw UnsupportedIntentException(resolved.intent)
        }
    }
}
```

### 5.8 `:superagent:gamification` — Points, Badges, Streaks

**Replaces:** GamificationEngine, InsightRewards, LevelProgressionRewards, MicroRewards, StreakRecovery, SocialHandler, LeaderboardService, PeerComparison, CommunityTips, StreakProtectionLoop, VariableRewardsLoop

```kotlin
class GamificationModule(
    private val gamificationEngine: GamificationEngine,
    private val streakEngine: StreakEngine,
    private val rewardEngine: RewardEngine,
    private val socialFeatures: SocialFeatures,
    private val contextEngine: ContextEngine
) {
    suspend fun handle(resolved: ResolvedIntent): AgentResponse {
        // Gamification is mostly passive — triggered by other modules
        // via events, not direct calls
        return when (resolved.intent) {
            IntentType.BADGE_QUERY -> gamificationEngine.queryBadges(resolved)
            IntentType.LEADERBOARD -> socialFeatures.getLeaderboard(resolved)
            else -> throw UnsupportedIntentException(resolved.intent)
        }
    }

    // Called by other modules after successful actions
    fun onTransaction(recorded: Transaction) { ... }
    fun onGoalProgress(goalId: Long, progress: Double) { ... }
    fun onStreakDay() { ... }
}
```

### 5.9 `:superagent:communication` — Voice Output & Dialect

**Replaces:** VoicePersonality, BriefingDelivery, AudioBriefingGenerator, AudioBriefingDelivery, AudioBriefingTextTransformer, MorningBriefingLoop

```kotlin
class CommunicationModule(
    private val voicePersonality: VoicePersonality,
    private val briefingEngine: BriefingEngine,
    private val briefingDelivery: BriefingDelivery,
    private val dialectAdapter: DialectAdapter
) {
    fun personalize(response: AgentResponse, language: String): AgentResponse {
        val withPersonality = voicePersonality.wrap(response, language)
        return dialectAdapter.adapt(withPersonality, language)
    }

    suspend fun deliverMorningBriefing(language: String) { ... }
    suspend fun deliverProactiveAlert(alert: Alert, language: String) { ... }
}
```

### 5.10 `:core:voice` — Voice Pipeline

**Replaces:** All files in `voice/` package

```
core/voice/
├── stt/
│   ├── SherpaVoiceEngine.kt         # Sherpa-ONNX STT
│   ├── SpeechRecognizer.kt          # High-level recognizer
│   ├── WhisperTokenizer.kt          # Whisper tokenizer
│   └── AdaptiveAsrEngine.kt         # Adaptive ASR (from core/language)
├── tts/
│   ├── TextToSpeech.kt              # TTS interface
│   ├── KokoroTtsEngine.kt           # Kokoro TTS
│   ├── MMSTextToSpeech.kt           # MMS TTS
│   └── VoiceModelRegistry.kt        # TTS model registry
├── vad/
│   ├── VoiceActivityDetector.kt     # Silero VAD
│   └── AudioRecorder.kt             # Audio recording
├── pipeline/
│   ├── VoicePipeline.kt             # Main pipeline (STT → Agent → TTS)
│   ├── StreamingVoicePipeline.kt    # Streaming pipeline
│   ├── VoicePipelineHarness.kt      # Monitoring/fallback
│   └── MultimodalPipeline.kt        # Multimodal (voice + vision)
├── dialect/
│   ├── DialectDetectionEngine.kt    # Dialect detection
│   ├── DialectLearningEngine.kt     # Dialect learning
│   └── WaxalAdapter.kt             # Waxal dialect enhancer
├── emotion/
│   ├── VoiceEmotionDetector.kt      # Emotion detection
│   └── AudioFeatureExtractor.kt     # Audio feature extraction
├── sts/
│   ├── SpeechToSpeechEngine.kt      # STS engine
│   └── providers/                   # ElevenLabs, GPT Realtime, Local
└── service/
    └── VoiceForegroundService.kt    # Background voice service
```

### 5.11 `:core:model` — LLM Engine

**Replaces:** All files in `core/ai/`, `voice/LlmEngine.kt`, `voice/LlamaCppEngine.kt`, `voice/ModelRegistry.kt`, `agent/ModelRouter.kt`, `agent/cost/`, `agent/harness/`, `agent/version/`, `agent/agi/ReasoningModelManager.kt`

```
core/model/
├── llm/
│   ├── LlmEngine.kt                 # High-level LLM interface
│   ├── LlamaCppEngine.kt            # llama.cpp JNI bridge
│   └── ModelRouter.kt               # Route to appropriate model tier
├── manager/
│   ├── ModelManager.kt              # Model lifecycle management
│   ├── BundledModelManager.kt       # Bundled model handling
│   └── SequentialModelLoader.kt     # Sequential model loading
├── downloader/
│   ├── ModelDownloader.kt           # Model download
│   ├── DownloadProgressTracker.kt   # Progress tracking
│   └── DataSaverManager.kt          # Data saver awareness
├── registry/
│   ├── ModelRegistry.kt             # Model registry
│   └── VoiceModelRegistry.kt        # Voice model registry
├── inference/
│   ├── InferenceHarness.kt          # Monitoring, fallback, retry
│   ├── CostBudgetManager.kt         # Cost tracking
│   └── InferenceCostTracker.kt      # Per-user cost tracking
└── version/
    └── ModelVersionManager.kt       # Model versioning
```

### 5.12 `:core:database` — Room Database

**Replaces:** All files in `core/database/`

```
core/database/
├── AppDatabase.kt                   # Room database (single source of truth)
├── entity/
│   ├── TransactionEntity.kt
│   ├── GoalEntity.kt
│   ├── LoanEntity.kt
│   ├── TitheEntity.kt
│   ├── GamificationEntity.kt
│   ├── InventoryEntity.kt
│   ├── SessionEntity.kt
│   ├── AgentTraceEntity.kt
│   ├── KnowledgeNodeEntity.kt
│   ├── KnowledgeEdgeEntity.kt
│   ├── BriefingDeliveryEntity.kt
│   ├── VocabularyEntity.kt
│   └── StickinessEntity.kt
│   └── ProofPointEntity.kt     # NEW: M-KOPA proof points
├── dao/
│   ├── TransactionDao.kt
│   ├── GoalDao.kt
│   ├── LoanDao.kt
│   ├── TitheDao.kt
│   ├── GamificationDao.kt
│   ├── InventoryDao.kt
│   ├── SessionDao.kt
│   ├── AgentTraceDao.kt
│   ├── KnowledgeDao.kt
│   ├── BriefingDeliveryDao.kt
│   ├── VocabularyLearningDao.kt
│   ├── PatternDao.kt
│   └── StickinessDao.kt
│   └── ProofPointDao.kt        # NEW: proof point queries
└── converter/
    └── Converters.kt
```

### 5.13 `:core:security` — Auth, Crypto, PQC

**Replaces:** All files in `security/` and `core/security/`

```
core/security/
├── auth/
│   ├── BiometricAuthManager.kt
│   ├── JwtTokenManager.kt
│   ├── OtpManager.kt
│   ├── SecureTokenStorage.kt
│   └── SessionManager.kt
├── crypto/
│   ├── CryptoService.kt
│   ├── CryptoServiceImpl.kt
│   ├── DatabaseKeyManager.kt
│   ├── EncryptedStorage.kt
│   └── TlsConfig.kt
├── pqc/
│   ├── AlgorithmRegistry.kt
│   ├── CryptoAuditLogger.kt
│   ├── CryptoProvider.kt
│   ├── DocumentSigner.kt
│   ├── HybridKeyExchange.kt
│   ├── MlDsaProvider.kt
│   ├── MlKemProvider.kt
│   └── PqcConfig.kt
├── privacy/
│   ├── ConsentManager.kt
│   ├── DataMinimizer.kt
│   ├── DataRetentionManager.kt
│   ├── DifferentialPrivacy.kt
│   └── FederatedLearningPrivacy.kt
├── validation/
│   ├── ApiValidator.kt
│   └── InputSanitizer.kt
├── simswap/
│   ├── DeviceBinder.kt
│   └── SuspiciousLoginDetector.kt
├── DeviceBinder.kt                  # core/security DeviceBinder
└── QuantumReadyLayer.kt
```

### 5.14 `:data` — API, Sync, Repositories

**Replaces:** `data/`, `sync/`, `mpesa/`, `core/network/`

**Critical role:** This module is the bridge between the app (data collector) and the backend (intelligence engine). Every sync operation must send backend-optimized data.

```
data/
├── api/
│   ├── MsaidiziApi.kt              # Retrofit API interface
│   ├── PinnedHttpClient.kt         # from core/network
│   └── BackendSyncApi.kt           # NEW: Backend-specific sync endpoints
├── sync/
│   ├── SyncManager.kt              # Orchestrates sync operations
│   ├── SyncQueue.kt                # Queues data for sync when offline
│   ├── BiasharaSync.kt             # Business data sync
│   ├── OfflineManager.kt           # Offline-first logic
│   ├── NetworkMonitor.kt           # Network state awareness
│   ├── SyncConflictResolver.kt     # Conflict resolution
│   ├── SyncableEntities.kt         # Entities that sync to backend
│   └── BackendDataMapper.kt        # NEW: Maps app data to backend format
├── mpesa/
│   ├── DarajaClient.kt             # M-Pesa API client
│   ├── MpesaSmsReceiver.kt         # SMS parsing
│   └── MpesaStatementParser.kt     # Statement parsing
├── repository/
│   └── (Repository implementations)
└── model/
    ├── ApiModels.kt
    ├── WhatsAppModels.kt
    ├── BackendTransactionPayload.kt # NEW: What backend receives
    ├── BackendSyncBatch.kt          # NEW: Batched sync payload
    └── BackendProofPoint.kt         # NEW: Proof point for Alama Score
```

### Backend Sync Payload Structure

Every sync batch sends this to the backend:

```kotlin
// data/model/BackendTransactionPayload.kt
data class BackendTransactionPayload(
    val workerId: String,              // Worker's unique ID
    val transactionId: String,         // App-generated UUID
    val type: String,                  // "SALE", "PURCHASE", "EXPENSE"
    val item: String,                  // "mandazi"
    val category: String,              // "food"
    val subcategory: String,           // "street_food"
    val quantity: Double,              // 10.0
    val unit: String,                  // "pieces"
    val unitPrice: Double,             // 20.0
    val totalAmount: Double,           // 200.0
    val costBasis: Double,             // 120.0 (if known)
    val margin: Double,                // 80.0
    val marginPercent: Double,         // 0.4
    val paymentMethod: String,         // "cash"
    val mpesaCode: String?,            // "QHK71H3F4P" (if M-Pesa)
    val locationLat: Double?,          // -1.2921
    val locationLng: Double?,          // 36.8219
    val locationName: String,          // "Gikomba"
    val timestamp: Long,               // Unix seconds
    val timeOfDay: String,             // "morning"
    val dayOfWeek: Int,                // 3
    val confidence: Float,             // 0.95
    val verificationSource: String,    // "voice"
    val dataCompleteness: Float        // 0.85
)

// data/model/BackendSyncBatch.kt
data class BackendSyncBatch(
    val batchId: String,               // UUID for this batch
    val workerId: String,
    val transactions: List<BackendTransactionPayload>,
    val proofPoints: List<BackendProofPoint>,
    val workerProfile: BackendWorkerProfile,
    val deviceInfo: DeviceInfo,
    val syncTimestamp: Long
)

// data/model/BackendProofPoint.kt
data class BackendProofPoint(
    val proofType: String,             // "TRANSACTION", "GOAL_PROGRESS", etc.
    val weight: Double,                // 1.0, 1.5, etc.
    val timestamp: Long,
    val data: Map<String, String>      // Proof-specific data
)
```

### Sync Strategy

```
┌─────────────────────────────────────────────────────────────┐
│                    SYNC STRATEGY                            │
│                                                             │
│  OFFLINE (no internet):                                     │
│  ├── Transactions saved to Room DB immediately              │
│  ├── Alama Score calculated locally                         │
│  ├── Proof points queued in SyncQueue                       │
│  └── Worker experience unaffected                           │
│                                                             │
│  ONLINE (internet available):                               │
│  ├── SyncManager picks up queued items                      │
│  ├── Batches into BackendSyncBatch (max 100 items)          │
│  ├── Compresses payload (gzip)                              │
│  ├── Sends to backend via BackendSyncApi                    │
│  ├── Receives updated Alama Score from backend              │
│  ├── Receives new capabilities if tier changed              │
│  └── Marks items as synced in Room DB                       │
│                                                             │
│  CONFLICT RESOLUTION:                                       │
│  ├── Backend is authoritative for Alama Score               │
│  ├── App is authoritative for transaction data              │
│  └── Last-write-wins for worker profile                     │
└─────────────────────────────────────────────────────────────┘
```

### 5.15 `:onboarding` — Bootstrap Experience

**Replaces:** All files in `onboarding/`

```
onboarding/
├── OnboardingActivity.kt
├── bootstrap/
│   ├── BootstrapActivity.kt
│   ├── BootstrapConversation.kt
│   ├── BootstrapViewModel.kt
│   └── WorkerUnderstanding.kt
├── conversation/
│   ├── OnboardingConversation.kt
│   ├── BootstrapConversation.kt    # from onboarding/ root
│   └── AhaMomentFlow.kt
├── setup/
│   ├── LanguageSelectionFragment.kt
│   ├── VoiceSetupFragment.kt
│   ├── BusinessDiscoveryFragment.kt
│   ├── AgentNamingFragment.kt
│   ├── PersonalityFragment.kt
│   ├── PhoneVerificationFragment.kt
│   ├── WhatsAppConnectionStepFragment.kt
│   └── ModelSetupFragment.kt
├── manager/
│   ├── ModelDownloadManager.kt
│   ├── ModelSetupViewModel.kt
│   ├── SmsVerificationManager.kt
│   └── WhatsAppVerificationManager.kt
└── model/
    ├── WorkerProfile.kt
    ├── WorkerProfileDao.kt
    ├── SupportedLanguage.kt
    └── PhoneVerificationStep.kt
```

---

## 6. File Migration Map: What Moves Where

### 6.1 Agent Package (29 files → scattered)

| Current File | Action | Destination |
|---|---|---|
| `agent/Orchestrator.kt` | **DELETE** | Replaced by `superagent/engine/ReasoningEngine.kt` |
| `agent/IntentRouter.kt` | **MOVE** | `superagent/engine/IntentClassifier.kt` |
| `agent/BusinessAgent.kt` | **DELETE** | Was just a thin wrapper |
| `agent/AnalysisAgent.kt` | **DELETE** | Was just a thin wrapper |
| `agent/AdvisorAgent.kt` | **DELETE** | Was just a thin wrapper |
| `agent/LearningAgent.kt` | **DELETE** | Was just a thin wrapper |
| `agent/TransactionHandler.kt` | **MOVE** | `superagent/financial/TransactionEngine.kt` |
| `agent/QueryHandler.kt` | **MOVE** | `superagent/financial/QueryEngine.kt` |
| `agent/AdviceHandler.kt` | **MOVE** | `superagent/education/AdviceEngine.kt` |
| `agent/GamificationHandler.kt` | **MOVE** | `superagent/gamification/GamificationModule.kt` |
| `agent/DomainRouter.kt` | **MOVE** | `superagent/engine/IntentClassifier.kt` (merged) |
| `agent/ConversationManager.kt` | **MOVE** | `superagent/context/ContextEngine.kt` |
| `agent/ConversationMemory.kt` | **MOVE** | `superagent/context/ConversationMemory.kt` |
| `agent/ContextManager.kt` | **MOVE** | `superagent/context/ContextEngine.kt` |
| `agent/AdaptiveLearningEngine.kt` | **MOVE** | `superagent/flywheel/AdaptiveLearning.kt` |
| `agent/PreferenceLearner.kt` | **MOVE** | `superagent/flywheel/PreferenceLearner.kt` |
| `agent/BusinessPatternTracker.kt` | **MOVE** | `superagent/flywheel/PatternTracker.kt` |
| `agent/WorkerClassifier.kt` | **MOVE** | `superagent/context/WorkerProfile.kt` |
| `agent/VoicePersonality.kt` | **MOVE** | `superagent/communication/VoicePersonality.kt` |
| `agent/OutputSanitizer.kt` | **MOVE** | `superagent/engine/OutputSanitizer.kt` |
| `agent/ModelRouter.kt` | **MOVE** | `core/model/ModelRouter.kt` |
| `agent/IntentPatternConfig.kt` | **MOVE** | `superagent/engine/IntentPatternConfig.kt` |
| `agent/IntentPatternLoader.kt` | **MOVE** | `superagent/engine/IntentPatternLoader.kt` |
| `agent/ReasoningTemplates.kt` | **MOVE** | `superagent/engine/ReasoningTemplates.kt` |
| `agent/ErrorCompactor.kt` | **MOVE** | `core/common/error/ErrorCompactor.kt` |
| `agent/AgentEvent.kt` | **DELETE** | Multi-agent event system |
| `agent/AgentEventBus.kt` | **DELETE** | Multi-agent event bus |
| `agent/AcademicFramework.kt` | **MOVE** | `superagent/education/AcademicFramework.kt` |
| `agent/a2a/A2AProtocol.kt` | **DELETE** | Inter-agent protocol |
| `agent/agi/AGIReadyLayer.kt` | **MOVE** | `superagent/engine/SafetyGuard.kt` |
| `agent/agi/ReasoningModelManager.kt` | **MOVE** | `core/model/llm/ReasoningModelManager.kt` |
| `agent/autonomy/ProgressiveAutonomy.kt` | **MOVE** | `superagent/engine/AutonomyManager.kt` |
| `agent/cost/CostBudgetManager.kt` | **MOVE** | `core/model/inference/CostBudgetManager.kt` |
| `agent/cost/InferenceCostTracker.kt` | **MOVE** | `core/model/inference/InferenceCostTracker.kt` |
| `agent/credit/CreditScoringLogic.kt` | **MOVE** | `superagent/credit/CreditScorer.kt` |
| `agent/dataanalysis/QueryIntent.kt` | **MOVE** | `superagent/financial/DataAnalysis.kt` |
| `agent/dataanalysis/ResultSummarizer.kt` | **MOVE** | `superagent/financial/DataAnalysis.kt` |
| `agent/dataanalysis/SafeQueryExecutor.kt` | **MOVE** | `superagent/financial/DataAnalysis.kt` |
| `agent/dataanalysis/SwahiliQueryParser.kt` | **MOVE** | `superagent/financial/DataAnalysis.kt` |
| `agent/harness/InferenceHarness.kt` | **MOVE** | `core/model/inference/InferenceHarness.kt` |
| `agent/harness/LearningHarness.kt` | **MOVE** | `superagent/flywheel/FlywheelEngine.kt` |
| `agent/hermes/HermesSessionManager.kt` | **MOVE** | `superagent/context/HermesSession.kt` |
| `agent/knowledge/CrossDomainKnowledgeGraph.kt` | **MOVE** | `superagent/context/KnowledgeGraph.kt` |
| `agent/loops/FeedbackLoop.kt` | **MOVE** | `superagent/flywheel/FeedbackCollector.kt` |
| `agent/loops/HumanInTheLoop.kt` | **MOVE** | `superagent/engine/AutonomyManager.kt` |
| `agent/loops/OodaLoop.kt` | **MOVE** | `superagent/engine/ReasoningEngine.kt` (integrated) |
| `agent/moe/ExpertRegistry.kt` | **DELETE** | Multi-agent routing |
| `agent/moe/MoERouter.kt` | **DELETE** | Multi-agent routing |
| `agent/multimodal/MultimodalPipeline.kt` | **MOVE** | `core/voice/pipeline/MultimodalPipeline.kt` |
| `agent/proactive/CashFlowPredictor.kt` | **MOVE** | `superagent/financial/CashFlowPredictor.kt` |
| `agent/proactive/ProactiveAlertEngine.kt` | **MOVE** | `superagent/financial/ProactiveAlerts.kt` |
| `agent/proactive/ProactiveAnomalyDetector.kt` | **MOVE** | `superagent/financial/AnomalyDetector.kt` |
| `agent/proactive/StockOutPredictor.kt` | **MOVE** | `superagent/financial/StockOutPredictor.kt` |
| `agent/recovery/AgentTaskCheckpoint.kt` | **MOVE** | `core/common/recovery/TaskCheckpoint.kt` |
| `agent/recovery/AgentTraceDao.kt` | **MOVE** | `core/database/dao/AgentTraceDao.kt` |
| `agent/recovery/AgentTraceEntity.kt` | **MOVE** | `core/database/entity/AgentTraceEntity.kt` |
| `agent/recovery/TaskCheckpointDao.kt` | **MOVE** | `core/database/dao/TaskCheckpointDao.kt` |
| `agent/recovery/TaskCheckpointManager.kt` | **MOVE** | `core/common/recovery/TaskCheckpointManager.kt` |
| `agent/version/ModelVersionManager.kt` | **MOVE** | `core/model/version/ModelVersionManager.kt` |

### 6.2 Core Package (82 files)

| Current File | Action | Destination |
|---|---|---|
| `core/ai/*` (6 files) | **MOVE** | `core/model/` (various subdirs) |
| `core/database/*` (19 files) | **MOVE** | `core/database/` (reorganized) |
| `core/di/*` (6 files) | **SPLIT** | Each module gets its own DI module |
| `core/dialect/*` (39 files) | **MOVE** | `core/common/dialect/` (shared by all) |
| `core/language/*` (7 files) | **MOVE** | `core/voice/stt/` (ASR learning) |
| `core/model/*` (19 files) | **MOVE** | `core/common/model/` |
| `core/network/*` (1 file) | **MOVE** | `data/api/` |
| `core/security/*` (2 files) | **MOVE** | `core/security/` |
| `core/util/*` (4 files) | **MOVE** | `core/common/util/` |
| `core/validation/*` (4 files) | **MOVE** | `core/common/validation/` |
| `core/BatteryOptimizer.kt` | **MOVE** | `core/common/util/` |
| `core/CodeSwitchDetector.kt` | **MOVE** | `core/common/dialect/` |
| `core/LanguageDetector.kt` | **MOVE** | `core/voice/stt/` |
| `core/LanguageDetectorV2.kt` | **MOVE** | `core/voice/stt/` |
| `core/MemoryManager.kt` | **MOVE** | `core/common/util/` |
| `core/ShengUpdater.kt` | **MOVE** | `core/common/dialect/` |

### 6.3 Other Packages

| Current Package | Files | Action | Destination |
|---|---|---|---|
| `voice/` | 15 | **MOVE** | `core/voice/` (reorganized) |
| `cfo/` | 7 | **SPLIT** | `superagent/financial/` + `superagent/communication/` |
| `finance/` | 3 | **MOVE** | `superagent/goals/` |
| `gamification/` | 5 | **MOVE** | `superagent/gamification/` |
| `mindset/` | 2 | **MOVE** | `superagent/education/` |
| `loops/` | 7 | **MOVE** | `superagent/engine/` + `superagent/flywheel/` |
| `memory/` | 1 | **MOVE** | `superagent/context/` |
| `evolution/` | 4 | **MOVE** | `superagent/flywheel/` |
| `social/` | 7 | **MOVE** | `superagent/gamification/` |
| `briefing/` | 5 | **MOVE** | `superagent/communication/` |
| `vision/` | 6 | **MOVE** | `core/model/multimodal/` |
| `scanner/` | 5 | **MOVE** | `superagent/financial/` |
| `mpesa/` | 3 | **MOVE** | `data/mpesa/` |
| `sync/` | 5 | **MOVE** | `data/sync/` |
| `data/` | 4 | **MOVE** | `data/` |
| `onboarding/` | 24 | **MOVE** | `onboarding/` |
| `skills/` | 1 | **MOVE** | `superagent/engine/` |
| `value/` | 1 | **MOVE** | `superagent/engine/` |
| `update/` | 2 | **MOVE** | `core/common/update/` |
| `security/` | 17 | **MOVE** | `core/security/` |
| `ui/` | 35 | **STAY** | `app/ui/` (unchanged) |

---

## 7. What Gets DELETED

These files are architectural overhead from the multi-agent design. They add complexity without value.

### 7.1 Files to DELETE (with line counts)

| File | Lines | Why Delete |
|---|---|---|
| `agent/Orchestrator.kt` | ~400 | Replaced by ReasoningEngine (10 params, not 40+) |
| `agent/BusinessAgent.kt` | ~50 | Thin wrapper, no unique logic |
| `agent/AnalysisAgent.kt` | ~50 | Thin wrapper, no unique logic |
| `agent/AdvisorAgent.kt` | ~50 | Thin wrapper, no unique logic |
| `agent/LearningAgent.kt` | ~50 | Thin wrapper, no unique logic |
| `agent/AgentEvent.kt` | ~80 | Multi-agent event definitions |
| `agent/AgentEventBus.kt` | ~100 | Multi-agent pub/sub bus |
| `agent/a2a/A2AProtocol.kt` | ~400 | Inter-agent communication protocol |
| `agent/moe/ExpertRegistry.kt` | ~60 | Multi-agent expert routing |
| `agent/moe/MoERouter.kt` | ~80 | Multi-agent mixture-of-experts |
| `cfo/FinancialCoachOrchestrator.kt` | ~100 | Duplicate orchestrator for CFO domain |

**Total deleted: ~1,420 lines** of pure multi-agent infrastructure.

### 7.2 Conceptual Deletions (patterns removed)

| Pattern | Where It Exists | Why Remove |
|---|---|---|
| A2A Protocol | `agent/a2a/` | In-process agents don't need network protocols |
| AgentEventBus | `agent/AgentEventBus.kt` | Direct function calls are faster and simpler |
| Agent Registration | `Orchestrator.initializeAGI()` | No agents to register |
| MoE Router | `agent/moe/` | IntentRouter already does this |
| Agent Profiles | `a2a/AgentProfile` | No agents to profile |
| Capability Negotiation | `a2a/NegotiationResult` | Modules are statically composed |
| Delegation Protocol | `a2a/DelegationResult` | Direct calls, no delegation needed |

---

## 8. The Superagent Reasoning Flow

### 8.1 Main Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    VOICE INPUT                                   │
│                    "Nimeuziwa mandazi kumi"                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 :core:voice                                      │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                   │
│  │   VAD    │───▶│   STT    │───▶│ Dialect  │                   │
│  │ (Silero) │    │ (Sherpa) │    │ Detection│                   │
│  └──────────┘    └──────────┘    └──────────┘                   │
│                                       │                          │
│  Output: "Nimeuziwa mandazi kumi" (Swahili, Sheng-influenced)   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              :superagent:engine                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              IntentClassifier                             │   │
│  │  Input: "Nimeuziwa mandazi kumi"                         │   │
│  │  → Normalize Sheng/dialect                               │   │
│  │  → Match patterns (code-first, 90% no LLM)               │   │
│  │  → Output: IntentType.SALE, confidence=0.95              │   │
│  │           extractedData={item:"mandazi", qty:10}          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              ConfidenceRouter                             │   │
│  │  confidence=0.95 → HIGH → route directly                 │   │
│  │  (LOW → clarify, MEDIUM → confirm, HIGH → execute)       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              ContextEngine.resolve()                      │   │
│  │  → Check L1 conversation memory (is this a follow-up?)   │   │
│  │  → Query L2 episodic memory (past mandazi sales?)        │   │
│  │  → Load L3 worker profile (business type: food vendor)   │   │
│  │  → Enrich intent with context                            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Route to Module                              │   │
│  │  Domain.FINANCIAL → financialModule.handle(resolved)     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              :superagent:financial                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              TransactionEngine.recordSale()               │   │
│  │  → Parse: item=mandazi, qty=10, price=auto-infer         │   │
│  │  → Calculate: revenue, cost, profit                       │   │
│  │  → Save to Room database                                  │   │
│  │  → Update inventory                                        │   │
│  │  → Trigger proactive alerts (if needed)                   │   │
│  │  → Return: AgentResponse("Umeuza mandazi 10...")          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Side Effects (async)                         │   │
│  │  → gamificationModule.onTransaction(sale)                 │   │
│  │  → flywheel.record(text, intent, response)                │   │
│  │  → contextEngine.store(text, intent, response)            │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              :superagent:engine (continued)                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              SafetyGuard.check()                          │   │
│  │  → No deception, no manipulation                          │   │
│  │  → Financial advice disclaimer if needed                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              AutonomyManager.check()                      │   │
│  │  → Transaction recording: auto-approved at Level 1+      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           │                                      │
│                           ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              CommunicationModule.personalize()            │   │
│  │  → Add warmth: "Hongera! Umeuza mandazi 10..."           │   │
│  │  → Add proverb: "Jua lina kila siku..." (if appropriate) │   │
│  │  → Adapt dialect: Sheng markers if worker uses Sheng     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 :core:voice                                      │
│  ┌──────────┐                                                   │
│  │   TTS    │  "Hongera! Umeuza mandazi kumi. Faida ni..."     │
│  │ (Kokoro) │                                                   │
│  └──────────┘                                                   │
│                    VOICE OUTPUT                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 LLM Escalation Path

When IntentClassifier confidence is LOW or `needsLLM=true`:

```
IntentClassifier (confidence < 0.5)
    ↓
ReasoningEngine.handleLlmEscalation()
    ↓
:core:model LlmEngine
    ↓
On-device Qwen 3.5 0.8B (or Gemma 4 E2B)
    ↓
Parse LLM response → extract intent → continue normal flow
```

The LLM is a **fallback**, not the primary path. 90% of inputs are handled by code alone.

---

## 9. Bootstrap & Onboarding Flow

### 9.1 The M-KOPA Principle: Smallest Possible Action

M-KOPA's genius was making the first purchase a $30 phone — not a $500 solar system. The phone was the **on-ramp** to a relationship that eventually became $2B in credit.

For Msaidizi, the **smallest possible action** is: **record one transaction.**

```
┌─────────────────────────────────────────────────────────────┐
│  M-KOPA:  Buy phone ($30) → daily payments → trust → credit │
│  Msaidizi: Say one sale → daily voice tracking → proof →    │
│            Alama Score → formal finance access               │
└─────────────────────────────────────────────────────────────┘
```

The bootstrap is NOT about collecting profile data. It's about getting the worker to **record their first transaction in under 60 seconds.** Everything else is secondary.

### 9.2 First Launch Experience (M-KOPA Style)

```
┌─────────────────────────────────────────────────────────────┐
│                    FIRST LAUNCH (0-60 seconds)               │
│                    App opens → BootstrapActivity             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Voice Introduction + FIRST TRANSACTION (30 sec)     │
│                                                              │
│  Msaidizi (TTS): "Habari! Mimi ni Msaidizi wako.            │
│   Nitakusaidia kufuatilia biashara yako.                     │
│   Leo umefanya mauzo yapi? Sema tu:                         │
│   'Nimeuziwa kitu X, bei Y'"                                │
│                                                              │
│  Worker: "Nimeuziwa nyanya tano, mia tano"                  │
│                                                              │
│  Msaidizi: "Hongera! Umeuza nyanya 5 kwa KSh 500.           │
│   Sasa ninaanza kufuatilia biashara yako!"                   │
│                                                              │
│  ★ PROOF POINT #1 RECORDED ★                                │
│  Alama Score initialized: 1 transaction, Day 1               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Quick Profile (20 sec, optional)                    │
│                                                              │
│  Msaidizi: "Sasa, unaitwa nani?"                           │
│  Worker: "Amina"                                            │
│  Msaidizi: "Karibu, Amina! Uko wapi?"                      │
│  Worker: "Gikomba"                                          │
│  Msaidizi: "Sawa! Sasa nieleze biashara yako kwa ufupi."   │
│  Worker: "Ninamauza mboga"                                  │
│                                                              │
│  (Profile captured between transactions, not before them)    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Second Transaction + Pattern (10 sec)               │
│                                                              │
│  Msaidizi: "Asante! Je, leo pia umenunua kitu?             │
│   Kwa mfano: 'Nimenunua mboga kwa 300'"                     │
│  Worker: "Nimenunua nyanya kwa mia mbili"                   │
│  Msaidizi: "Sawa! Umeweka. Bei ya nyanya ni KSh 200."       │
│                                                              │
│  ★ PROOF POINT #2 RECORDED ★                                │
│  Alama Score: 2 transactions, Day 1                          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Language Calibration (passive, during conversation)  │
│                                                              │
│  System (background):                                        │
│  → Detects language (Swahili) from first utterance           │
│  → Detects dialect (Sheng-influenced) from word choices      │
│  → Calibrates ASR for voice profile                          │
│  → No explicit step — calibration happens naturally          │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: The Hook — Tomorrow's Promise (5 sec)               │
│                                                              │
│  Msaidizi: "Amina, kesho nikumbushe mauzo yako.             │
│   Kila siku sema tu — mimi nitahesabu.                       │
│   Baada ya siku 30, nitakuambia faida yako halisi!"         │
│                                                              │
│  ★ HOOK: Worker returns tomorrow to maintain streak ★        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  STEP 6: Model Download (Background, invisible)              │
│                                                              │
│  While worker is already using Msaidizi:                     │
│  → Download STT model (Whisper, ~50MB)                      │
│  → Download TTS model (Kokoro/Piper, ~30MB)                 │
│  → Download LLM model (Qwen 0.8B, ~500MB) — optional       │
│                                                              │
│  Worker doesn't wait. Cloud mode while models download.      │
│  Models enhance the experience, not gate it.                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  BOOTSTRAP COMPLETE — Total time: < 60 seconds               │
│                                                              │
│  WorkerProfile created:                                      │
│  {                                                           │
│    name: "Amina",                                            │
│    businessType: "mboga",                                    │
│    location: "Gikomba, Nairobi",                             │
│    language: "sw",                                           │
│    dialect: "sheng-influenced",                              │
│    voiceProfile: <calibrated>,                               │
│    alamaScore: {                                             │
│      transactions: 2,                                        │
│      daysActive: 1,                                          │
│      proofPoints: 2,                                         │
│      creditReadiness: "building"                             │
│    }                                                         │
│  }                                                           │
│                                                              │
│  ★ KEY INSIGHT: Profile was captured DURING transactions,    │
│    not BEFORE them. The worker's first action was WORK,      │
│    not configuration. Like M-KOPA's first action was GET     │
│    THE PHONE, not fill out a credit application. ★           │
└─────────────────────────────────────────────────────────────┘
```

### 9.3 Why This Order Matters (M-KOPA Parallel)

| M-KOPA | Msaidizi | Principle |
|---|---|---|
| Buy phone for $30 | Record one transaction (10 sec) | Smallest possible first action |
| Daily small payments | Daily voice tracking | Habit before features |
| Payment history builds trust | Transaction history builds Alama Score | Proof over promises |
| After 6 months: unlock credit | After 90 days: unlock credit readiness | Time as proof |
| Phone is the platform | Voice is the platform | The device IS the relationship |

**The critical insight:** M-KOPA didn't start by asking "What's your income? What's your credit history?" They started by giving you a phone. Msaidizi doesn't start by asking "What's your business type? What's your monthly revenue?" It starts by recording one transaction.

### 9.4 Bootstrap Architecture

The onboarding module is **voice-first, transaction-first**. The first action is NOT profile setup — it's recording a transaction.

```kotlin
// onboarding/bootstrap/BootstrapConversation.kt
class BootstrapConversation(
    private val voicePipeline: VoicePipeline,
    private val contextEngine: ContextEngine,
    private val workerProfile: WorkerProfileSetup,
    private val alamaScore: AlamaScoreEngine
) {
    /**
     * M-KOPA-style bootstrap: transaction FIRST, profile SECOND.
     *
     * The worker's first action is recording a transaction — not filling
     * out a form. Profile data is captured DURING the transaction flow,
     * not before it.
     *
     * This mirrors M-KOPA: the first action is "get the phone", not
     * "prove your creditworthiness". The proof comes from using it.
     */
    suspend fun run() {
        // ── PHASE 1: First Transaction (< 30 seconds) ──
        // This is the M-KOPA "phone purchase" moment
        voicePipeline.speak("Habari! Mimi ni Msaidizi wako. " +
            "Nitakusaidia kufuatilia biashara yako. " +
            "Leo umefanya mauzo yapi? Sema tu: " +
            "'Nimeuziwa kitu X, bei Y'")

        val firstSale = voicePipeline.listen()
        val saleResult = transactionEngine.parseAndRecord(firstSale)

        // ★ PROOF POINT #1 — Alama Score initialized ★
        alamaScore.recordProof(ProofPoint(
            type = ProofType.TRANSACTION,
            dayNumber = 1,
            data = saleResult
        ))

        voicePipeline.speak("Hongera! ${saleResult.summary}. " +
            "Sasa ninaanza kufuatilia biashara yako!")

        // ── PHASE 2: Quick Profile (captured between transactions) ──
        // Profile is secondary — worker is already engaged
        voicePipeline.speak("Sasa, unaitwa nani?")
        val name = voicePipeline.listen()
        contextEngine.updateWorkerProfile("name", name)

        voicePipeline.speak("Karibu, $name! Uko wapi?")
        val location = voicePipeline.listen()
        contextEngine.updateWorkerProfile("location", location)

        // ── PHASE 3: Second Transaction (reinforces the habit) ──
        voicePipeline.speak("Je, leo pia umenunua kitu? " +
            "Kwa mfano: 'Nimenunua mboga kwa 300'")
        val firstPurchase = voicePipeline.listen()
        val purchaseResult = transactionEngine.parseAndRecord(firstPurchase)

        // ★ PROOF POINT #2 ★
        alamaScore.recordProof(ProofPoint(
            type = ProofType.TRANSACTION,
            dayNumber = 1,
            data = purchaseResult
        ))

        // ── PHASE 4: The Hook — tomorrow's promise ──
        voicePipeline.speak("$name, kesho nikumbushe mauzo yako. " +
            "Kila siku sema tu — mimi nitahesabu. " +
            "Baada ya siku 30, nitakuambia faida yako halisi!")

        // Language/dialect calibration happened passively during conversation
        // No explicit step needed

        // Bootstrap complete
        contextEngine.finalizeWorkerProfile()
    }
}
```

---

## 10. The Proof Flywheel (M-KOPA Model)

### 10.1 The Core Thesis: Proof, Not Features

M-KOPA didn't sell credit. They sold phones. But every phone payment was **proof** — proof that this person pays on time, proof that they're reliable, proof that they deserve more credit.

Msaidizi doesn't sell financial services. It helps workers track their business. But every voice-recorded transaction is **proof** — proof that this business exists, proof of revenue patterns, proof of reliability.

```
┌─────────────────────────────────────────────────────────────┐
│                    THE PROOF FLYWHEEL                        │
│                                                             │
│   Worker records    Transaction      Proof accumulates      │
│   daily transactions  ──────────▶    in Alama Score         │
│        ▲                                    │               │
│        │                                    ▼               │
│   Msaidizi gets    ◀──────────  Alama Score unlocks         │
│   more useful         better      new capabilities          │
│   (proactive tips,    insights    (credit readiness,         │
│    forecasts,                      market intelligence)      │
│    alerts)                                                   │
│        │                                    │               │
│        │                                    ▼               │
│        └────────────  Worker engages  ◀─────┘               │
│                       more (daily habit)                     │
│                                                             │
│   ★ More use → more proof → more value → more use ★        │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 What Counts as Proof

Not all interactions are equal. The Proof Flywheel tracks **proof points** that build the worker's financial identity:

| Proof Type | Signal | Weight | What It Proves |
|---|---|---|---|
| Transaction | "Nimeuziwa mandazi kumi" | 1.0 | Business exists, revenue is real |
| Purchase | "Nimenunua unga kwa 500" | 0.8 | Supply chain, cost structure |
| Consistency | 7 consecutive days of tracking | 2.0 | Reliability, commitment |
| Goal Progress | Worker saves toward friji | 1.5 | Financial discipline |
| Correction | Worker corrects a mistake | 0.5 | Engagement, accuracy |
| Query | Worker asks "faida ya leo?" | 0.3 | Financial awareness |
| M-Pesa Link | Worker connects M-Pesa | 3.0 | Verifiable income stream |
| Receipt Scan | Worker scans a receipt | 1.2 | Paper trail, legitimacy |

**Alama Score** = weighted sum of proof points × consistency factor × time factor

### 10.3 The Proof Flywheel Architecture

```kotlin
// superagent/flywheel/FlywheelEngine.kt
class FlywheelEngine(
    private val alamaScore: AlamaScoreEngine,
    private val adaptiveLearning: AdaptiveLearning,
    private val preferenceLearner: PreferenceLearner,
    private val patternTracker: PatternTracker,
    private val selfEvolution: SelfEvolution,
    private val feedbackCollector: FeedbackCollector,
    private val contextEngine: ContextEngine
) {
    /**
     * Record every interaction — both for learning AND proof.
     * Called after every successful response.
     *
     * This is the core of the flywheel: every interaction is simultaneously
     * (1) a learning signal and (2) a proof point.
     */
    fun record(
        input: String,
        intent: IntentResult,
        response: AgentResponse
    ) {
        // ── PROOF ACCUMULATION ──
        // Every transaction is proof. Every day of tracking is proof.
        val proofPoint = classifyProofPoint(intent, response)
        if (proofPoint != null) {
            alamaScore.recordProof(proofPoint)

            // Check if Alama Score crossed a threshold
            val newTier = alamaScore.getCurrentTier()
            if (newTier != alamaScore.getPreviousTier()) {
                // Worker unlocked a new capability!
                triggerTierUnlock(newTier)
            }
        }

        // ── LEARNING ──
        adaptiveLearning.recordInteraction(input, intent)
        preferenceLearner.update(input, response)
        patternTracker.track(intent)
        feedbackCollector.ingest(input, response)
    }

    /**
     * Classify an interaction as a proof point.
     * Not all interactions generate proof — only meaningful ones.
     */
    private fun classifyProofPoint(
        intent: IntentResult,
        response: AgentResponse
    ): ProofPoint? {
        return when (intent.intent) {
            IntentType.SALE, IntentType.PURCHASE, IntentType.EXPENSE ->
                ProofPoint(ProofType.TRANSACTION, weight = 1.0, data = intent.extractedData)
            IntentType.GOAL_CREATE, IntentType.GOAL_PROGRESS ->
                ProofPoint(ProofType.GOAL_PROGRESS, weight = 1.5, data = intent.extractedData)
            IntentType.CORRECTION ->
                ProofPoint(ProofType.CORRECTION, weight = 0.5, data = intent.extractedData)
            IntentType.PROFIT_QUERY, IntentType.CHECK_BALANCE ->
                ProofPoint(ProofType.FINANCIAL_QUERY, weight = 0.3, data = intent.extractedData)
            IntentType.RECEIPT_SCAN ->
                ProofPoint(ProofType.RECEIPT, weight = 1.2, data = intent.extractedData)
            else -> null // Not everything is proof
        }
    }

    /**
     * When Alama Score crosses a tier threshold, notify the worker.
     * This is the "unlock" moment — like M-KOPA increasing credit limit.
     */
    private fun triggerTierUnlock(newTier: AlamaTier) {
        contextEngine.addEvent(TierUnlockEvent(
            tier = newTier,
            message = newTier.unlockMessage,
            newCapabilities = newTier.capabilities
        ))
    }

    /**
     * Run the improvement cycle.
     * Called periodically (every N interactions or on background thread).
     */
    fun improve() {
        adaptiveLearning.retrain()
        preferenceLearner.consolidate()
        patternTracker.updatePatterns()
        selfEvolution.evolve()
    }

    /**
     * Get flywheel metrics — how well is the proof accumulating?
     */
    fun getMetrics(): FlywheelMetrics {
        return FlywheelMetrics(
            alamaScore = alamaScore.getCurrentScore(),
            alamaTier = alamaScore.getCurrentTier().name,
            proofPointCount = alamaScore.getTotalProofPoints(),
            daysActive = alamaScore.getDaysActive(),
            consistencyStreak = alamaScore.getConsistencyStreak(),
            intentAccuracy = adaptiveLearning.getAccuracy(),
            correctionRate = feedbackCollector.getCorrectionRate(),
            patternCount = patternTracker.getPatternCount(),
            preferenceConfidence = preferenceLearner.getConfidence(),
            evolutionScore = selfEvolution.getScore()
        )
    }
}
```

### 10.4 Offline-First Proof Building

**Critical design constraint:** Proof must build WITHOUT internet.

```
┌─────────────────────────────────────────────────────────────┐
│                    OFFLINE PROOF FLOW                        │
│                                                             │
│  Worker speaks (no internet needed)                         │
│       │                                                     │
│       ▼                                                     │
│  Voice Pipeline (on-device STT)                            │
│       │                                                     │
│       ▼                                                     │
│  IntentClassifier (on-device, code-first)                  │
│       │                                                     │
│       ▼                                                     │
│  Transaction recorded to Room DB (on-device)               │
│       │                                                     │
│       ▼                                                     │
│  Alama Score updated (on-device)                           │
│       │                                                     │
│       ▼                                                     │
│  Response generated (on-device)                            │
│       │                                                     │
│       ▼                                                     │
│  Voice output (on-device TTS)                              │
│                                                             │
│  ★ ENTIRE FLOW WORKS OFFLINE ★                             │
│  ★ PROOF NEVER STOPS BUILDING ★                            │
│                                                             │
│  ─── When internet available ───                           │
│       │                                                     │
│       ▼                                                     │
│  Sync proof to cloud (batched, compressed)                 │
│       │                                                     │
│       ▼                                                     │
│  Cloud Alama Score updated                                 │
│       │                                                     │
│       ▼                                                     │
│  Credit partners see verified history                      │
└─────────────────────────────────────────────────────────────┘
```

The sync queue (`data/sync/SyncQueue.kt`) batches proof points and syncs them when connected. The cloud score is the **authoritative** score for credit decisions, but the local score drives the worker experience even offline.

---

---

## 11. Progressive Service Stacking & Alama Score

### 11.1 The M-KOPA Service Stack

M-KOPA didn't offer $2B in credit on day one. They started with a $30 phone and progressively unlocked:

```
M-KOPA Progression:
  Phone ($30) → TV ($200) → Solar ($500) → Credit ($1,000) → Insurance → ...

Msaidizi Progression:
  Transaction Tracking → Daily Summaries → Weekly Reports → Alama Score →
  Credit Readiness → Market Intelligence → Insurance Access → ...
```

### 11.2 Alama Score Tiers

The Alama Score is the **unlock mechanism** for progressive services. It's not a credit score — it's a **proof score** that measures how much verified financial history a worker has built.

```
┌─────────────────────────────────────────────────────────────┐
│                    ALAMA SCORE TIERS                         │
│                                                             │
│  Tier 0: MTOTO (Newborn)        0-2 proof points            │
│  ├── Just started. Basic tracking only.                     │
│  ├── Capabilities: record transactions, basic summaries     │
│  └── M-KOPA equivalent: just bought the phone               │
│                                                             │
│  Tier 1: MBEGU (Seed)           3-14 proof points           │
│  ├── 1-2 weeks of consistent tracking.                      │
│  ├── Capabilities: daily briefings, profit tracking,        │
│  │   goal setting, basic advice                             │
│  └── M-KOPA equivalent: 2 weeks of phone payments           │
│                                                             │
│  Tier 2: MZAZI (Parent Tree)    15-50 proof points          │
│  ├── 1 month+ of tracking. Business patterns visible.       │
│  ├── Capabilities: weekly reports, cash flow forecasts,     │
│  │   stock alerts, savings recommendations,                 │
│  │   Alama Score visible to worker                          │
│  └── M-KOPA equivalent: 1 month, credit limit increase      │
│                                                             │
│  Tier 3: MKUU (Leader)          51-150 proof points         │
│  ├── 3 months+ of tracking. Reliable financial identity.    │
│  ├── Capabilities: CREDIT READINESS ASSESSMENT,             │
│  │   monthly reports, market price intelligence,            │
│  │   business optimization advice, peer comparison          │
│  └── M-KOPA equivalent: 3 months, unlocking bigger items    │
│                                                             │
│  Tier 4: JIJI (City)            151-500 proof points        │
│  ├── 6 months+ of tracking. Strong financial identity.      │
│  ├── Capabilities: FORMAL FINANCE ELIGIBILITY,              │
│  │   insurance access, supply chain optimization,           │
│  │   cross-business insights, tax estimation                │
│  └── M-KOPA equivalent: 6 months, full credit access        │
│                                                             │
│  Tier 5: DUNIA (World)          500+ proof points           │
│  ├── 12 months+ of tracking. Verified financial history.    │
│  ├── Capabilities: FULL FINANCIAL IDENTITY,                 │
│  │   bank-grade credit score export, insurance quotes,      │
│  │   business expansion loans, supplier credit terms        │
│  └── M-KOPA equivalent: mature customer, full ecosystem     │
└─────────────────────────────────────────────────────────────┘
```

### 11.3 Alama Score Calculation

```kotlin
// superagent/flywheel/AlamaScoreEngine.kt
class AlamaScoreEngine(
    private val proofDao: ProofPointDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Calculate Alama Score from accumulated proof points.
     *
     * Score = Σ(proof_weight × consistency_factor × time_decay)
     *
     * Where:
     * - proof_weight: per-type weight (see 10.2)
     * - consistency_factor: bonus for consecutive days (1.0 + 0.1 × streak)
     * - time_decay: recent proofs count more (e^(-days/90))
     */
    fun calculateScore(): AlamaScore {
        val proofs = proofDao.getAllProofPoints()
        val streak = calculateConsistencyStreak(proofs)
        val now = System.currentTimeMillis()

        val weightedSum = proofs.sumOf { proof ->
            val ageDays = (now - proof.timestamp) / (1000 * 60 * 60 * 24.0)
            val timeDecay = Math.exp(-ageDays / 90.0)
            val consistencyFactor = 1.0 + (0.1 * streak)
            proof.weight * consistencyFactor * timeDecay
        }

        val tier = when {
            weightedSum < 3 -> AlamaTier.MTOTO
            weightedSum < 15 -> AlamaTier.MBEGU
            weightedSum < 51 -> AlamaTier.MZAZI
            weightedSum < 151 -> AlamaTier.MKUU
            weightedSum < 501 -> AlamaTier.JIJI
            else -> AlamaTier.DUNIA
        }

        return AlamaScore(
            score = weightedSum,
            tier = tier,
            totalProofPoints = proofs.size,
            daysActive = calculateDaysActive(proofs),
            consistencyStreak = streak,
            tierProgress = calculateTierProgress(weightedSum, tier)
        )
    }

    /**
     * Get capabilities unlocked at current tier.
     * Each tier unlocks new services — this is the progressive stack.
     */
    fun getUnlockedCapabilities(): List<Capability> {
        val tier = calculateScore().tier
        return when (tier) {
            AlamaTier.MTOTO -> listOf(
                Capability.TRANSACTION_RECORDING,
                Capability.BASIC_SUMMARY
            )
            AlamaTier.MBEGU -> listOf(
                Capability.DAILY_BRIEFING,
                Capability.PROFIT_TRACKING,
                Capability.GOAL_SETTING,
                Capability.BASIC_ADVICE
            )
            AlamaTier.MZAZI -> listOf(
                Capability.WEEKLY_REPORT,
                Capability.CASH_FLOW_FORECAST,
                Capability.STOCK_ALERTS,
                Capability.SAVINGS_RECOMMENDATIONS,
                Capability.ALAMA_SCORE_VISIBLE
            )
            AlamaTier.MKUU -> listOf(
                Capability.CREDIT_READINESS,
                Capability.MONTHLY_REPORT,
                Capability.MARKET_INTELLIGENCE,
                Capability.BUSINESS_OPTIMIZATION,
                Capability.PEER_COMPARISON
            )
            AlamaTier.JIJI -> listOf(
                Capability.FORMAL_FINANCE_ELIGIBLE,
                Capability.INSURANCE_ACCESS,
                Capability.SUPPLY_CHAIN_OPTIMIZATION,
                Capability.TAX_ESTIMATION
            )
            AlamaTier.DUNIA -> listOf(
                Capability.FINANCIAL_IDENTITY_EXPORT,
                Capability.BANK_CREDIT_SCORE,
                Capability.BUSINESS_EXPANSION_LOANS,
                Capability.SUPPLIER_CREDIT_TERMS
            )
        }
    }
}
```

### 11.4 How Progressive Stacking Works in Practice

```
Day 1:  Worker records first transaction
        → Tier 0 (MTOTO): basic tracking
        → Msaidizi: "Umeuza mandazi 10. Faida ni KSh 200."

Day 7:  Worker has 14 proof points, 7-day streak
        → Tier 1 (MBEGU): daily briefings unlock
        → Msaidizi: "Amina, leo ni siku yako ya 7! Umefanya " +
           "mauzo ya KSh 14,000 wiki hii. Faida ni KSh 3,500."

Day 30: Worker has 52 proof points, 30-day streak
        → Tier 2 (MZAZI): cash flow forecasts unlock
        → Msaidizi: "Sasa una Alama Score ya 52. " +
           "Biashara yako inaongezeka! Nitakuambia " +
           "kiwango cha stock kabla ya kuisha."

Day 90: Worker has 155 proof points, 90-day streak
        → Tier 3 (MKUU): credit readiness unlocks
        → Msaidizi: "Amina, sasa una historia ya siku 90. " +
           "Alama Score yako ni 155 — unastahili kukopa " +
           "kwa riba nafuu. Nakuunganisha na mshahara?"

Day 180: Worker has 320 proof points
        → Tier 4 (JIJI): formal finance eligible
        → Msaidizi: "Historia yako ni thabiti. Sasa unaweza " +
           "kupata mkopo wa biashara. Je, unataka nieleze?"
```

### 11.5 M-KOPA Lesson: Patience is the Strategy

M-KOPA's timeline:
- **Year 1-3:** Aggressive customer acquisition, small credit amounts
- **Year 4-6:** Credit amounts grow as proof accumulates
- **Year 7-8:** First million customers (8 years!)
- **Year 8+:** Acceleration — 10M customers in 2 more years

Msaidizi's timeline should mirror this:
- **Month 1-3:** Focus on transaction recording habit (Tier 0→1→2)
- **Month 3-6:** Build Alama Score, unlock reports and forecasts (Tier 2→3)
- **Month 6-12:** Credit readiness assessment, partner introductions (Tier 3→4)
- **Year 1+:** Full financial identity, formal finance access (Tier 4→5)

**The patience principle:** Don't rush to offer credit. Let proof accumulate. The worker who tracks 365 days of transactions is a fundamentally different credit risk than one who tracked 7 days. The architecture must honor this difference.

---

## 12. Shared Context Engine

### 12.1 Context Layers

```
┌─────────────────────────────────────────────────────────┐
│                    ContextEngine                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  L1: ConversationMemory (in-session, ephemeral)  │    │
│  │  - Last 20 turns of conversation                 │    │
│  │  - Current topic and subtopic                    │    │
│  │  - Pending corrections                           │    │
│  │  - Active follow-up chain                        │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  L2: EpisodicMemory (cross-session, persisted)   │    │
│  │  - Past interactions with outcomes               │    │
│  │  - Relevance scoring (access frequency × recency)│    │
│  │  - Lessons learned from failures                 │    │
│  │  - Stored in Room database                       │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  L3: WorkerProfile (persistent, accumulated)     │    │
│  │  - Identity: name, business, location            │    │
│  │  - Patterns: what sells, when, seasonal trends   │    │
│  │  - Preferences: language, voice, report format   │    │
│  │  - Financial: avg daily revenue, profit margin   │    │
│  │  - Learning: frequent topics, known vocabulary    │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  L4: KnowledgeGraph (cross-domain, relational)   │    │
│  │  - Business relationships (supplier → product)   │    │
│  │  - Market patterns (price trends, demand)        │    │
│  │  - Cross-module insights (sales ↔ goals ↔ credit)│    │
│  │  - Stored as nodes + edges in Room               │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  L5: ProofIdentity (M-KOPA model, accumulated)   │    │
│  │  - Alama Score and tier                          │    │
│  │  - Proof points history                          │    │
│  │  - Consistency streak                            │    │
│  │  - Unlocked capabilities                         │    │
│  │  - Credit readiness status                       │    │
│  │  - Synced to cloud when online                   │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 12.2 Context Sharing

All capability modules read from and write to the same ContextEngine. The ProofIdentity layer (L5) is read by all modules to determine what capabilities are unlocked:

```kotlin
// Financial module writes transaction context AND proof
financialModule.recordSale(sale) {
    contextEngine.addTransaction(sale)
    contextEngine.updateWorkerProfile("lastSale", sale)
    // Every transaction is a proof point
    contextEngine.addProofPoint(ProofPoint(
        type = ProofType.TRANSACTION,
        weight = 1.0,
        data = sale.toMap()
    ))
}

// Credit module reads financial context AND proof identity
creditModule.assessCreditReadiness() {
    val transactions = contextEngine.getRecentTransactions(30)
    val profile = contextEngine.getWorkerProfile()
    val proofIdentity = contextEngine.getProofIdentity()

    // Only assess if tier >= MKUU (3 months of proof)
    if (proofIdentity.tier < AlamaTier.MKUU) {
        return AgentResponse(
            text = "Unahitaji historia zaidi. Sasa una siku " +
                "${proofIdentity.daysActive} za ufuatiliaji. " +
                "Baada ya siku 90, nitakujulisha Alama Score yako.",
            type = ResponseType.INFORMATION
        )
    }
    // Full credit assessment with verified history
    return assessWithProof(transactions, profile, proofIdentity)
}

// Goals module reads proof identity for goal feasibility
goalsModule.createGoal(target) {
    val proofIdentity = contextEngine.getProofIdentity()
    val avgDailyProfit = contextEngine.getAverageDailyProfit()

    // Use proof history to give realistic goal timeline
    // A worker with 90 days of proof gets a more accurate forecast
    // than one with 7 days
    return goalPlanner.createWithTimeline(target, avgDailyProfit, proofIdentity)
}
```

---

## 13. Dependency Graph

```
:app
  ├── :superagent:engine
  │     ├── :superagent:context
  │     │     ├── :core:database
  │     │     └── :core:common
  │     ├── :superagent:flywheel
  │     │     ├── :superagent:context
  │     │     └── :core:common
  │     ├── :superagent:financial
  │     │     ├── :superagent:context
  │     │     ├── :core:database
  │     │     ├── :core:common
  │     │     └── :data
  │     ├── :superagent:credit
  │     │     ├── :superagent:context
  │     │     ├── :core:database
  │     │     └── :core:common
  │     ├── :superagent:goals
  │     │     ├── :superagent:context
  │     │     ├── :core:database
  │     │     └── :core:common
  │     ├── :superagent:education
  │     │     ├── :superagent:context
  │     │     ├── :core:database
  │     │     └── :core:common
  │     ├── :superagent:gamification
  │     │     ├── :superagent:context
  │     │     ├── :core:database
  │     │     └── :core:common
  │     ├── :superagent:communication
  │     │     ├── :core:voice
  │     │     ├── :core:common
  │     │     └── :superagent:context
  │     ├── :core:model
  │     │     └── :core:common
  │     └── :core:common
  ├── :core:voice
  │     ├── :core:model
  │     └── :core:common
  ├── :core:security
  │     └── :core:common
  ├── :data
  │     ├── :core:database
  │     ├── :core:common
  │     └── :core:security
  ├── :onboarding
  │     ├── :superagent:engine
  │     ├── :core:voice
  │     ├── :core:model
  │     └── :core:common
  └── :core:database
        └── :core:common
```

**Key rule:** No circular dependencies. `core:common` is the leaf. `superagent:engine` is the root (below `:app`).

---

## 14. Build Configuration

### 13.1 `settings.gradle.kts`

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://jitpack.io") }
    }
}

rootProject.name = "msaidizi"

// Core modules
include(":core:common")
include(":core:database")
include(":core:voice")
include(":core:model")
include(":core:security")

// Superagent modules
include(":superagent:engine")
include(":superagent:context")
include(":superagent:flywheel")
include(":superagent:financial")
include(":superagent:credit")
include(":superagent:goals")
include(":superagent:education")
include(":superagent:gamification")
include(":superagent:communication")

// Feature modules
include(":data")
include(":onboarding")

// Application
include(":app")
```

### 13.2 Module Build Files

Each module is an Android library (`com.android.library`) except `:app` which remains `com.android.application`.

```kotlin
// core/common/build.gradle.kts
plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.msaidizi.core.common"
    compileSdk = 35
    defaultConfig { minSdk = 26 }
}

dependencies {
    // Pure Kotlin/AndroidX — no app-specific deps
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.3")
    implementation("com.google.dagger:hilt-android:2.52")
    ksp("com.google.dagger:hilt-compiler:2.52")
}
```

```kotlin
// superagent/engine/build.gradle.kts
plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("com.google.devtools.ksp")
    id("com.google.dagger.hilt.android")
}

android {
    namespace = "com.msaidizi.superagent.engine"
    compileSdk = 35
    defaultConfig { minSdk = 26 }
}

dependencies {
    implementation(project(":core:common"))
    implementation(project(":core:model"))
    implementation(project(":superagent:context"))
    implementation(project(":superagent:flywheel"))
    implementation(project(":superagent:financial"))
    implementation(project(":superagent:credit"))
    implementation(project(":superagent:goals"))
    implementation(project(":superagent:education"))
    implementation(project(":superagent:gamification"))
    implementation(project(":superagent:communication"))
    // ... standard deps
}
```

---

## 15. Migration Strategy

### 15.1 Phase 1: Extract Core Modules (Week 1-2)

**Goal:** Create `:core:common`, `:core:database`, `:core:voice`, `:core:model`, `:core:security`

1. Create module directories and build files
2. Move files (preserving package structure within each module)
3. Update imports in `:app`
4. Verify build compiles
5. Run existing tests

**Risk:** Low. These are already logically separate packages.

### 15.2 Phase 2: Create Superagent Shell (Week 3)

**Goal:** Create `:superagent:engine`, `:superagent:context`, `:superagent:flywheel`

1. Create ReasoningEngine as a thin wrapper that delegates to existing handlers
2. Create ContextEngine that wraps existing ConversationManager
3. Create FlywheelEngine that wraps existing AdaptiveLearningEngine
4. Wire up via Hilt DI
5. Verify `:app` still works through the new entry point

**Risk:** Medium. The new ReasoningEngine must produce identical results to the old Orchestrator.

### 15.3 Phase 3: Migrate Capability Modules (Week 4-5)

**Goal:** Create `:superagent:financial`, `:superagent:credit`, `:superagent:goals`, `:superagent:education`, `:superagent:gamification`, `:superagent:communication`

1. Move TransactionHandler → `superagent/financial/TransactionEngine.kt`
2. Move QueryHandler → `superagent/financial/QueryEngine.kt`
3. Move CFOEngine → `superagent/financial/CFOEngine.kt`
4. Move CreditScoringLogic → `superagent/credit/CreditScorer.kt`
5. Move GoalPlanner/TitheTracker → `superagent/goals/`
6. Move MindsetAcademy → `superagent/education/`
7. Move GamificationEngine → `superagent/gamification/`
8. Move VoicePersonality → `superagent/communication/`
9. Update ReasoningEngine to call modules directly

**Risk:** Medium. Each module must maintain its existing behavior.

### 15.4 Phase 4: Delete Multi-Agent Infrastructure (Week 6)

**Goal:** Remove all multi-agent code

1. Delete Orchestrator.kt
2. Delete BusinessAgent.kt, AnalysisAgent.kt, AdvisorAgent.kt, LearningAgent.kt
3. Delete AgentEvent.kt, AgentEventBus.kt
4. Delete A2AProtocol.kt
5. Delete MoERouter.kt, ExpertRegistry.kt
6. Delete FinancialCoachOrchestrator.kt
7. Remove all A2A references from ReasoningEngine
8. Verify no remaining imports of deleted files

**Risk:** Low. These files are being replaced, not modified.

### 15.5 Phase 5: Create Data & Onboarding Modules (Week 7)

**Goal:** Extract `:data` and `:onboarding`

1. Move API/sync/M-Pesa → `:data`
2. Move onboarding → `:onboarding`
3. Update dependency graph
4. Final integration testing

**Risk:** Low.

### 15.6 Phase 6: Polish & Optimize (Week 8)

**Goal:** Final cleanup

1. Verify all tests pass
2. Run detekt and fix any issues
3. Update documentation
4. Performance benchmarking (ensure no regression)
5. Remove dead code
6. Optimize module boundaries

---

## 16. Testing Strategy

### 16.1 Module-Level Tests

Each module has its own test source set:

```
superagent/financial/src/test/    # Unit tests
superagent/financial/src/androidTest/  # Instrumented tests
```

### 16.2 Integration Tests

The `:app` module contains integration tests that verify the full pipeline:

```
app/src/androidTest/
├── SuperagentIntegrationTest.kt    # Full voice → response pipeline
├── FinancialModuleTest.kt          # Financial module integration
├── ContextEngineTest.kt            # Context sharing between modules
├── FlywheelTest.kt                 # Learning cycle verification
└── OnboardingFlowTest.kt           # Bootstrap conversation test
```

### 16.3 Migration Verification Tests

During migration, run the existing test suite against the new structure:

```kotlin
// Verify ReasoningEngine produces identical output to Orchestrator
@Test
fun reasoningEngine_matches_orchestrator_output() {
    val oldOrchestrator = // ... old code
    val newEngine = // ... new code

    val testInputs = listOf(
        "Nimeuziwa mandazi kumi",
        "Faida ya leo ni ngapi?",
        "Nataka kununua friji",
        // ... 100+ test cases
    )

    for (input in testInputs) {
        val oldResponse = oldOrchestrator.processInput(input)
        val newResponse = newEngine.processInput(input)
        assertEquals(oldResponse.text, newResponse.text)
        assertEquals(oldResponse.type, newResponse.type)
    }
}
```

---

## Appendix A: Complete File Count by Module

| Module | Files | Lines (est.) |
|---|---|---|
| `:app` | 35 (UI only) | ~3,500 |
| `:core:common` | 65 | ~8,000 |
| `:core:database` | 25 | ~3,000 |
| `:core:voice` | 30 | ~6,000 |
| `:core:model` | 25 | ~5,000 |
| `:core:security` | 30 | ~4,500 |
| `:superagent:engine` | 12 | ~3,000 |
| `:superagent:context` | 10 | ~4,000 |
| `:superagent:flywheel` | 10 | ~3,000 |
| `:superagent:financial` | 20 | ~8,000 |
| `:superagent:credit` | 5 | ~2,000 |
| `:superagent:goals` | 5 | ~2,500 |
| `:superagent:education` | 5 | ~2,000 |
| `:superagent:gamification` | 10 | ~3,000 |
| `:superagent:communication` | 8 | ~2,500 |
| `:data` | 15 | ~3,000 |
| `:onboarding` | 25 | ~5,000 |
| **DELETED** | 11 | ~1,420 |
| **TOTAL** | ~346 | ~68,420 |

Note: Line counts are estimates. Actual counts will vary during migration. The total is lower than the current 127K because:
1. Multi-agent overhead is removed (~1,420 lines)
2. Duplicate code is consolidated (e.g., two orchestrators → one)
3. Thin wrapper agents are deleted
4. Some utility code is shared rather than duplicated

---

## Appendix B: Naming Conventions

| Layer | Package Prefix | Example |
|---|---|---|
| Core modules | `com.msaidizi.core.*` | `com.msaidizi.core.common.model.Transaction` |
| Superagent | `com.msaidizi.superagent.*` | `com.msaidizi.superagent.engine.ReasoningEngine` |
| Data | `com.msaidizi.data.*` | `com.msaidizi.data.api.MsaidiziApi` |
| Onboarding | `com.msaidizi.onboarding.*` | `com.msaidizi.onboarding.BootstrapConversation` |
| App (UI) | `com.msaidizi.app.*` | `com.msaidizi.app.ui.home.HomeScreen` |

---

## Appendix C: Key Design Decisions

| Decision | Rationale |
|---|---|
| **Direct module calls, not event bus** | In-process communication doesn't need pub/sub overhead |
| **Shared ContextEngine, not per-module context** | All modules need the same worker knowledge |
| **Single FlywheelEngine, not per-module learning** | Learning signals are cross-domain |
| **Capability modules are NOT independent agents** | They share process, memory, and failure domain |
| **IntentClassifier remains code-first** | 90% of inputs handled without LLM = faster, cheaper, offline |
| **Voice-first onboarding, no text forms** | Target users may be semi-literate; voice is natural |
| **Dialect adapters in core:common** | All modules need dialect awareness, not just voice |
| **SafetyGuard in engine, not per-module** | Safety is a system-wide concern |
| **Progressive autonomy in engine** | Autonomy level affects all modules equally |

---

## Deep Research Additions - Inventory and Operations

These additions extend the financial module with inventory management, supplier intelligence, pricing optimization, and operational tracking capabilities.

### 1. Perishability-Aware Inventory

Tracks shelf life per item and alerts workers when stock is approaching expiry. Critical for food vendors (tomatoes: 3 days), grain sellers (maize: 6 months), and any perishable goods.

```kotlin
// superagent/financial/model/InventoryItem.kt
data class InventoryItem(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val itemName: String,                  // "nyanya", "mahindi"
    val category: String = "",             // "produce", "grains"
    val quantity: Double = 0.0,
    val unit: String = "pieces",            // "pieces", "kg", "liters"
    val unitCost: Double = 0.0,            // Purchase cost per unit (KSh)
    val totalCost: Double = 0.0,           // quantity × unitCost
    val purchaseDate: Long = System.currentTimeMillis(), // When acquired
    val shelfLifeDays: Int = 0,            // Days until expiry (0 = non-perishable)
    val expiryDate: Long = 0L,             // Calculated: purchaseDate + shelfLifeDays
    val storageLocation: String = "",       // "warehouse", "stall", "home"
    val supplier: String = "",
    val batchId: String = "",              // Group items bought together
    val alertThreshold: Double = 0.8,      // Alert at 80% of shelf life consumed
    val isExpired: Boolean = false,
    val syncedAt: Long? = null
) {
    val daysUntilExpiry: Int
        get() {
            if (shelfLifeDays <= 0) return Int.MAX_VALUE
            val elapsed = (System.currentTimeMillis() - purchaseDate) / (1000 * 60 * 60 * 24)
            return (shelfLifeDays - elapsed).toInt().coerceAtLeast(0)
        }

    val shelfLifePercentUsed: Double
        get() {
            if (shelfLifeDays <= 0) return 0.0
            val elapsed = (System.currentTimeMillis() - purchaseDate) / (1000 * 60 * 60 * 24.0)
            return (elapsed / shelfLifeDays).coerceIn(0.0, 1.0)
        }

    val isApproachingExpiry: Boolean
        get() = shelfLifeDays > 0 && shelfLifePercentUsed >= alertThreshold
}

// superagent/financial/model/ShelfLifeDefaults.kt
object ShelfLifeDefaults {
    val SHELF_LIFE_MAP = mapOf(
        // Produce (days)
        "nyanya" to 3,       // tomatoes
        "matunda" to 5,      // fruits
        "mboga" to 3,        // vegetables
        "maziwa" to 3,       // milk
        "samaki" to 2,       // fish
        "nyama" to 3,        // meat
        "mayai" to 21,       // eggs
        // Grains & staples (days)
        "mahindi" to 180,    // maize (6 months)
        "mchele" to 365,     // rice
        "unga" to 180,       // flour
        "njugu" to 120,      // groundnuts
        // Processed
        "mandazi" to 2,      // fried dough
        "chapati" to 2,      // flatbread
        "mkate" to 5         // bread
    )

    fun getShelfLife(itemName: String): Int {
        val normalized = itemName.lowercase().trim()
        return SHELF_LIFE_MAP.entries
            .firstOrNull { normalized.contains(it.key) }?.value
            ?: 0 // non-perishable by default
    }
}
```

### 2. Spoilage/Waste Recording

Records waste events for accurate profit calculation and loss tracking. Workers lose money to spoilage — capturing this data is essential for realistic financial advice.

```kotlin
// superagent/financial/model/SpoilageRecord.kt
enum class SpoilageReason {
    EXPIRED,            // Past shelf life
    DAMAGED,            // Physical damage (dropped, crushed)
    PEST,               // Rodents, insects
    POWER_OUTAGE,       // Refrigeration failure
    THEFT,              // Missing stock
    QUALITY_DEGRADED,   // Still edible but unsellable
    OVERSTOCK,          // Bought too much
    OTHER
}

data class SpoilageRecord(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val inventoryItemId: Long = 0,         // Links to InventoryItem
    val itemName: String,                  // "nyanya", "mandazi"
    val quantitySpoiled: Double = 0.0,     // How much was lost
    val unit: String = "pieces",
    val unitCost: Double = 0.0,            // Cost per unit at purchase
    val estimatedCost: Double = 0.0,       // quantitySpoiled × unitCost
    val reason: SpoilageReason = SpoilageReason.EXPIRED,
    val reasonDetail: String = "",         // "ilikuwa imevunjika"
    val recordedAt: Long = System.currentTimeMillis(),
    val locationName: String = "",         // Where spoilage occurred
    val preventable: Boolean = true,       // Could this have been avoided?
    val syncedAt: Long? = null
)

// TransactionType extension (add to existing enum)
// enum class TransactionType {
//     SALE, PURCHASE, EXPENSE, SPOLIAGE  // ← new
// }

// superagent/financial/engine/SpoilageEngine.kt
class SpoilageEngine(
    private val inventoryDao: InventoryDao,
    private val transactionDao: TransactionDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Record spoilage from voice: "Nyanya tatu zimeharibika"
     * Creates both a SpoilageRecord and a Transaction entry for accounting.
     */
    suspend fun recordSpoilage(
        itemName: String,
        quantity: Double,
        reason: SpoilageReason,
        reasonDetail: String = ""
    ): SpoilageRecord {
        val inventory = inventoryDao.findByName(itemName)
        val unitCost = inventory?.unitCost ?: 0.0

        val record = SpoilageRecord(
            inventoryItemId = inventory?.id ?: 0,
            itemName = itemName,
            quantitySpoiled = quantity,
            unit = inventory?.unit ?: "pieces",
            unitCost = unitCost,
            estimatedCost = quantity * unitCost,
            reason = reason,
            reasonDetail = reasonDetail
        )

        // Deduct from inventory
        if (inventory != null) {
            inventoryDao.updateQuantity(
                inventory.id,
                (inventory.quantity - quantity).coerceAtLeast(0.0)
            )
        }

        // Record as transaction for financial tracking
        transactionDao.insert(
            Transaction(
                type = TransactionType.SPOLIAGE,
                item = itemName,
                quantity = quantity,
                unit = inventory?.unit ?: "pieces",
                totalAmount = 0.0,             // No revenue
                costBasis = record.estimatedCost, // Pure loss
                margin = -record.estimatedCost,   // Negative margin
                marginPercent = -1.0,
                notes = "Spoilage: ${reason.name} - $reasonDetail"
            )
        )

        // Track patterns — recurring spoilage = systemic issue
        contextEngine.addEvent(SpoilageEvent(itemName, quantity, reason))

        return record
    }
}
```

### 3. Client Management

Tracks clients (customers) to identify reliable payers, repeat buyers, and credit risks. Essential for workers who sell on credit or have recurring clients.

```kotlin
// superagent/financial/model/ClientProfile.kt
data class ClientProfile(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val name: String,                      // "Mama Wanjiku"
    val phone: String = "",                // Phone number if known
    val location: String = "",             // "Gikomba", "Eastleigh"
    val locationLat: Double? = null,
    val locationLng: Double? = null,
    val paymentPattern: String = "cash",    // "cash", "mpesa", "credit", "mixed"
    val totalJobs: Int = 0,                // Total transactions with this client
    val totalSpent: Double = 0.0,          // Lifetime spend (KSh)
    val averagePayment: Double = 0.0,      // totalSpent / totalJobs
    val reliability: Double = 1.0,         // 0.0-1.0 (payment reliability score)
    val lastTransactionAt: Long = 0L,      // Last interaction timestamp
    val firstTransactionAt: Long = 0L,     // When relationship started
    val creditLimit: Double = 0.0,         // Max credit allowed (KSh)
    val currentBalance: Double = 0.0,      // Outstanding credit (positive = owes)
    val onTimePaymentRate: Double = 1.0,   // % of credit paid on time
    val notes: String = "",                // "Huyu analipa kwa wakati"
    val tags: String = "",                 // Comma-separated: "vip,wholesale,regular"
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val syncedAt: Long? = null
) {
    val isNewClient: Boolean get() = totalJobs < 3
    val isRecurringClient: Boolean get() = totalJobs >= 10
    val isReliablePayer: Boolean get() = reliability >= 0.8 && onTimePaymentRate >= 0.9
    val hasOutstandingCredit: Boolean get() = currentBalance > 0
}

// superagent/financial/engine/ClientEngine.kt
class ClientEngine(
    private val clientDao: ClientDao,
    private val transactionDao: TransactionDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Update client profile after each transaction.
     * Called automatically by TransactionEngine.
     */
    suspend fun recordInteraction(
        clientName: String,
        amount: Double,
        paymentMethod: String,
        isOnCredit: Boolean
    ) {
        var client = clientDao.findByName(clientName)
        if (client == null) {
            client = ClientProfile(
                name = clientName,
                firstTransactionAt = System.currentTimeMillis()
            )
            client = client.copy(id = clientDao.insert(client))
        }

        val updated = client.copy(
            totalJobs = client.totalJobs + 1,
            totalSpent = client.totalSpent + amount,
            averagePayment = (client.totalSpent + amount) / (client.totalJobs + 1),
            lastTransactionAt = System.currentTimeMillis(),
            paymentPattern = inferPaymentPattern(client.paymentPattern, paymentMethod),
            currentBalance = if (isOnCredit) client.currentBalance + amount else client.currentBalance,
            updatedAt = System.currentTimeMillis()
        )
        clientDao.update(updated)
    }

    /**
     * Get clients sorted by reliability — who pays well?
     */
    suspend fun getReliableClients(): List<ClientProfile> {
        return clientDao.getAll()
            .filter { it.totalJobs >= 3 }
            .sortedByDescending { it.reliability }
    }

    private fun inferPaymentPattern(existing: String, newMethod: String): String {
        return if (existing == newMethod || existing == "mixed") "mixed" else newMethod
    }
}
```

### 4. Material Inventory

Tracks raw materials and supplies (not just products for sale). Alerts when stock is low so workers never run out mid-operation.

```kotlin
// superagent/financial/model/MaterialInventory.kt
data class MaterialInventory(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val itemName: String,                  // "mafuta ya kupikia", "unga", "sukari"
    val category: String = "",             // "ingredients", "packaging", "tools"
    val quantity: Double = 0.0,            // Current stock level
    val unit: String = "kg",               // "kg", "liters", "pieces", "rolls"
    val unitCost: Double = 0.0,            // Cost per unit (KSh)
    val reorderLevel: Double = 0.0,        // Alert when quantity <= this
    val reorderQuantity: Double = 0.0,     // Suggested reorder amount
    val supplier: String = "",             // Preferred supplier
    val supplierContact: String = "",      // Supplier phone
    val lastPurchasedAt: Long = 0L,        // Last restock date
    val lastPurchasePrice: Double = 0.0,   // What was paid last time
    val avgDailyUsage: Double = 0.0,       // Estimated daily consumption
    val daysUntilStockout: Int = 0,        // quantity / avgDailyUsage
    val location: String = "",             // Where it's stored
    val notes: String = "",
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val syncedAt: Long? = null
) {
    val isLowStock: Boolean get() = reorderLevel > 0 && quantity <= reorderLevel
    val isOutOfStock: Boolean get() = quantity <= 0
    val stockValue: Double get() = quantity * unitCost
}

// superagent/financial/engine/MaterialInventoryEngine.kt
class MaterialInventoryEngine(
    private val materialDao: MaterialDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Check all materials and generate alerts for low stock.
     * Called during daily briefings and after transactions.
     */
    suspend fun checkStockLevels(): List<StockAlert> {
        return materialDao.getAll()
            .filter { it.isLowStock }
            .map { material ->
                StockAlert(
                    itemName = material.itemName,
                    currentQuantity = material.quantity,
                    unit = material.unit,
                    reorderLevel = material.reorderLevel,
                    supplier = material.supplier,
                    urgency = when {
                        material.isOutOfStock -> StockUrgency.CRITICAL

                        material.daysUntilStockout <= 1 -> StockUrgency.HIGH
                        material.daysUntilStockout <= 3 -> StockUrgency.MEDIUM
                        else -> StockUrgency.LOW
                    }
                )
            }
            .sortedByDescending { it.urgency }
    }

    /**
     * Record material purchase and update stock.
     * Voice: "Nimenunua mafuta kilo tatu kwa 450"
     */
    suspend fun recordPurchase(
        itemName: String,
        quantity: Double,
        unitCost: Double,
        supplier: String = ""
    ) {
        var material = materialDao.findByName(itemName)
        if (material == null) {
            material = MaterialInventory(
                itemName = itemName,
                quantity = quantity,
                unitCost = unitCost,
                supplier = supplier,
                lastPurchasedAt = System.currentTimeMillis(),
                lastPurchasePrice = quantity * unitCost
            )
            materialDao.insert(material)
        } else {
            materialDao.updateQuantity(
                material.id,
                material.quantity + quantity
            )
            materialDao.updateLastPurchase(
                material.id,
                unitCost,
                System.currentTimeMillis()
            )
        }
    }
}

data class StockAlert(
    val itemName: String,
    val currentQuantity: Double,
    val unit: String,
    val reorderLevel: Double,
    val supplier: String,
    val urgency: StockUrgency
)

enum class StockUrgency { LOW, MEDIUM, HIGH, CRITICAL }
```

### 5. Tool Depreciation

Tracks tools and equipment value over time. When a worker buys a jiko, scale, or bicycle for deliveries, this tracks depreciation and maintenance schedules.

```kotlin
// superagent/financial/model/ToolTracker.kt
data class ToolTracker(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val toolName: String,                  // "kibao cha kupimia", "baiskeli", "jiko"
    val category: String = "",             // "measuring", "transport", "cooking", "storage"
    val purchaseDate: Long = System.currentTimeMillis(),
    val purchaseCost: Double = 0.0,        // What was paid (KSh)
    val expectedLifespan: Int = 365,       // Expected useful life in days
    val currentValue: Double = 0.0,        // Depreciated value (KSh)
    val depreciationMethod: String = "straight_line", // "straight_line", "declining_balance"
    val maintenanceSchedule: String = "",   // "weekly", "monthly", "as_needed"
    val lastMaintenanceDate: Long = 0L,
    val nextMaintenanceDate: Long = 0L,
    val totalMaintenanceCost: Double = 0.0,
    val condition: String = "good",         // "new", "good", "fair", "poor", "broken"
    val location: String = "",
    val supplier: String = "",
    val receiptImageUrl: String = "",
    val notes: String = "",
    val isActive: Boolean = true,          // Still in use
    val disposedAt: Long? = null,          // When sold/discarded
    val disposalAmount: Double = 0.0,      // What was recovered
    val syncedAt: Long? = null
) {
    val ageInDays: Int
        get() = ((System.currentTimeMillis() - purchaseDate) / (1000 * 60 * 60 * 24)).toInt()

    val remainingLifeDays: Int
        get() = (expectedLifespan - ageInDays).coerceAtLeast(0)

    val lifePercentUsed: Double
        get() = (ageInDays.toDouble() / expectedLifespan).coerceIn(0.0, 1.0)

    val isNearEndOfLife: Boolean
        get() = lifePercentUsed >= 0.8

    val isMaintenanceDue: Boolean
        get() = nextMaintenanceDate > 0 && System.currentTimeMillis() >= nextMaintenanceDate

    /**
     * Calculate current value using straight-line depreciation.
     * Formula: currentValue = purchaseCost × (1 - lifePercentUsed)
     */
    fun calculateCurrentValue(): Double {
        return when (depreciationMethod) {
            "straight_line" -> purchaseCost * (1.0 - lifePercentUsed)
            "declining_balance" -> purchaseCost * Math.pow(0.8, lifePercentUsed * 5)
            else -> purchaseCost * (1.0 - lifePercentUsed)
        }.coerceAtLeast(0.0)
    }

    /**
     * Calculate cost per day of ownership.
     * Useful for pricing decisions: "this tool costs KSh 5/day to own."
     */
    val costPerDay: Double
        get() {
            val totalCost = purchaseCost + totalMaintenanceCost
            val days = ageInDays.coerceAtLeast(1)
            return totalCost / days
        }
}

// superagent/financial/engine/ToolDepreciationEngine.kt
class ToolDepreciationEngine(
    private val toolDao: ToolDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Update all tool values. Run daily or on-demand.
     */
    suspend fun updateDepreciationValues() {
        toolDao.getAllActive().forEach { tool ->
            val newValue = tool.calculateCurrentValue()
            toolDao.updateCurrentValue(tool.id, newValue)
        }
    }

    /**
     * Get maintenance alerts — tools needing attention.
     */
    suspend fun getMaintenanceAlerts(): List<ToolAlert> {
        return toolDao.getAllActive()
            .filter { it.isMaintenanceDue || it.isNearEndOfLife || it.condition == "broken" }
            .map { tool ->
                ToolAlert(
                    toolName = tool.toolName,
                    alertType = when {
                        tool.condition == "broken" -> ToolAlertType.NEEDS_REPLACEMENT
                        tool.isNearEndOfLife -> ToolAlertType.NEAR_END_OF_LIFE
                        tool.isMaintenanceDue -> ToolAlertType.MAINTENANCE_DUE
                        else -> ToolAlertType.GENERAL
                    },
                    message = when {
                        tool.condition == "broken" -> "${tool.toolName} imevunjika — unahitaji mpya"
                        tool.isNearEndOfLife -> "${tool.toolName} inakaribia kumalizika. Fikiria kununua mpya."
                        tool.isMaintenanceDue -> "${tool.toolName} inahitaji matengenezo."
                        else -> "${tool.toolName} — angalia hali yake."
                    }
                )
            }
    }
}

data class ToolAlert(
    val toolName: String,
    val alertType: ToolAlertType,
    val message: String
)

enum class ToolAlertType { MAINTENANCE_DUE, NEAR_END_OF_LIFE, NEEDS_REPLACEMENT, GENERAL }
```

### 6. Supplier Comparison

Tracks prices from different suppliers per item. Alerts when a cheaper source is available, helping workers maximize margins.

```kotlin
// superagent/financial/model/SupplierComparator.kt
data class SupplierPrice(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val itemName: String,                  // "nyanya", "unga"
    val supplierName: String,              // "Mama Njeri", "Gikomba Wholesale"
    val supplierPhone: String = "",
    val supplierLocation: String = "",
    val unitPrice: Double = 0.0,           // Price per unit (KSh)
    val unit: String = "kg",
    val minimumOrder: Double = 0.0,        // Minimum quantity to buy
    val quality: String = "good",           // "excellent", "good", "fair", "poor"
    val reliability: Double = 1.0,         // 0.0-1.0 (consistent supply)
    val lastCheckedAt: Long = System.currentTimeMillis(),
    val lastPurchasedAt: Long = 0L,
    val totalPurchases: Int = 0,           // How many times bought from this supplier
    val notes: String = "",
    val syncedAt: Long? = null
)

data class PriceComparison(
    val itemName: String,
    val bestPrice: SupplierPrice,
    val alternatives: List<SupplierPrice>,
    val potentialSavings: Double,          // Best price vs current supplier
    val savingsPercent: Double
)

class SupplierComparisonEngine(
    private val supplierPriceDao: SupplierPriceDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Record a supplier price observation.
     * Voice: "Mama Njeri anauza nyanya kwa 100 kilo"
     */
    suspend fun recordPrice(
        itemName: String,
        supplierName: String,
        unitPrice: Double,
        unit: String = "kg",
        supplierPhone: String = "",
        supplierLocation: String = ""
    ) {
        val existing = supplierPriceDao.find(itemName, supplierName)
        if (existing != null) {
            supplierPriceDao.update(existing.copy(
                unitPrice = unitPrice,
                lastCheckedAt = System.currentTimeMillis()
            ))
        } else {
            supplierPriceDao.insert(SupplierPrice(
                itemName = itemName,
                supplierName = supplierName,
                unitPrice = unitPrice,
                unit = unit,
                supplierPhone = supplierPhone,
                supplierLocation = supplierLocation
            ))
        }
    }

    /**
     * Find best price for an item. Returns comparison with savings.
     * Called during purchase advice and daily briefings.
     */
    suspend fun compareForItem(
        itemName: String,
        currentSupplier: String = ""
    ): PriceComparison? {
        val prices = supplierPriceDao.findByItem(itemName)
            .filter { it.lastCheckedAt > System.currentTimeMillis() - 30L * 24 * 60 * 60 * 1000 } // Last 30 days
            .sortedBy { it.unitPrice }

        if (prices.size < 2) return null

        val best = prices.first()
        val current = prices.find { it.supplierName == currentSupplier } ?: prices.last()
        val savings = current.unitPrice - best.unitPrice
        val savingsPercent = if (current.unitPrice > 0) savings / current.unitPrice else 0.0

        return PriceComparison(
            itemName = itemName,
            bestPrice = best,
            alternatives = prices.drop(1),
            potentialSavings = savings,
            savingsPercent = savingsPercent
        )
    }

    /**
     * Alert when cheaper supplier found.
     * Called during daily briefings.
     */
    suspend fun getCheaperAlternatives(): List<PriceComparison> {
        val allItems = supplierPriceDao.getAllItems()
        return allItems.mapNotNull { compareForItem(it) }
            .filter { it.savingsPercent >= 0.1 } // At least 10% savings worth mentioning
            .sortedByDescending { it.potentialSavings }
    }
}
```

### 7. Pricing Advisor

Recommends optimal pricing based on cost basis, market rates, margin targets, and competitive positioning. Helps workers set prices that maximize profit without losing customers.

```kotlin
// superagent/financial/model/PricingAdvisor.kt
data class PricingRecommendation(
    val itemName: String,
    val currentPrice: Double,              // What worker currently charges
    val costBasis: Double,                 // Material + labor + tool depreciation per unit
    val suggestedPrice: Double,            // Recommended price
    val minimumPrice: Double,              // Floor — never sell below this
    val maximumPrice: Double,              // Ceiling — market won't bear more
    val targetMargin: Double,              // Desired margin percent (e.g., 0.3 = 30%)
    val actualMargin: Double,              // Margin at suggested price
    val marketAverage: Double,             // What others charge
    val pricingStrategy: PricingStrategy,  // Recommended approach
    val reasoning: String                  // "Bei yako ni chini ya soko. Ongeza KSh 10."
)

enum class PricingStrategy {
    COST_PLUS,          // Cost + fixed margin
    MARKET_MATCH,       // Match market average
    PREMIUM,            // Above market (quality differentiation)
    PENETRATION,        // Below market (gain customers)
    DYNAMIC             // Adjust based on time/demand
}

class PricingAdvisor(
    private val transactionDao: TransactionDao,
    private val supplierPriceDao: SupplierPriceDao,
    private val toolDao: ToolDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Recommend price for an item.
     * Considers: cost basis, market rates, margin targets, competition.
     */
    suspend fun recommendPrice(
        itemName: String,
        currentPrice: Double = 0.0,
        targetMargin: Double = 0.3 // Default 30% margin
    ): PricingRecommendation {
        // 1. Calculate cost basis
        val materialCost = calculateMaterialCost(itemName)
        val laborCost = estimateLaborCost(itemName)
        val toolCost = estimateToolDepreciation(itemName)
        val costBasis = materialCost + laborCost + toolCost

        // 2. Get market rates from transaction history
        val marketPrices = transactionDao.getSalePricesForItem(itemName, limit = 50)
        val marketAverage = if (marketPrices.isNotEmpty()) {
            marketPrices.average()
        } else {
            costBasis * (1 + targetMargin) // Fallback: cost + margin
        }

        // 3. Calculate price bounds
        val minimumPrice = costBasis * 1.05 // 5% above cost (absolute floor)
        val maximumPrice = marketAverage * 1.3 // 30% above market average

        // 4. Determine strategy
        val strategy = when {
            currentPrice < costBasis -> PricingStrategy.COST_PLUS
            currentPrice < marketAverage * 0.85 -> PricingStrategy.PENETRATION
            currentPrice > marketAverage * 1.15 -> PricingStrategy.PREMIUM
            else -> PricingStrategy.MARKET_MATCH
        }

        // 5. Calculate suggested price
        val suggestedPrice = when (strategy) {
            PricingStrategy.COST_PLUS -> costBasis * (1 + targetMargin)
            PricingStrategy.MARKET_MATCH -> marketAverage
            PricingStrategy.PREMIUM -> (marketAverage * 1.1).coerceAtMost(maximumPrice)
            PricingStrategy.PENETRATION -> (marketAverage * 0.9).coerceAtLeast(minimumPrice)
            PricingStrategy.DYNAMIC -> calculateDynamicPrice(itemName, costBasis, marketAverage)
        }

        val actualMargin = if (suggestedPrice > 0) (suggestedPrice - costBasis) / suggestedPrice else 0.0

        // 6. Generate reasoning
        val reasoning = buildReasoning(itemName, currentPrice, suggestedPrice, marketAverage, costBasis, strategy)

        return PricingRecommendation(
            itemName = itemName,
            currentPrice = currentPrice,
            costBasis = costBasis,
            suggestedPrice = suggestedPrice,
            minimumPrice = minimumPrice,
            maximumPrice = maximumPrice,
            targetMargin = targetMargin,
            actualMargin = actualMargin,
            marketAverage = marketAverage,
            pricingStrategy = strategy,
            reasoning = reasoning
        )
    }

    private suspend fun calculateMaterialCost(itemName: String): Double {
        // Look up raw material costs for this product
        val materials = supplierPriceDao.findByItem(itemName)
        return if (materials.isNotEmpty()) materials.minOf { it.unitPrice } else 0.0
    }

    private fun estimateLaborCost(itemName: String): Double {
        // Simple heuristic — can be refined with worker input
        return 0.0 // Worker's time is implicit in margin
    }

    private suspend fun estimateToolDepreciation(itemName: String): Double {
        val tools = toolDao.getAllActive()
        if (tools.isEmpty()) return 0.0
        // Amortize daily tool costs across estimated daily production
        val dailyToolCost = tools.sumOf { it.costPerDay }
        return dailyToolCost / 50.0 // Assume 50 units/day (adjustable)
    }

    private suspend fun calculateDynamicPrice(
        itemName: String,
        costBasis: Double,
        marketAverage: Double
    ): Double {
        val hour = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY)
        return when {
            hour < 10 -> marketAverage * 1.0  // Morning: standard price
            hour < 14 -> marketAverage * 1.05 // Midday: slight premium
            hour >= 17 -> marketAverage * 0.9 // Evening: discount to clear stock
            else -> marketAverage
        }
    }

    private fun buildReasoning(
        itemName: String,
        currentPrice: Double,
        suggestedPrice: Double,
        marketAverage: Double,
        costBasis: Double,
        strategy: PricingStrategy
    ): String {
        val diff = suggestedPrice - currentPrice
        return when (strategy) {
            PricingStrategy.COST_PLUS ->
                "Bei yako ya sasa (KSh ${currentPrice.toInt()}) ni chini ya gharama. " +
                "Ongeza hadi KSh ${suggestedPrice.toInt()} ili kupata faida."
            PricingStrategy.PENETRATION ->
                "Bei yako ni ya chini kuliko soko — unaongeza wateja lakini unapoteza pesa. " +
                "Fikiria kuongeza polepole hadi KSh ${suggestedPrice.toInt()}."
            PricingStrategy.PREMIUM ->
                "Bei yako ni ya juu — hakikisha ubora wako unaendana na bei. " +
                "Soko la wastani ni KSh ${marketAverage.toInt()}."
            PricingStrategy.MARKET_MATCH ->
                "Bei yako iko sawa na soko. Faida yako ni ${(suggestedPrice - costBasis).toInt()} KSh."
            PricingStrategy.DYNAMIC ->
                "Wakati huu wa siku, bei nzuri ni KSh ${suggestedPrice.toInt()}."
        }
    }
}
```

---

## Deep Research Additions - Financial Models

Seven extensions to the financial data model, each addressing a specific gap in the current architecture. These plug into `:superagent:financial` and `:superagent:flywheel`.

---

### 1. WorkPattern Field — WorkerProfile Extension

Different workers have different rhythms. A mama mboga works daily; a fundi takes project-based jobs; a farm worker is seasonal. The Alama Score and financial advice must account for this.

```kotlin
// superagent/context/WorkPattern.kt
enum class WorkPattern {
    DAILY,          // Mama mboga, kiosk owner — works every day
    WEEKLY,         // Market vendor — works specific market days
    SEASONAL,       // Farm worker, seasonal trader — active in certain months
    PROJECT_BASED,  // Fundi, contractor — income per job
    ON_DEMAND       // Boda boda, casual labor — income when available
}

// superagent/context/WorkerProfile.kt (extended)
data class WorkerProfile(
    val id: String,
    val name: String,
    val businessType: String,
    val location: String,
    val language: String,
    val dialect: String,
    val workPattern: WorkPattern = WorkPattern.DAILY,  // NEW
    // Pattern-specific config
    val activeMonths: List<Int> = emptyList(),          // For SEASONAL: [1,2,3,10,11,12]
    val marketDays: List<Int> = emptyList(),             // For WEEKLY: [1,3,6] (Mon,Wed,Sat)
    val avgJobsPerMonth: Int = 0,                        // For PROJECT_BASED
    // Existing fields...
    val alamaScore: AlamaScore = AlamaScore(),
    val createdAt: Long = System.currentTimeMillis()
)
```

**Why it matters:** A daily vendor with 30 days of proof and a seasonal worker with 30 days (but only 10 active) should NOT get the same Alama Score. WorkPattern normalizes the scoring.

---

### 2. Service Transaction Model — Transaction Extension

Service workers (boda boda, fundi, taxi) have richer transactions than product sellers. They need distance, duration, fare breakdown, and client info.

```kotlin
// superagent/financial/ServiceTransaction.kt
data class ServiceTransaction(
    val transaction: Transaction,

    // SERVICE-SPECIFIC FIELDS
    val distanceKm: Double = 0.0,          // Boda boda: 5.2 km
    val durationMinutes: Int = 0,           // Trip or job duration
    val fare: Double = 0.0,                 // Total fare charged to client
    val laborCost: Double = 0.0,            // Labor component (for fundis)
    val materialCost: Double = 0.0,         // Materials used (cement, nails, etc.)
    val clientName: String = "",            // Repeat client tracking
    val serviceType: String = "",           // "transport", "repair", "construction"
    val origin: String = "",                // For transport: pickup location
    val destination: String = "",           // For transport: dropoff location
) {
    val pureLabor: Double get() = fare - materialCost
    val profitMargin: Double get() = if (fare > 0) pureLabor / fare else 0.0
}
```

**Example usage:**
```kotlin
val trip = ServiceTransaction(
    transaction = Transaction(
        type = TransactionType.SALE,
        item = "boda boda trip",
        totalAmount = 500.0,
        category = "transport"
    ),
    distanceKm = 5.0,
    durationMinutes = 20,
    fare = 500.0,
    clientName = "Mteja wa kawaida",
    serviceType = "transport",
    origin = "Gikomba",
    destination = "Eastlands"
)
```

---

### 3. JobManager — Project-Based Job Lifecycle

Fundi and contractor workers think in **jobs**, not individual transactions. A bathroom renovation is one job with multiple expenses, materials, and labor hours.

```kotlin
// superagent/financial/JobManager.kt
class JobManager(
    private val jobDao: JobDao,
    private val transactionEngine: TransactionEngine,
    private val contextEngine: ContextEngine
) {
    suspend fun createJob(description: String, quotedAmount: Double): Job {
        val job = Job(
            id = UUID.randomUUID().toString(),
            description = description,
            quotedAmount = quotedAmount,
            status = JobStatus.QUOTED
        )
        jobDao.insert(job)
        return job
    }

    suspend fun startJob(jobId: String): Job = updateStatus(jobId, JobStatus.IN_PROGRESS)

    suspend fun addMaterial(jobId: String, item: String, cost: Double) {
        val job = jobDao.getById(jobId)
        jobDao.update(job.copy(
            materials = job.materials + Material(item, cost),
            materialCostTotal = job.materialCostTotal + cost
        ))
    }

    suspend fun addLaborHours(jobId: String, hours: Double, rate: Double = 0.0) {
        val job = jobDao.getById(jobId)
        jobDao.update(job.copy(
            laborHours = job.laborHours + hours,
            laborCostTotal = job.laborCostTotal + (hours * rate)
        ))
    }

    suspend fun completeJob(jobId: String): Job = updateStatus(jobId, JobStatus.COMPLETED)

    suspend fun markPaid(jobId: String, amount: Double): Job {
        val job = updateStatus(jobId, JobStatus.PAID)
        transactionEngine.recordSale(ResolvedIntent(
            intent = IntentType.SALE,
            extractedData = mapOf("item" to job.description, "amount" to amount, "category" to "service")
        ))
        return job.copy(amountPaid = amount)
    }

    suspend fun getJobProfit(jobId: String): JobProfit {
        val job = jobDao.getById(jobId)
        val revenue = job.amountPaid
        val totalCost = job.materialCostTotal + job.laborCostTotal
        return JobProfit(jobId, revenue, job.materialCostTotal, job.laborCostTotal,
            revenue - totalCost, if (revenue > 0) (revenue - totalCost) / revenue else 0.0)
    }
}

data class Job(
    val id: String,
    val description: String,
    val quotedAmount: Double,
    val deposit: Double = 0.0,
    val balanceDue: Double = quotedAmount - deposit,
    val status: JobStatus = JobStatus.QUOTED,
    val materials: List<Material> = emptyList(),
    val materialCostTotal: Double = 0.0,
    val laborHours: Double = 0.0,
    val laborCostTotal: Double = 0.0,
    val amountPaid: Double = 0.0,
    val clientName: String = "",
    val startDate: Long? = null,
    val completedDate: Long? = null,
    val createdAt: Long = System.currentTimeMillis()
)

data class Material(val name: String, val cost: Double)
data class JobProfit(val jobId: String, val revenue: Double, val materialCost: Double,
                    val laborCost: Double, val profit: Double, val margin: Double)
enum class JobStatus { QUOTED, IN_PROGRESS, COMPLETED, PAID }
```

---

### 4. Project Tracking — High-Level Project Model

Distinct from JobManager (which tracks granular labor/materials), Project is a higher-level view for workers managing multiple concurrent jobs or larger contracts.

```kotlin
// superagent/financial/Project.kt
data class Project(
    val id: String = UUID.randomUUID().toString(),
    val description: String,                   // "Renovate bathroom for Mama Njeri"
    val quotedAmount: Double,                  // Total contract value
    val deposit: Double = 0.0,                 // Upfront payment received
    val balanceDue: Double = quotedAmount - deposit,
    val status: ProjectStatus = ProjectStatus.PROPOSED,
    val materials: List<ProjectMaterial> = emptyList(),
    val materialBudget: Double = 0.0,          // Estimated material cost
    val materialSpent: Double = 0.0,           // Actual material spend
    val laborHours: Double = 0.0,
    val laborBudget: Double = 0.0,
    val laborSpent: Double = 0.0,
    val jobs: List<String> = emptyList(),      // Job IDs under this project
    val clientName: String = "",
    val startDate: Long? = null,
    val dueDate: Long? = null,
    val completedDate: Long? = null,
    val notes: String = "",
    val createdAt: Long = System.currentTimeMillis()
) {
    val totalSpent: Double get() = materialSpent + laborSpent
    val estimatedProfit: Double get() = quotedAmount - materialBudget - laborBudget
    val actualProfit: Double get() = amountReceived - totalSpent
    val amountReceived: Double get() = deposit + (if (status == ProjectStatus.PAID_FULL) balanceDue else 0.0)
    val isOverBudget: Boolean get() = totalSpent > (materialBudget + laborBudget)
    val progressPercent: Double
        get() = when (status) {
            ProjectStatus.PROPOSED -> 0.0
            ProjectStatus.ACCEPTED -> 10.0
            ProjectStatus.IN_PROGRESS -> 50.0
            ProjectStatus.COMPLETED -> 90.0
            ProjectStatus.PAID_FULL -> 100.0
        }
}

data class ProjectMaterial(
    val name: String,
    val estimatedCost: Double,
    val actualCost: Double = 0.0,
    val purchased: Boolean = false
)

enum class ProjectStatus {
    PROPOSED, ACCEPTED, IN_PROGRESS, COMPLETED, PAID_FULL
}
```

---

### 5. Voice Budget Creation — BudgetCreator

Workers don't think in spreadsheets. "Nataka kutumia 3000 kwa wiki hii" is how they express budgets. BudgetCreator parses natural voice into structured budgets and tracks vs actual.

```kotlin
// superagent/financial/BudgetCreator.kt
class BudgetCreator(
    private val budgetDao: BudgetDao,
    private val transactionEngine: TransactionEngine,
    private val contextEngine: ContextEngine
) {
    /**
     * Parse voice input into a budget.
     * "Nataka kutumia 3000 kwa wiki hii" -> Weekly budget of 3000
     * "Bajeti ya mboga ni 500 kwa siku" -> Daily budget of 500 for vegetables
     */
    suspend fun createFromVoice(text: String, language: String = "sw"): Budget {
        val parsed = parseBudgetIntent(text)
        val budget = Budget(
            id = UUID.randomUUID().toString(),
            name = parsed.name,
            amount = parsed.amount,
            period = parsed.period,
            category = parsed.category,
            startDate = System.currentTimeMillis(),
            endDate = parsed.period.endDateFrom(System.currentTimeMillis())
        )
        budgetDao.insert(budget)
        return budget
    }

    suspend fun getBudgetStatus(budgetId: String): BudgetStatus {
        val budget = budgetDao.getById(budgetId)
        val actual = transactionEngine.getExpenses(budget.startDate, budget.endDate, budget.category)
        val spent = actual.sumOf { it.totalAmount }
        val remaining = budget.amount - spent
        val daysLeft = daysUntil(budget.endDate)
        return BudgetStatus(
            budget = budget, spent = spent, remaining = remaining,
            percentUsed = if (budget.amount > 0) spent / budget.amount else 0.0,
            isOverBudget = remaining < 0, daysLeft = daysLeft,
            dailyAllowance = if (remaining > 0 && daysLeft > 0) remaining / daysLeft else 0.0,
            transactions = actual
        )
    }
}

data class Budget(
    val id: String,
    val name: String,                          // "Wiki hii", "Mboga ya kila siku"
    val amount: Double,                        // 3000.0
    val period: BudgetPeriod,                  // WEEKLY
    val category: String? = null,              // "mboga" or null for general
    val startDate: Long,
    val endDate: Long,
    val createdAt: Long = System.currentTimeMillis()
)

data class BudgetStatus(
    val budget: Budget, val spent: Double, val remaining: Double,
    val percentUsed: Double, val isOverBudget: Boolean,
    val daysLeft: Int, val dailyAllowance: Double,
    val transactions: List<Transaction>
)

enum class BudgetPeriod {
    DAILY, WEEKLY, MONTHLY;
    fun endDateFrom(start: Long): Long = when (this) {
        DAILY -> start + 86_400_000L
        WEEKLY -> start + 7 * 86_400_000L
        MONTHLY -> start + 30 * 86_400_000L
    }
}
```

**Example voice flow:**
```
Worker: "Nataka kutumia 3000 kwa wiki hii"
Msaidizi: "Sawa! Bajeti ya KSh 3,000 wiki hii. Utapata taarifa kila siku."

[3 days later]
Msaidizi: "Umekatumia KSh 1,200 kati ya 3,000. Bado KSh 1,800. Wiki bado ina siku 4."
```

---

### 6. Seasonal Alama Score — WorkPattern Normalization

The Alama Score must be fair across different work patterns. A seasonal worker active 3 months shouldn't be scored the same as someone inactive for 9 months.

```kotlin
// superagent/flywheel/SeasonalAlamaScorer.kt
class SeasonalAlamaScorer(
    private val proofDao: ProofPointDao,
    private val contextEngine: ContextEngine
) {
    /**
     * Normalize Alama Score based on WorkPattern.
     *
     * DAILY: Standard scoring (current model)
     * WEEKLY: Weight active days heavier (e.g., 3 market days = 1 week)
     * SEASONAL: Normalize by active season. 3 months of proof in 3 months
     *           of activity = same score as 12 months for daily worker.
     * PROJECT_BASED: Use completion rate. 10 completed jobs > 30 days idle.
     * ON_DEMAND: Weight availability windows, not calendar days.
     */
    fun normalizeScore(
        rawScore: Double,
        workPattern: WorkPattern,
        proofs: List<ProofPoint>
    ): NormalizedAlamaScore {
        return when (workPattern) {
            WorkPattern.DAILY -> NormalizedAlamaScore(
                normalizedScore = rawScore, normalizationFactor = 1.0,
                pattern = workPattern, explanation = "Standard daily scoring"
            )

            WorkPattern.WEEKLY -> {
                val profile = contextEngine.getWorkerProfile()
                val activeDaysPerWeek = profile.marketDays.size.coerceAtLeast(1)
                val scaleFactor = 7.0 / activeDaysPerWeek
                NormalizedAlamaScore(
                    normalizedScore = rawScore * scaleFactor,
                    normalizationFactor = scaleFactor, pattern = workPattern,
                    explanation = "Normalized: $activeDaysPerWeek active days/week (x${"%.1f".format(scaleFactor)} boost)"
                )
            }

            WorkPattern.SEASONAL -> {
                val profile = contextEngine.getWorkerProfile()
                val activeMonths = profile.activeMonths.size.coerceAtLeast(1)
                val activeRatio = activeMonths / 12.0
                val scaleFactor = 1.0 / activeRatio
                NormalizedAlamaScore(
                    normalizedScore = rawScore * scaleFactor,
                    normalizationFactor = scaleFactor, pattern = workPattern,
                    explanation = "Normalized: $activeMonths active months/year (x${"%.1f".format(scaleFactor)} seasonal boost)"
                )
            }

            WorkPattern.PROJECT_BASED -> {
                val completedJobs = proofs.count { it.type == ProofType.PROJECT_COMPLETE }
                val totalJobs = proofs.count {
                    it.type == ProofType.PROJECT_COMPLETE || it.type == ProofType.PROJECT_START
                }
                val completionRate = if (totalJobs > 0) completedJobs / totalJobs.toDouble() else 0.0
                val scaleFactor = completionRate.coerceIn(0.3, 1.5)
                NormalizedAlamaScore(
                    normalizedScore = rawScore * scaleFactor,
                    normalizationFactor = scaleFactor, pattern = workPattern,
                    explanation = "Normalized: $completedJobs/$totalJobs jobs completed (${(completionRate * 100).toInt()}%)"
                )
            }

            WorkPattern.ON_DEMAND -> {
                val workingDays = proofs.map {
                    Calendar.getInstance().apply { timeInMillis = it.timestamp }.get(Calendar.DAY_OF_YEAR)
                }.distinct().size
                val totalDays = ((proofs.maxOfOrNull { it.timestamp } ?: 0) -
                    (proofs.minOfOrNull { it.timestamp } ?: 0)) / 86_400_000L + 1
                val activityRate = if (totalDays > 0) workingDays / totalDays.toDouble() else 0.0
                val scaleFactor = 1.0 / activityRate.coerceAtLeast(0.2)
                NormalizedAlamaScore(
                    normalizedScore = rawScore * scaleFactor,
                    normalizationFactor = scaleFactor, pattern = workPattern,
                    explanation = "Normalized: $workingDays active days out of $totalDays (${(activityRate * 100).toInt()}%)"
                )
            }
        }
    }
}

data class NormalizedAlamaScore(
    val normalizedScore: Double,
    val normalizationFactor: Double,
    val pattern: WorkPattern,
    val explanation: String
)
```

---

### 7. Fraud & Duplicate Detection — FraudDetector

Protects data integrity. Detects duplicate entries, unusual spending patterns, and suspicious activity that could corrupt the Alama Score.

```kotlin
// superagent/financial/FraudDetector.kt
class FraudDetector(
    private val transactionDao: TransactionDao,
    private val contextEngine: ContextEngine
) {
    companion object {
        private const val DUPLICATE_WINDOW_SECONDS = 300  // 5 minutes
        private const val AMOUNT_TOLERANCE = 0.01         // KSh 0.01
    }

    /**
     * Run all fraud checks on a new transaction.
     * Returns a list of alerts (empty = clean).
     */
    suspend fun checkTransaction(tx: Transaction): List<FraudAlert> {
        val alerts = mutableListOf<FraudAlert>()
        checkDuplicate(tx)?.let { alerts.add(it) }
        checkUnusualAmount(tx)?.let { alerts.add(it) }
        checkTimeAnomaly(tx)?.let { alerts.add(it) }
        checkVelocity(tx)?.let { alerts.add(it) }
        return alerts
    }

    private suspend fun checkDuplicate(tx: Transaction): FraudAlert? {
        val recentSimilar = transactionDao.findRecent(
            item = tx.item, amount = tx.totalAmount,
            withinSeconds = DUPLICATE_WINDOW_SECONDS, excludeId = tx.id
        )
        return if (recentSimilar.isNotEmpty()) {
            FraudAlert(FraudType.DUPLICATE, AlertSeverity.MEDIUM, tx,
                "Kuna muamala kama huu uliorekodiwa — je, ni mara mbili?",
                "Futa muamala wa ziada?", recentSimilar)
        } else null
    }

    private suspend fun checkUnusualAmount(tx: Transaction): FraudAlert? {
        val avgAmount = transactionDao.getAverageAmount(tx.category, days = 30)
        if (avgAmount == 0.0) return null
        val ratio = tx.totalAmount / avgAmount
        return if (ratio > 10.0 || ratio < 0.1) {
            FraudAlert(FraudType.UNUSUAL_AMOUNT, AlertSeverity.LOW, tx,
                "Kiasi cha KSh ${tx.totalAmount} ni tofauti sana na kawaida (KSh ${"%.0f".format(avgAmount)}). Je, ni sahihi?",
                "Thibitisha kiasi")
        } else null
    }

    private suspend fun checkTimeAnomaly(tx: Transaction): FraudAlert? {
        val hour = Calendar.getInstance().apply { timeInMillis = tx.createdAt * 1000 }
            .get(Calendar.HOUR_OF_DAY)
        return if (hour < 4 || hour > 23) {
            FraudAlert(FraudType.TIME_ANOMALY, AlertSeverity.LOW, tx,
                "Muamala saa $hour usiku — ni sahihi?", "Thibitisha wakati")
        } else null
    }

    private suspend fun checkVelocity(tx: Transaction): FraudAlert? {
        val recentCount = transactionDao.countSince(System.currentTimeMillis() / 1000 - 60)
        return if (recentCount > 5) {
            FraudAlert(FraudType.HIGH_VELOCITY, AlertSeverity.MEDIUM, tx,
                "Umerekodi muamala $recentCount ndani ya dakika 1. Je, zote ni sahihi?",
                "Kagua muamala za hivi karibuni")
        } else null
    }
}

data class FraudAlert(
    val type: FraudType,
    val severity: AlertSeverity,
    val transaction: Transaction,
    val message: String,                       // In worker's language
    val suggestion: String,                    // What to do about it
    val duplicates: List<Transaction> = emptyList(),
    val timestamp: Long = System.currentTimeMillis()
)

enum class FraudType {
    DUPLICATE,           // Same amount + item within time window
    UNUSUAL_AMOUNT,      // Amount far outside normal pattern
    TIME_ANOMALY,        // Transaction at unusual hour
    HIGH_VELOCITY,       // Too many transactions too fast
    SUSPICIOUS_PATTERN   // General pattern anomaly (future use)
}

enum class AlertSeverity { LOW, MEDIUM, HIGH, CRITICAL }
```

**Example flow:**
```
Worker says: "Nimeuziwa mandazi kumi, mia mbili"
Worker says (again): "Nimeuziwa mandazi kumi, mia mbili"  <- accidental repeat

FraudDetector -> DUPLICATE alert
Msaidizi: "Umerekodi mandazi kumi kwa KSh 200 mara mbili. Je, ni mauzo mawili au mara mbili tu?"
Worker: "Mara moja tu"
Msaidizi: "Sawa! Nimemuamala wa pili."
```

---

## Deep Research Additions - Skills and Verification

### Skill Verification
data class SkillVerification(
    val skillName: String,
    val level: SkillLevel, // BEGINNER, INTERMEDIATE, EXPERT
    val completedJobs: Int,
    val averageRating: Float,
    val isVerified: Boolean,
    val verifiedDate: Long?
)
enum class SkillLevel { BEGINNER, INTERMEDIATE, EXPERT }
// Verified skills unlock premium pricing

### Portfolio Verification
data class PortfolioEntry(
    val projectId: String,
    val description: String,
    val clientTestimonial: String?,
    val rating: Float,
    val isVerified: Boolean
)
// Verified portfolio unlocks premium clients

### cuOpt Route Optimization
// NVIDIA cuOpt integration for transport/delivery workers
// App sends route request → Backend calls cuOpt → App receives optimized route
// Works offline with cached routes, online for real-time optimization

### Harvest Timing Intelligence
data class HarvestRecommendation(
    val crop: String,
    val optimalHarvestDate: Long,
    val expectedPrice: Double,
    val priceConfidence: Float,
    val reasoning: String // "Bei ya mahindi itapanda 30% kwa wiki 2"
)
// Uses weather + market prices + crop cycles

### Tax/KRA Module
data class TaxRecord(
    val category: String, // Tax-deductible category
    val amount: Double,
    val isDeductible: Boolean,
    val quarter: String
)
// Categorize expenses, estimate quarterly tax, generate KRA-ready reports

*End of Architecture Document*
