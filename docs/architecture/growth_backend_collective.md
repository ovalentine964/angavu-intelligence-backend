# Angavu Backend Collective Intelligence System

## Design Philosophy

**"Every transaction teaches the system. Every worker makes every other worker smarter."**

The Angavu backend is not a static service — it is a learning organism. Each of the 50 million Jua Kali workers contributes a data point. Aggregated, anonymized, and modeled, these data points create intelligence that no single worker could generate alone. This document designs the feedback loops that make the system compound-smart.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ANGAVU COLLECTIVE INTELLIGENCE                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Workers     │  │  Transaction │  │  Outcome     │              │
│  │   (50M+)      │──▶  Stream      │──▶  Tracker     │              │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘              │
│                           │                  │                      │
│                           ▼                  ▼                      │
│  ┌─────────────────────────────────────────────────────┐           │
│  │              PRIVACY- PRESERVING LAYER               │           │
│  │   Differential Privacy │ K-Anonymity │ Federated     │           │
│  └──────────────────────┬──────────────────────────────┘           │
│                         │                                           │
│           ┌─────────────┼─────────────┐                            │
│           ▼             ▼             ▼                             │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐                   │
│  │ Market       │ │ Credit   │ │ Distribution │                    │
│  │ Pattern      │ │ Model    │ │ Intelligence │                    │
│  │ Mining       │ │ Engine   │ │ (Soko Pulse) │                    │
│  └──────┬───────┘ └────┬─────┘ └──────┬───────┘                   │
│         │              │               │                            │
│         ▼              ▼               ▼                            │
│  ┌──────────────┐ ┌──────────┐ ┌──────────────┐                   │
│  │ Economic     │ │ Cross-   │ │ FMCG Data    │                    │
│  │ Indicator    │ │ Worker   │ │ Products     │                    │
│  │ Models       │ │ Learning │ │ (Revenue)    │                    │
│  └──────┬───────┘ └────┬─────┘ └──────┬───────┘                   │
│         │              │               │                            │
│         └──────────────┼───────────────┘                            │
│                        ▼                                            │
│              ┌──────────────────┐                                   │
│              │   Insights back  │                                   │
│              │   to Workers     │                                   │
│              └──────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Market Pattern Mining

### Problem
1,000 mama mbogas in Nairobi each see their own slice of the market. None see the whole picture. The backend can.

### Data Ingestion Pipeline

```
Worker Transaction → Event Stream → Pattern Mining Engine
     (POS/SMS)         (Kafka)         (Spark/Flink)
```

**Transaction Event Schema:**
```json
{
  "event_id": "uuid-v4",
  "worker_id": "hashed-anonymized-id",
  "timestamp": "2026-07-25T10:30:00+03:00",
  "region": "nairobi-eastlands",
  "product_category": "vegetables",
  "product_subcategory": "tomatoes",
  "quantity": 2.5,
  "unit": "kg",
  "unit_price": 120,
  "currency": "KES",
  "payment_method": "mpesa",
  "customer_type": "walk-in",
  "weather_condition": "sunny",
  "day_of_week": "thursday"
}
```

### Pattern Discovery Engine

**Stage 1: Real-Time Aggregation (Flink)**
- Rolling 1-hour, 24-hour, 7-day, 30-day windows
- Aggregation dimensions: region × product × time
- Metrics: volume, avg price, price volatility, demand velocity

```python
# Simplified Flink-style aggregation
class MarketAggregator:
    def __init__(self):
        self.windows = {
            '1h': TumblingWindow(hours=1),
            '24h': SlidingWindow(hours=24, slide=hours=1),
            '7d': SlidingWindow(days=7, slide=days=1),
            '30d': SlidingWindow(days=30, slide=days=1)
        }
    
    def process_event(self, event: TransactionEvent):
        for window_name, window in self.windows.items():
            bucket = window.get_bucket(event.timestamp)
            key = f"{event.region}:{event.product_category}"
            
            self.state[key][bucket].update(
                volume=event.quantity,
                revenue=event.quantity * event.unit_price,
                price=event.unit_price,
                count=1
            )
            
            # Emit aggregates for downstream
            if window.is_complete(bucket):
                yield MarketAggregate(
                    key=key,
                    window=window_name,
                    metrics=self.state[key][bucket].snapshot()
                )
```

**Stage 2: Trend Detection (Batch + Streaming Hybrid)**

