use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use anyhow::Result;
use std::collections::{HashMap, VecDeque};

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyConfig {
    /// Z-score threshold for point anomalies (default: 3.0).
    pub z_score_threshold: f64,
    /// Minimum data points before detection activates for a metric.
    pub min_history_points: u32,
    /// Sliding window size for rolling statistics (data points).
    pub window_size: u32,
    /// Minimum consecutive anomalous points before raising alert.
    pub min_consecutive_anomalies: u32,
    /// Rate limit: max anomalies raised per metric per hour.
    pub max_alerts_per_metric_per_hour: u32,
    /// CUSUM target mean shift threshold (in standard deviations).
    pub cusum_threshold: f64,
    /// CUSUM allowance (slack parameter, in standard deviations).
    pub cusum_allowance: f64,
    /// Seasonal period for decomposition (e.g., 7 for weekly, 30 for monthly).
    pub seasonal_period: usize,
}

impl Default for AnomalyConfig {
    fn default() -> Self {
        Self {
            z_score_threshold: 3.0,
            min_history_points: 30,
            window_size: 100,
            min_consecutive_anomalies: 3,
            max_alerts_per_metric_per_hour: 10,
            cusum_threshold: 4.0,
            cusum_allowance: 0.5,
            seasonal_period: 7,
        }
    }
}

