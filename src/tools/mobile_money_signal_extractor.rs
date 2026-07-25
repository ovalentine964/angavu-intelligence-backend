//! MobileMoneySignalExtractor — Credit signals from anonymized M-Pesa patterns
//!
//! Extracts credit-relevant signals from anonymized mobile money transaction
//! patterns. Operates on pre-aggregated, k-anonymous statistical summaries
//! produced by FederatedAggregator — never on raw individual transactions.
//!
//! Core signals extracted:
//! - **Regularity**: How consistent are transaction patterns (low CV = stable income)
//! - **Savings behavior**: Recurring savings patterns and discipline
//! - **Payment reliability**: Consistency of outgoing payments to recurring payees
//! - **Network breadth**: Diversity of incoming payee base (customer breadth proxy)
//!
//! These signals feed into CreditScorer (as Alama Score features) and
//! CompositeIndexBuilder (as input signals for economic health indices).

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::db::DatabaseConnections;

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

/// Configuration for the mobile money signal extractor.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalExtractorConfig {
    /// Minimum cohort size for extraction (k-anonymity guard).
    pub min_cohort_size: u32,
    /// Default lookback window for signal computation (days).
    pub default_lookback_days: u32,
    /// Signal categories to extract.
    pub enabled_signals: Vec<SignalCategory>,
}

impl Default for SignalExtractorConfig {
    fn default() -> Self {
        Self {
            min_cohort_size: 50,
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
        }
    }
}

/// Signal categories that can be extracted from mobile money patterns.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
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

// ---------------------------------------------------------------------------
// Output types
// ---------------------------------------------------------------------------

/// Full set of extracted signals for a k-anonymous cohort.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MobileMoneySignals {
    /// k-anonymous cohort identifier (never an individual).
    pub cohort_id: String,
    pub region: String,
    pub worker_type: WorkerType,
    pub extraction_date: DateTime<Utc>,
    pub lookback_days: u32,
    pub cohort_size: u32,
    pub signals: Vec<ExtractedSignal>,
}

/// A single extracted signal with confidence and interpretation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractedSignal {
    pub category: SignalCategory,
    pub name: String,
    pub value: f64,
    /// Confidence in this signal (0.0–1.0). Based on sample size and variance.
    pub confidence: f64,
    /// Human-readable explanation of the signal.
    pub interpretation: String,
    /// Where this cohort sits vs. all cohorts (0.0–100.0).
    pub percentile_rank: Option<f64>,
}

/// Cash flow profile derived from transaction timing patterns.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CashFlowProfile {
    /// % of daily inflows received before noon.
    pub morning_receiving_pct: f64,
    /// % of daily inflows received after 5 PM.
    pub evening_receiving_pct: f64,
    /// Weekday average / weekend average.
    pub weekday_weekend_ratio: f64,
    /// Day of week with highest volume (0=Mon, 6=Sun).
    pub peak_day_of_week: u8,
    /// Day of week with lowest volume.
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
    /// Average Fuliza amount on days it was used.
    pub avg_daily_overdraft: f64,
    /// Average days between borrowing and full repayment.
    pub debt_cycle_length_days: f64,
    /// Composite dependency score (0–100, higher = more dependent).
    pub dependency_score: f64,
    pub trend: TrendDirection,
}

/// Trend direction for a metric over time.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum TrendDirection {
    /// >10% month-over-month increase.
    StrongGrowth,
    /// 3–10% month-over-month increase.
    ModerateGrowth,
    /// -3% to +3% month-over-month.
    Stable,
    /// -3% to -10% month-over-month.
    ModerateDecline,
    /// >10% month-over-month decrease.
    StrongDecline,
}

/// Comparison of signal profiles across two cohorts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalComparison {
    pub cohort_a_id: String,
    pub cohort_b_id: String,
    pub signal_diffs: Vec<SignalDiff>,
    pub summary: String,
}

/// Difference of a single signal between two cohorts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SignalDiff {
    pub signal_name: String,
    pub value_a: f64,
    pub value_b: f64,
    pub absolute_diff: f64,
    pub percentage_diff: f64,
    pub significant: bool,
}

/// Drift detection report for a signal over time.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DriftReport {
    pub cohort_id: String,
    pub signal_name: String,
    pub window_days: u32,
    pub current_value: f64,
    pub baseline_value: f64,
    pub drift_magnitude: f64,
    pub drift_direction: TrendDirection,
    pub is_significant: bool,
    pub computed_at: DateTime<Utc>,
}

/// Worker type enumeration for cohort filtering.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
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

/// Cohort filter for selecting which group to analyze.
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
    Middle20,
    Upper20,
    Top20,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Gender {
    Male,
    Female,
}

// ---------------------------------------------------------------------------
// Internal ClickHouse row types
// ---------------------------------------------------------------------------

/// Aggregated daily transaction statistics from ClickHouse.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct DailyTxStats {
    day: chrono::NaiveDate,
    tx_count: u64,
    total_inflow: f64,
    total_outflow: f64,
    unique_senders: u64,
    unique_receivers: u64,
    morning_inflow: f64,
    evening_inflow: f64,
}

/// Aggregated savings pattern from ClickHouse.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct SavingsStats {
    month: chrono::NaiveDate,
    savings_deposit_count: u64,
    savings_deposit_total: f64,
    savings_withdrawal_count: u64,
    savings_withdrawal_total: f64,
    avg_days_between_deposits: f64,
}

/// Fuliza (overdraft) usage stats from ClickHouse.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct FulizaStats {
    month: chrono::NaiveDate,
    fuliza_days: u64,
    active_days: u64,
    total_overdraft: f64,
    avg_repay_days: f64,
}

/// Supplier payment stats from ClickHouse.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct PaymentStats {
    payee_id_hash: String,
    payment_count: u64,
    total_amount: f64,
    avg_interval_days: f64,
    interval_stddev: f64,
}

/// Customer breadth stats from ClickHouse.
#[derive(clickhouse::Row, Deserialize, Debug)]
struct BreadthStats {
    month: chrono::NaiveDate,
    unique_incoming_payees: u64,
    total_incoming_tx: u64,
    top5_payee_concentration: f64,
}

// ---------------------------------------------------------------------------
// MobileMoneySignalExtractor
// ---------------------------------------------------------------------------

