# MSAIDIZI/ANGAVU UNIFIED SUPER AGENT BLUEPRINT
## The Definitive Integration of Research + Architecture

**Date:** 2026-07-24
**Author:** Lead Synthesis Architect
**Mandate:** Integrate ALL research findings with ALL architecture blueprints into ONE unified blueprint
**Scope:** 10 research outputs × 9 architect outputs = 10 integration points

---

## EXECUTIVE SUMMARY

**The Problem:** Research teams designed from Jensen Huang's vision (Deep Agents 2.0, OpenClaw, Hermes, flywheel, quantum-ready, AGI-ready). Architect teams designed from the codebase (400 Kotlin files, 488 Python files, 33+ agents). They never connected.

**The Synthesis:** This document maps every research finding to every architectural component, specifying exactly WHERE each insight goes, WHAT code changes are needed, and WHAT to build first.

**The Core Insight:** Msaidizi is not building a chatbot, not building a multi-agent system, not building a cloud platform. It is building **one intelligence that lives in a $50 phone, speaks 14+ African dialects, learns from every interaction, and gets smarter for 600M+ informal workers** — using $0 of infrastructure spend.

---

## THE 10 INTEGRATION POINTS

---

### INTEGRATION POINT 1: Deep Agents 2.0 → Android App + Backend

#### What the Research Said

Deep Agents 2.0 (LangChain, 2026) provides: harness (tools + memory + guardrails), long-running agent loops, standardized tool interfaces, and the principle that "the harness makes the model deliver frontier capabilities." Jensen Huang: *"In the future, most companies will be built on harnesses."*

The research identified 6 components of the harness: prompt engineering, tool augmentation, memory retrieval, guardrails, execution sandbox, and post-training.

#### What the Architect Designed

The Android architect designed a `SuperAgent.kt` class with 10 dependencies (down from 40+), a `Tool` interface, a `ToolRegistry`, and a 7-phase cognitive loop (INPUT → PERCEIVE → REMEMBER → REASON → ACT → LEARN → OUTPUT). The backend architect designed a `SuperAgentBackend` service that replaces 33+ agents with direct service calls.

#### How They Connect

Deep Agents 2.0 IS the harness. The architect's cognitive loop IS the Deep Agents loop. They are the same thing described from different angles:

| Deep Agents 2.0 Component | Msaidizi Implementation | File Location |
|---|---|---|
| **Harness** (tools + memory + guardrails) | `SuperAgent.kt` + `ToolRegistry` + `UnifiedMemoryBridge` + `SafetyChecker` | Android: `agent/SuperAgent.kt` |
| **Tool Interface** | `Tool.kt` interface with `name`, `description`, `intents`, `execute()` | Android: `agent/Tool.kt` |
| **Guardrails** | `SafetyChecker` (inline) + `OutputSanitizer` (10-layer) + `AGIReadyLayer` | Android: `agent/safety/` |
| **Memory Retrieval** | `UnifiedMemoryBridge.enrichContext()` queries L1+L2+L3 before every response | Android: `agent/memory/UnifiedMemoryBridge.kt` |
| **Execution Sandbox** | `LlmSandbox` — no filesystem, no network, timeout, output sanitization | Android: `agent/safety/LlmSandbox.kt` |
| **Post-Training** | LoRA adapters (domain, dialect, personal) fine-tuned on-device | Android: `core/language/FederatedLearningClient.kt` |
| **Cognitive Loop** | `processInput()` — single suspend function, 7 phases | Android: `agent/SuperAgent.kt` |

#### Specific Code Changes

**Android (msaidizi-app):**
1. CREATE `agent/SuperAgent.kt` — Unified cognitive agent (replaces Orchestrator + all handlers)
2. CREATE `agent/Tool.kt` — Tool interface + ToolResult
3. CREATE `agent/tools/*.kt` — 22 tool implementations (from decomposed handlers)
4. CREATE `agent/SafetyChecker.kt` — Inline safety (replaces AGIReadyLayer)
5. DELETE `agent/Orchestrator.kt`, `BusinessAgent.kt`, `AnalysisAgent.kt`, `AdvisorAgent.kt`, `LearningAgent.kt`, `ConversationManager.kt`, all `*Handler.kt`, `MoERouter.kt`, `A2AProtocol.kt`, `CrossDomainKnowledgeGraph.kt`, and 20+ more files (~51% class reduction)
6. MODIFY `core/di/AIModule.kt` — 40+ providers → 10 providers

**Backend (angavu-intelligence-backend):**
1. CREATE `app/services/intelligence_engine.py` — Direct service calls (replaces agent indirection)
2. CREATE `app/services/scheduler.py` — Background task scheduling (replaces agent polling)
3. DELETE `app/agents/` (153 files, ~59,762 lines) — All agent infrastructure
4. MODIFY `app/main.py` — Remove agent wiring from lifespan (300+ lines → 30 lines)

#### Priority: 🔴 P0 — Build First (Weeks 1-4)

This is the foundation. Without the unified agent, nothing else connects.

---

### INTEGRATION POINT 2: OpenClaw → Security Architecture

#### What the Research Said

OpenClaw provides: secure runtime for autonomous agents, policy-based guardrails, sandboxing, access control, governance, and the principle that "security + access control = prerequisites for deployment, like HR for employees." The research identified OpenClaw as the security layer that makes autonomous agents safe to deploy.

#### What the Architect Designed

The security architect designed a 6-layer security architecture: input validation, processing sandboxing, output safety, data protection, progressive autonomy, and governance/audit. The capability-based access control model has 4 tiers (Auto-Execute, Worker-Confirm, Elevated, Locked). The PQC infrastructure already has ML-KEM + ML-DSA implemented.

#### How They Connect

OpenClaw's sandboxing model MAPS DIRECTLY to the architect's security layers:

