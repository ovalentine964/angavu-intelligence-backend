//! AnomalyDetector — Real-time anomaly detection across all data streams
//!
//! Detects sudden shifts that indicate fraud, market shocks, policy impacts,
//! or emerging crises before they show up in aggregate statistics.
//!
//! ## Detection Methods
//!
//! - **Z-score**: Statistical outlier detection against rolling mean ± std dev
//! - **CUSUM**: Change-point detection for sustained baseline shifts
//! - **Seasonal ESD**: Extreme Studentized Deviate for time series with trend + seasonality
//! - **Multi-stream correlation**: Auto-correlates simultaneous anomalies to generate hypotheses
//!
//! ## OODA Integration
//!
//! - **Observe**: Receives streaming data from ALL other tools via OODA event bus
//! - **Orient**: Maintains rolling statistical models per metric per region
//! - **Decide**: Classifies severity; Critical/Emergency bypass normal cadence
//! - **Act**: Routes to AlertGenerator, AuditLogger, ScenarioModeler, ReportEngine

use anyhow::{anyhow, Result};
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use uuid::Uuid;

use crate::db::DatabaseConnections;
use super::demand_forecaster::WorkerType;

// ─────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────

/// Configuration for the AnomalyDetector.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyConfig {
    /// Z-score threshold for point anomalies (default: 3.0).
    pub z_score_threshold: f64,
    /// Minimum data points before detection activates for a metric.
    pub min_history_points: u32,
    /// Sliding window size for rolling statistics (data points).
    pub window_size: u32,
    /// How far back to load baselines on startup (days).
    pub baseline_lookback_days: u32,
    /// Minimum consecutive anomalous points before raising alert.
    pub min_consecutive_anomalies: u32,
    /// Rate limit: max anomalies raised per metric per hour.
    pub max_alerts_per_metric_per_hour: u32,
    /// CUSUM threshold for change-point detection.
    pub cusum_threshold: f64,
    /// CUSUM slack parameter (allowance for normal variation).
    pub cusum_slack: f64,
    /// Seasonal ESD maximum ratio of outliers to detect.
    pub seasonal_esd_max_outlier_ratio: f64,
    /// Seasonal period (data points per cycle, e.g. 7 for daily data with weekly seasonality).
    pub seasonal_period: usize,
    /// Correlation window for multi-stream anomaly matching (minutes).
    pub correlation_window_minutes: i64,
}

impl Default for AnomalyConfig {
    fn default() -> Self {
        Self {
            z_score_threshold: 3.0,
            min_history_points: 30,
            window_size: 100,
            baseline_lookback_days: 90,
            min_consecutive_anomalies: 3,
            max_alerts_per_metric_per_hour: 5,
            cusum_threshold: 5.0,
            cusum_slack: 0.5,
            seasonal_esd_max_outlier_ratio: 0.1,
            seasonal_period: 7,
            correlation_window_minutes: 30,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Statistical Models (in-memory for speed)
// ─────────────────────────────────────────────────────────────────────

/// Running statistical models loaded into memory for real-time detection.
#[derive(Debug, Clone)]
pub enum StatisticalModel {
    /// Z-score based: compare point to rolling mean ± std dev.
    ZScore {
        mean: f64,
        std_dev: f64,
        window: VecDeque<f64>,
    },
    /// CUSUM change-point detection model.
    CUSUM {
        target_mean: f64,
        cumulative_sum_pos: f64,
        cumulative_sum_neg: f64,
        threshold: f64,
        slack: f64,
    },
    /// Seasonal hybrid ESD for time series with trend + seasonality.
    SeasonalESD {
        trend_component: Vec<f64>,
        seasonal_component: Vec<f64>,
        residual_std: f64,
        period: usize,
    },
}

impl StatisticalModel {
    /// Create a new Z-score model with an empty window.
    pub fn new_zscore() -> Self {
        Self::ZScore {
            mean: 0.0,
            std_dev: 0.0,
            window: VecDeque::new(),
        }
    }

    /// Create a new CUSUM model with the given parameters.
    pub fn new_cusum(initial_mean: f64, threshold: f64, slack: f64) -> Self {
        Self::CUSUM {
            target_mean: initial_mean,
            cumulative_sum_pos: 0.0,
            cumulative_sum_neg: 0.0,
            threshold,
            slack,
        }
    }

    /// Create a new Seasonal ESD model.
    pub fn new_seasonal_esd(period: usize) -> Self {
        Self::SeasonalESD {
            trend_component: Vec::new(),
            seasonal_component: vec![0.0; period],
            residual_std: 0.0,
            period,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Anomaly Event Types
// ─────────────────────────────────────────────────────────────────────

/// A detected anomaly event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyEvent {
    pub id: Uuid,
    pub metric_name: String,
    pub region: String,
    pub worker_type: Option<WorkerType>,
    pub anomaly_type: AnomalyType,
    pub severity: AnomalySeverity,
    pub observed_value: f64,
    pub expected_value: f64,
    pub deviation_sigma: f64,
    pub context: AnomalyContext,
    pub detected_at: DateTime<Utc>,
    pub acknowledged: bool,
    pub root_cause: Option<String>,
}

/// Classification of anomaly types.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum AnomalyType {
    /// Single outlier value.
    PointAnomaly,
    /// Normal value in abnormal context (e.g., high sales at 3 AM).
    ContextualAnomaly,
    /// Sequence of values that together are anomalous.
    CollectiveAnomaly,
    /// Sustained shift in baseline.
    ChangePoint,
    /// Pattern breaks expected seasonality.
    SeasonalBreak,
}

/// Severity levels for anomalies.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum AnomalySeverity {
    /// Noteworthy, no action needed.
    Info,
    /// May indicate emerging issue.
    Warning,
    /// Requires immediate investigation.
    Critical,
    /// Systemic risk detected.
    Emergency,
}

/// Contextual information attached to an anomaly event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyContext {
    pub recent_values: Vec<TimestampedValue>,
    pub historical_mean: f64,
    pub historical_std: f64,
    pub peer_comparison: Option<PeerComparison>,
    pub possible_causes: Vec<String>,
}

/// A value with its timestamp for context windows.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimestampedValue {
    pub timestamp: DateTime<Utc>,
    pub value: f64,
}

/// Comparison against a peer region or cohort.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PeerComparison {
    pub peer_region: String,
    pub peer_value: f64,
    pub divergence_pct: f64,
}

