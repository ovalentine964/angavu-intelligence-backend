# Alama Score Engine — Architecture Design

> **Alama** (Swahili: "mark/sign") — A real-time financial readiness assessment engine built from voice transaction data for Msaidizi informal workers.

---

## 1. Design Philosophy

### Core Principles

| Principle | Implication |
|-----------|------------|
| **Behavior is the score** | No self-reported data. Every data point comes from actual voice-recorded transactions. |
| **Worker owns the data** | Score is computed locally on-device. Sync is opt-in. Sharing requires explicit consent. |
| **Offline-first** | Engine runs entirely on-device. Network is a bonus, not a requirement. |
| **Transparent** | Worker can always see why their score is what it is. No black boxes. |
| **Regulatory safe** | This is "financial readiness," not "credit scoring." The distinction is legal and architectural. |

### What Alama Score Is NOT

- NOT a credit bureau score (no third-party data aggregation)
- NOT a social graph score (no "your friends' scores affect yours")
- NOT a one-time assessment (continuous, evolving with every transaction)
- NOT a judgment (high or low score, the worker always sees actionable next steps)

---

## 2. Data Pipeline — From Voice to Signal

### 2.1 Voice Transaction Extraction

```
┌─────────────────────────────────────────────────────────────┐
│                    VOICE RECORDING                          │
│  "Nilikuza mboga leo, nimepata mia tano, nimebuy stock      │
│   ya mia tatu, nimesave mia moja"                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              SPEECH-TO-TEXT + NLU PIPELINE                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Whisper  │→ │ Language │→ │  Entity   │→ │ Intent +  │ │
│  │ /Local   │  │ Detect   │  │ Extract   │  │ Slot Fill │ │
│  └──────────┘  └──────────┘  └───────────┘  └───────────┘ │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  STRUCTURED TRANSACTION                      │
│  {                                                           │
│    "timestamp": "2026-07-24T08:30:00+03:00",                │
│    "type": "sale",                                           │
│    "amount": 500,                                            │
│    "currency": "KES",                                        │
│    "category": "vegetables",                                 │
│    "location": "marikiti_market",                            │
│    "expenses": [{"amount": 300, "category": "stock"}],      │
│    "savings": [{"amount": 100, "destination": "mpesa"}],    │
│    "confidence": 0.87,                                       │
│    "language": "sw"                                          │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Raw Data Points Extracted Per Transaction

| Field | Type | Source | Signal Value |
|-------|------|--------|-------------|
| `timestamp` | ISO 8601 | System clock | Regularity, consistency |
| `transaction_type` | enum | NLU intent | Business activity type |
| `revenue` | float | NER extraction | Income tracking |
| `cost_of_goods` | float | NER extraction | Margin calculation |
| `expenses` | float[] | NER extraction | Expense control |
| `savings_amount` | float | NER extraction | Savings behavior |
| `product_category` | string | NLU slot | Diversity tracking |
| `location` | GPS/label | Device/voice | Consistency signal |
| `voice_confidence` | float | ASR model | Data quality weight |
| `language` | string | Lang detect | Localization |

### 2.3 Feature Store (On-Device)

```
features/
├── daily/
│   ├── 2026-07-24.json      # Daily aggregates
│   ├── 2026-07-23.json
│   └── ...
├── rolling/
│   ├── 7d_summary.json      # 7-day rolling windows
│   ├── 30d_summary.json     # 30-day rolling windows
│   └── 90d_summary.json     # 90-day rolling windows
├── lifetime/
│   └── all_time.json         # Lifetime aggregates
└── derived/
    ├── consistency.json      # Regularity metrics
    ├── growth.json           # Trend analysis
    └── risk.json             # Risk indicators
```

---

## 3. Feature Engineering — The Eight Pillars

Each pillar contributes a sub-score (0–100) to the final Alama Score.

### Pillar 1: Transaction Frequency (Weight: 15%)

**What it measures:** How consistently the worker records transactions.

```
Input:  daily_transaction_counts[] over rolling window
Output: frequency_score (0-100)

Computation:
  active_days    = count(days with ≥1 transaction in window)
  total_days     = window_size
  daily_consistency = active_days / total_days

  # Penalize gaps (consecutive inactive days)
  max_gap = max(consecutive_inactive_days)
  gap_penalty = max(0, 1 - (max_gap / 7))  # 7+ day gap = 0

  frequency_score = daily_consistency * gap_penalty * 100
```

**Why it matters:** A worker who records daily has a real business. Sporadic recording = uncertain activity.

---

### Pillar 2: Revenue Trends (Weight: 15%)

**What it measures:** Whether income is growing, stable, or declining.

```
Input:  daily_revenue[] over rolling window
Output: revenue_trend_score (0-100)