| OpenClaw Concept | Msaidizi Security Layer | Implementation |
|---|---|---|
| **Sandbox** | Layer 2: Processing Sandboxing | `LlmSandbox.kt` — no filesystem, no network, timeout |
| **Policy-based Guardrails** | Layer 1: Input Validation + Layer 3: Output Safety | `PromptGuard` (20+ patterns) + `OutputSanitizer` (10-layer) |
| **Access Control** | Layer 4: Capability-Based Permissions | `capability_tokens.py` (ML-DSA-65 signed) |
| **Governance** | Layer 6: Audit + Ethics | `GovernanceModule` — audit log, ethics review, bias detection |
| **Worker Sovereignty** | Layer 5: Progressive Autonomy | `ProgressiveAutonomy` — trust-based capability unlocking |

#### Specific Code Changes

**Backend:**
1. KEEP `app/security/pqc/` — Already production-ready (ML-KEM, ML-DSA, hybrid key exchange)
2. KEEP `app/security/capability_tokens.py` — ML-DSA-65 signed capability tokens
3. KEEP `app/security/prompt_guard.py` — 20+ regex patterns for injection detection
4. CREATE `app/security/tool_sandbox.py` — Network allowlisting, resource limits, execution isolation
5. CREATE `app/security/constitutional_enforcer.py` — Runtime principle enforcement (12 principles)
6. MODIFY `app/security/rate_limiter.py` — Add per-tool rate limits

**Android:**
1. CREATE `agent/safety/LlmSandbox.kt` — On-device LLM sandboxing
2. MODIFY `agent/SafetyChecker.kt` — Integrate constitutional principles
3. KEEP `agent/agi/AGIReadyLayer.kt` — Already has safety boundaries (refactor into SafetyChecker)

#### Priority: 🔴 P0 — Build Alongside Agent (Weeks 1-4)

Security is not a phase — it's woven into every component from Day 1.

---

### INTEGRATION POINT 3: Hermes → Memory Architecture

#### What the Research Said

Hermes provides a 3-layer memory system: L1 (Working/Session), L2 (Episodic/Past Events), L3 (Behavioral/Learned Patterns). The research identified that "the agent doesn't retrieve knowledge — it HAS knowledge" and that memory must be unified, not three separate databases.

#### What the Architect Designed

The memory architect designed a `UnifiedMemoryBridge` class that connects L1↔L2↔L3. L1 is `ConversationMemory` (in-RAM, 10 turns). L2 is `EpisodicMemory` (SQLite FTS5, 10K episodes, BM25 search). L3 is `HermesSessionManager` (WorkerProfile, Bayesian beliefs, skill discovery). The bridge enriches context before every interaction and updates all layers after every interaction.

#### How They Connect

Hermes IS the memory architecture. The research's 5-layer model (Working, Episodic, Behavioral, Semantic, Collective) maps to the architect's 3-layer model with extensions:

| Hermes Layer | Architect Layer | Implementation | Status |
|---|---|---|---|
| **L1: Working** | `ConversationMemory.kt` | In-RAM, 10 turns, 30-min window | ✅ EXISTS |
| **L2: Episodic** | `EpisodicMemory.kt` | SQLite FTS5, 10K episodes, BM25 | ✅ EXISTS |
| **L3: Behavioral** | `HermesSessionManager.kt` | WorkerProfile, Bayesian beliefs, skills | ✅ EXISTS |
| **L4: Semantic** | Domain Knowledge DB | Structured informal economy facts | ⚠️ NEEDS BUILDING |
| **L5: Collective** | Federated Learning Aggregation | Cross-worker patterns via FL | ⚠️ NEEDS BUILDING |

#### Specific Code Changes

