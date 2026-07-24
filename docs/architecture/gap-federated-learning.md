# Msaidizi — Federated Learning Architecture

> **Version:** 0.1.0 · **Date:** 2026-07-24  
> **Status:** Design Draft  
> **Target:** On-device personalization + global model improvement for 2 GB RAM phones

---

## 1. Design Philosophy

Msaidizi's learning system follows a simple principle: **the device teaches itself, the cloud helps everyone.**

- **Personal learning stays personal.** A worker's voice patterns, vocabulary, and business context never leave their phone.
- **Global learning benefits everyone.** Anonymized, privacy-protected gradients aggregate into a stronger base model for all workers.
- **The phone is the classroom.** All training happens on-device during idle moments — charging, WiFi-connected, screen off.
- **Privacy is non-negotiable.** Differential privacy, k-anonymity, and post-quantum encryption are defaults, not options.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        DEVICE LAYER                         │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Base Model   │  │ Personal     │  │  Local Training  │  │
│  │  (frozen)     │  │ LoRA (r=8)  │  │  Engine          │  │
│  │  ~400MB       │  │ ~5-10MB      │  │  (idle-time)     │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘  │
│         │                 │                    │            │
│         └────────┬────────┘                    │            │
│                  ▼                             ▼            │
│         ┌──────────────┐            ┌──────────────────┐    │
│         │  Inference    │            │  Gradient        │    │
│         │  (base+LoRA)  │            │  Generator       │    │
│         └──────────────┘            └────────┬─────────┘    │
│                                              │              │
│                                    ┌─────────▼───────────┐  │
│                                    │  Privacy Engine     │  │
│                                    │  (DP + k-anon)      │  │
│                                    └─────────┬───────────┘  │
│                                              │              │
└──────────────────────────────────────────────┼──────────────┘
                                               │
                                    PQC-encrypted gradients
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────┐
│                       CLOUD LAYER                           │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Gradient     │  │  FedAvg      │  │  Model Registry  │  │
│  │  Collector    │──│  Aggregator  │──│  & Distributor   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Per-Dialect Federation Coordinator                  │   │
│  │  (Swahili · Kikuyu · Luo · Kamba · Kalenjin · …)    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Device-Level Learning

### 3.1 Personal LoRA Adapter

Each worker's phone maintains a **personal LoRA adapter** that captures individual patterns:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Rank (r) | 8 | Balance between expressiveness and memory (~5-10 MB) |
| Target layers | Attention Q/K/V + FFN up/down | Maximum personalization with minimal parameters |
| Precision | INT4 quantized (on disk) / INT8 (during training) | Fits in 2 GB RAM alongside base model |
| Storage | `/data/local/msaidizi/lora_personal/` | Persists across app updates |

**What the personal LoRA learns:**

- **Voice patterns:** Accent, speaking speed, common filler words, pronunciation quirks
- **Vocabulary:** Domain-specific terms (e.g., "mjengo" for construction workers, "mshahara" patterns)
- **Business patterns:** Frequently queried products, typical transaction amounts, time-of-day patterns
- **Interaction preferences:** How the worker phrases commands, preferred response length, language mixing patterns (code-switching between Swahili/English)
- **Dialect markers:** Regional word choices, tonal patterns, idiomatic expressions

### 3.2 On-Device Training Engine

Training runs **exclusively during idle time** to avoid impacting the worker's experience:

```python
# Pseudocode: Idle-time training trigger
class DeviceTrainer:
    
    IDLE_THRESHOLD_SEC = 300      # 5 min idle before training starts
    CHARGING_REQUIRED = True       # Only train while charging
    WIFI_REQUIRED = True           # Only on WiFi (saves data)
    MAX_TRAIN_MINUTES = 15         # Cap per session
    LEARNING_RATE = 1e-4
    BATCH_SIZE = 4                 # Tiny batch for 2GB RAM
    GRADIENT_ACCUMULATION_STEPS = 8 # Effective batch = 32
    
    def should_train(self) -> bool:
        return (
            self.is_idle(self.IDLE_THRESHOLD_SEC)
            and self.is_charging()
            and self.is_wifi_connected()
            and self.has_training_data()
            and not self.is_thermal_throttled()
        )
    
    def train_step(self, batch):
        """Single training step on-device."""
        # Forward pass through base model + personal LoRA
        outputs = self.model(batch.input_ids, adapter="personal")
        loss = self.compute_loss(outputs, batch.labels)
        
        # Backward pass — only LoRA parameters are trainable
        loss.backward()
        
        # Gradient accumulation (save memory)
        if self.step % self.GRADIENT_ACCUMULATION_STEPS == 0:
            self.optimizer.step()
            self.optimizer.zero_grad()
        
        return loss.item()
```

