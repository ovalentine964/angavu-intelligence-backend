# Msaidizi/Angavu Super Agent Architecture
## Chief Architect's Master Blueprint

**Date:** 2026-07-24
**Status:** Architecture Design — Ready for Implementation
**Constraint:** $0 spend, Oracle Cloud Free Tier, $50 phones, voice-only, Swahili-first

---

## Executive Summary

We are collapsing **three separate codebases** (400 Kotlin files, 488 Python files, 99 pipeline files) into **one unified super agent**. The current system is already impressively architected — it has 3-tier memory, ReAct/Reflexion loops, progressive autonomy, dialect detection for 14+ languages, mutual-exclusion memory management for 2GB devices, and an agent factory with 6 swarms. The problem isn't capability — it's **fragmentation**.

**The core insight:** The Android app already IS the super agent. The backend is a mirror that adds server-side compute. The language pipeline is the learning flywheel. We need to **unify the control plane**, not rebuild from scratch.

### Current State → Target State

| Dimension | Current | Target |
|-----------|---------|--------|
| Agents | 30+ separate agents across backend | ONE agent, multiple skill modules |
| Memory | L1 (on-device) + L2 (episodic) + L3 (backend Hermes) | Unified Hermes L1/L2/L3 with sync |
| Voice | Sherpa-ONNX + Kokoro + Piper + MMS (good!) | Same, + offline dialect learning flywheel |
| Intelligence | Backend RAG + on-device LLM | On-device primary, backend augmentation |
| Learning | SelfEvolution + ConversationLearning + DialectLearning | Dual flywheel (device + cloud) |
| Protocol | A2A + MCP (over-engineered for single agent) | Simplified internal skill dispatch |

---

## Part 1: Android Architect — Restructuring msaidizi-app

### 1.1 Current Architecture (What We Keep)

The existing architecture is **excellent** and mostly stays:

- **Orchestrator.kt** — Already a thin coordinator (decomposed from 1,664-line god class). KEEP.
- **VoicePipeline.kt** — Mutual exclusion for 2GB devices. KEEP.
- **EpisodicMemory.kt** — SQLite FTS5, sub-10ms, zero dependencies. KEEP.
- **IntentRouter** → Handler pattern — 90% requests handled without LLM. KEEP.
- **ReActLoop** — Reasoning backbone. KEEP.
- **ReflexionLoop** — Integrated into SuperAgent as `reflectOnDecision()` method (optional, for high-stakes decisions ≥KSh 5,000).
- **PlanExecuteLoop** — Integrated into SuperAgent as `planSteps()` method (for multi-step intents).
- **AGIReadyLayer** — Safety boundaries. KEEP.
- **ProgressiveAutonomy** — Trust-based capability unlocking. KEEP.

### 1.2 What Changes

**Eliminate multi-agent overhead.** The app has `A2AProtocol`, `AgentProfile`, agent registration, and cross-agent communication — all for a single agent. Collapse into internal skill dispatch:

```
BEFORE:  Orchestrator → A2AProtocol → discoverAgent("business") → delegate
AFTER:   Orchestrator → SkillRegistry.get("business") → execute
```

**Specific deletions:**
- `agent/a2a/A2AProtocol.kt` — Replace with `SkillRegistry`
- `agent/a2a/AgentProfile.kt` — Merge into skill metadata
- Multiple `*Agent.kt` classes (BusinessAgent, AnalysisAgent, etc.) — Convert to `Skill` interface implementations

**New unified skill interface:**

```kotlin
interface AgentSkill {
    val name: String
    val capabilities: List<String>
    val requiredMemoryMB: Int  // For 2GB device management
    
    suspend fun canHandle(intent: IntentType): Boolean
    suspend fun execute(input: SkillInput): SkillOutput
    suspend fun onLowMemory()  // Graceful degradation
}
```

### 1.3 Memory-Safe Model Loading (Already Solved — Document for Reference)

The existing `VoicePipeline` mutual exclusion pattern is the canonical solution:

```
2GB Device Budget:
  OS + App baseline:     ~800MB
  Piper TTS (always on):  25MB
  Whisper STT (on-demand): 40MB ←→ Kokoro TTS (on-demand): 90MB
  LLM (on-demand):        ~200MB (INT4 quantized)
  
Rule: Whisper and Kokoro NEVER loaded simultaneously.
Rule: LLM loads only after Whisper unloads.
Rule: Piper is the always-available fallback TTS.
```

### 1.4 On-Device LLM Strategy

Current: `LlmEngine.kt` + `LlamaCppEngine.kt` exist. Enhance:

| Model | Size | Use Case | Device Tier |
|-------|------|----------|-------------|
| Phi-3-mini INT4 | ~2GB | Complex reasoning | STANDARD+ (3GB+) |
| Qwen2-0.5B INT4 | ~400MB | Intent classification, simple Q&A | ALL (including BASIC) |
| SmolLM-135M | ~135MB | Keyword extraction, classification | ALL |

**Model selection logic:**
```
if (DeviceTier == BASIC && task.complexity < MEDIUM) → SmolLM
if (DeviceTier == BASIC && task.complexity >= MEDIUM) → NVIDIA API (if online)
if (DeviceTier >= STANDARD) → Qwen2-0.5B
if (DeviceTier >= STANDARD && task.complexity >= HIGH) → Phi-3-mini
```

### 1.5 File Structure (Simplified)