Computation:
  # Linear regression on daily revenue
  slope, intercept = linear_fit(days[], revenue[])

  # Normalized slope (revenue change per week as % of mean)
  weekly_change_pct = (slope * 7) / mean(revenue)
  trend_signal = tanh(weekly_change_pct * 5)  # Bounded [-1, 1]

  # Also consider volatility (low volatility = stable = better)
  cv = stddev(revenue) / mean(revenue)  # Coefficient of variation
  stability = max(0, 1 - cv)

  revenue_trend_score = ((trend_signal + 1) / 2 * 0.6 + stability * 0.4) * 100
```

**Why it matters:** Growing revenue signals a healthy business. High volatility signals risk.

---

### Pillar 3: Profit Margins (Weight: 15%)

**What it measures:** Is the business actually profitable?

```
Input:  daily_revenue[], daily_cogs[], daily_expenses[]
Output: margin_score (0-100)

Computation:
  gross_margin  = (revenue - cogs) / revenue
  net_margin    = (revenue - cogs - expenses) / revenue

  # Score based on margin thresholds (informal economy norms)
  gross_score = clamp(gross_margin / 0.40, 0, 1)  # 40%+ gross = perfect
  net_score   = clamp(net_margin / 0.20, 0, 1)    # 20%+ net = perfect

  # Negative margins are a strong negative signal
  if net_margin < 0:
      net_score = max(-0.5, net_margin) * 2  # Penalties, not just zero

  margin_score = (gross_score * 0.4 + net_score * 0.6) * 100
```

**Why it matters:** Revenue means nothing without profit. A KES 10,000/day business with KES 11,000 in costs is failing.

---

### Pillar 4: Product Diversity (Weight: 10%)

**What it measures:** Risk concentration — is income from one product or many?

```
Input:  product_category_distribution over rolling window
Output: diversity_score (0-100)

Computation:
  # Shannon entropy over product categories
  H = -Σ(p_i * log(p_i))  for each category i
  H_max = log(n_categories)

  # Normalize
  diversity_ratio = H / H_max  # 0 = single product, 1 = perfectly diverse

  # Penalize extreme concentration
  max_share = max(p_i)
  concentration_penalty = max(0, 1 - (max_share - 0.5) * 2)  # >50% one product = penalty

  diversity_score = (diversity_ratio * 0.6 + concentration_penalty * 0.4) * 100
```

**Why it matters:** A mama mboga selling only tomatoes collapses when tomato prices spike. Diversity = resilience.

---

### Pillar 5: Regularity (Weight: 10%)

**What it measures:** Does the worker operate on a predictable schedule?

```
Input:  transaction_timestamps[] over rolling window
Output: regularity_score (0-100)

Computation:
  # Hour-of-day distribution
  hour_hist = histogram(timestamps, bins=24)
  hour_entropy = entropy(hour_hist) / log(24)

  # Day-of-week distribution
  dow_hist = histogram(day_of_week(timestamps), bins=7)
  dow_entropy = entropy(dow_hist) / log(7)

  # Low entropy = predictable = good
  hour_regularity = 1 - hour_entropy
  dow_regularity  = 1 - dow_entropy

  # Location consistency (if available)
  location_consistency = mode_location_count / total_sessions

  regularity_score = (hour_regularity * 0.4 + dow_regularity * 0.3 +
                      location_consistency * 0.3) * 100
```

**Why it matters:** Predictable behavior signals a real, established business. Random activity signals chaos.

---

### Pillar 6: Growth Trajectory (Weight: 10%)

**What it measures:** Is the business improving over time?

```
Input:  30d_summary vs 90d_summary feature vectors
Output: growth_score (0-100)

Computation:
  # Compare rolling averages
  revenue_growth  = (avg_30d_revenue - avg_90d_revenue) / avg_90d_revenue
  margin_growth   = avg_30d_margin - avg_90d_margin
  frequency_growth = avg_30d_frequency - avg_90d_frequency
  savings_growth  = (avg_30d_savings - avg_90d_savings) / max(avg_90d_savings, 1)

  # Weighted composite
  raw_growth = (revenue_growth * 0.35 + margin_growth * 0.25 +
                frequency_growth * 0.20 + savings_growth * 0.20)

  # Sigmoid to bound
  growth_score = sigmoid(raw_growth * 10) * 100
```

**Why it matters:** A worker whose business is improving — even slowly — is a fundamentally different risk than one who's stagnating.

---

### Pillar 7: Expense Patterns (Weight: 10%)

**What it measures:** Is the worker disciplined about spending?

```
Input:  daily_expense_breakdown[] over rolling window
Output: expense_control_score (0-100)