**Android:**
1. CREATE `agent/memory/UnifiedMemoryBridge.kt` — THE GLUE connecting L1↔L2↔L3 (see Memory Architect's design — 500+ lines of production-ready code)
2. MODIFY `agent/Orchestrator.kt` (or `SuperAgent.kt`) — Add `memoryBridge.enrichContext()` before intent classification, `memoryBridge.postProcess()` after response
3. MODIFY `agent/hermes/HermesSessionManager.kt` — Add `updateWorkerBeliefs()`, `updateWorkerProfile()`, `updateGlobalPrior()`
4. CREATE `agent/memory/FederatedMemorySync.kt` — Backend sync with differential privacy

**Backend:**
1. CREATE `app/services/consolidation_engine.py` — L2→L3 pattern extraction (weekly)
2. CREATE `app/services/skill_marketplace.py` — Cross-worker skill distribution
3. MODIFY `app/services/federated_learning.py` — Add Fisher information distribution for EWC

#### Priority: 🔴 P0 — Build With Agent (Weeks 2-4)

Memory is what makes the agent learn. Without the bridge, L2 and L3 are dead code.

---

### INTEGRATION POINT 4: Jensen's Super Agent Vision → Code Architecture

#### What the Research Said

Jensen Huang: *"A super agent is NOT multi-agentic. It's ONE unified intelligence."* The research validated this: LangChain says "start with a single agent with well-designed tools." Anthropic's research shows single-agent with tool use outperforms multi-agent for most tasks. The research identified the fundamental difference: multi-agent = distributed intelligence with message passing; super agent = unified intelligence with internal specialization.

#### What the Architect Designed

The Android architect collapsed 33+ agents into 1 `SuperAgent.kt` with 22 tools. The backend architect collapsed 105+ agent classes into 0 agents — pure service architecture. The chief architect's summary: "The Android app already IS the super agent. The backend is a mirror."

#### How They Connect

Jensen's vision IS the architect's design. The specific translation:

| Jensen's Principle | Architectural Implementation |
|---|---|
| "One intelligence, not multi-agent" | `SuperAgent.kt` — single class, 10 deps, 22 tools |
| "Harness makes the model deliver" | `ToolRegistry` + `UnifiedMemoryBridge` + `SafetyChecker` + LoRA adapters |
| "Post-trained in the harness" | On-device LoRA fine-tuning from worker interactions |
| "Explore larger spaces" | On-device inference ($0 marginal cost) enables unlimited interactions |
| "Skills, not separate agents" | `AgentSkill` interface — capabilities as registered tools |

#### Specific Code Changes

The code changes are ALREADY SPECIFIED in Integration Points 1, 2, and 3. The key principle is:

**DELETE:** Everything agent-related that adds overhead without value:
- `A2AProtocol.kt`, `AgentProfile.kt` — Multi-agent protocol (unused on-device)
- `MoERouter.kt`, `ExpertRegistry.kt` — Model routing (one model on 2GB)
- `CrossDomainKnowledgeGraph.kt` — Too heavy for 2GB
- `ProgressiveAutonomy.kt` — Premature (inline into SuperAgent)
- `CostBudgetManager.kt`, `InferenceCostTracker.kt` — On-device = free
- `SpeechToSpeechEngine.kt`, `StreamingVoicePipeline.kt` — Too heavy for 2GB
- All `security/pqc/*.kt` on Android — Premature (TLS 1.3 sufficient for v1)
- All `security/privacy/*.kt` on Android — Keep FederatedLearningClient only

**KEEP:** Everything that makes the agent smart:
- `IntentRouter.kt` — 90% code-only intent classification (0 RAM)
- `EpisodicMemory.kt` — SQLite FTS5 (sub-10ms, offline)
- `VoicePipeline.kt` — Mutual exclusion for 2GB devices
- `HermesSessionManager.kt` — Worker-keyed sessions + skills
- `ReActLoop.kt` — Lightweight reasoning trace
- `AdaptiveLearningEngine.kt` — Vocabulary + corrections + context injection
- `ConversationMemory.kt` — Clean, minimal, works

#### Priority: 🔴 P0 — This IS the build (Weeks 1-4)

---

### INTEGRATION POINT 5: Flywheel Learning → Flywheel Architecture

#### What the Research Said

McKinsey's AI Flywheel: "Better technology → more applications → more data → more investment." Jensen Huang: *"Use → gets smarter → more useful → more use → even smarter."* The research identified the dual flywheel: personal (on-device) and collective (backend). The research also identified the critical missing piece: intelligence products (Soko Pulse, Alama Score) don't feed back into the learning loop.

#### What the Architect Designed

The flywheel architect designed a complete dual-loop system:
- **Device Flywheel:** Interaction → signal capture → L3 LoRA update → personal model → better responses → more use
- **Cloud Flywheel:** Aggregation → FedAvg + DP → global model → intelligence products → all workers smarter → more data
- **Missing connection:** Intelligence product outcomes don't feed back into training

The flywheel architect also designed:
- EWC (Elastic Weight Consolidation) to prevent catastrophic forgetting
- Intelligence feedback collector to close the loop
- Collective intelligence synthesis for cross-worker patterns
- Privacy budget tracking (cumulative ε enforcement)
- A/B testing framework (already implemented in LearningHarness)
- CUSUM drift detection (exists but not connected to retraining)

#### How They Connect

The research's flywheel IS the architect's dual loop. The critical synthesis:

| Research Flywheel Concept | Architect Implementation | Gap |
|---|---|---|
| "Use → smarter" (personal) | `DeviceFlywheel.kt` — on-device learning | ⚠️ Needs wiring into SuperAgent |
| "Smarter → more use" (collective) | `CloudFlywheel` — FL aggregation + model distribution | ⚠️ Needs version check endpoint |
| "Intelligence products feedback" | `IntelligenceFeedbackCollector` | ❌ NOT YET DESIGNED (new file needed) |
| "Cross-worker patterns" | `CollectiveIntelligenceService` | ❌ NOT YET DESIGNED (new file needed) |
| "Catastrophic forgetting prevention" | `EWCRegularizer.kt` | ❌ NOT YET DESIGNED (new file needed) |
| "Drift detection → retraining" | `CusumDriftTracker.kt` + event emission | ⚠️ Exists but not connected |
| "Privacy budget tracking" | `PrivacyBudgetTracker.kt` | ❌ NOT YET DESIGNED (new file needed) |

#### Specific Code Changes

**Android:**
1. CREATE `agent/flywheel/DeviceFlywheel.kt` — Wire into SuperAgent's LEARN phase
2. CREATE `agent/flywheel/EWCRegularizer.kt` — Fisher information + gradient penalty
3. CREATE `agent/flywheel/PrivacyBudgetTracker.kt` — Cumulative ε enforcement
4. MODIFY `core/language/FederatedLearningClient.kt` — Add retry logic, delta downloads, EWC integration
5. MODIFY `core/model/CusumDriftTracker.kt` — Emit drift events to trigger retraining

**Backend:**
1. CREATE `app/services/intelligence_feedback.py` — Track advice outcomes → training signals
2. CREATE `app/services/collective_intelligence.py` — Cross-worker pattern synthesis
3. CREATE `app/services/fisher_information.py` — Compute Fisher info for EWC distribution
4. MODIFY `app/services/federated_learning.py` — Add version check endpoint, Fisher info distribution, delta computation
5. MODIFY `app/services/adaptive_learning.py` — Subscribe to intelligence outcome events
6. MODIFY `app/services/training/loop.py` — Implement all 8 agent `collect()`/`train()`/`evaluate()` methods

#### Priority: 🟡 P1 — Build After Agent Foundation (Weeks 5-8)

The flywheel needs the agent to exist first. You can't learn from interactions if there's no agent having interactions.

---

### INTEGRATION POINT 6: Quantum-Ready → Security + Backend Architecture

#### What the Research Said

**Honest assessment from research:** 95% of problems informal workers face are solved by classical AI/ML. Quantum computing offers genuine advantage in only ~5% of cases (Monte Carlo for credit risk, large-scale portfolio optimization), and even there, practical timelines are 5-15 years. However, post-quantum cryptography (PQC) is critical NOW — "harvest now, decrypt later" attacks mean data encrypted today could be decrypted by quantum computers in 10-15 years.

**Key finding:** PQC is the immediate quantum win. Quantum-ready architecture means designing interfaces that can swap algorithms later. Quantum processing is a 5-10 year horizon.

**Free quantum resources available NOW:**
- IBM Quantum: 10 min/month free on real hardware
- D-Wave Leap: Free tier for quantum annealing
- PennyLane: Free quantum ML framework
- NVIDIA CUDA-Q: Free quantum simulation on GPUs

#### What the Architect Designed

The security architect designed a 4-phase PQC migration:
- Phase 1 (NOW): Hybrid X25519+ML-KEM-768 for TLS, ML-DSA-65 for tokens
- Phase 2 (Jan 2027): PQC-preferred, classical fallback
- Phase 3 (Jul 2027): PQC-only for new connections
- Phase 4 (Jan 2028+): PQC-only, classical removed

The backend already has production-grade PQC: `ml_kem.py`, `ml_dsa.py`, `hybrid_key_exchange.py`, `fl_encryption.py` — all using real liboqs.

#### How They Connect

| Research Finding | Architectural Response | Status |
|---|---|---|
| PQC is critical NOW | Phase 1 hybrid mode already implemented | ✅ DONE |
| PQC protects FL gradients | `fl_encryption.py` — ML-KEM + AES-256-GCM + ML-DSA | ✅ DONE |
| PQC protects capability tokens | `capability_tokens.py` — ML-DSA-65 signed | ✅ DONE |
| Quantum-ready interfaces | `crypto_provider.py` — algorithm-agnostic abstraction | ✅ DONE |
| Quantum optimization (future) | Design `QuantumOptimizer` interface that can swap classical↔quantum | ⚠️ DESIGN ONLY |
| Free quantum access | IBM Quantum + D-Wave + PennyLane — team literacy program | ⚠️ NEEDS ACTION |

#### Specific Code Changes

**Backend:**
1. KEEP `app/security/pqc/` — Already production-ready (do NOT delete as originally planned)
2. CREATE `app/services/quantum_optimizer.py` — Abstract interface for optimization problems
3. MODIFY `app/security/pqc/config.py` — Verify Phase 1 is active

**Team Actions (not code):**
1. Sign up for IBM Quantum Open Plan (free)
2. Install Qiskit, D-Wave Ocean SDK, PennyLane (free)
3. Complete IBM quantum learning courses (free)
4. Run first quantum circuit on real hardware
5. Benchmark quantum vs classical on a Msaidizi optimization problem

**Android:**
1. KEEP `FederatedLearningPrivacy.kt` — Hybrid PQC encryption (X25519+ML-KEM-768)
2. No other Android PQC changes needed for v1

#### Priority: 🟢 P2 — PQC is Done, Quantum Exploration is Ongoing

PQC is already implemented. Quantum computing is a 5-10 year horizon. Build team literacy now, integrate when practical advantage is demonstrated.

---

### INTEGRATION POINT 7: AGI-Ready → Android + Backend Architecture

#### What the Research Said

The AGI readiness research identified a hybrid model stack:
- **On-device (80%):** Qwen 0.8B — free, offline, instant
- **Cloud Tier 1 (15%):** DeepSeek V4 Flash ($0.14/MTok) — reasoning, translation
- **Cloud Tier 2 (5%):** Claude Haiku 4.5 ($1/MTok) — complex reasoning
- **Free tier:** Google Gemini (1,500 prompts/day free)

**Cost projection:** $0.50-$2.00/worker/month at 1K workers, dropping to $0.05-$0.10 at 1M workers. At scale with self-hosted inference: <$0.01/worker/month.

**Key models:**
- On-device: Qwen 0.8B (already in Msaidizi), SmolLM 135M (fallback)
- Cloud: DeepSeek V4 Flash (price-performance champion), Gemini Flash (free tier)
- Self-hosted future: Mistral Small 4 (Apache 2.0, 119B total, 6B active)

#### What the Architect Designed

The Android architect designed a model selection logic:
- BASIC tier (2GB): SmolLM for simple tasks, NVIDIA API for complex (if online)
- STANDARD tier (3GB+): Qwen2-0.5B, Phi-3-mini for complex reasoning
- Mutual exclusion: Only ONE heavy model in memory at a time

The backend architect designed `LLMService` that routes to NVIDIA API (free) or local model.

#### How They Connect

| Research Model Stack | Architect Implementation | Integration |
|---|---|---|
| Qwen 0.8B on-device | `LlamaCppEngine.kt` — already exists | ✅ DONE |
| SmolLM 135M fallback | `LlmEngine.kt` — model selection by device tier | ⚠️ Needs SmolLM integration |
| DeepSeek V4 Flash (cloud) | `LLMService` — cloud escalation | ⚠️ Needs DeepSeek API integration |
| Gemini Flash (free tier) | `LLMService` — free tier routing | ⚠️ Needs Gemini API integration |
| Claude Haiku 4.5 (complex) | `LLMService` — frontier model routing | ⚠️ Needs Claude API integration |
| Mistral Small 4 (self-hosted) | Future: Docker container on Oracle | 🔮 Phase 4+ |

#### Specific Code Changes

**Android:**
1. MODIFY `voice/LlmEngine.kt` — Add cloud escalation logic
2. CREATE `agent/CloudEscalationRouter.kt` — Intent complexity → model routing
3. MODIFY `voice/LlamaCppEngine.kt` — Add SmolLM 135M support for BASIC tier

**Backend:**
1. CREATE `app/services/cloud_brain.py` — Unified cloud LLM interface
2. MODIFY `app/services/llm_service.py` — Add DeepSeek, Gemini, Claude providers
3. CREATE `app/services/cost_tracker.py` — Per-worker cloud cost tracking

**Configuration:**
```python
CLOUD_LLM_STACK = {
    "tier1": {"provider": "deepseek", "model": "deepseek-v4-flash", "cost_per_mtok": 0.14},
    "tier2": {"provider": "anthropic", "model": "claude-haiku-4.5", "cost_per_mtok": 1.00},
    "free": {"provider": "google", "model": "gemini-flash", "daily_limit": 1500},
}
```

#### Priority: 🟡 P1 — Cloud Escalation After On-Device Agent Works

The on-device agent handles 80% of tasks. Cloud escalation is the 20% enhancement.

---

### INTEGRATION POINT 8: Multi-Language → Voice + Flywheel Architecture

#### What the Research Said

Meta's MMS-1B supports 1,107 ASR languages and 4,017 language identification. This is the foundation. The research designed a 5-phase dialect rollout:
1. Swahili only (Month 1-2)
2. Swahili + Sheng (Month 3-4)
3. East African expansion — Kikuyu, Dholuo, Luhya, Kalenjin, Maasai (Month 5-6)
4. Pan-African — Hausa, Yoruba, Igbo, Somali, Amharic, Zulu, Xhosa (Month 7-9)
5. Premium quality — Kokoro fine-tuned for top 5 languages (Month 10-12)

**Key finding:** Sheng is not a language — it's dynamic urban slang mixing Swahili, English, and local languages. No ASR model supports it. It requires custom learning from workers.

**ASR quality (WER):**
- Swahili: 8-10% (MMS-1B) — production-ready
- Hausa: 12-15% — usable with context correction
- Yoruba: 14-18% — moderate, tonal challenges
- Kalenjin/Maasai: 25-40% — needs dedicated fine-tuning

**TTS strategy:** MMS-TTS for breadth (all dialects), Kokoro for quality (Swahili), Piper for fallback (25MB).

#### What the Architect Designed

The voice architect designed:
- Sherpa-ONNX as primary engine (Whisper for ASR, Piper/Kokoro for TTS)
- Mutual exclusion for 2GB devices (Whisper ↔ Kokoro)
- `DialectLearningEngine` with 14+ dialect detection, phoneme confusion matrices, code-switching detection
- `ConversationLearningPipeline` for ASR word-level confidence tracking, unknown word capture, auto-promotion after 3 uses
- `FederatedLearningClient` for privacy-preserving dialect learning
- Wake word detection for voice-only interface
- Barge-in detection for interruption support
- Progressive model download (bundled → first launch → on-demand)

The flywheel architect designed:
- Device flywheel: corrections → vocabulary → LoRA training → better ASR
- Cloud flywheel: aggregated corrections → global dialect model → all devices

#### How They Connect

| Research Finding | Architect Implementation | Integration Point |
|---|---|---|
| MMS-1B for 1,107 languages | `SherpaVoiceEngine.kt` — Sherpa-ONNX supports MMS | ✅ EXISTS |
| 5-phase dialect rollout | `DialectLearningEngine.kt` — already supports 14+ dialects | ✅ EXISTS |
| Sheng custom learning | `ConversationLearningPipeline.kt` — unknown word capture + auto-promotion | ✅ EXISTS |
| LoRA per-dialect adapters | `FederatedLearningClient.kt` — on-device LoRA training | ✅ EXISTS |
| Federated dialect learning | `federated_learning.py` — FedAvg + DP aggregation | ✅ EXISTS |
| Wake word detection | Voice architect design — Sherpa-ONNX keyword spotter | ⚠️ NEEDS BUILDING |
| Barge-in detection | Voice architect design — VAD during TTS playback | ⚠️ NEEDS BUILDING |
| Progressive model download | `ModelRegistry.kt` — tier-based loading | ✅ EXISTS |
| Code-switching TTS | Voice architect design — blend Swahili+English audio | ⚠️ NEEDS BUILDING |
| 195 seed vocabulary terms | `seed_vocabulary_sw.json` — exists | ✅ EXISTS |

#### Specific Code Changes

**Android:**
1. CREATE `voice/WakeWordDetector.kt` — Sherpa-ONNX keyword spotter (~3MB)
2. MODIFY `voice/VoicePipeline.kt` — Add barge-in detection during TTS
3. MODIFY `voice/KokoroTtsEngine.kt` — Add code-switching audio blending
4. MODIFY `voice/DialectLearningEngine.kt` — Wire into SuperAgent's LEARN phase

**Backend:**
1. MODIFY `app/services/federated_learning.py` — Add dialect-specific aggregation
2. CREATE `app/services/dialect_model_registry.py` — LoRA adapter versioning per dialect

**Language Pipeline (angavu-intelligence):**
1. IMPLEMENT `msaidizi-language-pipeline/fine_tuning/__init__.py` — Wire to real llama.cpp NDK
2. IMPLEMENT `msaidizi-language-pipeline/agents/memory/skill_generator.py` — Skill generation from successful patterns

#### Priority: 🟡 P1 — Voice Enhancements After Core Agent (Weeks 5-8)

The voice pipeline already works. Enhancements (wake word, barge-in, code-switching TTS) are quality-of-life improvements.

---

### INTEGRATION POINT 9: Free Resources → Every Architectural Decision

#### What the Research Said

The $0 constraint is not a limitation — it's a design principle. Available free resources:
- **Oracle Cloud Free Tier:** 2 ARM OCPUs, 12GB RAM, 200GB storage
- **NVIDIA API:** Free frontier models (Llama 3.1 8B)
- **Google Gemini:** 1,500 free prompts/day
- **IBM Quantum:** 10 min/month free on real quantum hardware
- **D-Wave Leap:** Free quantum annealing access
- **All models open-source:** Qwen, SmolLM, Mistral, Whisper, Piper, MMS
- **All frameworks open-source:** Sherpa-ONNX, llama.cpp, Flower, Qiskit

**Cost projection at scale:**
- 1K workers: $500-$1,000/month ($0.50-$1.00/worker)
- 10K workers: $3,000-$5,000/month ($0.30-$0.50/worker)
- 100K workers: $15,000-$25,000/month ($0.15-$0.25/worker)
- 1M workers with self-hosted: <$0.01/worker/month

#### What the Architect Designed

The backend architect allocated Oracle Free Tier:
- PostgreSQL: 0.5 CPU, 1.5GB RAM, 50GB storage
- Redis: 0.25 CPU, 256MB RAM
- ClickHouse: 0.25 CPU, 1GB RAM, 100GB storage
- FastAPI: 0.5 CPU, 512MB RAM
- Worker: 0.25 CPU, 512MB RAM
- Monitoring: 0.15 CPU, 384MB RAM
- **Total: 2.0 OCPUs, 4.3GB RAM, 165GB storage — 7.7GB headroom**

**Decision: No llama.cpp on free tier.** The 7B model needs 6-8GB RAM. Use free tier for data pipeline + intelligence products. LLM inference is on-device (free) or cloud API (free tier).

#### How They Connect

Every architectural decision is shaped by the $0 constraint:

| Decision | $0 Constraint Impact |
|---|---|
| On-device inference | Qwen 0.8B on phone = $0 marginal cost per interaction |
| Oracle Free Tier | Backend runs intelligence products, not LLM inference |
| No cloud STT/TTS | Sherpa-ONNX on-device = $0, works offline |
| Open-source everything | No licensing costs, full control |
| NVIDIA API for complex queries | Free frontier model for the 10% that need it |
| Gemini free tier | 1,500 prompts/day for market data queries |
| Self-hosted future | Mistral Small 4 on Oracle (when revenue justifies upgrade) |
| Federated learning | Privacy-preserving aggregation without centralizing data |
| Progressive model download | Workers download models on WiFi, not on our bandwidth |

#### Specific Code Changes

**Backend:**
1. MODIFY `deploy/oracle/docker-compose.yml` — Use the architect's resource allocation (see Backend Architect's design)
2. CREATE `app/services/cost_guard.py` — Prevent runaway costs (already exists as script, integrate into service)
3. MODIFY `app/worker.py` — Add intelligence scheduler (replaces agent polling)