| Pattern Type | Detection Method | Latency | Use Case |
|---|---|---|---|
| Price spikes | Z-score > 2.5 on 7d rolling mean | Real-time | Worker alerts |
| Seasonal trends | STL decomposition on 90d+ data | Daily | Forecasting |
| Demand shifts | Change-point detection (PELT) | Hourly | Inventory advice |
| Regional correlations | Cross-correlation matrix | Weekly | Distribution planning |
| New product emergence | Novel category frequency threshold | Daily | Market discovery |

**Stage 3: Anonymization Before Storage**

```python
class DifferentialPrivacyAggregator:
    """
    Ensures no individual worker's data can be reverse-engineered
    from aggregate statistics.
    """
    def __init__(self, epsilon=1.0, delta=1e-5):
        self.epsilon = epsilon  # Privacy budget
        self.delta = delta
    
    def privatize_count(self, true_count: int) -> int:
        """Add Laplacian noise to counts."""
        sensitivity = 1
        scale = sensitivity / self.epsilon
        noise = np.random.laplace(0, scale)
        return max(0, int(true_count + noise))
    
    def privatize_mean(self, values: List[float]) -> float:
        """Noisy mean with bounded sensitivity."""
        clipped = np.clip(values, self.lower_bound, self.upper_bound)
        true_mean = np.mean(clipped)
        sensitivity = (self.upper_bound - self.lower_bound) / len(values)
        noise = np.random.laplace(0, sensitivity / self.epsilon)
        return true_mean + noise
    
    def k_anonymize(self, group: pd.DataFrame, k: int = 50) -> pd.DataFrame:
        """Suppress groups smaller than k workers."""
        group_sizes = group.groupby(['region', 'product']).size()
        valid_groups = group_sizes[group_sizes >= k].index
        return group.set_index(['region', 'product']).loc[valid_groups].reset_index()
```

### Nairobi Tomato Example

```
Input:  1,000 mama mbogas selling tomatoes across Nairobi
        → 15,000 tomato transactions/day
        → aggregated to 50 Nairobi sub-regions

Output: "Tomato prices in Eastlands are 15% higher than Westlands.
         Trend: 8% week-over-week increase.
         Predicted: prices will normalize in 3-5 days based on
         historical seasonal pattern.
         Recommendation: Buy 2-day stock, not 5-day."
```

### Implementation Priority
- **Phase 1 (Month 1-3):** Real-time aggregation, basic alerts
- **Phase 2 (Month 4-6):** Seasonal forecasting, regional correlation
- **Phase 3 (Month 7-12):** Predictive pricing, anomaly detection

---

## 2. Credit Model Evolution (Alama Score)

### The Learning Loop

```
Worker uses Angavu → Transactions recorded → Features extracted →
Score computed → Loan issued → Repayment tracked → Model retrained →
Better scores for next worker
```

### Feature Engineering Pipeline

**Raw Transaction → Credit Features:**

```python
class AlamaFeatureExtractor:
    def extract(self, worker_id: str, lookback_days: int = 180) -> dict:
        transactions = self.get_transactions(worker_id, lookback_days)
        
        return {
            # Volume features
            'total_transactions': len(transactions),
            'daily_avg_transactions': len(transactions) / lookback_days,
            'transaction_trend': self._linear_trend(transactions),
            
            # Revenue features
            'total_revenue': sum(t.revenue for t in transactions),
            'daily_avg_revenue': self._daily_average(transactions),
            'revenue_volatility': self._coefficient_of_variation(transactions),
            'revenue_growth_rate': self._growth_rate(transactions),
            
            # Consistency features
            'active_days_ratio': self._active_days(transactions) / lookback_days,
            'longest_streak': self._max_active_streak(transactions),
            'days_since_last_transaction': self._days_since_last(transactions),
            
            # Diversity features
            'product_diversity': len(set(t.product for t in transactions)),
            'customer_diversity': self._unique_customers(transactions),
            'payment_method_diversity': len(set(t.payment_method for t in transactions)),
            
            # Behavioral features
            'avg_transaction_size': np.mean([t.revenue for t in transactions]),
            'peak_hour_consistency': self._peak_hour_stability(transactions),
            'weekend_ratio': self._weekend_activity_ratio(transactions),
            
            # Network features (anonymized)
            'supplier_count': self._unique_suppliers(worker_id),
            'customer_return_rate': self._repeat_customer_ratio(transactions),
            
            # External features
            'mpesa_balance_trend': self._mpesa_trend(worker_id),
            'region_economic_index': self._region_index(worker_id),
        }
```

### Model Architecture