Computation:
  # Expense-to-revenue ratio stability
  expense_ratio = expenses / revenue
  ratio_cv = stddev(expense_ratio) / mean(expense_ratio)
  stability = max(0, 1 - ratio_cv)

  # Unnecessary expense detection (heuristic)
  # Categories: stock (good), transport (necessary), misc (suspicious)
  good_expense_share = (stock + transport) / total_expenses
  expense_quality = good_expense_share

  # Impulse detection: large single-day expense spikes
  daily_expenses_z = zscore(daily_expenses)
  spike_days = count(daily_expenses_z > 2.0)
  spike_penalty = max(0, 1 - spike_days / (window_size * 0.1))

  expense_control_score = (stability * 0.4 + expense_quality * 0.3 +
                           spike_penalty * 0.3) * 100
```

**Why it matters:** Controlled expenses signal financial discipline. Erratic spending signals risk.

---

### Pillar 8: Savings Behavior (Weight: 15%)

**What it measures:** Does the worker save? How consistently?

```
Input:  daily_savings[] over rolling window
Output: savings_score (0-100)

Computation:
  # Savings rate
  total_savings = sum(savings)
  total_revenue = sum(revenue)
  savings_rate = total_savings / total_revenue

  # Score: 10%+ savings rate is excellent for informal economy
  rate_score = clamp(savings_rate / 0.10, 0, 1)

  # Consistency: how many days had savings?
  savings_days = count(days with savings > 0)
  consistency = savings_days / active_days

  # Trend: are savings growing?
  savings_trend = regression_slope(daily_savings_cumulative)
  trend_score = sigmoid(savings_trend * 5)

  savings_score = (rate_score * 0.4 + consistency * 0.35 + trend_score * 0.25) * 100
```

**Why it matters:** M-KOPA proved it: the single best predictor of repayment is savings behavior. Someone who saves—even KES 50/day—is fundamentally different from someone who doesn't.

---

## 4. Score Computation

### 4.1 Composite Score

```
Alama Score = Σ(pillar_score_i × weight_i)

Where weights:
  frequency      = 0.15
  revenue_trend  = 0.15
  margins        = 0.15
  diversity      = 0.10
  regularity     = 0.10
  growth         = 0.10
  expense_ctrl   = 0.10
  savings        = 0.15
  ─────────────────────
  Total          = 1.00
```

### 4.2 Confidence Score

Raw score is meaningless without confidence. Confidence comes from data quantity and quality.

```
Confidence = data_quantity_factor × data_quality_factor × consistency_factor

Where:
  data_quantity_factor = min(1.0, total_transactions / 100)
  data_quality_factor  = mean(voice_confidence_scores) × asr_word_error_rate_factor
  consistency_factor   = 1 - (gap_days / total_days)

Confidence levels:
  0.00 - 0.25: "Insufficient data"    → No score shown
  0.25 - 0.50: "Preliminary"          → Score shown with caveat
  0.50 - 0.75: "Moderate confidence"  → Score shown normally
  0.75 - 1.00: "High confidence"      → Score eligible for products
```

### 4.3 Score Lifecycle Timeline

```
Day 0  ─── No score. "Keep recording your business to build your Alama Score."
Day 7  ─── Preliminary score appears. Low confidence (~0.3). For awareness only.
Day 30 ─── Basic score. Medium confidence (~0.6). Can see trends.
Day 60 ─── Reliable score. Good confidence (~0.8). Eligible for basic products.
Day 90 ─── Full score. High confidence (~0.9). Eligible for all products.
         ─── Updates in real-time with every transaction after this.
```

### 4.4 Algorithm Implementation (Python Pseudocode)

```python
import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta

@dataclass
class PillarScore:
    name: str
    raw_value: float      # 0-100
    weight: float         # 0-1
    contributing_data: dict  # For transparency

@dataclass
class AlamaScore:
    score: float              # 0-100
    confidence: float         # 0-1
    confidence_level: str     # "insufficient" | "preliminary" | "moderate" | "high"
    pillars: list[PillarScore]
    computed_at: datetime
    data_window_days: int
    transaction_count: int