**No Android changes** — on-device is already $0.

#### Priority: 🔴 P0 — This Constrains Everything

The $0 constraint is not a phase — it's a permanent design principle. Every architectural decision must be validated against it.

---

### INTEGRATION POINT 10: The People → UX, Voice, Language, Trust Architecture

#### What the Research Said

**The economic reality:**
- 600M+ informal workers in Africa, 85.8% of employment
- Kenya: 83% informal workforce (~15.2 million workers)
- The three problems cost Kenya $12-20 billion/year (conservatively)
- Only 17% of informal workers have access to formal credit
- Informal workers earn $2-10/day
- Most use $50 phones (Tecno/Infinix/Itel, 2GB RAM)
- Many are semi-literate or illiterate
- Voice is the PRIMARY interface, not text

**The trust reality:**
- Workers distrust technology companies
- Data exploitation is a real risk
- M-Pesa charges 7.5-12% per month for credit (vs 1.5% formal)
- Middlemen exploit information gaps
- Women are disproportionately affected (90% of employed women in informal work)

**The opportunity:**
- Solving these 3 problems unlocks $1.5-3 trillion/year for Africa
- Kenya alone: $15-25 billion/year potential GDP increase
- No one else is building a holistic AI agent for informal workers
- Window: 18-24 months before big tech enters