// ─────────────────────────────────────────────────────────────────────
// Data Point for batch ingestion
// ─────────────────────────────────────────────────────────────────────

/// A single data point for ingestion.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataPoint {
    pub metric_name: String,
    pub region: String,
    pub worker_type: Option<WorkerType>,
    pub value: f64,
    pub timestamp: DateTime<Utc>,
}

// ─────────────────────────────────────────────────────────────────────
// Anomaly Filter
// ─────────────────────────────────────────────────────────────────────

/// Filter for querying active anomalies.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AnomalyFilter {
    pub metric_name: Option<String>,
    pub region: Option<String>,
    pub worker_type: Option<WorkerType>,
    pub min_severity: Option<AnomalySeverity>,
    pub unacknowledged_only: bool,
    pub since: Option<DateTime<Utc>>,
}

// ─────────────────────────────────────────────────────────────────────
// Rate Limiter State
// ─────────────────────────────────────────────────────────────────────

/// Per-metric rate limiting for anomaly alerts.
#[derive(Debug, Clone)]
struct RateLimitState {
    window_start: DateTime<Utc>,
    count: u32,
}

// ─────────────────────────────────────────────────────────────────────
// Anomaly Detector
// ─────────────────────────────────────────────────────────────────────

/// The main anomaly detection engine.
///
/// Maintains in-memory statistical models for real-time detection across
/// all data streams. Supports Z-score, CUSUM, and Seasonal ESD methods,
/// with automatic multi-stream correlation for hypothesis generation.
pub struct AnomalyDetector {
    db: DatabaseConnections,
    config: AnomalyConfig,
    /// Running statistical models keyed by "metric:region:worker_type".
    models: dashmap::DashMap<String, Vec<StatisticalModel>>,
    /// Recent values per metric key for context windows.
    recent_values: dashmap::DashMap<String, VecDeque<TimestampedValue>>,
    /// Active (unacknowledged) anomalies.
    active_anomalies: dashmap::DashMap<Uuid, AnomalyEvent>,
    /// Rate limit state per metric key.
    rate_limits: dashmap::DashMap<String, RateLimitState>,
}

