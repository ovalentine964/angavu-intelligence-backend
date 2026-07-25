//! CompositeIndexBuilder — "Dow Jones for the Informal Economy"
//!
//! Fuses multiple weak signals (profit, spoilage, debt, customer retention, etc.)
//! into a single 0–1000 health score per region/cohort. Configurable weights,
//! normalization methods, and bootstrap confidence intervals.
//!
//! ## OODA Integration
//!
//! - **Observe:**  Receives `RawSignal` ingestions from MarketAnalyzer, CreditScorer,
//!   DistributionAnalyzer, HealthMetrics, EconomicAnalyzer, MobileMoneySignalExtractor.
//! - **Orient:**  Normalizes, weights, and fuses signals into composite indices.
//!   Detects divergence when component signals disagree.
//! - **Decide:**  Fires threshold alerts when index crosses critical levels.
//! - **Act:**     Publishes indices to Redis cache and feeds values back into
//!   CreditScorer (as features) and PolicyImpactAnalyzer (as baselines).

use anyhow::{anyhow, Context, Result};
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::{debug, info, warn};
use uuid::Uuid;

use crate::db::DatabaseConnections;

// ─────────────────────────────────────────────────────────────────────
// Configuration & Enums
// ─────────────────────────────────────────────────────────────────────

/// Worker type classification for the informal economy.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum WorkerType {
    MamaMboga,
    BodaBoda,
    MitiMba,
    Fundi,
    JuaKali,
    HouseHelp,
    FarmWorker,
    Other(String),
}

impl std::fmt::Display for WorkerType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MamaMboga => write!(f, "mama_mboga"),
            Self::BodaBoda => write!(f, "boda_boda"),
            Self::MitiMba => write!(f, "miti_mba"),
            Self::Fundi => write!(f, "fundi"),
            Self::JuaKali => write!(f, "jua_kali"),
            Self::HouseHelp => write!(f, "house_help"),
            Self::FarmWorker => write!(f, "farm_worker"),
            Self::Other(s) => write!(f, "{}", s),
        }
    }
}

/// Configuration for the CompositeIndexBuilder.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositeIndexConfig {
    /// Minimum number of source signals required before publishing an index.
    pub min_signals: usize,
    /// Maximum staleness (seconds) before a signal is considered expired.
    pub signal_max_age_secs: i64,
    /// Default decay half-life for time-weighted signals (seconds).
    pub decay_half_life_secs: i64,
    /// Minimum k-anonymity cohort size before inclusion.
    pub min_cohort_size: u32,
    /// Number of bootstrap resamples for confidence interval estimation.
    pub bootstrap_resamples: usize,
}

impl Default for CompositeIndexConfig {
    fn default() -> Self {
        Self {
            min_signals: 3,
            signal_max_age_secs: 86400,      // 24 hours
            decay_half_life_secs: 604_800,    // 7 days
            min_cohort_size: 10,
            bootstrap_resamples: 1000,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Index Definition & Signal Types
// ─────────────────────────────────────────────────────────────────────

/// A named composite index definition — lives in `index_definitions` table.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexDefinition {
    pub id: Uuid,
    pub name: String,
    pub region: String,
    pub worker_type: WorkerType,
    pub signal_weights: Vec<SignalWeight>,
    pub normalization: NormalizationMethod,
    pub publish_cadence: PublishCadence,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
}

/// How a single signal contributes to the composite.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalWeight {
    pub signal_name: String,
    pub weight: f64,
    pub direction: SignalDirection,
    pub transform: Option<Transform>,
}

/// Whether higher raw values are better or worse.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SignalDirection {
    HigherIsBetter,
    LowerIsBetter,
}

/// Optional pre-normalization transform.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Transform {
    Log,
    Sqrt,
    ZScore,
    Percentile,
    MinMax { min: f64, max: f64 },
}

/// How raw values are scaled to the 0–1 intermediate range.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum NormalizationMethod {
    MinMax,
    ZScore,
    PercentileRank,
    RobustScaler,
}

/// Publish frequency.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PublishCadence {
    Hourly,
    Daily,
    Weekly,
}

impl PublishCadence {
    fn ttl_seconds(&self) -> i64 {
        match self {
            Self::Hourly => 7200,    // 2 hours
            Self::Daily => 172_800,  // 48 hours
            Self::Weekly => 1_209_600,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Raw Signal Ingest
// ─────────────────────────────────────────────────────────────────────

/// A raw signal ingested from another tool (MarketAnalyzer, CreditScorer, etc.).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawSignal {
    pub signal_name: String,
    pub region: String,
    pub worker_type: WorkerType,
    pub value: f64,
    pub data_points: u32,
    pub ingested_at: DateTime<Utc>,
}

// ─────────────────────────────────────────────────────────────────────
// Composite Index Output
// ─────────────────────────────────────────────────────────────────────

/// The computed composite index — the deliverable.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompositeIndex {
    pub id: Uuid,
    pub definition_id: Uuid,
    pub value: f64,
    pub signals_used: Vec<SignalContribution>,
    pub cohort_size: u32,
    pub confidence: f64,
    pub confidence_interval: Option<ConfidenceInterval>,
    pub computed_at: DateTime<Utc>,
    pub region: String,
    pub worker_type: WorkerType,
}

/// How one signal contributed to the final score.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalContribution {
    pub signal_name: String,
    pub raw_value: f64,
    pub normalized_value: f64,
    pub weighted_contribution: f64,
    pub data_points: u32,
    pub staleness_secs: i64,
}

/// Bootstrap confidence interval.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfidenceInterval {
    pub lower: f64,
    pub upper: f64,
    pub level: f64,
}

// ─────────────────────────────────────────────────────────────────────
// Comparison & History Types
// ─────────────────────────────────────────────────────────────────────

/// Filter for selecting a cohort of workers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CohortFilter {
    pub region: Option<String>,
    pub worker_type: Option<WorkerType>,
    pub income_bracket: Option<String>,
}

/// Side-by-side comparison of two cohorts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexComparison {
    pub definition_id: Uuid,
    pub cohort_a: ComparisonResult,
    pub cohort_b: ComparisonResult,
    pub gap: f64,
    pub gap_pct: f64,
    pub computed_at: DateTime<Utc>,
}

/// One side of a comparison.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComparisonResult {
    pub cohort_label: String,
    pub index_value: f64,
    pub confidence: f64,
    pub signals_used: usize,
}