#### What the Architect Designed

The architects designed for these exact constraints:
- **Voice-first:** Sherpa-ONNX, mutual exclusion for 2GB, Piper TTS fallback
- **Offline-first:** Everything works without internet
- **Swahili-first:** Bilingual UI, 195 seed terms, dialect learning
- **$50 phones:** BASIC tier with SmolLM 135M, STANDARD with Qwen 0.8B
- **Privacy-first:** On-device processing, differential privacy, worker data sovereignty
- **Trust-based:** Progressive autonomy, constitutional AI principles, worker confirmation for financial ops

#### How They Connect

| Worker Need | Architecture Response | Implementation |
|---|---|---|
| Voice interaction (no keyboard) | Voice pipeline with wake word, barge-in, dialect learning | `VoicePipeline.kt` + `SherpaVoiceEngine.kt` |
| Works on $50 phone | Mutual exclusion, model budgeting, BASIC tier support | `DeviceTier.kt`, `VoicePipeline.kt` |
| Works offline | On-device inference, SQLite storage, queue-and-sync | `LlamaCppEngine.kt`, `EpisodicMemory.kt`, `SyncEngine.kt` |
| Speaks their language | MMS-1B, 14+ dialects, Sheng learning, code-switching | `DialectLearningEngine.kt`, `ConversationLearningPipeline.kt` |
| Trusts the agent | Progressive autonomy, constitutional AI, worker confirmation | `SafetyChecker.kt`, `ConstitutionalEnforcer.py` |
| Owns their data | On-device processing, DP, no raw data leaves phone | `FederatedLearningClient.kt`, `FederatedLearningPrivacy.kt` |
| Gets value immediately | 195 seed terms, rule-based intent (90% no LLM), Piper TTS bundled | `IntentRouter.kt`, `seed_vocabulary_sw.json` |
| Learns their business | Flywheel: corrections → vocabulary → LoRA → personalization | `DeviceFlywheel.kt`, `AdaptiveLearningEngine.kt` |
| Financial protection | Confirmation for M-Pesa, daily limits, elevated confirmation thresholds | `SafetyChecker.kt`, capability tokens |
| Cultural sensitivity | Ubuntu philosophy, no shaming, positive framing, Swahili proverbs | `VoicePersonality.kt`, `BiasMonitor.py` |