**Memory management for 2 GB devices:**

```
Total RAM budget:                    2048 MB
─────────────────────────────────────────────
OS + system services:                 512 MB
Base model (INT4, loaded):            250 MB
Personal LoRA (INT8, training):        10 MB
Optimizer states (Adam, 2x LoRA):      20 MB
Activation memory (batch=4):           50 MB
Training data buffer:                  50 MB
App + UI overhead:                    200 MB
─────────────────────────────────────────────
Total allocated:                     1092 MB
Free buffer:                          956 MB  ← headroom for OS
```

**Training data collection (on-device only):**

Every interaction becomes a training example — but stays local:

```python
class LocalTrainingBuffer:
    """Ring buffer of training examples. Never leaves the device."""
    
    MAX_EXAMPLES = 500  # ~500 examples, ~2MB storage
    
    def add_interaction(self, user_input, model_output, feedback_signal):
        """
        feedback_signal:
          - explicit: user said "yes/no/good/bad"
          - implicit: user repeated request (bad), continued conversation (good),
                      edited response (neutral), used response directly (good)
        """
        example = {
            "input": user_input,
            "output": model_output,
            "reward": self.compute_reward(feedback_signal),
            "timestamp": now(),
            "dialect_tag": self.detect_dialect(user_input),
        }
        self.buffer.append(example)
        self.prune_old_examples()
```

### 3.3 Inference with Personal LoRA

At inference time, the base model and personal LoRA are combined:

```
Final output = BaseModel(x) + PersonalLoRA(x)
```

The personal LoRA is a lightweight additive layer — it doesn't replace the base model's knowledge, it **specializes** it. A construction worker's phone learns to recognize "simiti" (cement) instantly, while a mama mboga's phone learns produce-related vocabulary.

---

## 4. Global Aggregation

### 4.1 Gradient Preparation (Device-Side)

Before any data leaves the phone, it goes through rigorous preparation:

```python
class GradientGenerator:
    """Converts local training into privacy-protected gradients."""
    
    def compute_gradients(self) -> Optional[GradientPayload]:
        """
        Steps:
        1. Compute gradient of personal LoRA on recent training data
        2. Clip gradient norm (max_norm=1.0)
        3. Add calibrated Gaussian noise (differential privacy)
        4. Verify k-anonymity threshold is met
        5. Encrypt with PQC
        6. Return encrypted gradient payload
        """
        if not self.meets_k_anonymity_threshold():
            return None  # Not enough similar workers — skip this round
        
        gradient = self.model.compute_gradient(self.training_buffer)
        gradient = self.clip_gradient(gradient, max_norm=1.0)
        gradient = self.add_dp_noise(gradient, epsilon=0.1, delta=1e-5)
        
        payload = GradientPayload(
            dialect=self.worker_dialect,
            region=self.worker_region,      # coarse region, not GPS
            gradient=gradient,
            metadata=self.build_metadata(),
            timestamp=now(),
        )
        
        return self.encrypt_pqc(payload)
```

### 4.2 What Leaves the Device

**Only these items are transmitted:**

| Item | Description | Privacy Level |
|------|-------------|---------------|
| Gradient tensor | DP-noised, clipped LoRA weight deltas | ε=0.1, δ=1e-5 |
| Dialect tag | e.g., "swahili-coastal" | Coarse, self-reported |
| Region code | e.g., "KE-01" (county level) | Coarse geographic |
| Round ID | Which federation round | No PII |
| Device class | RAM tier (2GB/3GB/4GB) | No device fingerprint |

**Never transmitted:**

- Raw audio recordings
- Transcribed text
- Contact lists
- GPS coordinates
- Phone numbers
- Business transaction details
- Personal LoRA weights (stays on device)

### 4.3 Global LoRA Adapter