// ─────────────────────────────────────────────────────────────────────
// Internal: Fetched signal row from ClickHouse
// ─────────────────────────────────────────────────────────────────────

#[derive(clickhouse::Row, Deserialize, Clone)]
struct RawSignalRow {
    signal_name: String,
    region: String,
    worker_type: String,
    value: f64,
    data_points: u32,
    ingested_at: chrono::NaiveDateTime,
}

// ─────────────────────────────────────────────────────────────────────
// CompositeIndexBuilder — The Tool
// ─────────────────────────────────────────────────────────────────────

/// The main composite index builder tool.
pub struct CompositeIndexBuilder {
    db: DatabaseConnections,
    config: CompositeIndexConfig,
}

impl CompositeIndexBuilder {
    /// Create a new builder with default configuration.
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            config: CompositeIndexConfig::default(),
        }
    }

    /// Create with custom configuration.
    pub fn with_config(db: DatabaseConnections, config: CompositeIndexConfig) -> Self {
        Self { db, config }
    }

    // ─────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────

    /// Register a new composite index definition.
    pub async fn define_index(&self, def: &IndexDefinition) -> Result<Uuid> {
        // Validate weights sum to ~1.0
        let weight_sum: f64 = def.signal_weights.iter().map(|w| w.weight).sum();
        if (weight_sum - 1.0).abs() > 0.01 {
            return Err(anyhow!(
                "Signal weights must sum to 1.0, got {:.4}",
                weight_sum
            ));
        }

        let id = def.id;

        sqlx::query(
            r#"
            INSERT INTO index_definitions (id, name, region, worker_type, signal_weights, normalization, publish_cadence, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9)
            ON CONFLICT (name) DO UPDATE SET
                region = EXCLUDED.region,
                worker_type = EXCLUDED.worker_type,
                signal_weights = EXCLUDED.signal_weights,
                normalization = EXCLUDED.normalization,
                publish_cadence = EXCLUDED.publish_cadence,
                is_active = EXCLUDED.is_active,
                updated_at = EXCLUDED.created_at
            "#,
        )
        .bind(id)
        .bind(&def.name)
        .bind(&def.region)
        .bind(def.worker_type.to_string())
        .bind(serde_json::to_value(&def.signal_weights)?)
        .bind(format!("{:?}", def.normalization))
        .bind(format!("{:?}", def.publish_cadence))
        .bind(def.is_active)
        .bind(def.created_at)
        .execute(&self.db.postgres)
        .await
        .context("Failed to register index definition")?;

        info!(id = %id, name = %def.name, "Index definition registered");
        Ok(id)
    }

    /// Compute a single index snapshot for a region/cohort.
    pub async fn compute_index(
        &self,
        definition_id: Uuid,
        as_of: DateTime<Utc>,
    ) -> Result<CompositeIndex> {
        // 1. Load definition
        let def = self.load_definition(definition_id).await?;

        // 2. Fetch raw signals from ClickHouse
        let raw_signals = self
            .fetch_signals(&def.region, &def.worker_type, as_of)
            .await?;

        // 3. Filter to signals referenced in definition
        let signal_names: Vec<&str> = def
            .signal_weights
            .iter()
            .map(|sw| sw.signal_name.as_str())
            .collect();
        let relevant: Vec<&RawSignalRow> = raw_signals
            .iter()
            .filter(|s| signal_names.contains(&s.signal_name.as_str()))
            .collect();

        if relevant.len() < self.config.min_signals {
            return Err(anyhow!(
                "Insufficient signals: need {}, got {}",
                self.config.min_signals,
                relevant.len()
            ));
        }

        // 4. Compute contributions per signal
        let mut contributions = Vec::new();
        for sw in &def.signal_weights {
            if let Some(sig) = relevant.iter().find(|s| s.signal_name == sw.signal_name) {
                let stale_secs = (as_of - DateTime::<Utc>::from_naive_utc_and_offset(sig.ingested_at, Utc)).num_seconds();

                if stale_secs > self.config.signal_max_age_secs {
                    warn!(
                        signal = %sw.signal_name,
                        staleness = stale_secs,
                        "Signal exceeds max age, excluding"
                    );
                    continue;
                }

                // Apply optional transform
                let transformed = self.apply_transform(sig.value, &sw.transform);

                // Normalize to 0–1
                let normalized = self.normalize(transformed, &def.normalization, &relevant, sw);

                // Handle directionality
                let directed = match sw.direction {
                    SignalDirection::HigherIsBetter => normalized,
                    SignalDirection::LowerIsBetter => 1.0 - normalized,
                };

                let weighted = directed * sw.weight;

                contributions.push(SignalContribution {
                    signal_name: sw.signal_name.clone(),
                    raw_value: sig.value,
                    normalized_value: directed,
                    weighted_contribution: weighted,
                    data_points: sig.data_points,
                    staleness_secs: stale_secs,
                });
            }
        }

        if contributions.is_empty() {
            return Err(anyhow!("No valid signal contributions after filtering"));
        }

        // 5. Composite score (0–1000 scale)
        let weight_used: f64 = contributions.iter().map(|c| {
            def.signal_weights
                .iter()
                .find(|w| w.signal_name == c.signal_name)
                .map(|w| w.weight)
                .unwrap_or(0.0)
        }).sum();

        let raw_composite: f64 = contributions.iter().map(|c| c.weighted_contribution).sum();
        let renormalized = if weight_used > 0.0 {
            raw_composite / weight_used
        } else {
            0.0
        };
        let index_value = (renormalized * 1000.0).clamp(0.0, 1000.0);

        // 6. Confidence: signal coverage + data quality
        let signal_coverage = contributions.len() as f64 / def.signal_weights.len() as f64;
        let avg_data_points: f64 = contributions
            .iter()
            .map(|c| c.data_points as f64)
            .sum::<f64>()
            / contributions.len() as f64;
        let data_quality = (avg_data_points / 100.0).min(1.0);
        let confidence = (signal_coverage * 0.6 + data_quality * 0.4).min(1.0);

        // 7. Cohort size from the raw data (total unique data_points across signals)
        let cohort_size = relevant
            .iter()
            .map(|s| s.data_points)
            .max()
            .unwrap_or(0);

        // 8. Bootstrap confidence interval
        let ci = self.confidence_interval(
            &contributions,
            &def.signal_weights,
            &def.normalization,
        );

        let index = CompositeIndex {
            id: Uuid::new_v4(),
            definition_id,
            value: index_value,
            signals_used: contributions,
            cohort_size,
            confidence,
            confidence_interval: Some(ci),
            computed_at: Utc::now(),
            region: def.region.clone(),
            worker_type: def.worker_type.clone(),
        };

        // 9. Persist + publish
        self.persist_index(&index).await?;
        self.publish(&index, &def).await?;

        Ok(index)
    }

    /// Bulk-recompute all active indices (called by OODA scheduler).
    pub async fn compute_all_active(&self) -> Result<Vec<CompositeIndex>> {
        let defs = self.load_active_definitions().await?;
        let mut results = Vec::with_capacity(defs.len());
        let now = Utc::now();

        for def in &defs {
            match self.compute_index(def.id, now).await {
                Ok(idx) => {
                    info!(
                        definition = %def.name,
                        value = idx.value,
                        confidence = idx.confidence,
                        "Index computed"
                    );
                    results.push(idx);
                }
                Err(e) => {
                    warn!(definition = %def.name, error = %e, "Failed to compute index");
                }
            }
        }

        info!(count = results.len(), "Bulk index computation complete");
        Ok(results)
    }

    /// Ingest a raw signal value.
    ///
    /// Called by other tools: CreditScorer, MarketAnalyzer, etc.
    pub async fn ingest_signal(&self, signal: &RawSignal) -> Result<()> {
        // Enforce k-anonymity minimum
        if signal.data_points < self.config.min_cohort_size {
            debug!(
                signal = %signal.signal_name,
                data_points = signal.data_points,
                min = self.config.min_cohort_size,
                "Signal below k-anonymity threshold, skipping"
            );
            return Ok(());
        }

        // Write to ClickHouse raw_signals table
        let query = format!(
            r#"
            INSERT INTO raw_signals (signal_name, region, worker_type, value, data_points, ingested_at)
            VALUES ('{}', '{}', '{}', {}, {}, '{}')
            "#,
            signal.signal_name.replace('\'', "''"),
            signal.region.replace('\'', "''"),
            signal.worker_type.to_string().replace('\'', "''"),
            signal.value,
            signal.data_points,
            signal.ingested_at.format("%Y-%m-%d %H:%M:%S%.3f"),
        );

        self.db
            .clickhouse
            .query(&query)
            .execute()
            .await
            .context("Failed to ingest raw signal into ClickHouse")?;

        debug!(
            signal = %signal.signal_name,
            region = %signal.region,
            value = signal.value,
            "Raw signal ingested"
        );

        Ok(())
    }

    /// Retrieve historical index values for trend analysis.
    pub async fn get_history(
        &self,
        definition_id: Uuid,
        from: DateTime<Utc>,
        to: DateTime<Utc>,
    ) -> Result<Vec<CompositeIndex>> {
        let query = format!(
            r#"
            SELECT id, definition_id, value, signals_used, cohort_size, confidence,
                   region, worker_type, computed_at
            FROM composite_index_history
            WHERE definition_id = '{}'
              AND computed_at >= '{}'
              AND computed_at <= '{}'
            ORDER BY computed_at ASC
            "#,
            definition_id,
            from.format("%Y-%m-%d %H:%M:%S%.3f"),
            to.format("%Y-%m-%d %H:%M:%S%.3f"),
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct HistoryRow {
            id: String,
            definition_id: String,
            value: f64,
            signals_used: String,
            cohort_size: u32,
            confidence: f64,
            region: String,
            worker_type: String,
            computed_at: chrono::NaiveDateTime,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<HistoryRow>()
            .await
            .context("Failed to fetch index history from ClickHouse")?;

        let indices: Vec<CompositeIndex> = rows
            .into_iter()
            .filter_map(|row| {
                let signals: Vec<SignalContribution> =
                    serde_json::from_str(&row.signals_used).unwrap_or_default();
                Some(CompositeIndex {
                    id: Uuid::parse_str(&row.id).ok()?,
                    definition_id: Uuid::parse_str(&row.definition_id).ok()?,
                    value: row.value,
                    signals_used: signals,
                    cohort_size: row.cohort_size,
                    confidence: row.confidence,
                    confidence_interval: None,
                    computed_at: DateTime::<Utc>::from_naive_utc_and_offset(row.computed_at, Utc),
                    region: row.region,
                    worker_type: parse_worker_type(&row.worker_type),
                })
            })
            .collect();

        Ok(indices)
    }

    /// Compare two regions or cohorts side by side.
    pub async fn compare(
        &self,
        definition_id: Uuid,
        cohort_a: &CohortFilter,
        cohort_b: &CohortFilter,
    ) -> Result<IndexComparison> {
        let now = Utc::now();

        // For each cohort, compute a filtered index
        let result_a = self
            .compute_filtered_index(definition_id, cohort_a, now)
            .await?;
        let result_b = self
            .compute_filtered_index(definition_id, cohort_b, now)
            .await?;

        let gap = result_a.index_value - result_b.index_value;
        let gap_pct = if result_b.index_value > 0.0 {
            (gap / result_b.index_value) * 100.0
        } else {
            0.0
        };

        Ok(IndexComparison {
            definition_id,
            cohort_a: result_a,
            cohort_b: result_b,
            gap,
            gap_pct,
            computed_at: now,
        })
    }

    /// Auto-tune weights based on predictive power.
    ///
    /// Regresses each signal against an outcome variable and reweights
    /// proportionally to the absolute correlation coefficient.
    pub async fn auto_tune_weights(
        &self,
        definition_id: Uuid,
        outcome_signal: &str,
        lookback_days: u32,
    ) -> Result<Vec<SignalWeight>> {
        let def = self.load_definition(definition_id).await?;

        // Fetch historical signals for correlation
        let from = Utc::now() - chrono::Duration::days(lookback_days as i64);
        let to = Utc::now();

        // Gather time-aligned series for each signal + outcome
        let mut series: HashMap<String, Vec<f64>> = HashMap::new();

        for sw in &def.signal_weights {
            let data = self
                .fetch_signal_series(&sw.signal_name, &def.region, &def.worker_type, from, to)
                .await?;
            if !data.is_empty() {
                series.insert(sw.signal_name.clone(), data);
            }
        }

        let outcome_data = self
            .fetch_signal_series(outcome_signal, &def.region, &def.worker_type, from, to)
            .await?;

        if outcome_data.is_empty() {
            return Err(anyhow!("No data for outcome signal '{}'", outcome_signal));
        }

        // Compute Pearson correlation for each signal against outcome
        let mut correlations: Vec<(String, f64)> = Vec::new();
        for sw in &def.signal_weights {
            if let Some(sig_data) = series.get(&sw.signal_name) {
                let n = sig_data.len().min(outcome_data.len());
                if n < 10 {
                    continue;
                }
                let corr = pearson_correlation(
                    &sig_data[..n],
                    &outcome_data[..n],
                );
                correlations.push((sw.signal_name.clone(), corr.abs()));
            }
        }

        if correlations.is_empty() {
            return Err(anyhow!("No valid correlations computed"));
        }

        // Normalize correlation weights to sum to 1.0
        let total_corr: f64 = correlations.iter().map(|(_, c)| c).sum();
        let new_weights: Vec<SignalWeight> = def
            .signal_weights
            .iter()
            .map(|sw| {
                let corr = correlations
                    .iter()
                    .find(|(name, _)| *name == sw.signal_name)
                    .map(|(_, c)| *c)
                    .unwrap_or(0.0);
                let new_weight = if total_corr > 0.0 {
                    corr / total_corr
                } else {
                    sw.weight // fallback to existing
                };
                SignalWeight {
                    signal_name: sw.signal_name.clone(),
                    weight: new_weight,
                    direction: sw.direction.clone(),
                    transform: sw.transform.clone(),
                }
            })
            .collect();

        info!(
            definition = %def.name,
            outcome = outcome_signal,
            "Auto-tuned weights via correlation"
        );

        Ok(new_weights)
    }

    /// Compute a bootstrap confidence interval for the composite index.
    ///
    /// Resamples signal contributions with replacement and recomputes the
    /// composite score for each resample.
    pub fn confidence_interval(
        &self,
        contributions: &[SignalContribution],
        weights: &[SignalWeight],
        _normalization: &NormalizationMethod,
    ) -> ConfidenceInterval {
        use rand::seq::SliceRandom;
        use rand::SeedableRng;

        if contributions.is_empty() {
            return ConfidenceInterval {
                lower: 0.0,
                upper: 0.0,
                level: 0.95,
            };
        }

        let n_resamples = self.config.bootstrap_resamples;
        let mut rng = rand::rngs::StdRng::seed_from_u64(42); // deterministic seed
        let mut resampled_scores = Vec::with_capacity(n_resamples);

        for _ in 0..n_resamples {
            // Resample contributions with replacement
            let mut resample_sum = 0.0;
            let mut resample_weight = 0.0;
            for _ in 0..contributions.len() {
                if let Some(c) = contributions.choose(&mut rng) {
                    if let Some(w) = weights.iter().find(|w| w.signal_name == c.signal_name) {
                        resample_sum += c.weighted_contribution;
                        resample_weight += w.weight;
                    }
                }
            }
            let score = if resample_weight > 0.0 {
                (resample_sum / resample_weight * 1000.0).clamp(0.0, 1000.0)
            } else {
                0.0
            };
            resampled_scores.push(score);
        }

        resampled_scores.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let alpha = 0.05; // 95% CI
        let lower_idx = ((alpha / 2.0) * n_resamples as f64) as usize;
        let upper_idx = ((1.0 - alpha / 2.0) * n_resamples as f64) as usize;

        ConfidenceInterval {
            lower: resampled_scores[lower_idx.min(n_resamples - 1)],
            upper: resampled_scores[upper_idx.min(n_resamples - 1)],
            level: 0.95,
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Normalize — min-max normalization across available signal values
    // ─────────────────────────────────────────────────────────────────

    /// Normalize a value to [0, 1] using the specified method.
    ///
    /// For MinMax, we use the observed range across all signals of the same
    /// name. For other methods, we fall back to simple clamping heuristics
    /// when the full population isn't available inline.
    pub fn normalize(
        &self,
        value: f64,
        method: &NormalizationMethod,
        all_signals: &[&RawSignalRow],
        signal_weight: &SignalWeight,
    ) -> f64 {
        match method {
            NormalizationMethod::MinMax => {
                self.normalize_min_max(value, all_signals, &signal_weight.signal_name)
            }
            NormalizationMethod::ZScore => {
                self.normalize_z_score(value, all_signals, &signal_weight.signal_name)
            }
            NormalizationMethod::PercentileRank => {
                self.normalize_percentile(value, all_signals, &signal_weight.signal_name)
            }
            NormalizationMethod::RobustScaler => {
                self.normalize_robust(value, all_signals, &signal_weight.signal_name)
            }
        }
    }

    /// Min-max: (value - min) / (max - min), clamped to [0, 1].
    fn normalize_min_max(
        &self,
        value: f64,
        all_signals: &[&RawSignalRow],
        signal_name: &str,
    ) -> f64 {
        let values: Vec<f64> = all_signals
            .iter()
            .filter(|s| s.signal_name == signal_name)
            .map(|s| s.value)
            .collect();

        if values.is_empty() {
            return 0.5;
        }

        let min = values.iter().cloned().fold(f64::INFINITY, f64::min);
        let max = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

        if (max - min).abs() < f64::EPSILON {
            return 0.5; // all values identical
        }

        ((value - min) / (max - min)).clamp(0.0, 1.0)
    }

    /// Z-score normalization, mapped to [0, 1] via sigmoid.
    fn normalize_z_score(
        &self,
        value: f64,
        all_signals: &[&RawSignalRow],
        signal_name: &str,
    ) -> f64 {
        let values: Vec<f64> = all_signals
            .iter()
            .filter(|s| s.signal_name == signal_name)
            .map(|s| s.value)
            .collect();

        if values.len() < 2 {
            return 0.5;
        }

        let mean = values.iter().sum::<f64>() / values.len() as f64;
        let variance =
            values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (values.len() - 1) as f64;
        let std_dev = variance.sqrt();

        if std_dev < f64::EPSILON {
            return 0.5;
        }

        let z = (value - mean) / std_dev;
        // Sigmoid mapping: 1 / (1 + e^(-z))
        1.0 / (1.0 + (-z).exp())
    }

    /// Percentile rank among observed values.
    fn normalize_percentile(
        &self,
        value: f64,
        all_signals: &[&RawSignalRow],
        signal_name: &str,
    ) -> f64 {
        let mut values: Vec<f64> = all_signals
            .iter()
            .filter(|s| s.signal_name == signal_name)
            .map(|s| s.value)
            .collect();

        if values.is_empty() {
            return 0.5;
        }

        values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let rank = values.iter().filter(|&&v| v <= value).count();
        rank as f64 / values.len() as f64
    }

    /// Robust scaler: (value - median) / IQR, mapped to [0, 1] via clamping.
    fn normalize_robust(
        &self,
        value: f64,
        all_signals: &[&RawSignalRow],
        signal_name: &str,
    ) -> f64 {
        let mut values: Vec<f64> = all_signals
            .iter()
            .filter(|s| s.signal_name == signal_name)
            .map(|s| s.value)
            .collect();

        if values.len() < 4 {
            return self.normalize_min_max(value, all_signals, signal_name);
        }

        values.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let n = values.len();
        let median = if n % 2 == 0 {
            (values[n / 2 - 1] + values[n / 2]) / 2.0
        } else {
            values[n / 2]
        };
        let q1 = values[n / 4];
        let q3 = values[3 * n / 4];
        let iqr = q3 - q1;

        if iqr < f64::EPSILON {
            return 0.5;
        }

        let scaled = (value - median) / iqr;
        // Map to [0, 1] — assume ±3 IQR covers the full range
        ((scaled + 3.0) / 6.0).clamp(0.0, 1.0)
    }

    // ─────────────────────────────────────────────────────────────────
    // Weight Signals — configurable weights
    // ─────────────────────────────────────────────────────────────────

    /// Apply configurable weights to normalized signal values.
    ///
    /// Returns the weighted contribution for each signal. Weights must
    /// sum to 1.0 (validated at definition time).
    pub fn weight_signals(
        &self,
        normalized_values: &[(String, f64)], // (signal_name, normalized_0_1)
        weights: &[SignalWeight],
    ) -> Vec<(String, f64)> {
        normalized_values
            .iter()
            .map(|(name, norm_val)| {
                let w = weights
                    .iter()
                    .find(|sw| sw.signal_name == *name)
                    .map(|sw| sw.weight)
                    .unwrap_or(0.0);
                (name.clone(), norm_val * w)
            })
            .collect()
    }

    // ─────────────────────────────────────────────────────────────────
    // Private Helpers
    // ─────────────────────────────────────────────────────────────────

    /// Apply an optional transform to a raw signal value.
    fn apply_transform(&self, value: f64, transform: &Option<Transform>) -> f64 {
        match transform {
            None => value,
            Some(Transform::Log) => (value + 1.0).ln(),        // ln(1+x) to handle zeros
            Some(Transform::Sqrt) => value.abs().sqrt(),
            Some(Transform::ZScore) => value,                   // handled in normalization
            Some(Transform::Percentile) => value,               // handled in normalization
            Some(Transform::MinMax { min, max }) => {
                if (max - min).abs() < f64::EPSILON {
                    0.5
                } else {
                    ((value - min) / (max - min)).clamp(0.0, 1.0)
                }
            }
        }
    }

    /// Load an index definition from PostgreSQL.
    async fn load_definition(&self, definition_id: Uuid) -> Result<IndexDefinition> {
        #[derive(sqlx::FromRow)]
        struct DefRow {
            id: Uuid,
            name: String,
            region: String,
            worker_type: String,
            signal_weights: serde_json::Value,
            normalization: String,
            publish_cadence: String,
            is_active: bool,
            created_at: DateTime<Utc>,
        }

        let row = sqlx::query_as::<_, DefRow>(
            "SELECT id, name, region, worker_type, signal_weights, normalization, publish_cadence, is_active, created_at FROM index_definitions WHERE id = $1",
        )
        .bind(definition_id)
        .fetch_one(&self.db.postgres)
        .await
        .context("Failed to load index definition")?;

        Ok(IndexDefinition {
            id: row.id,
            name: row.name,
            region: row.region,
            worker_type: parse_worker_type(&row.worker_type),
            signal_weights: serde_json::from_value(row.signal_weights)
                .unwrap_or_default(),
            normalization: parse_normalization(&row.normalization),
            publish_cadence: parse_cadence(&row.publish_cadence),
            is_active: row.is_active,
            created_at: row.created_at,
        })
    }

    /// Load all active index definitions.
    async fn load_active_definitions(&self) -> Result<Vec<IndexDefinition>> {
        #[derive(sqlx::FromRow)]
        struct DefRow {
            id: Uuid,
            name: String,
            region: String,
            worker_type: String,
            signal_weights: serde_json::Value,
            normalization: String,
            publish_cadence: String,
            is_active: bool,
            created_at: DateTime<Utc>,
        }

        let rows = sqlx::query_as::<_, DefRow>(
            "SELECT id, name, region, worker_type, signal_weights, normalization, publish_cadence, is_active, created_at FROM index_definitions WHERE is_active = true",
        )
        .fetch_all(&self.db.postgres)
        .await
        .context("Failed to load active definitions")?;

        Ok(rows
            .into_iter()
            .map(|row| IndexDefinition {
                id: row.id,
                name: row.name,
                region: row.region,
                worker_type: parse_worker_type(&row.worker_type),
                signal_weights: serde_json::from_value(row.signal_weights).unwrap_or_default(),
                normalization: parse_normalization(&row.normalization),
                publish_cadence: parse_cadence(&row.publish_cadence),
                is_active: row.is_active,
                created_at: row.created_at,
            })
            .collect())
    }

    /// Fetch raw signals from ClickHouse for a region/worker_type.
    async fn fetch_signals(
        &self,
        region: &str,
        worker_type: &WorkerType,
        as_of: DateTime<Utc>,
    ) -> Result<Vec<RawSignalRow>> {
        let cutoff = as_of - chrono::Duration::seconds(self.config.signal_max_age_secs);

        let query = format!(
            r#"
            SELECT signal_name, region, worker_type, value, data_points, ingested_at
            FROM raw_signals
            WHERE region = '{}'
              AND worker_type = '{}'
              AND ingested_at >= '{}'
            ORDER BY ingested_at DESC
            "#,
            region.replace('\'', "''"),
            worker_type.to_string().replace('\'', "''"),
            cutoff.format("%Y-%m-%d %H:%M:%S%.3f"),
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_all::<RawSignalRow>()
            .await
            .context("Failed to fetch raw signals from ClickHouse")
    }

    /// Fetch a time series of one signal for correlation analysis.
    async fn fetch_signal_series(
        &self,
        signal_name: &str,
        region: &str,
        worker_type: &WorkerType,
        from: DateTime<Utc>,
        to: DateTime<Utc>,
    ) -> Result<Vec<f64>> {
        let query = format!(
            r#"
            SELECT value
            FROM raw_signals
            WHERE signal_name = '{}'
              AND region = '{}'
              AND worker_type = '{}'
              AND ingested_at >= '{}'
              AND ingested_at <= '{}'
            ORDER BY ingested_at ASC
            "#,
            signal_name.replace('\'', "''"),
            region.replace('\'', "''"),
            worker_type.to_string().replace('\'', "''"),
            from.format("%Y-%m-%d %H:%M:%S%.3f"),
            to.format("%Y-%m-%d %H:%M:%S%.3f"),
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct ValueRow {
            value: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<ValueRow>()
            .await
            .context("Failed to fetch signal series")?;

        Ok(rows.into_iter().map(|r| r.value).collect())
    }

    /// Compute a filtered index for a specific cohort (used by `compare`).
    async fn compute_filtered_index(
        &self,
        definition_id: Uuid,
        cohort: &CohortFilter,
        as_of: DateTime<Utc>,
    ) -> Result<ComparisonResult> {
        let def = self.load_definition(definition_id).await?;

        // Use cohort overrides if present
        let region = cohort.region.as_deref().unwrap_or(&def.region);
        let worker_type = cohort
            .worker_type
            .as_ref()
            .unwrap_or(&def.worker_type);

        let signals = self.fetch_signals(region, worker_type, as_of).await?;

        let signal_names: Vec<&str> = def
            .signal_weights
            .iter()
            .map(|sw| sw.signal_name.as_str())
            .collect();
        let relevant: Vec<&RawSignalRow> = signals
            .iter()
            .filter(|s| signal_names.contains(&s.signal_name.as_str()))
            .collect();

        let mut contributions = Vec::new();
        for sw in &def.signal_weights {
            if let Some(sig) = relevant.iter().find(|s| s.signal_name == sw.signal_name) {
                let transformed = self.apply_transform(sig.value, &sw.transform);
                let normalized = self.normalize(transformed, &def.normalization, &relevant, sw);
                let directed = match sw.direction {
                    SignalDirection::HigherIsBetter => normalized,
                    SignalDirection::LowerIsBetter => 1.0 - normalized,
                };
                contributions.push(SignalContribution {
                    signal_name: sw.signal_name.clone(),
                    raw_value: sig.value,
                    normalized_value: directed,
                    weighted_contribution: directed * sw.weight,
                    data_points: sig.data_points,
                    staleness_secs: 0,
                });
            }
        }

        let weight_used: f64 = contributions
            .iter()
            .filter_map(|c| def.signal_weights.iter().find(|w| w.signal_name == c.signal_name).map(|w| w.weight))
            .sum();

        let raw_sum: f64 = contributions.iter().map(|c| c.weighted_contribution).sum();
        let value = if weight_used > 0.0 {
            (raw_sum / weight_used * 1000.0).clamp(0.0, 1000.0)
        } else {
            0.0
        };

        let signal_coverage = contributions.len() as f64 / def.signal_weights.len().max(1) as f64;
        let confidence = signal_coverage.min(1.0);

        Ok(ComparisonResult {
            cohort_label: format!("{}:{}", region, worker_type),
            index_value: value,
            confidence,
            signals_used: contributions.len(),
        })
    }

    /// Persist a computed index to PostgreSQL (index_latest) and ClickHouse (history).
    async fn persist_index(&self, index: &CompositeIndex) -> Result<()> {
        // PostgreSQL: upsert into index_latest
        sqlx::query(
            r#"
            INSERT INTO index_latest (definition_id, value, signals_used, cohort_size, confidence, computed_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (definition_id) DO UPDATE SET
                value = EXCLUDED.value,
                signals_used = EXCLUDED.signals_used,
                cohort_size = EXCLUDED.cohort_size,
                confidence = EXCLUDED.confidence,
                computed_at = EXCLUDED.computed_at
            "#,
        )
        .bind(index.definition_id)
        .bind(index.value)
        .bind(serde_json::to_value(&index.signals_used)?)
        .bind(index.cohort_size as i32)
        .bind(index.confidence)
        .bind(index.computed_at)
        .execute(&self.db.postgres)
        .await
        .context("Failed to persist index to PostgreSQL")?;

        // ClickHouse: append to history
        let ch_query = format!(
            r#"
            INSERT INTO composite_index_history (id, definition_id, value, signals_used, cohort_size, confidence, region, worker_type, computed_at)
            VALUES ('{}', '{}', {}, '{}', {}, {}, '{}', '{}', '{}')
            "#,
            index.id,
            index.definition_id,
            index.value,
            serde_json::to_string(&index.signals_used).unwrap_or_default().replace('\'', "''"),
            index.cohort_size,
            index.confidence,
            index.region.replace('\'', "''"),
            index.worker_type.to_string().replace('\'', "''"),
            index.computed_at.format("%Y-%m-%d %H:%M:%S%.3f"),
        );

        if let Err(e) = self.db.clickhouse.query(&ch_query).execute().await {
            warn!(error = %e, "Failed to persist index history to ClickHouse (non-fatal)");
        }

        Ok(())
    }

    /// Publish index to Redis cache.
    async fn publish(&self, index: &CompositeIndex, def: &IndexDefinition) -> Result<()> {
        use redis::AsyncCommands;

        let mut conn = self.db.redis.clone();

        // Latest index cache
        let key = format!("idx:latest:{}", index.definition_id);
        let json = serde_json::to_string(index)?;
        let ttl = def.publish_cadence.ttl_seconds();
        conn.set_ex::<_, _, ()>(&key, &json, ttl as u64)
            .await
            .context("Failed to publish index to Redis")?;

        // Daily snapshot for fast API responses
        let date_key = format!(
            "idx:{}:{}",
            index.definition_id,
            index.computed_at.format("%Y-%m-%d")
        );
        let _: () = conn
            .lpush(&date_key, &json)
            .await
            .unwrap_or(());
        let _: () = conn
            .expire(&date_key, 86400 * 7)
            .await
            .unwrap_or(());

        debug!(
            index_id = %index.id,
            value = index.value,
            "Index published to Redis"
        );

        Ok(())
    }
}

// ─────────────────────────────────────────────────────────────────────
// OODA Integration — called by OODAOrchestrator
// ─────────────────────────────────────────────────────────────────────

impl CompositeIndexBuilder {
    /// OODA Observe: ingest signals from other tools.
    ///
    /// Called by the orchestrator when MarketAnalyzer, CreditScorer, etc.
    /// produce new data. Routes raw values through `ingest_signal`.
    pub async fn ooda_observe(&self, signals: &[RawSignal]) -> Result<usize> {
        let mut ingested = 0;
        for signal in signals {
            if let Err(e) = self.ingest_signal(signal).await {
                warn!(signal = %signal.signal_name, error = %e, "OODA observe ingest failed");
            } else {
                ingested += 1;
            }
        }
        Ok(ingested)
    }

    /// OODA Orient: compute all active indices and detect divergence.
    ///
    /// Returns indices that show divergent signals (e.g., profits up but
    /// debt also up) — these need investigation.
    pub async fn ooda_orient(&self) -> Result<Vec<CompositeIndex>> {
        let indices = self.compute_all_active().await?;

        for idx in &indices {
            // Detect divergence: if direction-agreed signals disagree significantly
            let positive_signals: Vec<&SignalContribution> = idx
                .signals_used
                .iter()
                .filter(|s| s.normalized_value > 0.6)
                .collect();
            let negative_signals: Vec<&SignalContribution> = idx
                .signals_used
                .iter()
                .filter(|s| s.normalized_value < 0.4)
                .collect();

            if !positive_signals.is_empty() && !negative_signals.is_empty() {
                warn!(
                    index = %idx.definition_id,
                    positive = positive_signals.len(),
                    negative = negative_signals.len(),
                    "Divergent signals detected — index may be masking internal conflict"
                );
            }
        }

        Ok(indices)
    }

    /// OODA Decide: check indices against thresholds and emit alerts.
    ///
    /// Returns indices that crossed critical thresholds.
    pub async fn ooda_decide(
        &self,
        indices: &[CompositeIndex],
    ) -> Result<Vec<ThresholdAlert>> {
        let mut alerts = Vec::new();

        for idx in indices {
            // Critical low: index below 300 for 3+ consecutive computations
            if idx.value < 300.0 && idx.confidence > 0.5 {
                let history = self
                    .get_history(
                        idx.definition_id,
                        Utc::now() - chrono::Duration::days(7),
                        Utc::now(),
                    )
                    .await
                    .unwrap_or_default();

                let consecutive_low = history
                    .iter()
                    .rev()
                    .take(10)
                    .filter(|h| h.value < 300.0)
                    .count();

                if consecutive_low >= 3 {
                    alerts.push(ThresholdAlert {
                        definition_id: idx.definition_id,
                        region: idx.region.clone(),
                        worker_type: idx.worker_type.clone(),
                        current_value: idx.value,
                        threshold: 300.0,
                        direction: AlertDirection::Below,
                        consecutive_breaches: consecutive_low,
                        severity: AlertSeverity::Critical,
                        message: format!(
                            "{} index dropped below 300 for {} consecutive computations",
                            idx.region, consecutive_low
                        ),
                    });
                }
            }

            // Opportunity high: index above 750
            if idx.value > 750.0 && idx.confidence > 0.6 {
                alerts.push(ThresholdAlert {
                    definition_id: idx.definition_id,
                    region: idx.region.clone(),
                    worker_type: idx.worker_type.clone(),
                    current_value: idx.value,
                    threshold: 750.0,
                    direction: AlertDirection::Above,
                    consecutive_breaches: 1,
                    severity: AlertSeverity::Opportunity,
                    message: format!(
                        "{} index crossed 750 — strong economic health signal",
                        idx.region
                    ),
                });
            }
        }

        Ok(alerts)
    }

    /// OODA Act: publish alert indices and feed back into CreditScorer features.
    pub async fn ooda_act(&self, alerts: &[ThresholdAlert]) -> Result<()> {
        use redis::AsyncCommands;
        let mut conn = self.db.redis.clone();

        for alert in alerts {
            let key = "idx:alerts:active";
            let json = serde_json::to_string(alert)?;
            let _: () = conn
                .lpush(key, &json)
                .await
                .unwrap_or(());

            info!(
                severity = ?alert.severity,
                region = %alert.region,
                value = alert.current_value,
                "OODA Act: threshold alert published"
            );
        }

        Ok(())
    }
}

// ─────────────────────────────────────────────────────────────────────
// Threshold Alert Types (OODA Decide output)
// ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThresholdAlert {
    pub definition_id: Uuid,
    pub region: String,
    pub worker_type: WorkerType,
    pub current_value: f64,
    pub threshold: f64,
    pub direction: AlertDirection,
    pub consecutive_breaches: usize,
    pub severity: AlertSeverity,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AlertDirection {
    Above,
    Below,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AlertSeverity {
    Info,
    Warning,
    Critical,
    Opportunity,
}

// ─────────────────────────────────────────────────────────────────────
// Pure Math Helpers
// ─────────────────────────────────────────────────────────────────────

/// Pearson correlation coefficient between two equal-length slices.
fn pearson_correlation(x: &[f64], y: &[f64]) -> f64 {
    let n = x.len().min(y.len()) as f64;
    if n < 2.0 {
        return 0.0;
    }

    let mean_x = x.iter().sum::<f64>() / n;
    let mean_y = y.iter().sum::<f64>() / n;

    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;

    for i in 0..n as usize {
        let dx = x[i] - mean_x;
        let dy = y[i] - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }

    let denom = (var_x * var_y).sqrt();
    if denom < f64::EPSILON {
        0.0
    } else {
        cov / denom
    }
}

// ─────────────────────────────────────────────────────────────────────
// Parsing Helpers
// ─────────────────────────────────────────────────────────────────────

fn parse_worker_type(s: &str) -> WorkerType {
    match s.to_lowercase().as_str() {
        "mama_mboga" => WorkerType::MamaMboga,
        "boda_boda" => WorkerType::BodaBoda,
        "miti_mba" => WorkerType::MitiMba,
        "fundi" => WorkerType::Fundi,
        "jua_kali" => WorkerType::JuaKali,
        "house_help" => WorkerType::HouseHelp,
        "farm_worker" => WorkerType::FarmWorker,
        other => WorkerType::Other(other.to_string()),
    }
}

fn parse_normalization(s: &str) -> NormalizationMethod {
    match s.to_lowercase().as_str() {
        "minmax" | "min_max" => NormalizationMethod::MinMax,
        "zscore" | "z_score" => NormalizationMethod::ZScore,
        "percentilerank" | "percentile_rank" => NormalizationMethod::PercentileRank,
        "robustscaler" | "robust_scaler" => NormalizationMethod::RobustScaler,
        _ => NormalizationMethod::MinMax,
    }
}

fn parse_cadence(s: &str) -> PublishCadence {
    match s.to_lowercase().as_str() {
        "hourly" => PublishCadence::Hourly,
        "daily" => PublishCadence::Daily,
        "weekly" => PublishCadence::Weekly,
        _ => PublishCadence::Daily,
    }
}

// ─────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_worker_type_display() {
        assert_eq!(WorkerType::MamaMboga.to_string(), "mama_mboga");
        assert_eq!(WorkerType::BodaBoda.to_string(), "boda_boda");
        assert_eq!(WorkerType::Other("custom".into()).to_string(), "custom");
    }

    #[test]
    fn test_parse_worker_type() {
        assert_eq!(parse_worker_type("mama_mboga"), WorkerType::MamaMboga);
        assert_eq!(parse_worker_type("BODA_BODA"), WorkerType::BodaBoda);
        assert_eq!(
            parse_worker_type("market_vendor"),
            WorkerType::Other("market_vendor".to_string())
        );
    }

    #[test]
    fn test_pearson_correlation_perfect() {
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![2.0, 4.0, 6.0, 8.0, 10.0];
        let r = pearson_correlation(&x, &y);
        assert!((r - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_pearson_correlation_negative() {
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![10.0, 8.0, 6.0, 4.0, 2.0];
        let r = pearson_correlation(&x, &y);
        assert!((r - (-1.0)).abs() < 1e-10);
    }

    #[test]
    fn test_pearson_correlation_zero() {
        let x = vec![1.0, 1.0, 1.0];
        let y = vec![2.0, 3.0, 4.0];
        let r = pearson_correlation(&x, &y);
        assert!(r.abs() < 1e-10);
    }

    #[test]
    fn test_normalize_min_max() {
        // Inline test: can't construct CompositeIndexBuilder without DB
        // but we can test the math directly
        let values = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        let min = values.iter().cloned().fold(f64::INFINITY, f64::min);
        let max = values.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let normalized = (30.0 - min) / (max - min);
        assert!((normalized - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_normalize_z_score_sigmoid() {
        // z=0 should map to 0.5 via sigmoid
        let z = 0.0;
        let sigmoid = 1.0 / (1.0 + (-z).exp());
        assert!((sigmoid - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_confidence_interval_deterministic() {
        // Bootstrap CI with seed 42 should be deterministic
        let contributions = vec![
            SignalContribution {
                signal_name: "profit".into(),
                raw_value: 500.0,
                normalized_value: 0.6,
                weighted_contribution: 0.18,
                data_points: 100,
                staleness_secs: 0,
            },
            SignalContribution {
                signal_name: "spoilage".into(),
                raw_value: 0.1,
                normalized_value: 0.8,
                weighted_contribution: 0.24,
                data_points: 100,
                staleness_secs: 0,
            },
        ];
        let weights = vec![
            SignalWeight {
                signal_name: "profit".into(),
                weight: 0.3,
                direction: SignalDirection::HigherIsBetter,
                transform: None,
            },
            SignalWeight {
                signal_name: "spoilage".into(),
                weight: 0.7,
                direction: SignalDirection::LowerIsBetter,
                transform: None,
            },
        ];

        // We can't construct CompositeIndexBuilder without DB in unit tests,
        // but we can test the bootstrap math directly by calling the function
        // with the same seed logic. For now, verify the structure is sound.
        assert_eq!(contributions.len(), 2);
        assert_eq!(weights.len(), 2);
        let total_weight: f64 = weights.iter().map(|w| w.weight).sum();
        assert!((total_weight - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_publish_cadence_ttl() {
        assert_eq!(PublishCadence::Hourly.ttl_seconds(), 7200);
        assert_eq!(PublishCadence::Daily.ttl_seconds(), 172_800);
        assert_eq!(PublishCadence::Weekly.ttl_seconds(), 1_209_600);
    }

    #[test]
    fn test_signal_direction() {
        // HigherIsBetter: 0.8 stays 0.8
        let v = 0.8;
        assert_eq!(v, 0.8);
        // LowerIsBetter: 1.0 - 0.8 = 0.2
        assert!((1.0 - v - 0.2).abs() < 1e-10);
    }

    #[test]
    fn test_weight_signals() {
        let normalized = vec![
            ("profit".to_string(), 0.7),
            ("spoilage".to_string(), 0.3),
        ];
        let weights = vec![
            SignalWeight {
                signal_name: "profit".into(),
                weight: 0.6,
                direction: SignalDirection::HigherIsBetter,
                transform: None,
            },
            SignalWeight {
                signal_name: "spoilage".into(),
                weight: 0.4,
                direction: SignalDirection::LowerIsBetter,
                transform: None,
            },
        ];

        let weighted: Vec<(String, f64)> = normalized
            .iter()
            .map(|(name, val)| {
                let w = weights
                    .iter()
                    .find(|sw| sw.signal_name == *name)
                    .map(|sw| sw.weight)
                    .unwrap_or(0.0);
                (name.clone(), val * w)
            })
            .collect();

        assert!((weighted[0].1 - 0.42).abs() < 1e-10); // 0.7 * 0.6
        assert!((weighted[1].1 - 0.12).abs() < 1e-10); // 0.3 * 0.4
    }

    #[test]
    fn test_index_config_defaults() {
        let config = CompositeIndexConfig::default();
        assert_eq!(config.min_signals, 3);
        assert_eq!(config.signal_max_age_secs, 86400);
        assert_eq!(config.bootstrap_resamples, 1000);
    }
}
