# Federated Learning Pipeline: Device ↔ Backend Intelligence Sharing

**Version:** 1.0  
**Date:** 2026-07-25  
**Status:** Technical Design  

---

## Executive Summary

This document defines the privacy-preserving federated learning pipeline that connects millions of informal economy workers' devices with a central backend. The core principle: **raw data never leaves the device**. Only encrypted, differentially-private gradient updates travel to the backend, where they are aggregated into an improved global model and pushed back out as lightweight deltas.

---

## 1. Gradient Aggregation

### 1.1 Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Device A    │     │  Device B    │     │  Device C    │
│              │     │              │     │              │
│ Local Model  │     │ Local Model  │     │ Local Model  │
│ + Local Data │     │ + Local Data │     │ + Local Data │
│              │     │              │     │              │
│ Compute      │     │ Compute      │     │ Compute      │
│ Gradients    │     │ Gradients    │     │ Gradients    │
│              │     │              │     │              │
│ Add DP Noise │     │ Add DP Noise │     │ Add DP Noise │
│              │     │              │     │              │
│ Encrypt w/   │     │ Encrypt w/   │     │ Encrypt w/   │
│ Masking      │     │ Masking      │     │ Masking      │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   Aggregation   │
                   │     Server      │
                   │                 │
                   │ Receive masked  │
                   │ gradients       │
                   │                 │
                   │ Sum (masks      │
                   │ cancel out)     │
                   │                 │
                   │ Apply FedAvg /  │
                   │ FedProx         │
                   │                 │
                   │ Update Global   │
                   │ Model           │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Push Delta to  │
                   │    Devices      │
                   └─────────────────┘
```

### 1.2 Secure Aggregation Protocol

We use a modified version of the Bonawitz et al. (2017) secure aggregation protocol, optimized for low-bandwidth mobile networks.

#### Step 1: Local Gradient Computation

Each device computes gradients over its local data:

```
g_i = ∇L(θ_global, D_local_i)
```

Where:
- `θ_global` = current global model weights
- `D_local_i` = device i's local interaction data (never uploaded)
- `L` = loss function (cross-entropy for classification, MSE for regression)

#### Step 2: Differential Privacy Noise Addition

Before encryption, each device adds calibrated noise:

```
g̃_i = g_i + N(0, σ²I)
```

Where `σ = (Δf × √(2 ln(1.25/δ))) / ε`

- `ε = 0.1` (privacy budget per round)
- `δ = 1/n²` (where n = number of devices)
- `Δf` = gradient clipping threshold (L2 norm clipped to C = 1.0)

#### Step 3: Masking with Pairwise Seeds

Each pair of devices (i, j) establishes a shared secret via Diffie-Hellman during setup. Device i adds mask `s_{i,j}` and device j subtracts it. When summed, all pairwise masks cancel:

```
masked_g_i = g̃_i + Σ_{j<i} s_{i,j} - Σ_{j>i} s_{i,j}
```

The aggregation server sees only `Σ masked_g_i = Σ g̃_i` (masks cancel).

#### Step 4: Server-Side Aggregation

```
θ_global_new = θ_global - η × (1/|S|) × Σ_{i∈S} masked_g_i
```

Where `S` is the set of participating devices in this round, `η` is the learning rate.

### 1.3 Handling 100K+ Devices

Not all devices participate every round. We use a stratified sampling strategy:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Devices per round | 1,000–5,000 | Diminishing returns beyond ~5K; communication cost |
| Round duration | 4 hours | Accommodates intermittent connectivity |
| Minimum completion | 80% of sampled | Threshold for valid aggregation |
| Sampling bias | Stratified by cohort | Ensures representation |

**Stratified Random Sampling Algorithm:**

```python
def select_participants(all_devices, cohort_map, target_per_round=2000):
    """
    Select devices for next FL round, ensuring cohort representation.
    """
    cohorts = group_by_cohort(all_devices, cohort_map)
    selected = []
    
    # Allocate slots proportional to cohort size, with minimum 5 per cohort
    total = len(all_devices)
    for cohort_id, devices in cohorts.items():
        n = max(5, int(target_per_round * len(devices) / total))
        # Filter: battery > 20%, charging or WiFi, not in power-save
        eligible = [d for d in devices if is_eligible(d)]
        selected.extend(random.sample(eligible, min(n, len(eligible))))
    
    return selected[:target_per_round]