The aggregated global LoRA uses **higher rank** to capture cross-worker patterns:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Rank (r) | 16 | More capacity for population-level patterns |
| Target layers | Same as personal (Q/K/V + FFN) | Consistent architecture |
| Precision | FP16 (server) / INT4 (distributed) | Quality during aggregation, size for delivery |
| Size | ~20-40 MB | Acceptable for OTA delivery |

**What the global LoRA learns:**

- Common Swahili business vocabulary across all workers
- Shared product naming conventions
- Typical query patterns ("How much is…", "Do you have…")
- Common pronunciation patterns for ASR improvement
- Cross-worker correction patterns (what outputs get good feedback universally)

---

## 5. Privacy Guarantees

### 5.1 Differential Privacy

We use **Rényi Differential Privacy (RDP)** for tighter composition across rounds:

```
Per-round privacy budget:
  ε = 0.1 (very strong privacy)
  δ = 1e-5 (less than 1 in 100,000 chance of any individual's contribution being detectable)

Noise mechanism: Gaussian
  σ = sensitivity × √(2 ln(1.25/δ)) / ε
  
Gradient clipping:
  max_norm = 1.0 (L2 norm clipping per worker)
  
Composition over rounds:
  After R rounds: ε_total ≈ ε × √(2R × ln(1/δ))  [RDP accounting]
  At 100 rounds: ε_total ≈ 0.1 × √(200 × 11.5) ≈ 4.8
  (Still within acceptable bounds for practical DP)
```

**Adaptive noise calibration:**

```python
class DifferentialPrivacyEngine:
    
    def __init__(self, epsilon=0.1, delta=1e-5, max_norm=1.0):
        self.epsilon = epsilon
        self.delta = delta
        self.max_norm = max_norm
        self.sigma = self._compute_sigma()
        self.rounds_used = 0
        self.privacy_budget_used = 0.0
    
    def _compute_sigma(self) -> float:
        """Gaussian noise scale for (ε, δ)-DP."""
        return self.max_norm * math.sqrt(2 * math.log(1.25 / self.delta)) / self.epsilon
    
    def add_noise(self, gradient: Tensor) -> Tensor:
        """Add calibrated Gaussian noise to gradient."""
        noise = torch.randn_like(gradient) * self.sigma
        self.rounds_used += 1
        self.privacy_budget_used = self._compute_rdp_budget()
        return gradient + noise
    
    def budget_remaining(self) -> float:
        """Check if worker can still participate in federation."""
        MAX_BUDGET = 10.0  # Total ε budget per worker per month
        return MAX_BUDGET - self.privacy_budget_used
```

### 5.2 k-Anonymity

A worker's gradients are **only submitted** when at least `k=5` similar workers exist in the same batch:

```python
class KAnonymityGuard:
    """Ensures no individual can be isolated from a group."""
    
    MIN_GROUP_SIZE = 5  # k=5
    
    def can_submit(self, worker_profile: WorkerProfile, current_round: RoundInfo) -> bool:
        """
        Check if enough similar workers exist in this round.
        Similarity defined by: dialect + region + device_class
        """
        similar_workers = self.count_similar_workers(
            dialect=worker_profile.dialect,
            region=worker_profile.region,
            device_class=worker_profile.device_class,
            round_id=current_round.id,
        )
        return similar_workers >= self.MIN_GROUP_SIZE
    
    def count_similar_workers(self, **kwargs) -> int:
        """
        Server-side count (via secure aggregation protocol).
        The server knows how many workers match, but not who they are.
        Uses Private Set Intersection (PSI) to count without revealing identities.
        """
        return self.psi_count(kwargs)
```

**When k-anonymity is not met:**

- The worker's gradients are **held locally** until a future round has enough similar participants
- The worker is notified: "Your model improvements will be shared when more similar users join"
- This is **not** a degradation — the personal LoRA still works fine locally

### 5.3 Post-Quantum Encryption (ML-KEM-768)

All gradient transport uses **ML-KEM-768** (formerly CRYSTALS-Kyber, NIST PQC standard):