/// The MobileMoneySignalExtractor tool.
///
/// Extracts credit-relevant signals from anonymized M-Pesa/mobile money
/// transaction patterns. All data comes from pre-aggregated, k-anonymous
/// cohort summaries — never individual-level transactions.
pub struct MobileMoneySignalExtractor {
    db: DatabaseConnections,
    config: SignalExtractorConfig,
}

impl MobileMoneySignalExtractor {
    pub fn new(db: DatabaseConnections, config: SignalExtractorConfig) -> Self {
        Self { db, config }
    }

    pub fn with_defaults(db: DatabaseConnections) -> Self {
        Self {
            db,
            config: SignalExtractorConfig::default(),
        }
    }

    // -----------------------------------------------------------------------
    // Public API — Signal extraction
    // -----------------------------------------------------------------------

    /// Extract all enabled signals for a specific cohort.
    ///
    /// Returns a `MobileMoneySignals` struct with one `ExtractedSignal` per
    /// enabled category. Each signal includes a confidence score based on
    /// cohort size and data availability.
    pub async fn extract_signals(
        &self,
        cohort: &CohortFilter,
        lookback_days: u32,
    ) -> Result<MobileMoneySignals> {
        let cohort_id = self.resolve_cohort_id(cohort).await?;
        let cohort_size = self.get_cohort_size(&cohort_id).await?;

        if cohort_size < self.config.min_cohort_size {
            return Err(anyhow!(
                "Cohort size {} below minimum k-anonymity threshold {}",
                cohort_size,
                self.config.min_cohort_size
            ));
        }

        let region = cohort.region.clone().unwrap_or_else(|| "all".to_string());
        let worker_type = cohort.worker_type.clone().unwrap_or(WorkerType::Other);

        let mut signals = Vec::new();

        for category in &self.config.enabled_signals {
            let extracted = match category {
                SignalCategory::TransactionRegularity => {
                    self.extract_regularity(&cohort_id, lookback_days).await?
                }
                SignalCategory::SavingsBehavior => {
                    self.extract_savings_behavior(&cohort_id, lookback_days).await?
                }
                SignalCategory::SupplierConsistency => {
                    self.extract_payment_reliability(&cohort_id, lookback_days).await?
                }
                SignalCategory::CustomerBreadth => {
                    self.extract_network_breadth(&cohort_id, lookback_days).await?
                }
                SignalCategory::IncomeStability => {
                    self.extract_income_stability(&cohort_id, lookback_days).await?
                }
                SignalCategory::CashFlowPattern => {
                    self.extract_cashflow_signal(&cohort_id, lookback_days).await?
                }
                SignalCategory::FulizaDependency => {
                    self.extract_fuliza_signal(&cohort_id, lookback_days).await?
                }
                SignalCategory::SeasonalSensitivity => {
                    self.extract_seasonal_sensitivity(&cohort_id, lookback_days).await?
                }
                SignalCategory::GrowthTrajectory => {
                    self.extract_growth_trajectory(&cohort_id, lookback_days).await?
                }
            };

            if let Some(signal) = extracted {
                signals.push(signal);
            }
        }

        Ok(MobileMoneySignals {
            cohort_id,
            region,
            worker_type,
            extraction_date: Utc::now(),
            lookback_days,
            cohort_size,
            signals,
        })
    }

    /// Extract signals for all active cohorts in a region (batch mode).
    pub async fn extract_region_signals(
        &self,
        region: &str,
    ) -> Result<Vec<MobileMoneySignals>> {
        let cohorts = self.list_cohorts_in_region(region).await?;
        let lookback = self.config.default_lookback_days;

        let mut results = Vec::with_capacity(cohorts.len());
        for cohort in cohorts {
            match self.extract_signals(&cohort, lookback).await {
                Ok(signals) => results.push(signals),
                Err(e) => {
                    // Log but continue — a single cohort failure shouldn't block the batch
                    eprintln!(
                        "Warning: failed to extract signals for cohort in {}: {}",
                        region, e
                    );
                }
            }
        }

        Ok(results)
    }

    /// Build cash flow profile for a cohort.
    pub async fn build_cash_flow_profile(
        &self,
        cohort: &CohortFilter,
    ) -> Result<CashFlowProfile> {
        let cohort_id = self.resolve_cohort_id(cohort).await?;

        let query = format!(
            r#"
            SELECT
                day,
                sum(total_inflow) as total_inflow,
                sum(morning_inflow) as morning_inflow,
                sum(evening_inflow) as evening_inflow,
                toDayOfWeek(day) as dow
            FROM aggregated_daily_transactions
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL 90 DAY
            GROUP BY day, dow
            ORDER BY day
            "#
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<DailyTxStats>()
            .await?;

        if rows.is_empty() {
            return Err(anyhow!("No transaction data found for cohort {}", cohort_id));
        }

        // Aggregate morning/evening percentages
        let total_inflow: f64 = rows.iter().map(|r| r.total_inflow).sum();
        let total_morning: f64 = rows.iter().map(|r| r.morning_inflow).sum();
        let total_evening: f64 = rows.iter().map(|r| r.evening_inflow).sum();

        let morning_pct = if total_inflow > 0.0 {
            (total_morning / total_inflow) * 100.0
        } else {
            0.0
        };
        let evening_pct = if total_inflow > 0.0 {
            (total_evening / total_inflow) * 100.0
        } else {
            0.0
        };

        // Weekday vs weekend
        let mut weekday_sum = 0.0;
        let mut weekday_count = 0u32;
        let mut weekend_sum = 0.0;
        let mut weekend_count = 0u32;

        for row in &rows {
            let dow = row.day.weekday().num_days_from_monday(); // 0=Mon, 6=Sun
            if dow < 5 {
                weekday_sum += row.total_inflow;
                weekday_count += 1;
            } else {
                weekend_sum += row.total_inflow;
                weekend_count += 1;
            }
        }

        let weekday_avg = if weekday_count > 0 {
            weekday_sum / weekday_count as f64
        } else {
            0.0
        };
        let weekend_avg = if weekend_count > 0 {
            weekend_sum / weekend_count as f64
        } else {
            0.0
        };
        let weekday_weekend_ratio = if weekend_avg > 0.0 {
            weekday_avg / weekend_avg
        } else {
            f64::INFINITY
        };

        // Peak and trough days
        let mut daily_by_dow = [0.0f64; 7];
        let mut count_by_dow = [0u32; 7];
        for row in &rows {
            let dow = row.day.weekday().num_days_from_monday() as usize;
            daily_by_dow[dow] += row.total_inflow;
            count_by_dow[dow] += 1;
        }
        let avg_by_dow: Vec<f64> = daily_by_dow
            .iter()
            .zip(count_by_dow.iter())
            .map(|(sum, cnt)| if *cnt > 0 { sum / *cnt as f64 } else { 0.0 })
            .collect();

        let peak_dow = avg_by_dow
            .iter()
            .enumerate()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i as u8)
            .unwrap_or(0);
        let trough_dow = avg_by_dow
            .iter()
            .enumerate()
            .min_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(i, _)| i as u8)
            .unwrap_or(0);