class AlamaEngine:
    def __init__(self, feature_store):
        self.features = feature_store
        self.weights = {
            'frequency': 0.15,
            'revenue_trend': 0.15,
            'margins': 0.15,
            'diversity': 0.10,
            'regularity': 0.10,
            'growth': 0.10,
            'expense_control': 0.10,
            'savings': 0.15,
        }

    def compute(self, worker_id: str) -> AlamaScore:
        """Main entry point. Computes Alama Score from feature store."""

        # 1. Determine data window based on available data
        window = self._determine_window(worker_id)

        # 2. Compute each pillar
        pillars = [
            self._frequency(window),
            self._revenue_trend(window),
            self._margins(window),
            self._diversity(window),
            self._regularity(window),
            self._growth(window),
            self._expense_control(window),
            self._savings(window),
        ]

        # 3. Weighted composite
        raw_score = sum(p.raw_value * p.weight for p in pillars)

        # 4. Confidence
        confidence = self._compute_confidence(worker_id, window)

        # 5. Apply confidence dampening (low confidence → pull toward 50)
        adjusted_score = raw_score * confidence + 50 * (1 - confidence)

        return AlamaScore(
            score=round(adjusted_score, 1),
            confidence=round(confidence, 3),
            confidence_level=self._confidence_level(confidence),
            pillars=pillars,
            computed_at=datetime.now(),
            data_window_days=window.days,
            transaction_count=self._count_transactions(worker_id, window),
        )

    def _determine_window(self, worker_id) -> timedelta:
        """Largest available window up to 90 days."""
        first_txn = self.features.first_transaction_date(worker_id)
        days_available = (datetime.now() - first_txn).days
        window_days = min(days_available, 90)
        return timedelta(days=max(window_days, 1))

    def _compute_confidence(self, worker_id, window) -> float:
        """How much to trust the score."""
        txn_count = self._count_transactions(worker_id, window)
        quantity = min(1.0, txn_count / 100)

        avg_voice_conf = self.features.avg_confidence(worker_id, window)
        quality = avg_voice_conf  # ASR confidence as proxy

        active_days = self.features.active_days(worker_id, window)
        consistency = active_days / window.days

        return quantity * quality * consistency

    def _confidence_level(self, confidence: float) -> str:
        if confidence < 0.25: return "insufficient"
        if confidence < 0.50: return "preliminary"
        if confidence < 0.75: return "moderate"
        return "high"
```

---

## 5. Offline-First Architecture

### 5.1 On-Device Computation

```
┌──────────────────────────────────────────────────────────────┐
│                    WORKER'S DEVICE                            │
│                                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐│
│  │  Voice   │──→│  Feature │──→│  Alama   │──→│  Score   ││
│  │ Recorder │   │  Store   │   │  Engine  │   │  Cache   ││
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘│
│       │                              │               │      │
│       │         ┌──────────┐         │               │      │
│       └────────→│  SQLite  │←────────┘               │      │
│                 │  Local   │←─────────────────────────┘      │
│                 └──────────┘                                 │
│                       │                                      │
│                       │ (when connected)                     │
│                       ▼                                      │
│              ┌──────────────┐                                │
│              │   Sync to    │                                │
│              │   Cloud      │                                │
│              └──────────────┘                                │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 Sync Strategy

| Data | Sync Direction | Frequency | Encryption |
|------|---------------|-----------|------------|
| Raw transactions | Device → Cloud | On connection | E2E encrypted |
| Feature summaries | Device → Cloud | Daily (batch) | E2E encrypted |
| Alama Score | Device → Cloud | On change | E2E encrypted |
| Score products/loans | Cloud → Device | On request | E2E encrypted |
| Model updates | Cloud → Device | Weekly | Signed + encrypted |

### 5.3 SQLite Schema (On-Device)

```sql
-- Raw transactions (source of truth)
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    timestamp INTEGER NOT NULL,
    type TEXT NOT NULL,          -- 'sale', 'expense', 'savings', 'withdrawal'
    amount REAL NOT NULL,
    category TEXT,
    subcategory TEXT,
    location_lat REAL,
    location_lng REAL,
    location_label TEXT,
    voice_audio_path TEXT,
    voice_confidence REAL,
    language TEXT,
    synced INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL
);

-- Daily aggregates (pre-computed for speed)
CREATE TABLE daily_aggregates (
    date TEXT NOT NULL,
    transaction_count INTEGER,
    total_revenue REAL,
    total_expenses REAL,
    total_savings REAL,
    total_cogs REAL,
    gross_margin REAL,
    net_margin REAL,
    unique_categories INTEGER,
    active_hours INTEGER,
    PRIMARY KEY (date)
);

-- Rolling windows (pre-computed)
CREATE TABLE rolling_features (
    window TEXT NOT NULL,        -- '7d', '30d', '90d'
    feature_name TEXT NOT NULL,
    feature_value REAL,
    computed_at INTEGER NOT NULL,
    PRIMARY KEY (window, feature_name)
);

-- Score history
CREATE TABLE alama_scores (
    computed_at INTEGER NOT NULL,
    score REAL NOT NULL,
    confidence REAL NOT NULL,
    confidence_level TEXT NOT NULL,
    pillar_scores TEXT NOT NULL,  -- JSON blob
    window_days INTEGER,
    transaction_count INTEGER,
    PRIMARY KEY (computed_at)
);

-- Consent ledger (immutable)
CREATE TABLE consent_log (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,        -- 'grant', 'revoke'
    recipient TEXT NOT NULL,     -- who gets the score
    scope TEXT NOT NULL,         -- 'full', 'summary', 'range'
    timestamp INTEGER NOT NULL,
    expires_at INTEGER,
    signature TEXT               -- Worker's cryptographic signature
);
```