```
com/msaidizi/app/
├── agent/
│   ├── Orchestrator.kt          ← KEEP (thin coordinator)
│   ├── IntentRouter.kt          ← KEEP
│   ├── skills/                   ← NEW: replaces multiple *Agent.kt
│   │   ├── AgentSkill.kt        ← Interface
│   │   ├── BusinessSkill.kt     ← From BusinessAgent
│   │   ├── AnalysisSkill.kt     ← From AnalysisAgent
│   │   ├── AdvisorSkill.kt      ← From AdvisorAgent
│   │   ├── DomainRouter.kt      ← KEEP (routes to domain skills)
│   │   └── SkillRegistry.kt     ← Replaces A2A protocol
│   ├── safety/                   ← KEEP
│   │   ├── AGIReadyLayer.kt
│   │   ├── OutputSanitizer.kt
│   │   └── ProgressiveAutonomy.kt
│   └── reasoning/                ← KEEP
│       ├── ReActLoop.kt
│       └── ReActLoop.kt              (Reflexion + PlanExecute absorbed into SuperAgent methods)
├── voice/                        ← KEEP (already excellent)
│   ├── VoicePipeline.kt
│   ├── SherpaVoiceEngine.kt
│   ├── DialectLearningEngine.kt  ← Enhance for flywheel
│   └── dialect/
├── memory/                       ← KEEP
│   ├── EpisodicMemory.kt        ← SQLite FTS5
│   ├── HermesSessionManager.kt  ← Enhance for L1/L2/L3 sync
│   └── ConversationMemory.kt
└── flywheel/                     ← NEW: unified learning
    ├── DeviceFlywheel.kt         ← On-device learning loop
    ├── SyncEngine.kt             ← Backend sync (when online)
    └── DialectFlywheel.kt        ← Dialect learning loop
```

---

## Part 2: Backend Architect — Restructuring angavu-intelligence-backend

### 2.1 Current Architecture (What We Keep)

The backend has a sophisticated 6-swarm agent architecture. For the super agent, we **drastically simplify** — the backend becomes a **supporting service**, not the brain.

**Keep:**
- `BiasharaAgent` base class — excellent observe→think→act→reflect lifecycle
- `TieredMemoryManager` — working/episodic/long-term memory
- `EventBus` — internal event routing
- `AgentTracer` — observability
- `InferenceHarness` — model routing with circuit breakers
- Domain agents (Agriculture, Retail, Transport, etc.) — as backend-only intelligence

**Delete/simplify:**
- `MetaAgent` → Replace with single `SuperAgentOrchestrator`
- `A2AServer/Client`, `MCPServer/Client` → Not needed (single agent)
- `SubAgentOrchestrator`, `TaskDecomposer` → Not needed
- `DeerFlow integration` → Over-engineered for current needs
- 6 separate governance/research agents → Collapse into 2 modules

### 2.2 New Backend Architecture

```
┌─────────────────────────────────────────────────────┐
│                   API Gateway (FastAPI)               │
│  /voice/upload  /sync  /intelligence  /admin         │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│            SuperAgent Backend Service                 │
│                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ Sync Engine  │  │ Intelligence│  │  Language     │ │
│  │ (device ↔    │  │ Pipeline    │  │  Pipeline     │ │
│  │  cloud)      │  │ (RAG, Soko  │  │  (dialect     │ │
│  │              │  │  Pulse,     │  │   learning,   │ │
│  │              │  │  Alama)     │  │   flywheel)   │ │
│  └─────────────┘  └─────────────┘  └──────────────┘ │
│                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ Tiered      │  │ Hermes      │  │  Governance   │ │
│  │ Memory      │  │ Service     │  │  (audit +     │ │
│  │ (L1/L2/L3)  │  │ (worker     │  │   ethics)     │ │
│  │              │  │  profiles)  │  │               │ │
│  └─────────────┘  └─────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│              Oracle Cloud Free Tier                    │
│  PostgreSQL (free) │ Redis (free) │ Object Storage    │
│  2 ARM OCPUs │ 12GB RAM │ 200GB storage               │
└─────────────────────────────────────────────────────┘
```

### 2.3 Key Backend Changes

**1. SuperAgent Backend Service (replaces AgentFactory)**
```python
class SuperAgentBackend:
    """Single backend service — not a multi-agent system."""
    
    def __init__(self):
        self.sync_engine = SyncEngine()          # Device ↔ cloud sync
        self.intelligence = IntelligencePipeline() # RAG, Soko Pulse, Alama Score
        self.language = LanguagePipeline()         # Dialect learning, vocabulary
        self.memory = TieredMemoryManager("super_agent")  # L1/L2/L3
        self.hermes = HermesService()              # Worker profiles
        self.governance = GovernanceModule()        # Audit + ethics (not separate agents)
```

**2. Sync Protocol (replaces full agent communication)**
```python
# Device → Cloud sync payload (compressed, efficient)
@dataclass
class SyncPayload:
    worker_id: str
    episodes: list[Episode]          # New L2 episodes to upload
    vocabulary: list[WordLearned]    # New dialect words learned
    metrics: DeviceMetrics           # Performance data
    last_sync_ts: float
    
# Cloud → Device sync response
@dataclass  
class SyncResponse:
    updated_skills: list[Skill]      # New/updated skills from cloud learning
    model_updates: list[ModelDelta]  # LoRA weight updates for ASR/TTS
    intelligence: list[Insight]      # Soko Pulse, Alama Score updates
    config: AgentConfig              # Updated agent configuration
```