        // Daily coefficient of variation
        let daily_values: Vec<f64> = rows.iter().map(|r| r.total_inflow).collect();
        let cv = coefficient_of_variation(&daily_values);

        // Trend: compare last 30 days vs previous 30 days
        let mid = rows.len() / 2;
        let recent_avg = if mid > 0 {
            rows[mid..].iter().map(|r| r.total_inflow).sum::<f64>()
                / (rows.len() - mid) as f64
        } else {
            0.0
        };
        let earlier_avg = if mid > 0 {
            rows[..mid].iter().map(|r| r.total_inflow).sum::<f64>() / mid as f64
        } else {
            0.0
        };
        let trend = classify_trend(recent_avg, earlier_avg);

        Ok(CashFlowProfile {
            morning_receiving_pct: morning_pct,
            evening_receiving_pct: evening_pct,
            weekday_weekend_ratio,
            peak_day_of_week: peak_dow,
            trough_day_of_week: trough_dow,
            daily_variance_coefficient: cv,
            trend_direction: trend,
        })
    }

    /// Build Fuliza (overdraft) dependency profile.
    pub async fn build_fuliza_profile(
        &self,
        cohort: &CohortFilter,
    ) -> Result<FulizaProfile> {
        let cohort_id = self.resolve_cohort_id(cohort).await?;

        let query = format!(
            r#"
            SELECT
                toStartOfMonth(day) as month,
                sum(fuliza_days) as fuliza_days,
                sum(active_days) as active_days,
                sum(total_overdraft) as total_overdraft,
                avg(avg_repay_days) as avg_repay_days
            FROM aggregated_fuliza_usage
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL 180 DAY
            GROUP BY month
            ORDER BY month
            "#
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<FulizaStats>()
            .await?;

        if rows.is_empty() {
            return Ok(FulizaProfile {
                usage_frequency: 0.0,
                avg_daily_overdraft: 0.0,
                debt_cycle_length_days: 0.0,
                dependency_score: 0.0,
                trend: TrendDirection::Stable,
            });
        }

        let total_fuliza_days: u64 = rows.iter().map(|r| r.fuliza_days).sum();
        let total_active_days: u64 = rows.iter().map(|r| r.active_days).sum();
        let total_overdraft: f64 = rows.iter().map(|r| r.total_overdraft).sum();
        let avg_repay: f64 = rows
            .iter()
            .map(|r| r.avg_repay_days)
            .sum::<f64>()
            / rows.len() as f64;

        let usage_frequency = if total_active_days > 0 {
            total_fuliza_days as f64 / total_active_days as f64
        } else {
            0.0
        };

        let avg_daily_overdraft = if total_fuliza_days > 0 {
            total_overdraft / total_fuliza_days as f64
        } else {
            0.0
        };

        // Dependency score: composite of frequency, overdraft size, and cycle speed
        let freq_score = (usage_frequency * 100.0).min(100.0);
        let size_score = (avg_daily_overdraft / 5000.0 * 50.0).min(50.0);
        let cycle_score = if avg_repay > 0.0 {
            (30.0 / avg_repay * 20.0).min(20.0)
        } else {
            0.0
        };
        let dependency_score = (freq_score + size_score + cycle_score).min(100.0);

        // Trend from first half vs second half
        let mid = rows.len() / 2;
        let recent_freq = if mid > 0 {
            let r = &rows[mid..];
            let fd: u64 = r.iter().map(|x| x.fuliza_days).sum();
            let ad: u64 = r.iter().map(|x| x.active_days).sum();
            if ad > 0 {
                fd as f64 / ad as f64
            } else {
                0.0
            }
        } else {
            usage_frequency
        };
        let earlier_freq = if mid > 0 {
            let r = &rows[..mid];
            let fd: u64 = r.iter().map(|x| x.fuliza_days).sum();
            let ad: u64 = r.iter().map(|x| x.active_days).sum();
            if ad > 0 {
                fd as f64 / ad as f64
            } else {
                0.0
            }
        } else {
            usage_frequency
        };
        let trend = classify_trend(recent_freq, earlier_freq);

        Ok(FulizaProfile {
            usage_frequency,
            avg_daily_overdraft,
            debt_cycle_length_days: avg_repay,
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
        let lookback = self.config.default_lookback_days;
        let signals_a = self.extract_signals(cohort_a, lookback).await?;
        let signals_b = self.extract_signals(cohort_b, lookback).await?;

        let mut diffs = Vec::new();

        // Match signals by name
        for sa in &signals_a.signals {
            if let Some(sb) = signals_b.signals.iter().find(|s| s.name == sa.name) {
                let abs_diff = sa.value - sb.value;
                let pct_diff = if sb.value.abs() > f64::EPSILON {
                    (abs_diff / sb.value) * 100.0
                } else {
                    0.0
                };

                // Significance: both must have reasonable confidence
                let significant =
                    sa.confidence >= 0.5 && sb.confidence >= 0.5 && pct_diff.abs() >= 10.0;

                diffs.push(SignalDiff {
                    signal_name: sa.name.clone(),
                    value_a: sa.value,
                    value_b: sb.value,
                    absolute_diff: abs_diff,
                    percentage_diff: pct_diff,
                    significant,
                });
            }
        }

        let sig_count = diffs.iter().filter(|d| d.significant).count();
        let summary = format!(
            "Compared {} signals across cohorts. {} showed significant differences.",
            diffs.len(),
            sig_count
        );

        Ok(SignalComparison {
            cohort_a_id: signals_a.cohort_id,
            cohort_b_id: signals_b.cohort_id,
            signal_diffs: diffs,
            summary,
        })
    }

    /// Detect signal drift over time (are patterns changing?).
    pub async fn detect_drift(
        &self,
        cohort: &CohortFilter,
        signal_name: &str,
        window_days: u32,
    ) -> Result<DriftReport> {
        let cohort_id = self.resolve_cohort_id(cohort).await?;

        // Fetch current window and baseline window
        let query = format!(
            r#"
            SELECT
                value,
                extracted_at
            FROM mobile_money_signals
            WHERE cohort_id = '{cohort_id}'
              AND signal_name = '{signal_name}'
              AND extracted_at >= now() - INTERVAL {total_days} DAY
            ORDER BY extracted_at
            "#,
            total_days = window_days * 2
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct SignalPoint {
            value: f64,
            extracted_at: chrono::NaiveDateTime,
        }

        let points = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<SignalPoint>()
            .await?;

        if points.is_empty() {
            return Err(anyhow!(
                "No historical data for signal '{}' on cohort {}",
                signal_name,
                cohort_id
            ));
        }

        let mid = points.len() / 2;
        let baseline_avg = if mid > 0 {
            points[..mid].iter().map(|p| p.value).sum::<f64>() / mid as f64
        } else {
            points[0].value
        };
        let current_avg = if mid > 0 {
            points[mid..].iter().map(|p| p.value).sum::<f64>()
                / (points.len() - mid) as f64
        } else {
            points[0].value
        };

        let drift_magnitude = if baseline_avg.abs() > f64::EPSILON {
            ((current_avg - baseline_avg) / baseline_avg).abs()
        } else {
            0.0
        };

        let drift_direction = classify_trend(current_avg, baseline_avg);
        let is_significant = drift_magnitude >= 0.10; // 10% threshold

        Ok(DriftReport {
            cohort_id,
            signal_name: signal_name.to_string(),
            window_days,
            current_value: current_avg,
            baseline_value: baseline_avg,
            drift_magnitude,
            drift_direction,
            is_significant,
            computed_at: Utc::now(),
        })
    }

    // -----------------------------------------------------------------------
    // Core extraction methods (the four key signals)
    // -----------------------------------------------------------------------

    /// **Extract Regularity** — How consistent are transaction patterns.
    ///
    /// Computes the coefficient of variation (CV) of daily transaction counts
    /// and volumes over the lookback window. A low CV indicates a stable,
    /// predictable income stream — a strong credit signal.
    ///
    /// Returns a signal where:
    /// - value = 1.0 - normalized CV (higher = more regular)
    /// - confidence scales with cohort size and data completeness
    pub async fn extract_regularity(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                day,
                count() as tx_count,
                sum(amount) as daily_volume
            FROM aggregated_daily_transactions
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            GROUP BY day
            ORDER BY day
            "#
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct DailyRow {
            day: chrono::NaiveDate,
            tx_count: u64,
            daily_volume: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<DailyRow>()
            .await?;

        if rows.len() < 7 {
            return Ok(None); // Insufficient data
        }

        // CV of daily transaction count
        let counts: Vec<f64> = rows.iter().map(|r| r.tx_count as f64).collect();
        let cv_count = coefficient_of_variation(&counts);

        // CV of daily volume
        let volumes: Vec<f64> = rows.iter().map(|r| r.daily_volume).collect();
        let cv_volume = coefficient_of_variation(&volumes);

        // Combined regularity score: lower CV = higher regularity
        // Weight count CV more (volume can vary even with regular transactions)
        let combined_cv = cv_count * 0.6 + cv_volume * 0.4;

        // Invert and normalize: CV of 0 → perfect regularity (1.0), CV of 3+ → very irregular (0.0)
        let regularity_score = (1.0 - combined_cv / 3.0).clamp(0.0, 1.0);

        let confidence = compute_signal_confidence(rows.len(), self.config.min_cohort_size);

        let interpretation = if regularity_score >= 0.8 {
            format!(
                "Highly regular transactions (CV={:.2}). Strong income stability signal.",
                combined_cv
            )
        } else if regularity_score >= 0.5 {
            format!(
                "Moderately regular transactions (CV={:.2}). Some income variability.",
                combined_cv
            )
        } else {
            format!(
                "Irregular transactions (CV={:.2}). Income appears volatile.",
                combined_cv
            )
        };

        Ok(Some(ExtractedSignal {
            category: SignalCategory::TransactionRegularity,
            name: "transaction_regularity".to_string(),
            value: regularity_score,
            confidence,
            interpretation,
            percentile_rank: None, // Computed separately in batch ranking
        }))
    }

    /// **Extract Savings Behavior** — Savings discipline and patterns.
    ///
    /// Analyzes recurring deposits into savings wallets/accounts, consistency
    /// of deposit amounts, and net savings accumulation. Workers who
    /// demonstrate consistent savings behavior are lower credit risk.
    ///
    /// Returns a composite savings behavior score where:
    /// - value = 0.0–1.0 (higher = better savings discipline)
    /// - Components: deposit regularity, amount consistency, net accumulation
    pub async fn extract_savings_behavior(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                toStartOfMonth(day) as month,
                sum(savings_deposit_count) as deposit_count,
                sum(savings_deposit_total) as deposit_total,
                sum(savings_withdrawal_count) as withdrawal_count,
                sum(savings_withdrawal_total) as withdrawal_total,
                avg(avg_days_between_deposits) as avg_deposit_interval
            FROM aggregated_savings_patterns
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            GROUP BY month
            ORDER BY month
            "#
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<SavingsStats>()
            .await?;

        if rows.is_empty() {
            return Ok(None);
        }

        let total_deposits: u64 = rows.iter().map(|r| r.savings_deposit_count).sum();
        let total_deposit_amount: f64 = rows.iter().map(|r| r.savings_deposit_total).sum();
        let total_withdrawals: f64 = rows.iter().map(|r| r.savings_withdrawal_total).sum();
        let avg_interval: f64 = rows
            .iter()
            .map(|r| r.avg_days_between_deposits)
            .sum::<f64>()
            / rows.len() as f64;

        // Component 1: Deposit regularity (consistent intervals between deposits)
        // Ideal: deposit every 7-14 days
        let regularity = if avg_interval > 0.0 && avg_interval <= 30.0 {
            let deviation_from_weekly = (avg_interval - 7.0).abs() / 7.0;
            (1.0 - deviation_from_weekly).clamp(0.0, 1.0)
        } else if avg_interval > 30.0 {
            0.2 // Very infrequent deposits
        } else {
            0.5 // No clear pattern
        };

        // Component 2: Deposit consistency (do amounts stay similar?)
        let deposit_amounts: Vec<f64> = rows.iter().map(|r| r.savings_deposit_total).collect();
        let amount_cv = coefficient_of_variation(&deposit_amounts);
        let amount_consistency = (1.0 - amount_cv / 2.0).clamp(0.0, 1.0);

        // Component 3: Net savings ratio (deposits - withdrawals) / deposits
        let net_savings_ratio = if total_deposit_amount > 0.0 {
            ((total_deposit_amount - total_withdrawals) / total_deposit_amount).clamp(0.0, 1.0)
        } else {
            0.0
        };

        // Component 4: Savings frequency (deposits per month)
        let months = rows.len().max(1) as f64;
        let deposits_per_month = total_deposits as f64 / months;
        let frequency_score = (deposits_per_month / 4.0).min(1.0); // 4 deposits/month = ideal

        // Weighted composite
        let savings_score = regularity * 0.25
            + amount_consistency * 0.20
            + net_savings_ratio * 0.35
            + frequency_score * 0.20;

        let confidence = compute_signal_confidence(rows.len(), self.config.min_cohort_size);

        let interpretation = if savings_score >= 0.7 {
            format!(
                "Strong savings discipline: {:.0} deposits/month, {:.0}% net retention, regular intervals.",
                deposits_per_month,
                net_savings_ratio * 100.0
            )
        } else if savings_score >= 0.4 {
            format!(
                "Moderate savings: {:.0} deposits/month, {:.0}% net retention.",
                deposits_per_month,
                net_savings_ratio * 100.0
            )
        } else {
            format!(
                "Weak savings pattern: {:.0} deposits/month, {:.0}% net retention. Frequent withdrawals.",
                deposits_per_month,
                net_savings_ratio * 100.0
            )
        };

        Ok(Some(ExtractedSignal {
            category: SignalCategory::SavingsBehavior,
            name: "savings_behavior".to_string(),
            value: savings_score,
            confidence,
            interpretation,
            percentile_rank: None,
        }))
    }

    /// **Extract Payment Reliability** — Consistency of outgoing payments.
    ///
    /// Analyzes payments to recurring payees (suppliers, landlords, service
    /// providers) for consistency in timing and amount. Reliable payment
    /// patterns indicate good financial management and lower default risk.
    ///
    /// Returns a reliability score where:
    /// - value = 0.0–1.0 (higher = more reliable payments)
    /// - Considers: number of recurring payees, interval consistency, completion rate
    pub async fn extract_payment_reliability(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                payee_id_hash,
                count() as payment_count,
                sum(amount) as total_amount,
                avg(days_between_payments) as avg_interval,
                stddevPop(days_between_payments) as interval_stddev
            FROM aggregated_outgoing_payments
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            GROUP BY payee_id_hash
            HAVING payment_count >= 3
            ORDER BY payment_count DESC
            "#
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<PaymentStats>()
            .await?;

        if rows.is_empty() {
            return Ok(None);
        }

        let recurring_payee_count = rows.len();

        // For each recurring payee, compute their payment regularity
        let mut payee_scores: Vec<f64> = Vec::new();

        for row in &rows {
            // How consistent is the interval between payments?
            let interval_cv = if row.avg_interval_days > 0.0 {
                row.interval_stddev / row.avg_interval_days
            } else {
                0.0
            };
            let interval_score = (1.0 - interval_cv / 2.0).clamp(0.0, 1.0);

            // Payment frequency (more frequent = more established relationship)
            let freq_score = (row.payment_count as f64 / 10.0).min(1.0);

            // Per-payee reliability
            let payee_score = interval_score * 0.7 + freq_score * 0.3;
            payee_scores.push(payee_score);
        }

        // Overall payment reliability
        let avg_payee_score = payee_scores.iter().sum::<f64>() / payee_scores.len() as f64;

        // Breadth bonus: having multiple recurring payees is a positive signal
        let breadth_bonus = (recurring_payee_count as f64 / 5.0).min(1.0) * 0.15;

        let reliability_score = (avg_payee_score * 0.85 + breadth_bonus).min(1.0);

        let confidence = compute_signal_confidence(
            recurring_payee_count.max(1),
            self.config.min_cohort_size,
        );

        let interpretation = if reliability_score >= 0.7 {
            format!(
                "Highly reliable payments: {} recurring payees, consistent timing (avg score: {:.2}).",
                recurring_payee_count, avg_payee_score
            )
        } else if reliability_score >= 0.4 {
            format!(
                "Moderate payment reliability: {} recurring payees, some timing variation.",
                recurring_payee_count
            )
        } else {
            format!(
                "Inconsistent payments: {} recurring payees, irregular timing patterns.",
                recurring_payee_count
            )
        };

        Ok(Some(ExtractedSignal {
            category: SignalCategory::SupplierConsistency,
            name: "payment_reliability".to_string(),
            value: reliability_score,
            confidence,
            interpretation,
            percentile_rank: None,
        }))
    }

    /// **Extract Network Breadth** — Diversity of incoming payee base.
    ///
    /// Measures how many unique payees send money to this cohort. A broad
    /// customer base indicates business resilience — losing one customer
    /// has less impact. Also measures concentration (top-5 payee share).
    ///
    /// Returns a breadth score where:
    /// - value = 0.0–1.0 (higher = broader, more resilient customer base)
    /// - Components: unique payee count, concentration ratio, growth trend
    pub async fn extract_network_breadth(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                toStartOfMonth(day) as month,
                sum(unique_incoming_payees) as unique_payees,
                sum(total_incoming_tx) as total_tx,
                avg(top5_concentration) as top5_conc
            FROM aggregated_customer_breadth
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            GROUP BY month
            ORDER BY month
            "#
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<BreadthStats>()
            .await?;

        if rows.is_empty() {
            return Ok(None);
        }

        // Average unique payees per month
        let avg_monthly_payees: f64 = rows
            .iter()
            .map(|r| r.unique_incoming_payees as f64)
            .sum::<f64>()
            / rows.len() as f64;

        // Average top-5 concentration (lower = more distributed = better)
        let avg_top5_conc: f64 =
            rows.iter().map(|r| r.top5_payee_concentration).sum::<f64>()
                / rows.len() as f64;

        // Component 1: Unique payee count
        // 50+ unique monthly payees = excellent breadth
        let count_score = (avg_monthly_payees / 50.0).min(1.0);

        // Component 2: Concentration (inverse — lower concentration = higher score)
        // top5_conc of 0.3 (30%) = excellent, 0.8 (80%) = highly concentrated
        let concentration_score = (1.0 - avg_top5_conc).clamp(0.0, 1.0);

        // Component 3: Growth trend in payee count
        let mid = rows.len() / 2;
        let recent_payees = if mid > 0 {
            rows[mid..]
                .iter()
                .map(|r| r.unique_incoming_payees as f64)
                .sum::<f64>()
                / (rows.len() - mid) as f64
        } else {
            avg_monthly_payees
        };
        let earlier_payees = if mid > 0 {
            rows[..mid]
                .iter()
                .map(|r| r.unique_incoming_payees as f64)
                .sum::<f64>()
                / mid as f64
        } else {
            avg_monthly_payees
        };
        let growth_score = if earlier_payees > 0.0 {
            ((recent_payees / earlier_payees - 1.0) * 2.0 + 0.5).clamp(0.0, 1.0)
        } else {
            0.5
        };

        // Weighted composite
        let breadth_score =
            count_score * 0.40 + concentration_score * 0.35 + growth_score * 0.25;

        let confidence = compute_signal_confidence(rows.len(), self.config.min_cohort_size);

        let interpretation = if breadth_score >= 0.7 {
            format!(
                "Broad customer base: ~{:.0} unique monthly payees, top-5 concentration {:.0}%. Resilient.",
                avg_monthly_payees, avg_top5_conc * 100.0
            )
        } else if breadth_score >= 0.4 {
            format!(
                "Moderate customer breadth: ~{:.0} unique monthly payees, {:.0}% top-5 concentration.",
                avg_monthly_payees, avg_top5_conc * 100.0
            )
        } else {
            format!(
                "Narrow customer base: ~{:.0} unique monthly payees, {:.0}% top-5 concentration. High dependency risk.",
                avg_monthly_payees, avg_top5_conc * 100.0
            )
        };

        Ok(Some(ExtractedSignal {
            category: SignalCategory::CustomerBreadth,
            name: "network_breadth".to_string(),
            value: breadth_score,
            confidence,
            interpretation,
            percentile_rank: None,
        }))
    }

    // -----------------------------------------------------------------------
    // Additional signal extractors (design doc categories)
    // -----------------------------------------------------------------------

    /// Extract income stability signal (rolling standard deviation of income).
    async fn extract_income_stability(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                day,
                sum(total_inflow) as daily_income
            FROM aggregated_daily_transactions
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            GROUP BY day
            ORDER BY day
            "#
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct IncomeRow {
            day: chrono::NaiveDate,
            daily_income: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<IncomeRow>()
            .await?;

        if rows.len() < 14 {
            return Ok(None);
        }

        let incomes: Vec<f64> = rows.iter().map(|r| r.daily_income).collect();
        let cv = coefficient_of_variation(&incomes);

        // Stability score: lower CV = more stable
        let stability_score = (1.0 - cv / 3.0).clamp(0.0, 1.0);
        let confidence = compute_signal_confidence(rows.len(), self.config.min_cohort_size);

        Ok(Some(ExtractedSignal {
            category: SignalCategory::IncomeStability,
            name: "income_stability".to_string(),
            value: stability_score,
            confidence,
            interpretation: format!(
                "Income stability (CV={:.2}): {}",
                cv,
                if stability_score >= 0.7 {
                    "Stable income stream"
                } else if stability_score >= 0.4 {
                    "Moderate income variability"
                } else {
                    "Highly variable income"
                }
            ),
            percentile_rank: None,
        }))
    }

    /// Extract cash flow timing signal (simplified version of build_cash_flow_profile).
    async fn extract_cashflow_signal(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                sum(morning_inflow) as morning,
                sum(evening_inflow) as evening,
                sum(total_inflow) as total
            FROM aggregated_daily_transactions
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            "#
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct FlowAgg {
            morning: f64,
            evening: f64,
            total: f64,
        }

        let agg = self
            .db
            .clickhouse
            .query(&query)
            .fetch_one::<FlowAgg>()
            .await;

        let agg = match agg {
            Ok(a) if a.total > 0.0 => a,
            _ => return Ok(None),
        };

        // Business-like pattern: morning activity indicates trade/retail
        let morning_ratio = agg.morning / agg.total;
        let evening_ratio = agg.evening / agg.total;

        // Score: balanced morning+evening = retail pattern (good signal)
        // Mostly evening = salary/remittance pattern (also valid)
        // Score based on having clear, consistent patterns
        let balance = 1.0 - (morning_ratio - 0.5).abs() * 2.0; // Closer to 50/50 = higher
        let cashflow_score = (morning_ratio * 0.4 + evening_ratio * 0.3 + balance * 0.3).min(1.0);

        Ok(Some(ExtractedSignal {
            category: SignalCategory::CashFlowPattern,
            name: "cashflow_pattern".to_string(),
            value: cashflow_score,
            confidence: 0.6, // Simplified extraction has lower confidence
            interpretation: format!(
                "Morning: {:.0}%, Evening: {:.0}% of inflows",
                morning_ratio * 100.0,
                evening_ratio * 100.0
            ),
            percentile_rank: None,
        }))
    }

    /// Extract Fuliza dependency signal (simplified version of build_fuliza_profile).
    async fn extract_fuliza_signal(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                sum(fuliza_days) as fuliza_days,
                sum(active_days) as active_days
            FROM aggregated_fuliza_usage
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            "#
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct FulizaAgg {
            fuliza_days: u64,
            active_days: u64,
        }

        let agg = self
            .db
            .clickhouse
            .query(&query)
            .fetch_one::<FulizaAgg>()
            .await;

        let agg = match agg {
            Ok(a) if a.active_days > 0 => a,
            _ => return Ok(None),
        };

        let dependency = agg.fuliza_days as f64 / agg.active_days as f64;

        // Invert: lower dependency = better credit signal
        let fuliza_score = (1.0 - dependency).clamp(0.0, 1.0);

        Ok(Some(ExtractedSignal {
            category: SignalCategory::FulizaDependency,
            name: "fuliza_dependency".to_string(),
            value: fuliza_score,
            confidence: 0.7,
            interpretation: format!(
                "Fuliza usage: {:.0}% of active days. {}",
                dependency * 100.0,
                if fuliza_score >= 0.7 {
                    "Low overdraft reliance"
                } else if fuliza_score >= 0.4 {
                    "Moderate overdraft usage"
                } else {
                    "High overdraft dependency"
                }
            ),
            percentile_rank: None,
        }))
    }

    /// Extract seasonal sensitivity signal.
    async fn extract_seasonal_sensitivity(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                toMonth(day) as month,
                avg(total_inflow) as avg_daily_inflow
            FROM aggregated_daily_transactions
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            GROUP BY month
            ORDER BY month
            "#
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct MonthRow {
            month: u8,
            avg_daily_inflow: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<MonthRow>()
            .await?;

        if rows.len() < 3 {
            return Ok(None);
        }

        let values: Vec<f64> = rows.iter().map(|r| r.avg_daily_inflow).collect();
        let cv = coefficient_of_variation(&values);

        // Lower seasonal variation = better (more stable year-round)
        let sensitivity_score = (1.0 - cv / 2.0).clamp(0.0, 1.0);
        let confidence = compute_signal_confidence(rows.len(), self.config.min_cohort_size);

        Ok(Some(ExtractedSignal {
            category: SignalCategory::SeasonalSensitivity,
            name: "seasonal_sensitivity".to_string(),
            value: sensitivity_score,
            confidence,
            interpretation: format!(
                "Seasonal variation CV={:.2}. {}",
                cv,
                if sensitivity_score >= 0.7 {
                    "Low seasonality — consistent year-round"
                } else {
                    "High seasonality — income varies significantly by season"
                }
            ),
            percentile_rank: None,
        }))
    }

    /// Extract growth trajectory signal.
    async fn extract_growth_trajectory(
        &self,
        cohort_id: &str,
        lookback_days: u32,
    ) -> Result<Option<ExtractedSignal>> {
        let query = format!(
            r#"
            SELECT
                toStartOfMonth(day) as month,
                sum(total_inflow) as monthly_inflow
            FROM aggregated_daily_transactions
            WHERE cohort_id = '{cohort_id}'
              AND day >= today() - INTERVAL {lookback_days} DAY
            GROUP BY month
            ORDER BY month
            "#
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct MonthInflow {
            month: chrono::NaiveDate,
            monthly_inflow: f64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<MonthInflow>()
            .await?;

        if rows.len() < 2 {
            return Ok(None);
        }

        // Simple linear trend: compare last month to first month
        let first = rows.first().unwrap().monthly_inflow;
        let last = rows.last().unwrap().monthly_inflow;

        let growth = if first > 0.0 {
            (last - first) / first
        } else {
            0.0
        };

        // Map growth to 0-1 score: -50% → 0.0, +50% → 1.0
        let growth_score = ((growth + 0.5) / 1.0).clamp(0.0, 1.0);
        let confidence = compute_signal_confidence(rows.len(), self.config.min_cohort_size);

        Ok(Some(ExtractedSignal {
            category: SignalCategory::GrowthTrajectory,
            name: "growth_trajectory".to_string(),
            value: growth_score,
            confidence,
            interpretation: format!(
                "Income trend: {:+.0}% over {} months. {}",
                growth * 100.0,
                rows.len(),
                if growth >= 0.1 {
                    "Strong growth trajectory"
                } else if growth >= 0.0 {
                    "Stable to slight growth"
                } else if growth >= -0.1 {
                    "Slight decline"
                } else {
                    "Declining trajectory — concerning"
                }
            ),
            percentile_rank: None,
        }))
    }

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    /// Resolve a cohort filter to a k-anonymous cohort identifier.
    ///
    /// In production this would query the FederatedAggregator's cohort
    /// registry. Here we construct the ID from filter dimensions.
    async fn resolve_cohort_id(&self, cohort: &CohortFilter) -> Result<String> {
        let region = cohort.region.as_deref().unwrap_or("all");
        let worker = match &cohort.worker_type {
            Some(wt) => format!("{:?}", wt).to_lowercase(),
            None => "all".to_string(),
        };
        let gender = match &cohort.gender {
            Some(Gender::Male) => "male",
            Some(Gender::Female) => "female",
            None => "all",
        };

        Ok(format!("{}_{}_{}", region, worker, gender))
    }

    /// Get the cohort size for k-anonymity validation.
    async fn get_cohort_size(&self, cohort_id: &str) -> Result<u32> {
        let query = format!(
            r#"
            SELECT cohort_size
            FROM cohort_registry
            WHERE cohort_id = '{cohort_id}'
            "#
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct CohortRow {
            cohort_size: u32,
        }

        let result = self
            .db
            .clickhouse
            .query(&query)
            .fetch_one::<CohortRow>()
            .await;

        match result {
            Ok(row) => Ok(row.cohort_size),
            Err(_) => {
                // Fallback: query aggregated data count
                let fallback_query = format!(
                    r#"
                    SELECT uniq(worker_id_hash) as cnt
                    FROM aggregated_daily_transactions
                    WHERE cohort_id = '{cohort_id}'
                    "#
                );

                #[derive(clickhouse::Row, Deserialize)]
                struct CntRow {
                    cnt: u64,
                }

                let cnt = self
                    .db
                    .clickhouse
                    .query(&fallback_query)
                    .fetch_one::<CntRow>()
                    .await;

                Ok(cnt.map(|r| r.cnt as u32).unwrap_or(0))
            }
        }
    }

    /// List all active cohorts in a region for batch extraction.
    async fn list_cohorts_in_region(&self, region: &str) -> Result<Vec<CohortFilter>> {
        let query = format!(
            r#"
            SELECT DISTINCT worker_type, gender
            FROM cohort_registry
            WHERE region = '{region}'
              AND is_active = true
              AND cohort_size >= {}
            "#,
            self.config.min_cohort_size
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct CohortEntry {
            worker_type: String,
            gender: String,
        }

        let entries = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<CohortEntry>()
            .await
            .unwrap_or_default();

        let mut cohorts = Vec::new();
        for entry in entries {
            let worker_type = match entry.worker_type.as_str() {
                "mama_mboga" => Some(WorkerType::MamaMboga),
                "boda_boda" => Some(WorkerType::BodaBoda),
                "miti_mba" => Some(WorkerType::MitiMba),
                "fundi" => Some(WorkerType::Fundi),
                "jua_kali" => Some(WorkerType::JuaKali),
                "house_help" => Some(WorkerType::HouseHelp),
                "farm_worker" => Some(WorkerType::FarmWorker),
                _ => None,
            };

            let gender = match entry.gender.as_str() {
                "male" => Some(Gender::Male),
                "female" => Some(Gender::Female),
                _ => None,
            };

            cohorts.push(CohortFilter {
                region: Some(region.to_string()),
                worker_type,
                income_bracket: None,
                gender,
                business_age_months_min: None,
            });
        }

        Ok(cohorts)
    }

    // -----------------------------------------------------------------------
    // Signal publishing (feeds into CreditScorer + CompositeIndexBuilder)
    // -----------------------------------------------------------------------

    /// Publish extracted signals to downstream tools via ClickHouse + OODA.
    ///
    /// Stores signals in the `mobile_money_signals` table for historical
    /// tracking and makes them available to CreditScorer and
    /// CompositeIndexBuilder through the shared data layer.
    pub async fn publish_signals(&self, signals: &MobileMoneySignals) -> Result<()> {
        for signal in &signals.signals {
            let insert = format!(
                r#"
                INSERT INTO mobile_money_signals
                (cohort_id, region, worker_type, signal_category, signal_name,
                 value, confidence, percentile_rank, cohort_size, lookback_days, extracted_at)
                VALUES
                ('{cohort_id}', '{region}', '{worker_type}', '{category}', '{name}',
                 {value}, {confidence}, {percentile_rank}, {cohort_size}, {lookback_days}, now())
                "#,
                cohort_id = signals.cohort_id,
                region = signals.region,
                worker_type = format!("{:?}", signals.worker_type).to_lowercase(),
                category = format!("{:?}", signal.category).to_lowercase(),
                name = signal.name,
                value = signal.value,
                confidence = signal.confidence,
                percentile_rank = signal.percentile_rank.unwrap_or(0.0),
                cohort_size = signals.cohort_size,
                lookback_days = signals.lookback_days,
            );

            self.db
                .clickhouse
                .query(&insert)
                .execute()
                .await
                .map_err(|e| anyhow!("Failed to publish signal '{}': {}", signal.name, e))?;
        }

        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Statistical helpers
// ---------------------------------------------------------------------------

/// Compute the coefficient of variation (std dev / mean) for a slice of values.
/// Returns 0.0 if the mean is zero or the slice is empty.
fn coefficient_of_variation(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }

    let n = values.len() as f64;
    let mean = values.iter().sum::<f64>() / n;

    if mean.abs() < f64::EPSILON {
        return 0.0;
    }

    let variance = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n;
    let std_dev = variance.sqrt();

    std_dev / mean
}

/// Compute signal confidence based on data point count and minimum cohort size.
///
/// Confidence scales from 0.0 (no data) to 1.0 (abundant, high-quality data).
fn compute_signal_confidence(data_points: usize, min_cohort_size: u32) -> f64 {
    let point_factor = (data_points as f64 / 90.0).min(1.0); // 90 days = full confidence
    let size_factor = if min_cohort_size > 0 {
        (data_points as f64 / min_cohort_size as f64).min(1.0)
    } else {
        1.0
    };

    point_factor * 0.7 + size_factor * 0.3
}

/// Classify a trend direction from two values (recent vs. earlier).
fn classify_trend(recent: f64, earlier: f64) -> TrendDirection {
    if earlier.abs() < f64::EPSILON {
        return TrendDirection::Stable;
    }

    let change_pct = (recent - earlier) / earlier;

    if change_pct > 0.10 {
        TrendDirection::StrongGrowth
    } else if change_pct > 0.03 {
        TrendDirection::ModerateGrowth
    } else if change_pct >= -0.03 {
        TrendDirection::Stable
    } else if change_pct >= -0.10 {
        TrendDirection::ModerateDecline
    } else {
        TrendDirection::StrongDecline
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_coefficient_of_variation_constant() {
        // All same values → CV = 0
        let values = vec![100.0, 100.0, 100.0, 100.0];
        let cv = coefficient_of_variation(&values);
        assert!((cv - 0.0).abs() < 0.001, "CV of constant values should be 0, got {}", cv);
    }

    #[test]
    fn test_coefficient_of_variation_variable() {
        // High variance → high CV
        let values = vec![10.0, 100.0, 10.0, 100.0];
        let cv = coefficient_of_variation(&values);
        assert!(cv > 0.5, "CV of variable values should be high, got {}", cv);
    }

    #[test]
    fn test_coefficient_of_variation_empty() {
        let values: Vec<f64> = vec![];
        let cv = coefficient_of_variation(&values);
        assert!((cv - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_coefficient_of_variation_zero_mean() {
        let values = vec![0.0, 0.0, 0.0];
        let cv = coefficient_of_variation(&values);
        assert!((cv - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_compute_signal_confidence_full() {
        // 90 data points, min cohort 50 → high confidence
        let conf = compute_signal_confidence(90, 50);
        assert!(conf > 0.9, "Full data should give high confidence, got {}", conf);
    }

    #[test]
    fn test_compute_signal_confidence_sparse() {
        // Only 10 data points → low confidence
        let conf = compute_signal_confidence(10, 50);
        assert!(conf < 0.5, "Sparse data should give low confidence, got {}", conf);
    }

    #[test]
    fn test_classify_trend_strong_growth() {
        assert_eq!(
            classify_trend(120.0, 100.0),
            TrendDirection::StrongGrowth
        );
    }

    #[test]
    fn test_classify_trend_moderate_growth() {
        assert_eq!(
            classify_trend(105.0, 100.0),
            TrendDirection::ModerateGrowth
        );
    }

    #[test]
    fn test_classify_trend_stable() {
        assert_eq!(
            classify_trend(101.0, 100.0),
            TrendDirection::Stable
        );
    }

    #[test]
    fn test_classify_trend_moderate_decline() {
        assert_eq!(
            classify_trend(92.0, 100.0),
            TrendDirection::ModerateDecline
        );
    }

    #[test]
    fn test_classify_trend_strong_decline() {
        assert_eq!(
            classify_trend(80.0, 100.0),
            TrendDirection::StrongDecline
        );
    }

    #[test]
    fn test_classify_trend_zero_baseline() {
        assert_eq!(classify_trend(50.0, 0.0), TrendDirection::Stable);
    }

    #[test]
    fn test_signal_extractor_default_config() {
        let config = SignalExtractorConfig::default();
        assert_eq!(config.min_cohort_size, 50);
        assert_eq!(config.default_lookback_days, 90);
        assert!(config.enabled_signals.contains(&SignalCategory::TransactionRegularity));
        assert!(config.enabled_signals.contains(&SignalCategory::SavingsBehavior));
        assert!(config.enabled_signals.contains(&SignalCategory::SupplierConsistency));
        assert!(config.enabled_signals.contains(&SignalCategory::CustomerBreadth));
    }
}