---

## 6. Statistical Methods

### 6.1 PCA — Dimensionality Reduction

The eight pillars may be correlated (high revenue → high savings → high margins). PCA identifies the true independent factors.

```python
from sklearn.decomposition import PCA

def compute_pca_weights(pillar_matrix):
    """
    pillar_matrix: (n_workers, 8) — all pillar scores for calibration cohort
    Returns: adjusted weights that account for correlated pillars
    """
    pca = PCA(n_components=4)  # 4 components explain ~85% variance typically
    pca.fit(pillar_matrix)

    # Use loading matrix to adjust weights
    # Pillars that load heavily on PC1 (general business health) get balanced weight
    # Pillars that uniquely contribute to variance get boosted
    uniqueness = 1 - np.sum(pca.components_[:3] ** 2, axis=0)
    adjusted_weights = base_weights * (1 + uniqueness)
    adjusted_weights /= adjusted_weights.sum()

    return adjusted_weights
```

### 6.2 Logistic Regression — Default Probability

For workers who have been offered products, the model learns from outcomes:

```python
from sklearn.linear_model import LogisticRegression

def train_default_model(outcome_data):
    """
    outcome_data: historical records of workers who received products
    Features: 8 pillar scores + confidence + days_active
    Target: 1 = repaid, 0 = defaulted
    """
    X = outcome_data[['freq', 'rev', 'margin', 'diversity',
                       'regularity', 'growth', 'expense', 'savings', 'confidence']]
    y = outcome_data['repaid']

    model = LogisticRegression(C=1.0, class_weight='balanced')
    model.fit(X, y)

    # Probability of repayment = financial readiness
    return model
```

### 6.3 KDE — Risk Estimation

For workers without product history, estimate risk using kernel density estimation on the known population:

```python
from sklearn.neighbors import KernelDensity

def estimate_risk_kde(worker_features, population_features):
    """
    Where does this worker sit relative to known-good and known-bad workers?
    """
    kde_good = KernelDensity(bandwidth=0.5, kernel='gaussian')
    kde_bad  = KernelDensity(bandwidth=0.5, kernel='gaussian')

    kde_good.fit(population_features[population_features['repaid'] == 1])
    kde_bad.fit(population_features[population_features['repaid'] == 0])

    log_p_good = kde_good.score(worker_features)
    log_p_bad  = kde_bad.score(worker_features)

    # Log-likelihood ratio
    risk_ratio = np.exp(log_p_bad - log_p_good)

    # Convert to readiness score (lower risk = higher readiness)
    readiness = 100 / (1 + risk_ratio)

    return readiness
```

### 6.4 Confidence Intervals

```python
def compute_confidence_interval(score, n_observations, pillar_variance):
    """
    More data + less variance = tighter interval
    """
    from scipy import stats

    se = np.sqrt(pillar_variance / n_observations)
    ci_lower = score - 1.96 * se
    ci_upper = score + 1.96 * se

    return {
        'point_estimate': score,
        'ci_95_lower': max(0, ci_lower),
        'ci_95_upper': min(100, ci_upper),
        'standard_error': se,
        'margin_of_error': 1.96 * se,
    }
```

---

## 7. Score Application Layer

### 7.1 Credit Readiness Tiers

| Tier | Score Range | Label | Products Available |
|------|------------|-------|-------------------|
| — | < 25 or confidence < 0.25 | "Building" | Education only |
| 🌱 | 25-44 | "Starting" | Savings products, financial tips |
| 🌿 | 45-59 | "Growing" | Micro-loans up to KES 2,000 |
| 🌳 | 60-74 | "Established" | Loans up to KES 10,000, micro-insurance |
| 🏆 | 75-89 | "Thriving" | Loans up to KES 50,000, full insurance |
| ⭐ | 90-100 | "Excellent" | Premium products, lowest rates |

### 7.2 Loan Pre-Qualification