def is_eligible(device):
    return (
        device.battery_level > 20 and
        (device.is_charging or device.connection_type == 'wifi') and
        device.last_round_ts < now() - timedelta(hours=2) and  # cooldown
        device.model_version >= MIN_SUPPORTED_VERSION
    )
```

**Hierarchical Aggregation (for very large scale):**

```
100K devices → 50 regional aggregators → 1 central server
```

Regional aggregators perform first-pass aggregation, then send only the aggregated (still masked) gradients to the central server. This reduces bandwidth by 50x and adds an additional privacy layer.

```
┌──────────────────────────────────────────────────────┐
│                   Central Server                      │
│              Aggregates regional sums                 │
└───────────┬──────────────┬──────────────┬────────────┘
            │              │              │
    ┌───────▼──────┐ ┌─────▼───────┐ ┌───▼─────────┐
    │  Regional    │ │  Regional   │ │  Regional    │
    │  Aggregator  │ │  Aggregator │ │  Aggregator  │
    │  (Nairobi)   │ │  (Mombasa)  │ │  (Kisumu)    │
    └──┬───┬───┬───┘ └──┬───┬───┬──┘ └──┬───┬───┬──┘
       │   │   │        │   │   │       │   │   │
       ▼   ▼   ▼        ▼   ▼   ▼       ▼   ▼   ▼
     [Devices]        [Devices]       [Devices]
```

### 1.4 Aggregation Algorithms

| Algorithm | When to Use | Formula |
|-----------|-------------|---------|
| **FedAvg** | Default; IID data | θ_new = Σ(n_i/n) × θ_i |
| **FedProx** | Non-IID data (different worker types) | Adds proximal term μ‖θ - θ_global‖² |
| **FedMA** | Different model architectures | Bayesian non-parametric matching |

**We default to FedProx** because our data is inherently non-IID (different business types, regions, languages).

---

## 2. Cohort Formation

### 2.1 Cohort Taxonomy

Cohorts are defined by a multi-dimensional feature vector:

```
cohort_id = hash(region, business_type, language, scale_bucket)
```

#### Dimensions

| Dimension | Values | Cardinality |
|-----------|--------|-------------|
| **Region** | Nairobi, Mombasa, Kisumu, Nakuru, Eldoret, + 20 more | ~25 |
| **Business Type** | mama_mboga, boda_boda, mitumba, salon, hardware, kiosk, mobile_money, + 10 more | ~17 |
| **Language** | Swahili, English, Sheng, Dholuo, Kikuyu, Kalenjin, + 5 more | ~11 |
| **Scale** | solo (1 person), micro (2-5), small (6-15) | 3 |

**Theoretical max cohorts:** 25 × 17 × 11 × 3 = **14,025**

**Expected active cohorts** (sparse): ~500–800

### 2.2 Dynamic Cohort Assignment

Devices are not statically assigned. Cohort is computed at round time:

```python
def compute_cohort(device):
    region = device.location_cluster  # GPS → cluster ID
    biz_type = device.primary_category  # From transaction patterns
    language = device.dominant_language  # From keyboard/input analysis
    scale = bucket(device.transaction_count_30d, [10, 50])
    
    return f"{region}|{biz_type}|{language}|{scale}"
```

### 2.3 Minimum Cohort Size for k-Anonymity

**Hard constraint: k ≥ 10**

Any cohort with fewer than 10 active devices is **merged** with its nearest neighbor:

```python
def enforce_k_anonymity(cohorts, k=10):
    """
    Merge cohorts smaller than k with nearest neighbor.
    """
    merged = {}
    small_cohorts = []
    
    for cid, devices in cohorts.items():
        if len(devices) >= k:
            merged[cid] = devices
        else:
            small_cohorts.append((cid, devices))
    
    for cid, devices in small_cohorts:
        nearest = find_nearest_cohort(cid, merged)
        merged[nearest].extend(devices)
        log(f"Merged {cid} ({len(devices)} devices) into {nearest}")
    
    return merged

def find_nearest_cohort(cid, existing):
    """
    Find most similar existing cohort by Levenshtein on cohort ID components.
    Preference order: same region > same business > same language.
    """
    region, biz, lang, scale = cid.split('|')
    
    candidates = []
    for eid in existing:
        er, eb, el, es = eid.split('|')
        score = 0
        if er == region: score += 4  # Region most important
        if eb == biz:    score += 2
        if el == lang:   score += 1
        candidates.append((score, eid))
    
    return max(candidates, key=lambda x: x[0])[1]