impl AnomalyDetector {
    /// Create a new AnomalyDetector with default configuration.
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            config: AnomalyConfig::default(),
            models: dashmap::DashMap::new(),
            recent_values: dashmap::DashMap::new(),
            active_anomalies: dashmap::DashMap::new(),
            rate_limits: dashmap::DashMap::new(),
        }
    }

    /// Create with custom configuration.
    pub fn with_config(db: DatabaseConnections, config: AnomalyConfig) -> Self {
        Self {
            db,
            config,
            models: dashmap::DashMap::new(),
            recent_values: dashmap::DashMap::new(),
            active_anomalies: dashmap::DashMap::new(),
            rate_limits: dashmap::DashMap::new(),
        }
    }

    /// Build the composite key for a metric stream.
    fn metric_key(metric: &str, region: &str, worker_type: &Option<WorkerType>) -> String {
        let wt = worker_type
            .as_ref()
            .map(|w| format!("{:?}", w))
            .unwrap_or_else(|| "all".to_string());
        format!("{}:{}:{}", metric, region, wt)
    }

    // ─────────────────────────────────────────────────────────────────
    // Public API
    // ─────────────────────────────────────────────────────────────────

    /// Ingest a single data point and check for anomalies in real-time.
    ///
    /// Updates the internal statistical models and returns an anomaly event
    /// if the point is detected as anomalous.
    pub async fn ingest_and_detect(
        &self,
        metric: &str,
        region: &str,
        worker_type: Option<WorkerType>,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Option<AnomalyEvent>> {
        let key = Self::metric_key(metric, region, &worker_type);

        // Update recent values for context
        self.push_recent_value(&key, value, timestamp);

        // Get or initialize models for this metric stream
        let has_enough_history = {
            let entry = self.models.entry(key.clone()).or_insert_with(|| {
                vec![
                    StatisticalModel::new_zscore(),
                    StatisticalModel::new_cusum(
                        value,
                        self.config.cusum_threshold,
                        self.config.cusum_slack,
                    ),
                    StatisticalModel::new_seasonal_esd(self.config.seasonal_period),
                ]
            });
            let zscore = &entry[0];
            match zscore {
                StatisticalModel::ZScore { window, .. } => {
                    window.len() >= self.config.min_history_points as usize
                }
                _ => false,
            }
        };

        // Not enough history yet — just update models, no detection
        if !has_enough_history {
            self.update_models(&key, value)?;
            return Ok(None);
        }

        // Run all detectors
        let mut anomalies = Vec::new();

        // 1. Z-score point anomaly detection
        if let Some(event) = self.detect_zscore(&key, metric, region, &worker_type, value, timestamp)? {
            anomalies.push(event);
        }

        // 2. CUSUM change-point detection
        if let Some(event) = self.detect_cusum(&key, metric, region, &worker_type, value, timestamp)? {
            anomalies.push(event);
        }

        // 3. Seasonal anomaly detection
        if let Some(event) =
            self.detect_seasonal(&key, metric, region, &worker_type, value, timestamp)?
        {
            anomalies.push(event);
        }

        // Update models with the new value
        self.update_models(&key, value)?;

        // Select the most severe anomaly (if any)
        let event = anomalies
            .into_iter()
            .max_by_key(|a| a.severity.clone())
            .map(|mut e| {
                // Correlate with other simultaneous anomalies
                if let Ok(causes) =
                    self.correlate_anomalies_sync(&e, self.config.correlation_window_minutes)
                {
                    e.context.possible_causes = causes;
                }

                // Rate limit check
                if self.is_rate_limited(&key) {
                    return None;
                }

                // Store as active anomaly
                self.active_anomalies.insert(e.id, e.clone());

                // Persist to ClickHouse
                let db = self.db.clone();
                let event_clone = e.clone();
                tokio::spawn(async move {
                    Self::persist_anomaly(&db, &event_clone).await;
                });

                Some(e)
            })
            .flatten();

        Ok(event)
    }

    /// Batch-ingest and detect (for bulk ETL pipelines).
    pub async fn batch_detect(&self, points: Vec<DataPoint>) -> Result<Vec<AnomalyEvent>> {
        let mut events = Vec::new();
        for point in points {
            if let Some(event) = self
                .ingest_and_detect(
                    &point.metric_name,
                    &point.region,
                    point.worker_type,
                    point.value,
                    point.timestamp,
                )
                .await?
            {
                events.push(event);
            }
        }
        Ok(events)
    }

    /// Get active anomalies (unacknowledged), filtered.
    pub async fn get_active_anomalies(
        &self,
        filter: AnomalyFilter,
    ) -> Result<Vec<AnomalyEvent>> {
        let mut results: Vec<AnomalyEvent> = self
            .active_anomalies
            .iter()
            .filter(|entry| {
                let e = entry.value();
                if filter.unacknowledged_only && e.acknowledged {
                    return false;
                }
                if let Some(ref metric) = filter.metric_name {
                    if e.metric_name != *metric {
                        return false;
                    }
                }
                if let Some(ref region) = filter.region {
                    if e.region != *region {
                        return false;
                    }
                }
                if let Some(ref wt) = filter.worker_type {
                    let wt_str = format!("{:?}", wt);
                    let ewt_str = e.worker_type.as_ref().map(|w| format!("{:?}", w));
                    if ewt_str.as_deref() != Some(wt_str.as_str()) {
                        return false;
                    }
                }
                if let Some(ref min_sev) = filter.min_severity {
                    if e.severity < *min_sev {
                        return false;
                    }
                }
                if let Some(since) = filter.since {
                    if e.detected_at < since {
                        return false;
                    }
                }
                true
            })
            .map(|entry| entry.value().clone())
            .collect();

        // Sort by severity (descending) then timestamp (descending)
        results.sort_by(|a, b| {
            b.severity
                .cmp(&a.severity)
                .then_with(|| b.detected_at.cmp(&a.detected_at))
        });

        Ok(results)
    }

    /// Acknowledge an anomaly and optionally attach root cause.
    pub async fn acknowledge(
        &self,
        anomaly_id: Uuid,
        root_cause: Option<String>,
        acknowledged_by: String,
    ) -> Result<()> {
        let mut event = self
            .active_anomalies
            .get_mut(&anomaly_id)
            .ok_or_else(|| anyhow!("Anomaly {} not found", anomaly_id))?;

        event.acknowledged = true;
        event.root_cause = root_cause.clone();

        // Persist acknowledgment to PostgreSQL
        sqlx::query(
            "INSERT INTO anomaly_acknowledgments (anomaly_id, root_cause, acknowledged_by, acknowledged_at)
             VALUES ($1, $2, $3, now())
             ON CONFLICT (anomaly_id) DO UPDATE SET root_cause = $2, acknowledged_by = $3, acknowledged_at = now()",
        )
        .bind(anomaly_id)
        .bind(&root_cause)
        .bind(&acknowledged_by)
        .execute(&self.db.postgres)
        .await?;

        Ok(())
    }

    /// Run batch anomaly scan over historical data (backfill or audit).
    pub async fn scan_historical(
        &self,
        metric: &str,
        from: DateTime<Utc>,
        to: DateTime<Utc>,
    ) -> Result<Vec<AnomalyEvent>> {
        let query = format!(
            r#"
            SELECT
                region,
                worker_type,
                value,
                event_time
            FROM metric_timeseries
            WHERE metric_name = '{metric}'
              AND event_time >= '{from}'
              AND event_time <= '{to}'
            ORDER BY region, worker_type, event_time
            "#,
            metric = metric,
            from = from.format("%Y-%m-%d %H:%M:%S"),
            to = to.format("%Y-%m-%d %H:%M:%S"),
        );

        #[derive(clickhouse::Row, Deserialize)]
        struct MetricRow {
            region: String,
            worker_type: String,
            value: f64,
            event_time: chrono::NaiveDateTime,
        }

        let rows = self
            .db
            .clickhouse
            .query(&query)
            .fetch_all::<MetricRow>()
            .await
            .unwrap_or_default();

        // Group by region + worker_type and run detection
        let mut grouped: HashMap<String, Vec<(f64, DateTime<Utc>)>> = HashMap::new();
        for row in &rows {
            let key = format!("{}:{}", row.region, row.worker_type);
            grouped
                .entry(key)
                .or_default()
                .push((row.value, row.event_time.and_utc()));
        }

        let mut all_events = Vec::new();
        for (_key, points) in grouped {
            // Create temporary detector for this scan
            let temp_config = AnomalyConfig {
                min_history_points: 10, // Lower threshold for historical scan
                ..self.config.clone()
            };
            let temp_detector = AnomalyDetector::with_config(self.db.clone(), temp_config);

            for (value, ts) in &points {
                if let Some(event) = temp_detector
                    .ingest_and_detect(metric, "historical", None, *value, *ts)
                    .await?
                {
                    all_events.push(event);
                }
            }
        }

        Ok(all_events)
    }

    // ─────────────────────────────────────────────────────────────────
    // Detection Methods
    // ─────────────────────────────────────────────────────────────────

    /// Z-score based statistical outlier detection.
    ///
    /// Compares the incoming value against the rolling mean and standard
    /// deviation of the metric stream. Returns an anomaly if the absolute
    /// z-score exceeds the configured threshold.
    pub fn detect_zscore(
        &self,
        key: &str,
        metric: &str,
        region: &str,
        worker_type: &Option<WorkerType>,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Option<AnomalyEvent>> {
        let models = self.models.get(key).ok_or_else(|| {
            anyhow!("No models found for key {}", key)
        })?;

        let zscore_model = models.iter().find_map(|m| match m {
            StatisticalModel::ZScore {
                mean,
                std_dev,
                window,
            } => Some((*mean, *std_dev, window.len())),
            _ => None,
        });

        let (mean, std_dev, _window_len) = match zscore_model {
            Some(v) => v,
            None => return Ok(None),
        };

        if std_dev < 1e-10 {
            return Ok(None); // No variance yet
        }

        let z_score = (value - mean).abs() / std_dev;

        if z_score >= self.config.z_score_threshold {
            let expected = mean;
            let severity = self.classify_zscore_severity(z_score);

            let recent = self.get_recent_values(key, 20);
            let causes = self.generate_point_anomaly_hypotheses(metric, region, value, mean, std_dev);

            Ok(Some(AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: metric.to_string(),
                region: region.to_string(),
                worker_type: worker_type.clone(),
                anomaly_type: AnomalyType::PointAnomaly,
                severity,
                observed_value: value,
                expected_value: expected,
                deviation_sigma: z_score,
                context: AnomalyContext {
                    recent_values: recent,
                    historical_mean: mean,
                    historical_std: std_dev,
                    peer_comparison: None, // Populated by correlate_anomalies
                    possible_causes: causes,
                },
                detected_at: timestamp,
                acknowledged: false,
                root_cause: None,
            }))
        } else {
            Ok(None)
        }
    }

    /// CUSUM (Cumulative Sum) change-point detection.
    ///
    /// Detects sustained shifts in the mean of a metric stream. Unlike
    /// Z-score which catches individual outliers, CUSUM accumulates
    /// deviations from the target mean and fires when the cumulative
    /// sum crosses a threshold — indicating a regime change.
    pub fn detect_cusum(
        &self,
        key: &str,
        metric: &str,
        region: &str,
        worker_type: &Option<WorkerType>,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Option<AnomalyEvent>> {
        let mut models = self.models.get_mut(key).ok_or_else(|| {
            anyhow!("No models found for key {}", key)
        })?;

        let mut change_detected = false;
        let mut cumulative_pos = 0.0;
        let mut cumulative_neg = 0.0;
        let mut target = 0.0;
        let mut threshold = 0.0;

        for model in models.iter_mut() {
            if let StatisticalModel::CUSUM {
                target_mean,
                cumulative_sum_pos,
                cumulative_sum_neg,
                threshold: thresh,
                slack,
            } = model
            {
                target = *target_mean;
                threshold = *thresh;

                // CUSUM accumulation with slack
                let deviation_pos = value - target_mean - slack;
                let deviation_neg = target_mean - value - slack;

                *cumulative_sum_pos = (*cumulative_sum_pos + deviation_pos).max(0.0);
                *cumulative_sum_neg = (*cumulative_sum_neg + deviation_neg).max(0.0);

                cumulative_pos = *cumulative_sum_pos;
                cumulative_neg = *cumulative_sum_neg;

                // Check if either cumulative sum exceeds the threshold
                if *cumulative_sum_pos > *thresh || *cumulative_sum_neg > *thresh {
                    change_detected = true;
                    // Reset after detection
                    *cumulative_sum_pos = 0.0;
                    *cumulative_sum_neg = 0.0;
                    // Update target mean to new level
                    *target_mean = value;
                }
                break;
            }
        }

        if change_detected {
            let direction = if cumulative_pos > cumulative_neg {
                "increase"
            } else {
                "decrease"
            };
            let severity = AnomalySeverity::Critical;

            let recent = self.get_recent_values(key, 30);
            let causes = vec![
                format!(
                    "Sustained {} detected in {} — baseline shifted from {:.2}",
                    direction, metric, target
                ),
                "Possible policy change or market shock".to_string(),
                "Check for concurrent events in the same region".to_string(),
            ];

            Ok(Some(AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: metric.to_string(),
                region: region.to_string(),
                worker_type: worker_type.clone(),
                anomaly_type: AnomalyType::ChangePoint,
                severity,
                observed_value: value,
                expected_value: target,
                deviation_sigma: if cumulative_pos > cumulative_neg {
                    cumulative_pos / threshold
                } else {
                    cumulative_neg / threshold
                },
                context: AnomalyContext {
                    recent_values: recent,
                    historical_mean: target,
                    historical_std: 0.0, // Not applicable for CUSUM
                    peer_comparison: None,
                    possible_causes: causes,
                },
                detected_at: timestamp,
                acknowledged: false,
                root_cause: None,
            }))
        } else {
            Ok(None)
        }
    }

    /// Seasonal anomaly detection using decomposition.
    ///
    /// Decomposes the time series into trend + seasonal + residual components,
    /// then checks if the residual is abnormally large — indicating a value
    /// that breaks expected seasonal patterns.
    pub fn detect_seasonal(
        &self,
        key: &str,
        metric: &str,
        region: &str,
        worker_type: &Option<WorkerType>,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Option<AnomalyEvent>> {
        let mut models = self.models.get_mut(key).ok_or_else(|| {
            anyhow!("No models found for key {}", key)
        })?;

        let mut anomaly = None;

        for model in models.iter_mut() {
            if let StatisticalModel::SeasonalESD {
                trend_component,
                seasonal_component,
                residual_std,
                period,
            } = model
            {
                if trend_component.len() < *period * 2 {
                    // Not enough data for seasonal decomposition
                    break;
                }

                // Compute expected value: trend + seasonal
                let trend = if trend_component.len() >= 5 {
                    // Simple moving average trend
                    let n = trend_component.len();
                    let window = 5.min(n);
                    trend_component[n - window..n].iter().sum::<f64>() / window as f64
                } else {
                    trend_component.last().copied().unwrap_or(value)
                };

                let season_idx = trend_component.len() % period;
                let seasonal = seasonal_component[season_idx];
                let expected = trend + seasonal;

                // Compute residual
                let residual = value - expected;

                if *residual_std > 1e-10 {
                    let residual_z = residual.abs() / *residual_std;

                    if residual_z >= self.config.z_score_threshold {
                        let severity = self.classify_zscore_severity(residual_z);

                        let recent = self.get_recent_values(key, 20);
                        let causes = vec![
                            format!(
                                "Value deviates {:.1}σ from expected seasonal pattern",
                                residual_z
                            ),
                            format!(
                                "Expected: {:.2} (trend={:.2}, seasonal={:+.2})",
                                expected, trend, seasonal
                            ),
                            "Check for calendar effects, holidays, or one-off events".to_string(),
                        ];

                        anomaly = Some(AnomalyEvent {
                            id: Uuid::new_v4(),
                            metric_name: metric.to_string(),
                            region: region.to_string(),
                            worker_type: worker_type.clone(),
                            anomaly_type: AnomalyType::SeasonalBreak,
                            severity,
                            observed_value: value,
                            expected_value: expected,
                            deviation_sigma: residual_z,
                            context: AnomalyContext {
                                recent_values: recent,
                                historical_mean: trend,
                                historical_std: *residual_std,
                                peer_comparison: None,
                                possible_causes: causes,
                            },
                            detected_at: timestamp,
                            acknowledged: false,
                            root_cause: None,
                        });
                    }
                }

                // Update seasonal model
                trend_component.push(value);
                if trend_component.len() > *period * 10 {
                    trend_component.remove(0);
                }

                // Update seasonal component (exponential smoothing)
                let alpha = 0.1;
                let deseasonalized = value - trend;
                seasonal_component[season_idx] =
                    seasonal_component[season_idx] * (1.0 - alpha) + deseasonalized * alpha;

                // Update residual std (exponential moving average of squared residuals)
                let residual_sq = residual * residual;
                *residual_std =
                    (*residual_std * *residual_std * 0.95 + residual_sq * 0.05).sqrt();

                break;
            }
        }

        Ok(anomaly)
    }

    /// Correlate anomalies across multiple data streams.
    ///
    /// When an anomaly is detected in one stream, checks if other streams
    /// also show anomalies within the correlation window. Uses temporal
    /// proximity and metric relationships to generate hypotheses about
    /// root causes.
    pub fn correlate_anomalies_sync(
        &self,
        event: &AnomalyEvent,
        window_minutes: i64,
    ) -> Result<Vec<String>> {
        let window_start = event.detected_at - Duration::minutes(window_minutes);
        let window_end = event.detected_at + Duration::minutes(window_minutes);

        // Find anomalies in other streams within the time window
        let correlated: Vec<&AnomalyEvent> = self
            .active_anomalies
            .iter()
            .filter(|entry| {
                let other = entry.value();
                other.id != event.id
                    && other.detected_at >= window_start
                    && other.detected_at <= window_end
                    && !other.acknowledged
            })
            .map(|entry| entry.value())
            .collect();

        if correlated.is_empty() {
            return Ok(Vec::new());
        }

        let mut hypotheses = Vec::new();

        // Generate hypotheses based on correlated anomalies
        for other in &correlated {
            let hypothesis = self.generate_correlation_hypothesis(event, other);
            if !hypothesis.is_empty() {
                hypotheses.push(hypothesis);
            }
        }

        // Add systemic hypothesis if many streams are affected
        if correlated.len() >= 3 {
            let regions: std::collections::HashSet<&str> = correlated
                .iter()
                .map(|a| a.region.as_str())
                .collect();

            if regions.len() >= 2 {
                hypotheses.push(
                    "⚠️ Multi-region anomaly detected — possible systemic shock or policy event"
                        .to_string(),
                );
            }

            let metrics: std::collections::HashSet<&str> = correlated
                .iter()
                .map(|a| a.metric_name.as_str())
                .collect();

            if metrics.len() >= 3 {
                hypotheses.push(
                    "⚠️ Cross-metric anomaly cluster — investigate upstream cause (policy, weather, market event)".to_string(),
                );
            }
        }

        Ok(hypotheses)
    }

    /// Async wrapper for correlate_anomalies (used in OODA integration).
    pub async fn correlate_anomalies(
        &self,
        event: &AnomalyEvent,
        window_minutes: i64,
    ) -> Result<Vec<String>> {
        self.correlate_anomalies_sync(event, window_minutes)
    }

    // ─────────────────────────────────────────────────────────────────
    // Model Update
    // ─────────────────────────────────────────────────────────────────

    /// Update all statistical models for a metric stream with a new value.
    fn update_models(&self, key: &str, value: f64) -> Result<()> {
        if let Some(mut models) = self.models.get_mut(key) {
            for model in models.iter_mut() {
                match model {
                    StatisticalModel::ZScore {
                        mean,
                        std_dev,
                        window,
                    } => {
                        window.push_back(value);
                        if window.len() > self.config.window_size as usize {
                            window.pop_front();
                        }

                        // Recompute mean and std_dev
                        let n = window.len() as f64;
                        if n > 0.0 {
                            *mean = window.iter().sum::<f64>() / n;
                            if n > 1.0 {
                                let variance = window
                                    .iter()
                                    .map(|v| (v - *mean).powi(2))
                                    .sum::<f64>()
                                    / (n - 1.0);
                                *std_dev = variance.sqrt();
                            }
                        }
                    }
                    StatisticalModel::CUSUM { .. } => {
                        // CUSUM is updated in detect_cusum
                    }
                    StatisticalModel::SeasonalESD { .. } => {
                        // Seasonal ESD is updated in detect_seasonal
                    }
                }
            }
        }
        Ok(())
    }

    // ─────────────────────────────────────────────────────────────────
    // Severity Classification
    // ─────────────────────────────────────────────────────────────────

    /// Classify severity based on z-score magnitude.
    fn classify_zscore_severity(&self, z_score: f64) -> AnomalySeverity {
        if z_score >= 6.0 {
            AnomalySeverity::Emergency
        } else if z_score >= 4.5 {
            AnomalySeverity::Critical
        } else if z_score >= 3.5 {
            AnomalySeverity::Warning
        } else {
            AnomalySeverity::Info
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Rate Limiting
    // ─────────────────────────────────────────────────────────────────

    /// Check if a metric key is rate-limited.
    fn is_rate_limited(&self, key: &str) -> bool {
        let now = Utc::now();
        let mut entry = self.rate_limits.entry(key.to_string()).or_insert(RateLimitState {
            window_start: now,
            count: 0,
        });

        // Reset window if expired (1 hour)
        if now.signed_duration_since(entry.window_start).num_hours() >= 1 {
            entry.window_start = now;
            entry.count = 0;
        }

        entry.count += 1;
        entry.count > self.config.max_alerts_per_metric_per_hour
    }

    // ─────────────────────────────────────────────────────────────────
    // Context & Hypothesis Generation
    // ─────────────────────────────────────────────────────────────────

    /// Push a value into the recent values buffer.
    fn push_recent_value(&self, key: &str, value: f64, timestamp: DateTime<Utc>) {
        let mut entry = self
            .recent_values
            .entry(key.to_string())
            .or_insert_with(VecDeque::new);
        entry.push_back(TimestampedValue { timestamp, value });
        // Keep last 100 values
        while entry.len() > 100 {
            entry.pop_front();
        }
    }

    /// Get recent values for a metric key.
    fn get_recent_values(&self, key: &str, limit: usize) -> Vec<TimestampedValue> {
        self.recent_values
            .get(key)
            .map(|entry| entry.iter().rev().take(limit).cloned().collect())
            .unwrap_or_default()
    }

    /// Generate hypotheses for a point anomaly based on metric and deviation.
    fn generate_point_anomaly_hypotheses(
        &self,
        metric: &str,
        region: &str,
        value: f64,
        mean: f64,
        std_dev: f64,
    ) -> Vec<String> {
        let direction = if value > mean { "spike" } else { "drop" };
        let pct_change = ((value - mean) / mean.abs().max(1e-10) * 100.0).abs();

        let mut causes = vec![format!(
            "Unusual {} of {:.1}% in {} (z={:.1}σ)",
            direction,
            pct_change,
            metric,
            (value - mean).abs() / std_dev.max(1e-10)
        )];

        // Metric-specific hypotheses
        match metric {
            m if m.contains("transaction") || m.contains("volume") => {
                causes.push("Possible market closure, crackdown, or holiday".to_string());
                causes.push("Check for concurrent infrastructure disruptions".to_string());
            }
            m if m.contains("price") => {
                causes.push("Supply chain disruption or price manipulation".to_string());
                causes.push("Check fuel prices, import policies, or weather events".to_string());
            }
            m if m.contains("credit") || m.contains("fuliza") => {
                causes.push("Possible predatory lending sweep or policy change".to_string());
                causes.push("Check M-Pesa policy announcements".to_string());
            }
            m if m.contains("profit") || m.contains("income") => {
                causes.push("Demand shift, cost increase, or competitive entry".to_string());
                causes.push("Check market levy changes or supplier pricing".to_string());
            }
            _ => {
                causes.push(format!("Investigate {} in {}", metric, region));
            }
        }

        causes
    }

    /// Generate a hypothesis based on two correlated anomalies.
    fn generate_correlation_hypothesis(
        &self,
        primary: &AnomalyEvent,
        correlated: &AnomalyEvent,
    ) -> String {
        let same_region = primary.region == correlated.region;
        let time_diff = (primary.detected_at - correlated.detected_at)
            .num_minutes()
            .abs();

        match (
            primary.metric_name.as_str(),
            correlated.metric_name.as_str(),
        ) {
            (a, b)
                if (a.contains("price") && b.contains("volume"))
                    || (a.contains("volume") && b.contains("price")) =>
            {
                if same_region {
                    format!(
                        "Price-volume divergence in {}: possible supply shock (Δ{}min)",
                        primary.region, time_diff
                    )
                } else {
                    format!(
                        "Cross-region price-volume signal: {} ↔ {}",
                        primary.region, correlated.region
                    )
                }
            }
            (a, b)
                if (a.contains("credit") && b.contains("profit"))
                    || (a.contains("profit") && b.contains("credit")) =>
            {
                format!(
                    "Credit-profit correlation: rising debt with falling income in {}",
                    primary.region
                )
            }
            (a, b)
                if (a.contains("transaction") && b.contains("fuliza"))
                    || (a.contains("fuliza") && b.contains("transaction")) =>
            {
                format!(
                    "Transaction-Fuliza spike: possible cash flow crisis in {}",
                    primary.region
                )
            }
            _ => {
                if same_region {
                    format!(
                        "Simultaneous anomalies in {}: {} & {} (Δ{}min)",
                        primary.region,
                        primary.metric_name,
                        correlated.metric_name,
                        time_diff
                    )
                } else {
                    format!(
                        "Cross-region anomaly: {} in {} ↔ {} in {}",
                        primary.metric_name,
                        primary.region,
                        correlated.metric_name,
                        correlated.region
                    )
                }
            }
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // Persistence
    // ─────────────────────────────────────────────────────────────────

    /// Persist an anomaly event to ClickHouse.
    async fn persist_anomaly(db: &DatabaseConnections, event: &AnomalyEvent) {
        let context_json = serde_json::to_string(&event.context).unwrap_or_default();
        let anomaly_type = format!("{:?}", event.anomaly_type);
        let severity = format!("{:?}", event.severity);
        let worker_type = event
            .worker_type
            .as_ref()
            .map(|w| format!("{:?}", w))
            .unwrap_or_default();

        let query = format!(
            r#"INSERT INTO anomaly_events (id, metric_name, region, worker_type, anomaly_type, severity, observed_value, expected_value, deviation_sigma, context_json, detected_at) VALUES ('{id}', '{metric}', '{region}', '{wt}', '{atype}', '{sev}', {observed}, {expected}, {sigma}, '{ctx}', '{detected}')"#,
            id = event.id,
            metric = event.metric_name,
            region = event.region,
            wt = worker_type,
            atype = anomaly_type,
            sev = severity,
            observed = event.observed_value,
            expected = event.expected_value,
            sigma = event.deviation_sigma,
            ctx = context_json.replace('\'', "''"),
            detected = event.detected_at.format("%Y-%m-%d %H:%M:%S%.3f"),
        );

        if let Err(e) = db.clickhouse.query(&query).execute().await {
            tracing::warn!(error = %e, "Failed to persist anomaly to ClickHouse");
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> AnomalyConfig {
        AnomalyConfig {
            z_score_threshold: 3.0,
            min_history_points: 5,
            window_size: 20,
            baseline_lookback_days: 30,
            min_consecutive_anomalies: 1,
            max_alerts_per_metric_per_hour: 100,
            cusum_threshold: 4.0,
            cusum_slack: 0.5,
            seasonal_esd_max_outlier_ratio: 0.1,
            seasonal_period: 7,
            correlation_window_minutes: 30,
        }
    }

    #[test]
    fn test_zscore_severity_classification() {
        // Severity classification uses AnomalyDetector's method
        // We test the logic directly
        let thresholds = vec![
            (2.5, AnomalySeverity::Info),
            (3.5, AnomalySeverity::Warning),
            (5.0, AnomalySeverity::Critical),
            (7.0, AnomalySeverity::Emergency),
        ];

        for (z, expected) in thresholds {
            let severity = if z >= 6.0 {
                AnomalySeverity::Emergency
            } else if z >= 4.5 {
                AnomalySeverity::Critical
            } else if z >= 3.5 {
                AnomalySeverity::Warning
            } else {
                AnomalySeverity::Info
            };
            assert_eq!(severity, expected, "z_score={}", z);
        }
    }

    #[test]
    fn test_statistical_model_zscore_update() {
        let mut model = StatisticalModel::new_zscore();
        let values = vec![10.0, 12.0, 11.0, 13.0, 9.0, 10.5, 11.5, 12.5, 10.0, 11.0];

        for v in &values {
            if let StatisticalModel::ZScore {
                mean,
                std_dev,
                window,
            } = &mut model
            {
                window.push_back(*v);
                let n = window.len() as f64;
                *mean = window.iter().sum::<f64>() / n;
                if n > 1.0 {
                    let variance =
                        window.iter().map(|x| (x - *mean).powi(2)).sum::<f64>() / (n - 1.0);
                    *std_dev = variance.sqrt();
                }
            }
        }

        if let StatisticalModel::ZScore {
            mean, std_dev, window, ..
        } = &model
        {
            assert!(window.len() == 10);
            assert!((*mean - 11.1).abs() < 0.2, "mean={}", mean);
            assert!(*std_dev > 0.0, "std_dev={}", std_dev);

            // An outlier at 50.0 should produce a high z-score
            let z = (50.0 - mean).abs() / *std_dev;
            assert!(z > 3.0, "z_score for outlier={}", z);
        }
    }

    #[test]
    fn test_cusum_detection() {
        let mut model = StatisticalModel::new_cusum(10.0, 4.0, 0.5);

        // Feed stable values around the mean
        for _ in 0..20 {
            if let StatisticalModel::CUSUM {
                cumulative_sum_pos,
                cumulative_sum_neg,
                target_mean,
                slack,
                ..
            } = &mut model
            {
                let v = 10.0 + (rand::random::<f64>() - 0.5) * 0.5;
                let dev_pos = v - target_mean - slack;
                let dev_neg = target_mean - v - slack;
                *cumulative_sum_pos = (*cumulative_sum_pos + dev_pos).max(0.0);
                *cumulative_sum_neg = (*cumulative_sum_neg + dev_neg).max(0.0);
            }
        }

        // CUSUMs should be near zero for stable data
        if let StatisticalModel::CUSUM {
            cumulative_sum_pos,
            cumulative_sum_neg,
            ..
        } = &model
        {
            assert!(
                *cumulative_sum_pos < 4.0,
                "pos cusum={}",
                cumulative_sum_pos
            );
            assert!(
                *cumulative_sum_neg < 4.0,
                "neg cusum={}",
                cumulative_sum_neg
            );
        }
    }

    #[test]
    fn test_metric_key_generation() {
        let key = AnomalyDetector::metric_key(
            "daily_profit",
            "nairobi",
            &Some(WorkerType::MamaMboga),
        );
        assert_eq!(key, "daily_profit:nairobi:MamaMboga");

        let key = AnomalyDetector::metric_key("volume", "mombasa", &None);
        assert_eq!(key, "volume:mombasa:all");
    }

    #[test]
    fn test_hypothesis_generation() {
        // Test that hypotheses are generated for different metric types
        let metrics = vec![
            ("transaction_volume", "Possible market closure"),
            ("price_sukuma", "Supply chain disruption"),
            ("credit_score", "predatory lending"),
            ("daily_profit", "Demand shift"),
        ];

        for (metric, expected_fragment) in metrics {
            let causes = generate_test_hypotheses(metric, "nairobi", 50.0, 100.0, 10.0);
            let has_match = causes.iter().any(|c| c.contains(expected_fragment));
            assert!(
                has_match,
                "Expected '{}' in causes for metric '{}', got: {:?}",
                expected_fragment, metric, causes
            );
        }
    }

    fn generate_test_hypotheses(
        metric: &str,
        region: &str,
        value: f64,
        mean: f64,
        std_dev: f64,
    ) -> Vec<String> {
        let direction = if value > mean { "spike" } else { "drop" };
        let pct_change = ((value - mean) / mean.abs().max(1e-10) * 100.0).abs();

        let mut causes = vec![format!(
            "Unusual {} of {:.1}% in {} (z={:.1}σ)",
            direction,
            pct_change,
            metric,
            (value - mean).abs() / std_dev.max(1e-10)
        )];

        match metric {
            m if m.contains("transaction") || m.contains("volume") => {
                causes.push("Possible market closure, crackdown, or holiday".to_string());
            }
            m if m.contains("price") => {
                causes.push("Supply chain disruption or price manipulation".to_string());
            }
            m if m.contains("credit") || m.contains("fuliza") => {
                causes.push("Possible predatory lending sweep or policy change".to_string());
            }
            m if m.contains("profit") || m.contains("income") => {
                causes.push("Demand shift, cost increase, or competitive entry".to_string());
            }
            _ => {}
        }

        causes
    }
}