```python
def pre_qualify(alama_score: AlamaScore) -> dict:
    """Determine what a worker qualifies for."""

    if alama_score.confidence_level == "insufficient":
        return {"eligible": False, "reason": "Not enough data yet. Keep recording!"}

    # Base amount from score
    base_amount = alama_score.score * 100  # Score 50 → KES 5,000 base

    # Confidence adjustment
    adjusted_amount = base_amount * alama_score.confidence

    # Margin safety (don't lend more than 30% of monthly revenue)
    monthly_revenue = alama_score.pillars['revenue'].contributing_data.get('monthly_avg', 0)
    revenue_cap = monthly_revenue * 0.30

    max_loan = min(adjusted_amount, revenue_cap)

    # Interest rate: inverse relationship with score
    # Score 90+ → 8% monthly, Score 30 → 25% monthly
    base_rate = 0.25 - (alama_score.score / 100 * 0.17)
    rate = max(0.08, base_rate) * (1 + (1 - alama_score.confidence) * 0.5)

    return {
        "eligible": max_loan >= 500,  # Minimum KES 500
        "max_loan_kes": round(max_loan / 100) * 100,  # Round to nearest 100
        "monthly_rate_pct": round(rate * 100, 1),
        "confidence": alama_score.confidence_level,
        "factors": _explain_score(alama_score),
    }
```

### 7.3 Insurance Eligibility

```python
def insurance_eligibility(alama_score: AlamaScore) -> dict:
    """Micro-insurance unlock based on Alama Score."""

    products = []

    if alama_score.score >= 45 and alama_score.confidence >= 0.5:
        products.append({
            "name": "Health Cover Lite",
            "premium_kes_month": 200,
            "coverage_kes": 10_000,
            "description": "Covers basic hospital visits",
        })

    if alama_score.score >= 60 and alama_score.confidence >= 0.6:
        products.append({
            "name": "Business Protection",
            "premium_kes_month": 350,
            "coverage_kes": 25_000,
            "description": "Covers stock loss from fire, theft, or flooding",
        })

    if alama_score.score >= 75 and alama_score.confidence >= 0.75:
        products.append({
            "name": "Full Cover",
            "premium_kes_month": 500,
            "coverage_kes": 50_000,
            "description": "Comprehensive health + business coverage",
        })

    return {"eligible_products": products}
```

### 7.4 Transparency — Score Explanation

Every score comes with a human-readable explanation:

```python
def _explain_score(alama: AlamaScore) -> list[dict]:
    """Generate actionable, transparent explanations."""

    explanations = []

    for pillar in sorted(alama.pillars, key=lambda p: p.raw_value * p.weight, reverse=True):
        if pillar.raw_value >= 70:
            tone = "strength"
            emoji = "✅"
        elif pillar.raw_value >= 40:
            tone = "neutral"
            emoji = "➖"
        else:
            tone = "improvement"
            emoji = "📈"

        explanations.append({
            "factor": pillar.name,
            "score": pillar.raw_value,
            "impact": round(pillar.raw_value * pillar.weight, 1),
            "tone": tone,
            "emoji": emoji,
            "message": _pillar_message(pillar),
            "tip": _improvement_tip(pillar),
        })

    return explanations

# Example output:
# [
#   {"factor": "Savings", "score": 82, "impact": 12.3, "emoji": "✅",
#    "message": "You save consistently — KES 150/day average. This is your biggest strength.",
#    "tip": "Keep saving! Even KES 20 more per day would improve your score."},
#   {"factor": "Product Diversity", "score": 35, "impact": 3.5, "emoji": "📈",
#    "message": "Most of your income comes from one product (tomatoes).",
#    "tip": "Try adding 1-2 more products. Even selling onions alongside tomatoes helps."}
# ]
```

---

## 8. Privacy & Trust Architecture

### 8.1 Data Ownership Model