```

### 2.4 Cohort-Specific Model Heads

The global model uses a **shared backbone + cohort-specific heads** architecture:

```
Input (transaction text, amount, time)
        │
        ▼
┌───────────────────┐
│  Shared Backbone   │  ← Updated via federated averaging
│  (encoder layers)  │
└─────────┬─────────┘
          │
    ┌─────┼─────┬─────────┐
    ▼     ▼     ▼         ▼
┌──────┐┌──────┐┌──────┐┌──────┐
│Nairobi││Mombasa││Boda  ││Mama  │  ← Cohort-specific heads
│Head   ││Head   ││Head  ││Mboga │    Updated only by cohort members
└──────┘└──────┘└──────┘└──────┘
```

This means:
- **Backbone** learns universal patterns (what a "sale" looks like)
- **Heads** learn cohort-specific patterns (Nairobi pricing vs Mombasa pricing)

---

## 3. Model Update Distribution

### 3.1 Delta Updates

Full model size: ~15 MB (quantized INT8)  
Typical delta size: ~500 KB–2 MB (depending on change magnitude)

**Delta encoding:**

```python
def compute_delta(old_weights, new_weights):
    """
    Compute sparse delta between model versions.
    Only transmit weights that changed by > threshold.
    """
    delta = {}
    threshold = 1e-6  # Skip negligible changes
    
    for layer_name in old_weights:
        diff = new_weights[layer_name] - old_weights[layer_name]
        mask = np.abs(diff) > threshold
        
        if not mask.any():
            continue
        
        # Store only changed values with their indices
        delta[layer_name] = {
            'indices': np.where(mask),
            'values': diff[mask].astype(np.float16),  # Half precision for transport
            'shape': old_weights[layer_name].shape
        }
    
    return compress(delta)  # LZ4 compression, typically 3-5x further reduction
```

**Typical delta sizes:**

| Scenario | Delta Size | Reason |
|----------|-----------|--------|
| Minor update (1 round) | 200–500 KB | Few weights changed significantly |
| Major update (10+ rounds) | 1–3 MB | More weights drifted |
| Architecture change | 15 MB (full) | Cannot delta; full replacement |

### 3.2 Delivery Mechanism

```
┌─────────────────────────────────────────────────────────┐
│                    Update Delivery                        │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. Backend publishes update manifest:                   │
│     {                                                    │
│       "version": "2026.07.25.3",                        │
│       "delta_from": "2026.07.25.2",                     │
│       "delta_url": "https://cdn..../delta_v3.bin",      │
│       "delta_size": 847293,                              │
│       "checksum": "sha256:...",                          │
│       "min_app_version": "1.4.0",                        │
│       "rollback_to": "2026.07.25.2"                     │
│     }                                                    │
│                                                          │
│  2. Device checks eligibility:                           │
│     - WiFi connected? OR cellular + small delta (<500KB) │
│     - Battery > 30% OR charging                          │
│     - Storage > 50MB free                                │
│     - Not in active use (idle detection)                 │
│                                                          │
│  3. Download with resume support                         │
│  4. Verify checksum                                      │
│  5. Apply delta to local model                           │
│  6. Report success/failure to backend                    │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Network-Aware Download Policy

```python
DOWNLOAD_POLICY = {
    'wifi': {
        'max_delta_size': float('inf'),  # No limit on WiFi
        'battery_min': 15,
        'background_ok': True
    },
    'cellular': {
        'max_delta_size': 500_000,  # 500KB max on cellular
        'battery_min': 40,
        'background_ok': False,    # Only foreground
        'user_prompt': True        # Ask user first
    },
    'metered_wifi': {
        'max_delta_size': 2_000_000,  # 2MB on metered WiFi
        'battery_min': 30,
        'background_ok': True
    }
}
```

### 3.4 Version Management & Rollback

**Version scheme:** `YYYY.MM.DD.build` (e.g., `2026.07.25.3`)

**Rollback triggers:**

