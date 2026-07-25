//! InequalityTracker — Economic inequality metrics across regions, worker types, gender
//!
//! Measures and tracks economic inequality across multiple dimensions within the
//! informal economy — making invisible disparities visible.
//!
//! ## Metrics
//!
//! - **Gini coefficient** — 0 (perfect equality) to 1 (perfect inequality)
//! - **Theil index** — GE(1), decomposable into within-group and between-group components
//! - **Atkinson index** — With configurable inequality aversion parameter ε
//! - **P90/P10 ratio**, **coefficient of variation**, percentile spreads
//!
//! ## Dimensions
//!
//! Regional, gender, worker type, business age, income tier, digital access,
//! and **intersectional** (compounding disadvantage across multiple axes).
//!
//! ## OODA Integration
//!
//! - **Observe:**  Consumes aggregated worker data from FederatedAggregator,
//!   CreditScorer, MobileMoneySignalExtractor, HealthMetrics, CompositeIndexBuilder.
//! - **Orient:**  Computes Gini, Theil, Atkinson across all dimensions. Decomposes
//!   inequality. Runs intersectional analysis to find compounding disadvantage.
//! - **Decide:**  Detects significant inequality changes, triggers ScenarioModeler
//!   for counterfactual analysis, flags new disparities for PolicyImpactAnalyzer.
//! - **Act:**     Publishes dashboards to API/ReportEngine, sends alerts via
//!   AlertGenerator, feeds inequality metrics back into CompositeIndexBuilder.

use anyhow::{anyhow, Context, Result};
use chrono::{DateTime, NaiveDate, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tracing::{debug, info, warn};
use uuid::Uuid;

use crate::db::DatabaseConnections;

// ─────────────────────────────────────────────────────────────────────
// Worker Type & Domain Enums (consistent with sibling tools)
// ─────────────────────────────────────────────────────────────────────

/// Worker archetypes in the informal economy.
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

/// Gender classification.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum Gender {
    Male,
    Female,
    Other,
}

impl std::fmt::Display for Gender {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Male => write!(f, "male"),
            Self::Female => write!(f, "female"),
            Self::Other => write!(f, "other"),
        }
    }
}

/// Income bracket classification.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum IncomeBracket {
    Bottom20,
    LowerMiddle,
    Middle,
    UpperMiddle,
    Top20,
}

impl std::fmt::Display for IncomeBracket {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Bottom20 => write!(f, "bottom_20"),
            Self::LowerMiddle => write!(f, "lower_middle"),
            Self::Middle => write!(f, "middle"),
            Self::UpperMiddle => write!(f, "upper_middle"),
            Self::Top20 => write!(f, "top_20"),
        }
    }
}

/// Trend direction for inequality time series.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum TrendDirection {
    /// Inequality is increasing (Gini rising, gaps widening).
    Widening,
    /// Inequality is decreasing (Gini falling, gaps narrowing).
    Narrowing,
    /// No significant change.
    Stable,
}

impl std::fmt::Display for TrendDirection {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Widening => write!(f, "widening"),
            Self::Narrowing => write!(f, "narrowing"),
            Self::Stable => write!(f, "stable"),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────

/// Configuration for the InequalityTracker.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalityConfig {
    /// Minimum cohort size for any comparison cell (k-anonymity guard).
    pub min_cell_size: u32,
    /// Metrics to track for inequality (default: all).
    pub tracked_metrics: Vec<InequalityMetric>,
    /// Recompute cadence.
    pub cadence: InequalityCadence,
    /// Alert threshold: Gini coefficient change that triggers alert.
    pub gini_change_alert_threshold: f64,
    /// Default Atkinson inequality aversion parameter (epsilon).
    pub default_atkinson_epsilon: f64,
}

impl Default for InequalityConfig {
    fn default() -> Self {
        Self {
            min_cell_size: 10,
            tracked_metrics: vec![
                InequalityMetric::DailyProfit,
                InequalityMetric::MonthlyIncome,
                InequalityMetric::SavingsRate,
                InequalityMetric::CreditAccess,
                InequalityMetric::CreditCost,
            ],
            cadence: InequalityCadence::Monthly,
            gini_change_alert_threshold: 0.02,
            default_atkinson_epsilon: 0.5,
        }
    }
}

/// Metrics tracked for inequality analysis.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum InequalityMetric {
    DailyProfit,
    MonthlyIncome,
    SavingsRate,
    CreditAccess,
    CreditCost,
    SpoilageRate,
    BusinessSurvivalRate,
    DigitalAccess,
    InsuranceCoverage,
    AlamaScore,
    Custom(String),
}

impl std::fmt::Display for InequalityMetric {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::DailyProfit => write!(f, "daily_profit"),
            Self::MonthlyIncome => write!(f, "monthly_income"),
            Self::SavingsRate => write!(f, "savings_rate"),
            Self::CreditAccess => write!(f, "credit_access"),
            Self::CreditCost => write!(f, "credit_cost"),
            Self::SpoilageRate => write!(f, "spoilage_rate"),
            Self::BusinessSurvivalRate => write!(f, "business_survival_rate"),
            Self::DigitalAccess => write!(f, "digital_access"),
            Self::InsuranceCoverage => write!(f, "insurance_coverage"),
            Self::AlamaScore => write!(f, "alama_score"),
            Self::Custom(s) => write!(f, "{}", s),
        }
    }
}

/// Recompute cadence for inequality snapshots.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum InequalityCadence {
    Weekly,
    Monthly,
    Quarterly,
}

impl std::fmt::Display for InequalityCadence {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Weekly => write!(f, "weekly"),
            Self::Monthly => write!(f, "monthly"),
            Self::Quarterly => write!(f, "quarterly"),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// InequalityDimension — What we slice the data by
// ─────────────────────────────────────────────────────────────────────

/// Dimension along which inequality is measured.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum InequalityDimension {
    Region,
    Gender,
    WorkerType,
    BusinessAge {
        brackets: Vec<(u32, u32)>,
    },
    IncomeTier {
        percentiles: Vec<u8>,
    },
    DigitalAccess,
    /// Compound dimension: e.g., Gender × Region × WorkerType.
    Intersectional {
        dimensions: Vec<InequalityDimension>,
    },
}

impl std::fmt::Display for InequalityDimension {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Region => write!(f, "region"),
            Self::Gender => write!(f, "gender"),
            Self::WorkerType => write!(f, "worker_type"),
            Self::BusinessAge { .. } => write!(f, "business_age"),
            Self::IncomeTier { .. } => write!(f, "income_tier"),
            Self::DigitalAccess => write!(f, "digital_access"),
            Self::Intersectional { dimensions } => {
                let parts: Vec<String> = dimensions.iter().map(|d| d.to_string()).collect();
                write!(f, "intersectional({})", parts.join("_x_"))
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Output Data Structures
// ─────────────────────────────────────────────────────────────────────

/// Full inequality snapshot for a dimension × metric combination.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalitySnapshot {
    pub id: Uuid,
    pub snapshot_date: NaiveDate,
    pub dimension: InequalityDimension,
    pub metric: InequalityMetric,
    pub global_stats: GlobalInequalityStats,
    pub cell_stats: Vec<CellStats>,
    pub comparisons: Vec<InequalityComparison>,
    pub trends: Vec<InequalityTrend>,
    pub computed_at: DateTime<Utc>,
}

/// Global inequality statistics across all cells in a dimension.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobalInequalityStats {
    /// Gini coefficient: 0 (perfect equality) to 1 (perfect inequality).
    pub gini_coefficient: f64,
    /// Theil index (GE(1)): decomposable into within/between group.
    pub theil_index: f64,
    /// Top decile / bottom decile income ratio.
    pub p90_p10_ratio: f64,
    /// Top decile / median ratio.
    pub p90_p50_ratio: f64,
    /// Coefficient of variation (std_dev / mean).
    pub coefficient_of_variation: f64,
    /// Atkinson index with ε = 0.5 (moderate inequality aversion).
    pub atkinson_index: f64,
}

/// Per-cell statistics within a dimension.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CellStats {
    pub cell_id: String,
    pub cell_label: String,
    pub mean: f64,
    pub median: f64,
    pub p10: f64,
    pub p25: f64,
    pub p75: f64,
    pub p90: f64,
    pub std_dev: f64,
    pub sample_size: u32,
    /// This cell's share of the aggregate metric across all cells.
    pub share_of_total: f64,
}

/// Pairwise inequality comparison between two cells.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalityComparison {
    pub cell_a: String,
    pub cell_b: String,
    /// mean_a / mean_b.
    pub ratio: f64,
    /// mean_a - mean_b.
    pub absolute_gap: f64,
    /// p-value from Welch's t-test.
    pub statistical_significance: f64,
    pub is_significant: bool,
    /// Cohen's d effect size.
    pub effect_size: f64,
    /// Human-readable narrative.
    pub narrative: String,
}

/// Trend in inequality over time.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalityTrend {
    pub dimension: String,
    pub metric: String,
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub gini_start: f64,
    pub gini_end: f64,
    pub gini_change: f64,
    pub direction: TrendDirection,
    /// Which comparison worsened most.
    pub fastest_widening_gap: Option<String>,
    /// Which comparison improved most.
    pub fastest_narrowing_gap: Option<String>,
}

/// Theil index decomposition result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TheilDecomposition {
    pub total_theil: f64,
    /// Inequality within each group.
    pub within_group: Vec<GroupTheil>,
    /// Inequality between group means.
    pub between_group_theil: f64,
    /// within_group_total / total_theil — how much inequality is intra-group.
    pub within_share: f64,
    /// between_group_theil / total_theil — how much is inter-group.
    pub between_share: f64,
    pub computed_at: DateTime<Utc>,
}

