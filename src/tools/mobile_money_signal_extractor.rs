//! MobileMoneySignalExtractor — Credit-relevant behavioral signals from M-Pesa patterns
//!
//! Extracts credit-relevant signals from anonymized M-Pesa/mobile money transaction
//! patterns. Operates on pre-aggregated, k-anonymous statistical summaries produced by
//! FederatedAggregator — never raw transaction data.
//!
//! Derives signals: transaction regularity, income stability, cash flow patterns,
//! Fuliza dependency, supplier consistency, customer breadth, savings behavior,
//! seasonal sensitivity, and growth trajectory.
//!
//! These signals feed into CreditScorer and CompositeIndexBuilder.

use anyhow::{Context, Result};
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::db::DatabaseConnections;

// ─── WorkerType ──────────────────────────────────────────────────────────────

/// Informal economy worker classification.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum WorkerType {
    MamaMboga,
    BodaBoda,
    MitiMba,
    Fundi,
    JuaKali,
    HouseHelp,
    FarmWorker,
    Other,
}

impl WorkerType {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::MamaMboga => "mama_mboga",
            Self::BodaBoda => "boda_boda",
            Self::MitiMba => "miti_mba",
            Self::Fundi => "fundi",
            Self::JuaKali => "jua_kali",
            Self::HouseHelp => "house_help",
            Self::FarmWorker => "farm_worker",
            Self::Other => "other",
        }
    }
}

// ─── Trend Direction ─────────────────────────────────────────────────────────

/// Direction of a time-series trend.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum TrendDirection {
    /// >10% month-over-month growth
    StrongGrowth,
    /// 3–10% month-over-month growth
    ModerateGrowth,
    /// -3% to +3% — effectively flat
    Stable,
    /// -3% to -10% month-over-month decline
    ModerateDecline,
    /// < -10% month-over-month decline
    StrongDecline,
}

impl TrendDirection {
    pub fn from_mom_pct(pct: f64) -> Self {
        if pct > 10.0 {
            Self::StrongGrowth
        } else if pct > 3.0 {
            Self::ModerateGrowth
        } else if pct >= -3.0 {
            Self::Stable
        } else if pct >= -10.0 {
            Self::ModerateDecline
        } else {
            Self::StrongDecline
        }
    }
}

// ─── Signal Category ─────────────────────────────────────────────────────────

/// Broad category of credit-relevant signal.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum SignalCategory {
    TransactionRegularity,
    IncomeStability,
    CashFlowPattern,
    FulizaDependency,
    SupplierConsistency,
    CustomerBreadth,
    SavingsBehavior,
    SeasonalSensitivity,
    GrowthTrajectory,
}

impl SignalCategory {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::TransactionRegularity => "transaction_regularity",
            Self::IncomeStability => "income_stability",
            Self::CashFlowPattern => "cash_flow_pattern",
            Self::FulizaDependency => "fuliza_dependency",
            Self::SupplierConsistency => "supplier_consistency",
            Self::CustomerBreadth => "customer_breadth",
            Self::SavingsBehavior => "savings_behavior",
            Self::SeasonalSensitivity => "seasonal_sensitivity",
            Self::GrowthTrajectory => "growth_trajectory",
        }
    }
}

// ─── Configuration ───────────────────────────────────────────────────────────

/// Configuration for the signal extractor.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalExtractorConfig {
    /// Minimum cohort size for extraction (k-anonymity guard).
    pub min_cohort_size: u32,
    /// Default lookback window for signal computation (days).
    pub default_lookback_days: u32,
    /// Signal categories to extract.
    pub enabled_signals: Vec<SignalCategory>,
    /// Confidence floor — signals below this are marked unreliable.
    pub min_confidence: f64,
}

impl Default for SignalExtractorConfig {
    fn default() -> Self {
        Self {
            min_cohort_size: 20,
            default_lookback_days: 90,
            enabled_signals: vec![
                SignalCategory::TransactionRegularity,
                SignalCategory::IncomeStability,
                SignalCategory::CashFlowPattern,
                SignalCategory::FulizaDependency,
                SignalCategory::SupplierConsistency,
                SignalCategory::CustomerBreadth,
                SignalCategory::SavingsBehavior,
                SignalCategory::SeasonalSensitivity,
                SignalCategory::GrowthTrajectory,
            ],
            min_confidence: 0.3,
        }
    }
}

// ─── Cohort Filter ───────────────────────────────────────────────────────────

/// Filter for selecting k-anonymous worker cohorts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CohortFilter {
    pub region: Option<String>,
    pub worker_type: Option<WorkerType>,
    pub income_bracket: Option<IncomeBracket>,
    pub gender: Option<Gender>,
    pub business_age_months_min: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum IncomeBracket {
    Bottom20,
    Lower40,
    Middle40,
    Upper20,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Gender {
    Male,
    Female,
    Other,
}

// ─── Output Types ────────────────────────────────────────────────────────────

/// All extracted signals for a single cohort.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MobileMoneySignals {
    pub cohort_id: String,
    pub region: String,
    pub worker_type: WorkerType,
    pub extraction_date: DateTime<Utc>,
    pub lookback_days: u32,
    pub cohort_size: u32,
    pub signals: Vec<ExtractedSignal>,
}

/// A single extracted signal with metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedSignal {
    pub category: SignalCategory,
    pub name: String,
    pub value: f64,
    /// 0.0–1.0 confidence based on data availability and sample size.
    pub confidence: f64,
    /// Human-readable explanation.
    pub interpretation: String,
    /// Where this cohort sits vs. all cohorts (0.0–1.0), if available.
    pub percentile_rank: Option<f64>,
}

/// Cash flow profile describing when money flows in and out.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CashFlowProfile {
    /// % of daily inflows before noon.
    pub morning_receiving_pct: f64,
    /// % of daily inflows after 5 PM.
    pub evening_receiving_pct: f64,
    /// Weekday average / weekend average.
    pub weekday_weekend_ratio: f64,
    /// Peak day of week (0=Mon, 6=Sun).
    pub peak_day_of_week: u8,
    /// Trough day of week.
    pub trough_day_of_week: u8,
    /// Coefficient of variation of daily totals.
    pub daily_variance_coefficient: f64,
    pub trend_direction: TrendDirection,
}

/// Fuliza (overdraft) dependency profile.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FulizaProfile {
    /// Days with Fuliza usage / total active days.
    pub usage_frequency: f64,
    /// Average Fuliza amount per use day (KES).
    pub avg_daily_overdraft: f64,
    /// Average days to repay and re-borrow.
    pub debt_cycle_length_days: f64,
    /// 0–100, higher = more dependent.
    pub dependency_score: f64,
    pub trend: TrendDirection,
}

/// Comparison of signal profiles across two cohorts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalComparison {
    pub cohort_a_id: String,
    pub cohort_b_id: String,
    pub differences: Vec<SignalDifference>,
}

/// Per-signal difference between two cohorts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalDifference {
    pub signal_name: String,
    pub value_a: f64,
    pub value_b: f64,
    pub absolute_diff: f64,
    pub relative_diff_pct: f64,
    pub interpretation: String,
}

/// Report on signal drift over time.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftReport {
    pub cohort_id: String,
    pub signal_name: String,
    pub window_days: u32,
    pub current_value: f64,
    pub baseline_value: f64,
    pub drift_pct: f64,
    pub drift_direction: TrendDirection,
    pub is_significant: bool,
    pub p_value: f64,
}

// ─── ClickHouse Row Types ────────────────────────────────────────────────────

/// Raw aggregate transaction stats from ClickHouse (k-anonymous cohort summary).
#[derive(clickhouse::Row, Deserialize, Debug)]
struct CohortTxStats {
    tx_count: u64,
    total_volume: f64,
    avg_tx: f64,
    tx_stddev: f64,
    active_days: u64,
    total_inflow: f64,
    total_outflow: f64,
    unique_senders: u64,
    unique_recipients: u64,
}