```python
class ModelHealthMonitor:
    def __init__(self):
        self.prediction_history = deque(maxlen=100)
        self.error_rates = deque(maxlen=10)
    
    def should_rollback(self, current_version):
        """
        Trigger rollback if model performance degrades significantly.
        """
        recent_error = np.mean(list(self.error_rates)[-3:])
        baseline_error = self.get_baseline_error(current_version)
        
        # Rollback if error rate increased by >50% relative
        if recent_error > baseline_error * 1.5:
            return True
        
        # Rollback if prediction confidence dropped below threshold
        recent_confidence = np.mean([p['confidence'] for p in self.prediction_history])
        if recent_confidence < 0.3:
            return True
        
        return False
    
    def rollback(self):
        """Revert to previous model version."""
        prev_version = self.get_previous_version()
        prev_weights = self.load_cached_model(prev_version)
        self.apply_weights(prev_version, prev_weights)
        self.report_rollback_to_backend(prev_version)
```

**Backend-side rollback propagation:**

When the backend detects widespread rollback reports (>10% of devices in a cohort):
1. Immediately marks the update as suspect
2. Stops pushing to remaining devices
3. Reverts the global model to previous checkpoint
4. Investigates root cause before re-attempting

---

## 4. Privacy Guarantees

### 4.1 Threat Model

| Adversary | Capability | Defense |
|-----------|------------|---------|
| **Honest-but-curious server** | Sees all transmitted data | Secure aggregation (server sees only sum) |
| **Malicious device** | Sends crafted gradients | Robust aggregation (coordinate-wise median) |
| **Network eavesdropper** | Intercepts traffic | TLS 1.3 + encrypted gradients |
| **Model inversion attacker** | Queries model to extract training data | Differential privacy (ε=0.1) |
| **Membership inference** | Determines if data was in training | DP + k-anonymity |

### 4.2 Differential Privacy Guarantee

**Definition:** A mechanism M satisfies (ε, δ)-differential privacy if for all neighboring datasets D, D' (differing in one record) and all outputs S:

```
Pr[M(D) ∈ S] ≤ e^ε × Pr[M(D') ∈ S] + δ
```

**Our parameters:**

| Parameter | Value | Meaning |
|-----------|-------|---------|
| ε (epsilon) | 0.1 per round | Very strong privacy |
| δ (delta) | 1/n² (n = cohort size) | Negligible probability of privacy breach |
| Clip norm C | 1.0 | Gradient clipping bound |
| Noise multiplier σ | Calculated per round | Scales with sensitivity |

**Privacy accounting (Rényi DP):**

Over T rounds of training, the total privacy budget accumulates. Using Rényi DP composition:

```
ε_total = ε × √(2T × ln(1/δ))
```

For T = 100 rounds, ε = 0.1, δ = 10⁻⁸:
```
ε_total = 0.1 × √(200 × ln(10⁸)) ≈ 0.1 × √(3684) ≈ 6.1
```

This is still considered reasonable privacy (ε < 10 is generally accepted in practice).

### 4.3 Secure Aggregation Protocol Detail

```
Phase 1: Setup (one-time, per round)
──────────────────────────────────────
Each device pair (i,j) runs Diffie-Hellman to establish shared seed s_{i,j}.
Public keys are broadcast; shared seeds computed locally.
A key server (separate from aggregation server) holds backup shares
for dropout recovery.

Phase 2: Masked Upload
──────────────────────────────────────
Device i computes:
  masked_gradient_i = gradient_i + noise_i + Σ_{j<i} PRG(s_{i,j}) - Σ_{j>i} PRG(s_{i,j})

Uploads masked_gradient_i to aggregation server.

Phase 3: Aggregation
──────────────────────────────────────
Server computes:
  sum = Σ masked_gradient_i
     = Σ (gradient_i + noise_i + canceling_masks)
     = Σ gradient_i + Σ noise_i
     (masks cancel in sum)

Phase 4: Dropout Handling
──────────────────────────────────────
If device k drops out:
  - Surviving devices reconstruct k's share via Shamir secret sharing
  - Masks for k are subtracted from the sum
  - k's gradient is simply excluded (privacy preserved for k)
```

### 4.4 k-Anonymity Enforcement

Beyond cohort-level k-anonymity (k ≥ 10), we enforce:

1. **Gradient-level k-anonymity:** Any gradient update is indistinguishable from at least k-1 other devices' updates (guaranteed by the DP noise)