```python
class PQCEncryption:
    """Post-quantum encryption for gradient transport."""
    
    ALGORITHM = "ML-KEM-768"  # NIST FIPS 203
    KEY_SIZE = 768 bits
    CIPHERTEXT_SIZE = 1088 bytes
    SHARED_SECRET = 32 bytes
    
    def encrypt_gradients(self, gradient_bytes: bytes, server_public_key: bytes) -> bytes:
        """
        Hybrid encryption:
        1. ML-KEM-768 key encapsulation → shared secret
        2. AES-256-GCM with shared secret → encrypted gradient
        3. Return: KEM ciphertext + AES-GCM ciphertext + tag
        """
        shared_secret, kem_ciphertext = ml_kem.encapsulate(server_public_key)
        
        aes_key = self.derive_key(shared_secret)  # HKDF
        nonce = os.urandom(12)
        aes_ciphertext, tag = aes_gcm_encrypt(aes_key, nonce, gradient_bytes)
        
        return kem_ciphertext + nonce + tag + aes_ciphertext
```

**Key rotation:**

- Server keypair rotated weekly
- Old public keys remain valid for 48 hours (grace period for offline devices)
- Device-side: ephemeral keypair per submission (forward secrecy)

### 5.4 Privacy Summary

```
┌─────────────────────────────────────────────────────────┐
│                 PRIVACY GUARANTEE STACK                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Layer 1: DATA MINIMIZATION                            │
│  └─ Only gradients leave device. Never raw data.       │
│                                                         │
│  Layer 2: DIFFERENTIAL PRIVACY (ε=0.1, δ=1e-5)        │
│  └─ Noise calibrated so individual contribution        │
│     is statistically undetectable.                     │
│                                                         │
│  Layer 3: k-ANONYMITY (k=5)                           │
│  └─ Gradients only submitted when ≥5 similar           │
│     workers exist. No one stands alone.                │
│                                                         │
│  Layer 4: SECURE AGGREGATION                           │
│  └─ Server aggregates without seeing individual        │
│     gradients. Sum is computed in encrypted form.      │
│                                                         │
│  Layer 5: POST-QUANTUM ENCRYPTION (ML-KEM-768)        │
│  └─ Transport encrypted with NIST PQC standard.        │
│     Quantum-resistant.                                  │
│                                                         │
│  Layer 6: LOCAL DIFFERENTIAL PRIVACY                   │
│  └─ Noise added BEFORE data leaves device.             │
│     Server never sees clean gradients.                 │
│                                                         │
│  Layer 7: OPT-OUT                                      │
│  └─ Worker can disable federation at any time.         │
│     Personal LoRA still works. Just no global sync.    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Per-Dialect Federation

### 6.1 Dialect Structure

Each dialect forms its own **federation group** with independent aggregation:

```
Federation Groups
├── swahili-standard     (Standard Swahili — Nairobi, formal)
├── swahili-coastal      (Mombasa, Lamu — Kiamu influence)
├── swahili-bongo        (Tanzania Swahili)
├── kikuyu               (Central Kenya)
├── luo                   (Nyanza region)
├── kamba                 (Eastern Kenya)
├── kalenjin              (Rift Valley)
├── meru                  (Meru/Tharaka)
├── luhya                 (Western Kenya)
└── cross-dialect         (Shared patterns — see §6.3)
```

### 6.2 Per-Dialect Aggregation

Each dialect group runs **independent federation rounds:**

```python
class DialectFederationRound:
    """One round of federated learning for a specific dialect."""
    
    def __init__(self, dialect: str, round_id: int):
        self.dialect = dialect
        self.round_id = round_id
        self.min_participants = 10   # Minimum for a valid round
        self.target_participants = 50 # Ideal round size
        self.timeout_hours = 48       # Max wait for participants
    
    async def run(self):
        # 1. Advertise round to eligible devices
        eligible = self.get_eligible_devices(self.dialect)
        self.broadcast_round_invitation(eligible)
        
        # 2. Collect encrypted gradients (with timeout)
        gradients = await self.collect_gradients(
            min_count=self.min_participants,
            target_count=self.target_participants,
            timeout_hours=self.timeout_hours,
        )
        
        if len(gradients) < self.min_participants:
            logger.warning(f"Round {self.round_id} for {self.dialect}: "
                         f"only {len(gradients)} participants, need {self.min_participants}. "
                         f"Deferring.")
            return None
        
        # 3. Secure aggregation (server never sees individual gradients)
        aggregated = self.secure_aggregate(gradients)
        
        # 4. Update global LoRA for this dialect
        new_global_lora = self.apply_aggregated_gradient(
            current_global_lora=self.load_global_lora(self.dialect),
            aggregated_gradient=aggregated,
            learning_rate=0.1,  # Conservative update
        )
        
        # 5. Evaluate before deploying
        if self.evaluate_model(new_global_lora) > self.evaluate_model(self.current_global_lora):
            self.distribute_update(self.dialect, new_global_lora)
            return new_global_lora
        else:
            logger.info(f"Round {self.round_id} for {self.dialect}: "
                       f"evaluation failed, skipping update.")
            return None
