# Design: Backend Language Model Training for African Dialects
## Aggregate Learning from ALL Workers, Improve for Everyone

**Date:** 2026-07-14  
**Scope:** End-to-end design for collecting dialect data from Msaidizi workers, training/fine-tuning language models, and distributing improvements back to all devices.  
**Status:** Technical Design — Ready for Implementation

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Architecture Overview](#2-architecture-overview)
3. [Data Collection Pipeline](#3-data-collection-pipeline)
4. [Shared Dialect Dictionary Service](#4-shared-dialect-dictionary-service)
5. [Backend Training Pipeline](#5-backend-training-pipeline)
6. [Model Distribution & Deployment](#6-model-distribution--deployment)
7. [Quality Control & Adversarial Defense](#7-quality-control--adversarial-defense)
8. [Academic Foundations: Economics & Statistics](#8-academic-foundations-economics--statistics)
9. [Available Tools & Infrastructure](#9-available-tools--infrastructure)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Cost Estimates](#11-cost-estimates)
12. [Appendix: API Contracts](#12-appendix-api-contracts)

---

## 1. Current State Analysis

### 1.1 What Exists Today

The backend has a **solid federated learning scaffold** with two implementations:

| Component | Status | Key Details |
|-----------|--------|-------------|
| `FederatedLearningService` (v1) | ✅ Working | FedAvg, DP (ε=0.1), dialect clustering, quality validation |
| `FederatedLearningV2Service` | ✅ Working | K-anonymity (k≥5), multi-category data, tighter DP |
| `FederatedAggregator` (external) | ⚠️ Partial | Krum + Trimmed Mean, imports from `msaidizi-language-pipeline` |
| `FLPersistence` | ✅ Working | SQLite storage for updates, models, device info |
| `SelfEvolutionService` | ✅ Working | Feedback flywheel, keyword clustering, feature spec generation |
| `WorkerClassifier` | ✅ Working | 6 worker types, keyword + transaction pattern matching |
| PQC Encryption | ✅ Working | ML-KEM-768 + ML-DSA-65 for gradient transport |
| DialectAdapter (onboarding) | ⚠️ Unused | 10 dialect adapters defined but not wired to pipeline |

### 1.2 What's Missing

| Gap | Impact |
|-----|--------|
| **No dialect dictionary service** | Can't build shared vocabulary across workers |
| **No backend model training** | FedAvg aggregates LoRA deltas but never trains a base model |
| **No data annotation pipeline** | Correction patterns are anonymous hashes, not learnable text |
| **No model evaluation framework** | Can't measure if aggregated model actually improves |
| **No cross-dialect transfer learning** | Luo improvements don't help Luhya speakers |
| **No crowdsourced vocabulary building** | Phoneme patterns are ephemeral, not accumulated |

### 1.3 What the FL System Currently Collects

From `FLUpdate` schema (device → server):
```
- device_id: SHA-256 hash (anonymous)
- language: dialect code (sw, en, luo, kik, etc.)
- correction_patterns[]:
    - error_type: classification of the error
    - error_hash: SHA-256 of original text (NOT the text itself)
    - correction_hash: SHA-256 of corrected text
    - phoneme_pattern: phoneme substitution (e.g., "th→t")
    - edit_distance: normalized [0.0, 1.0]
    - hour_of_day: temporal signal
- adapter_deltas: base64-encoded LoRA weight changes (encrypted)
- calibration_params: temperature, Platt scaling, prior
- metadata: corrections_count, vocabulary_size, estimated_wer, device_tier
```

**Key insight:** The current system sends *hashed* text (not raw text), phoneme patterns, and LoRA deltas. This is privacy-safe but limits what the backend can learn — it can aggregate model weights but can't learn new vocabulary or language patterns from the raw corrections.

---

## 2. Architecture Overview

### 2.1 Design Philosophy

**"Aggregate from everyone, improve for everyone"** — the system learns dialect patterns from the collective behavior of all workers, without any single worker's raw data leaving their device.

### 2.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Msaidizi Android Devices                      │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Worker A │  │ Worker B │  │ Worker C │  │ Worker N │        │
│  │ (Luo)    │  │ (Kikuyu) │  │ (Swahili)│  │ (Kamba)  │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘        │
│       │              │              │              │              │
│  ┌────▼──────────────▼──────────────▼──────────────▼────┐        │
│  │          On-Device Processing (Privacy Layer)         │        │
│  │  • Speech recognition (local Whisper/QuartzNet)       │        │
│  │  • Correction capture (what worker said vs. heard)    │        │
│  │  • Anonymization (hash text, extract phoneme patterns)│        │
│  │  • LoRA fine-tuning (local adapter updates)           │        │
│  │  • Consent gate (opt-in required)                     │        │
│  └──────────────────────┬───────────────────────────────┘        │
│                         │                                        │
└─────────────────────────┼────────────────────────────────────────┘
                          │ Encrypted (ML-KEM-768 + AES-256-GCM)
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend Training Infrastructure               │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ FL API       │  │ Dialect      │  │ Vocabulary        │       │
│  │ Gateway      │──│ Dictionary   │──│ Aggregator        │       │
│  │ (existing)   │  │ Service (NEW)│  │ (NEW)             │       │
│  └──────┬───────┘  └──────────────┘  └──────────────────┘       │
│         │                                                        │
│  ┌──────▼───────────────────────────────────────────────┐       │
│  │              Aggregation Engine (Enhanced)             │       │
│  │  • FedAvg (existing) + FedProx + SCAFFOLD             │       │
│  │  • Cross-dialect transfer learning                    │       │
│  │  • Bayesian dialect confidence scoring                │       │
│  │  • Econometric quality filters                        │       │
│  └──────┬───────────────────────────────────────────────┘       │
│         │                                                        │
│  ┌──────▼───────────────────────────────────────────────┐       │
│  │              Model Training Pipeline (NEW)             │       │
│  │  • LoRA adapter merging across dialects               │       │
│  │  • Base model fine-tuning on aggregated vocabulary     │       │
│  │  • Evaluation suite (WER, BLEU, dialect accuracy)     │       │
│  │  • A/B testing framework                              │       │
│  └──────┬───────────────────────────────────────────────┘       │
│         │                                                        │
│  ┌──────▼───────────────────────────────────────────────┐       │
│  │              Model Registry & Distribution (NEW)       │       │
│  │  • Version management (semantic versioning)           │       │
│  │  • Delta compression for OTA updates                  │       │
│  │  • Staged rollout (canary → 10% → 50% → 100%)       │       │
│  │  • Rollback on quality regression                     │       │
│  └───────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                          │
                          │ OTA Model Download
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Updated Devices                               │
│  • New LoRA adapter weights                                    │
│  • Updated vocabulary/dialect dictionary                        │
│  • Calibration parameters                                       │
│  • Language detection model improvements                        │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Data Flow Summary

```
Worker speaks → Device transcribes → Worker corrects →
Device extracts patterns (privacy-safe) → Encrypts →
Backend aggregates across all workers → Trains improved model →
Evaluates quality → Deploys to all devices → Everyone benefits
```

---

## 3. Data Collection Pipeline

### 3.1 What to Collect (Privacy-Preserving)

The current FL system collects **hashed corrections** and **LoRA deltas**. We extend this with **privacy-safe aggregated signals**:

#### Tier 1: Already Collected (No Changes)
- Phoneme substitution patterns (e.g., "th→t", "r→l")
- Edit distance distributions
- Error type classifications
- LoRA adapter weight deltas
- Calibration parameters

#### Tier 2: New Collection (Privacy-Safe)
```python
class DialectContribution(BaseModel):
    """New data type: anonymized dialect learning signals."""

    # Vocabulary signals (aggregated, not raw text)
    word_frequency_distribution: Dict[str, int]  # {hashed_word: count}
    phoneme_inventory: List[str]  # Phonemes the worker uses
    tone_patterns: List[float]  # Pitch contour statistics (no audio)

    # Grammar signals (structural, not content)
    sentence_length_distribution: Dict[str, float]  # mean, std, median
    word_order_patterns: List[str]  # e.g., "SVO", "SOV" tendencies
    code_switching_frequency: float  # How often they mix languages

    # Dialect confidence signals
    self_reported_dialect: str  # What dialect they claim to speak
    regional_dialect_markers: List[str]  # Region-specific patterns
    formality_level: float  # Formal vs informal speech patterns
```

#### Tier 3: Opt-In Rich Data (Requires Explicit Consent)
```python
class RichDialectData(BaseModel):
    """Opt-in: richer data for dialect research."""

    # Only with explicit "Help improve Msaidizi for your language" consent
    anonymized_text_corrections: List[Dict[str, str]]
    # {original_hash, corrected_text_snippet} — snippets, not full sentences
    # Snippets are ≤5 words, randomly sampled, PII-stripped

    dialect_vocabulary_contributions: List[Dict[str, str]]
    # {word_in_dialect, standard_swahili_equivalent}
    # Workers actively contribute dialect → standard mappings
```

### 3.2 Collection Architecture

```python
# New service: app/services/dialect_collector.py

class DialectCollector:
    """
    Collects and aggregates dialect data from devices.

    Three-tier collection:
    1. Automatic (FL updates) — already happening
    2. Passive (usage patterns) — collected via existing APIs
    3. Active (crowdsourced contributions) — opt-in vocabulary building
    """

    async def process_fl_update(self, update: FLUpdate) -> None:
        """Extract dialect signals from existing FL updates."""
        # Already happening — enhance with vocabulary extraction
        dialect = update.language
        for pattern in update.correction_patterns:
            await self._record_phoneme_pattern(dialect, pattern.phoneme_pattern)
            await self._record_error_type(dialect, pattern.error_type)

    async def record_usage_pattern(self, worker_id: str, interaction: Dict) -> None:
        """Record anonymized usage patterns for dialect learning."""
        # From WhatsApp interactions (language, response patterns)
        pass

    async def accept_vocabulary_contribution(
        self, worker_id: str, dialect: str, contributions: List[Dict]
    ) -> None:
        """Accept crowdsourced dialect vocabulary."""
        # Workers voluntarily contribute dialect words
        pass
```

### 3.3 Privacy Guarantees

| Data Type | What Leaves Device | What Backend Sees | Privacy Level |
|-----------|-------------------|-------------------|---------------|
| Correction patterns | Hashed text, phoneme patterns | Aggregated statistics | 🔒 Full anonymity |
| LoRA deltas | Encrypted weight changes | Aggregated model weights | 🔒 Encrypted |
| Vocabulary | Hashed word frequencies | Global frequency distributions | 🔒 k-anonymity |
| Usage patterns | Aggregated session stats | Cohort-level patterns | 🔒 Differential privacy |
| Text corrections | Short snippets (opt-in, PII-stripped) | Learnable text fragments | ⚠️ Requires consent |

**Key principle:** The backend NEVER sees a full sentence from any worker. At most, it sees 5-word snippets that the worker explicitly chose to share.

---

## 4. Shared Dialect Dictionary Service

### 4.1 Problem

Currently, each device maintains its own vocabulary. There's no shared dialect dictionary that aggregates knowledge from all workers. A Luo speaker in Kisumu who corrects "atapata" → "atopata" doesn't help other Luo speakers.

### 4.2 Design: Crowdsourced Dialect Dictionary

```python
# New service: app/services/dialect_dictionary.py

@dataclass
class DialectEntry:
    """A single entry in the dialect dictionary."""
    word: str                    # The dialect word
    standard_equivalent: str     # Standard Swahili equivalent
    dialect: str                 # Which dialect (luo, kik, kal, etc.)
    phonetic_transcription: str  # IPA or simplified phonetic
    usage_examples: List[str]    # Hashed usage examples
    confidence: float            # Bayesian confidence [0, 1]
    contributor_count: int       # How many workers contributed
    region_geohash: str          # Geographic signal (coarse)
    category: str                # noun, verb, adjective, phrase
    frequency_rank: int          # How common in this dialect
    first_seen: datetime         # When first contributed
    last_updated: datetime       # Most recent contribution


class DialectDictionaryService:
    """
    Crowdsourced dialect dictionary that learns from all workers.

    Aggregation strategy:
    1. Workers contribute dialect ↔ standard word pairs (opt-in)
    2. Backend validates against multiple contributors
    3. Bayesian confidence scoring (more contributors = higher confidence)
    4. Dictionary entries flow back to all devices in that dialect
    5. Cross-dialect mapping enables transfer learning

    The dictionary is the SHARED KNOWLEDGE that makes everyone's
    experience better — one worker's correction helps all speakers
    of that dialect.
    """

    def __init__(self, db_session):
        self.db = db_session
        self.min_contributors = 3  # Minimum for inclusion
        self.confidence_threshold = 0.7  # Minimum confidence for distribution

    async def contribute(
        self,
        worker_id_hash: str,
        dialect: str,
        word: str,
        standard_equivalent: str,
        category: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Accept a dialect vocabulary contribution from a worker.

        Steps:
        1. Validate inputs (word length, dialect code, etc.)
        2. Check for existing entry (same word + dialect)
        3. If exists: increment contributor count, update confidence
        4. If new: create entry with confidence = 1/min_contributors
        5. Check if confidence threshold met for distribution
        """
        pass

    async def get_dialect_vocabulary(
        self, dialect: str, min_confidence: float = 0.7
    ) -> List[DialectEntry]:
        """Get all validated vocabulary for a dialect."""
        pass

    async def get_cross_dialect_mappings(
        self, word: str
    ) -> Dict[str, str]:
        """Get how a word maps across dialects."""
        pass

    async def aggregate_from_fl_updates(
        self, updates: List[FLUpdate]
    ) -> None:
        """
        Extract vocabulary from FL correction patterns.

        Even though individual corrections are hashed, we can:
        1. Count phoneme patterns across many workers
        2. Identify systematic substitutions (e.g., "th→t" in Luo)
        3. Build phoneme confusion matrices per dialect
        4. Infer vocabulary patterns from edit distance distributions
        """
        pass
```

### 4.3 Dictionary Schema (Database)

```sql
CREATE TABLE dialect_dictionary (
    id SERIAL PRIMARY KEY,
    word VARCHAR(100) NOT NULL,
    standard_equivalent VARCHAR(100) NOT NULL,
    dialect VARCHAR(10) NOT NULL,
    phonetic_ipa VARCHAR(100),
    category VARCHAR(20),  -- noun, verb, adjective, phrase, idiom
    confidence FLOAT DEFAULT 0.0,
    contributor_count INT DEFAULT 1,
    region_geohash VARCHAR(6),
    frequency_rank INT,
    is_validated BOOLEAN DEFAULT FALSE,
    first_seen TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(word, dialect, standard_equivalent)
);

CREATE TABLE dialect_contributions (
    id SERIAL PRIMARY KEY,
    entry_id INT REFERENCES dialect_dictionary(id),
    worker_id_hash VARCHAR(64) NOT NULL,
    contribution_type VARCHAR(20),  -- new_word, correction, validation
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE phoneme_confusion_matrix (
    id SERIAL PRIMARY KEY,
    dialect VARCHAR(10) NOT NULL,
    source_phoneme VARCHAR(10) NOT NULL,
    target_phoneme VARCHAR(10) NOT NULL,
    frequency INT DEFAULT 0,
    confidence FLOAT DEFAULT 0.0,
    UNIQUE(dialect, source_phoneme, target_phoneme)
);
```

### 4.4 How Dictionary Feeds into Model Training

```
Dialect Dictionary entries →
  ├── Vocabulary expansion for ASR model (new words to recognize)
  ├── Phoneme confusion matrix → pronunciation model improvement
  ├── Cross-dialect mappings → transfer learning training data
  ├── Frequency data → language model prior probabilities
  └── Regional variation → geographic dialect models
```

---

## 5. Backend Training Pipeline

### 5.1 What We're Training

The backend doesn't train a base LLM from scratch. Instead, it:

1. **Aggregates LoRA adapters** from devices (existing FedAvg)
2. **Merges adapters** into improved global adapters (new)
3. **Fine-tunes vocabulary** using dialect dictionary (new)
4. **Calibrates confidence** using Bayesian methods (new)
5. **Evaluates and deploys** improved models (new)

### 5.2 Training Pipeline Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 Backend Training Pipeline                 │
│                                                          │
│  Phase 1: Data Aggregation (existing + enhanced)         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ FL Updates from Devices                          │    │
│  │   ↓                                              │    │
│  │ Quality Filter (z-test, ε=0.1 DP)               │    │
│  │   ↓                                              │    │
│  │ Dialect Clustering (K-means on phoneme patterns) │    │
│  │   ↓                                              │    │
│  │ K-Anonymity Check (k≥5 per dialect)              │    │
│  │   ↓                                              │    │
│  │ FedAvg Aggregation (weighted by data size)       │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  Phase 2: Adapter Merging (NEW)                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Per-Dialect Aggregated LoRA Adapters             │    │
│  │   ↓                                              │    │
│  │ Cross-Dialect Transfer (shared patterns)         │    │
│  │   ↓                                              │    │
│  │ Adapter Merging (TIES-MERGE or DARE)             │    │
│  │   ↓                                              │    │
│  │ Merged Global Adapter                            │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  Phase 3: Vocabulary Training (NEW)                      │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Dialect Dictionary Entries                       │    │
│  │   ↓                                              │    │
│  │ Phoneme Confusion Matrices                       │    │
│  │   ↓                                              │    │
│  │ Tokenizer Extension (add dialect tokens)         │    │
│  │   ↓                                              │    │
│  │ Language Model Vocabulary Update                 │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  Phase 4: Evaluation (NEW)                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Held-out Test Set per Dialect                    │    │
│  │   ↓                                              │    │
│  │ WER (Word Error Rate) Measurement                │    │
│  │   ↓                                              │    │
│  │ BLEU Score for Generation Quality                │    │
│  │   ↓                                              │    │
│  │ Dialect Classification Accuracy                  │    │
│  │   ↓                                              │    │
│  │ A/B Test: New Model vs Current Model             │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  Phase 5: Deployment (NEW)                               │
│  ┌─────────────────────────────────────────────────┐    │
│  │ Model Registry (versioned)                       │    │
│  │   ↓                                              │    │
│  │ Canary Deployment (5% of devices)                │    │
│  │   ↓                                              │    │
│  │ Quality Monitoring (error rate, user feedback)   │    │
│  │   ↓                                              │    │
│  │ Gradual Rollout (10% → 50% → 100%)              │    │
│  │   ↓                                              │    │
│  │ OTA Model Distribution                           │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 5.3 LoRA Adapter Merging (Phase 2 Detail)

When multiple devices send LoRA adapter deltas for the same dialect, we need to merge them intelligently.

```python
# New: app/services/adapter_merger.py

class AdapterMerger:
    """
    Merges LoRA adapters from multiple devices and dialects.

    Methods:
    1. Simple FedAvg (existing) — weighted average of deltas
    2. TIES-MERGE — trim, elect sign, disjoint merge
    3. DARE — drop and rescale for delta merging
    4. Cross-dialect transfer — share common patterns across dialects
    """

    def merge_dialect_adapters(
        self,
        dialect: str,
        adapter_updates: List[Tuple[bytes, float]],  # (delta_bytes, weight)
        method: str = "fedavg",
    ) -> bytes:
        """
        Merge LoRA adapters for a single dialect.

        Args:
            dialect: Target dialect code
            adapter_updates: List of (adapter_delta_bytes, sample_weight)
            method: Merge method ("fedavg", "ties", "dare")

        Returns:
            Merged adapter delta bytes
        """
        if method == "fedavg":
            return self._fedavg_merge(adapter_updates)
        elif method == "ties":
            return self._ties_merge(adapter_updates)
        elif method == "dare":
            return self._dare_merge(adapter_updates)

    def cross_dialect_transfer(
        self,
        dialect_adapters: Dict[str, bytes],  # {dialect: adapter_bytes}
        shared_patterns: Dict[str, List[str]],  # {pattern_type: [phonemes]}
    ) -> Dict[str, bytes]:
        """
        Transfer common patterns across dialects.

        If 5 dialects all show "th→t" confusion, that pattern
        should be strengthened in all of them, not just the ones
        with enough data individually.

        Uses the linguistic principle: shared phonological rules
        across Bantu languages can be transferred.
        """
        pass

    def _ties_merge(
        self, updates: List[Tuple[bytes, float]]
    ) -> bytes:
        """
        TIES-Merging (Yu et al., 2023):
        1. Trim: Remove small-magnitude changes (noise)
        2. Elect sign: Take majority sign for each parameter
        3. Disjoint merge: Average only parameters that agree on sign

        Better than FedAvg when devices have divergent updates.
        """
        pass

    def _dare_merge(
        self, updates: List[Tuple[bytes, float]]
    ) -> bytes:
        """
        DARE (Zeng et al., 2024):
        1. Randomly drop delta parameters (set to 0)
        2. Rescale remaining by 1/(1-p) where p is drop rate
        3. Merge rescaled deltas

        Reduces interference between different devices' updates.
        """
        pass
```

### 5.4 Base Model Fine-Tuning (Phase 3 Detail)

Beyond LoRA aggregation, we periodically fine-tune the base model on aggregated dialect data.

```python
# New: app/services/model_trainer.py

class DialectModelTrainer:
    """
    Fine-tunes the base language model on aggregated dialect data.

    This is NOT done on-device — it runs on the backend server
    with access to aggregated, anonymized data from all workers.

    Training schedule: Weekly or when sufficient new data accumulates.
    """

    def __init__(
        self,
        base_model: str = "Qwen/Qwen3-8B",  # Upgrade from Qwen2.5
        output_dir: str = "models/dialect/",
    ):
        self.base_model = base_model
        self.output_dir = output_dir

    async def prepare_training_data(
        self,
        dialect: str,
        dictionary_entries: List[DialectEntry],
        phoneme_matrices: Dict[str, Any],
        fl_aggregated_patterns: List[Dict],
    ) -> Dataset:
        """
        Prepare training data from aggregated dialect sources.

        Sources:
        1. Dialect dictionary entries → (dialect_word, standard_equivalent) pairs
        2. Phoneme confusion matrices → pronunciation training data
        3. FL correction patterns → error correction training pairs
        4. Cross-dialect mappings → translation training pairs

        All data is aggregated and anonymized — no individual
        worker's text is used directly.
        """
        pass

    async def train_lora_adapter(
        self,
        dialect: str,
        training_data: Dataset,
        config: TrainingConfig,
    ) -> str:
        """
        Train a LoRA adapter for a specific dialect.

        Uses PEFT (Parameter-Efficient Fine-Tuning) with LoRA:
        - Rank: 16 (balance between quality and size)
        - Alpha: 32
        - Target modules: q_proj, v_proj (attention layers)
        - Epochs: 3-5 (depends on data size)
        - Learning rate: 2e-4 with cosine schedule

        Returns path to trained adapter.
        """
        pass

    async def extend_tokenizer(
        self,
        dialect: str,
        new_tokens: List[str],
    ) -> str:
        """
        Extend the base model's tokenizer with dialect-specific tokens.

        Adds new tokens from the dialect dictionary that aren't
        in the base vocabulary. This improves tokenization quality
        for dialect words (fewer subword splits = better understanding).

        Returns path to updated tokenizer.
        """
        pass


@dataclass
class TrainingConfig:
    """Configuration for dialect model training."""
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: ["q_proj", "v_proj"])
    num_epochs: int = 3
    learning_rate: float = 2e-4
    batch_size: int = 8
    gradient_accumulation_steps: int = 4
    warmup_ratio: float = 0.1
    max_seq_length: int = 512
    fp16: bool = True
    gradient_checkpointing: bool = True
```

### 5.5 Cross-Dialect Transfer Learning

A key insight: **African Bantu languages share deep structural similarities**. Luo (Nilotic) is different from Kikuyu (Bantu), but both share the East African linguistic context.

```python
class CrossDialectTransfer:
    """
    Transfer learning across dialects.

    Strategy:
    1. Identify shared phonological patterns across dialects
    2. Train a "base African" adapter on shared patterns
    3. Fine-tune per-dialect adapters on dialect-specific patterns
    4. Combine: base_adapter + dialect_adapter = final model

    Academic basis:
    - Bantu languages share noun class systems, verb serialization
    - East African languages share loanword patterns (Arabic, English)
    - Code-switching patterns are similar across urban dialects
    """

    def identify_shared_patterns(
        self,
        dialect_data: Dict[str, List[DialectEntry]],
    ) -> Dict[str, float]:
        """
        Find patterns that appear across multiple dialects.

        If "th→t" appears in Luo, Kikuyu, and Kamba with high
        frequency, it's a shared East African pattern that can
        be transferred to other dialects with less data.
        """
        pass

    def train_base_adapter(
        self,
        shared_patterns: Dict[str, Any],
        all_dialect_data: Dict[str, Dataset],
    ) -> bytes:
        """
        Train a base adapter on shared patterns across all dialects.

        This adapter captures universal East African phonological
        patterns and serves as the starting point for dialect-specific
        adapters.
        """
        pass

    def compose_final_adapter(
        self,
        base_adapter: bytes,
        dialect_adapter: bytes,
        base_weight: float = 0.3,
    ) -> bytes:
        """
        Compose base + dialect adapters.

        final = base_weight * base_adapter + (1 - base_weight) * dialect_adapter

        The base weight controls how much shared knowledge vs
        dialect-specific knowledge is used.
        """
        pass
```

---

## 6. Model Distribution & Deployment

### 6.1 Model Registry

```python
# New: app/services/model_registry.py

class ModelRegistry:
    """
    Versioned model registry with staged rollout.

    Models are versioned semantically:
    - Major: Base model change (e.g., Qwen2.5 → Qwen3)
    - Minor: New dialect or significant training improvement
    - Patch: Incremental update from FL aggregation

    Rollout stages:
    1. canary (5% of devices) — catch catastrophic failures
    2. early (10%) — broader testing
    3. half (50%) — statistical significance for A/B testing
    4. full (100%) — general availability
    """

    async def register_model(
        self,
        dialect: str,
        adapter_path: str,
        vocabulary_path: str,
        calibration_params: Dict,
        training_metadata: Dict,
    ) -> str:
        """Register a new model version."""
        pass

    async def get_latest_for_device(
        self,
        dialect: str,
        device_id: str,
    ) -> Optional[ModelArtifact]:
        """
        Get the appropriate model version for a device.

        Respects staged rollout: different devices may get
        different versions based on their rollout group.
        """
        pass

    async def advance_rollout(
        self,
        model_version: str,
        target_stage: str,
    ) -> bool:
        """Advance a model to the next rollout stage."""
        pass

    async def rollback(
        self,
        model_version: str,
        reason: str,
    ) -> bool:
        """Rollback a model to the previous version."""
        pass
```

### 6.2 OTA Model Distribution

```
Device polls: GET /api/v1/fl/check-version/{dialect}
  ↓
If update_available:
  Device requests: GET /api/v1/fl/global-model/{dialect}
  ↓
Server returns:
  - LoRA adapter deltas (base64, gzip-compressed)
  - Vocabulary updates (new words + frequencies)
  - Calibration parameters
  - Version metadata
  ↓
Device applies:
  - Merges new LoRA adapter with existing
  - Updates local vocabulary
  - Recalibrates confidence thresholds
  - Reports success/failure back to server
```

### 6.3 Delta Compression

For bandwidth efficiency, send only the **diff** between the device's current model and the new model:

```python
class DeltaCompressor:
    """Compress model updates as deltas for OTA transfer."""

    def compute_delta(
        self,
        current_adapter: bytes,
        new_adapter: bytes,
    ) -> bytes:
        """
        Compute delta between two adapters.

        Only sends the difference, not the full adapter.
        Typical savings: 60-80% bandwidth reduction.
        """
        pass

    def apply_delta(
        self,
        current_adapter: bytes,
        delta: bytes,
    ) -> bytes:
        """Apply a delta to reconstruct the new adapter."""
        pass
```

---

## 7. Quality Control & Adversarial Defense

### 7.1 Data Quality Pipeline

```python
class QualityController:
    """
    Multi-layer quality control for federated learning data.

    Layers:
    1. Syntactic validation (schema, types, ranges)
    2. Statistical validation (hypothesis tests, outlier detection)
    3. Behavioral validation (device reputation, history)
    4. Adversarial detection (Byzantine-resilient aggregation)
    """

    def validate_update(self, update: FLUpdate) -> QualityReport:
        """
        Run all quality checks on an incoming update.

        Returns QualityReport with:
        - overall_score: float [0, 1]
        - passed_checks: List[str]
        - failed_checks: List[str]
        - risk_flags: List[str]
        - recommendation: "accept" | "accept_low_weight" | "reject"
        """
        pass
```

### 7.2 Byzantine-Robust Aggregation

To handle adversarial or corrupted updates:

```python
class ByzantineRobustAggregator:
    """
    Aggregation methods resilient to adversarial updates.

    Methods:
    1. Krum — Select the update closest to its neighbors
    2. Trimmed Mean — Remove top/bottom percentile, average remainder
    3. Median — Coordinate-wise median across updates
    4. Bulyan — Krum + Trimmed Mean combination

    References:
    - Blanchard et al. (2017) "Machine Learning with Adversaries"
    - Yin et al. (2018) "Byzantine-Robust Distributed Learning"
    """

    def aggregate(
        self,
        updates: List[FLUpdate],
        method: str = "trimmed_mean",
        trim_fraction: float = 0.1,
    ) -> FLUpdate:
        """
        Aggregate updates with Byzantine resilience.

        trimmed_mean: Remove top/bottom 10% of updates by norm,
        then average. This eliminates both adversarial outliers
        and low-quality updates.
        """
        pass
```

### 7.3 Adversarial Input Detection

```python
class AdversarialDetector:
    """
    Detect adversarial or gaming attempts in FL updates.

    Red flags:
    1. Update norms far from cohort mean (>3σ)
    2. Contradictory patterns (e.g., all corrections go the wrong way)
    3. Sybil attacks (same patterns from many "different" devices)
    4. Data poisoning (systematic bias in one direction)
    5. Free-rider attacks (updates that don't change from baseline)
    """

    def detect_sybil_attack(
        self,
        updates: List[FLUpdate],
    ) -> List[str]:
        """
        Detect groups of devices sending identical/similar updates.

        Uses clustering on update feature vectors. If >5 devices
        send nearly identical updates, flag as potential Sybil.
        """
        pass

    def detect_data_poisoning(
        self,
        updates: List[FLUpdate],
        historical_baseline: Dict,
    ) -> List[str]:
        """
        Detect systematic bias injection.

        If all updates from a region push calibration parameters
        in the opposite direction from historical trend, flag.
        """
        pass
```

---

## 8. Academic Foundations: Economics & Statistics

### 8.1 Econometric Models for Dialect Classification

Valentine's economics background provides powerful tools for dialect analysis:

```python
class EconometricDialectClassifier:
    """
    Use econometric methods for dialect classification.

    Inspired by how economists classify markets, we classify dialects:

    1. Discrete Choice Model (McFadden, 1974):
       - Workers "choose" dialect features based on utility
       - P(dialect=k | features) = exp(β_k · X) / Σ exp(β_j · X)
       - Multinomial logit for dialect probability

    2. Hedonic Pricing Model (Rosen, 1974):
       - Dialect "price" = how much it deviates from standard
       - Each phoneme feature contributes to the "price"
       - Workers in different regions pay different "prices"

    3. Instrumental Variables:
       - Use geographic distance as instrument for dialect similarity
       - Control for migration patterns (workers moving between regions)
    """

    def classify_dialect_multinomial(
        self,
        phoneme_features: Dict[str, float],
        region_features: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Multinomial logit for dialect classification.

        Returns probability distribution over dialects.
        """
        pass

    def estimate_dialect_distance(
        self,
        dialect_a_features: Dict[str, float],
        dialect_b_features: Dict[str, float],
    ) -> float:
        """
        Estimate linguistic distance between dialects.

        Uses hedonic decomposition: distance = Σ β_i · |feature_diff_i|
        """
        pass
```

### 8.2 Statistical Sampling for Quality Control

```python
class SamplingQualityControl:
    """
    Use statistical sampling theory for efficient quality control.

    Instead of checking every update (expensive), sample and
    make inference about the full batch:

    1. Stratified Sampling:
       - Stratify by dialect, device tier, region
       - Ensure each stratum is represented
       - Reduces variance of quality estimates

    2. Sequential Testing (SPRT):
       - Wald's Sequential Probability Ratio Test
       - Accept/reject batches as evidence accumulates
       - More efficient than fixed-sample tests

    3. Bootstrap Confidence Intervals:
       - Estimate quality metric uncertainty
       - Wide CI → need more data before aggregation
       - Narrow CI → confident in quality
    """

    def stratified_quality_sample(
        self,
        updates: List[FLUpdate],
        strata: Dict[str, List[str]],  # {stratum_name: [device_ids]}
        sample_fraction: float = 0.1,
    ) -> List[FLUpdate]:
        """
        Stratified random sample for quality checking.
        """
        pass

    def sequential_quality_test(
        self,
        sampled_updates: List[FLUpdate],
        null_hypothesis_quality: float = 0.5,
        alpha: float = 0.05,
        beta: float = 0.1,
    ) -> Dict[str, Any]:
        """
        Wald's SPRT for batch quality decision.

        H0: Quality ≤ null_hypothesis (reject batch)
        H1: Quality > null_hypothesis (accept batch)

        Returns: accept/reject/continue_sampling
        """
        pass
```

### 8.3 Bayesian Models for Dialect Detection Confidence

```python
class BayesianDialectDetector:
    """
    Bayesian inference for dialect detection with uncertainty.

    Instead of point estimates, we maintain posterior distributions
    over dialect assignments. This gives us:
    1. Confidence intervals on dialect classification
    2. Ability to incorporate prior knowledge (region, worker type)
    3. Natural handling of code-switching (mixture of dialects)

    Model:
        P(dialect=k | observations) ∝ P(obs | dialect=k) · P(dialect=k)

    Prior: P(dialect=k) based on regional demographics
    Likelihood: P(obs | dialect=k) from phoneme patterns
    """

    def update_dialect_posterior(
        self,
        prior: Dict[str, float],  # {dialect: probability}
        phoneme_observations: List[str],
        observation_reliability: float = 0.9,
    ) -> Dict[str, float]:
        """
        Bayesian update of dialect probabilities.

        Each phoneme observation shifts the posterior.
        More reliable observations have larger effect.
        """
        pass

    def estimate_dialect_mixing(
        self,
        observations: List[str],
    ) -> Dict[str, float]:
        """
        Estimate code-switching: worker uses multiple dialects.

        Returns mixing proportions (e.g., 70% Luo, 30% Swahili).
        Uses Dirichlet-Multinomial model.
        """
        pass
```

### 8.4 Selection Bias Handling

A critical concern: **workers who contribute FL data are not representative of all workers**.

```python
class SelectionBiasCorrector:
    """
    Correct for selection bias in dialect data.

    Sources of bias:
    1. Self-selection: Only opted-in workers contribute
    2. Survivorship: Active workers contribute more than churned
    3. Geographic: Urban workers have better connectivity
    4. Device: Higher-end devices run FL more reliably
    5. Language: Workers comfortable with tech contribute more

    Correction methods (from econometrics):
    1. Inverse Probability Weighting (IPW)
    2. Heckman Selection Model
    3. Propensity Score Matching
    """

    def compute_ipw_weights(
        self,
        contributors: List[Dict],  # Worker profiles of contributors
        all_workers: List[Dict],   # Worker profiles of everyone
    ) -> Dict[str, float]:
        """
        Inverse Probability Weighting.

        Weight each contributor by 1/P(contributing | characteristics).
        This upweights contributors who are similar to non-contributors,
        making the aggregated data more representative.
        """
        pass

    def heckman_correction(
        self,
        observed_data: List[Dict],
        selection_covariates: List[str],
    ) -> Dict[str, Any]:
        """
        Heckman two-step correction for selection bias.

        Step 1: Probit model for participation decision
        Step 2: Correct outcome equation for selection

        Returns bias-corrected estimates.
        """
        pass
```

### 8.5 How Valentine's Economics Background Helps

| Economics Concept | Application to Dialect Training |
|---|---|
| **Market design** | Design incentive structures for workers to contribute dialect data |
| **Auction theory** | Optimal pricing for data bounties (pay workers for contributions) |
| **Game theory** | Detect strategic behavior (workers gaming contribution rewards) |
| **Causal inference** | Separate correlation from causation in dialect patterns |
| **Panel data methods** | Track how dialect patterns evolve over time per worker |
| **Regression discontinuity** | Quality thresholds for model deployment decisions |
| **Difference-in-differences** | Measure impact of model updates on dialect recognition accuracy |

---

## 9. Available Tools & Infrastructure

### 9.1 Training Frameworks

| Framework | Use Case | License | Notes |
|-----------|----------|---------|-------|
| **PEFT (HuggingFace)** | LoRA fine-tuning | Apache 2.0 | Industry standard for adapter training |
| **TRL (HuggingFace)** | RLHF, DPO training | Apache 2.0 | For preference-based optimization |
| **DeepSpeed** | Distributed training | MIT | ZeRO optimization for large models |
| **Axolotl** | Fine-tuning workflows | Apache 2.0 | Simplified config-driven training |
| **LLaMA-Factory** | Multi-model fine-tuning | Apache 2.0 | Supports Qwen, LLaMA, Mistral |
| **vLLM** | Efficient inference | Apache 2.0 | For serving models during evaluation |

### 9.2 Cloud Infrastructure

| Provider | Service | Use Case | Cost Estimate |
|----------|---------|----------|---------------|
| **Oracle Cloud** | A10 GPU instances | LoRA training | ~$1.50/GPU-hour |
| **AWS** | SageMaker | Training pipeline | ~$1.20/GPU-hour |
| **GCP** | Vertex AI | AutoML + training | ~$1.10/GPU-hour |
| **Lambda Labs** | GPU cloud | Cost-effective training | ~$0.80/GPU-hour |
| **RunPod** | Serverless GPU | Burst training | ~$0.40/GPU-hour |
| **Modal** | Serverless compute | Event-driven training | Pay-per-second |

**Recommendation:** Start with **RunPod or Lambda Labs** for cost-effective GPU access. Move to Oracle Cloud (already used by Angavu) for production.

### 9.3 African Language Datasets

| Dataset | Languages | Size | Source |
|---------|-----------|------|--------|
| **Masakhane** | 30+ African languages | Large | Community-driven |
| **AfriQA** | 10 African languages | Medium | Question answering |
| **MADAR** | Arabic dialects (for methodology) | Large | Dialect identification |
| **NLLB-SC2** | 200+ languages | Very Large | Meta |
| **Common Voice** | Swahili + others | Large | Mozilla, crowdsourced |
| **OpenSLR** | Swahili speech | Medium | Community |
| **FLORES-200** | 200 languages | Medium | Translation benchmark |
| **XL-Sum** | Swahili + others | Medium | BBC summarization |

### 9.4 Data Annotation Tools

| Tool | Use Case | Cost |
|------|----------|------|
| **Label Studio** | Multi-modal annotation | Free (open source) |
| **Prodigy** | NLP annotation | $490/license |
| **Argilla** | LLM feedback annotation | Free (open source) |
| **Doccano** | Text classification | Free (open source) |

**Recommendation:** Use **Argilla** — it's designed for LLM feedback and supports crowdsourced annotation natively.

### 9.5 Model Evaluation Tools

| Tool | What It Measures | Use Case |
|------|-----------------|----------|
| **lm-evaluation-harness** | Perplexity, benchmarks | Base model quality |
| **sacrebleu** | BLEU scores | Translation quality |
| **jiwer** | Word Error Rate | ASR quality |
| **langdetect/fasttext** | Language detection accuracy | Dialect classification |
| **rouge-score** | ROUGE scores | Summarization quality |
| **comet** | Translation quality (neural) | Cross-dialect translation |

---

## 10. Implementation Roadmap

### Phase 0: Foundation (Week 1-2)

**Goal:** Set up infrastructure and data pipelines.

```
Week 1:
├── Set up GPU training environment (RunPod/Lambda)
├── Install PEFT, TRL, DeepSpeed
├── Create dialect_dictionary table in PostgreSQL
├── Create model_registry table
└── Extend FL persistence schema for new data types

Week 2:
├── Implement DialectDictionaryService (basic CRUD)
├── Implement DialectCollector (Tier 1: from FL updates)
├── Add vocabulary contribution endpoint to FL API
├── Create evaluation dataset (held-out test set per dialect)
└── Set up Argilla for annotation
```

### Phase 1: Data Collection (Week 3-4)

**Goal:** Start collecting richer dialect data from devices.

```
Week 3:
├── Deploy vocabulary contribution API endpoint
├── Update Android app with "Contribute to dialect dictionary" feature
├── Implement phoneme confusion matrix aggregation
├── Add DialectContribution schema to FL updates
└── Start collecting Tier 2 data (usage patterns)

Week 4:
├── Implement quality control pipeline (statistical validation)
├── Implement adversarial detection (basic Sybil detection)
├── Build cross-dialect mapping from dictionary entries
├── Create training data preparation pipeline
└── First batch of dialect dictionary entries (from existing FL data)
```

### Phase 2: Training Pipeline (Week 5-8)

**Goal:** Build and run the first model training.

```
Week 5:
├── Implement AdapterMerger (FedAvg + TIES-MERGE)
├── Implement DialectModelTrainer (LoRA fine-tuning)
├── Implement tokenizer extension for dialect tokens
├── First training run: Swahili dialect (most data)
└── Evaluate: WER, BLEU, dialect accuracy

Week 6:
├── Implement cross-dialect transfer learning
├── Train adapters for Luo, Kikuyu (second most data)
├── Implement Bayesian dialect detector
├── Implement econometric dialect classifier
└── Compare: new models vs existing models

Week 7:
├── Implement ModelRegistry with staged rollout
├── Implement DeltaCompressor for OTA
├── Implement canary deployment system
├── Deploy first model update (Swahili, canary 5%)
└── Monitor quality metrics

Week 8:
├── A/B testing framework
├── Rollback mechanism
├── Expand to all 9 dialects
├── Full evaluation suite
└── Documentation and runbooks
```

### Phase 3: Full Production (Week 9-12)

**Goal:** Continuous learning loop fully operational.

```
Week 9-10:
├── Automated training pipeline (weekly retraining)
├── Selection bias correction (IPW)
├── Advanced adversarial defense (Bulyan aggregation)
├── Model performance dashboard
└── Worker-facing "Your dialect is improving!" feedback

Week 11-12:
├── Cross-dialect transfer in production
├── Dialect dictionary public API (for other apps)
├── Research paper: "Federated Dialect Learning in East Africa"
├── Scaling optimization (batch training, model distillation)
└── Cost optimization (spot instances, model quantization)
```

---

## 11. Cost Estimates

### 11.1 Training Costs (Monthly)

| Item | Specification | Cost/Month |
|------|--------------|------------|
| GPU Training (LoRA) | 1× A100, 8h/week | ~$200 |
| GPU Inference (eval) | 1× A10, 24h eval runs | ~$100 |
| Storage (models + data) | 100GB SSD | ~$10 |
| PostgreSQL (dialect dict) | Managed DB | ~$50 |
| Argilla (annotation) | Self-hosted | $0 |
| Monitoring (W&B) | Free tier | $0 |
| **Total** | | **~$360/month** |

### 11.2 Scaling Costs

| Scale | Devices | Dialects | Training Freq | Est. Cost/Month |
|-------|---------|----------|---------------|-----------------|
| Current | ~100 | 9 | Weekly | ~$360 |
| Growth | 1,000 | 9 | 2x/week | ~$600 |
| Scale | 10,000 | 15 | Daily | ~$2,000 |
| Large | 100,000 | 20 | Daily | ~$8,000 |

### 11.3 Cost Optimization Strategies

1. **Spot instances** for training (60-70% savings)
2. **Model quantization** (INT8/INT4) for inference
3. **Delta compression** for OTA (60-80% bandwidth savings)
4. **Training on CPU** for small adapters (LoRA rank ≤ 8)
5. **Caching** frequent model requests
6. **Scheduled training** during off-peak hours

---

## 12. Appendix: API Contracts

### 12.1 New Endpoints

#### Dialect Dictionary Contribution
```
POST /api/v1/dialect/contribute
Authorization: Bearer <token>

{
    "dialect": "luo",
    "contributions": [
        {
            "word": "atopata",
            "standard_equivalent": "atapata",
            "category": "verb",
            "context": "future tense correction"
        },
        {
            "word": "nyathi",
            "standard_equivalent": "mtoto",
            "category": "noun",
            "context": "child"
        }
    ]
}

Response:
{
    "status": "accepted",
    "contributions_accepted": 2,
    "contributions_duplicate": 0,
    "total_contributions_this_dialect": 156,
    "your_contribution_rank": 12
}
```

#### Get Dialect Dictionary
```
GET /api/v1/dialect/dictionary/{dialect}?min_confidence=0.7&limit=100
Authorization: Bearer <token>

Response:
{
    "dialect": "luo",
    "total_entries": 156,
    "validated_entries": 89,
    "entries": [
        {
            "word": "atopata",
            "standard_equivalent": "atapata",
            "category": "verb",
            "confidence": 0.92,
            "contributor_count": 8,
            "region": "Kisumu"
        }
    ]
}
```

#### Training Status
```
GET /api/v1/training/status
Authorization: Bearer <token>

Response:
{
    "last_training_run": "2026-07-14T08:00:00Z",
    "current_model_versions": {
        "sw": "v3.2.15",
        "luo": "v3.2.8",
        "kik": "v3.2.5"
    },
    "next_scheduled_training": "2026-07-21T08:00:00Z",
    "training_data_stats": {
        "total_contributions": 2340,
        "dialects_with_data": 7,
        "avg_confidence": 0.78
    },
    "model_quality": {
        "sw": {"wer": 0.12, "dialect_accuracy": 0.89},
        "luo": {"wer": 0.18, "dialect_accuracy": 0.82},
        "kik": {"wer": 0.21, "dialect_accuracy": 0.76}
    }
}
```

#### Model Rollout Status
```
GET /api/v1/training/rollout/{dialect}
Authorization: Bearer <token>

Response:
{
    "dialect": "luo",
    "current_version": "v3.2.8",
    "rollout_stage": "half",
    "rollout_percentage": 50,
    "canary_metrics": {
        "error_rate": 0.02,
        "avg_confidence": 0.85,
        "user_feedback_positive": 0.91
    },
    "decision": "proceed_to_full",
    "auto_advance_at": "2026-07-16T08:00:00Z"
}
```

### 12.2 Android Client Changes Required

The Android app needs these additions:

1. **Dialect contribution UI** — "Help improve Msaidizi for your language" screen
2. **Vocabulary contribution** — Select dialect words and their standard equivalents
3. **Rich FL data** — Send Tier 2 signals (usage patterns, code-switching frequency)
4. **Model update handler** — Apply vocabulary updates alongside LoRA deltas
5. **Feedback on model quality** — "Did Msaidizi understand you correctly?" after interactions

---

## Summary

This design transforms Msaidizi's federated learning from a **weight aggregation system** into a **full dialect learning platform**:

| Before | After |
|--------|-------|
| Aggregates LoRA deltas only | Trains improved models on aggregated data |
| No shared vocabulary | Crowdsourced dialect dictionary |
| No quality evaluation | Multi-metric evaluation suite |
| Deploy latest model blindly | Staged rollout with A/B testing |
| Each dialect learns independently | Cross-dialect transfer learning |
| No adversarial defense | Byzantine-robust aggregation |
| No selection bias handling | Econometric correction methods |

**The key innovation:** Every worker who speaks Luo in Kisumu makes Msaidizi better for ALL Luo speakers — not just on their device, but across the entire system. This is the "aggregate from everyone, improve for everyone" principle in action.