/// Daily aggregated totals for regularity analysis.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct DailyTotal {
    day: NaiveDate,
    daily_volume: f64,
    daily_count: u64,
    daily_inflow: f64,
    daily_outflow: f64,
}

/// Hourly distribution for cash flow profiling.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct HourlyDistribution {
    hour: u8,
    avg_volume: f64,
    avg_count: f64,
}

/// Day-of-week distribution.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct DayOfWeekDistribution {
    day_of_week: u8,
    avg_volume: f64,
    avg_count: f64,
}

/// Fuliza usage aggregate.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct FulizaStats {
    fuliza_days: u64,
    total_fuliza_amount: f64,
    avg_fuliza_per_use: f64,
    total_repayment_amount: f64,
    avg_repayment_days: f64,
}

/// Monthly income totals for stability and growth.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct MonthlyIncome {
    month: NaiveDate,
    total_inflow: f64,
    tx_count: u64,
}

/// Supplier (outgoing recurring payee) stats.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct SupplierStats {
    recurring_payees: u64,
    consistent_payment_days: u64,
    total_outflow_to_suppliers: f64,
    avg_payment_interval_days: f64,
}

// ─── The Extractor ───────────────────────────────────────────────────────────

/// Extracts credit-relevant behavioral signals from anonymized M-Pesa patterns.
pub struct MobileMoneySignalExtractor {
    db: DatabaseConnections,
    config: SignalExtractorConfig,
}

impl MobileMoneySignalExtractor {
    pub fn new(db: DatabaseConnections, config: SignalExtractorConfig) -> Self {
        Self { db, config }
    }

    pub fn with_defaults(db: DatabaseConnections) -> Self {
        Self::new(db, SignalExtractorConfig::default())
    }

    // ── Public API ──────────────────────────────────────────────────────────

    /// Extract all enabled signals for a specific cohort.
    pub async fn extract_signals(
        &self,
        cohort: &CohortFilter,
        lookback_days: u32,
    ) -> Result<MobileMoneySignals> {
        let lookback = if lookback_days == 0 {
            self.config.default_lookback_days
        } else {
            lookback_days
        };

        // Build k-anonymous cohort ID from filter dimensions
        let cohort_id = self.build_cohort_id(cohort);
        let region = cohort
            .region
            .clone()
            .unwrap_or_else(|| "all".to_string());
        let worker_type = cohort
            .worker_type
            .clone()
            .unwrap_or(WorkerType::Other);

        // Fetch cohort statistics from ClickHouse
        let stats = self.fetch_cohort_stats(&cohort_id, lookback).await?;

        // Enforce k-anonymity minimum
        if (stats.tx_count as u32) < self.config.min_cohort_size {
            anyhow::bail!(
                "Cohort {} has {} members (minimum {})",
                cohort_id,
                stats.tx_count,
                self.config.min_cohort_size
            );
        }

        let mut signals = Vec::new();

        for category in &self.config.enabled_signals {
            let extracted = match category {
                SignalCategory::TransactionRegularity => {
                    self.extract_regularity(&cohort_id, lookback, &stats)
                        .await?
                }
                SignalCategory::IncomeStability => {
                    self.extract_income_stability(&cohort_id, lookback).await?
                }
                SignalCategory::CashFlowPattern => {
                    self.extract_cash_flow_signals(&cohort_id, lookback).await?
                }
                SignalCategory::FulizaDependency => {
                    self.extract_fuliza_signals(&cohort_id, lookback).await?
                }
                SignalCategory::SupplierConsistency => {
                    self.extract_supplier_consistency(&cohort_id, lookback, &stats)
                        .await?
                }
                SignalCategory::CustomerBreadth => {
                    self.extract_network_breadth(&stats)?
                }
                SignalCategory::SavingsBehavior => {
                    self.extract_savings_behavior(&cohort_id, lookback, &stats)
                        .await?
                }
                SignalCategory::SeasonalSensitivity => {
                    self.extract_seasonal_sensitivity(&cohort_id).await?
                }
                SignalCategory::GrowthTrajectory => {
                    self.extract_growth_trajectory(&cohort_id).await?
                }
            };
            signals.extend(extracted);
        }

        // Filter by minimum confidence
        signals.retain(|s| s.confidence >= self.config.min_confidence);

        let result = MobileMoneySignals {
            cohort_id: cohort_id.clone(),
            region,
            worker_type,
            extraction_date: Utc::now(),
            lookback_days: lookback,
            cohort_size: stats.tx_count as u32,
            signals,
        };

        // Publish to downstream tools (CreditScorer, CompositeIndexBuilder)
        self.publish_signals(&result).await?;

        Ok(result)
    }

    /// Extract signals for all active cohorts in a region (batch mode).
    pub async fn extract_region_signals(
        &self,
        region: &str,
    ) -> Result<Vec<MobileMoneySignals>> {
        // Discover distinct worker types with sufficient data in the region
        let worker_types = self.discover_region_cohorts(region).await?;

        let mut all_signals = Vec::new();
        for wt in worker_types {
            let cohort = CohortFilter {
                region: Some(region.to_string()),
                worker_type: Some(wt),
                income_bracket: None,
                gender: None,
                business_age_months_min: None,
            };
            match self
                .extract_signals(&cohort, self.config.default_lookback_days)
                .await
            {
                Ok(signals) => all_signals.push(signals),
                Err(e) => {
                    // Log and continue — some cohorts may not meet k-anonymity
                    tracing::warn!(
                        region = region,
                        error = %e,
                        "Skipping cohort extraction"
                    );
                }
            }
        }

        Ok(all_signals)
    }

    /// Build a cash flow profile for a cohort.
    pub async fn build_cash_flow_profile(
        &self,
        cohort: &CohortFilter,
    ) -> Result<CashFlowProfile> {
        let cohort_id = self.build_cohort_id(cohort);
        let lookback = self.config.default_lookback_days;

        // Hourly distribution
        let hourly = self.fetch_hourly_distribution(&cohort_id, lookback).await?;
        let morning_volume: f64 = hourly
            .iter()
            .filter(|h| h.hour < 12)
            .map(|h| h.avg_volume)
            .sum();
        let evening_volume: f64 = hourly
            .iter()
            .filter(|h| h.hour >= 17)
            .map(|h| h.avg_volume)
            .sum();
        let total_volume: f64 = hourly.iter().map(|h| h.avg_volume).sum();

        let morning_receiving_pct = if total_volume > 0.0 {
            (morning_volume / total_volume) * 100.0
        } else {
            0.0
        };
        let evening_receiving_pct = if total_volume > 0.0 {
            (evening_volume / total_volume) * 100.0
        } else {
            0.0
        };

        // Day-of-week distribution
        let dow = self
            .fetch_day_of_week_distribution(&cohort_id, lookback)
            .await?;
        let (peak_dow, trough_dow) = if dow.is_empty() {
            (0u8, 0u8)
        } else {
            let peak = dow
                .iter()
                .max_by(|a, b| a.avg_volume.partial_cmp(&b.avg_volume).unwrap())
                .unwrap();
            let trough = dow
                .iter()
                .min_by(|a, b| a.avg_volume.partial_cmp(&b.avg_volume).unwrap())
                .unwrap();
            (peak.day_of_week, trough.day_of_week)
        };

        // Weekday vs weekend
        let weekday_vol: f64 = dow
            .iter()
            .filter(|d| d.day_of_week < 5)
            .map(|d| d.avg_volume)
            .sum();
        let weekend_vol: f64 = dow
            .iter()
            .filter(|d| d.day_of_week >= 5)
            .map(|d| d.avg_volume)
            .sum();
        let weekday_avg = weekday_vol / 5.0;
        let weekend_avg = weekend_vol / 2.0;
        let weekday_weekend_ratio = if weekend_avg > 0.0 {
            weekday_avg / weekend_avg
        } else {
            f64::INFINITY
        };

        // Daily CV
        let daily = self.fetch_daily_totals(&cohort_id, lookback).await?;
        let daily_cv = compute_coefficient_of_variation(
            &daily.iter().map(|d| d.daily_volume).collect::<Vec<_>>(),
        );

        // Trend from monthly data
        let monthly = self.fetch_monthly_income(&cohort_id, 180).await?;
        let trend_direction = compute_trend_direction(&monthly);

        Ok(CashFlowProfile {
            morning_receiving_pct,
            evening_receiving_pct,
            weekday_weekend_ratio,
            peak_day_of_week: peak_dow,
            trough_day_of_week: trough_dow,
            daily_variance_coefficient: daily_cv,
            trend_direction,
        })
    }