```

### 6.3 Cross-Dialect Transfer Learning

Shared linguistic patterns are extracted and applied across dialects:

```python
class CrossDialectTransfer:
    """
    Learns shared patterns across dialects without exposing
    dialect-specific data to other groups.
    """
    
    def extract_shared_features(self, dialect_global_loras: dict) -> Tensor:
        """
        Uses Federated Multi-Task Learning (FMTL):
        1. Each dialect's global LoRA is decomposed into shared + dialect-specific
        2. Shared components are averaged across dialects
        3. Dialect-specific components are preserved
        
        Shared features include:
        - Base Swahili grammar patterns
        - Number/time expressions
        - Greeting formulas
        - Business transaction structures
        - Code-switching patterns (Swahili-English)
        """
        shared_components = []
        for dialect, lora in dialect_global_loras.items():
            # Decompose: W = W_shared + W_dialect
            W_shared, W_dialect = self.decompose(lora)
            shared_components.append(W_shared)
        
        # Average shared components
        W_cross_dialect = torch.stack(shared_components).mean(dim=0)
        return W_cross_dialect
    
    def decompose(self, lora_weights: Tensor) -> Tuple[Tensor, Tensor]:
        """
        SVD-based decomposition:
        - Top singular vectors → shared (cross-dialect)
        - Remaining → dialect-specific
        """
        U, S, V = torch.svd(lora_weights)
        
        # Keep top-k components as shared (k=rank//2)
        k = lora_weights.shape[0] // 2
        W_shared = U[:, :k] @ torch.diag(S[:k]) @ V[:, :k].T
        W_dialect = lora_weights - W_shared
        
        return W_shared, W_dialect
```

### 6.4 Federation Round Schedule

```
Weekly Federation Calendar (all times UTC+3 / EAT)
═══════════════════════════════════════════════════

Monday     02:00-06:00  swahili-standard round
Tuesday    02:00-06:00  swahili-coastal round
Wednesday  02:00-06:00  kikuyu round
Thursday   02:00-06:00  luo round
Friday     02:00-06:00  kamba round
Saturday   02:00-06:00  cross-dialect transfer round
Sunday     02:00-06:00  model evaluation + promotion

Smaller dialects (meru, luhya, kalenjin, swahili-bongo):
  Bi-weekly, alternating Wednesdays

Rounds run at 02:00-06:00 local time because:
  - Most phones are charging overnight
  - WiFi is available (home routers)
  - No impact on daytime usage
```

---

## 7. Backend Aggregation Pipeline

### 7.1 Pipeline Architecture

```
                    GRADIENT COLLECTION
                           │
                    ┌──────▼──────┐
                    │   Ingest     │
                    │   Gateway    │
                    │  (PQC decap) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Validation  │
                    │  & Filtering │
                    │  (anomaly    │
                    │   detection) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  k-Anonymity │
                    │  Check       │
                    │  (≥5 similar │
                    │   workers)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Secure      │
                    │  Aggregation │
                    │  (FedAvg)    │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Evaluation  │
                    │  & Quality   │
                    │  Gate        │
                    └──────┬──────┘
                           │
                ┌──────────┼──────────┐
                │          │          │
         ┌──────▼───┐ ┌───▼────┐ ┌──▼──────┐
         │  Model    │ │ Cross- │ │ Metrics │
         │  Registry │ │ Dialect│ │ Store   │
         │           │ │ Transfer│ │         │
         └──────┬───┘ └────────┘ └─────────┘
                │
         ┌──────▼──────┐
         │  OTA Model   │
         │  Distribution│
         └─────────────┘