/// Per-group Theil contribution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GroupTheil {
    pub group_id: String,
    pub group_label: String,
    pub theil: f64,
    pub population_share: f64,
    pub income_share: f64,
    pub contribution_to_total: f64,
}

/// Intersectional analysis result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntersectionalAnalysis {
    pub id: Uuid,
    pub dimensions: Vec<String>,
    pub metric: InequalityMetric,
    pub intersectional_cells: Vec<IntersectionalCell>,
    /// How much worse the worst intersectional cell is vs. additive prediction.
    pub additive_vs_intersectional_gap: f64,
    pub most_disadvantaged: Vec<IntersectionalCell>,
    pub most_advantaged: Vec<IntersectionalCell>,
    pub computed_at: DateTime<Utc>,
}

/// A single intersectional cell (e.g., rural + female + mama_mboga).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntersectionalCell {
    pub combination: HashMap<String, String>,
    pub mean: f64,
    pub median: f64,
    pub sample_size: u32,
    /// Percentile rank among all intersectional cells (0–100).
    pub percentile_rank: f64,
    /// Composite disadvantage score (higher = more disadvantaged).
    pub disadvantage_score: f64,
}

/// Alert raised when inequality crosses a threshold.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InequalityAlert {
    pub id: Uuid,
    pub dimension: InequalityDimension,
    pub metric: InequalityMetric,
    pub alert_type: InequalityAlertType,
    pub severity: AlertSeverity,
    pub message: String,
    pub details: serde_json::Value,
    pub created_at: DateTime<Utc>,
}

/// Type of inequality alert.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum InequalityAlertType {
    /// Gini coefficient increased beyond threshold.
    GiniIncrease,
    /// A specific gap widened beyond threshold.
    GapWidening,
    /// A new disparity detected (previously non-significant).
    NewDisparity,
    /// Intersectional disadvantage compounded.
    IntersectionalCompound,
}

/// Alert severity.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AlertSeverity {
    Info,
    Warning,
    Critical,
}

/// Comparison of inequality between two time periods.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PeriodComparison {
    pub dimension: InequalityDimension,
    pub metric: InequalityMetric,
    pub period_a: PeriodStats,
    pub period_b: PeriodStats,
    pub gini_change: f64,
    pub theil_change: f64,
    pub significant_changes: Vec<InequalityComparison>,
    pub verdict: TrendDirection,
}

/// Statistics for one period in a comparison.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PeriodStats {
    pub period_start: NaiveDate,
    pub period_end: NaiveDate,
    pub gini: f64,
    pub theil: f64,
    pub atkinson: f64,
    pub cell_stats: Vec<CellStats>,
}

/// Date range helper.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DateRange {
    pub start: NaiveDate,
    pub end: NaiveDate,
}

// ─────────────────────────────────────────────────────────────────────
// InequalityTracker — The Tool
// ─────────────────────────────────────────────────────────────────────

/// Main inequality tracking tool.
///
/// Computes Gini, Theil, and Atkinson indices across multiple dimensions
/// (region, gender, worker type, and intersectional combinations) to reveal
/// economic disparities in the informal economy.
pub struct InequalityTracker {
    db: DatabaseConnections,
    config: InequalityConfig,
}