**3. Backend File Structure (Simplified)**
```
app/
├── api/
│   ├── sync.py              ← Device sync endpoint
│   ├── intelligence.py      ← RAG/query endpoint
│   └── admin.py             ← Admin dashboard
├── core/
│   ├── super_agent.py       ← Replaces AgentFactory
│   ├── sync_engine.py       ← Device ↔ cloud sync
│   └── governance.py        ← Merged audit + ethics + privacy
├── intelligence/
│   ├── rag_engine.py        ← KEEP
│   ├── soko_pulse.py        ← KEEP (market intelligence)
│   └── alama_score.py       ← KEEP (credit scoring)
├── language/
│   ├── dialect_pipeline.py  ← Dialect learning
│   ├── vocabulary_builder.py← Vocabulary from flywheel
│   └── model_trainer.py     ← LoRA fine-tuning for ASR/TTS
├── memory/
│   ├── tiered.py            ← KEEP (3-tier memory)
│   └── hermes_service.py    ← KEEP (worker profiles)
└── services/
    ├── llm_service.py       ← NVIDIA API + local models
    └── storage.py           ← PostgreSQL + Redis + S3
```

---

## Part 3: Memory Architect — Unified Hermes L1/L2/L3

### 3.1 Current Memory Architecture (Already Excellent)

The system already has a well-designed 3-tier memory:

| Tier | Location | Implementation | Latency | Capacity |
|------|----------|---------------|---------|----------|
| L1 | On-device | `ConversationMemory.kt` (in-RAM) | <1ms | Current session |
| L2 | On-device | `EpisodicMemory.kt` (SQLite FTS5) | <10ms | ~10K episodes |
| L3 | Backend | `TieredMemoryManager` (PostgreSQL) | ~100ms | Unlimited |

**What's missing:** Synchronization between device L2 and backend L3.

### 3.2 Unified Memory Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     DEVICE (Android)                          │
│                                                               │
│  L1: Working Memory (RAM)                                     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ ConversationMemory — current session turns            │     │
│  │ IntentContext — current intent + extracted entities   │     │
│  │ EpisodicBuffer — top-3 relevant L2 episodes          │     │
│  │ Capacity: ~50 items, <1ms access                      │     │
│  └─────────────────────────────────────────────────────┘     │
│                          │ inject context                      │
│                          ▼                                     │
│  L2: Episodic Memory (SQLite FTS5)                            │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Episodes: worker interactions with outcomes           │     │
│  │ Skills: generated skills from closed learning loop    │     │
│  │ Dialect cache: learned vocabulary per dialect         │     │
│  │ BM25 ranking, relevance decay (30-day half-life)      │     │
│  │ Capacity: ~10K episodes, <10ms search                  │     │
│  └─────────────────────────────────────────────────────┘     │
│                          │ sync (when online)                  │
│                          ▼                                     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ SyncEngine: batches new episodes, uploads to cloud    │     │
│  │ Conflict resolution: vector clocks + per-data-type     │     │
│  │ Compression: zstd for bandwidth efficiency            │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
                           │
                    ───────┼──── Network ──────
                           │
┌──────────────────────────────────────────────────────────────┐
│                     CLOUD (Oracle Free Tier)                  │
│                                                               │
│  L3: Long-term Memory (PostgreSQL + Redis)                    │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ WorkerProfile (Hermes): per-worker patterns           │     │
│  │ AggregatedEpisodes: cross-worker pattern mining       │     │
│  │ GlobalSkills: validated skills from all workers       │     │
│  │ DialectCorpus: vocabulary corpus per dialect          │     │
│  │ Capacity: unlimited, ~100ms query (with Redis cache)  │     │
│  └─────────────────────────────────────────────────────┘     │
│                          │ consolidate                        │
│                          ▼                                     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ ConsolidationEngine:                                   │     │
│  │   - Extract patterns from N episodes → LongTermPattern│     │
│  │   - Generate skills from successful interaction paths  │     │
│  │   - Build dialect adapters from vocabulary corpus      │     │
│  │   - Train LoRA updates for ASR/TTS models              │     │
│  └─────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### 3.3 Sync Protocol

```kotlin
// On-device SyncEngine
class SyncEngine(
    private val episodicMemory: EpisodicMemory,
    private val hermesClient: HermesClient,
    private val connectivity: ConnectivityMonitor
) {
    // Sync strategy: opportunistic
    // - WiFi: full sync (episodes + vocabulary + metrics)
    // - Mobile data: metadata only (episode counts, new skill hashes)
    // - Offline: queue locally, sync when connected
    
    suspend fun sync() {
        if (!connectivity.isConnected()) return // Queue for later
        
        val pending = episodicMemory.getUnsyncedEpisodes()
        if (pending.isEmpty()) return
        
        val payload = SyncPayload(
            episodes = pending,
            vocabulary = dialectFlywheel.getNewWords(),
            metrics = deviceMetrics.collect()
        )
        
        val response = hermesClient.sync(payload)
        
        // Apply cloud-learned updates
        response.updated_skills.forEach { skill ->
            episodicMemory.storeSkill(skill)
        }
        response.model_updates.forEach { delta ->
            modelRegistry.applyDelta(delta) // LoRA weight update
        }
    }
}
```

### 3.4 Hermes WorkerProfile Enhancement

Current `HermesSessionManager.kt` manages per-worker profiles. Enhance:

```kotlin
data class WorkerProfile(
    val workerId: String,
    // Existing
    val frequentTopics: List<String>,
    val preferredLanguage: String,
    val preferredReportFormat: String,
    // New: Flywheel-derived insights
    val dialectProfile: DialectProfile,       // Detected dialect + adaptations
    val vocabularySize: Int,                   // Words learned from this worker
    val interactionPatterns: List<Pattern>,    // Behavioral patterns
    val skillContributions: List<String>,      // Skills this worker helped generate
    val trustScore: Float,                     // Progressive autonomy trust
    val lastSyncTs: Long                       // Last cloud sync
)
```