2. **Query-level k-anonymity:** The model cannot be queried in a way that reveals fewer than k training examples (enforced by output perturbation)

3. **Temporal k-anonymity:** A device's participation pattern across rounds cannot be uniquely identified (random participation scheduling)

### 4.5 What Never Leaves the Device

```
┌─────────────────────────────────────────────┐
│           DATA THAT STAYS ON DEVICE          │
├─────────────────────────────────────────────┤
│ ✗ Raw transaction text                      │
│ ✗ Transaction amounts                       │
│ ✗ Customer names/details                    │
│ ✗ GPS coordinates (only cluster ID used)    │
│ ✗ Contact lists                             │
│ ✗ Photos                                    │
│ ✗ Audio recordings                          │
│ ✗ Exact timestamps (quantized to hour)      │
│ ✗ Individual predictions                    │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│           DATA THAT LEAVES DEVICE            │
│         (encrypted + differentially private) │
├─────────────────────────────────────────────┤
│ ✓ Masked gradient vectors                   │
│ ✓ Model version number                      │
│ ✓ Cohort ID (aggregated, k≥10)             │
│ ✓ Aggregate error metrics (no raw data)     │
│ ✓ Device capability metadata (OS, RAM)      │
│ ✓ Participation signal (round ID)           │
└─────────────────────────────────────────────┘
```

---

## 5. Feedback Loop

### 5.1 Device-Side Feedback Collection

Devices collect lightweight feedback signals without exposing raw data:

```python
class FeedbackCollector:
    def __init__(self):
        self.predictions = []
        self.corrections = []
    
    def record_prediction(self, prediction, confidence, context_hash):
        """Record a model prediction (stored locally)."""
        self.predictions.append({
            'timestamp': quantize_time(now()),  # Hour-level precision
            'prediction': prediction,           # Category, not raw text
            'confidence': confidence,
            'context_hash': context_hash,       # Hashed, not reversible
            'cohort': self.cohort_id
        })
    
    def record_correction(self, prediction_id, actual_category, error_magnitude):
        """User corrected the prediction. Record the delta."""
        self.corrections.append({
            'prediction_id': prediction_id,
            'actual': actual_category,
            'error': error_magnitude,  # 0.0 = correct, 1.0 = completely wrong
            'cohort': self.cohort_id
        })
    
    def compute_feedback_summary(self):
        """
        Aggregate feedback into a privacy-safe summary.
        No individual predictions are included.
        """
        if len(self.corrections) < MIN_FEEDBACK_SAMPLES:
            return None  # Not enough data to report
        
        return {
            'n_predictions': len(self.predictions),
            'n_corrections': len(self.corrections),
            'mean_error': np.mean([c['error'] for c in self.corrections]),
            'error_by_category': self._aggregate_by_category(),  # Only if k≥10
            'confidence_calibration': self._compute_calibration(),
            'cohort': self.cohort_id,
            'round_id': current_round
        }
```

### 5.2 Feedback-Weighted Model Updates

Not all feedback is equal. We weight feedback signals by reliability:

```python
def compute_feedback_weights(feedback_reports):
    """
    Weight feedback from different devices/cohorts for model update priority.
    """
    weights = {}
    
    for report in feedback_reports:
        cohort = report['cohort']
        
        # Factor 1: Sample size (more predictions = more reliable)
        sample_weight = min(1.0, report['n_predictions'] / 50)
        
        # Factor 2: Error severity (high-error cohorts get priority attention)
        error_weight = report['mean_error']  # 0 to 1
        
        # Factor 3: Device reliability (based on history)
        device_reliability = get_device_reliability_score(report['device_id'])
        
        # Factor 4: Cohort diversity (underrepresented cohorts weighted up)
        cohort_size = get_cohort_size(cohort)
        diversity_weight = 1.0 / np.log2(max(2, cohort_size))
        
        # Combined weight
        weights[cohort] = (
            0.3 * sample_weight +
            0.3 * error_weight +
            0.2 * device_reliability +
            0.2 * diversity_weight
        )
    
    return normalize(weights)
```

### 5.3 Feedback-Driven Model Improvement Cycle