impl InequalityTracker {
    /// Create a new tracker with default configuration.
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            config: InequalityConfig::default(),
        }
    }

    /// Create with custom configuration.
    pub fn with_config(db: DatabaseConnections, config: InequalityConfig) -> Self {
        Self { db, config }
    }

    // ─────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────

    /// Compute a full inequality snapshot for a given dimension and metric.
    ///
    /// Fetches aggregated data from ClickHouse, computes all inequality indices,
    /// performs pairwise comparisons, and stores the snapshot in PostgreSQL.
    pub async fn compute_snapshot(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        as_of: NaiveDate,
    ) -> Result<InequalitySnapshot> {
        debug!(
            dimension = %dimension,
            metric = %metric,
            date = %as_of,
            "Computing inequality snapshot"
        );

        // Fetch aggregated values per cell from ClickHouse
        let cells = self.fetch_cell_data(dimension, metric, as_of).await?;

        if cells.is_empty() {
            return Err(anyhow!(
                "No data found for dimension={}, metric={}, date={}",
                dimension, metric, as_of
            ));
        }

        // Flatten all individual values for global stats
        let all_values: Vec<f64> = cells.iter().flat_map(|c| c.values.clone()).collect();

        if all_values.is_empty() {
            return Err(anyhow!("Empty value set after flattening cell data"));
        }

        let global_stats = Self::compute_global_stats(&all_values, self.config.default_atkinson_epsilon);
        let cell_stats = self.compute_cell_stats(&cells, &all_values);
        let comparisons = self.compute_pairwise_comparisons(&cell_stats);
        let trends = self
            .fetch_trends(dimension, metric, as_of)
            .await
            .unwrap_or_default();

        let snapshot = InequalitySnapshot {
            id: Uuid::new_v4(),
            snapshot_date: as_of,
            dimension: dimension.clone(),
            metric: metric.clone(),
            global_stats,
            cell_stats,
            comparisons,
            trends,
            computed_at: Utc::now(),
        };

        // Persist to PostgreSQL and ClickHouse
        self.store_snapshot(&snapshot).await?;

        // Cache in Redis
        self.cache_snapshot(&snapshot).await?;

        // Emit OODA signal if Gini crossed threshold
        self.check_and_emit_alerts(&snapshot).await?;

        info!(
            id = %snapshot.id,
            gini = %format!("{:.4}", snapshot.global_stats.gini_coefficient),
            theil = %format!("{:.4}", snapshot.global_stats.theil_index),
            "Inequality snapshot computed"
        );

        Ok(snapshot)
    }

    /// Compute intersectional analysis across multiple dimensions.
    ///
    /// For example: gender × region × worker_type to find that
    /// "rural female mama_mboga" has compounding disadvantage.
    pub async fn compute_intersectional(
        &self,
        dimensions: &[InequalityDimension],
        metric: &InequalityMetric,
    ) -> Result<IntersectionalAnalysis> {
        if dimensions.len() < 2 {
            return Err(anyhow!(
                "Intersectional analysis requires at least 2 dimensions, got {}",
                dimensions.len()
            ));
        }

        debug!(
            dimensions = ?dimensions.iter().map(|d| d.to_string()).collect::<Vec<_>>(),
            metric = %metric,
            "Computing intersectional analysis"
        );

        // Fetch cross-tabulated data from ClickHouse
        let intersectional_cells = self.fetch_intersectional_data(dimensions, metric).await?;

        if intersectional_cells.is_empty() {
            return Err(anyhow!("No intersectional data found"));
        }

        // Compute disadvantage scores and percentile ranks
        let mut cells = intersectional_cells;
        Self::assign_disadvantage_scores(&mut cells);
        Self::assign_percentile_ranks(&mut cells);

        // Sort by disadvantage score descending (most disadvantaged first)
        cells.sort_by(|a, b| {
            b.disadvantage_score
                .partial_cmp(&a.disadvantage_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        // Compute additive vs. intersectional gap
        let additive_gap = self.compute_additive_gap(dimensions, metric).await?;
        let worst_intersectional = cells.first().map(|c| c.disadvantage_score).unwrap_or(0.0);
        let gap = worst_intersectional - additive_gap;

        // Top/bottom 3 for most disadvantaged/advantaged
        let most_disadvantaged: Vec<IntersectionalCell> = cells.iter().take(3).cloned().collect();
        let most_advantaged: Vec<IntersectionalCell> = cells.iter().rev().take(3).cloned().collect();

        let dimension_names: Vec<String> = dimensions.iter().map(|d| d.to_string()).collect();

        let analysis = IntersectionalAnalysis {
            id: Uuid::new_v4(),
            dimensions: dimension_names,
            metric: metric.clone(),
            intersectional_cells: cells,
            additive_vs_intersectional_gap: gap,
            most_disadvantaged,
            most_advantaged,
            computed_at: Utc::now(),
        };

        // Store and emit signals
        self.store_intersectional(&analysis).await?;

        // If compounding disadvantage detected, emit OODA alert
        if gap > 0.15 {
            self.emit_intersectional_alert(&analysis).await?;
        }

        info!(
            id = %analysis.id,
            gap = %format!("{:.4}", analysis.additive_vs_intersectional_gap),
            "Intersectional analysis computed"
        );

        Ok(analysis)
    }

    /// Track inequality trends over time for a dimension × metric.
    pub async fn get_trends(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        from: NaiveDate,
        to: NaiveDate,
    ) -> Result<Vec<InequalityTrend>> {
        debug!(
            dimension = %dimension,
            metric = %metric,
            from = %from,
            to = %to,
            "Fetching inequality trends"
        );

        let dimension_str = dimension.to_string();
        let metric_str = metric.to_string();

        let query = format!(
            r#"
            SELECT
                snapshot_date,
                gini
            FROM inequality_timeseries
            WHERE dimension = '{dim}'
              AND metric = '{metric}'
              AND snapshot_date BETWEEN '{from}' AND '{to}'
            ORDER BY snapshot_date ASC
            "#,
            dim = dimension_str,
            metric = metric_str,
            from = from,
            to = to,
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<TrendRow>()
            .await
            .context("Failed to fetch inequality trends from ClickHouse")?;

        if rows.len() < 2 {
            return Ok(vec![]);
        }

        let first = &rows[0];
        let last = &rows[rows.len() - 1];
        let gini_change = last.gini - first.gini;

        let first_date = NaiveDate::parse_from_str(&first.snapshot_date, "%Y-%m-%d")
            .unwrap_or_else(|_| Utc::now().date_naive());
        let last_date = NaiveDate::parse_from_str(&last.snapshot_date, "%Y-%m-%d")
            .unwrap_or_else(|_| Utc::now().date_naive());

        let direction = if gini_change > self.config.gini_change_alert_threshold {
            TrendDirection::Widening
        } else if gini_change < -self.config.gini_change_alert_threshold {
            TrendDirection::Narrowing
        } else {
            TrendDirection::Stable
        };

        Ok(vec![InequalityTrend {
            dimension: dimension_str,
            metric: metric_str,
            period_start: first_date,
            period_end: last_date,
            gini_start: first.gini,
            gini_end: last.gini,
            gini_change,
            direction,
            fastest_widening_gap: None,
            fastest_narrowing_gap: None,
        }])
    }

    /// Decompose Theil index to show within-group vs. between-group inequality.
    ///
    /// The Theil index is uniquely decomposable: T = T_within + T_between.
    /// This reveals whether inequality is driven by differences *within* groups
    /// (e.g., among mama mbogas in Nairobi) or *between* groups
    /// (e.g., Nairobi vs. rural counties).
    pub async fn decompose_inequality(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
    ) -> Result<TheilDecomposition> {
        debug!(
            dimension = %dimension,
            metric = %metric,
            "Decomposing Theil index"
        );

        // Fetch per-cell value vectors
        let cells = self
            .fetch_cell_data(dimension, metric, Utc::now().date_naive())
            .await?;

        if cells.is_empty() {
            return Err(anyhow!("No data for Theil decomposition"));
        }

        let all_values: Vec<f64> = cells.iter().flat_map(|c| c.values.clone()).collect();
        let groups: Vec<Vec<f64>> = cells.iter().map(|c| c.values.clone()).collect();

        let decomposition = Self::theil_decompose(&all_values, &groups, &cells);

        info!(
            total = %format!("{:.4}", decomposition.total_theil),
            within_share = %format!("{:.2}%", decomposition.within_share * 100.0),
            between_share = %format!("{:.2}%", decomposition.between_share * 100.0),
            "Theil decomposition complete"
        );

        Ok(decomposition)
    }

    /// Compare inequality across two time periods (before/after policy, etc.).
    pub async fn compare_periods(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        period_a: &DateRange,
        period_b: &DateRange,
    ) -> Result<PeriodComparison> {
        debug!(
            dimension = %dimension,
            metric = %metric,
            "Comparing inequality across periods"
        );

        let cells_a = self
            .fetch_cell_data_range(dimension, metric, period_a)
            .await?;
        let cells_b = self
            .fetch_cell_data_range(dimension, metric, period_b)
            .await?;

        let values_a: Vec<f64> = cells_a.iter().flat_map(|c| c.values.clone()).collect();
        let values_b: Vec<f64> = cells_b.iter().flat_map(|c| c.values.clone()).collect();

        let stats_a = Self::compute_global_stats(&values_a, self.config.default_atkinson_epsilon);
        let stats_b = Self::compute_global_stats(&values_b, self.config.default_atkinson_epsilon);

        let cell_stats_a = self.compute_cell_stats(&cells_a, &values_a);
        let cell_stats_b = self.compute_cell_stats(&cells_b, &values_b);

        let gini_change = stats_b.gini_coefficient - stats_a.gini_coefficient;
        let theil_change = stats_b.theil_index - stats_a.theil_index;

        let verdict = if gini_change > self.config.gini_change_alert_threshold {
            TrendDirection::Widening
        } else if gini_change < -self.config.gini_change_alert_threshold {
            TrendDirection::Narrowing
        } else {
            TrendDirection::Stable
        };

        Ok(PeriodComparison {
            dimension: dimension.clone(),
            metric: metric.clone(),
            period_a: PeriodStats {
                period_start: period_a.start,
                period_end: period_a.end,
                gini: stats_a.gini_coefficient,
                theil: stats_a.theil_index,
                atkinson: stats_a.atkinson_index,
                cell_stats: cell_stats_a,
            },
            period_b: PeriodStats {
                period_start: period_b.start,
                period_end: period_b.end,
                gini: stats_b.gini_coefficient,
                theil: stats_b.theil_index,
                atkinson: stats_b.atkinson_index,
                cell_stats: cell_stats_b,
            },
            gini_change,
            theil_change,
            significant_changes: vec![],
            verdict,
        })
    }

    /// Check for inequality alerts and emit OODA signals.
    pub async fn check_inequality_alerts(&self) -> Result<Vec<InequalityAlert>> {
        let mut alerts = Vec::new();

        for metric in &self.config.tracked_metrics {
            for dimension in &[
                InequalityDimension::Region,
                InequalityDimension::Gender,
                InequalityDimension::WorkerType,
            ] {
                match self
                    .get_trends(dimension, metric, Utc::now().date_naive() - chrono::Duration::days(90), Utc::now().date_naive())
                    .await
                {
                    Ok(trends) => {
                        for trend in &trends {
                            if trend.direction == TrendDirection::Widening
                                && trend.gini_change.abs() > self.config.gini_change_alert_threshold
                            {
                                alerts.push(InequalityAlert {
                                    id: Uuid::new_v4(),
                                    dimension: dimension.clone(),
                                    metric: metric.clone(),
                                    alert_type: InequalityAlertType::GiniIncrease,
                                    severity: if trend.gini_change > 0.05 {
                                        AlertSeverity::Critical
                                    } else {
                                        AlertSeverity::Warning
                                    },
                                    message: format!(
                                        "Gini coefficient for {} inequality in {} increased by {:.3} over the past quarter (from {:.3} to {:.3})",
                                        metric, dimension, trend.gini_change, trend.gini_start, trend.gini_end
                                    ),
                                    details: serde_json::json!({
                                        "gini_start": trend.gini_start,
                                        "gini_end": trend.gini_end,
                                        "gini_change": trend.gini_change,
                                    }),
                                    created_at: Utc::now(),
                                });
                            }
                        }
                    }
                    Err(e) => {
                        warn!(
                            metric = %metric,
                            dimension = %dimension,
                            error = %e,
                            "Failed to check trends for alerts"
                        );
                    }
                }
            }
        }

        // Store alerts in PostgreSQL
        for alert in &alerts {
            self.store_alert(alert).await?;
        }

        Ok(alerts)
    }

    /// Full recomputation of all tracked metrics × dimensions (scheduled job).
    pub async fn full_recompute(&self) -> Result<Vec<InequalitySnapshot>> {
        info!("Starting full inequality recompute");

        let as_of = Utc::now().date_naive();
        let mut snapshots = Vec::new();

        let dimensions = vec![
            InequalityDimension::Region,
            InequalityDimension::Gender,
            InequalityDimension::WorkerType,
            InequalityDimension::DigitalAccess,
        ];

        for metric in &self.config.tracked_metrics {
            for dimension in &dimensions {
                match self.compute_snapshot(dimension, metric, as_of).await {
                    Ok(snapshot) => snapshots.push(snapshot),
                    Err(e) => {
                        warn!(
                            dimension = %dimension,
                            metric = %metric,
                            error = %e,
                            "Failed to compute snapshot during full recompute"
                        );
                    }
                }
            }
        }

        // Also run intersectional: gender × region × worker_type
        for metric in &self.config.tracked_metrics {
            let intersectional_dims = vec![
                InequalityDimension::Gender,
                InequalityDimension::Region,
                InequalityDimension::WorkerType,
            ];
            match self.compute_intersectional(&intersectional_dims, metric).await {
                Ok(_) => debug!("Intersectional analysis complete for {}", metric),
                Err(e) => warn!("Intersectional analysis failed for {}: {}", metric, e),
            }
        }

        info!(
            count = snapshots.len(),
            "Full inequality recompute complete"
        );

        Ok(snapshots)
    }

    // ─────────────────────────────────────────────────────────────────
    // Pure Math — Gini, Theil, Atkinson
    // ─────────────────────────────────────────────────────────────────

    /// Compute the Gini coefficient from a set of income values.
    ///
    /// Formula: G = (2 * Σ(i * y_i)) / (n * Σ(y_i)) - (n+1)/n
    /// where y_i are sorted values and i is the 1-based rank.
    ///
    /// Returns 0.0 for perfect equality, 1.0 for perfect inequality.
    /// Returns 0.0 for empty or single-value inputs.
    pub fn calculate_gini(values: &[f64]) -> f64 {
        let n = values.len();
        if n < 2 {
            return 0.0;
        }

        let mut sorted = values.to_vec();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let sum: f64 = sorted.iter().sum();
        if sum <= 0.0 {
            return 0.0;
        }

        let n_f = n as f64;
        let mut weighted_sum = 0.0;
        for (i, val) in sorted.iter().enumerate() {
            weighted_sum += (i as f64 + 1.0) * val;
        }

        (2.0 * weighted_sum) / (n_f * sum) - (n_f + 1.0) / n_f
    }

    /// Compute the Theil index (GE(1)) from a set of income values.
    ///
    /// Formula: T = (1/n) * Σ((y_i / μ) * ln(y_i / μ))
    /// where μ is the mean income.
    ///
    /// Theil is decomposable into within-group and between-group components.
    /// Returns 0.0 for perfect equality.
    pub fn calculate_theil(values: &[f64]) -> f64 {
        let n = values.len();
        if n == 0 {
            return 0.0;
        }

        let mean: f64 = values.iter().sum::<f64>() / n as f64;
        if mean <= 0.0 {
            return 0.0;
        }

        let mut theil = 0.0;
        for val in values {
            if *val > 0.0 {
                let ratio = val / mean;
                theil += ratio * ratio.ln();
            }
            // Values <= 0 contribute 0 to Theil (by convention for income data)
        }

        theil / n as f64
    }

    /// Compute the Atkinson index with inequality aversion parameter ε (epsilon).
    ///
    /// Formula: A = 1 - (1/μ) * [(1/n) * Σ(y_i^(1-ε))]^(1/(1-ε))
    ///
    /// - ε = 0: No aversion to inequality (A → 0)
    /// - ε = 0.5: Moderate aversion (default)
    /// - ε → 1: Strong aversion (focuses on bottom of distribution)
    /// - ε → ∞: Maximum aversion (Rawlsian, only cares about worst-off)
    ///
    /// Returns 0.0 for perfect equality, approaches 1.0 for extreme inequality.
    pub fn calculate_atkinson(values: &[f64], epsilon: f64) -> f64 {
        let n = values.len();
        if n == 0 {
            return 0.0;
        }

        let mean: f64 = values.iter().sum::<f64>() / n as f64;
        if mean <= 0.0 {
            return 0.0;
        }

        // Special case: ε = 1 (limit as ε → 1)
        if (epsilon - 1.0).abs() < f64::EPSILON {
            // A = 1 - (geometric_mean / arithmetic_mean)
            let log_sum: f64 = values.iter().filter(|v| **v > 0.0).map(|v| v.ln()).sum();
            let n_positive = values.iter().filter(|v| **v > 0.0).count() as f64;
            if n_positive == 0.0 {
                return 0.0;
            }
            let geometric_mean = (log_sum / n_positive).exp();
            return 1.0 - geometric_mean / mean;
        }

        // Special case: ε = 0
        if epsilon.abs() < f64::EPSILON {
            return 0.0;
        }

        let one_minus_eps = 1.0 - epsilon;

        // Compute generalized mean: [(1/n) * Σ(y_i^(1-ε))]^(1/(1-ε))
        let power_sum: f64 = values
            .iter()
            .filter(|v| **v >= 0.0)
            .map(|v| v.powf(one_minus_eps))
            .sum();

        let generalized_mean = (power_sum / n as f64).powf(1.0 / one_minus_eps);

        1.0 - generalized_mean / mean
    }

    /// Decompose the Theil index into within-group and between-group components.
    ///
    /// T_total = T_within + T_between
    ///
    /// - T_within: inequality *within* each group (e.g., among mama mbogas)
    /// - T_between: inequality *between* group means (e.g., mama mboga vs boda boda)
    ///
    /// This is the key advantage of Theil over Gini — Gini cannot be decomposed.
    pub fn theil_decompose(
        all_values: &[f64],
        groups: &[Vec<f64>],
        group_meta: &[CellData],
    ) -> TheilDecomposition {
        let total_theil = Self::calculate_theil(all_values);
        let total_income: f64 = all_values.iter().sum();
        let total_n = all_values.len() as f64;

        if total_income <= 0.0 || total_n == 0.0 {
            return TheilDecomposition {
                total_theil: 0.0,
                within_group: vec![],
                between_group_theil: 0.0,
                within_share: 0.0,
                between_share: 0.0,
                computed_at: Utc::now(),
            };
        }

        let overall_mean = total_income / total_n;

        let mut within_groups = Vec::new();
        let mut total_within_weighted = 0.0;

        for (i, group) in groups.iter().enumerate() {
            if group.is_empty() {
                continue;
            }

            let group_n = group.len() as f64;
            let group_income: f64 = group.iter().sum();
            let group_mean = group_income / group_n;
            let group_theil = Self::calculate_theil(group);

            let population_share = group_n / total_n;
            let income_share = group_income / total_income;

            // Contribution: s_j * T_j where s_j is income share
            let contribution = income_share * group_theil;
            total_within_weighted += contribution;

            let meta = group_meta.get(i);
            within_groups.push(GroupTheil {
                group_id: meta.map(|m| m.cell_id.clone()).unwrap_or_else(|| format!("group_{}", i)),
                group_label: meta.map(|m| m.cell_label.clone()).unwrap_or_else(|| format!("Group {}", i)),
                theil: group_theil,
                population_share,
                income_share,
                contribution_to_total: if total_theil > 0.0 {
                    contribution / total_theil
                } else {
                    0.0
                },
            });
        }

        // Between-group Theil: T_between = Σ(s_j * (μ_j/μ) * ln(μ_j/μ))
        let mut between_theil = 0.0;
        for group in groups {
            if group.is_empty() {
                continue;
            }
            let group_n = group.len() as f64;
            let group_income: f64 = group.iter().sum();
            let group_mean = group_income / group_n;
            let income_share = group_income / total_income;

            if group_mean > 0.0 && overall_mean > 0.0 {
                let ratio = group_mean / overall_mean;
                between_theil += income_share * ratio * ratio.ln();
            }
        }

        let within_share = if total_theil > 0.0 {
            total_within_weighted / total_theil
        } else {
            0.0
        };
        let between_share = if total_theil > 0.0 {
            between_theil / total_theil
        } else {
            0.0
        };

        TheilDecomposition {
            total_theil,
            within_group: within_groups,
            between_group_theil: between_theil,
            within_share,
            between_share,
            computed_at: Utc::now(),
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Internal Helpers — Data Fetching
    // ─────────────────────────────────────────────────────────────────

    /// Fetch per-cell aggregated data from ClickHouse.
    /// Uses per-worker rows grouped in Rust to avoid ClickHouse array type issues.
    async fn fetch_cell_data(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        as_of: NaiveDate,
    ) -> Result<Vec<CellData>> {
        let metric_str = metric.to_string();

        // Query aggregated worker-level data grouped by the dimension
        let cell_column = match dimension {
            InequalityDimension::Region => "region",
            InequalityDimension::Gender => "gender",
            InequalityDimension::WorkerType => "worker_type",
            InequalityDimension::DigitalAccess => "digital_access",
            InequalityDimension::BusinessAge { .. } => "business_age_bracket",
            InequalityDimension::IncomeTier { .. } => "income_tier",
            InequalityDimension::Intersectional { .. } => {
                return self.fetch_intersectional_cell_data(dimension, metric, as_of).await;
            }
        };

        let query = format!(
            r#"
            SELECT
                {cc} AS cell_id,
                {cc} AS cell_label,
                value
            FROM inequality_worker_data
            WHERE metric_name = '{metric}'
              AND snapshot_date = '{date}'
            ORDER BY cell_id
            "#,
            cc = cell_column,
            metric = metric_str,
            date = as_of,
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<ValueRow>()
            .await
            .context("Failed to fetch cell data from ClickHouse")?;

        // Group by cell_id in Rust
        let mut grouped: HashMap<String, CellData> = HashMap::new();
        for row in rows {
            let entry = grouped.entry(row.cell_id.clone()).or_insert_with(|| CellData {
                cell_id: row.cell_id,
                cell_label: row.cell_label,
                values: Vec::new(),
            });
            entry.values.push(row.value);
        }

        // Filter by minimum cell size
        Ok(grouped
            .into_values()
            .filter(|c| c.values.len() as u32 >= self.config.min_cell_size)
            .collect())
    }

    /// Fetch cell data for a date range (for period comparisons).
    async fn fetch_cell_data_range(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        range: &DateRange,
    ) -> Result<Vec<CellData>> {
        let metric_str = metric.to_string();

        let cell_column = match dimension {
            InequalityDimension::Region => "region",
            InequalityDimension::Gender => "gender",
            InequalityDimension::WorkerType => "worker_type",
            InequalityDimension::DigitalAccess => "digital_access",
            InequalityDimension::BusinessAge { .. } => "business_age_bracket",
            InequalityDimension::IncomeTier { .. } => "income_tier",
            InequalityDimension::Intersectional { .. } => "intersectional_key",
        };

        let query = format!(
            r#"
            SELECT
                {cc} AS cell_id,
                {cc} AS cell_label,
                value
            FROM inequality_worker_data
            WHERE metric_name = '{metric}'
              AND snapshot_date BETWEEN '{start}' AND '{end}'
            ORDER BY cell_id
            "#,
            cc = cell_column,
            metric = metric_str,
            start = range.start,
            end = range.end,
        );

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<ValueRow>()
            .await
            .context("Failed to fetch cell data range from ClickHouse")?;

        // Group by cell_id in Rust
        let mut grouped: HashMap<String, CellData> = HashMap::new();
        for row in rows {
            let entry = grouped.entry(row.cell_id.clone()).or_insert_with(|| CellData {
                cell_id: row.cell_id,
                cell_label: row.cell_label,
                values: Vec::new(),
            });
            entry.values.push(row.value);
        }

        Ok(grouped
            .into_values()
            .filter(|c| c.values.len() as u32 >= self.config.min_cell_size)
            .collect())
    }

    /// Fetch intersectional cell data (cross-tabulated across multiple dimensions).
    async fn fetch_intersectional_data(
        &self,
        dimensions: &[InequalityDimension],
        metric: &InequalityMetric,
    ) -> Result<Vec<IntersectionalCell>> {
        let metric_str = metric.to_string();
        let dim_columns: Vec<String> = dimensions
            .iter()
            .map(|d| match d {
                InequalityDimension::Region => "region".to_string(),
                InequalityDimension::Gender => "gender".to_string(),
                InequalityDimension::WorkerType => "worker_type".to_string(),
                InequalityDimension::DigitalAccess => "digital_access".to_string(),
                InequalityDimension::BusinessAge { .. } => "business_age_bracket".to_string(),
                InequalityDimension::IncomeTier { .. } => "income_tier".to_string(),
                InequalityDimension::Intersectional { .. } => "intersectional_key".to_string(),
            })
            .collect();

        // Build a composite key from all dimensions
        let composite_key = dim_columns.join(" || '_' || ");
        let group_by = dim_columns.join(", ");

        let query = format!(
            r#"
            SELECT
                {composite_key} AS combo_key,
                avg(value) AS mean_val,
                median(value) AS median_val,
                count() AS sample_size
            FROM inequality_worker_data
            WHERE metric_name = '{metric}'
            GROUP BY {group_by}
            HAVING sample_size >= {min}
            ORDER BY mean_val ASC
            "#,
            composite_key = composite_key,
            group_by = group_by,
            metric = metric_str,
            min = self.config.min_cell_size,
        );

        #[derive(Debug, clickhouse::Row, Deserialize)]
        struct IntersectionalRow {
            combo_key: String,
            mean_val: f64,
            median_val: f64,
            sample_size: u64,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<IntersectionalRow>()
            .await
            .context("Failed to fetch intersectional data from ClickHouse")?;

        Ok(rows
            .into_iter()
            .map(|r| {
                let combination: HashMap<String, String> = r
                    .combo_key
                    .split('_')
                    .zip(dim_columns.iter())
                    .map(|(val, dim)| (dim.clone(), val.to_string()))
                    .collect();

                IntersectionalCell {
                    combination,
                    mean: r.mean_val,
                    median: r.median_val,
                    sample_size: r.sample_size as u32,
                    percentile_rank: 0.0,   // computed later
                    disadvantage_score: 0.0, // computed later
                }
            })
            .collect())
    }

    /// Helper: fetch intersectional cell data for the dimension-based fetch path.
    async fn fetch_intersectional_cell_data(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        as_of: NaiveDate,
    ) -> Result<Vec<CellData>> {
        if let InequalityDimension::Intersectional { dimensions } = dimension {
            let cells = self.fetch_intersectional_data(dimensions, metric).await?;
            Ok(cells
                .into_iter()
                .map(|c| CellData {
                    cell_id: c
                        .combination
                        .values()
                        .cloned()
                        .collect::<Vec<_>>()
                        .join("_"),
                    cell_label: c
                        .combination
                        .iter()
                        .map(|(k, v)| format!("{}={}", k, v))
                        .collect::<Vec<_>>()
                        .join(", "),
                    values: vec![c.mean], // Approximation: use mean for Gini/Theil on groups
                })
                .collect())
        } else {
            unreachable!()
        }
    }

    /// Fetch historical trend data from ClickHouse.
    async fn fetch_trends(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        as_of: NaiveDate,
    ) -> Result<Vec<InequalityTrend>> {
        let from = as_of - chrono::Duration::days(90);
        self.get_trends(dimension, metric, from, as_of).await
    }

    /// Fetch previous Gini coefficient for comparison.
    async fn fetch_previous_gini(
        &self,
        dimension: &InequalityDimension,
        metric: &InequalityMetric,
        current_date: NaiveDate,
    ) -> Option<f64> {
        let dimension_str = dimension.to_string();
        let metric_str = metric.to_string();

        let query = format!(
            r#"
            SELECT gini
            FROM inequality_timeseries
            WHERE dimension = '{dim}'
              AND metric = '{metric}'
              AND snapshot_date < '{date}'
            ORDER BY snapshot_date DESC
            LIMIT 1
            "#,
            dim = dimension_str,
            metric = metric_str,
            date = current_date,
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct GiniRow {
            gini: f64,
        }

        self.db
            .clickhouse
            .query(&query)
            .fetch_one::<GiniRow>()
            .await
            .ok()
            .map(|r| r.gini)
    }

    /// Compute the additive (non-interaction) disadvantage score for comparison.
    async fn compute_additive_gap(
        &self,
        dimensions: &[InequalityDimension],
        metric: &InequalityMetric,
    ) -> Result<f64> {
        // Compute the worst single-dimension disadvantage and sum them
        let mut total_gap = 0.0;
        for dim in dimensions {
            let cells = self
                .fetch_cell_data(dim, metric, Utc::now().date_naive())
                .await?;
            if cells.len() >= 2 {
                let means: Vec<f64> = cells.iter().map(|c| {
                    if c.values.is_empty() {
                        0.0
                    } else {
                        c.values.iter().sum::<f64>() / c.values.len() as f64
                    }
                }).collect();
                let max_mean = means.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
                let min_mean = means.iter().cloned().fold(f64::INFINITY, f64::min);
                if max_mean > 0.0 {
                    total_gap += (max_mean - min_mean) / max_mean;
                }
            }
        }
        Ok(total_gap)
    }

    // ─────────────────────────────────────────────────────────────────
    // Internal Helpers — Statistics
    // ─────────────────────────────────────────────────────────────────

    /// Compute global inequality statistics for a flat array of values.
    fn compute_global_stats(values: &[f64], atkinson_epsilon: f64) -> GlobalInequalityStats {
        let gini = Self::calculate_gini(values);
        let theil = Self::calculate_theil(values);
        let atkinson = Self::calculate_atkinson(values, atkinson_epsilon);

        let n = values.len();
        let mean = if n > 0 {
            values.iter().sum::<f64>() / n as f64
        } else {
            0.0
        };

        let mut sorted = values.to_vec();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let p90_p10_ratio = if n >= 10 {
            let p10 = Self::percentile(&sorted, 10.0);
            let p90 = Self::percentile(&sorted, 90.0);
            if p10 > 0.0 {
                p90 / p10
            } else {
                f64::INFINITY
            }
        } else {
            0.0
        };

        let p90_p50_ratio = if n >= 4 {
            let p50 = Self::percentile(&sorted, 50.0);
            let p90 = Self::percentile(&sorted, 90.0);
            if p50 > 0.0 {
                p90 / p50
            } else {
                f64::INFINITY
            }
        } else {
            0.0
        };

        let variance = if n > 1 {
            values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1) as f64
        } else {
            0.0
        };
        let std_dev = variance.sqrt();
        let cv = if mean > 0.0 { std_dev / mean } else { 0.0 };

        GlobalInequalityStats {
            gini_coefficient: gini,
            theil_index: theil,
            p90_p10_ratio,
            p90_p50_ratio,
            coefficient_of_variation: cv,
            atkinson_index: atkinson,
        }
    }

    /// Compute per-cell statistics.
    fn compute_cell_stats(&self, cells: &[CellData], all_values: &[f64]) -> Vec<CellStats> {
        let total_sum: f64 = all_values.iter().sum();

        cells
            .iter()
            .map(|cell| {
                let mut sorted = cell.values.clone();
                sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

                let n = sorted.len();
                let mean = if n > 0 {
                    sorted.iter().sum::<f64>() / n as f64
                } else {
                    0.0
                };
                let median = Self::percentile(&sorted, 50.0);
                let p10 = Self::percentile(&sorted, 10.0);
                let p25 = Self::percentile(&sorted, 25.0);
                let p75 = Self::percentile(&sorted, 75.0);
                let p90 = Self::percentile(&sorted, 90.0);

                let variance = if n > 1 {
                    sorted.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / (n - 1) as f64
                } else {
                    0.0
                };
                let std_dev = variance.sqrt();

                let cell_sum: f64 = sorted.iter().sum();
                let share_of_total = if total_sum > 0.0 {
                    cell_sum / total_sum
                } else {
                    0.0
                };

                CellStats {
                    cell_id: cell.cell_id.clone(),
                    cell_label: cell.cell_label.clone(),
                    mean,
                    median,
                    p10,
                    p25,
                    p75,
                    p90,
                    std_dev,
                    sample_size: n as u32,
                    share_of_total,
                }
            })
            .collect()
    }

    /// Compute pairwise comparisons between all cells.
    fn compute_pairwise_comparisons(&self, cell_stats: &[CellStats]) -> Vec<InequalityComparison> {
        let mut comparisons = Vec::new();

        for i in 0..cell_stats.len() {
            for j in (i + 1)..cell_stats.len() {
                let a = &cell_stats[i];
                let b = &cell_stats[j];

                let ratio = if b.mean > 0.0 {
                    a.mean / b.mean
                } else {
                    f64::INFINITY
                };
                let absolute_gap = a.mean - b.mean;

                // Welch's t-test approximation
                let (p_value, cohens_d) = Self::welch_t_test(
                    a.mean, a.std_dev, a.sample_size,
                    b.mean, b.std_dev, b.sample_size,
                );

                let is_significant = p_value < 0.05;

                let narrative = if is_significant {
                    let pct_diff = if b.mean > 0.0 {
                        ((a.mean - b.mean) / b.mean * 100.0).abs()
                    } else {
                        0.0
                    };
                    let direction = if a.mean > b.mean { "more" } else { "less" };
                    format!(
                        "{} earns {:.0}% {} than {} (p={:.4}, Cohen's d={:.2})",
                        a.cell_label, pct_diff, direction, b.cell_label, p_value, cohens_d
                    )
                } else {
                    format!(
                        "No statistically significant difference between {} and {} (p={:.4})",
                        a.cell_label, b.cell_label, p_value
                    )
                };

                comparisons.push(InequalityComparison {
                    cell_a: a.cell_id.clone(),
                    cell_b: b.cell_id.clone(),
                    ratio,
                    absolute_gap,
                    statistical_significance: p_value,
                    is_significant,
                    effect_size: cohens_d,
                    narrative,
                });
            }
        }

        comparisons
    }

    /// Assign disadvantage scores to intersectional cells.
    /// Lower mean = higher disadvantage.
    fn assign_disadvantage_scores(cells: &mut [IntersectionalCell]) {
        if cells.is_empty() {
            return;
        }

        let means: Vec<f64> = cells.iter().map(|c| c.mean).collect();
        let max_mean = means.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let min_mean = means.iter().cloned().fold(f64::INFINITY, f64::min);
        let range = max_mean - min_mean;

        for cell in cells.iter_mut() {
            // Disadvantage = 1 - normalized_mean (so lower income = higher disadvantage)
            cell.disadvantage_score = if range > 0.0 {
                1.0 - (cell.mean - min_mean) / range
            } else {
                0.5 // All equal
            };
        }
    }

    /// Assign percentile ranks to intersectional cells.
    fn assign_percentile_ranks(cells: &mut [IntersectionalCell]) {
        let n = cells.len();
        if n == 0 {
            return;
        }

        // Sort by mean ascending
        let mut indexed: Vec<(usize, f64)> = cells.iter().enumerate().map(|(i, c)| (i, c.mean)).collect();
        indexed.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));

        for (rank, (original_idx, _)) in indexed.iter().enumerate() {
            cells[*original_idx].percentile_rank = (rank as f64 / (n - 1).max(1) as f64) * 100.0;
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Internal Helpers — Statistics Utilities
    // ─────────────────────────────────────────────────────────────────

    /// Compute percentile from a sorted array (linear interpolation).
    fn percentile(sorted: &[f64], p: f64) -> f64 {
        if sorted.is_empty() {
            return 0.0;
        }
        if sorted.len() == 1 {
            return sorted[0];
        }

        let n = sorted.len() as f64;
        let rank = (p / 100.0) * (n - 1.0);
        let lower = rank.floor() as usize;
        let upper = (rank.ceil() as usize).min(sorted.len() - 1);
        let frac = rank - lower as f64;

        sorted[lower] * (1.0 - frac) + sorted[upper] * frac
    }

    /// Welch's t-test: returns (p-value, Cohen's d).
    ///
    /// Uses the t-distribution approximation for p-value.
    fn welch_t_test(
        mean_a: f64, std_a: f64, n_a: u32,
        mean_b: f64, std_b: f64, n_b: u32,
    ) -> (f64, f64) {
        let na = n_a as f64;
        let nb = n_b as f64;

        if na < 2.0 || nb < 2.0 {
            return (1.0, 0.0);
        }

        let var_a = std_a * std_a;
        let var_b = std_b * std_b;

        // Welch's t-statistic
        let se = ((var_a / na) + (var_b / nb)).sqrt();
        if se == 0.0 {
            return (1.0, 0.0);
        }

        let t = (mean_a - mean_b) / se;

        // Welch-Satterthwaite degrees of freedom
        let df_num = (var_a / na + var_b / nb).powi(2);
        let df_den = (var_a / na).powi(2) / (na - 1.0) + (var_b / nb).powi(2) / (nb - 1.0);
        let df = if df_den > 0.0 { df_num / df_den } else { 1.0 };

        // Approximate two-tailed p-value using normal approximation for large df
        let p_value = if df > 30.0 {
            // Normal approximation
            2.0 * Self::standard_normal_cdf(-t.abs())
        } else {
            // Rough t-distribution approximation
            let x = df / (df + t * t);
            Self::regularized_incomplete_beta(df / 2.0, 0.5, x).min(1.0)
        };

        // Cohen's d
        let pooled_std = ((var_a * (na - 1.0) + var_b * (nb - 1.0)) / (na + nb - 2.0)).sqrt();
        let cohens_d = if pooled_std > 0.0 {
            (mean_a - mean_b) / pooled_std
        } else {
            0.0
        };

        (p_value, cohens_d)
    }

    /// Standard normal CDF approximation (Abramowitz & Stegun).
    fn standard_normal_cdf(x: f64) -> f64 {
        let a1 = 0.254829592;
        let a2 = -0.284496736;
        let a3 = 1.421413741;
        let a4 = -1.453152027;
        let a5 = 1.061405429;
        let p = 0.3275911;

        let sign = if x < 0.0 { -1.0 } else { 1.0 };
        let x_abs = x.abs();
        let t = 1.0 / (1.0 + p * x_abs);
        let y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x_abs * x_abs / 2.0).exp();

        0.5 * (1.0 + sign * y)
    }

    /// Regularized incomplete beta function approximation (for p-value computation).
    /// I_x(a, b) — rough approximation sufficient for inequality significance testing.
    fn regularized_incomplete_beta(a: f64, b: f64, x: f64) -> f64 {
        if x <= 0.0 {
            return 0.0;
        }
        if x >= 1.0 {
            return 1.0;
        }

        // Use continued fraction approximation (Lentz's method)
        let max_iterations = 200;
        let epsilon = 1e-10;

        let ln_beta = a.ln() + b.ln() - (a + b).ln()
            - Self::ln_gamma(a)
            - Self::ln_gamma(b)
            + Self::ln_gamma(a + b);

        let front = (a * x.ln() + b * (1.0 - x).ln() - ln_beta).exp() / a;

        // Continued fraction
        let mut f = 1.0;
        let mut c = 1.0;
        let mut d = 1.0 - (a + b) * x / (a + 1.0);
        if d.abs() < 1e-30 {
            d = 1e-30;
        }
        d = 1.0 / d;
        f = d;

        for m in 1..=max_iterations {
            let m_f = m as f64;

            // Even step
            let numerator = m_f * (b - m_f) * x / ((a + 2.0 * m_f - 1.0) * (a + 2.0 * m_f));
            d = 1.0 + numerator * d;
            if d.abs() < 1e-30 {
                d = 1e-30;
            }
            d = 1.0 / d;
            c = 1.0 + numerator / c;
            if c.abs() < 1e-30 {
                c = 1e-30;
            }
            f *= d * c;

            // Odd step
            let numerator = -(a + m_f) * (a + b + m_f) * x / ((a + 2.0 * m_f) * (a + 2.0 * m_f + 1.0));
            d = 1.0 + numerator * d;
            if d.abs() < 1e-30 {
                d = 1e-30;
            }
            d = 1.0 / d;
            c = 1.0 + numerator / c;
            if c.abs() < 1e-30 {
                c = 1e-30;
            }
            let delta = d * c;
            f *= delta;

            if (delta - 1.0).abs() < epsilon {
                break;
            }
        }

        (front * f).clamp(0.0, 1.0)
    }

    /// Log-gamma function (Stirling approximation).
    fn ln_gamma(x: f64) -> f64 {
        let coefficients = [
            76.18009172947146,
            -86.50532032941677,
            24.01409824083091,
            -1.231739572450155,
            0.1208650973866179e-2,
            -0.5395239384953e-5,
        ];

        let mut y = x;
        let mut tmp = x + 5.5;
        tmp -= (x + 0.5) * tmp.ln();
        let mut ser = 1.000000000190015;

        for coeff in &coefficients {
            y += 1.0;
            ser += coeff / y;
        }

        -tmp + (2.5066282746310005 * ser / x).ln()
    }

    // ─────────────────────────────────────────────────────────────────
    // Internal Helpers — Persistence & Caching
    // ─────────────────────────────────────────────────────────────────

    /// Store snapshot in PostgreSQL and time-series in ClickHouse.
    async fn store_snapshot(&self, snapshot: &InequalitySnapshot) -> Result<()> {
        // PostgreSQL: snapshot metadata
        sqlx::query(
            r#"
            INSERT INTO inequality_snapshots
                (id, snapshot_date, dimension, metric, global_stats, cell_stats, comparisons, trends, computed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO UPDATE SET
                global_stats = EXCLUDED.global_stats,
                cell_stats = EXCLUDED.cell_stats,
                comparisons = EXCLUDED.comparisons,
                trends = EXCLUDED.trends,
                computed_at = EXCLUDED.computed_at
            "#,
        )
        .bind(snapshot.id)
        .bind(snapshot.snapshot_date)
        .bind(snapshot.dimension.to_string())
        .bind(snapshot.metric.to_string())
        .bind(serde_json::to_value(&snapshot.global_stats)?)
        .bind(serde_json::to_value(&snapshot.cell_stats)?)
        .bind(serde_json::to_value(&snapshot.comparisons)?)
        .bind(serde_json::to_value(&snapshot.trends)?)
        .bind(snapshot.computed_at)
        .execute(&self.db.postgres)
        .await
        .context("Failed to store inequality snapshot in PostgreSQL")?;

        // ClickHouse: time-series per cell
        for cell in &snapshot.cell_stats {
            let insert = format!(
                r#"
                INSERT INTO inequality_timeseries
                    (snapshot_date, dimension, metric, cell_id, cell_label, mean, median, p10, p25, p75, p90, std_dev, sample_size, share_of_total, gini, theil, computed_at)
                VALUES ('{date}', '{dim}', '{metric}', '{cell_id}', '{cell_label}', {mean}, {median}, {p10}, {p25}, {p75}, {p90}, {std_dev}, {n}, {share}, {gini}, {theil}, '{computed}')
                "#,
                date = snapshot.snapshot_date,
                dim = snapshot.dimension,
                metric = snapshot.metric,
                cell_id = cell.cell_id,
                cell_label = cell.cell_label,
                mean = cell.mean,
                median = cell.median,
                p10 = cell.p10,
                p25 = cell.p25,
                p75 = cell.p75,
                p90 = cell.p90,
                std_dev = cell.std_dev,
                n = cell.sample_size,
                share = cell.share_of_total,
                gini = snapshot.global_stats.gini_coefficient,
                theil = snapshot.global_stats.theil_index,
                computed = snapshot.computed_at.format("%Y-%m-%d %H:%M:%S%.3f") ,
            );
            self.db
                .clickhouse
                .query(&insert)
                .execute()
                .await
                .context("Failed to insert inequality time-series into ClickHouse")?;
        }

        debug!(id = %snapshot.id, "Snapshot stored in PostgreSQL + ClickHouse");
        Ok(())
    }

    /// Store intersectional analysis results.
    async fn store_intersectional(&self, analysis: &IntersectionalAnalysis) -> Result<()> {
        let today = Utc::now().date_naive();
        let dims_json = serde_json::to_string(&analysis.dimensions)?;

        for cell in &analysis.intersectional_cells {
            let combo_json = serde_json::to_string(&cell.combination)?;
            let insert = format!(
                r#"
                INSERT INTO intersectional_inequality
                    (snapshot_date, metric, dimensions_json, cell_combination, mean, median, sample_size, percentile_rank, disadvantage_score, computed_at)
                VALUES ('{date}', '{metric}', '{dims}', '{combo}', {mean}, {median}, {n}, {pct}, {disadv}, '{computed}')
                "#,
                date = today,
                metric = analysis.metric,
                dims = dims_json.replace('"', "'"),
                combo = combo_json.replace('"', "'"),
                mean = cell.mean,
                median = cell.median,
                n = cell.sample_size,
                pct = cell.percentile_rank,
                disadv = cell.disadvantage_score,
                computed = analysis.computed_at.format("%Y-%m-%d %H:%M:%S%.3f"),
            );
            self.db
                .clickhouse
                .query(&insert)
                .execute()
                .await
                .context("Failed to store intersectional data in ClickHouse")?;
        }

        debug!(id = %analysis.id, "Intersectional analysis stored");
        Ok(())
    }

    /// Cache snapshot in Redis.
    async fn cache_snapshot(&self, snapshot: &InequalitySnapshot) -> Result<()> {
        let key = format!(
            "ineq:{}:{}:{}",
            snapshot.dimension,
            snapshot.metric,
            snapshot.snapshot_date
        );
        let value = serde_json::to_string(snapshot)?;
        let mut conn = self.db.redis.clone();

        redis::cmd("SET")
            .arg(&key)
            .arg(&value)
            .arg("EX")
            .arg(604_800_i64) // 7 days TTL
            .execute_async(&mut conn)
            .await
            .context("Failed to cache snapshot in Redis")?;

        debug!(key = %key, "Snapshot cached in Redis");
        Ok(())
    }

    /// Store an alert in PostgreSQL.
    async fn store_alert(&self, alert: &InequalityAlert) -> Result<()> {
        sqlx::query(
            r#"
            INSERT INTO inequality_alerts
                (id, dimension, metric, alert_type, severity, message, details, acknowledged, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, false, $8)
            "#,
        )
        .bind(alert.id)
        .bind(format!("{:?}", alert.dimension))
        .bind(format!("{:?}", alert.metric))
        .bind(format!("{:?}", alert.alert_type))
        .bind(format!("{:?}", alert.severity))
        .bind(&alert.message)
        .bind(&alert.details)
        .bind(alert.created_at)
        .execute(&self.db.postgres)
        .await
        .context("Failed to store inequality alert")?;

        Ok(())
    }

    /// Check snapshot against thresholds and emit OODA signals if needed.
    async fn check_and_emit_alerts(&self, snapshot: &InequalitySnapshot) -> Result<()> {
        // Check if Gini change exceeds threshold by comparing with previous snapshot
        let previous = self
            .fetch_previous_gini(&snapshot.dimension, &snapshot.metric, snapshot.snapshot_date)
            .await;

        if let Some(prev_gini) = previous {
            let change = snapshot.global_stats.gini_coefficient - prev_gini;
            if change.abs() > self.config.gini_change_alert_threshold {
                let alert = InequalityAlert {
                    id: Uuid::new_v4(),
                    dimension: snapshot.dimension.clone(),
                    metric: snapshot.metric.clone(),
                    alert_type: InequalityAlertType::GiniIncrease,
                    severity: if change > 0.05 {
                        AlertSeverity::Critical
                    } else {
                        AlertSeverity::Warning
                    },
                    message: format!(
                        "Gini coefficient for {} inequality in {} changed by {:.3} (from {:.3} to {:.3})",
                        snapshot.metric, snapshot.dimension, change, prev_gini, snapshot.global_stats.gini_coefficient
                    ),
                    details: serde_json::json!({
                        "previous_gini": prev_gini,
                        "current_gini": snapshot.global_stats.gini_coefficient,
                        "change": change,
                    }),
                    created_at: Utc::now(),
                };

                self.store_alert(&alert).await?;

                // Emit OODA signal
                self.emit_ooda_signal("inequality_alert", &serde_json::json!({
                    "alert_id": alert.id,
                    "dimension": snapshot.dimension.to_string(),
                    "metric": snapshot.metric.to_string(),
                    "gini_change": change,
                    "severity": format!("{:?}", alert.severity),
                }))
                .await?;
            }
        }

        Ok(())
    }

    /// Emit intersectional compound disadvantage alert.
    async fn emit_intersectional_alert(&self, analysis: &IntersectionalAnalysis) -> Result<()> {
        let worst = analysis.most_disadvantaged.first();
        if let Some(worst_cell) = worst {
            let alert = InequalityAlert {
                id: Uuid::new_v4(),
                dimension: InequalityDimension::Intersectional {
                    dimensions: analysis
                        .dimensions
                        .iter()
                        .map(|d| match d.as_str() {
                            "gender" => InequalityDimension::Gender,
                            "region" => InequalityDimension::Region,
                            "worker_type" => InequalityDimension::WorkerType,
                            _ => InequalityDimension::Region,
                        })
                        .collect(),
                },
                metric: analysis.metric.clone(),
                alert_type: InequalityAlertType::IntersectionalCompound,
                severity: AlertSeverity::Critical,
                message: format!(
                    "Compounding intersectional disadvantage detected: {} has disadvantage score {:.2} ({} metric)",
                    worst_cell
                        .combination
                        .values()
                        .cloned()
                        .collect::<Vec<_>>()
                        .join(" + "),
                    worst_cell.disadvantage_score,
                    analysis.metric,
                ),
                details: serde_json::json!({
                    "additive_vs_intersectional_gap": analysis.additive_vs_intersectional_gap,
                    "worst_cell": worst_cell.combination,
                    "worst_mean": worst_cell.mean,
                    "worst_disadvantage_score": worst_cell.disadvantage_score,
                }),
                created_at: Utc::now(),
            };

            self.store_alert(&alert).await?;

            self.emit_ooda_signal("intersectional_inequality_alert", &serde_json::json!({
                "alert_id": alert.id,
                "metric": analysis.metric.to_string(),
                "gap": analysis.additive_vs_intersectional_gap,
                "worst_combination": worst_cell.combination,
            }))
            .await?;
        }

        Ok(())
    }

}

// ─────────────────────────────────────────────────────────────────────
// Database Row Types (ClickHouse query results)
// ─────────────────────────────────────────────────────────────────────

/// Internal cell data fetched from ClickHouse.
#[derive(Debug, Clone)]
struct CellData {
    cell_id: String,
    cell_label: String,
    values: Vec<f64>,
}

/// ClickHouse row type for per-worker-value queries.
/// We fetch individual rows and group in Rust to avoid ClickHouse array type issues.
#[derive(Debug, clickhouse::Row, Deserialize)]
struct ValueRow {
    cell_id: String,
    cell_label: String,
    value: f64,
}

/// ClickHouse row type for trend queries.
#[derive(Debug, clickhouse::Row, Deserialize)]
struct TrendRow {
    snapshot_date: String,
    gini: f64,
}

// ─────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // ─── Gini Coefficient Tests ─────────────────────────────────────

    #[test]
    fn gini_perfect_equality() {
        let values = vec![100.0, 100.0, 100.0, 100.0, 100.0];
        let gini = InequalityTracker::calculate_gini(&values);
        assert!(
            gini.abs() < 1e-10,
            "Gini should be 0 for equal distribution, got {}",
            gini
        );
    }

    #[test]
    fn gini_perfect_inequality() {
        // One person has everything, rest have nothing
        let values = vec![0.0, 0.0, 0.0, 0.0, 1000.0];
        let gini = InequalityTracker::calculate_gini(&values);
        assert!(
            gini > 0.7,
            "Gini should be high for extreme inequality, got {}",
            gini
        );
    }

    #[test]
    fn gini_empty_input() {
        let values: Vec<f64> = vec![];
        let gini = InequalityTracker::calculate_gini(&values);
        assert_eq!(gini, 0.0);
    }

    #[test]
    fn gini_single_value() {
        let values = vec![500.0];
        let gini = InequalityTracker::calculate_gini(&values);
        assert_eq!(gini, 0.0);
    }

    #[test]
    fn gini_moderate_inequality() {
        // Typical informal economy distribution
        let values = vec![200.0, 300.0, 400.0, 500.0, 800.0, 1200.0, 2000.0];
        let gini = InequalityTracker::calculate_gini(&values);
        assert!(
            gini > 0.15 && gini < 0.45,
            "Moderate distribution should have Gini 0.15-0.45, got {}",
            gini
        );
    }

    // ─── Theil Index Tests ──────────────────────────────────────────

    #[test]
    fn theil_perfect_equality() {
        let values = vec![100.0, 100.0, 100.0, 100.0];
        let theil = InequalityTracker::calculate_theil(&values);
        assert!(
            theil.abs() < 1e-10,
            "Theil should be 0 for equal distribution, got {}",
            theil
        );
    }

    #[test]
    fn theil_positive_for_inequality() {
        let values = vec![100.0, 200.0, 500.0, 2000.0];
        let theil = InequalityTracker::calculate_theil(&values);
        assert!(theil > 0.0, "Theil should be positive for unequal distribution");
    }

    #[test]
    fn theil_empty_input() {
        let values: Vec<f64> = vec![];
        let theil = InequalityTracker::calculate_theil(&values);
        assert_eq!(theil, 0.0);
    }

    #[test]
    fn theil_zero_mean() {
        let values = vec![0.0, 0.0, 0.0];
        let theil = InequalityTracker::calculate_theil(&values);
        assert_eq!(theil, 0.0);
    }

    // ─── Theil Decomposition Tests ──────────────────────────────────

    #[test]
    fn theil_decompose_additivity() {
        // T_total = T_within + T_between
        let group_a = vec![100.0, 200.0, 300.0];
        let group_b = vec![500.0, 600.0, 700.0];
        let all: Vec<f64> = group_a.iter().chain(group_b.iter()).cloned().collect();
        let groups = vec![group_a, group_b];
        let meta = vec![
            CellData {
                cell_id: "a".into(),
                cell_label: "Group A".into(),
                values: vec![],
            },
            CellData {
                cell_id: "b".into(),
                cell_label: "Group B".into(),
                values: vec![],
            },
        ];

        let decomp = InequalityTracker::theil_decompose(&all, &groups, &meta);

        // Within + Between should approximately equal Total
        let reconstructed = decomp
            .within_group
            .iter()
            .map(|g| g.income_share * g.theil)
            .sum::<f64>()
            + decomp.between_group_theil;

        assert!(
            (decomp.total_theil - reconstructed).abs() < 0.01,
            "Theil decomposition should be additive: total={}, within+between={}",
            decomp.total_theil,
            reconstructed
        );
    }

    #[test]
    fn theil_decompose_homogeneous_groups() {
        // If within-group inequality is 0, all inequality is between groups
        let group_a = vec![100.0, 100.0, 100.0];
        let group_b = vec![500.0, 500.0, 500.0];
        let all: Vec<f64> = group_a.iter().chain(group_b.iter()).cloned().collect();
        let groups = vec![group_a, group_b];
        let meta = vec![
            CellData {
                cell_id: "a".into(),
                cell_label: "Group A".into(),
                values: vec![],
            },
            CellData {
                cell_id: "b".into(),
                cell_label: "Group B".into(),
                values: vec![],
            },
        ];

        let decomp = InequalityTracker::theil_decompose(&all, &groups, &meta);

        // Within-group should be ~0 (all members equal within each group)
        for g in &decomp.within_group {
            assert!(
                g.theil.abs() < 1e-10,
                "Within-group Theil should be ~0 for homogeneous groups, got {}",
                g.theil
            );
        }

        // Between should be close to total
        assert!(
            decomp.between_share > 0.95,
            "Between-group share should be ~100% when groups are internally equal, got {:.2}%",
            decomp.between_share * 100.0
        );
    }

    // ─── Atkinson Index Tests ───────────────────────────────────────

    #[test]
    fn atkinson_perfect_equality() {
        let values = vec![100.0, 100.0, 100.0, 100.0];
        let atkinson = InequalityTracker::calculate_atkinson(&values, 0.5);
        assert!(
            atkinson.abs() < 1e-10,
            "Atkinson should be 0 for equal distribution, got {}",
            atkinson
        );
    }

    #[test]
    fn atkinson_increases_with_epsilon() {
        let values = vec![100.0, 200.0, 500.0, 2000.0, 5000.0];

        let a_low = InequalityTracker::calculate_atkinson(&values, 0.1);
        let a_mid = InequalityTracker::calculate_atkinson(&values, 0.5);
        let a_high = InequalityTracker::calculate_atkinson(&values, 0.9);
        let a_extreme = InequalityTracker::calculate_atkinson(&values, 1.0);

        assert!(
            a_low < a_mid && a_mid < a_high && a_high < a_extreme,
            "Atkinson should increase with epsilon: {} < {} < {} < {}",
            a_low, a_mid, a_high, a_extreme
        );
    }

    #[test]
    fn atkinson_epsilon_zero() {
        let values = vec![100.0, 200.0, 500.0, 2000.0];
        let atkinson = InequalityTracker::calculate_atkinson(&values, 0.0);
        assert_eq!(atkinson, 0.0, "Atkinson with ε=0 should be 0");
    }

    #[test]
    fn atkinson_epsilon_one_log_mean() {
        // ε=1 uses geometric mean / arithmetic mean
        let values = vec![100.0, 200.0, 300.0, 400.0];
        let atkinson = InequalityTracker::calculate_atkinson(&values, 1.0);
        assert!(
            atkinson > 0.0 && atkinson < 1.0,
            "Atkinson with ε=1 should be between 0 and 1, got {}",
            atkinson
        );
    }

    #[test]
    fn atkinson_empty_input() {
        let values: Vec<f64> = vec![];
        let atkinson = InequalityTracker::calculate_atkinson(&values, 0.5);
        assert_eq!(atkinson, 0.0);
    }

    // ─── Percentile Tests ───────────────────────────────────────────

    #[test]
    fn percentile_basic() {
        let sorted = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        assert_eq!(InequalityTracker::percentile(&sorted, 0.0), 10.0);
        assert_eq!(InequalityTracker::percentile(&sorted, 100.0), 50.0);
        assert_eq!(InequalityTracker::percentile(&sorted, 50.0), 30.0);
    }

    #[test]
    fn percentile_interpolation() {
        let sorted = vec![10.0, 20.0, 30.0, 40.0];
        let p25 = InequalityTracker::percentile(&sorted, 25.0);
        assert!(
            (p25 - 17.5).abs() < 0.1,
            "P25 should be ~17.5, got {}",
            p25
        );
    }

    // ─── Disadvantage Score Tests ───────────────────────────────────

    #[test]
    fn disadvantage_score_assignment() {
        let mut cells = vec![
            IntersectionalCell {
                combination: HashMap::new(),
                mean: 500.0,
                median: 450.0,
                sample_size: 100,
                percentile_rank: 0.0,
                disadvantage_score: 0.0,
            },
            IntersectionalCell {
                combination: HashMap::new(),
                mean: 200.0,
                median: 180.0,
                sample_size: 100,
                percentile_rank: 0.0,
                disadvantage_score: 0.0,
            },
            IntersectionalCell {
                combination: HashMap::new(),
                mean: 1000.0,
                median: 900.0,
                sample_size: 100,
                percentile_rank: 0.0,
                disadvantage_score: 0.0,
            },
        ];

        InequalityTracker::assign_disadvantage_scores(&mut cells);

        // Lowest income should have highest disadvantage
        assert!(
            cells[1].disadvantage_score > cells[0].disadvantage_score,
            "Lower income should have higher disadvantage score"
        );
        assert!(
            cells[0].disadvantage_score > cells[2].disadvantage_score,
            "Middle income should have higher disadvantage than highest income"
        );

        // Highest income should have lowest disadvantage
        assert!(
            cells[2].disadvantage_score < 0.1,
            "Highest income disadvantage should be near 0, got {}",
            cells[2].disadvantage_score
        );
    }

    // ─── Display Trait Tests ────────────────────────────────────────

    #[test]
    fn worker_type_display() {
        assert_eq!(WorkerType::MamaMboga.to_string(), "mama_mboga");
        assert_eq!(WorkerType::BodaBoda.to_string(), "boda_boda");
        assert_eq!(WorkerType::Other("custom".into()).to_string(), "custom");
    }

    #[test]
    fn dimension_display() {
        assert_eq!(InequalityDimension::Region.to_string(), "region");
        assert_eq!(InequalityDimension::Gender.to_string(), "gender");

        let intersectional = InequalityDimension::Intersectional {
            dimensions: vec![
                InequalityDimension::Gender,
                InequalityDimension::Region,
                InequalityDimension::WorkerType,
            ],
        };
        assert_eq!(
            intersectional.to_string(),
            "intersectional(gender_x_region_x_worker_type)"
        );
    }

    #[test]
    fn metric_display() {
        assert_eq!(InequalityMetric::DailyProfit.to_string(), "daily_profit");
        assert_eq!(InequalityMetric::CreditAccess.to_string(), "credit_access");
        assert_eq!(
            InequalityMetric::Custom("my_metric".into()).to_string(),
            "my_metric"
        );
    }

    // ─── Welch's t-test Tests ───────────────────────────────────────

    #[test]
    fn welch_t_test_identical_groups() {
        let (p, d) = InequalityTracker::welch_t_test(100.0, 10.0, 50, 100.0, 10.0, 50);
        assert!(p > 0.99, "Identical groups should have p≈1.0, got {}", p);
        assert!(d.abs() < 0.01, "Cohen's d should be ~0, got {}", d);
    }

    #[test]
    fn welch_t_test_different_groups() {
        let (p, d) = InequalityTracker::welch_t_test(100.0, 10.0, 100, 150.0, 10.0, 100);
        assert!(p < 0.001, "Very different groups should have p<0.001, got {}", p);
        assert!(d.abs() > 2.0, "Cohen's d should be large, got {}", d);
    }
}