---

## Part 4: Voice Architect — Offline-First Voice Pipeline

### 4.1 Current Voice Pipeline (Already Excellent)

The existing `VoicePipeline.kt` is production-grade:
- Sherpa-ONNX for ASR/TTS/VAD
- Mutual exclusion for 2GB devices (Whisper ↔ Kokoro)
- Piper TTS as always-available fallback (25MB)
- MMS for 1,100+ languages
- DialectDetectionEngine for 14 dialects
- Emotion-aware voice personality
- Audio focus management
- Graceful degradation to text

**This stays. We enhance, not replace.**

### 4.2 Voice Pipeline Enhancements

**1. Offline Dialect Learning (the flywheel — see Part 5)**

```
Voice Input → ASR (Whisper Tiny) → Raw Transcript
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
            DialectDetection    UnknownWordDetector    ConfidenceScorer
            (which dialect?)    (new words?)           (how sure?)
                    │                    │                    │
                    └────────────────────┼────────────────────┘
                                         │
                                         ▼
                              ConversationLearningPipeline
                              (already exists — enhance)
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
            AdaptiveVocabulary    DialectAdapter        SkillGenerator
            (personal vocab)      (normalize to std)    (new patterns)
```

**2. ASR Model Hierarchy (for 100+ dialects)**

| Layer | Model | Size | Coverage | Update Frequency |
|-------|-------|------|----------|-----------------|
| Base | Whisper Tiny INT4 | 40MB | Swahili (standard) | Static |
| Dialect LoRA | Per-dialect adapter | +5MB each | 14 dialects → 100+ | Monthly (from flywheel) |
| Personal | User-specific corrections | <1MB | Individual worker | Real-time |

**3. TTS Model Hierarchy**

| Layer | Model | Size | Quality | Use Case |
|-------|-------|------|---------|----------|
| Primary | Kokoro | 90MB | Best | STANDARD+ devices, Swahili |
| Fallback | Piper | 25MB | Good | BASIC devices, always available |
| Multilingual | MMS | 35MB/lang | Medium | Other African languages |
| Sheng/slang | Kokoro + Sheng adapter | +2MB | Good | Nairobi users |

### 4.3 Voice Pipeline for $50 Phones

```
BASIC TIER (2GB RAM, Tecno Spark Go):
  ┌─────────────────────────────────────────────┐
  │ Always loaded:                                │
  │   Piper TTS (25MB) — voice output            │
  │   Qwen2-0.5B INT4 (400MB) — core reasoning   │
  │   App + OS (~800MB)                           │
  │   Total: ~1.2GB / 2GB available               │
  │                                               │
  │ On-demand (mutual exclusion):                  │
  │   Whisper Tiny (40MB) — STT only              │
  │   → Unloaded after transcription               │
  │   → Piper speaks the response                  │
  │                                               │
  │ Never loaded:                                  │
  │   Kokoro (90MB) — too heavy for 2GB           │
  │   Phi-3-mini (2GB) — too heavy                │
  └─────────────────────────────────────────────┘

STANDARD TIER (3GB+ RAM, Tecno Camon):
  ┌─────────────────────────────────────────────┐
  │ Always loaded:                                │
  │   Kokoro TTS (90MB) — best voice quality      │
  │   Qwen2-0.5B INT4 (400MB) — core reasoning   │
  │   App + OS (~900MB)                           │
  │   Total: ~1.4GB / 3GB available               │
  │                                               │
  │ On-demand:                                     │
  │   Whisper Tiny (40MB) — STT                   │
  │   Phi-3-mini INT4 (2GB) — complex reasoning   │
  │   → Loaded when memory allows                  │
  └─────────────────────────────────────────────┘
```

---

## Part 5: Flywheel Architect — Dual Learning Loop

### 5.1 The Dual Flywheel Concept

Two parallel learning loops that compound over time:

```
┌─────────────────────────────────────────────────────────────┐
│                    DEVICE FLYWHEEL (Offline)                  │
│                                                               │
│  Worker speaks → ASR transcribes → Agent responds            │
│       │                    │                  │               │
│       │              Unknown words?     Response quality?     │
│       │              Corrections?       User satisfied?       │
│       │                    │                  │               │
│       ▼                    ▼                  ▼               │
│  DialectLearning    VocabularyBuilder    SkillGenerator       │
│  (new dialect       (personal vocab)    (successful           │
│   patterns)                              patterns)            │
│       │                    │                  │               │
│       └────────────────────┼──────────────────┘               │
│                            │                                  │
│                            ▼                                  │
│                   LocalModelUpdate                             │
│                   (on-device adaptation)                       │
│                   - ASR correction table                       │
│                   - Intent pattern tuning                      │
│                   - Response template refinement               │
│                                                               │
│  Speed: Real-time (every interaction)                          │
│  Scope: Individual worker                                      │
│  Works: Always (offline)                                       │
└─────────────────────────────────────────────────────────────┘
                            │
                     Sync when online
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    CLOUD FLYWHEEL (Online)                     │
│                                                               │
│  Aggregated device data from thousands of workers             │
│       │                                                       │
│       ▼                                                       │
│  PatternMining                                                │
│  - Common unknown words across workers → add to ASR vocab     │
│  - Successful response patterns → new skills                  │
│  - Dialect boundary detection → new dialect adapters          │
│  - Intent misclassification patterns → router tuning          │
│       │                                                       │
│       ▼                                                       │
│  ModelTraining                                                │
│  - LoRA fine-tuning on dialect corpus → ASR improvement       │
│  - Response quality training → better agent responses         │
│  - Dialect adapter generation → new dialect support           │
│       │                                                       │
│       ▼                                                       │
│  ModelDistribution                                            │
│  - LoRA deltas pushed to devices via sync                     │
│  - New skills pushed to devices                               │
│  - Updated dialect adapters pushed                            │
│                                                               │
│  Speed: Weekly cycles (batch processing)                       │
│  Scope: All workers                                            │
│  Works: When connected                                         │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Device Flywheel Implementation

```kotlin
class DeviceFlywheel(
    private val episodicMemory: EpisodicMemory,
    private val conversationLearning: ConversationLearningPipeline,
    private val dialectLearning: DialectLearningEngine,
    private val adaptiveVocabulary: AdaptiveVocabulary
) {
    /**
     * Called after every interaction.
     * Runs in <5ms — no blocking, no heavy computation.
     */
    fun onInteractionComplete(interaction: Interaction) {
        // 1. Learn from corrections
        if (interaction.wasCorrected) {
            conversationLearning.learnCorrection(
                original = interaction.rawTranscript,
                corrected = interaction.correctedTranscript,
                dialect = interaction.detectedDialect
            )
        }
        
        // 2. Learn new vocabulary
        interaction.unknownWords.forEach { word ->
            adaptiveVocabulary.addWord(
                word = word,
                context = interaction.context,
                dialect = interaction.detectedDialect,
                confidence = interaction.confidence
            )
        }
        
        // 3. Learn dialect patterns
        if (interaction.detectedDialect != "sw") {
            dialectLearning.recordDialectUsage(
                dialect = interaction.detectedDialect,
                markers = interaction.dialectMarkers,
                audioFeatures = interaction.audioFeatures
            )
        }
        
        // 4. Generate skill if successful pattern
        if (interaction.outcome == "success" && interaction.isNovelPattern) {
            episodicMemory.storeSkill(
                title = "Learned: ${interaction.patternSummary}",
                category = interaction.domain,
                content = interaction.responseTemplate,
                confidence = 0.5  // Starts low, grows with usage
            )
        }
    }
}
```

### 5.3 Cloud Flywheel Implementation

```python
class CloudFlywheel:
    """
    Runs weekly on Oracle Cloud Free Tier.
    Processes aggregated device data to improve the system.
    """
    
    async def run_weekly_cycle(self):
        # 1. Aggregate device sync data
        episodes = await self.db.get_unprocessed_episodes(limit=10000)
        vocabulary = await self.db.get_new_vocabulary()
        metrics = await self.db.get_device_metrics()
        
        # 2. Mine patterns
        new_words = self.mine_new_words(episodes)  # Words seen by 3+ workers
        new_skills = self.mine_skills(episodes)      # Successful patterns
        dialect_patterns = self.mine_dialects(episodes, vocabulary)
        
        # 3. Train model updates
        if len(new_words) > 10:
            asr_delta = await self.train_asr_lora(new_words)
            await self.distribute_delta(asr_delta, "asr")
        
        if len(dialect_patterns) > 5:
            dialect_adapter = await self.train_dialect_adapter(dialect_patterns)
            await self.distribute_adapter(dialect_adapter)
        
        # 4. Update global skills
        for skill in new_skills:
            await self.db.upsert_global_skill(skill)
        
        # 5. Update Hermes worker profiles
        await self.hermes.consolidate_weekly()
    
    def mine_new_words(self, episodes):
        """Find words that 3+ workers encountered but weren't in vocabulary."""
        word_counts = Counter()
        for ep in episodes:
            for word in ep.unknown_words:
                word_counts[word] += 1
        return [w for w, c in word_counts.items() if c >= 3]
    
    def mine_dialects(self, episodes, vocabulary):
        """Detect emerging dialect patterns from worker data."""
        dialect_markers = defaultdict(Counter)
        for ep in episodes:
            if ep.dialect != "sw":
                for marker in ep.dialect_markers:
                    dialect_markers[ep.dialect][marker] += 1
        return {
            dialect: {m: c for m, c in markers.most_common(50)}
            for dialect, markers in dialect_markers.items()
            if len(markers) >= 5  # Need at least 5 markers
        }
```

### 5.4 Dialect Learning Flywheel (100+ Dialects)

```
Phase 1 (Month 1-3): Seed with 14 existing dialects
  - DialectDetectionEngine already supports 14 dialects
  - Each dialect has a DialectAdapter with markers + normalization rules
  - Seed vocabulary from msaidizi-language-pipeline/config/seed_vocabulary_sw.json

Phase 2 (Month 3-6): Worker-driven discovery
  - Workers in new regions produce unknown words
  - DialectLearningEngine clusters unknown words by:
    - Geographic proximity (GPS from phone)
    - Phonological patterns (audio features)
    - Lexical similarity (shared words with known dialects)
  - When cluster reaches 20+ words → candidate new dialect

Phase 3 (Month 6-12): Cloud validation + model training
  - Cloud flywheel aggregates candidate dialects
  - Linguistic validation (frequency, consistency, distinctiveness)
  - LoRA adapter trained on dialect corpus
  - Adapter pushed to devices in that region

Phase 4 (Month 12+): Autonomous dialect expansion
  - System automatically detects, validates, and deploys new dialects
  - Target: 100+ dialects by month 24
  - Each dialect requires: ~200 word corpus, ~50 audio samples
  - Workers contribute unknowingly through normal usage