**Ensemble Approach:**

```python
class AlamaScoreModel:
    """
    Ensemble of gradient boosting + neural network + logistic regression.
    Each model captures different signal patterns.
    """
    def __init__(self):
        self.models = {
            'xgboost': XGBClassifier(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8
            ),
            'neural_net': self._build_nn(),
            'logistic': LogisticRegression(C=1.0, max_iter=1000),
        }
        self.weights = {'xgboost': 0.5, 'neural_net': 0.3, 'logistic': 0.2}
        self.calibration = IsotonicRegression()
    
    def _build_nn(self):
        return tf.keras.Sequential([
            tf.keras.layers.Dense(128, activation='relu', input_shape=(30,)),
            tf.keras.layers.Dropout(0.3),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(32, activation='relu'),
            tf.keras.layers.Dense(1, activation='sigmoid')
        ])
    
    def predict(self, features: dict) -> float:
        """Returns calibrated probability of repayment (0-1)."""
        X = self._vectorize(features)
        
        raw_predictions = []
        for name, model in self.models.items():
            pred = model.predict_proba(X)[:, 1] if hasattr(model, 'predict_proba') else model.predict(X)
            raw_predictions.append(pred * self.weights[name])
        
        ensemble_pred = sum(raw_predictions)
        
        # Calibrate to actual observed repayment rates
        calibrated = self.calibration.predict(ensemble_pred)
        
        return float(calibrated[0])
```

### Continuous Learning Pipeline

```
┌─────────────────────────────────────────────────────────┐
│              ALAMA MODEL RETRAINING CYCLE                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Daily: Feature store update (new transactions)         │
│  Weekly: Outcome labeling (loans marked repaid/default) │
│  Monthly: Full model retrain on accumulated data        │
│  Quarterly: Architecture review, feature engineering    │
│                                                         │
│  Feedback signals:                                      │
│  ├── Loan approved → repayment (positive)               │
│  ├── Loan approved → default (negative)                 │
│  ├── Loan denied → worker continues earning (indirect)  │
│  └── Score improved → worker accesses better terms      │
└─────────────────────────────────────────────────────────┘
```

**Retraining Logic:**

```python
class ModelRetrainer:
    def __init__(self, min_new_samples=1000, performance_threshold=0.02):
        self.min_new_samples = min_new_samples
        self.performance_threshold = performance_threshold
    
    def should_retrain(self) -> bool:
        """Check if retraining conditions are met."""
        new_outcomes = self.count_new_outcomes_since_last_train()
        current_auc = self.evaluate_current_model()
        baseline_auc = self.get_last_train_auc()
        
        return (
            new_outcomes >= self.min_new_samples and
            (baseline_auc - current_auc) > self.performance_threshold
        )
    
    def retrain(self):
        """Champion-challenger retraining."""
        # Get all labeled data
        X, y = self.get_training_data()
        
        # Train challenger
        challenger = AlamaScoreModel()
        challenger.fit(X_train, y_train)
        
        # Evaluate on holdout
        champion_auc = self.current_model.evaluate(X_test, y_test)
        challenger_auc = challenger.evaluate(X_test, y_test)
        
        # Promote challenger only if better
        if challenger_auc > champion_auc + 0.005:  # Minimum improvement
            self.deploy_model(challenger)
            self.log_promotion(champion_auc, challenger_auc)
        else:
            self.log_retention(champion_auc, challenger_auc)
    
    def track_calibration(self):
        """Ensure predicted probabilities match observed rates."""
        predictions = self.current_model.predict_batch(self.recent_features)
        outcomes = self.recent_outcomes
        
        # Bin predictions and compare with actuals
        bins = pd.cut(predictions, bins=10)
        calibration_df = pd.DataFrame({
            'predicted': predictions,
            'actual': outcomes,
            'bin': bins
        }).groupby('bin').agg({'predicted': 'mean', 'actual': 'mean'})
        
        # If calibration drift exceeds threshold, recalibrate
        mae = np.mean(np.abs(calibration_df.predicted - calibration_df.actual))
        if mae > 0.05:
            self.recalibrate(predictions, outcomes)
```

### Model Improvement Over Time

| Workers | Transactions | AUC-ROC | Key Insight |
|---|---|---|---|
| 1,000 | 50K | 0.65 | Basic volume features work |
| 10,000 | 500K | 0.72 | Consistency features become predictive |
| 100,000 | 5M | 0.78 | Network effects emerge |
| 1,000,000 | 50M | 0.83 | Regional patterns stabilize |
| 10,000,000 | 500M | 0.87 | Rare event prediction improves |