#### Specific Code Changes

**Android:**
1. BUNDLE in APK: Silero VAD (0.6MB) + Piper TTS (25MB) + seed vocabulary (0.02MB) = ~30MB
2. IMPLEMENT wake word detection for voice-only interface
3. IMPLEMENT barge-in detection for natural conversation
4. ENSURE all responses follow voice-only formatting rules (no URLs, numbers as words, short sentences)

**Backend:**
1. IMPLEMENT constitutional AI principles (12 principles, runtime enforcement)
2. IMPLEMENT bias monitoring (EEOC 4/5ths rule, shaming language detection)
3. IMPLEMENT explainability engine (why was this recommendation made?)
4. IMPLEMENT right-to-be-forgotten pipeline (automated cascade deletion)

**Website:**
1. FIX Formspree placeholder
2. CREATE `download.html` — Step-by-step install guide in Swahili
3. CREATE `vision.html` — Company presence for investors/partners
4. FIX privacy policy email

#### Priority: 🔴 P0 — This IS the Mission

Everything we build must serve these workers. If it doesn't work on a $50 phone, offline, in Sheng, with voice — it doesn't ship.

---

## UNIFIED IMPLEMENTATION ROADMAP

### Phase 1: Foundation (Weeks 1-4) — "Make It One"

**Goal:** Collapse 33+ agents into 1 SuperAgent. Wire memory. Secure it.