```

---

## Part 6: Security Architect — PQC, Access Control, Sandboxing

### 6.1 Current Security (Already Strong)

The existing system has:
- `AGIReadyLayer` — Safety boundaries (no deception, no manipulation, financial disclaimers)
- `OutputSanitizer` — 10-layer defense-in-depth
- `ProgressiveAutonomy` — Trust-based capability unlocking
- `GovernanceModule` — Audit, Ethics, Privacy agents
- Worker ID hashing (SHA-256) in EpisodicMemory
- `InferenceHarness` with circuit breakers

### 6.2 Security Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SECURITY LAYERS                            │
│                                                               │
│  Layer 1: Input Validation                                    │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Voice input → ASR → text sanitization                │     │
│  │ Prompt injection detection (regex + pattern match)   │     │
│  │ Rate limiting (per-worker, per-device)                │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  Layer 2: Processing Sandboxing                               │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ LLM inference in sandboxed scope (no filesystem)     │     │
│  │ Skill execution with permission model                 │     │
│  │ Memory access control (skills can't read other users) │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  Layer 3: Output Safety (existing AGIReadyLayer)              │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ No deception, no manipulation, no false certainty    │     │
│  │ Financial advice disclaimers (auto-injected)         │     │
│  │ Cultural sensitivity checks                           │     │
│  │ Output sanitizer (10-layer defense)                   │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  Layer 4: Data Protection                                     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Worker IDs: SHA-256 hashed (existing)                 │     │
│  │ Episodic data: encrypted at rest (SQLCipher)          │     │
│  │ Sync payload: TLS 1.3 + zstd compression             │     │
│  │ PQC-ready: Kyber KEM for future key exchange          │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  Layer 5: Progressive Autonomy (existing)                     │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Level 0 (TOOL): Every action confirmed                │     │
│  │ Level 1 (ASSISTANT): Transactions confirmed           │     │
│  │ Level 2 (COLLEAGUE): High-value actions confirmed     │     │
│  │ Level 3+ (DELEGATE): Operates independently           │     │
│  │ Trust score: earned through successful interactions    │     │
│  └─────────────────────────────────────────────────────┘     │
│                                                               │
│  Layer 6: Governance & Audit                                  │
│  ┌─────────────────────────────────────────────────────┐     │
│  │ Every decision logged with ReAct trace                │     │
│  │ Reflexion scoring (self-critique for high-stakes)     │     │
│  │ Weekly audit reports (automated)                      │     │
│  │ Ethics review for sensitive domains                   │     │
│  └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 Post-Quantum Cryptography (PQC) Readiness

**Current:** SHA-256 for worker ID hashing, TLS for network.

**PQC Migration Path:**

```kotlin
// Phase 1: Hybrid approach (current + PQC)
// Uses both classical and PQC algorithms simultaneously
class PQCReadyCrypto {
    // Current: SHA-256 for hashing
    fun hashWorkerId(id: String): String = sha256(id)
    