**Key Insight:** The model doesn't just get more data — it gets *better features*. At 100K workers, "how does this worker compare to similar workers in their region" becomes a powerful signal that doesn't exist at 1K workers.

---

## 3. Distribution Intelligence (Soko Pulse)

### The Data Flywheel

```
More Workers → Better Demand Data → More Valuable Insights →
FMCG Companies Pay → Revenue Funds Better Models →
Better Models → Better Worker Recommendations → More Workers
```

### Signal Collection Architecture

```python
class SokoPulseCollector:
    """
    Collects and structures demand signals for FMCG intelligence.
    """
    def collect_demand_signals(self, region: str, time_range: TimeRange) -> DemandSnapshot:
        transactions = self.get_region_transactions(region, time_range)
        
        return DemandSnapshot(
            region=region,
            timestamp=time_range.end,
            
            # What's selling
            top_products=self._rank_products(transactions, top_n=20),
            emerging_products=self._detect_emerging(transactions),
            declining_products=self._detect_declining(transactions),
            
            # How it's selling
            avg_basket_size=self._avg_basket(transactions),
            price_sensitivity=self._price_elasticity(transactions),
            brand_switching=self._brand_switching_matrix(transactions),
            
            # When it's selling
            peak_hours=self._hourly_distribution(transactions),
            day_of_week_pattern=self._dow_distribution(transactions),
            pay_cycle_correlation=self._mpesa_payday_pattern(transactions),
            
            # Where it's selling
            geographic_hotspots=self._hotspot_grid(transactions),
            transport_corridors=self._corridor_analysis(transactions),
            
            # Confidence metrics
            sample_size=len(transactions),
            worker_coverage=self._unique_workers(transactions),
            data_completeness=self._completeness_score(transactions),
        )
```

### FMCG Data Products

**Tier 1: Market Pulse (Basic)**
- Regional demand rankings
- Price benchmarks
- Volume trends
- Price: $500/month per region

**Tier 2: Consumer Insights (Standard)**
- Brand switching patterns
- Price elasticity curves
- Pay-cycle demand patterns
- Competitive positioning
- Price: $2,000/month per region

**Tier 3: Predictive Intelligence (Premium)**
- Demand forecasting (30/60/90 day)
- New product opportunity detection
- Distribution gap analysis
- Real-time alerts on market shifts
- Price: $10,000/month per region

**Tier 4: Custom Analytics (Enterprise)**
- Bespoke analysis teams
- API access to real-time data
- Integration with client supply chain
- Price: $50,000+/month

### Revenue → Intelligence Feedback Loop

```python
class IntelligenceFlywheel:
    """
    Revenue from FMCG clients funds model improvements
    that benefit workers, which attracts more workers,
    which generates more data, which increases data value.
    """
    def allocate_revenue(self, monthly_revenue: float) -> dict:
        return {
            'model_improvement': monthly_revenue * 0.30,  # R&D
            'worker_incentives': monthly_revenue * 0.25,  # Data quality bonuses
            'infrastructure': monthly_revenue * 0.25,      # Compute/storage
            'operations': monthly_revenue * 0.20,          # Team/overhead
        }
    
    def worker_data_bonus(self, worker_id: str, data_quality_score: float) -> float:
        """
        Workers with consistent, high-quality data get bonuses.
        This incentivizes continued participation.
        """
        base_bonus = 50  # KES per month
        quality_multiplier = min(data_quality_score, 2.0)  # Cap at 2x
        return base_bonus * quality_multiplier
```

### FMCG Integration Example

```
Unilever wants to know: "How is OMO performing vs. new
local detergent brands in Nairobi's informal settlements?"

Soko Pulse Answer (from 5,000 mama mbogas):
- OMO market share: 45% → 38% (6-month decline)
- Local brand 'Sparkle' market share: 8% → 18% (rapid growth)
- Price gap: OMO @ 180 KES vs Sparkle @ 120 KES
- Switching trigger: 65% switch at >20% price difference
- Pay-cycle pattern: OMO bought on 1st-3rd (payday), Sparkle on 15th-20th
- Recommendation: Launch 150 KES promotional SKU or risk further erosion

Revenue: Unilever pays $15,000/month for this intelligence.
Worker benefit: Better stock recommendations, data bonuses.
```

---

## 4. Economic Indicator Refinement

### Ground-Truth Economic Data