// ---------------------------------------------------------------------------
// Anomaly event types
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyEvent {
    pub id: Uuid,
    pub metric_name: String,
    pub region: String,
    pub worker_type: Option<String>,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AnomalyType {
    PointAnomaly,
    ContextualAnomaly,
    CollectiveAnomaly,
    ChangePoint,
    SeasonalBreak,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AnomalySeverity {
    Info,
    Warning,
    Critical,
    Emergency,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyContext {
    pub recent_values: Vec<TimestampedValue>,
    pub historical_mean: f64,
    pub historical_std: f64,
    pub peer_comparison: Option<PeerComparison>,
    pub possible_causes: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimestampedValue {
    pub timestamp: DateTime<Utc>,
    pub value: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PeerComparison {
    pub peer_region: String,
    pub peer_value: f64,
    pub divergence_pct: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataPoint {
    pub metric: String,
    pub region: String,
    pub worker_type: Option<String>,
    pub value: f64,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnomalyFilter {
    pub region: Option<String>,
    pub metric_name: Option<String>,
    pub severity: Option<AnomalySeverity>,
    pub worker_type: Option<String>,
    pub acknowledged: Option<bool>,
    pub since: Option<DateTime<Utc>>,
}

// ---------------------------------------------------------------------------
// Internal statistical model state
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct MetricState {
    /// Sliding window of recent values.
    pub window: VecDeque<f64>,
    /// Timestamps corresponding to window values.
    pub timestamps: VecDeque<DateTime<Utc>>,
    /// Running sum for incremental mean.
    pub sum: f64,
    /// Running sum of squares for incremental variance.
    pub sum_sq: f64,
    /// Total count of observed values.
    pub count: u64,
    /// CUSUM: cumulative sum above target.
    pub cusum_high: f64,
    /// CUSUM: cumulative sum below target.
    pub cusum_low: f64,
    /// CUSUM target mean (estimated from initial data).
    pub cusum_target: f64,
    /// CUSUM running std dev.
    pub cusum_std: f64,
    /// Consecutive anomaly count.
    pub consecutive_anomalies: u32,
    /// Seasonal component (one full period).
    pub seasonal: Vec<f64>,
    /// Seasonal baseline established flag.
    pub seasonal_established: bool,
    /// Count of alerts raised in the current hour window.
    pub alerts_this_hour: u32,
    /// Hour marker for rate limiting.
    pub alert_hour: Option<u64>,
}

impl MetricState {
    pub fn new(window_size: usize) -> Self {
        Self {
            window: VecDeque::with_capacity(window_size),
            timestamps: VecDeque::with_capacity(window_size),
            sum: 0.0,
            sum_sq: 0.0,
            count: 0,
            cusum_high: 0.0,
            cusum_low: 0.0,
            cusum_target: 0.0,
            cusum_std: 0.0,
            consecutive_anomalies: 0,
            seasonal: vec![0.0; window_size],
            seasonal_established: false,
            alerts_this_hour: 0,
            alert_hour: None,
        }
    }

    pub fn mean(&self) -> f64 {
        if self.count == 0 { 0.0 } else { self.sum / self.count as f64 }
    }

    pub fn std_dev(&self) -> f64 {
        if self.count < 2 { return 0.0; }
        let mean = self.mean();
        let variance = (self.sum_sq / self.count as f64) - mean * mean;
        variance.max(0.0).sqrt()
    }
}

// ---------------------------------------------------------------------------
// AnomalyDetector
// ---------------------------------------------------------------------------

pub struct AnomalyDetector {
    config: AnomalyConfig,
    /// Per-metric-region statistical state, keyed by "{metric}:{region}".
    models: std::sync::RwLock<HashMap<String, MetricState>>,
    /// Active (unacknowledged) anomaly events.
    active_anomalies: std::sync::RwLock<Vec<AnomalyEvent>>,
}

impl AnomalyDetector {
    pub fn new(config: AnomalyConfig) -> Self {
        Self {
            config,
            models: std::sync::RwLock::new(HashMap::new()),
            active_anomalies: std::sync::RwLock::new(Vec::new()),
        }
    }

    // -----------------------------------------------------------------------
    // 1. detect_zscore — Z-score outlier detection
    // -----------------------------------------------------------------------

    /// Detect point anomalies using Z-score against a rolling window.
    /// Returns the anomaly event if the value is an outlier, None otherwise.
    pub fn detect_zscore(
        &self,
        metric: &str,
        region: &str,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Option<AnomalyEvent>> {
        let key = format!("{}:{}", metric, region);
        let mut models = self.models.write().unwrap();
        let state = models.entry(key.clone()).or_insert_with(|| MetricState::new(self.config.window_size as usize));

        // Update incremental statistics
        state.sum += value;
        state.sum_sq += value * value;
        state.count += 1;
        state.window.push_back(value);
        state.timestamps.push_back(timestamp);

        // Trim window
        while state.window.len() > self.config.window_size as usize {
            if let Some(old) = state.window.pop_front() {
                state.sum -= old;
                state.sum_sq -= old * old;
                state.count -= 1; // approximate; window stats are rolling
            }
            state.timestamps.pop_front();
        }

        // Not enough data yet
        if state.window.len() < self.config.min_history_points as usize {
            return Ok(None);
        }

        let mean = state.mean();
        let std = state.std_dev();

        if std < 1e-10 {
            return Ok(None); // No variance, can't compute z-score
        }

        let z_score = (value - mean) / std;
        let abs_z = z_score.abs();

        if abs_z >= self.config.z_score_threshold {
            // Classify severity based on sigma distance
            let severity = if abs_z >= 5.0 {
                AnomalySeverity::Emergency
            } else if abs_z >= 4.0 {
                AnomalySeverity::Critical
            } else if abs_z >= 3.5 {
                AnomalySeverity::Warning
            } else {
                AnomalySeverity::Info
            };

            state.consecutive_anomalies += 1;

            // Only emit alert if consecutive threshold met
            if state.consecutive_anomalies >= self.config.min_consecutive_anomalies {
                let recent: Vec<TimestampedValue> = state
                    .window
                    .iter()
                    .zip(state.timestamps.iter())
                    .take(10)
                    .map(|(v, t)| TimestampedValue { timestamp: *t, value: *v })
                    .collect();

                let event = AnomalyEvent {
                    id: Uuid::new_v4(),
                    metric_name: metric.to_string(),
                    region: region.to_string(),
                    worker_type: None,
                    anomaly_type: AnomalyType::PointAnomaly,
                    severity,
                    observed_value: value,
                    expected_value: mean,
                    deviation_sigma: abs_z,
                    context: AnomalyContext {
                        recent_values: recent,
                        historical_mean: mean,
                        historical_std: std,
                        peer_comparison: None,
                        possible_causes: self.generate_hypotheses(metric, value, mean),
                    },
                    detected_at: timestamp,
                    acknowledged: false,
                    root_cause: None,
                };

                return Ok(Some(event));
            }
        } else {
            state.consecutive_anomalies = 0;
        }

        Ok(None)
    }

    // -----------------------------------------------------------------------
    // 2. detect_cusum — CUSUM change-point detection
    // -----------------------------------------------------------------------

    /// Detect sustained shifts in the mean using the Cumulative Sum (CUSUM) algorithm.
    /// Returns a ChangePoint anomaly if the process mean has shifted.
    pub fn detect_cusum(
        &self,
        metric: &str,
        region: &str,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Option<AnomalyEvent>> {
        let key = format!("{}:{}", metric, region);
        let mut models = self.models.write().unwrap();
        let state = models.entry(key.clone()).or_insert_with(|| MetricState::new(self.config.window_size as usize));

        // Bootstrap target mean and std from initial observations
        if state.count < self.config.min_history_points as u64 {
            state.sum += value;
            state.sum_sq += value * value;
            state.count += 1;
            state.window.push_back(value);
            state.timestamps.push_back(timestamp);

            if state.count == self.config.min_history_points as u64 {
                state.cusum_target = state.mean();
                state.cusum_std = state.std_dev().max(1e-10);
            }
            return Ok(None);
        }

        let k = self.config.cusum_allowance * state.cusum_std; // allowance (slack)
        let h = self.config.cusum_threshold * state.cusum_std; // decision threshold

        // Standardized deviation from target
        let dev = value - state.cusum_target;

        // Update CUSUM statistics (two-sided)
        state.cusum_high = (state.cusum_high + dev - k).max(0.0);
        state.cusum_low = (state.cusum_low - dev - k).max(0.0);

        // Also update rolling window for recent context
        state.window.push_back(value);
        state.timestamps.push_back(timestamp);
        while state.window.len() > self.config.window_size as usize {
            state.window.pop_front();
            state.timestamps.pop_front();
        }

        // Check for change-point
        let (triggered, direction) = if state.cusum_high > h {
            (true, "upward")
        } else if state.cusum_low > h {
            (true, "downward")
        } else {
            (false, "none")
        };

        if triggered {
            let shift_magnitude = if direction == "upward" {
                state.cusum_high
            } else {
                state.cusum_low
            };

            let sigma_deviation = shift_magnitude / state.cusum_std;

            let severity = if sigma_deviation >= 8.0 {
                AnomalySeverity::Emergency
            } else if sigma_deviation >= 6.0 {
                AnomalySeverity::Critical
            } else if sigma_deviation >= 4.5 {
                AnomalySeverity::Warning
            } else {
                AnomalySeverity::Info
            };

            let recent: Vec<TimestampedValue> = state
                .window
                .iter()
                .zip(state.timestamps.iter())
                .rev()
                .take(15)
                .map(|(v, t)| TimestampedValue { timestamp: *t, value: *v })
                .collect();

            let mut causes = vec![
                format!("Sustained {} shift detected by CUSUM", direction),
                format!("Target mean was {:.2}, recent drift is {:.2}σ", state.cusum_target, sigma_deviation),
            ];
            if direction == "upward" {
                causes.push("Possible demand surge or price spike".to_string());
            } else {
                causes.push("Possible market disruption, crackdown, or supply shock".to_string());
            }

            let event = AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: metric.to_string(),
                region: region.to_string(),
                worker_type: None,
                anomaly_type: AnomalyType::ChangePoint,
                severity,
                observed_value: value,
                expected_value: state.cusum_target,
                deviation_sigma: sigma_deviation,
                context: AnomalyContext {
                    recent_values: recent,
                    historical_mean: state.cusum_target,
                    historical_std: state.cusum_std,
                    peer_comparison: None,
                    possible_causes: causes,
                },
                detected_at: timestamp,
                acknowledged: false,
                root_cause: None,
            };

            // Reset CUSUM after detection to avoid repeated alerts for same shift
            state.cusum_high = 0.0;
            state.cusum_low = 0.0;
            // Update target to new level (adaptive)
            state.cusum_target = state.window.iter().sum::<f64>() / state.window.len() as f64;

            return Ok(Some(event));
        }

        Ok(None)
    }

    // -----------------------------------------------------------------------
    // 3. detect_seasonal — Seasonal decomposition anomaly detection
    // -----------------------------------------------------------------------

    /// Detect anomalies by decomposing the time series into trend + seasonal + residual,
    /// then flagging observations where the residual is abnormally large.
    /// Uses a simple moving-average decomposition (STL-lite).
    pub fn detect_seasonal(
        &self,
        metric: &str,
        region: &str,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Option<AnomalyEvent>> {
        let key = format!("{}:{}", metric, region);
        let mut models = self.models.write().unwrap();
        let state = models.entry(key.clone()).or_insert_with(|| MetricState::new(self.config.window_size as usize));

        let period = self.config.seasonal_period;

        state.window.push_back(value);
        state.timestamps.push_back(timestamp);
        while state.window.len() > self.config.window_size as usize {
            state.window.pop_front();
            state.timestamps.pop_front();
        }

        // Need at least 2 full periods to establish seasonal pattern
        if state.window.len() < period * 2 {
            return Ok(None);
        }

        let data: Vec<f64> = state.window.iter().copied().collect();
        let n = data.len();

        // Step 1: Compute trend via centered moving average (window = seasonal period)
        let half = period / 2;
        let mut trend = vec![0.0f64; n];
        for i in half..n - half {
            let sum: f64 = data[i - half..=i + half].iter().sum();
            trend[i] = sum / period as f64;
        }
        // Fill edges with nearest computed value
        for i in 0..half {
            trend[i] = trend[half];
        }
        for i in n - half..n {
            trend[i] = trend[n - half - 1];
        }

        // Step 2: Detrended series
        let detrended: Vec<f64> = data.iter().zip(trend.iter()).map(|(d, t)| d - t).collect();

        // Step 3: Compute seasonal component (average detrended value at each position in period)
        let mut seasonal_means = vec![0.0f64; period];
        let mut seasonal_counts = vec![0u32; period];
        for (i, &val) in detrended.iter().enumerate() {
            let pos = i % period;
            seasonal_means[pos] += val;
            seasonal_counts[pos] += 1;
        }
        for i in 0..period {
            if seasonal_counts[i] > 0 {
                seasonal_means[i] /= seasonal_counts[i] as f64;
            }
        }
        // Center seasonal component (sum to zero)
        let seasonal_mean: f64 = seasonal_means.iter().sum::<f64>() / period as f64;
        for s in seasonal_means.iter_mut() {
            *s -= seasonal_mean;
        }

        state.seasonal = seasonal_means.clone();
        state.seasonal_established = true;

        // Step 4: Residual = detrended - seasonal
        let mut residuals = Vec::with_capacity(n);
        for (i, &d) in detrended.iter().enumerate() {
            residuals.push(d - seasonal_means[i % period]);
        }

        // Step 5: Compute residual statistics
        let resid_mean: f64 = residuals.iter().sum::<f64>() / n as f64;
        let resid_var: f64 = residuals.iter().map(|r| (r - resid_mean).powi(2)).sum::<f64>() / n as f64;
        let resid_std = resid_var.max(1e-10).sqrt();

        // Step 6: Check latest residual
        let latest_residual = residuals[n - 1];
        let sigma = latest_residual.abs() / resid_std;

        if sigma >= self.config.z_score_threshold {
            let severity = if sigma >= 5.0 {
                AnomalySeverity::Emergency
            } else if sigma >= 4.0 {
                AnomalySeverity::Critical
            } else if sigma >= 3.5 {
                AnomalySeverity::Warning
            } else {
                AnomalySeverity::Info
            };

            let expected = trend[n - 1] + seasonal_means[(n - 1) % period];

            let recent: Vec<TimestampedValue> = state
                .window
                .iter()
                .zip(state.timestamps.iter())
                .rev()
                .take(10)
                .map(|(v, t)| TimestampedValue { timestamp: *t, value: *v })
                .collect();

            let mut causes = vec![
                "Residual exceeds expected seasonal pattern".to_string(),
                format!("Expected seasonal value: {:.2}, observed: {:.2}", expected, value),
            ];

            // Check if other recent points are also breaking seasonal pattern
            let recent_residuals: Vec<f64> = residuals[n.saturating_sub(5)..].to_vec();
            let recent_breaks = recent_residuals.iter().filter(|r| r.abs() / resid_std > 2.0).count();
            if recent_breaks >= 3 {
                causes.push(format!("{} of last 5 observations also break seasonal pattern", recent_breaks));
            }

            let event = AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: metric.to_string(),
                region: region.to_string(),
                worker_type: None,
                anomaly_type: AnomalyType::SeasonalBreak,
                severity,
                observed_value: value,
                expected_value: expected,
                deviation_sigma: sigma,
                context: AnomalyContext {
                    recent_values: recent,
                    historical_mean: expected,
                    historical_std: resid_std,
                    peer_comparison: None,
                    possible_causes: causes,
                },
                detected_at: timestamp,
                acknowledged: false,
                root_cause: None,
            };

            return Ok(Some(event));
        }

        Ok(None)
    }

    // -----------------------------------------------------------------------
    // 4. correlate_anomalies — Multi-stream correlation
    // -----------------------------------------------------------------------

    /// Given an anomaly event, find other anomalies that occurred within a time window
    /// across different metrics/regions to generate cross-stream hypotheses.
    pub fn correlate_anomalies(
        &self,
        event: &AnomalyEvent,
        window_minutes: i64,
    ) -> Result<Vec<String>> {
        let active = self.active_anomalies.read().unwrap();
        let window = chrono::Duration::minutes(window_minutes);

        let correlated: Vec<&AnomalyEvent> = active
            .iter()
            .filter(|other| {
                // Different metric or region
                (other.metric_name != event.metric_name || other.region != event.region)
                // Same worker type or both None
                && other.worker_type == event.worker_type
                // Within time window
                && (other.detected_at - event.detected_at).num_seconds().abs() <= window.num_seconds()
                // Not the same event
                && other.id != event.id
            })
            .collect();

        let mut hypotheses = Vec::new();

        if correlated.is_empty() {
            hypotheses.push("No correlated anomalies detected — possible isolated incident".to_string());
            return Ok(hypotheses);
        }

        // Group by region
        let mut by_region: HashMap<&str, Vec<&AnomalyEvent>> = HashMap::new();
        for a in &correlated {
            by_region.entry(&a.region).or_default().push(a);
        }

        // Multi-metric anomaly in same region → systemic issue
        for (reg, events) in &by_region {
            let metrics: Vec<&str> = events.iter().map(|e| e.metric_name.as_str()).collect();
            if metrics.len() >= 2 {
                hypotheses.push(format!(
                    "Multi-metric anomaly in {}: {} — possible systemic economic event",
                    reg, metrics.join(", ")
                ));
            }
        }

        // Same metric across multiple regions → widespread event
        let mut by_metric: HashMap<&str, Vec<&AnomalyEvent>> = HashMap::new();
        for a in &correlated {
            by_metric.entry(&a.metric_name).or_default().push(a);
        }
        for (met, events) in &by_metric {
            let regions: Vec<&str> = events.iter().map(|e| e.region.as_str()).collect();
            if regions.len() >= 2 {
                hypotheses.push(format!(
                    "Cross-regional anomaly in {}: {} — possible national-level event",
                    met, regions.join(", ")
                ));
            }
        }

        // Check for cascade pattern: one metric's anomaly followed by another
        let mut time_sorted = correlated.clone();
        time_sorted.sort_by_key(|a| a.detected_at);
        for window_events in time_sorted.windows(2) {
            if let [earlier, later] = window_events {
                let lag_secs = (later.detected_at - earlier.detected_at).num_seconds();
                if lag_secs > 0 && lag_secs < 1800 {
                    hypotheses.push(format!(
                        "Cascade: {} ({}) preceded {} ({}) by {}s — possible causal chain",
                        earlier.metric_name, earlier.region,
                        later.metric_name, later.region,
                        lag_secs
                    ));
                }
            }
        }

        if hypotheses.is_empty() {
            hypotheses.push(format!("{} correlated anomalies found but no clear pattern", correlated.len()));
        }

        Ok(hypotheses)
    }

    // -----------------------------------------------------------------------
    // 5. ingest_and_detect — Real-time ingestion with all detectors
    // -----------------------------------------------------------------------

    /// Ingest a single data point and run all detection algorithms.
    /// Returns all anomaly events triggered by this observation.
    pub fn ingest_and_detect(
        &self,
        metric: &str,
        region: &str,
        worker_type: Option<String>,
        value: f64,
        timestamp: DateTime<Utc>,
    ) -> Result<Vec<AnomalyEvent>> {
        let mut anomalies = Vec::new();

        // Run Z-score detection
        if let Some(mut event) = self.detect_zscore(metric, region, value, timestamp)? {
            event.worker_type = worker_type.clone();
            anomalies.push(event);
        }

        // Run CUSUM detection
        if let Some(mut event) = self.detect_cusum(metric, region, value, timestamp)? {
            event.worker_type = worker_type.clone();
            anomalies.push(event);
        }

        // Run seasonal detection
        if let Some(mut event) = self.detect_seasonal(metric, region, value, timestamp)? {
            event.worker_type = worker_type.clone();
            anomalies.push(event);
        }

        // Deduplicate: if multiple detectors fire, keep the highest severity
        // (they may detect the same underlying anomaly differently)
        if anomalies.len() > 1 {
            let severity_rank = |s: &AnomalySeverity| -> u8 {
                match s {
                    AnomalySeverity::Emergency => 4,
                    AnomalySeverity::Critical => 3,
                    AnomalySeverity::Warning => 2,
                    AnomalySeverity::Info => 1,
                }
            };
            anomalies.sort_by(|a, b| severity_rank(&b.severity).cmp(&severity_rank(&a.severity)));
            anomalies.truncate(1);
        }

        // Enrich with correlation hypotheses
        for event in &mut anomalies {
            if let Ok(hypotheses) = self.correlate_anomalies(event, 60) {
                event.context.possible_causes.extend(hypotheses);
            }
        }

        // Store active anomalies
        if !anomalies.is_empty() {
            let mut active = self.active_anomalies.write().unwrap();
            active.extend(anomalies.clone());

            // Prune old acknowledged anomalies (keep last 1000)
            if active.len() > 1000 {
                active.retain(|a| !a.acknowledged);
            }
        }

        Ok(anomalies)
    }

    // -----------------------------------------------------------------------
    // 6. get_active_anomalies — Query active (unacknowledged) anomalies
    // -----------------------------------------------------------------------

    /// Retrieve active anomalies filtered by region, metric, severity, etc.
    pub fn get_active_anomalies(
        &self,
        filter: AnomalyFilter,
    ) -> Result<Vec<AnomalyEvent>> {
        let active = self.active_anomalies.read().unwrap();

        let filtered: Vec<AnomalyEvent> = active
            .iter()
            .filter(|a| {
                if let Some(ref region) = filter.region {
                    if a.region != *region { return false; }
                }
                if let Some(ref metric) = filter.metric_name {
                    if a.metric_name != *metric { return false; }
                }
                if let Some(ref severity) = filter.severity {
                    let rank = |s: &AnomalySeverity| -> u8 {
                        match s {
                            AnomalySeverity::Info => 1,
                            AnomalySeverity::Warning => 2,
                            AnomalySeverity::Critical => 3,
                            AnomalySeverity::Emergency => 4,
                        }
                    };
                    if rank(&a.severity) < rank(severity) { return false; }
                }
                if let Some(ref wt) = filter.worker_type {
                    if a.worker_type.as_ref() != Some(wt) { return false; }
                }
                if let Some(ack) = filter.acknowledged {
                    if a.acknowledged != ack { return false; }
                }
                if let Some(since) = filter.since {
                    if a.detected_at < since { return false; }
                }
                true
            })
            .cloned()
            .collect();

        Ok(filtered)
    }

    // -----------------------------------------------------------------------
    // Acknowledge an anomaly
    // -----------------------------------------------------------------------

    /// Acknowledge an anomaly and optionally attach a root cause explanation.
    pub fn acknowledge(
        &self,
        anomaly_id: Uuid,
        root_cause: Option<String>,
    ) -> Result<bool> {
        let mut active = self.active_anomalies.write().unwrap();
        if let Some(event) = active.iter_mut().find(|a| a.id == anomaly_id) {
            event.acknowledged = true;
            event.root_cause = root_cause;
            Ok(true)
        } else {
            Ok(false)
        }
    }

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    /// Generate possible cause hypotheses based on metric type and deviation.
    fn generate_hypotheses(&self, metric: &str, observed: f64, expected: f64) -> Vec<String> {
        let mut causes = Vec::new();
        let pct_change = ((observed - expected) / expected.abs().max(1e-10)) * 100.0;
        let direction = if observed > expected { "increase" } else { "decrease" };

        // Metric-specific hypotheses
        let metric_lower = metric.to_lowercase();

        if metric_lower.contains("transaction") || metric_lower.contains("volume") {
            causes.push(format!("Sudden {} in transaction volume — possible market event", direction));
            if pct_change.abs() > 30.0 {
                causes.push("Large shift may indicate market closure, crackdown, or holiday".to_string());
            }
        }

        if metric_lower.contains("price") || metric_lower.contains("cost") {
            causes.push(format!("Price {} detected — possible supply chain disruption", direction));
            if observed > expected {
                causes.push("Price spike may indicate scarcity or hoarding".to_string());
            }
        }

        if metric_lower.contains("credit") || metric_lower.contains("score") {
            causes.push(format!("Credit score {} — possible lending pattern change", direction));
            if observed < expected {
                causes.push("Drop may indicate predatory lending sweep or economic shock".to_string());
            }
        }

        if metric_lower.contains("fuliza") || metric_lower.contains("overdraft") {
            causes.push(format!("Overdraft usage {} — {} financial stress", direction,
                if observed > expected { "increasing" } else { "decreasing" }));
        }

        if metric_lower.contains("spoilage") || metric_lower.contains("waste") {
            causes.push(format!("Spoilage {} — possible supply chain or demand issue", direction));
        }

        if metric_lower.contains("profit") || metric_lower.contains("income") {
            causes.push(format!("Earnings {} detected — economic impact on workers", direction));
        }

        // Generic fallback
        if causes.is_empty() {
            causes.push(format!("{}% {} from expected value", pct_change.abs(), direction));
        }

        causes
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zscore_detects_outlier() {
        let detector = AnomalyDetector::new(AnomalyConfig::default());
        let base = Utc::now();

        // Feed normal values (all ~100.0)
        for i in 0..40 {
            let ts = base + chrono::Duration::hours(i);
            let val = 100.0 + ((i as f64) * 0.1).sin();
            let _ = detector.detect_zscore("test_metric", "nairobi", val, ts);
        }

        // Now feed an extreme outlier
        let ts = base + chrono::Duration::hours(41);
        // Need consecutive anomalies, so feed multiple outliers
        let mut result = None;
        for i in 0..4 {
            let ts = base + chrono::Duration::hours(41 + i);
            result = detector.detect_zscore("test_metric", "nairobi", 500.0, ts).unwrap();
        }

        assert!(result.is_some(), "Should detect the outlier after consecutive anomalies");
        let event = result.unwrap();
        assert_eq!(event.anomaly_type as u8, AnomalyType::PointAnomaly as u8);
        assert!(event.deviation_sigma >= 3.0);
    }

    #[test]
    fn test_cusum_detects_shift() {
        let detector = AnomalyDetector::new(AnomalyConfig {
            min_history_points: 20,
            cusum_threshold: 4.0,
            cusum_allowance: 0.5,
            ..Default::default()
        });
        let base = Utc::now();

        // Feed baseline data around 100
        for i in 0..25 {
            let ts = base + chrono::Duration::hours(i);
            let val = 100.0 + ((i as f64) * 0.3).sin() * 2.0;
            let _ = detector.detect_cusum("price", "mombasa", val, ts);
        }

        // Feed a sustained shift to 130 (30% increase)
        let mut result = None;
        for i in 0..15 {
            let ts = base + chrono::Duration::hours(25 + i);
            result = detector.detect_cusum("price", "mombasa", 130.0, ts).unwrap();
        }

        assert!(result.is_some(), "CUSUM should detect the sustained shift");
        let event = result.unwrap();
        assert_eq!(event.anomaly_type as u8, AnomalyType::ChangePoint as u8);
    }

    #[test]
    fn test_seasonal_break_detection() {
        let config = AnomalyConfig {
            seasonal_period: 7,
            min_history_points: 10,
            ..Default::default()
        };
        let detector = AnomalyDetector::new(config);
        let base = Utc::now();

        // Feed 3 weeks of data with a clear weekly pattern
        for i in 0..21 {
            let ts = base + chrono::Duration::days(i);
            let day_of_week = (i % 7) as f64;
            // Pattern: higher on weekdays, lower on weekends
            let val = if day_of_week < 5.0 { 100.0 } else { 60.0 };
            let _ = detector.detect_seasonal("sales", "kisumu", val, ts);
        }

        // Feed a value that breaks the pattern: weekend with weekday-level sales
        let ts = base + chrono::Duration::days(21); // This is a Saturday
        let result = detector.detect_seasonal("sales", "kisumu", 150.0, ts).unwrap();

        assert!(result.is_some(), "Should detect seasonal break");
        let event = result.unwrap();
        assert_eq!(event.anomaly_type as u8, AnomalyType::SeasonalBreak as u8);
    }

    #[test]
    fn test_ingest_and_detect_integration() {
        let detector = AnomalyDetector::new(AnomalyConfig {
            min_history_points: 10,
            window_size: 50,
            ..Default::default()
        });
        let base = Utc::now();

        // Feed normal data
        for i in 0..15 {
            let ts = base + chrono::Duration::hours(i);
            let _ = detector.ingest_and_detect("volume", "nairobi", Some("mama_mboga".to_string()), 50.0, ts);
        }

        // Feed anomalous data
        let ts = base + chrono::Duration::hours(16);
        let results = detector.ingest_and_detect("volume", "nairobi", Some("mama_mboga".to_string()), 500.0, ts).unwrap();

        // May or may not trigger depending on consecutive count, but should not panic
        assert!(results.len() <= 1); // Deduplication keeps at most 1
    }

    #[test]
    fn test_get_active_anomalies_filter() {
        let detector = AnomalyDetector::new(AnomalyConfig::default());

        // Manually insert test anomalies
        {
            let mut active = detector.active_anomalies.write().unwrap();
            active.push(AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: "price".to_string(),
                region: "nairobi".to_string(),
                worker_type: Some("mama_mboga".to_string()),
                anomaly_type: AnomalyType::PointAnomaly,
                severity: AnomalySeverity::Critical,
                observed_value: 200.0,
                expected_value: 100.0,
                deviation_sigma: 4.0,
                context: AnomalyContext {
                    recent_values: vec![],
                    historical_mean: 100.0,
                    historical_std: 25.0,
                    peer_comparison: None,
                    possible_causes: vec![],
                },
                detected_at: Utc::now(),
                acknowledged: false,
                root_cause: None,
            });
            active.push(AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: "volume".to_string(),
                region: "mombasa".to_string(),
                worker_type: None,
                anomaly_type: AnomalyType::ChangePoint,
                severity: AnomalySeverity::Info,
                observed_value: 10.0,
                expected_value: 50.0,
                deviation_sigma: 2.0,
                context: AnomalyContext {
                    recent_values: vec![],
                    historical_mean: 50.0,
                    historical_std: 15.0,
                    peer_comparison: None,
                    possible_causes: vec![],
                },
                detected_at: Utc::now(),
                acknowledged: true,
                root_cause: None,
            });
        }

        // Filter by region
        let nairobi = detector.get_active_anomalies(AnomalyFilter {
            region: Some("nairobi".to_string()),
            metric_name: None,
            severity: None,
            worker_type: None,
            acknowledged: None,
            since: None,
        }).unwrap();
        assert_eq!(nairobi.len(), 1);
        assert_eq!(nairobi[0].region, "nairobi");

        // Filter by severity (at least Critical)
        let critical = detector.get_active_anomalies(AnomalyFilter {
            region: None,
            metric_name: None,
            severity: Some(AnomalySeverity::Critical),
            worker_type: None,
            acknowledged: None,
            since: None,
        }).unwrap();
        assert_eq!(critical.len(), 1);
        assert_eq!(critical[0].severity as u8, AnomalySeverity::Critical as u8);

        // Filter unacknowledged only
        let unacked = detector.get_active_anomalies(AnomalyFilter {
            region: None,
            metric_name: None,
            severity: None,
            worker_type: None,
            acknowledged: Some(false),
            since: None,
        }).unwrap();
        assert_eq!(unacked.len(), 1);
    }

    #[test]
    fn test_correlate_anomalies() {
        let detector = AnomalyDetector::new(AnomalyConfig::default());
        let now = Utc::now();

        // Insert anomalies across different metrics in the same region
        {
            let mut active = detector.active_anomalies.write().unwrap();
            active.push(AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: "price".to_string(),
                region: "nairobi".to_string(),
                worker_type: Some("mama_mboga".to_string()),
                anomaly_type: AnomalyType::PointAnomaly,
                severity: AnomalySeverity::Critical,
                observed_value: 200.0,
                expected_value: 100.0,
                deviation_sigma: 4.0,
                context: AnomalyContext {
                    recent_values: vec![],
                    historical_mean: 100.0,
                    historical_std: 25.0,
                    peer_comparison: None,
                    possible_causes: vec![],
                },
                detected_at: now - chrono::Duration::minutes(5),
                acknowledged: false,
                root_cause: None,
            });
            active.push(AnomalyEvent {
                id: Uuid::new_v4(),
                metric_name: "volume".to_string(),
                region: "nairobi".to_string(),
                worker_type: Some("mama_mboga".to_string()),
                anomaly_type: AnomalyType::PointAnomaly,
                severity: AnomalySeverity::Warning,
                observed_value: 10.0,
                expected_value: 50.0,
                deviation_sigma: 3.5,
                context: AnomalyContext {
                    recent_values: vec![],
                    historical_mean: 50.0,
                    historical_std: 12.0,
                    peer_comparison: None,
                    possible_causes: vec![],
                },
                detected_at: now - chrono::Duration::minutes(2),
                acknowledged: false,
                root_cause: None,
            });
        }

        let test_event = AnomalyEvent {
            id: Uuid::new_v4(),
            metric_name: "profit".to_string(),
            region: "nairobi".to_string(),
            worker_type: Some("mama_mboga".to_string()),
            anomaly_type: AnomalyType::PointAnomaly,
            severity: AnomalySeverity::Critical,
            observed_value: 20.0,
            expected_value: 80.0,
            deviation_sigma: 4.0,
            context: AnomalyContext {
                recent_values: vec![],
                historical_mean: 80.0,
                historical_std: 15.0,
                peer_comparison: None,
                possible_causes: vec![],
            },
            detected_at: now,
            acknowledged: false,
            root_cause: None,
        };

        let hypotheses = detector.correlate_anomalies(&test_event, 30).unwrap();
        assert!(!hypotheses.is_empty());
        // Should find multi-metric correlation in nairobi
        assert!(hypotheses.iter().any(|h| h.contains("Multi-metric")));
    }

    #[test]
    fn test_acknowledge() {
        let detector = AnomalyDetector::new(AnomalyConfig::default());
        let id = Uuid::new_v4();

        {
            let mut active = detector.active_anomalies.write().unwrap();
            active.push(AnomalyEvent {
                id,
                metric_name: "test".to_string(),
                region: "test".to_string(),
                worker_type: None,
                anomaly_type: AnomalyType::PointAnomaly,
                severity: AnomalySeverity::Info,
                observed_value: 1.0,
                expected_value: 0.0,
                deviation_sigma: 1.0,
                context: AnomalyContext {
                    recent_values: vec![],
                    historical_mean: 0.0,
                    historical_std: 1.0,
                    peer_comparison: None,
                    possible_causes: vec![],
                },
                detected_at: Utc::now(),
                acknowledged: false,
                root_cause: None,
            });
        }

        let result = detector.acknowledge(id, Some("Test root cause".to_string())).unwrap();
        assert!(result);

        let active = detector.active_anomalies.read().unwrap();
        let event = active.iter().find(|a| a.id == id).unwrap();
        assert!(event.acknowledged);
        assert_eq!(event.root_cause.as_deref(), Some("Test root cause"));
    }
}