    // PQC-ready: Kyber KEM for key exchange (when available)
    // Falls back to X25519 if PQC not available
    suspend fun establishSecureChannel(): SecureChannel {
        return try {
            val kyberKey = Kyber.generateKeyPair()
            // Hybrid: both classical and PQC
            SecureChannel.hybrid(classical = x25519(), pqc = kyberKey)
        } catch (e: UnsupportedOperationException) {
            SecureChannel.classical(x25519())
        }
    }
}
```

**Timeline:** PQC is NOT needed for v1. The current security model is sufficient for the threat model (individual workers, not nation-state adversaries). PQC readiness means designing crypto interfaces that can swap algorithms later.

### 6.4 Sandboxing for On-Device LLM

```kotlin
class LlmSandbox {
    /**
     * Run LLM inference with restricted capabilities.
     * - No filesystem access
     * - No network access (except through agent)
     * - No access to other workers' data
     * - Output size limited
     * - Timeout enforced
     */
    suspend fun infer(
        prompt: String,
        workerId: String,
        maxTokens: Int = 256,
        timeoutMs: Long = 5000
    ): LlmResult {
        // 1. Sanitize prompt (remove injection attempts)
        val sanitized = PromptSanitizer.sanitize(prompt)
        
        // 2. Build context only from this worker's memory
        val context = memory.getContext(workerId) // No cross-worker leakage
        
        // 3. Run inference with timeout
        return withTimeout(timeoutMs) {
            val result = llmEngine.generate(
                prompt = sanitized,
                context = context,
                maxTokens = maxTokens
            )
            
            // 4. Sanitize output
            LlmResult(
                text = OutputSanitizer.sanitize(result.text),
                tokens = result.usage,
                latencyMs = result.latencyMs
            )
        }
    }
}
```

---

## Part 7: Implementation Roadmap

### Phase 0: Website & Distribution (Week 0-1)
- [ ] Update APK download link to point to GitHub Releases latest
- [ ] Add `/health` endpoint badge (links to backend status)
- [ ] Add `/api` page with minimal API docs for partners
- [ ] Ensure PWA install prompt works on Android (manifest.json exists)
- [ ] Test on 2G connection (target: <3s first paint)
- [ ] Verify Swahili-first content, English secondary
- [ ] Add QR code for WhatsApp sharing (already exists — verify)

### Phase 1: Foundation (Week 1-2)
- [ ] Create `AgentSkill` interface and `SkillRegistry`
- [ ] Convert `BusinessAgent`, `AnalysisAgent`, `AdvisorAgent` to skills
- [ ] Remove A2A protocol, simplify agent registration
- [ ] Create `SyncEngine` on device (stub — syncs when online)
- [ ] Create `SuperAgentBackend` (simplified backend service)

### Phase 2: Memory Unification (Week 3-4)
- [ ] Implement L2↔L3 sync protocol
- [ ] Enhance `HermesSessionManager` with `WorkerProfile` additions
- [ ] Create `ConsolidationEngine` on backend
- [ ] Wire `DeviceFlywheel.onInteractionComplete()` into Orchestrator

### Phase 3: Voice Enhancement (Week 5-6)
- [ ] Implement dialect learning flywheel on device
- [ ] Create `DialectFlywheel` for cloud-side dialect mining
- [ ] Add LoRA adapter distribution via sync
- [ ] Test on Tecno Spark Go (2GB device)

### Phase 4: Backend Simplification (Week 7-8)
- [ ] Collapse 30+ agents into `SuperAgentBackend` with modules
- [ ] Remove A2A/MCP protocol code (not needed for single agent)
- [ ] Deploy to Oracle Cloud Free Tier
- [ ] Implement weekly cloud flywheel cycle

### Phase 5: Security Hardening (Week 9-10)
- [ ] Add SQLCipher for episodic memory encryption
- [ ] Implement prompt injection detection
- [ ] Add LLM sandboxing
- [ ] Create automated audit reports

### Phase 6: Dialect Expansion (Week 11-12)
- [ ] Launch dialect discovery from worker data
- [ ] Create dialect validation pipeline
- [ ] Train first new dialect adapter from flywheel data
- [ ] Target: 20+ dialects by end of Phase 6

---

## Part 8: Website & Distribution Channel (angavu-intelligence)

### 8.1 The Website's Role

The `angavu-intelligence` repo is **NOT** just a language pipeline — it is the **distribution channel**. Workers find and install Msaidizi here. It serves three audiences:

| Audience | Page | Priority |
|----------|------|----------|
| **Workers** (mama mboga, boda boda) | APK download, WhatsApp share | P0 |
| **Investors/Partners** | Vision, traction, team | P1 |
| **Developers/Press** | API docs, mission, changelog | P2 |

### 8.2 Current Website (Already Good)

- **Bilingual**: Swahili-first (`lang="sw"`), English toggle
- **PWA-ready**: `manifest.json`, service worker (`sw.js`)
- **APK download**: Direct link to GitHub Releases
- **Mobile-first**: Responsive, accessibility (skip links, focus styles, reduced motion)
- **SEO**: Open Graph, Twitter cards, structured data
- **Security**: CSP headers, strict referrer policy
- **QR code**: For WhatsApp sharing
- **WhatsApp deep link**: Pre-filled share message

### 8.3 Website Enhancements Needed

**1. Reliable APK Hosting**
```
Current:  GitHub Releases (free, but URL may change)
Target:   GitHub Releases + Oracle Object Storage mirror
          Primary:  https://angavuintelligence.com/download/msaidizi.apk
                    → 302 redirect to latest GitHub Release
          Mirror:   Oracle Object Storage (200GB free)
                    → Fallback if GitHub is slow
          Version:  /download/msaidizi-v{VERSION}.apk (pinned)
```

**2. Health Status Page**
```html
<!-- Add to website: /status page -->
<!-- Shows backend health, API latency, active workers -->
<a href="/status" class="status-badge">
  <span class="status-dot green"></span> MFUMO UNAOFANYA KAZI
</a>
```
Backend endpoint: `GET /health` returns:
```json
{
  "status": "healthy",
  "uptime_hours": 720,
  "active_workers": 1247,
  "api_latency_ms": 45,
  "last_flywheel_cycle": "2026-07-20T02:00:00Z"
}
```

**3. Partner/Investor Page** (`/vision`)
```
- Mission: Economic intelligence for Africa's informal economy
- Traction: Workers, transactions processed, dialects supported
- Team: Founders, advisors
- Contact: Formspree (already integrated)
- Download CTA on every page
```

**4. API Documentation** (`/api` — lightweight)
```
For partners who want to integrate:
- POST /api/v1/sync — Device sync endpoint
- GET  /api/v1/intelligence/{query} — Market intelligence
- GET  /api/v1/health — System health
- Authentication: API key (partners), JWT (devices)
```

### 8.4 Website Architecture

```
┌─────────────────────────────────────────────────────┐
│              angavuintelligence.com                   │
│              (GitHub Pages → .com migration)          │
│                                                       │
│  Pages:                                               │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ / (home)     │  │ /download   │  │ /vision       │ │
│  │ Hero + CTA   │  │ APK direct  │  │ Investors     │ │
│  │ Swahili-first│  │ QR code     │  │ Traction      │ │
│  │ WhatsApp     │  │ WhatsApp    │  │ Team          │ │
│  └─────────────┘  └─────────────┘  └──────────────┘ │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │
│  │ /api        │  │ /status     │  │ /privacy      │ │
│  │ API docs    │  │ Health      │  │ Privacy policy│ │
│  │ For partners│  │ Uptime      │  │ (exists)      │ │
│  └─────────────┘  └─────────────┘  └──────────────┘ │
│                                                       │
│  Tech: Static HTML/CSS/JS (no framework)              │
│  Hosting: GitHub Pages (free) + custom domain         │
│  PWA: manifest.json + sw.js (offline support)         │
│  Analytics: None (privacy-first) or self-hosted       │
│  Forms: Formspree (free tier)                         │
└─────────────────────────────────────────────────────┘
         │
         │ APK download link
         ▼