Official GDP and inflation statistics in East Africa are:
- **Delayed** by 1-3 months
- **Estimated** from limited survey samples
- **Revised** significantly after initial release
- **Averaged** across diverse economic realities

Angavu workers provide real-time ground truth.

### Indicator Construction

```python
class EconomicIndicatorEngine:
    """
    Constructs real-time economic indicators from worker transaction data.
    """
    
    def compute_inflation_index(self, region: str, basket: List[str]) -> dict:
        """
        Consumer price index from actual transactions.
        basket: ['maize_flour', 'cooking_oil', 'soap', 'tomatoes', ...]
        """
        current_prices = self.get_current_prices(region, basket)
        baseline_prices = self.get_baseline_prices(region, basket, months_ago=12)
        
        # Laspeyres-style index
        price_ratios = []
        for item in basket:
            if item in current_prices and item in baseline_prices:
                current = current_prices[item]
                baseline = baseline_prices[item]
                weight = self.get_expenditure_weight(region, item)
                price_ratios.append((current / baseline) * weight)
        
        cpi = sum(price_ratios) / sum(
            self.get_expenditure_weight(region, item) 
            for item in basket 
            if item in current_prices
        ) * 100
        
        return {
            'cpi': cpi,
            'inflation_rate': cpi - 100,
            'confidence': self._compute_confidence(region, basket),
            'sample_size': self._count_contributors(region),
            'official_comparison': self._compare_with_knbs(region, cpi),
        }
    
    def compute_economic_activity_index(self, region: str) -> dict:
        """
        Proxy for regional GDP from transaction volume and patterns.
        """
        current_month = self.get_monthly_stats(region, offset=0)
        prev_month = self.get_monthly_stats(region, offset=1)
        prev_year = self.get_monthly_stats(region, offset=12)
        
        return {
            'transaction_volume_index': (
                current_month.total_volume / prev_year.total_volume
            ) * 100,
            'revenue_index': (
                current_month.total_revenue / prev_year.total_revenue
            ) * 100,
            'worker_activity_index': (
                current_month.active_workers / prev_year.active_workers
            ) * 100,
            'new_business_formation': current_month.new_workers,
            'business_closures': self._detect_inactive_businesses(region),
            'payment_digitization_rate': (
                current_month.mpesa_transactions / current_month.total_transactions
            ),
        }
```

### Calibration Against Official Statistics

```python
class IndicatorCalibrator:
    """
    Calibrates Angavu indicators against KNBS (Kenya National Bureau of Statistics)
    official figures when they become available.
    """
    
    def calibrate_inflation(self):
        # Get KNBS official inflation when released (monthly, ~15th of following month)
        knbs_inflation = self.fetch_knbs_data('cpi', latest=True)
        angavu_estimate = self.engine.compute_inflation_index('nairobi', BASKET)
        
        # Compute bias and adjust
        historical_errors = self.get_historical_errors()  # Angavu vs KNBS
        bias = np.mean(historical_errors)
        std = np.std(historical_errors)
        
        # Bayesian update of calibration parameters
        self.calibration_params = {
            'bias': self.ewma_update(self.calibration_params['bias'], 
                                      angavu_estimate - knbs_inflation),
            'scale': self.ewma_update(self.calibration_params['scale'],
                                       knbs_inflation / angavu_estimate),
            'confidence_interval': 1.96 * std,
        }
        
        return {
            'angavu_raw': angavu_estimate,
            'angavu_calibrated': self.apply_calibration(angavu_estimate),
            'knbs_official': knbs_inflation,
            'error': angavu_estimate - knbs_inflation,
            'cumulative_accuracy': self.cumulative_accuracy(),
        }
```

### Improvement Over Time

| Workers (Kenya) | Coverage | CPI Accuracy vs KNBS | Lead Time |
|---|---|---|---|
| 10,000 | 0.1% of informal sector | ±3.5% | 0 days |
| 100,000 | 1% of informal sector | ±1.8% | 0 days |
| 1,000,000 | 10% of informal sector | ±0.9% | 0 days |
| 5,000,000 | 50% of informal sector | ±0.4% | 0 days |

**Key advantage:** Angavu inflation data is *real-time*. KNBS releases lag by 45+ days. Even with ±1% error, Angavu data is more actionable than 45-day-old official data.

### Multi-Country Expansion

```
Kenya (KNBS)  ←→  Angavu Kenya data  ──┐
Tanzania (NBS) ←→  Angavu Tanzania data ─┼→ East Africa Economic Pulse
Uganda (UBOS)  ←→  Angavu Uganda data  ─┘

Cross-border indicators:
- Currency-adjusted price comparisons
- Trade flow patterns
- Regional economic integration index
```

