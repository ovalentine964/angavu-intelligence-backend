# THE FLYWHEEL ARCHITECTURE
## Dual Learning Loop for Msaidizi/Angavu Intelligence

> *"Use → gets smarter → more useful → more use → even smarter"*
> — Jensen Huang, on the flywheel effect

**Author:** Chief Flywheel Architect
**Date:** 2026-07-24
**Status:** Architecture Design

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [The Flywheel Vision](#2-the-flywheel-vision)
3. [On-Device Flywheel (Personal)](#3-on-device-flywheel-personal)
4. [Backend Flywheel (Collective)](#4-backend-flywheel-collective)
5. [The Connection: Device ↔ Backend Sync](#5-the-connection-device--backend-sync)
6. [Implementation Plan](#6-implementation-plan)
7. [Metrics & Measurement](#7-metrics--measurement)
8. [Model Drift Detection & Handling](#8-model-drift-detection--handling)
9. [A/B Testing Framework](#9-ab-testing-framework)
10. [Privacy Guarantees Summary](#10-privacy-guarantees-summary)

---

## 1. Current State Analysis

### 1.1 What Exists (On-Device — `msaidizi-app`)

| Component | File | Status | What It Does |
|-----------|------|--------|-------------|
| **AdaptiveLearningEngine** | `agent/AdaptiveLearningEngine.kt` | ✅ Working | L2 context injection — tracks corrections, learns vocabulary, generates personalized LLM prompts, suggests prices |
| **LearningAgent** | `agent/LearningAgent.kt` | ✅ Working | Bayesian confidence updating, pattern recording, A/B test framework (STA 342/343), vocabulary tracking |
| **ConversationLearningPipeline** | `core/language/ConversationLearningPipeline.kt` | ✅ Working | ASR word-level confidence tracking, unknown word capture, auto-promotion after 3 uses, Sheng vocabulary, pronunciation variants |
| **FederatedLearningClient** | `core/language/FederatedLearningClient.kt` | ✅ Working | FedAvg upload/download, LoRA training on-device (rank-4, 512-dim), differential privacy (ε=0.1), anonymized correction patterns |
| **FederatedLearningPrivacy** | `security/privacy/FederatedLearningPrivacy.kt` | ✅ Working | Gradient clipping, Laplace noise, top-k compression, int8 quantization, hybrid PQC encryption (X25519+ML-KEM-768) |
| **DifferentialPrivacy** | `security/privacy/DifferentialPrivacy.kt` | ✅ Working | Laplace mechanism, randomized response, histogram noise, vector noise, gradient clipping |
| **LearningHarness** | `agent/harness/LearningHarness.kt` | ✅ Working | A/B testing, held-out validation, regression detection (5% threshold), rollback to checkpoints, preference gradual adoption (sigmoid ramp) |
| **SelfEvolutionManager** | `evolution/SelfEvolutionManager.kt` | ✅ Working | Preference learning, correction pattern analysis, feature usage tracking, satisfaction signals |
| **BusinessPatternTracker** | `agent/BusinessPatternTracker.kt` | ✅ Working | Day-of-week patterns, peak hours, product performance, business health scoring |

### 1.2 What Exists (Backend — `angavu-intelligence-backend`)

| Component | File | Status | What It Does |
|-----------|------|--------|-------------|
| **FederatedLearningService** | `services/federated_learning.py` | ✅ Working | FedAvg aggregation, dialect clustering (K-means), quality validation (z-test), model versioning, DP noise |
| **FederatedLearningV2Service** | `services/federated_learning_v2.py` | ✅ Working | K-anonymity (k≥5), tighter DP (ε=0.1), multi-category data, gradient clipping, weighted LoRA averaging |
| **AdaptiveLearningService** | `services/adaptive_learning.py` | ✅ Working | Bridges feedback events → FL updates, per-worker learning state (Hermes pattern), signal aggregation |
| **TrainingLoop** | `services/training/loop.py` | ⚠️ Scaffolded | 8-agent training pipeline (Collector→Curator→Trainer→Evaluator→Experiment→Deployer→Monitor→Feedback) — agents defined but `collect()`, `train()`, `evaluate()` raise `NotImplementedError` |
| **ModelTrainer** | `services/ml/model_trainer.py` | ✅ Working | XGBoost training, temporal splits, cross-validation, drift detection integration |
| **SelfImprovingAgent** | `agents/orchestration/self_improving_agent.py` | ⚠️ Partial | FeedbackAnalyzer + SkillMutator pattern defined, mutation strategies enumerated |

### 1.3 What's Disconnected (The Gaps)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CRITICAL GAPS                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. DEVICE → BACKEND: LoRA training runs on-device but the         │
│     connection to upload trained adapters is fire-and-forget.       │
│     No retry logic, no version negotiation, no delta-only upload.   │
│                                                                     │
│  2. BACKEND → DEVICE: Global model download exists but there's      │
│     no mechanism to push updates. Devices must poll weekly.         │
│     No incremental updates — always full adapter download.          │
│                                                                     │
│  3. TRAINING LOOP: The 8-agent TrainingLoop has all agents          │
│     defined but none are wired to actual data sources.              │
│     DataCollectorAgent.collect() raises NotImplementedError.        │
│                                                                     │
│  4. INTELLIGENCE PRODUCTS: Soko Pulse, Alama Score, and other      │
│     intelligence products don't feed back into the learning loop.   │
│     Market intelligence is produced but never used to improve       │
│     the models that produce it.                                     │
│                                                                     │
│  5. CROSS-WORKER LEARNING: Backend aggregates patterns but          │
│     doesn't synthesize "collective wisdom" — e.g., "workers in     │
│     Nairobi who sell mandazi also tend to sell chapati" patterns    │
│     are never extracted or distributed.                             │
│                                                                     │
│  6. CATASTROPHIC FORGETTING: No explicit mechanism to prevent       │
│     LoRA fine-tuning from overwriting general knowledge.            │
│     LearningHarness checks regression but doesn't apply EWC/       │
│     knowledge distillation during LoRA training.                    │
│                                                                     │
│  7. DRIFT DETECTION: CUSUM exists in CusumDriftTracker but isn't   │
│     connected to trigger retraining automatically.                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. The Flywheel Vision

### 2.1 The Dual Loop Architecture

```
                    ╔══════════════════════════════════════════╗
                    ║         THE FLYWHEEL                     ║
                    ║                                          ║
                    ║   USE → SMARTER → MORE USE → SMARTER     ║
                    ╚══════════════════════════════════════════╝

    ┌─────────────────────────────────────────────────────────────────┐
    │                                                                 │
    │  ┌──────────────────────┐       ┌──────────────────────┐       │
    │  │   ON-DEVICE LOOP     │       │   BACKEND LOOP       │       │
    │  │   (Personal)         │       │   (Collective)       │       │
    │  │                      │       │                      │       │
    │  │  Interaction         │       │  Aggregation         │       │
    │  │      ↓               │       │      ↓               │       │
    │  │  Signal Capture      │       │  FedAvg + DP         │       │
    │  │      ↓               │       │      ↓               │       │
    │  │  L3 LoRA Update      │───────│  Global Model        │       │
    │  │      ↓               │  ↑    │      ↓               │       │
    │  │  Personal Model      │  │    │  Intelligence        │       │
    │  │      ↓               │  │    │  Products            │       │
    │  │  Better Responses    │  │    │      ↓               │       │
    │  │      ↓               │  │    │  All Workers         │       │
    │  │  More Use ───────────│──│────│  Smarter             │       │
    │  │                      │  │    │      ↓               │       │
    │  └──────────────────────┘  │    │  More Data ──────────│───────┘
    │                            │    │                      │
    │                            │    └──────────────────────┘
    │                            │
    │         Encrypted          │
    │         Gradients          │
    │         (ε=0.1 DP)         │
    └────────────────────────────┘
```

### 2.2 The Three Levels of Learning

| Level | Mechanism | Latency | What Learns | Current Status |
|-------|-----------|---------|-------------|----------------|
| **L1: Rules** | Code-based intent parsing (SwahiliParser, IntentRouter) | 0ms | Nothing — static | ✅ Exists |
| **L2: Context** | Vocabulary injection, price suggestions, pattern context into LLM prompts | <50ms | User's products, prices, business patterns | ✅ Exists |
| **L3: LoRA** | On-device fine-tuning of adapter weights | ~30s training, 0ms inference | Phoneme patterns, correction patterns, behavioral adaptations | ⚠️ Training exists, loop not closed |

**The flywheel closes when L3 improvements flow back to the backend and then to all devices.**

---

## 3. On-Device Flywheel (Personal)

### 3.1 How Each Interaction Updates the L3 Behavioral Model

```
Worker speaks → ASR transcribes → Intent parsed → Action taken
     │                                              │
     │              ┌───────────────────────────────┘
     │              ↓
     │    Did the worker confirm? ──Yes──→ Strengthen vocabulary
     │              │                      Update Bayesian calibration
     │              No                      Record positive signal
     │              │
     │              ↓
     │    Did the worker correct? ──Yes──→ Record correction pair
     │              │                       Update vocabulary mapping
     │              No                       Trigger LearningHarness validation
     │              │                       Queue for LoRA training
     │              ↓
     │    Did the worker abandon? ──Yes──→ Record negative signal
     │              │                       Analyze failure pattern
     │              No
     │              ↓
     └─── Neutral signal (implicit positive — continued use)
```

### 3.2 Learning Triggers

| Trigger | Signal Type | Action | Minimum to Trigger LoRA |
|---------|-------------|--------|------------------------|
| User says "no, that was X not Y" | Explicit correction | Record correction pair, update vocabulary | 50 corrections |
| User confirms transcription | Positive reinforcement | Strengthen vocabulary confidence | N/A |
| User re-asks same question | Failure signal | Record failure pattern | 3 re-asks |
| User abandons session mid-flow | Negative signal | Analyze what went wrong | 5 abandonments |
| User completes task successfully | Positive signal | Reinforce response pattern | N/A |
| Price correction detected | Price learning | Update price range for item | 3 price observations |
| New product mentioned | Vocabulary expansion | Add to user vocabulary | Immediate (L2) |

### 3.3 LoRA Fine-Tuning On-Device (Existing Implementation Enhancement)

The existing `FederatedLearningClient.performLoRATraining()` implements:
- **Rank:** r=4 (only ~0.1% of parameters trained)
- **Memory:** ~50MB RAM on 2GB device
- **Learning rate:** η_t = η₀ / (1 + λ·t) (inverse decay)
- **Convergence:** t-test on loss differences (STA 342)
- **Early stopping:** patience = 3 epochs

**Enhancement needed — Catastrophic Forgetting Prevention:**

```kotlin
// NEW: Elastic Weight Consolidation (EWC) for LoRA training
// Prevents forgetting general knowledge while learning user-specific patterns

class EWCRegularizer(
    private val fisherInformation: FloatArray,  // Pre-computed Fisher information
    private val optimalWeights: FloatArray,     // Pre-trained weights
    private val lambda: Float = 0.4f            // Regularization strength
) {
    /**
     * Compute EWC penalty: λ/2 * Σ F_i * (θ_i - θ*_i)²
     * where F_i = Fisher information for parameter i
     *       θ*_i = optimal (pre-trained) value
     */
    fun penalty(currentWeights: FloatArray): Float {
        var loss = 0.0f
        for (i in currentWeights.indices) {
            val diff = currentWeights[i] - optimalWeights[i]
            loss += fisherInformation[i] * diff * diff
        }
        return lambda * 0.5f * loss
    }

    /**
     * Add EWC gradient to training gradient.
     * gradient += λ * F * (θ - θ*)
     */
    fun addEwcGradient(
        gradient: FloatArray,
        currentWeights: FloatArray
    ) {
        for (i in gradient.indices) {
            gradient[i] += lambda * fisherInformation[i] *
                (currentWeights[i] - optimalWeights[i])
        }
    }
}
```

**Integration point:** Modify `FederatedLearningClient.performLoRATraining()` to:
1. Load pre-computed Fisher information matrix (downloaded with global model)
2. Compute EWC penalty in each training step
3. Add EWC gradient to LoRA gradient before weight update

### 3.4 Learning Rate Scheduling (Already Implemented)

```
η_t = η₀ / (1 + λ·t)

where:
  η₀ = 0.001 (initial learning rate)
  λ  = 0.1   (decay rate)
  t  = epoch number
```

This ensures aggressive learning early (when the model knows nothing about the user) and gentle refinement later (when it's already good).

### 3.5 Personal Model Composition

```
w_final = w_base + w_global + α · w_user

where:
  w_base  = pre-trained model weights (frozen)
  w_global = aggregated global adapter from FL server
  w_user   = user's personal LoRA adapter
  α = min(1.0, corrections / 100)  — grows as user provides more feedback
```

For a new user (0 corrections): α = 0.1 → mostly global knowledge.
For an experienced user (100+ corrections): α = 1.0 → full personalization.

---

## 4. Backend Flywheel (Collective)

### 4.1 How Federated Learning Aggregates Patterns

```
    Device 1 (Nairobi, mandazi seller)  ──┐
    Device 2 (Mombasa, fish seller)     ──┤
    Device 3 (Kisumu, sukuma seller)    ──┼──→ FL Server
    Device 4 (Nakuru, milk seller)      ──┤
    Device 5 (Eldoret, maize seller)    ──┘
                                           │
                                    ┌──────┘
                                    ↓
                            FedAvg Aggregation
                            + DP Noise (ε=0.1)
                            + K-Anonymity (k≥5)
                                    │
                                    ↓
                            Global Model v3.2.N
                                    │
                            ┌───────┴───────┐
                            ↓               ↓
                    Calibration         LoRA Adapter
                    Parameters          (Weighted Avg)
                            │               │
                            └───────┬───────┘
                                    ↓
                            Push to All Devices
```

### 4.2 FedAvg Algorithm (Implemented in `federated_learning.py`)

```python
# Weighted Federated Averaging
Δw_global = Σ_k (n_k / n_total) · Δw_k

where:
  n_k = number of local training samples for device k
  n_total = Σ n_k
  Δw_k = clipped + noised gradient from device k
```

**What gets aggregated:**
1. **Calibration parameters** (temperature, Platt scaling) — weighted mean
2. **Phoneme confusion patterns** — frequency counts across devices
3. **LoRA adapter deltas** — element-wise weighted average
4. **Vocabulary statistics** — aggregated frequency/confidence

### 4.3 Differential Privacy (Already Implemented)

**Client-side (device):**
```
σ_client = Δf · √(2 · ln(1.25/δ)) / ε = 1.0 · √(2 · ln(1.25/1e-5)) / 0.1 ≈ 49.1
```

**Server-side (backend):**
```
Same σ applied to aggregated output before distribution.
Composed budget: ε_total = ε_client + ε_server = 0.1 + 0.1 = 0.2
```

**K-Anonymity (V2):** No aggregation until ≥5 devices in each (category, dialect) cohort.

### 4.4 Intelligence Products Feedback Loop

**This is the critical missing piece.** Intelligence products need to feed back:

```
┌─────────────────────────────────────────────────────────────────┐
│                INTELLIGENCE PRODUCT FLYWHEEL                     │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Soko     │    │ Alama    │    │ Biashara │    │ Market   │  │
│  │ Pulse    │    │ Score    │    │ Advisor  │    │ Forecast │  │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│       │               │               │               │         │
│       └───────────────┴───────┬───────┴───────────────┘         │
│                               │                                  │
│                               ↓                                  │
│                    ┌─────────────────────┐                       │
│                    │  Outcome Tracker    │                       │
│                    │  Did the worker     │                       │
│                    │  act on the advice? │                       │
│                    └──────────┬──────────┘                       │
│                               │                                  │
│                    ┌──────────┴──────────┐                       │
│                    │                     │                       │
│                    ↓                     ↓                       │
│              Positive Signal       Negative Signal               │
│              (reinforce model)     (update model)                │
│                    │                     │                       │
│                    └──────────┬──────────┘                       │
│                               │                                  │
│                               ↓                                  │
│                    Training Signal Buffer                         │
│                    → FL Aggregation                               │
│                    → Improved Models                              │
│                    → Better Intelligence Products                 │
│                    → More Workers Use Them                        │
│                    → MORE DATA → ↻                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation — New file: `services/intelligence_feedback.py`**

```python
class IntelligenceFeedbackCollector:
    """
    Collects outcome signals from intelligence products to close
    the flywheel loop. When a worker acts on Soko Pulse advice
    and succeeds, that's a positive signal. When they ignore it
    and fail, that's a negative signal.
    """

    async def track_advice_outcome(
        self,
        worker_id: str,
        product: str,          # "soko_pulse", "alama_score", etc.
        advice_given: str,
        advice_actioned: bool,
        outcome_positive: bool,
        context: dict[str, Any]
    ) -> AggregatedSignal:
        """Convert advice outcome into a training signal."""
        # Positive outcome from acting on advice → reinforce
        # Negative outcome from ignoring advice → also reinforce
        # Positive outcome from ignoring advice → model was wrong
        # Negative outcome from acting on advice → model was wrong

        signal_value = self._compute_signal(
            advice_actioned, outcome_positive
        )

        return AggregatedSignal(
            source=FeedbackSource.INTELLIGENCE_OUTCOME,
            outcome_value=signal_value,
            context_tags=[f"product:{product}", f"worker:{worker_id[:8]}"],
            # ...
        )

    def _compute_signal(self, actioned: bool, positive: bool) -> float:
        if actioned and positive:     return 0.9   # Good advice, followed
        if actioned and not positive:  return 0.1   # Bad advice, followed
        if not actioned and positive:  return 0.7   # Good outcome, model irrelevant
        if not actioned and not positive: return 0.5  # Neutral — can't attribute
```

### 4.5 Collective Intelligence Products

The backend should synthesize cross-worker patterns into **actionable collective intelligence**:

| Product | What It Learns | How It's Distributed |
|---------|---------------|---------------------|
| **Soko Pulse** | Market price trends aggregated from thousands of workers' transactions | Push to all workers in same region/product category |
| **Alama Score** | Business health patterns from high-performing workers | Suggest best practices to struggling workers |
| **Dialect Model** | Phoneme confusion patterns from all speakers of a dialect | Global LoRA adapter update |
| **Demand Forecast** | Seasonal patterns from aggregated transaction data | Push inventory recommendations |
| **Pricing Intelligence** | Optimal price points from successful transactions | Price suggestion updates |

---

## 5. The Connection: Device ↔ Backend Sync

### 5.1 Sync Protocol

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SYNC PROTOCOL                                   │
│                                                                      │
│  UPLOAD (Device → Backend):                                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Trigger: WiFi + charging + ≥50 new corrections since last sync│  │
│  │ Frequency: Weekly (or on-demand after LoRA training)           │  │
│  │ Payload:                                                        │  │
│  │   1. Anonymized correction patterns (JSON, ~5-20 KB)           │  │
│  │   2. LoRA weight deltas (encrypted, ~5-20 MB)                  │  │
│  │   3. Calibration parameters                                     │  │
│  │   4. Device metadata (tier, language, dialect)                  │  │
│  │ Privacy:                                                        │  │
│  │   - Device ID: SHA-256 hash with per-install salt              │  │
│  │   - Corrections: Hashed n-grams, phoneme patterns only         │  │
│  │   - LoRA deltas: Encrypted with hybrid PQC (X25519+ML-KEM)    │  │
│  │   - DP: ε=0.1 Gaussian noise on all numerical features        │  │
│  │   - Transport: TLS 1.3                                          │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  DOWNLOAD (Backend → Device):                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ Trigger: Version check shows newer model available             │  │
│  │ Frequency: Weekly check, download if version > local           │  │
│  │ Payload:                                                        │  │
│  │   1. Global LoRA adapter (aggregated, DP-noised)               │  │
│  │   2. Updated calibration parameters                             │  │
│  │   3. Vocabulary updates (top phoneme patterns)                 │  │
│  │   4. Fisher information matrix (for EWC regularization)       │  │
│  │ Apply:                                                          │  │
│  │   w_final = w_base + w_global + α · w_user                     │  │
│  │   α = min(1.0, user_corrections / 100)                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  VERSION CHECK (Lightweight):                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ GET /api/v1/federated/models/{dialect}/version                 │  │
│  │ Response: { update_available: true, latest_version: "v3.2.7" } │  │
│  │ Frequency: Daily (lightweight, <1KB)                            │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Sync State Machine (On-Device)

```
                    ┌──────┐
                    │ IDLE │ ←────────────────────────────────┐
                    └──┬───┘                                   │
                       │                                       │
            WiFi + charging + corrections ≥ 50?                │
                       │                                       │
                       ↓                                       │
                ┌──────────┐                                   │
                │PREPARING │                                   │
                │ Anonymize │                                   │
                │ + encrypt │                                   │
                └──┬───────┘                                   │
                   │                                           │
                   ↓                                           │
            ┌──────────┐      fail                             │
            │UPLOADING │ ──────────→ ERROR ──retry──→ IDLE     │
            └──┬───────┘                                       │
               │ success                                       │
               ↓                                               │
        ┌──────────────┐                                       │
        │ CHECK VERSION│                                       │
        └──┬───────────┘                                       │
           │ update available?                                  │
           │ yes                                                │
           ↓                                                    │
    ┌────────────┐                                              │
    │ DOWNLOADING│      fail                                    │
    │ Global     │ ──────────→ ERROR ──retry──→ IDLE            │
    └──┬─────────┘                                              │
       │ success                                                │
       ↓                                                        │
  ┌──────────┐                                                  │
  │ APPLYING │                                                  │
  │ w = b+g+u│                                                  │
  └──┬───────┘                                                  │
     │                                                          │
     ↓                                                          │
   IDLE ────────────────────────────────────────────────────────┘
```

### 5.3 Delta-Only Updates (Bandwidth Optimization)

Instead of downloading the full global adapter every time:

```kotlin
// Device stores: current_global_version = "v3.2.5"
// Server has:    latest_global_version = "v3.2.7"

// Option A: Download full adapter (current)
// Size: ~5-20 MB

// Option B: Download delta only (NEW)
// Size: ~100-500 KB
// Δ_global = w_global_v3.2.7 - w_global_v3.2.5
// Device applies: w_global += Δ_global

// Implementation:
data class FederatedDownloadDelta(
    val fromVersion: String,
    val toVersion: String,
    val deltaBytes: ByteArray,      // Only the difference
    val calibrationParams: CalibrationParams?,
    val fisherInformation: FloatArray?  // For EWC
)
```

---

## 6. Implementation Plan

### 6.1 Phase 1: Close the Loop (Weeks 1-2)

**Goal:** Make the existing FL upload/download actually work end-to-end.

| Task | File | Change |
|------|------|--------|
| Add retry logic to FL upload | `FederatedLearningClient.kt` | Add exponential backoff, max 3 retries, persist failed uploads |
| Add version check endpoint | `federated_learning.py` | `GET /api/v1/federated/models/{dialect}/version` — lightweight, returns `{update_available, latest_version}` |
| Wire AdaptiveLearningService to EventBus | `adaptive_learning.py` | Subscribe to `feedback.received`, `transaction.processed` events |
| Implement DataCollectorAgent.collect() | `training/loop.py` | Query training signals from interaction log |
| Add delta-only downloads | `FederatedLearningClient.kt` + `federated_learning.py` | Compute and transmit only adapter deltas between versions |

### 6.2 Phase 2: Prevent Catastrophic Forgetting (Weeks 3-4)

**Goal:** LoRA training improves personalization without losing general knowledge.

| Task | File | Change |
|------|------|--------|
| Implement EWC regularizer | New: `EWCRegularizer.kt` | Fisher information computation + gradient penalty |
| Integrate EWC into LoRA training | `FederatedLearningClient.kt` | Add EWC penalty to `computeLoRAGradient()` |
| Compute Fisher information on backend | `federated_learning.py` | Compute from aggregated gradients, distribute with global model |
| Add knowledge distillation loss | `FederatedLearningClient.kt` | KL divergence between base model and fine-tuned model outputs |

### 6.3 Phase 3: Intelligence Product Feedback (Weeks 5-6)

**Goal:** Soko Pulse, Alama Score, etc. feed back into the learning loop.

| Task | File | Change |
|------|------|--------|
| Create IntelligenceFeedbackCollector | New: `services/intelligence_feedback.py` | Track advice outcomes, generate training signals |
| Add outcome tracking to Soko Pulse | `services/econometric_engine.py` | Record whether workers acted on price advice |
| Add outcome tracking to Alama Score | `services/statistical/` | Record whether business health advice was followed |
| Wire feedback to AdaptiveLearningService | `adaptive_learning.py` | New event type: `intelligence.outcome.recorded` |

### 6.4 Phase 4: Collective Intelligence Synthesis (Weeks 7-8)

**Goal:** Extract and distribute cross-worker patterns.

| Task | File | Change |
|------|------|--------|
| Implement pattern synthesis | New: `services/collective_intelligence.py` | Mine cross-worker patterns (product associations, pricing, seasonal) |
| Add push notifications for insights | `federated_learning.py` | Include synthesized patterns in global model download |
| Create worker similarity clustering | `services/federated_learning.py` | Cluster workers by behavior, not just dialect |
| Implement demand forecasting feedback | `services/ml/model_trainer.py` | Use aggregated transaction data for demand model training |

### 6.5 Phase 5: Automated Training Loop (Weeks 9-12)

**Goal:** Wire the 8-agent training loop to real data.

| Task | File | Change |
|------|------|--------|
| Implement DataCollectorAgent | `training/loop.py` | Query interaction log, feedback store |
| Implement DataCuratorAgent | `training/loop.py` | Quality scoring, deduplication, adversarial detection |
| Implement ModelTrainerAgent | `training/loop.py` | Select training recipe, run training |
| Implement ModelEvaluatorAgent | `training/loop.py` | McNemar's test, paired t-test, resource measurement |
| Implement ExperimentRunnerAgent | `training/loop.py` | Multi-armed bandit, stratified randomization |
| Implement ModelDeployerAgent | `training/loop.py` | Staged rollout: 1% → 5% → 25% → 100% |
| Implement QualityMonitorAgent | `training/loop.py` | SPC charts, CUSUM drift detection |
| Connect CusumDriftTracker to retraining | `core/model/CusumDriftTracker.kt` | Emit event when drift detected → trigger training cycle |

---

## 7. Metrics & Measurement

### 7.1 How to Measure "Smarter"

| Metric | What It Measures | Target | How to Compute |
|--------|-----------------|--------|----------------|
| **Word Error Rate (WER)** | ASR accuracy for this worker | Decreasing over time | `incorrect_words / total_words` from confirmations |
| **Intent Accuracy** | Correct intent classification rate | ≥95% after 100 interactions | `correct_intents / total_intents` from corrections |
| **Correction Rate** | How often the worker corrects the agent | Decreasing over time | `corrections / interactions` |
| **Task Completion Rate** | Worker completes intended action | ≥90% | `completed_tasks / started_tasks` |
| **Vocabulary Coverage** | % of worker's words known to ASR | ≥80% after 1 month | `known_words / total_unique_words` |
| **Price Suggestion Accuracy** | Suggested price vs actual price | MAE < 10% | `|suggested - actual| / actual` |
| **Response Latency** | Time to useful response | <2s on-device | Median latency from interaction logs |
| **Worker Satisfaction** | Implicit satisfaction signal | Increasing | Session completion rate, return rate |

### 7.2 Flywheel Velocity Metrics

| Metric | What It Measures | Formula |
|--------|-----------------|---------|
| **Learning Rate** | How fast the model improves | `Δaccuracy / Δtime` (rolling 7-day window) |
| **Data Collection Rate** | How much training data flows in | `corrections_per_day` |
| **Model Freshness** | How current the global model is | `days_since_last_aggregation` |
| **Coverage Breadth** | How many workers contribute | `active_devices / total_devices` |
| **Privacy Budget Consumption** | How much DP budget is used | `Σ ε_consumed / ε_total` |

### 7.3 Dashboard Implementation

```kotlin
// Enhance LearningHarness.LearningDashboard with flywheel metrics
data class FlywheelDashboard(
    // Personal flywheel
    val personalAccuracy: Double,        // WER + intent accuracy
    val personalLearningRate: Double,     // Δaccuracy/week
    val vocabularySize: Int,
    val correctionRate: Double,           // corrections/interactions

    // Collective flywheel
    val globalModelVersion: String,
    val globalModelAge: Hours,
    val contributingDevices: Int,
    val aggregationRound: Int,

    // Privacy
    val privacyBudgetUsed: Double,        // ε consumed
    val privacyBudgetRemaining: Double,   // ε remaining

    // Intelligence products
    val sokoPulseAccuracy: Double,        // Price prediction accuracy
    val alamaScoreAccuracy: Double,       // Business health prediction
)
```

---

## 8. Model Drift Detection & Handling

### 8.1 Drift Types and Detection

| Drift Type | Detection Method | Implementation | Trigger |
|------------|-----------------|----------------|---------|
| **Data Drift** | KL divergence on input features | `CusumDriftTracker` (exists) | Input distribution changes >2σ |
| **Concept Drift** | Performance decay tracking | Rolling window accuracy comparison | Accuracy drops >5% over 7 days |
| **Vocabulary Drift** | New word frequency explosion | Track unknown word rate | Unknown words >20% of total |
| **Price Drift** | Price range violations | Track price deviations from learned range | Price >3σ from learned mean |

### 8.2 Automated Response

```
Drift Detected
     │
     ├── Data Drift → Trigger data collection increase
     │                 Increase FL upload frequency
     │
     ├── Concept Drift → Trigger retraining cycle
     │                    Roll back to last known good model
     │
     ├── Vocabulary Drift → Expand vocabulary learning
     │                       Lower ASR confidence threshold temporarily
     │
     └── Price Drift → Update price models
                       Alert worker if significant
```

### 8.3 CUSUM Integration (Existing Code Enhancement)

The `CusumDriftTracker` exists but isn't connected to retraining. Wire it:

```kotlin
// In CusumDriftTracker — add drift event emission
class CusumDriftTracker {
    // Existing code...

    fun checkDrift(metric: Double): DriftResult {
        // Existing CUSUM logic...

        if (driftDetected) {
            // NEW: Emit event for training loop
            eventBus.publish(DriftDetectedEvent(
                metricName = currentMetric,
                driftMagnitude = cusumValue,
                threshold = decisionThreshold,
                recommendedAction = when {
                    cusumValue > decisionThreshold * 2 -> "IMMEDIATE_RETRAIN"
                    cusumValue > decisionThreshold -> "SCHEDULE_RETRAIN"
                    else -> "MONITOR"
                }
            ))
        }
        return result
    }
}
```

---

## 9. A/B Testing Framework

### 9.1 What Gets A/B Tested

| Test | Baseline | Challenger | Primary Metric | Minimum Sample |
|------|----------|------------|----------------|----------------|
| **ASR Calibration** | Current threshold (0.60) | New threshold (0.55) | Calibration accuracy | 30 words per group |
| **LoRA vs No LoRA** | Base model only | Base + personal LoRA | Task completion rate | 50 interactions |
| **Global Model Version** | Current global adapter | New global adapter | WER | 100 words per group |
| **Context Injection** | No personalized context | With personalized context | Response quality rating | 20 interactions |
| **Vocabulary Strategy** | Default dictionary | User vocabulary priority | Intent accuracy | 50 intents |

### 9.2 Statistical Framework (Already Implemented in `LearningHarness`)

```
Design: Completely randomized, two treatments
Traffic split: 80% baseline, 20% challenger
Primary metric: Task completion rate
Secondary: Latency, user satisfaction

Significance: p < 0.05 (two-tailed)
Minimum sample: 20 interactions per group
Auto-promote: If challenger is significantly better
Auto-rollback: If challenger is significantly worse
```

### 9.3 Experiment Lifecycle

```
1. Create experiment (LearningHarness.startExperiment())
2. Route traffic (80/20 split)
3. Collect metrics (per-interaction quality scores)
4. Check significance (after min samples)
5. Declare winner (or inconclusive)
6. Promote winner to production
7. Monitor for 7 days post-promotion
8. Archive experiment results
```

---

## 10. Privacy Guarantees Summary

### 10.1 End-to-End Privacy Chain

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRIVACY GUARANTEES                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ON-DEVICE:                                                      │
│  ✅ Raw audio NEVER leaves the device                           │
│  ✅ Raw text NEVER leaves the device                            │
│  ✅ All learning happens in local Room database                 │
│  ✅ LoRA training uses only local correction data               │
│                                                                  │
│  IN TRANSIT:                                                     │
│  ✅ TLS 1.3 for all communications                              │
│  ✅ Hybrid PQC encryption (X25519 + ML-KEM-768)                 │
│  ✅ Gradient quantization to int8 (limits reconstruction)       │
│  ✅ Top-k compression (sparse upload)                           │
│                                                                  │
│  AT REST (Server):                                               │
│  ✅ Device IDs are one-way hashed (SHA-256 + per-install salt)  │
│  ✅ Corrections are hashed n-grams (no raw text)                │
│  ✅ Phoneme patterns only (which sounds confused, not words)    │
│                                                                  │
│  AGGREGATION:                                                    │
│  ✅ Differential privacy: ε=0.1 (strong guarantee)              │
│  ✅ K-anonymity: k≥5 (no aggregation with <5 devices)           │
│  ✅ Gradient clipping: L2 norm ≤ 1.0 (bounds sensitivity)       │
│  ✅ Gaussian noise: σ ≈ 49.1 (very noisy individual gradients)  │
│  ✅ Subsampling amplification: 1% participation rate            │
│                                                                  │
│  COMPOSITION:                                                    │
│  ✅ Client ε=0.1 + Server ε=0.1 = Total ε=0.2                  │
│  ✅ Per-round: ε_amp ≈ ln(1 + 0.01·(e^0.1 - 1)) ≈ 0.001      │
│  ✅ Over 100 rounds: ε_total ≈ 0.1 (basic composition)         │
│                                                                  │
│  CONSENT:                                                        │
│  ✅ Explicit FL consent required before any upload               │
│  ✅ User can opt out at any time                                │
│  ✅ Opting out deletes local training data                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Privacy Budget Tracking

```kotlin
// NEW: Privacy budget tracker
class PrivacyBudgetTracker(
    private val maxEpsilon: Double = 1.0,  // Total budget per user
    private val timeWindowDays: Int = 365   // Rolling window
) {
    private val consumptionLog = mutableListOf<EpsilonConsumption>()

    fun recordConsumption(epsilon: Double, operation: String, timestamp: Long) {
        consumptionLog.add(EpsilonConsumption(epsilon, operation, timestamp))
        // Prune old entries
        val cutoff = timestamp - timeWindowDays * 24 * 3600 * 1000
        consumptionLog.removeAll { it.timestamp < cutoff }
    }

    fun remainingBudget(): Double {
        val consumed = consumptionLog.sumOf { it.epsilon }
        return (maxEpsilon - consumed).coerceAtLeast(0.0)
    }

    fun canConsume(epsilon: Double): Boolean {
        return remainingBudget() >= epsilon
    }
}
```

---

## Appendix A: File Change Summary

### New Files to Create

| File | Purpose |
|------|---------|
| `msaidizi-app/.../EWCRegularizer.kt` | Elastic Weight Consolidation for LoRA training |
| `msaidizi-app/.../PrivacyBudgetTracker.kt` | Track ε consumption per user |
| `backend/services/intelligence_feedback.py` | Intelligence product outcome tracking |
| `backend/services/collective_intelligence.py` | Cross-worker pattern synthesis |
| `backend/services/fisher_information.py` | Compute Fisher information for EWC |

### Files to Modify

| File | Changes |
|------|---------|
| `FederatedLearningClient.kt` | Add retry logic, delta downloads, EWC integration, privacy budget tracking |
| `federated_learning.py` | Add version check endpoint, Fisher information distribution, delta computation |
| `adaptive_learning.py` | Subscribe to intelligence outcome events |
| `training/loop.py` | Implement all 8 agent `collect()`/`train()`/`evaluate()` methods |
| `CusumDriftTracker.kt` | Emit drift events to trigger retraining |
| `LearningHarness.kt` | Add flywheel velocity metrics to dashboard |

---

## Appendix B: The Flywheel Effect Over Time

```
Week 1-2:   100 corrections → Basic vocabulary → L2 personalization
Week 3-4:   300 corrections → LoRA training begins → L3 personalization
Week 5-8:   500 corrections → Reliable personal model → Fewer corrections
Week 9-12:  800 corrections → Global model improves → All workers benefit
Week 13+:   Global model + personal LoRA → Flywheel at full speed

The rate of improvement ACCELERATES because:
1. Each correction makes the model better → fewer future corrections needed
2. Fewer corrections means higher confidence → more aggressive learning
3. More workers contribute → better global model → better starting point for new users
4. Better global model → new users need fewer corrections to reach same quality
5. Intelligence products improve → workers trust them more → more data → ↻
```

---

*"The flywheel is the most important concept in business. Each turn builds on the previous one, and the cumulative effect is enormous."* — Jim Collins, Good to Great

*The Msaidizi flywheel turns with every voice note, every correction, every successful sale. The agent that listens best, learns fastest, and protects privacy most rigorously wins.*