┌─────────────────────────────────────────────────────┐
│  GitHub Releases                                      │
│  msaidizi-app/releases/download/latest/               │
│  msaidizi-release.apk                                 │
│                                                       │
│  + Oracle Object Storage mirror (200GB free)          │
│  Fallback for slow GitHub connections                 │
└─────────────────────────────────────────────────────┘
```

### 8.5 Website Performance Targets

| Metric | Target | Why |
|--------|--------|-----|
| First Contentful Paint | <1.5s | 2G connections in rural Kenya |
| Largest Contentful Paint | <3s | Keep workers engaged |
| Total page weight | <200KB | Data is expensive |
| APK size | <50MB | Download on mobile data |
| Time to APK download start | <5s | Impatience threshold |
| Lighthouse score | >90 | SEO + accessibility |

### 8.6 Domain Migration Plan

```
Current:  GitHub Pages (ovalentine964.github.io/angavu-intelligence)
Target:   angavuintelligence.com (already configured in meta tags)

Steps:
1. Configure DNS A records → GitHub Pages IPs
2. Enable HTTPS (GitHub Pages auto-provisions Let's Encrypt)
3. Update all internal links
4. Set up 301 redirect from old URL
5. Update Google Search Console
6. Verify PWA install works on custom domain
```

---

## Part 9: Infrastructure Deployment

### Oracle Cloud Free Tier Layout

```
┌─────────────────────────────────────────────────┐
│  Oracle Cloud Always Free (2 ARM OCPUs, 12GB)    │
│                                                   │
│  ┌───────────────┐  ┌───────────────┐            │
│  │ PostgreSQL     │  │ Redis          │            │
│  │ (Always Free)  │  │ (Always Free)  │            │
│  │ Worker data    │  │ Session cache  │            │
│  │ Episodes (L3)  │  │ Rate limiting  │            │
│  │ Skills         │  │ Hot patterns   │            │
│  └───────────────┘  └───────────────┘            │
│                                                   │
│  ┌───────────────┐  ┌───────────────┐            │
│  │ FastAPI        │  │ Celery         │            │
│  │ (Gunicorn)     │  │ (Background)   │            │
│  │ API endpoints  │  │ Weekly flywheel│            │
│  │ Sync handler   │  │ Model training │            │
│  │ Intelligence   │  │ Consolidation  │            │
│  └───────────────┘  └───────────────┘            │
│                                                   │
│  ┌───────────────┐                               │
│  │ Object Storage │  ← Model files, LoRA deltas   │
│  │ (200GB free)   │  ← Audio corpus               │
│  │                │  ← Backups                     │
│  └───────────────┘                               │
└─────────────────────────────────────────────────┘
```

### NVIDIA API Integration (Free Frontier Model)

```python
class LLMService:
    """Routes to NVIDIA API (free) or local model."""
    
    async def infer(self, prompt: str, complexity: str = "low") -> str:
        if complexity == "high" and self.nvidia_available:
            # NVIDIA API: free frontier model for complex reasoning
            return await self.nvidia_client.complete(
                model="meta/llama-3.1-8b-instruct",  # Free tier
                prompt=prompt,
                max_tokens=512
            )
        else:
            # Local model: on-device or backend
            return await self.local_model.complete(prompt)
```

---

## Summary: The Super Agent in One Page

```
┌─────────────────────────────────────────────────────────────┐
│                    ONE SUPER AGENT                            │
│                                                               │
│  ┌─────────────┐                                             │
│  │   VOICE     │  Sherpa-ONNX + Kokoro/Piper + MMS           │
│  │  (input/    │  Mutual exclusion for 2GB devices            │
│  │   output)   │  14 dialects → 100+ via flywheel             │
│  └──────┬──────┘                                             │
│         │                                                     │
│  ┌──────▼──────┐                                             │
│  │  REASONING  │  IntentRouter → Skill dispatch               │
│  │  (think)    │  ReAct loop + optional Reflexion + planning   │
│  │             │  90% code-only, 10% LLM escalation           │
│  └──────┬──────┘                                             │
│         │                                                     │
│  ┌──────▼──────┐                                             │
│  │   SKILLS    │  Business, Analysis, Advisor, Domain         │
│  │  (act)      │  SkillRegistry replaces A2A protocol         │
│  │             │  Progressive autonomy (trust-based)           │
│  └──────┬──────┘                                             │
│         │                                                     │
│  ┌──────▼──────┐                                             │
│  │   MEMORY    │  L1 (RAM) → L2 (SQLite FTS5) → L3 (Cloud)  │
│  │  (learn)    │  Hermes worker profiles                      │
│  │             │  Episodic memory with relevance decay         │
│  └──────┬──────┘                                             │
│         │                                                     │
│  ┌──────▼──────┐                                             │
│  │  FLYWHEEL   │  Device: real-time learning (offline)        │
│  │  (evolve)   │  Cloud: weekly aggregation + model training  │
│  │             │  Dialect expansion: worker-driven             │
│  └──────┬──────┘                                             │
│         │                                                     │
│  ┌──────▼──────┐                                             │
│  │  SECURITY   │  AGIReadyLayer + OutputSanitizer             │
│  │  (protect)  │  Progressive autonomy + trust scoring        │
│  │             │  Encrypted at rest, TLS in transit            │
│  └─────────────┘                                             │
│                                                               │
│  Constraints: $0 spend | Oracle Free Tier | $50 phones       │
│  Voice-only | Swahili-first | Offline-first                   │
└─────────────────────────────────────────────────────────────┘
```

---

*This architecture preserves 80% of existing code while unifying the control plane. The existing code is production-grade — we're not rebuilding, we're consolidating.*