```
┌─────────────────────────────────────────────────────────┐
│                    WORKER'S DEVICE                       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │              LOCAL SCORE VAULT                   │   │
│  │                                                  │   │
│  │  Raw data:     Worker owns 100%                  │   │
│  │  Features:     Computed locally, never leaves    │   │
│  │                without consent                   │   │
│  │  Alama Score:  Computed locally, shared only     │   │
│  │                via explicit consent action        │   │
│  │                                                  │   │
│  │  ┌────────────────────────────────────────────┐ │   │
│  │  │  CONSENT GATE                              │ │   │
│  │  │                                            │ │   │
│  │  │  "Msaidizi wants to share your Alama       │ │   │
│  │  │   Score (72) with M-KOPA for loan           │ │   │
│  │  │   qualification."                          │ │   │
│  │  │                                            │ │   │
│  │  │  [ Share Score ]  [ Share Summary Only ]    │ │   │
│  │  │  [ Decline ]                               │ │   │
│  │  └────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 8.2 Consent Protocol

```python
class ConsentManager:
    """Immutable consent ledger. Every grant/revoke is logged and signed."""

    def grant(self, recipient: str, scope: str, expires_in_days: int = 30):
        """
        Worker explicitly shares their score.
        scope: 'full' (exact score + all pillars)
               'summary' (tier only, e.g., "Established")
               'range' (score range, e.g., "60-75")
        """
        consent = {
            'id': generate_uuid(),
            'action': 'grant',
            'recipient': recipient,
            'scope': scope,
            'timestamp': now(),
            'expires_at': now() + timedelta(days=expires_in_days),
            'worker_signature': sign_with_device_key(...)
        }
        self._append_to_ledger(consent)
        return consent

    def revoke(self, consent_id: str):
        """Worker can revoke at any time."""
        revocation = {
            'id': generate_uuid(),
            'action': 'revoke',
            'revokes': consent_id,
            'timestamp': now(),
            'worker_signature': sign_with_device_key(...)
        }
        self._append_to_ledger(revocation)

    def get_active_consents(self) -> list:
        """What is currently being shared and with whom."""
        return [c for c in self.ledger
                if c['action'] == 'grant'
                and c['expires_at'] > now()
                and not self._is_revoked(c['id'])]
```

### 8.3 Privacy Guarantees

| Guarantee | Implementation |
|-----------|---------------|
| **Worker owns their data** | All raw data stored on-device only |
| **Score computed locally** | Engine runs on-device, no server-side score computation |
| **Explicit consent for sharing** | Consent gate UI before any data leaves device |
| **Granular sharing** | Share full score, summary, or range — worker chooses |
| **Revocable** | Worker can revoke sharing at any time |
| **Audit trail** | Immutable consent ledger, worker can review all grants |
| **No third-party sale** | Architecturally impossible — Msaidizi never has the raw data to sell |
| **Expiry by default** | All consents expire (default 30 days), must be re-granted |
| **No score without explanation** | Every score includes transparent factor breakdown |

---

## 9. API Design

### 9.1 On-Device API (Internal)

```python
class AlamaAPI:
    """Internal API used by the Msaidizi app."""

    def get_score(self) -> AlamaScore:
        """Current Alama Score with full breakdown."""

    def get_score_history(self, days: int = 30) -> list[AlamaScore]:
        """How the score has changed over time."""

    def get_explanation(self) -> list[dict]:
        """Human-readable factor breakdown with improvement tips."""

    def get_pre_qualification(self) -> dict:
        """What loans/products the worker qualifies for right now."""

    def get_insurance_eligibility(self) -> dict:
        """Insurance products available based on current score."""

    def share_score(self, recipient: str, scope: str) -> Consent:
        """Share score with a specific recipient (e.g., lender)."""

    def revoke_sharing(self, consent_id: str) -> None:
        """Stop sharing with a recipient."""

    def get_active_shares(self) -> list[Consent]:
        """Who currently has access to the score."""

    def simulate(self, changes: dict) -> AlamaScore:
        """What-if: 'If I save KES 100 more per day, what happens to my score?'"""
```

### 9.2 Sync API (Cloud — Optional)

```python
# Only used when worker opts into cloud sync or product integration

POST /api/v1/score/sync
  Headers: Authorization: Bearer <device_token>
  Body: {
    "worker_id": "encrypted_id",
    "score": 72.3,
    "confidence": 0.85,
    "tier": "established",
    "consent_proof": { ... },  # Cryptographic proof of consent
    "timestamp": "2026-07-24T08:30:00+03:00"
  }

POST /api/v1/score/verify  # Lender verifies a shared score
  Body: {
    "consent_id": "uuid",
    "recipient_id": "mkopa",
    "scope": "summary"
  }
  Response: {
    "valid": true,
    "tier": "established",
    "expires_at": "2026-08-24T08:30:00+03:00",
    "confidence_level": "high"
  }