---

## 5. Cross-Worker Learning

### The Challenge
How do we propagate successful strategies from one worker to thousands, without revealing any individual's private business data?

### Solution: Federated Pattern Discovery

```python
class CrossWorkerLearning:
    """
    Discovers successful patterns from aggregate behavior
    without exposing individual worker data.
    """
    
    def discover_success_patterns(self, region: str) -> List[Pattern]:
        """
        Find what successful workers do differently.
        'Success' = consistent revenue growth + loan repayment.
        """
        # Define success cohorts
        workers = self.get_active_workers(region, min_days=90)
        
        success_scores = []
        for w in workers:
            score = self._compute_success_score(w)
            success_scores.append((w.id, score))
        
        # Top quartile vs bottom quartile
        success_scores.sort(key=lambda x: x[1], reverse=True)
        n = len(success_scores)
        top_quartile = [w_id for w_id, _ in success_scores[:n//4]]
        bottom_quartile = [w_id for w_id, _ in success_scores[-n//4:]]
        
        # Compare feature distributions (anonymized)
        patterns = []
        top_features = self._aggregate_features(top_quartile)
        bottom_features = self._aggregate_features(bottom_quartile)
        
        for feature_name in top_features:
            top_val = top_features[feature_name]
            bottom_val = bottom_features[feature_name]
            
            if self._is_significant_difference(top_val, bottom_val):
                patterns.append(Pattern(
                    feature=feature_name,
                    successful_workers_value=top_val,
                    average_workers_value=bottom_val,
                    effect_size=self._cohens_d(top_val, bottom_val),
                    sample_size=len(top_quartile),
                ))
        
        return patterns
    
    def _compute_success_score(self, worker) -> float:
        """Composite success metric."""
        return (
            0.3 * worker.revenue_growth_rate +
            0.25 * worker.transaction_consistency +
            0.2 * worker.loan_repayment_rate +
            0.15 * worker.customer_retention_rate +
            0.1 * worker.business_survival_months / 12
        )
```

### Pattern Propagation Without Data Leakage

**Approach 1: Aggregate Recommendations**

```python
class RecommendationEngine:
    """
    Generates recommendations from aggregate patterns,
    never from individual data points.
    """
    
    def generate_insight(self, worker: Worker) -> Insight:
        # Find similar workers (by region, product type, tenure)
        similar_workers = self.find_cohort(worker, min_size=50)  # k-anonymity
        
        # Only generate insight if cohort is large enough
        if len(similar_workers) < 50:
            return Insight(type='insufficient_data')
        
        # Get aggregate performance metrics
        cohort_stats = self.aggregate_stats(similar_workers)
        worker_percentile = self.compute_percentile(worker, cohort_stats)
        
        recommendations = []
        
        # Example: Pricing insight
        if worker_percentile['pricing'] < 50:
            optimal_price = cohort_stats['optimal_price'][worker.product_category]
            recommendations.append(Insight(
                type='pricing',
                message=f"Similar sellers of {worker.product_category} in {worker.region} "
                        f"find {optimal_price} KES per unit to be the sweet spot.",
                confidence=cohort_stats['pricing_confidence'],
                sample_size=len(similar_workers),
            ))
        
        # Example: Inventory timing
        if worker_percentile['inventory_management'] < 50:
            best_days = cohort_stats['restock_days']
            recommendations.append(Insight(
                type='inventory',
                message=f"Top sellers restock on {best_days}. "
                        f"They sell 23% more by having fresh stock on peak days.",
                confidence=cohort_stats['inventory_confidence'],
                sample_size=len(similar_workers),
            ))
        
        return recommendations
```

**Approach 2: Behavioral Nudges**

```
Instead of: "Mama A sells tomatoes at 120 KES and makes 15K/day"
            (reveals individual data)

We say:     "Top tomato sellers in your area price at 115-125 KES.
             They sell an average of 45 kg/day. How do you compare?"
            (aggregate, anonymous, actionable)
```

**Approach 3: Strategy Templates**