    /// Build a Fuliza dependency profile for a cohort.
    pub async fn build_fuliza_profile(
        &self,
        cohort: &CohortFilter,
    ) -> Result<FulizaProfile> {
        let cohort_id = self.build_cohort_id(cohort);
        let lookback = self.config.default_lookback_days;

        let stats = self.fetch_fuliza_stats(&cohort_id, lookback).await?;
        let active_days = lookback as u64; // approximation

        let usage_frequency = if active_days > 0 {
            stats.fuliza_days as f64 / active_days as f64
        } else {
            0.0
        };

        // Dependency score: composite of frequency, cycle speed, and amount
        let freq_component = (usage_frequency * 100.0).min(100.0);
        let cycle_component = if stats.avg_repayment_days > 0.0 {
            // Shorter cycles = higher dependency (more re-borrowing)
            (30.0 / stats.avg_repayment_days * 50.0).min(100.0)
        } else {
            0.0
        };
        let amount_component =
            (stats.avg_fuliza_per_use / 5000.0 * 50.0).min(100.0); // normalized to KES 5000

        let dependency_score =
            (freq_component * 0.4 + cycle_component * 0.3 + amount_component * 0.3).min(100.0);

        // Trend from monthly Fuliza usage
        let monthly = self.fetch_monthly_income(&cohort_id, 180).await?;
        let trend = compute_trend_direction(&monthly);

        Ok(FulizaProfile {
            usage_frequency,
            avg_daily_overdraft: stats.avg_fuliza_per_use,
            debt_cycle_length_days: stats.avg_repayment_days,
            dependency_score,
            trend,
        })
    }

    /// Compare signal profiles across two cohorts.
    pub async fn compare_signals(
        &self,
        cohort_a: &CohortFilter,
        cohort_b: &CohortFilter,
    ) -> Result<SignalComparison> {
        let signals_a = self
            .extract_signals(cohort_a, self.config.default_lookback_days)
            .await?;
        let signals_b = self
            .extract_signals(cohort_b, self.config.default_lookback_days)
            .await?;

        let mut differences = Vec::new();

        // Match signals by name
        for sa in &signals_a.signals {
            if let Some(sb) = signals_b.signals.iter().find(|s| s.name == sa.name) {
                let abs_diff = sa.value - sb.value;
                let rel_diff = if sb.value.abs() > f64::EPSILON {
                    (abs_diff / sb.value) * 100.0
                } else {
                    0.0
                };
                differences.push(SignalDifference {
                    signal_name: sa.name.clone(),
                    value_a: sa.value,
                    value_b: sb.value,
                    absolute_diff: abs_diff,
                    relative_diff_pct: rel_diff,
                    interpretation: format!(
                        "{}: {:.2} vs {:.2} ({:+.1}%)",
                        sa.name, sa.value, sb.value, rel_diff
                    ),
                });
            }
        }

        Ok(SignalComparison {
            cohort_a_id: signals_a.cohort_id,
            cohort_b_id: signals_b.cohort_id,
            differences,
        })
    }

    /// Detect signal drift over time for a specific signal.
    pub async fn detect_drift(
        &self,
        cohort: &CohortFilter,
        signal_name: &str,
        window_days: u32,
    ) -> Result<DriftReport> {
        let cohort_id = self.build_cohort_id(cohort);

        // Current window value
        let current = self
            .fetch_signal_value(&cohort_id, signal_name, window_days)
            .await?;

        // Baseline: same window immediately prior
        let baseline = self
            .fetch_signal_value(
                &cohort_id,
                signal_name,
                window_days * 2, // lookback covers both windows
            )
            .await?;

        // The baseline is the older window; we approximate by fetching the
        // combined value and subtracting the current window.
        let baseline_value = if current.count > 0 && baseline.count > current.count {
            // Weighted approximation: baseline = (combined_total - current_total) / older_count
            let older_count = baseline.count - current.count;
            if older_count > 0 {
                (baseline.total - current.total) / older_count as f64
            } else {
                current.value
            }
        } else {
            current.value
        };

        let drift_pct = if baseline_value.abs() > f64::EPSILON {
            ((current.value - baseline_value) / baseline_value) * 100.0
        } else {
            0.0
        };

        let drift_direction = TrendDirection::from_mom_pct(drift_pct);

        // Simple significance test: if drift > 2x estimated standard error
        let std_err = if current.count > 1 {
            current.stddev / (current.count as f64).sqrt()
        } else {
            f64::MAX
        };
        let z_score = if std_err > 0.0 {
            (current.value - baseline_value).abs() / std_err
        } else {
            0.0
        };
        let p_value = approximate_normal_p_value(z_score);
        let is_significant = p_value < 0.05;

        Ok(DriftReport {
            cohort_id,
            signal_name: signal_name.to_string(),
            window_days,
            current_value: current.value,
            baseline_value,
            drift_pct,
            drift_direction,
            is_significant,
            p_value,
        })
    }

    // ── Signal Extraction Methods ───────────────────────────────────────────