```

---

## 10. Regulatory & Ethical Safeguards

### 10.1 Regulatory Positioning

```
┌──────────────────────────────────────────────────────────┐
│  CREDIT SCORE (regulated)    │  ALAMA SCORE (our design) │
│  ─────────────────────────   │  ──────────────────────── │
│  Uses third-party data       │  Uses own voice data only │
│  Sold to lenders             │  Shared by worker choice  │
│  Bureau owns the score       │  Worker owns the score    │
│  Can deny based on history   │  Shows path to improve    │
│  Opaque algorithm            │  Fully transparent        │
│  Requires CBK license        │  Financial literacy tool  │
│  Affects credit decisions    │  Informs the worker       │
└──────────────────────────────────────────────────────────┘
```

### 10.2 Ethical Design Choices

1. **No dark patterns:** Score never creates anxiety. "Building" tier is framed positively.
2. **Improvement-oriented:** Every low-scoring factor comes with a specific, actionable tip.
3. **No gamification of risk:** We don't encourage workers to take on debt to "improve" their score.
4. **Bias monitoring:** Track score distributions across demographics to detect systematic bias.
5. **Right to explanation:** Worker can always ask "why is my score X?" and get a clear answer.
6. **Graceful degradation:** If voice data is poor quality, we say "insufficient data" rather than penalize.

### 10.3 Bias Detection

```python
def bias_audit(scores: list[AlamaScore], demographics: dict) -> dict:
    """
    Run quarterly. Check for systematic disparities.
    Report to ethics board. Fix before they become problems.
    """
    # Group by language (proxy for region/ethnicity)
    lang_groups = group_by(scores, key=lambda s: s.language)

    # Check: are score distributions significantly different across languages?
    # If yes, investigate — is it behavioral difference or model bias?

    # Check: does ASR quality vary by language?
    # If yes, language-specific ASR training may be needed

    # Check: are certain product categories systematically scored lower?
    # If yes, category normalization may be needed

    return audit_report
```

---

## 11. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)

- [ ] SQLite schema implementation on-device
- [ ] Basic feature extraction from structured transactions
- [ ] Simple frequency + revenue + savings scoring (3 pillars)
- [ ] Score computation with confidence
- [ ] Basic explanation generation

### Phase 2: Full Engine (Weeks 5-8)

- [ ] All 8 pillars implemented
- [ ] Rolling window aggregation
- [ ] PCA weight calibration
- [ ] Score lifecycle (7d/30d/90d milestones)
- [ ] Consent ledger

### Phase 3: Intelligence (Weeks 9-12)

- [ ] Logistic regression model training (when outcome data available)
- [ ] KDE risk estimation
- [ ] Confidence intervals
- [ ] What-if simulation engine
- [ ] Bias audit framework

### Phase 4: Integration (Weeks 13-16)

- [ ] Pre-qualification engine
- [ ] Insurance eligibility engine
- [ ] Sync API for lender integration
- [ ] Score verification protocol
- [ ] Partner onboarding (M-KOPA, insurers)

---

## 12. Key Metrics

| Metric | Target | Why |
|--------|--------|-----|
| Workers with score > 0 | 80% of active users in 90 days | Adoption |
| Mean confidence level | > 0.6 at Day 30 | Data quality |
| Score-update latency | < 2 seconds after transaction | Responsiveness |
| Explanation comprehension | > 70% understand their score in user testing | Transparency |
| Consent grant rate | > 60% when offered a product | Trust |
| False-negative rate (denied workers who would repay) | < 15% | Fairness |
| False-positive rate (approved workers who default) | < 10% | Risk |

---

## Appendix A: Score Visualization (for Worker UI)

```
┌─────────────────────────────────────────────┐
│         YOUR ALAMA SCORE                    │
│                                             │
│              ████████ 72/100                │
│              🌳 Established                 │
│                                             │
│  Confidence: ████████████░░ 85%             │
│                                             │
│  ─────────────────────────────────────────  │
│                                             │
│  ✅ Savings         ████████░░ 82  (+12.3) │
│     You save KES 150/day on average.        │
│     💡 Even KES 20 more/day would help.     │
│                                             │
│  ✅ Frequency       ███████░░░ 78  (+11.7) │
│     You record transactions 6 days/week.    │
│     💡 Record on Sundays too!               │
│                                             │
│  ➖ Revenue         ██████░░░░ 65  (+9.8)  │
│     Your income is steady but not growing.  │
│     💡 Try reaching 1 new customer/week.    │
│                                             │
│  ➖ Margins         █████░░░░░ 58  (+8.7)  │
│     Your profit margin is around 15%.       │
│     💡 Can you negotiate better stock       │
│        prices?                              │
│                                             │
│  📈 Diversity       ███░░░░░░░ 35  (+3.5)  │
│     Most income comes from one product.     │
│     💡 Add onions or tomatoes alongside     │
│        your main product.                   │
│                                             │
│  ─────────────────────────────────────────  │
│                                             │
│  🎯 YOU QUALIFY FOR:                        │
│     • Loan up to KES 5,000                  │
│     • Rate: 15% monthly                     │
│     • Health Cover Lite (KES 200/month)     │
│                                             │
│  [ See Loan Details ]  [ Share My Score ]   │
└─────────────────────────────────────────────┘
```

---

*Design v1.0 — Alama Score Engine for Msaidizi*
*Engineered for the informal economy. Owned by the worker.*