```python
class StrategyTemplates:
    """
    Distilled success patterns packaged as actionable templates.
    Derived from aggregate analysis, not individual data.
    """
    
    TEMPLATES = {
        'morning_pricing': {
            'description': 'Early-bird pricing strategy',
            'pattern': 'Successful sellers offer 5-10% discount before 8am '
                       'to capture morning commuters, then increase to full price.',
            'source': 'Aggregate analysis of 5,000 food sellers, Nairobi',
            'expected_impact': '+12% daily revenue',
            'confidence': 0.78,
        },
        'diversification': {
            'description': 'Product diversification during low season',
            'pattern': 'When tomato supply drops, top sellers add eggs and '
                       'cooking oil. Revenue drops only 8% vs 30% for non-diversified.',
            'source': 'Aggregate analysis of 2,000 mama mbogas, 18-month period',
            'expected_impact': '-22% revenue volatility',
            'confidence': 0.71,
        },
        'payday_stockup': {
            'description': 'Payday inventory boost',
            'pattern': 'Increase stock by 40% on 1st and 15th (M-Pesa paydays). '
                       'Top sellers capture 2x normal revenue on these days.',
            'source': 'Aggregate analysis of 10,000 sellers across Kenya',
            'expected_impact': '+18% monthly revenue',
            'confidence': 0.85,
        },
    }
```

### Network Effect Amplification

```
Worker count:     1K      10K     100K    1M      10M
Pattern quality:  Low     Medium  Good    Great   Excellent
Recommendations:  Basic   Useful  Smart   Precise Personalized
Cross-learning:   None    Some    Strong  Rich    Transformative

The value per worker increases with total workers — classic network effect.
```

---

## 6. Privacy & Trust Architecture

### Core Principles

1. **Data minimization** — Collect only what's needed for the service
2. **Local-first processing** — Compute features on-device when possible
3. **Aggregate over individual** — Always work with groups, never singletons
4. **Differential privacy** — Mathematically guarantee no individual leakage
5. **Worker control** — Workers can see and delete their data

### Implementation

```python
class PrivacyGuard:
    """
    Enforces privacy guarantees across all intelligence systems.
    """
    
    # Minimum group sizes for any aggregate
    MIN_GROUP_SIZE = 50
    
    # Privacy budget per worker per day
    EPSILON_PER_DAY = 1.0
    
    # Data retention limits
    TRANSACTION_RETENTION_DAYS = 730  # 2 years
    IDENTIFIED_RETENTION_DAYS = 90    # Raw identified data
    
    def enforce_k_anonymity(self, query_result: pd.DataFrame, 
                             group_columns: List[str]) -> pd.DataFrame:
        """Suppress results with fewer than MIN_GROUP_SIZE members."""
        group_sizes = query_result.groupby(group_columns).size()
        valid_groups = group_sizes[group_sizes >= self.MIN_GROUP_SIZE].index
        return query_result.set_index(group_columns).loc[valid_groups].reset_index()
    
    def check_privacy_budget(self, worker_id: str, epsilon_cost: float) -> bool:
        """Ensure we don't exceed per-worker privacy budget."""
        used = self.get_daily_epsilon_used(worker_id)
        return (used + epsilon_cost) <= self.EPSILON_PER_DAY
    
    def anonymize_for_fmgc(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare data for FMCG clients — maximum anonymization."""
        result = data.copy()
        
        # Remove direct identifiers
        result = result.drop(columns=['worker_id', 'phone', 'name'], errors='ignore')
        
        # Generalize quasi-identifiers
        result['age_group'] = pd.cut(result['age'], bins=[0, 25, 35, 45, 55, 100])
        result['location'] = result['location'].apply(self._generalize_location)
        
        # Add noise to sensitive values
        result['revenue'] = result['revenue'].apply(
            lambda x: x + np.random.laplace(0, 100)
        )
        
        # Enforce minimum group size
        result = self.enforce_k_anonymity(result, ['location', 'age_group', 'product_category'])
        
        return result
```

---

## 7. System Architecture

### Data Pipeline

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Mobile  │───▶│  Event   │───▶│  Stream  │───▶│  Feature │
│  App     │    │  Ingest  │    │  Process │    │  Store   │
│  (SMS)   │    │  (API)   │    │  (Flink) │    │  (Redis) │
└──────────┘    └──────────┘    └──────────┘    └────┬─────┘
                                                      │
                    ┌─────────────────────────────────┤
                    │              │                   │
                    ▼              ▼                   ▼
              ┌──────────┐  ┌──────────┐        ┌──────────┐
              │  Market  │  │  Credit  │        │  Soko    │
              │  Mining  │  │  Model   │        │  Pulse   │
              │  (Spark) │  │  (ML)    │        │  (API)   │
              └────┬─────┘  └────┬─────┘        └────┬─────┘
                   │              │                   │
                   ▼              ▼                   ▼
              ┌──────────┐  ┌──────────┐        ┌──────────┐
              │ Economic │  │  Alama   │        │  FMCG    │
              │ Indicators│  │  Score   │        │  Clients │
              └──────────┘  └──────────┘        └──────────┘