```

### 7.2 Gradient Collection & Validation

```python
class GradientCollector:
    """Collects and validates gradients from devices."""
    
    def __init__(self):
        self.pqc_decapsulator = MLKEM768Decapsulator()
        self.anomaly_detector = GradientAnomalyDetector()
    
    async def ingest(self, encrypted_payload: bytes, device_id_hash: str) -> Optional[ValidGradient]:
        # 1. Decrypt with PQC
        plaintext = self.pqc_decapsulator.decrypt(encrypted_payload)
        payload = GradientPayload.deserialize(plaintext)
        
        # 2. Validate structure
        if not self.validate_structure(payload):
            logger.warning(f"Invalid gradient structure from {device_id_hash[:8]}")
            return None
        
        # 3. Anomaly detection (prevent model poisoning)
        if self.anomaly_detector.is_anomalous(payload.gradient):
            logger.warning(f"Anomalous gradient from {device_id_hash[:8]}, discarding")
            return None
        
        # 4. Check gradient bounds (post-DP noise should still be bounded)
        if payload.gradient.norm() > self.MAX_GRADIENT_NORM * 2:  # 2x buffer for DP noise
            logger.warning(f"Gradient norm too large from {device_id_hash[:8]}")
            return None
        
        return ValidGradient(
            gradient=payload.gradient,
            dialect=payload.dialect,
            region=payload.region,
            device_class=payload.device_class,
            weight=self.compute_participation_weight(payload),
        )
```

### 7.3 Anomaly Detection (Model Poisoning Defense)

```python
class GradientAnomalyDetector:
    """
    Defends against model poisoning attacks.
    A malicious app might try to submit crafted gradients
    to degrade the global model.
    """
    
    def is_anomalous(self, gradient: Tensor) -> bool:
        """Multi-layered anomaly detection."""
        
        # Layer 1: Norm check
        if gradient.norm() > self.MAX_NORM:
            return True
        
        # Layer 2: Direction check (cosine similarity with historical mean)
        similarity = cosine_similarity(gradient, self.historical_mean)
        if similarity < -0.5:  # Opposite direction = suspicious
            return True
        
        # Layer 3: Statistical check (z-score per dimension)
        z_scores = (gradient - self.historical_mean) / (self.historical_std + 1e-8)
        if (z_scores.abs() > 5).sum() > gradient.numel() * 0.01:
            return True  # Too many outlier dimensions
        
        return False
```

### 7.4 FedAvg Aggregation

```python
class FedAvgAggregator:
    """Federated Averaging with weighted aggregation."""
    
    def aggregate(self, gradients: List[ValidGradient]) -> Tensor:
        """
        FedAvg: weighted average of client gradients.
        
        Weights based on:
        - Training data quantity (more data → higher weight)
        - Data quality score (from feedback signals)
        - Device class (normalize across hardware)
        """
        total_weight = sum(g.weight for g in gradients)
        
        aggregated = torch.zeros_like(gradients[0].gradient)
        for g in gradients:
            aggregated += (g.weight / total_weight) * g.gradient
        
        # Apply server-side learning rate
        aggregated *= self.server_lr  # Typically 0.1 — conservative
        
        return aggregated
    
    def compute_participation_weight(self, payload: GradientPayload) -> float:
        """
        Weight = f(data_quality, training_steps, device_reliability)
        
        This prevents gaming: a device can't just submit more
        gradients to get higher weight. Quality matters.
        """
        base_weight = 1.0
        quality_multiplier = payload.metadata.get("avg_reward", 0.5)
        steps_multiplier = min(payload.metadata.get("training_steps", 1) / 100, 1.0)
        
        return base_weight * quality_multiplier * steps_multiplier