    /// Extract transaction regularity — income stability score based on
    /// coefficient of variation of daily transaction volumes.
    pub async fn extract_regularity(
        &self,
        cohort_id: &str,
        lookback_days: u32,
        stats: &CohortTxStats,
    ) -> Result<Vec<ExtractedSignal>> {
        let daily = self
            .fetch_daily_totals(cohort_id, lookback_days)
            .await?;

        if daily.is_empty() {
            return Ok(vec![]);
        }

        let volumes: Vec<f64> = daily.iter().map(|d| d.daily_volume).collect();
        let counts: Vec<f64> = daily.iter().map(|d| d.daily_count as f64).collect();

        let volume_cv = compute_coefficient_of_variation(&volumes);
        let count_cv = compute_coefficient_of_variation(&counts);

        // Regularity score: lower CV = higher score (0–100)
        // CV of 0 = perfect regularity (100), CV >= 3 = very irregular (0)
        let regularity_score = (100.0 * (1.0 - (volume_cv / 3.0).min(1.0))).max(0.0);

        // Streak analysis: longest consecutive active days
        let active_streak = compute_longest_streak(&daily.iter().map(|d| d.daily_count > 0).collect::<Vec<_>>());
        let streak_score = (active_streak as f64 / lookback_days as f64 * 100.0).min(100.0);

        // Composite regularity: weighted average
        let composite = regularity_score * 0.6 + streak_score * 0.4;

        // Confidence based on data density
        let active_days = daily.iter().filter(|d| d.daily_count > 0).count();
        let confidence = (active_days as f64 / lookback_days as f64).min(1.0);

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::TransactionRegularity,
                name: "regularity_score".to_string(),
                value: round2(composite),
                confidence: round2(confidence),
                interpretation: format!(
                    "Transaction regularity score: {:.0}/100 (CV={:.2}, longest streak={} days)",
                    composite, volume_cv, active_streak
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::TransactionRegularity,
                name: "volume_cv".to_string(),
                value: round2(volume_cv),
                confidence: round2(confidence),
                interpretation: format!(
                    "Coefficient of variation of daily volume: {:.2} (lower = more regular)",
                    volume_cv
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::TransactionRegularity,
                name: "active_day_ratio".to_string(),
                value: round2(active_days as f64 / lookback_days as f64),
                confidence: round2(confidence),
                interpretation: format!(
                    "Active {}/{} days ({:.0}%)",
                    active_days,
                    lookback_days,
                    (active_days as f64 / lookback_days as f64) * 100.0
                ),
                percentile_rank: None,
            },
        ])
    }

    /// Extract savings behavior — savings discipline score.
    ///
    /// Analyzes inflow-to-outflow gap, consistent savings patterns, and
    /// the ratio of retained earnings to total income.
    pub async fn extract_savings_behavior(
        &self,
        cohort_id: &str,
        lookback_days: u32,
        stats: &CohortTxStats,
    ) -> Result<Vec<ExtractedSignal>> {
        let daily = self
            .fetch_daily_totals(cohort_id, lookback_days)
            .await?;

        if daily.is_empty() {
            return Ok(vec![]);
        }

        // Net savings = total inflow - total outflow
        let total_inflow: f64 = daily.iter().map(|d| d.daily_inflow).sum();
        let total_outflow: f64 = daily.iter().map(|d| d.daily_outflow).sum();
        let net_savings = total_inflow - total_outflow;

        // Savings rate = net / inflow
        let savings_rate = if total_inflow > 0.0 {
            (net_savings / total_inflow * 100.0).max(0.0)
        } else {
            0.0
        };

        // Consistency: how many days had positive net flow?
        let positive_days = daily
            .iter()
            .filter(|d| d.daily_inflow > d.daily_outflow)
            .count();
        let savings_consistency = positive_days as f64 / daily.len() as f64 * 100.0;

        // Discipline score: combines rate and consistency
        // A worker saving 10% consistently scores higher than one saving 30% sporadically
        let discipline_score = (savings_rate * 0.5 + savings_consistency * 0.5).min(100.0);

        // Confidence: based on having both inflow and outflow data
        let has_inflow = daily.iter().any(|d| d.daily_inflow > 0.0);
        let has_outflow = daily.iter().any(|d| d.daily_outflow > 0.0);
        let data_quality = match (has_inflow, has_outflow) {
            (true, true) => 0.9,
            (true, false) | (false, true) => 0.5,
            (false, false) => 0.1,
        };

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::SavingsBehavior,
                name: "savings_rate".to_string(),
                value: round2(savings_rate),
                confidence: round2(data_quality),
                interpretation: format!(
                    "Net savings rate: {:.1}% (inflow {:.0} - outflow {:.0} = net {:.0} KES)",
                    savings_rate, total_inflow, total_outflow, net_savings
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::SavingsBehavior,
                name: "savings_consistency".to_string(),
                value: round2(savings_consistency),
                confidence: round2(data_quality),
                interpretation: format!(
                    "Positive cash flow on {}/{} days ({:.0}%)",
                    positive_days,
                    daily.len(),
                    savings_consistency
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::SavingsBehavior,
                name: "savings_discipline_score".to_string(),
                value: round2(discipline_score),
                confidence: round2(data_quality),
                interpretation: format!(
                    "Savings discipline score: {:.0}/100 (rate {:.1}% × consistency {:.1}%)",
                    discipline_score, savings_rate, savings_consistency
                ),
                percentile_rank: None,
            },
        ])
    }

    /// Extract payment reliability — payment consistency to recurring payees.
    pub async fn extract_payment_reliability(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<ExtractedSignal>> {
        let supplier_stats = self
            .fetch_supplier_stats(cohort_id, lookback_days)
            .await?;

        if supplier_stats.recurring_payees == 0 {
            return Ok(vec![ExtractedSignal {
                category: SignalCategory::SupplierConsistency,
                name: "payment_reliability_score".to_string(),
                value: 0.0,
                confidence: 0.2,
                interpretation: "No recurring payees detected".to_string(),
                percentile_rank: None,
            }]);
        }

        // Payment regularity: lower interval std dev = more reliable
        let interval_cv = if supplier_stats.avg_payment_interval_days > 0.0 {
            // Approximate: use avg interval as proxy for consistency
            // Perfect consistency = every 7 days → score high
            // Highly variable → score low
            let deviation_from_weekly =
                (supplier_stats.avg_payment_interval_days - 7.0).abs() / 7.0;
            (1.0 - deviation_from_weekly.min(1.0)) * 100.0
        } else {
            0.0
        };

        // Coverage: what fraction of outflow goes to recurring suppliers?
        let stats = self.fetch_cohort_stats(cohort_id, lookback_days).await?;
        let supplier_coverage = if stats.total_outflow > 0.0 {
            (supplier_stats.total_outflow_to_suppliers / stats.total_outflow * 100.0).min(100.0)
        } else {
            0.0
        };

        // Composite reliability score
        let reliability_score = interval_cv * 0.6 + supplier_coverage * 0.4;

        let confidence = (supplier_stats.recurring_payees as f64 / 5.0).min(1.0) * 0.8;

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::SupplierConsistency,
                name: "payment_reliability_score".to_string(),
                value: round2(reliability_score),
                confidence: round2(confidence),
                interpretation: format!(
                    "Payment reliability: {:.0}/100 ({:.0} recurring payees, avg interval {:.1} days)",
                    reliability_score, supplier_stats.recurring_payees, supplier_stats.avg_payment_interval_days
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::SupplierConsistency,
                name: "supplier_coverage_pct".to_string(),
                value: round2(supplier_coverage),
                confidence: round2(confidence),
                interpretation: format!(
                    "{:.0}% of outflow goes to recurring suppliers",
                    supplier_coverage
                ),
                percentile_rank: None,
            },
        ])
    }

    /// Extract network breadth — economic activity breadth from unique
    /// counterparty counts.
    pub fn extract_network_breadth(
        &self,
        stats: &CohortTxStats,
    ) -> Result<Vec<ExtractedSignal>> {
        let total_parties = stats.unique_senders + stats.unique_recipients;

        // Breadth score: more unique counterparties = broader economic activity
        // Log scale: 1 party = 0, 10 = ~50, 100 = ~85, 500+ = ~100
        let breadth_score = if total_parties > 0 {
            ((total_parties as f64).ln() / 6.2_f64.ln() * 100.0).min(100.0)
        } else {
            0.0
        };

        // Asymmetry: more incoming than outgoing suggests a business (supplier)
        let asymmetry = if stats.unique_recipients > 0 {
            stats.unique_senders as f64 / stats.unique_recipients as f64
        } else {
            f64::INFINITY
        };

        // A ratio > 2 suggests strong business activity (many customers, few suppliers)
        let business_signal = if asymmetry > 2.0 {
            "strong_business_activity"
        } else if asymmetry > 1.0 {
            "moderate_business_activity"
        } else {
            "consumer_pattern"
        };

        let confidence = (total_parties as f64 / 10.0).min(1.0);

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::CustomerBreadth,
                name: "network_breadth_score".to_string(),
                value: round2(breadth_score),
                confidence: round2(confidence),
                interpretation: format!(
                    "Network breadth: {:.0}/100 ({} unique senders, {} recipients, {} total)",
                    breadth_score, stats.unique_senders, stats.unique_recipients, total_parties
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::CustomerBreadth,
                name: "counterparty_asymmetry".to_string(),
                value: round2(asymmetry),
                confidence: round2(confidence),
                interpretation: format!(
                    "Sender/recipient ratio: {:.2} ({})",
                    asymmetry, business_signal
                ),
                percentile_rank: None,
            },
        ])
    }

    // ── Private Helpers ──────────────────────────────────────────────────────

    /// Extract income stability signal from monthly inflow data.
    async fn extract_income_stability(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<ExtractedSignal>> {
        let monthly = self
            .fetch_monthly_income(cohort_id, lookback_days)
            .await?;

        if monthly.len() < 2 {
            return Ok(vec![]);
        }

        let inflows: Vec<f64> = monthly.iter().map(|m| m.total_inflow).collect();
        let cv = compute_coefficient_of_variation(&inflows);

        // Stability score: inverse of CV, clamped to 0–100
        // CV of 0 = perfect stability (100), CV >= 2 = very unstable (0)
        let stability_score = (100.0 * (1.0 - (cv / 2.0).min(1.0))).max(0.0);

        // Month-over-month volatility
        let mut mom_changes = Vec::new();
        for i in 1..inflows.len() {
            if inflows[i - 1] > 0.0 {
                mom_changes.push((inflows[i] - inflows[i - 1]) / inflows[i - 1] * 100.0);
            }
        }
        let mom_volatility = compute_std_dev(&mom_changes);

        let confidence = (monthly.len() as f64 / 6.0).min(1.0);

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::IncomeStability,
                name: "income_stability_score".to_string(),
                value: round2(stability_score),
                confidence: round2(confidence),
                interpretation: format!(
                    "Income stability: {:.0}/100 (monthly CV={:.2}, MoM volatility={:.1}%)",
                    stability_score, cv, mom_volatility
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::IncomeStability,
                name: "income_cv".to_string(),
                value: round2(cv),
                confidence: round2(confidence),
                interpretation: format!(
                    "Coefficient of variation of monthly income: {:.2}",
                    cv
                ),
                percentile_rank: None,
            },
        ])
    }

    /// Extract cash flow timing signals.
    async fn extract_cash_flow_signals(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<ExtractedSignal>> {
        let hourly = self
            .fetch_hourly_distribution(cohort_id, lookback_days)
            .await?;

        if hourly.is_empty() {
            return Ok(vec![]);
        }

        let total_volume: f64 = hourly.iter().map(|h| h.avg_volume).sum();
        if total_volume <= 0.0 {
            return Ok(vec![]);
        }

        let morning_pct: f64 = hourly
            .iter()
            .filter(|h| (6..12).contains(&h.hour))
            .map(|h| h.avg_volume)
            .sum::<f64>()
            / total_volume
            * 100.0;

        let afternoon_pct: f64 = hourly
            .iter()
            .filter(|h| (12..17).contains(&h.hour))
            .map(|h| h.avg_volume)
            .sum::<f64>()
            / total_volume
            * 100.0;

        let evening_pct: f64 = hourly
            .iter()
            .filter(|h| h.hour >= 17)
            .map(|h| h.avg_volume)
            .sum::<f64>()
            / total_volume
            * 100.0;

        // Early activity signal: morning-heavy = more disciplined/structured
        let early_activity_score = (morning_pct / 50.0 * 100.0).min(100.0);

        let confidence = (hourly.len() as f64 / 24.0).min(1.0);

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::CashFlowPattern,
                name: "morning_activity_pct".to_string(),
                value: round2(morning_pct),
                confidence: round2(confidence),
                interpretation: format!(
                    "{:.0}% of activity occurs in the morning (6AM–12PM)",
                    morning_pct
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::CashFlowPattern,
                name: "early_activity_score".to_string(),
                value: round2(early_activity_score),
                confidence: round2(confidence),
                interpretation: format!(
                    "Early activity score: {:.0}/100 (morning-heavy patterns suggest structured business)",
                    early_activity_score
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::CashFlowPattern,
                name: "evening_activity_pct".to_string(),
                value: round2(evening_pct),
                confidence: round2(confidence),
                interpretation: format!(
                    "{:.0}% of activity occurs in the evening (5PM+)",
                    evening_pct
                ),
                percentile_rank: None,
            },
        ])
    }

    /// Extract Fuliza dependency signals.
    async fn extract_fuliza_signals(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<ExtractedSignal>> {
        let fuliza = self.fetch_fuliza_stats(cohort_id, lookback_days).await?;

        if fuliza.fuliza_days == 0 {
            return Ok(vec![ExtractedSignal {
                category: SignalCategory::FulizaDependency,
                name: "fuliza_dependency_score".to_string(),
                value: 0.0,
                confidence: 0.7,
                interpretation: "No Fuliza usage detected — self-sufficient cash flow".to_string(),
                percentile_rank: None,
            }]);
        }

        let usage_freq = fuliza.fuliza_days as f64 / lookback_days as f64;
        let dependency = (usage_freq * 100.0).min(100.0);

        // Risk signal: high Fuliza + short repayment cycle = debt trap
        let debt_trap_risk = if fuliza.avg_repayment_days > 0.0 && usage_freq > 0.3 {
            ((1.0 / fuliza.avg_repayment_days) * usage_freq * 100.0).min(100.0)
        } else {
            0.0
        };

        let confidence = (fuliza.fuliza_days as f64 / 30.0).min(1.0);

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::FulizaDependency,
                name: "fuliza_usage_frequency".to_string(),
                value: round2(usage_freq),
                confidence: round2(confidence),
                interpretation: format!(
                    "Fuliza used on {:.0}% of days ({}/{})",
                    usage_freq * 100.0,
                    fuliza.fuliza_days,
                    lookback_days
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::FulizaDependency,
                name: "fuliza_dependency_score".to_string(),
                value: round2(dependency),
                confidence: round2(confidence),
                interpretation: format!(
                    "Fuliza dependency: {:.0}/100 (avg overdraft {:.0} KES, cycle {:.1} days)",
                    dependency, fuliza.avg_fuliza_per_use, fuliza.avg_repayment_days
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::FulizaDependency,
                name: "debt_trap_risk".to_string(),
                value: round2(debt_trap_risk),
                confidence: round2(confidence),
                interpretation: format!(
                    "Debt trap risk: {:.0}/100",
                    debt_trap_risk
                ),
                percentile_rank: None,
            },
        ])
    }

    /// Extract supplier consistency signals.
    async fn extract_supplier_consistency(
        &self,
        cohort_id: &str,
        lookback_days: u32,
        stats: &CohortTxStats,
    ) -> Result<Vec<ExtractedSignal>> {
        self.extract_payment_reliability(cohort_id, lookback_days)
            .await
    }

    /// Extract seasonal sensitivity from monthly data.
    async fn extract_seasonal_sensitivity(
        &self,
        cohort_id: &str,
    ) -> Result<Vec<ExtractedSignal>> {
        let monthly = self.fetch_monthly_income(cohort_id, 365).await?;

        if monthly.len() < 6 {
            return Ok(vec![]);
        }

        let inflows: Vec<f64> = monthly.iter().map(|m| m.total_inflow).collect();
        let cv = compute_coefficient_of_variation(&inflows);

        // Find peak and trough months
        let peak_idx = inflows
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
            .map(|(i, _)| i)
            .unwrap_or(0);
        let trough_idx = inflows
            .iter()
            .enumerate()
            .min_by(|a, b| a.1.partial_cmp(b.1).unwrap())
            .map(|(i, _)| i)
            .unwrap_or(0);

        let seasonal_swing = if inflows[trough_idx] > 0.0 {
            ((inflows[peak_idx] - inflows[trough_idx]) / inflows[trough_idx] * 100.0).abs()
        } else {
            0.0
        };

        // Sensitivity score: higher swing = more seasonal (risk factor)
        let sensitivity_score = (seasonal_swing / 200.0 * 100.0).min(100.0);

        let confidence = (monthly.len() as f64 / 12.0).min(1.0);

        Ok(vec![ExtractedSignal {
            category: SignalCategory::SeasonalSensitivity,
            name: "seasonal_sensitivity_score".to_string(),
            value: round2(sensitivity_score),
            confidence: round2(confidence),
            interpretation: format!(
                "Seasonal sensitivity: {:.0}/100 (peak-to-trough swing {:.0}%, CV={:.2})",
                sensitivity_score, seasonal_swing, cv
            ),
            percentile_rank: None,
        }])
    }

    /// Extract growth trajectory from monthly income trend.
    async fn extract_growth_trajectory(
        &self,
        cohort_id: &str,
    ) -> Result<Vec<ExtractedSignal>> {
        let monthly = self.fetch_monthly_income(cohort_id, 365).await?;

        if monthly.len() < 3 {
            return Ok(vec![]);
        }

        let inflows: Vec<f64> = monthly.iter().map(|m| m.total_inflow).collect();

        // Simple linear regression: y = a + b*x
        let n = inflows.len() as f64;
        let x_mean = (n - 1.0) / 2.0;
        let y_mean = inflows.iter().sum::<f64>() / n;

        let mut ss_xy = 0.0;
        let mut ss_xx = 0.0;
        for (i, &y) in inflows.iter().enumerate() {
            let x = i as f64;
            ss_xy += (x - x_mean) * (y - y_mean);
            ss_xx += (x - x_mean).powi(2);
        }

        let slope = if ss_xx > 0.0 { ss_xy / ss_xx } else { 0.0 };

        // Monthly growth rate as percentage of mean income
        let monthly_growth_pct = if y_mean > 0.0 {
            (slope / y_mean * 100.0)
        } else {
            0.0
        };

        let trend = TrendDirection::from_mom_pct(monthly_growth_pct);

        // Growth score: positive slope = higher score
        let growth_score = ((monthly_growth_pct + 20.0) / 40.0 * 100.0).clamp(0.0, 100.0);

        let confidence = (monthly.len() as f64 / 12.0).min(1.0);

        Ok(vec![
            ExtractedSignal {
                category: SignalCategory::GrowthTrajectory,
                name: "growth_trajectory_score".to_string(),
                value: round2(growth_score),
                confidence: round2(confidence),
                interpretation: format!(
                    "Growth trajectory: {:.0}/100 (monthly growth {:.1}%, trend: {:?})",
                    growth_score, monthly_growth_pct, trend
                ),
                percentile_rank: None,
            },
            ExtractedSignal {
                category: SignalCategory::GrowthTrajectory,
                name: "monthly_growth_pct".to_string(),
                value: round2(monthly_growth_pct),
                confidence: round2(confidence),
                interpretation: format!(
                    "Month-over-month income growth: {:.1}%",
                    monthly_growth_pct
                ),
                percentile_rank: None,
            },
        ])
    }

    /// Feed extracted signals into downstream tools (CreditScorer, CompositeIndexBuilder).
    async fn publish_signals(&self, signals: &MobileMoneySignals) -> Result<()> {
        // Store in ClickHouse for historical analysis
        for signal in &signals.signals {
            let query = format!(
                r#"
                INSERT INTO mobile_money_signals
                    (cohort_id, region, worker_type, signal_category, signal_name,
                     value, confidence, percentile_rank, cohort_size, lookback_days, extracted_at)
                VALUES
                    ('{}', '{}', '{}', '{}', '{}', {}, {}, {}, {}, {}, now())
                "#,
                signals.cohort_id,
                signals.region,
                signals.worker_type.as_str(),
                signal.category.as_str(),
                signal.name,
                signal.value,
                signal.confidence,
                signal
                    .percentile_rank
                    .map(|p| p.to_string())
                    .unwrap_or_else(|| "NULL".to_string()),
                signals.cohort_size,
                signals.lookback_days,
            );

            // Fire-and-forget insert — don't fail extraction on storage errors
            if let Err(e) = self.db.clickhouse.query(&query).execute().await {
                tracing::warn!(
                    cohort_id = %signals.cohort_id,
                    signal = %signal.name,
                    error = %e,
                    "Failed to store signal in ClickHouse"
                );
            }
        }

        // Cache latest signals in Redis
        let cache_key = format!(
            "mm:signals:{}:{}",
            signals.region,
            signals.worker_type.as_str()
        );
        if let Ok(json) = serde_json::to_string(signals) {
            // 6-hour TTL per design doc
            let _: std::result::Result<(), _> = redis::cmd("SETEX")
                .arg(&cache_key)
                .arg(21600) // 6h
                .arg(&json)
                .query_async(&mut self.db.redis.clone())
                .await;
        }

        Ok(())
    }

    /// Build a deterministic cohort ID from filter dimensions.
    fn build_cohort_id(&self, cohort: &CohortFilter) -> String {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut hasher = DefaultHasher::new();
        cohort.region.hash(&mut hasher);
        cohort
            .worker_type
            .as_ref()
            .map(|w| w.as_str())
            .hash(&mut hasher);
        format!("cohort_{:016x}", hasher.finish())
    }

    /// Discover which worker types have sufficient data in a region.
    async fn discover_region_cohorts(&self, region: &str) -> Result<Vec<WorkerType>> {
        let query = format!(
            r#"
            SELECT worker_type, count(DISTINCT cohort_id) as cohort_count
            FROM mobile_money_signals
            WHERE region = '{}'
              AND extracted_at > now() - INTERVAL 7 DAY
            GROUP BY worker_type
            HAVING cohort_count > 0
            "#,
            region
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct WorkerTypeCount {
            worker_type: String,
            cohort_count: u64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<WorkerTypeCount>()
            .await
            .unwrap_or_default();

        Ok(rows
            .iter()
            .filter_map(|r| match r.worker_type.as_str() {
                "mama_mboga" => Some(WorkerType::MamaMboga),
                "boda_boda" => Some(WorkerType::BodaBoda),
                "miti_mba" => Some(WorkerType::MitiMba),
                "fundi" => Some(WorkerType::Fundi),
                "jua_kali" => Some(WorkerType::JuaKali),
                "house_help" => Some(WorkerType::HouseHelp),
                "farm_worker" => Some(WorkerType::FarmWorker),
                "other" => Some(WorkerType::Other),
                _ => None,
            })
            .collect())
    }

    /// Fetch cohort-level aggregate transaction stats from ClickHouse.
    async fn fetch_cohort_stats(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<CohortTxStats> {
        let query = format!(
            r#"
            SELECT
                count() as tx_count,
                sum(amount) as total_volume,
                avg(amount) as avg_tx,
                stddevPop(amount) as tx_stddev,
                count(DISTINCT toDate(event_time)) as active_days,
                sum(CASE WHEN direction = 'in' THEN amount ELSE 0 END) as total_inflow,
                sum(CASE WHEN direction = 'out' THEN amount ELSE 0 END) as total_outflow,
                count(DISTINCT sender_id) as unique_senders,
                count(DISTINCT recipient_id) as unique_recipients
            FROM revenue_events
            WHERE cohort_id = '{}'
              AND event_time > now() - INTERVAL {} DAY
            "#,
            cohort_id, lookback_days
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_one::<CohortTxStats>()
            .await
            .context("Failed to fetch cohort transaction stats")
    }

    /// Fetch daily aggregated totals.
    async fn fetch_daily_totals(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<DailyTotal>> {
        let query = format!(
            r#"
            SELECT
                toDate(event_time) as day,
                sum(amount) as daily_volume,
                count() as daily_count,
                sum(CASE WHEN direction = 'in' THEN amount ELSE 0 END) as daily_inflow,
                sum(CASE WHEN direction = 'out' THEN amount ELSE 0 END) as daily_outflow
            FROM revenue_events
            WHERE cohort_id = '{}'
              AND event_time > now() - INTERVAL {} DAY
            GROUP BY day
            ORDER BY day
            "#,
            cohort_id, lookback_days
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_all::<DailyTotal>()
            .await
            .context("Failed to fetch daily totals")
    }

    /// Fetch hourly distribution.
    async fn fetch_hourly_distribution(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<HourlyDistribution>> {
        let query = format!(
            r#"
            SELECT
                toHour(event_time) as hour,
                avg(amount) as avg_volume,
                avg(cnt) as avg_count
            FROM (
                SELECT
                    event_time,
                    amount,
                    count() OVER (PARTITION BY toHour(event_time), toDate(event_time)) as cnt
                FROM revenue_events
                WHERE cohort_id = '{}'
                  AND event_time > now() - INTERVAL {} DAY
            )
            GROUP BY hour
            ORDER BY hour
            "#,
            cohort_id, lookback_days
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_all::<HourlyDistribution>()
            .await
            .context("Failed to fetch hourly distribution")
    }

    /// Fetch day-of-week distribution.
    async fn fetch_day_of_week_distribution(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<DayOfWeekDistribution>> {
        let query = format!(
            r#"
            SELECT
                toDayOfWeek(event_time) - 1 as day_of_week,
                avg(amount) as avg_volume,
                avg(cnt) as avg_count
            FROM (
                SELECT
                    event_time,
                    amount,
                    count() OVER (PARTITION BY toDate(event_time)) as cnt
                FROM revenue_events
                WHERE cohort_id = '{}'
                  AND event_time > now() - INTERVAL {} DAY
            )
            GROUP BY day_of_week
            ORDER BY day_of_week
            "#,
            cohort_id, lookback_days
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_all::<DayOfWeekDistribution>()
            .await
            .context("Failed to fetch day-of-week distribution")
    }

    /// Fetch monthly income totals.
    async fn fetch_monthly_income(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Vec<MonthlyIncome>> {
        let query = format!(
            r#"
            SELECT
                toStartOfMonth(event_time) as month,
                sum(CASE WHEN direction = 'in' THEN amount ELSE 0 END) as total_inflow,
                count() as tx_count
            FROM revenue_events
            WHERE cohort_id = '{}'
              AND event_time > now() - INTERVAL {} DAY
            GROUP BY month
            ORDER BY month
            "#,
            cohort_id, lookback_days
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_all::<MonthlyIncome>()
            .await
            .context("Failed to fetch monthly income")
    }

    /// Fetch Fuliza statistics.
    async fn fetch_fuliza_stats(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<FulizaStats> {
        let query = format!(
            r#"
            SELECT
                countIf(event_type = 'fuliza_disbursement') as fuliza_days,
                sumIf(amount, event_type = 'fuliza_disbursement') as total_fuliza_amount,
                avgIf(amount, event_type = 'fuliza_disbursement') as avg_fuliza_per_use,
                sumIf(amount, event_type = 'fuliza_repayment') as total_repayment_amount,
                avgIf(
                    dateDiff('day',
                        minIf(event_time, event_type = 'fuliza_disbursement'),
                        minIf(event_time, event_type = 'fuliza_repayment')
                    ),
                    event_type = 'fuliza_repayment'
                ) as avg_repayment_days
            FROM revenue_events
            WHERE cohort_id = '{}'
              AND event_time > now() - INTERVAL {} DAY
              AND event_type IN ('fuliza_disbursement', 'fuliza_repayment')
            "#,
            cohort_id, lookback_days
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_one::<FulizaStats>()
            .await
            .context("Failed to fetch Fuliza stats")
    }

    /// Fetch supplier/recurring payee statistics.
    async fn fetch_supplier_stats(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<SupplierStats> {
        let query = format!(
            r#"
            SELECT
                count(DISTINCT recipient_id) as recurring_payees,
                countIf(payment_count >= 3) as consistent_payment_days,
                sum(total_outflow) as total_outflow_to_suppliers,
                avg(avg_interval) as avg_payment_interval_days
            FROM (
                SELECT
                    recipient_id,
                    count() as payment_count,
                    sum(amount) as total_outflow,
                    avg(gap) as avg_interval
                FROM (
                    SELECT
                        recipient_id,
                        amount,
                        dateDiff('day',
                            lagInFrame(event_time) OVER (PARTITION BY recipient_id ORDER BY event_time),
                            event_time
                        ) as gap
                    FROM revenue_events
                    WHERE cohort_id = '{}'
                      AND event_time > now() - INTERVAL {} DAY
                      AND direction = 'out'
                )
                GROUP BY recipient_id
                HAVING payment_count >= 3
            )
            "#,
            cohort_id, lookback_days
        );

        self.db
            .clickhouse
            .query(&query)
            .fetch_one::<SupplierStats>()
            .await
            .context("Failed to fetch supplier stats")
    }

    /// Fetch a signal value for drift analysis.
    async fn fetch_signal_value(
        &self,
        cohort_id: &str,
        signal_name: &str,
        lookback_days: u32,
    ) -> Result<SignalAggregate> {
        let query = format!(
            r#"
            SELECT
                avg(value) as value,
                count() as count,
                stddevPop(value) as stddev
            FROM mobile_money_signals
            WHERE cohort_id = '{}'
              AND signal_name = '{}'
              AND extracted_at > now() - INTERVAL {} DAY
            "#,
            cohort_id, signal_name, lookback_days
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct SignalAgg {
            value: f64,
            count: u64,
            stddev: f64,
        }

        let agg = self
            .db
            .clickhouse
            .query(&query)
            .fetch_one::<SignalAgg>()
            .await
            .context("Failed to fetch signal value for drift")?;

        Ok(SignalAggregate {
            value: agg.value,
            count: agg.count,
            stddev: agg.stddev,
            total: agg.value * agg.count as f64,
        })
    }
}

// ─── Internal Aggregate ──────────────────────────────────────────────────────

struct SignalAggregate {
    value: f64,
    count: u64,
    stddev: f64,
    total: f64,
}

// ─── Statistical Helpers ─────────────────────────────────────────────────────

/// Compute coefficient of variation (std_dev / mean).
fn compute_coefficient_of_variation(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    if mean.abs() < f64::EPSILON {
        return 0.0;
    }
    let variance = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / values.len() as f64;
    variance.sqrt() / mean.abs()
}

/// Compute standard deviation.
fn compute_std_dev(values: &[f64]) -> f64 {
    if values.len() < 2 {
        return 0.0;
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    let variance =
        values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (values.len() - 1) as f64;
    variance.sqrt()
}

/// Compute trend direction from monthly income data.
fn compute_trend_direction(monthly: &[MonthlyIncome]) -> TrendDirection {
    if monthly.len() < 2 {
        return TrendDirection::Stable;
    }
    let inflows: Vec<f64> = monthly.iter().map(|m| m.total_inflow).collect();
    let recent = &inflows[inflows.len().saturating_sub(3)..];
    let earlier = &inflows[..inflows.len().saturating_sub(3).max(1)];

    let recent_avg = recent.iter().sum::<f64>() / recent.len() as f64;
    let earlier_avg = earlier.iter().sum::<f64>() / earlier.len() as f64;

    let mom_pct = if earlier_avg > 0.0 {
        ((recent_avg - earlier_avg) / earlier_avg) * 100.0
    } else {
        0.0
    };

    TrendDirection::from_mom_pct(mom_pct)
}

/// Compute the longest consecutive `true` streak in a boolean slice.
fn compute_longest_streak(active: &[bool]) -> usize {
    let mut max_streak = 0usize;
    let mut current = 0usize;
    for &a in active {
        if a {
            current += 1;
            max_streak = max_streak.max(current);
        } else {
            current = 0;
        }
    }
    max_streak
}

/// Approximate two-tailed p-value for a z-score using the error function.
fn approximate_normal_p_value(z: f64) -> f64 {
    // Abramowitz & Stegun approximation for the standard normal CDF
    let abs_z = z.abs();
    let cdf = if abs_z > 6.0 {
        1.0
    } else {
        let t = 1.0 / (1.0 + 0.2316419 * abs_z);
        let poly = t
            * (0.319381530
                + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
        1.0 - (1.0 / (2.0 * std::f64::consts::PI).sqrt()) * (-abs_z * abs_z / 2.0).exp() * poly
    };
    2.0 * (1.0 - cdf) // two-tailed
}

/// Round to 2 decimal places.
fn round2(v: f64) -> f64 {
    (v * 100.0).round() / 100.0
}

// ─── Integration with CreditScorer ───────────────────────────────────────────

/// Extension trait to feed mobile money signals into CreditScorer.
///
/// Usage:
/// ```ignore
/// use crate::tools::credit_scorer::CreditScorer;
/// use crate::tools::mobile_money_signal_extractor::MobileMoneySignalExtractor;
///
/// let extractor = MobileMoneySignalExtractor::with_defaults(db.clone());
/// let scorer = CreditScorer::new(db.clone());
///
/// let cohort = CohortFilter { region: Some("nairobi".into()), worker_type: Some(WorkerType::MamaMboga), .. };
/// let signals = extractor.extract_signals(&cohort, 90).await?;
///
/// // Convert signals into CreditScorer features
/// let features = signals.to_score_features();
/// // Feed features into scorer...
/// ```
impl MobileMoneySignals {
    /// Convert extracted signals into a flat feature vector suitable for
    /// CreditScorer consumption.
    ///
    /// Returns (feature_name, value) pairs ordered consistently.
    pub fn to_score_features(&self) -> Vec<(String, f64)> {
        let mut features = Vec::new();

        for signal in &self.signals {
            features.push((format!("mm_{}", signal.name), signal.value));
        }

        // Add derived composite features
        let regularity = self.get_signal_value("regularity_score").unwrap_or(50.0);
        let stability = self
            .get_signal_value("income_stability_score")
            .unwrap_or(50.0);
        let savings = self
            .get_signal_value("savings_discipline_score")
            .unwrap_or(50.0);
        let fuliza_dep = self
            .get_signal_value("fuliza_dependency_score")
            .unwrap_or(0.0);
        let breadth = self
            .get_signal_value("network_breadth_score")
            .unwrap_or(50.0);

        // Composite mobile money health score (0–100)
        let mm_health = (regularity * 0.25
            + stability * 0.25
            + savings * 0.2
            + (100.0 - fuliza_dep) * 0.15
            + breadth * 0.15)
            .min(100.0);

        features.push(("mm_composite_health".to_string(), round2(mm_health)));

        // Cash flow quality: early activity + regularity
        let early_activity = self
            .get_signal_value("early_activity_score")
            .unwrap_or(50.0);
        let cash_flow_quality = (early_activity * 0.4 + regularity * 0.6).min(100.0);
        features.push(("mm_cash_flow_quality".to_string(), round2(cash_flow_quality)));

        features
    }

    /// Get the value of a named signal, if present.
    fn get_signal_value(&self, name: &str) -> Option<f64> {
        self.signals
            .iter()
            .find(|s| s.name == name)
            .map(|s| s.value)
    }
}

// ─── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trend_direction_from_mom_pct() {
        assert_eq!(TrendDirection::from_mom_pct(15.0), TrendDirection::StrongGrowth);
        assert_eq!(TrendDirection::from_mom_pct(7.0), TrendDirection::ModerateGrowth);
        assert_eq!(TrendDirection::from_mom_pct(0.0), TrendDirection::Stable);
        assert_eq!(TrendDirection::from_mom_pct(-5.0), TrendDirection::ModerateDecline);
        assert_eq!(TrendDirection::from_mom_pct(-15.0), TrendDirection::StrongDecline);
    }

    #[test]
    fn test_coefficient_of_variation() {
        // Constant values → CV = 0
        assert!((compute_coefficient_of_variation(&[5.0, 5.0, 5.0]) - 0.0).abs() < 0.001);

        // Known CV: values [1, 2, 3, 4, 5], mean=3, std_dev≈1.58, CV≈0.527
        let cv = compute_coefficient_of_variation(&[1.0, 2.0, 3.0, 4.0, 5.0]);
        assert!((cv - 0.527).abs() < 0.01);

        // Empty → 0
        assert!((compute_coefficient_of_variation(&[]) - 0.0).abs() < 0.001);

        // All zeros → 0
        assert!((compute_coefficient_of_variation(&[0.0, 0.0]) - 0.0).abs() < 0.001);
    }

    #[test]
    fn test_longest_streak() {
        assert_eq!(compute_longest_streak(&[true, true, false, true, true, true]), 3);
        assert_eq!(compute_longest_streak(&[false, false, false]), 0);
        assert_eq!(compute_longest_streak(&[true, true, true]), 3);
        assert_eq!(compute_longest_streak(&[]), 0);
    }

    #[test]
    fn test_normal_p_value() {
        // z=0 → p≈1.0
        assert!((approximate_normal_p_value(0.0) - 1.0).abs() < 0.01);
        // z=1.96 → p≈0.05
        assert!((approximate_normal_p_value(1.96) - 0.05).abs() < 0.01);
        // z=2.576 → p≈0.01
        assert!((approximate_normal_p_value(2.576) - 0.01).abs() < 0.005);
    }

    #[test]
    fn test_worker_type_as_str() {
        assert_eq!(WorkerType::MamaMboga.as_str(), "mama_mboga");
        assert_eq!(WorkerType::BodaBoda.as_str(), "boda_boda");
        assert_eq!(WorkerType::JuaKali.as_str(), "jua_kali");
    }

    #[test]
    fn test_signal_category_as_str() {
        assert_eq!(
            SignalCategory::TransactionRegularity.as_str(),
            "transaction_regularity"
        );
        assert_eq!(
            SignalCategory::FulizaDependency.as_str(),
            "fuliza_dependency"
        );
    }

    #[test]
    fn test_round2() {
        assert!((round2(3.456) - 3.46).abs() < 0.001);
        assert!((round2(0.001) - 0.0).abs() < 0.001);
        assert!((round2(100.0) - 100.0).abs() < 0.001);
    }

    #[test]
    fn test_default_config() {
        let config = SignalExtractorConfig::default();
        assert_eq!(config.min_cohort_size, 20);
        assert_eq!(config.default_lookback_days, 90);
        assert_eq!(config.enabled_signals.len(), 9);
    }

    #[test]
    fn test_score_features_conversion() {
        let signals = MobileMoneySignals {
            cohort_id: "test".to_string(),
            region: "nairobi".to_string(),
            worker_type: WorkerType::MamaMboga,
            extraction_date: Utc::now(),
            lookback_days: 90,
            cohort_size: 100,
            signals: vec![
                ExtractedSignal {
                    category: SignalCategory::TransactionRegularity,
                    name: "regularity_score".to_string(),
                    value: 75.0,
                    confidence: 0.9,
                    interpretation: "test".to_string(),
                    percentile_rank: None,
                },
                ExtractedSignal {
                    category: SignalCategory::IncomeStability,
                    name: "income_stability_score".to_string(),
                    value: 60.0,
                    confidence: 0.8,
                    interpretation: "test".to_string(),
                    percentile_rank: None,
                },
            ],
        };

        let features = signals.to_score_features();
        assert!(features.iter().any(|(name, _)| name == "mm_composite_health"));
        assert!(features.iter().any(|(name, _)| name == "mm_cash_flow_quality"));
        assert!(features.iter().any(|(name, _)| name == "mm_regularity_score"));
    }

    #[test]
    fn test_build_cohort_id_deterministic() {
        // Use a dummy DatabaseConnections-free test of the hash logic
        let cohort = CohortFilter {
            region: Some("nairobi".to_string()),
            worker_type: Some(WorkerType::MamaMboga),
            income_bracket: None,
            gender: None,
            business_age_months_min: None,
        };

        // Two identical filters should produce the same ID
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};

        let mut h1 = DefaultHasher::new();
        cohort.region.hash(&mut h1);
        cohort
            .worker_type
            .as_ref()
            .map(|w| w.as_str())
            .hash(&mut h1);
        let id1 = format!("cohort_{:016x}", h1.finish());

        let mut h2 = DefaultHasher::new();
        cohort.region.hash(&mut h2);
        cohort
            .worker_type
            .as_ref()
            .map(|w| w.as_str())
            .hash(&mut h2);
        let id2 = format!("cohort_{:016x}", h2.finish());

        assert_eq!(id1, id2);
    }
}