```
                    ┌─────────────────┐
                    │  Global Model   │
                    │  Version N      │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Push to Devices │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Device A │  │ Device B │  │ Device C │
        │          │  │          │  │          │
        │ Make     │  │ Make     │  │ Make     │
        │ Predict- │  │ Predict- │  │ Predict- │
        │ ions     │  │ ions     │  │ ions     │
        │          │  │          │  │          │
        │ Collect  │  │ Collect  │  │ Collect  │
        │ Feedback │  │ Feedback │  │ Feedback │
        │          │  │          │  │          │
        │ Compute  │  │ Compute  │  │ Compute  │
        │ Local    │  │ Local    │  │ Local    │
        │ Gradients│  │ Gradients│  │ Gradients│
        └────┬─────┘  └────┬─────┘  └────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   Aggregation   │
                   │                 │
                   │ 1. Aggregate    │
                   │    gradients    │
                   │ 2. Weight by    │
                   │    feedback     │
                   │ 3. Apply to     │
                   │    global model │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Global Model   │
                   │  Version N+1    │
                   │                 │
                   │  Changelog:     │
                   │  - Fixed: X     │
                   │  - Improved: Y  │
                   │  - Feedback     │
                   │    addressed: Z │
                   └─────────────────┘
```

### 5.4 Feedback Categories and Weights by Worker Type

| Worker Type | Primary Feedback Signal | Weight Multiplier | Rationale |
|-------------|------------------------|-------------------|-----------|
| Mama mboga | Sale categorization errors | 1.2× | High volume, reliable signal |
| Boda boda | Route/fuel prediction errors | 1.0× | Standard weight |
| Mitumba | Price estimation errors | 1.1× | Good signal, variable data |
| Salon | Service categorization | 0.9× | Lower volume |
| Mobile money | Transaction type errors | 1.3× | High precision needed |
| New workers (<30 days) | All signals | 0.5× | Noisy data, still learning |

### 5.5 Continuous Improvement Metrics

The backend tracks these metrics per round:

```python
FL_METRICS = {
    # Model quality
    'global_loss': float,           # Average loss across all cohorts
    'cohort_losses': dict,          # Per-cohort loss breakdown
    'prediction_accuracy': float,   # % correct predictions
    'confidence_calibration': float, # How well confidence matches accuracy
    
    # Fairness
    'accuracy_parity': float,       # Max accuracy difference across cohorts
    'error_rate_ratio': float,      # Worst/best cohort error ratio
    'underrepresented_boost': float, # Did diversity weighting help?
    
    # Privacy
    'epsilon_spent': float,         # Cumulative privacy budget used
    'k_anonymity_min': int,         # Smallest cohort size
    'dropout_rate': float,          # % of sampled devices that dropped out
    
    # System
    'participation_rate': float,    # % of invited devices that participated
    'round_duration_sec': float,    # How long the round took
    'delta_size_bytes': int,        # Size of model update
    'rollback_rate': float,         # % of devices that rolled back
}
```

---

## 6. Implementation Timeline

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 1: Core FL** | 4 weeks | FedAvg with 100 devices, basic DP |
| **Phase 2: Secure Agg** | 3 weeks | Masked gradient protocol, dropout handling |
| **Phase 3: Cohorts** | 2 weeks | Cohort formation, k-anonymity, heads architecture |
| **Phase 4: Distribution** | 2 weeks | Delta updates, network-aware delivery, rollback |
| **Phase 5: Feedback Loop** | 3 weeks | Feedback collection, weighted aggregation |
| **Phase 6: Scale** | 3 weeks | Hierarchical aggregation, 100K+ device support |
| **Phase 7: Hardening** | 2 weeks | Adversarial robustness, privacy audit |

**Total: ~19 weeks to full production**

---

## 7. Open Questions

1. **Heterogeneous models:** Should different device tiers (low-end vs high-end) run different model sizes? Trade-off: complexity vs accessibility.

2. **Cross-cohort learning:** How aggressively should knowledge transfer between cohorts? A Nairobi mama mboga's patterns might help a Mombasa mama mboga, but could also introduce bias.

3. **Incentive design:** Should devices that contribute more FL rounds get better model quality? Risk: creates a two-tier system.

4. **Regulatory compliance:** How does this interact with Kenya's Data Protection Act (2019)? Need legal review of the DP guarantees.

5. **Offline workers:** Devices that are rarely online will have stale models. How long is acceptable before forced update via SMS-triggered background download?

---

*This document is a living design. Update as implementation reveals new constraints.*