```

### 7.5 Model Evaluation & Quality Gate

Before any aggregated model is distributed, it must pass evaluation:

```python
class ModelQualityGate:
    """Ensures aggregated model is actually better before deployment."""
    
    BENCHMARKS = {
        "swahili_standard": "eval/swahili_standard_bench.jsonl",
        "swahili_coastal": "eval/swahili_coastal_bench.jsonl",
        "kikuyu": "eval/kikuyu_bench.jsonl",
        "luo": "eval/luo_bench.jsonl",
        # ... per dialect
    }
    
    MIN_IMPROVEMENT = 0.005  # Must improve by at least 0.5%
    MAX_REGRESSION = 0.01    # Can't regress more than 1% on any benchmark
    
    def evaluate_and_gate(self, candidate: GlobalLoRA, current: GlobalLoRA, dialect: str) -> bool:
        """
        Returns True if candidate should replace current.
        """
        bench_path = self.BENCHMARKS[dialect]
        candidate_score = self.run_benchmark(candidate, bench_path)
        current_score = self.run_benchmark(current, bench_path)
        
        improvement = candidate_score - current_score
        
        if improvement < -self.MAX_REGRESSION:
            logger.warning(f"Model regressed by {-improvement:.3f} on {dialect}, rejecting")
            return False
        
        if improvement < self.MIN_IMPROVEMENT:
            logger.info(f"Model improvement {improvement:.3f} below threshold, rejecting")
            return False
        
        logger.info(f"Model improved by {improvement:.3f} on {dialect}, approving deployment")
        return True