| Week | Tasks | Integration Points |
|---|---|---|
| **1** | Create `SuperAgent.kt`, `Tool.kt`, `SafetyChecker.kt`. Decompose handlers into tools. | IP1 (Deep Agents), IP4 (Jensen) |
| **2** | Create `UnifiedMemoryBridge.kt`. Wire L1↔L2↔L3. Modify Orchestrator. | IP3 (Hermes) |
| **3** | Backend: Delete 153 agent files. Create `IntelligenceEngine`, `Scheduler`. | IP1 (Deep Agents), IP9 ($0) |
| **4** | Security: Wire `ConstitutionalEnforcer`, `tool_sandbox.py`, confirmation UX. | IP2 (OpenClaw), IP10 (People) |

**Deliverable:** One agent, unified memory, secured. Runs on $50 phone. $0 infrastructure cost.

### Phase 2: Learning (Weeks 5-8) — "Make It Smart"

**Goal:** Close the flywheel. Add cloud escalation. Enhance voice.

| Week | Tasks | Integration Points |
|---|---|---|
| **5** | Create `DeviceFlywheel.kt`. Wire into SuperAgent's LEARN phase. | IP5 (Flywheel) |
| **6** | Create `EWCRegularizer.kt`, `PrivacyBudgetTracker.kt`. Add retry logic to FL. | IP5 (Flywheel), IP6 (Quantum/PQC) |
| **7** | Create `CloudEscalationRouter.kt`. Integrate DeepSeek + Gemini free tier. | IP7 (AGI-Ready) |
| **8** | Wake word detection. Barge-in detection. Code-switching TTS. | IP8 (Multi-Language) |

**Deliverable:** Agent learns from every interaction. Cloud escalation for complex queries. Voice-only UX complete.

### Phase 3: Intelligence (Weeks 9-12) — "Make It Expert"

**Goal:** Close the intelligence feedback loop. Domain knowledge embedding. Collective intelligence.

| Week | Tasks | Integration Points |
|---|---|---|
| **9** | Create `IntelligenceFeedbackCollector`. Wire Soko Pulse + Alama Score outcomes. | IP5 (Flywheel) |
| **10** | Create `CollectiveIntelligenceService`. Cross-worker pattern synthesis. | IP5 (Flywheel), IP10 (People) |
| **11** | LoRA domain adapters: Swahili business, financial reasoning, market context. | IP1 (Deep Agents), IP8 (Language) |
| **12** | Backend: FL server with Flower. Consolidated FL service. Version check endpoint. | IP5 (Flywheel), IP9 ($0) |

**Deliverable:** Intelligence products feed back into learning. Cross-worker patterns distributed. Domain expertise embedded.

### Phase 4: Scale (Weeks 13-16) — "Make It Grow"

**Goal:** Dialect expansion. Website. Distribution. Quantum literacy.

| Week | Tasks | Integration Points |
|---|---|---|
| **13** | Website: Fix critical issues. Create download.html, vision.html, api.html. | IP10 (People), IP9 ($0) |
| **14** | Dialect expansion: Kikuyu, Dholuo, Luhya adapters from flywheel data. | IP8 (Multi-Language) |
| **15** | Quantum literacy: Team signs up for IBM Quantum, D-Wave, PennyLane. | IP6 (Quantum) |
| **16** | Monitoring: Prometheus + Grafana. Bias dashboard. Privacy budget dashboard. | IP2 (OpenClaw), IP10 (People) |

**Deliverable:** Production-grade system. 20+ dialects. Monitoring operational. Team quantum-literate.

---

## PRIORITY MATRIX

```
                         HIGH IMPACT
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          │  IP1: Deep Agents│  IP5: Flywheel   │
          │  ★ WEEK 1-4     │  ★ WEEK 5-8     │
          │                  │                  │
          │  IP4: Jensen     │  IP7: AGI-Ready  │
          │  ★ WEEK 1-4     │  ★ WEEK 5-8     │
          │                  │                  │
LOW ──────┼──────────────────┼──────────────────┼───── HIGH
EFFORT    │                  │                  │      EFFORT
          │  IP3: Hermes     │  IP8: Language    │
          │  ★ WEEK 2-4     │  ★ WEEK 5-8     │
          │                  │                  │
          │  IP2: OpenClaw   │  IP6: Quantum    │
          │  ★ WEEK 1-4     │  ★ WEEK 13-16   │
          │                  │                  │
          │  IP10: People    │  IP9: $0         │
          │  ★ ALWAYS        │  ★ ALWAYS        │
          │                  │                  │
          └──────────────────┼──────────────────┘
                             │
                         LOW IMPACT
```

---

## WHAT GETS BUILT FIRST (Week 1)

Day 1: Create `agent/Tool.kt` interface + `ToolResult` data class
Day 1: Create `agent/SafetyChecker.kt` (inline safety)
Day 2: Create `agent/SuperAgent.kt` with empty tool registry
Day 2: Create first 5 tools: `RecordSaleTool`, `RecordPurchaseTool`, `RecordExpenseTool`, `CheckBalanceTool`, `CheckProfitTool`
Day 3: Wire `SuperAgent` into DI alongside existing `Orchestrator` (dual-run)
Day 3: Implement `processInput()` cognitive loop
Day 4: Create `agent/memory/UnifiedMemoryBridge.kt`
Day 4: Wire L2 episode search into `enrichContext()`
Day 5: Test dual-run: both Orchestrator and SuperAgent produce same results
Day 5: Switch ViewModels to inject SuperAgent

**By end of Week 1:** One agent serving all capabilities. Memory bridge connecting L1↔L2. Safety checker inline. Dual-run validated.

---

## THE END STATE

A mama mboga in Gikomba, Nairobi, with a $50 Tecno phone, speaks into her device:

> *"Msaidizi, nimeuza nyanya kilo tano kwa mia tano"*
> (Msaidizi, I sold five kilos of tomatoes for five hundred)

The super agent:
1. **Hears** her in Sheng-inflected Swahili (dialect learning from her corrections)
2. **Understands** the intent (sale recording) in <50ms (code-only, no LLM)
3. **Remembers** she sold tomatoes yesterday for KSh 450 (L2 episodic memory)
4. **Records** the transaction (SQLite, offline)
5. **Updates** her behavioral model — tomato margin improving (L3 Bayesian beliefs)
6. **Responds** via Piper TTS: *"Sawa! Umefanya mauzo ya nyanya, KSh 500. Margin yako ni 22% — imepanda kutoka jana!"* (OK! You sold tomatoes, KSh 500. Your margin is 22% — up from yesterday!)
7. **Learns** — her vocabulary, her patterns, her business (flywheel)
8. **Syncs** — when she's on WiFi, her anonymized patterns join thousands of others (federated learning)
9. **Protects** — her data never leaves the phone in raw form (differential privacy, PQC)
10. **Gets smarter** — for her, and for every worker like her (dual flywheel)

**This is the super agent. Not a chatbot. Not 33 agents. One intelligence, specialized for her world, that gets smarter every day.**

---

*"In the future, most companies will be built on harnesses."* — Jensen Huang

Msaidizi is built on THE harness. The harness that makes a 0.8B parameter model deliver frontier intelligence for the 600M+ informal workers who need it most.

---

**END OF UNIFIED BLUEPRINT**

*Compiled from: 10 research outputs (675+ lines swarm report, 78KB super agent synthesis, quantum/AGI/multi-language/economic research) + 9 architect outputs (58KB chief, 54KB android, 49KB backend, 61KB memory, 57KB voice, 49KB flywheel, 54KB security, 23KB website, 51KB original architect)*

---

## POST-SYNTHESIS: ARCHITECTURE IMPROVEMENTS (Enterprise Architecture Council)

The following 6 improvements were recommended by the Enterprise Architecture Council and implemented into the architecture documents prior to implementation.

### 1. Reflexion as Optional Phase (High-Stakes Decisions)
- **Document:** `arch_android.md` — SuperAgent cognitive loop
- **Change:** ReflexionLoop integrated as `reflectOnDecision()` method in SuperAgent (not a separate class)
- **Activation:** Only for financial transactions ≥KSh 5,000, loan commitments, multi-step planned intents
- **Behavior:** Uses LLM to self-critique the decision before execution. Adds caution disclaimer if CONCERN detected.

### 2. Lightweight Planning for Multi-Step Intents
- **Document:** `arch_android.md` — SuperAgent REASON phase
- **Change:** PlanExecuteLoop integrated as `planSteps()` method in SuperAgent (not a separate class)
- **Activation:** When multi-step patterns detected ("compare...and suggest", "check...and record")
- **Behavior:** Breaks complex request into 2-4 ordered tool calls with dependencies.

### 3. Per-Phase Metrics (Prometheus Format)
- **Documents:** `arch_android.md` + `arch_backend.md`
- **Android:** `PhaseMetrics` class emits latency, success rate, error count per cognitive loop phase. Exported via sync payload.
- **Backend:** Prometheus histograms/gauges/counters for `perceive`, `remember`, `reason`, `reflect`, `act`, `learn`. Alerting rules for latency and success rate thresholds.
- **Sync:** Device phase metrics aggregated on backend via `POST /api/v1/sync/metrics`.

### 4. Vector Clocks (Not Last-Write-Wins)
- **Documents:** `arch_android.md` + `arch_backend.md`
- **Change:** Replaced last-write-wins with vector clocks for sync conflict detection.
- **Resolution per data type:**
  - Transactions: merge (additive) — both are real events
  - Inventory: latest timestamp wins — physical reality
  - Preferences: merge (union) — combine settings
  - Skills: merge (union + confidence scoring) — average confidence for overlaps
- **Escalation:** Inventory delta >20%, contradictory goal/loan states, tombstone conflicts → notify worker.

### 5. Buyer Dashboard (Revenue API)
- **Document:** `arch_backend.md` — Section 3.8
- **Endpoints:**
  - `GET /api/v1/buyer/soko-pulse` — FMCG demand forecasting ($0.10-$1.00/query)
  - `GET /api/v1/buyer/alama-score` — Credit scoring ($0.05-$0.50/score)
  - `GET /api/v1/buyer/angavu-pulse` — MSME activity index ($500-$5,000/month)
  - `GET /api/v1/buyer/jamii-insights` — Financial inclusion ($100-$1,000/report)
  - `GET /api/v1/buyer/report/{type}` — PDF/HTML report generation
- **Auth:** Separate buyer API key + JWT (not worker auth)
- **Rate Limiting:** Per-tier (starter=100/day, professional=1K/day, enterprise=10K/day)
- **Buyer model:** `BuyerAccount` with company_name, tier, budget, usage tracking

### 6. Scaling Playbook (Decision Tree)
- **Document:** `arch_backend.md` — Section 7
- **Thresholds:**
  - <1K workers: Default Oracle Free Tier stack
  - 1K workers: Add PgBouncer, enable Redis caching
  - 2K workers: Upgrade Oracle instance (4 OCPUs, ~$50/month)
  - 5K workers: Add PG read replicas, partition ClickHouse tables
  - 10K workers: PG read replicas (2+), ClickHouse materialized views, Redis Cluster
  - 25K workers: Upgrade to 8 OCPUs (~$150/month)
  - 50K workers: Add Kafka, separate API/Worker/Scheduler processes
  - 100K workers: Switch to microservices, Kubernetes, ClickHouse cluster
  - 250K workers: PostgreSQL sharding by region
  - 1M workers: Hash-based PG sharding (10 shards), self-hosted LLM, multi-region
  - 10M workers: Managed everything, CQRS, event sourcing, TiDB

---

*Improvements implemented: 2026-07-24*
*All changes consistent across: arch_android.md, arch_backend.md, arch_chief.md, synthesize_all.md*