```

### Technology Stack

| Component | Technology | Why |
|---|---|---|
| Event ingestion | Apache Kafka | High throughput, durability |
| Stream processing | Apache Flink | Low-latency, exactly-once |
| Batch processing | Apache Spark | Complex analytics at scale |
| Feature store | Redis + PostgreSQL | Fast reads, reliable storage |
| ML training | Python + XGBoost + TF | Mature ecosystem |
| ML serving | TensorFlow Serving / ONNX | Low-latency inference |
| API gateway | Kong / Envoy | Rate limiting, auth |
| Monitoring | Prometheus + Grafana | Observability |
| Privacy | Custom + OpenDP | Differential privacy |

### Scaling Projections

| Metric | Year 1 | Year 3 | Year 5 |
|---|---|---|---|
| Workers | 100K | 5M | 50M |
| Transactions/day | 500K | 25M | 250M |
| Data storage | 5 TB | 250 TB | 2.5 PB |
| ML models | 3 | 15 | 50+ |
| FMCG clients | 5 | 50 | 200+ |
| Revenue (data) | $500K | $25M | $200M |

---

## 8. Implementation Roadmap

### Phase 1: Foundation (Months 1-6)
- [ ] Transaction event pipeline (Kafka + Flink)
- [ ] Basic market aggregation (region × product × time)
- [ ] Alama Score v1 (logistic regression, 10 features)
- [ ] Privacy guard (k-anonymity + data retention)
- [ ] Worker insights MVP (daily SMS summary)

### Phase 2: Intelligence (Months 7-12)
- [ ] Trend detection (seasonal, price spikes)
- [ ] Alama Score v2 (ensemble model, 30 features)
- [ ] Soko Pulse MVP (FMCG data product)
- [ ] Economic indicators v1 (CPI, activity index)
- [ ] Cross-worker recommendations (aggregate patterns)

### Phase 3: Flywheel (Months 13-24)
- [ ] Predictive pricing models
- [ ] Alama Score v3 (neural network, 100+ features)
- [ ] Soko Pulse premium (predictive intelligence)
- [ ] Multi-country economic indicators
- [ ] Personalized strategy recommendations
- [ ] FMCG API platform

### Phase 4: Scale (Months 25-36)
- [ ] Real-time personalization at 10M+ workers
- [ ] Alama Score v4 (federated learning)
- [ ] Soko Pulse enterprise (custom analytics)
- [ ] East Africa Economic Pulse (cross-border)
- [ ] Worker-to-worker marketplace (trust-scored)

---

## 9. Success Metrics

### Intelligence Quality
| Metric | Target (Year 1) | Target (Year 3) |
|---|---|---|
| Price prediction accuracy | ±15% | ±5% |
| Demand forecast MAPE | 25% | 12% |
| Alama Score AUC-ROC | 0.72 | 0.85 |
| CPI vs KNBS correlation | 0.80 | 0.95 |
| Recommendation adoption | 20% | 45% |

### Business Impact
| Metric | Target (Year 1) | Target (Year 3) |
|---|---|---|
| FMCG revenue | $500K | $25M |
| Worker revenue uplift | +5% | +15% |
| Loan default reduction | -15% | -35% |
| New worker acquisition cost | -20% | -50% |

---

## 10. The Compound Effect

Each intelligence loop reinforces the others:

```
More transactions
    → Better credit model (Alama)
    → More loans approved
    → More workers join
    → More transactions

More transactions
    → Better market data (Soko Pulse)
    → FMCG companies pay
    → Revenue funds better models
    → Better worker recommendations
    → More workers join
    → More transactions

More workers
    → Better economic indicators
    → Government/NGO partnerships
    → Policy influence
    → More support for informal sector
    → More workers join
    → More transactions

Cross-worker learning
    → Better outcomes for each worker
    → Word-of-mouth growth
    → More workers join
    → More data
    → Better learning
    → Better outcomes
    → ...
```

**This is the Angavu flywheel. Every worker makes every other worker smarter. Every transaction makes the system more valuable. The compound effect is the moat.**

---

*Document version: 1.0*
*Last updated: 2026-07-25*
*Author: Angavu Architecture Team*