```

### 7.6 Model Distribution (OTA)

```python
class ModelDistributor:
    """Distributes updated global LoRA to devices."""
    
    DISTRIBUTION_STRATEGY = "progressive"  # Not all at once
    
    async def distribute(self, dialect: str, new_global_lora: GlobalLoRA):
        """
        Progressive rollout:
        1. 5% of devices (canary) — monitor for 24h
        2. 25% of devices — monitor for 24h
        3. 100% of devices
        
        Devices download during idle time, same as training.
        """
        devices = self.get_devices_for_dialect(dialect)
        
        # Stage 1: Canary
        canary = random.sample(devices, max(1, len(devices) // 20))
        await self.push_to_devices(canary, new_global_lora)
        await asyncio.sleep(86400)  # Wait 24h
        
        if not self.check_canary_health(canary):
            logger.error("Canary deployment failed, rolling back")
            await self.rollback(canary)
            return
        
        # Stage 2: Broader rollout
        broader = random.sample(devices, len(devices) // 4)
        await self.push_to_devices(broader, new_global_lora)
        await asyncio.sleep(86400)
        
        # Stage 3: Full rollout
        remaining = [d for d in devices if d not in canary and d not in broader]
        await self.push_to_devices(remaining, new_global_lora)
    
    def get_update_package(self, global_lora: GlobalLoRA) -> bytes:
        """
        Package for OTA delivery:
        - INT4 quantized global LoRA (~10-20 MB)
        - Delta from previous version (~2-5 MB if incremental)
        - Signature for integrity verification
        - Version metadata
        """
        quantized = self.quantize_int4(global_lora)
        delta = self.compute_delta(quantized, self.previous_version)
        signature = self.sign_package(delta)
        
        return Package(
            delta=delta,
            signature=signature,
            version=self.next_version(),
            dialect=global_lora.dialect,
            base_version=global_lora.base_version,
        )
```

---

## 8. Opt-Out & Worker Control

### 8.1 Opt-Out Mechanism

```python
class FederationControl:
    """Worker-controlled federation participation."""
    
    OPT_OUT_STATES = {
        "active": "Currently participating in federation",
        "paused": "Temporarily stopped (e.g., data saving mode)",
        "disabled": "Permanently opted out until re-enabled",
    }
    
    def opt_out(self, worker_id: str, state: str = "disabled"):
        """
        Opt-out is immediate and complete:
        1. Stop collecting gradients
        2. Delete any pending (unsent) gradients from device
        3. Delete server-side gradient queue for this worker
        4. Personal LoRA continues to work normally
        5. Global LoRA updates still delivered (opt-out ≠ exclusion)
        """
        self.set_federation_state(worker_id, state)
        self.delete_pending_gradients(worker_id)
        self.request_server_deletion(worker_id)
        
        # Personal LoRA is unaffected — it's purely local
        return FederationStatus(
            state=state,
            personal_lora_active=True,
            global_lora_updates=True,  # Still receives updates
            gradient_submission=False,
        )
```

### 8.2 Transparency Dashboard

The app shows workers exactly what's happening:

```
┌─────────────────────────────────────┐
│  📊 Your Learning Status            │
│                                     │
│  Personal Model: ✅ Active          │
│  ─────────────────────────────────  │
│  Your phone has learned:            │
│  • 47 business terms                │
│  • Your voice patterns              │
│  • 12 product categories            │
│                                     │
│  Federation: ✅ Active              │
│  ─────────────────────────────────  │
│  Sharing: Anonymized gradients only │
│  Privacy: ε=0.1 (very strong)       │
│  Group size: 23 similar workers     │
│  Last shared: 2 hours ago           │
│                                     │
│  [Pause Federation]  [Learn More]   │
└─────────────────────────────────────┘
```

---

## 9. Implementation Roadmap

### Phase 1: Personal LoRA (Weeks 1-4)

```
Week 1-2: On-device training engine
  - LoRA adapter initialization
  - Idle-time training loop
  - Training data buffer (ring buffer, 500 examples)
  - Memory management for 2GB devices

Week 3-4: Personal LoRA inference
  - Base model + personal LoRA merging at inference
  - A/B testing: compare personalized vs. base model
  - Telemetry: track personalization quality metrics
```

### Phase 2: Gradient Pipeline (Weeks 5-8)

```
Week 5-6: Device-side gradient generation
  - Gradient computation from personal LoRA
  - Gradient clipping (L2 norm = 1.0)
  - Differential privacy noise addition
  - PQC encryption (ML-KEM-768)

Week 7-8: Backend collection infrastructure
  - Gradient ingestion service
  - Anomaly detection
  - k-Anonymity verification
  - Secure aggregation protocol
```

### Phase 3: Federation Rounds (Weeks 9-12)

```
Week 9-10: FedAvg aggregation
  - Weighted averaging implementation
  - Per-dialect federation groups
  - Model evaluation pipeline
  - Quality gate (prevent regression)

Week 11-12: OTA distribution
  - Progressive rollout system
  - Delta/incremental updates
  - Rollback capability
  - Device-side model verification
```

### Phase 4: Cross-Dialect & Polish (Weeks 13-16)

```
Week 13-14: Cross-dialect transfer
  - SVD decomposition for shared/dialect-specific
  - Cross-dialect aggregation round
  - Evaluation across dialects

Week 15-16: Worker controls & monitoring
  - Opt-out mechanism
  - Transparency dashboard
  - Privacy budget tracking
  - Federation health monitoring
```

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Model poisoning (malicious gradients) | Degraded global model | Anomaly detection + gradient clipping + k-anonymity |
| Privacy leakage from gradients | Worker data exposure | DP (ε=0.1) + k-anonymity (k=5) + secure aggregation |
| Insufficient participants | Can't run federation rounds | Cross-dialect fallback + extend collection window |
| Device memory pressure | App crashes during training | Aggressive memory monitoring + pause training on pressure |
| Network costs for gradient upload | Worker data plan usage | Upload only on WiFi + compressed gradients (~100KB) |
| Model update too large for OTA | Slow/broken updates | Delta updates (~2-5MB) + INT4 quantization |
| Gradient staleness (offline devices) | Outdated contributions | 48h collection window + version-aware aggregation |
| Catastrophic forgetting in personal LoRA | Worker's model degrades | EWC regularization + periodic base model re-anchoring |

---

## 11. Key Design Decisions

| Decision | Choice | Alternatives Considered | Why |
|----------|--------|------------------------|-----|
| LoRA rank (personal) | 8 | 4, 16, 32 | Sweet spot: 5-10MB, enough capacity for personalization |
| LoRA rank (global) | 16 | 8, 32, 64 | More capacity needed for population patterns |
| DP epsilon | 0.1 | 0.5, 1.0, 5.0 | Very strong privacy; acceptable utility loss |
| k-anonymity | 5 | 3, 10, 20 | Small enough for diverse dialects, large enough for privacy |
| PQC algorithm | ML-KEM-768 | ML-KEM-510, ML-KEM-1024 | NIST standard, good security/performance balance |
| Training location | On-device | Server-side | Privacy + no data transfer + personalization |
| Aggregation method | FedAvg | FedProx, FedBN, SCAFFOLD | Simplicity + proven + works with LoRA |
| Update delivery | Delta OTA | Full model OTA | 2-5MB vs 20-40MB; critical for 2GB devices |

---

*This document is a living design. Update as implementation reveals practical constraints.*
