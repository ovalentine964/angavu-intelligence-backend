use uuid::Uuid;
// Data Pipeline Feedback Loops
// Each pipeline stage feeds back: error signals, quality metrics, adjustment parameters

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};
use tracing::{info, warn};

// ─── Pipeline Stage ───────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum PipelineStage {
    /// Device → Backend sync receiver
    SyncReceiver,
    /// Data validation layer
    Validator,
    /// Aggregation engine
    Aggregator,
    /// Pattern analysis
    Analyzer,
    /// Intelligence generation
    Intelligence,
    /// Federated learning
    FederatedLearning,
}

// ─── Feedback Signal ──────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeedbackSignal {
    pub signal_id: String,
    pub source_stage: PipelineStage,
    pub target_stage: PipelineStage,
    pub signal_type: FeedbackType,
    pub severity: Severity,
    pub data: serde_json::Value,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum FeedbackType {
    /// Error that should be reported back to the source
    ErrorSignal,
    /// Quality metric for the stage's output
    QualityMetric,
    /// Parameter adjustment recommendation
    ParameterAdjustment,
    /// Priority signal (increase/decrease processing priority)
    PriorityChange,
    /// Data collection focus change
    CollectionFocus,
    /// Model performance feedback
    ModelFeedback,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, PartialOrd)]
pub enum Severity {
    Info,
    Warning,
    Error,
    Critical,
}

// ─── Stage Quality Metrics ────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StageMetrics {
    pub stage: PipelineStage,
    pub throughput_per_hour: u64,
    pub error_rate: f64,
    pub avg_latency_ms: f64,
    pub quality_score: f64, // 0.0 - 1.0
    pub last_updated: DateTime<Utc>,
}

impl StageMetrics {
    pub fn new(stage: PipelineStage) -> Self {
        Self {
            stage,
            throughput_per_hour: 0,
            error_rate: 0.0,
            avg_latency_ms: 0.0,
            quality_score: 1.0,
            last_updated: Utc::now(),
        }
    }
}

// ─── Error Signal (Device Feedback) ───────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceErrorSignal {
    pub device_id: String,
    pub errors: Vec<String>,
    pub severity: Severity,
    pub suggested_fix: Option<String>,
    pub timestamp: DateTime<Utc>,
}

// ─── Aggregation Adjustment ───────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AggregationAdjustment {
    pub parameter: String,
    pub old_value: f64,
    pub new_value: f64,
    pub reason: String,
    pub confidence: f64,
}

// ─── Data Collection Priority ─────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CollectionPriority {
    pub region: String,
    pub product_category: String,
    pub priority_score: f64, // 0.0 = low, 1.0 = high
    pub reason: String,
}

// ─── Pipeline Feedback Channel ────────────────────────────────────────────

/// Central feedback channel connecting all pipeline stages.
/// Each stage can send feedback signals to any other stage.
/// Signals are processed asynchronously and don't block the pipeline.
pub struct PipelineFeedbackChannel {
    /// Per-stage feedback receivers
    receivers: RwLock<HashMap<PipelineStage, mpsc::Receiver<FeedbackSignal>>>,
    /// Per-stage feedback senders
    senders: RwLock<HashMap<PipelineStage, mpsc::Sender<FeedbackSignal>>>,
    /// Stage quality metrics
    stage_metrics: RwLock<HashMap<PipelineStage, StageMetrics>>,
    /// Pending device error signals (to be sent on next sync)
    pending_device_errors: RwLock<HashMap<String, Vec<DeviceErrorSignal>>>,
    /// Aggregation parameter adjustments
    aggregation_adjustments: RwLock<Vec<AggregationAdjustment>>,
    /// Data collection priorities
    collection_priorities: RwLock<Vec<CollectionPriority>>,
    /// Channel capacity
    channel_capacity: usize,
}

impl PipelineFeedbackChannel {
    pub fn new() -> Self {
        let channel_capacity = 1000;
        let mut senders = HashMap::new();
        let mut receivers = HashMap::new();
        let mut stage_metrics = HashMap::new();

        // Create channels for each pipeline stage
        let stages = vec![
            PipelineStage::SyncReceiver,
            PipelineStage::Validator,
            PipelineStage::Aggregator,
            PipelineStage::Analyzer,
            PipelineStage::Intelligence,
            PipelineStage::FederatedLearning,
        ];

        for stage in stages {
            let (tx, rx) = mpsc::channel(channel_capacity);
            senders.insert(stage.clone(), tx);
            receivers.insert(stage.clone(), rx);
            stage_metrics.insert(stage.clone(), StageMetrics::new(stage));
        }

        Self {
            receivers: RwLock::new(receivers),
            senders: RwLock::new(senders),
            stage_metrics: RwLock::new(stage_metrics),
            pending_device_errors: RwLock::new(HashMap::new()),
            aggregation_adjustments: RwLock::new(Vec::new()),
            collection_priorities: RwLock::new(Vec::new()),
            channel_capacity,
        }
    }

    /// Send a feedback signal to a specific pipeline stage.
    pub async fn send(&self, signal: FeedbackSignal) -> Result<(), FeedbackError> {
        let senders = self.senders.read().await;
        if let Some(sender) = senders.get(&signal.target_stage) {
            sender.try_send(signal).map_err(|e| match e {
                mpsc::error::TrySendError::Full(_) => FeedbackError::ChannelFull,
                mpsc::error::TrySendError::Closed(_) => FeedbackError::ChannelClosed,
            })
        } else {
            Err(FeedbackError::UnknownStage)
        }
    }

    /// Send an error signal back to the device (via SyncReceiver stage).
    pub async fn send_error(&self, device_id: &str, errors: &[String]) {
        let signal = FeedbackSignal {
            signal_id: uuid::Uuid::new_v4().to_string(),
            source_stage: PipelineStage::Validator,
            target_stage: PipelineStage::SyncReceiver,
            signal_type: FeedbackType::ErrorSignal,
            severity: Severity::Warning,
            data: serde_json::json!({
                "device_id": device_id,
                "errors": errors,
            }),
            timestamp: Utc::now(),
        };

        if let Err(e) = self.send(signal).await {
            warn!(
                "Failed to send error signal for device {}: {:?}",
                device_id, e
            );
        }

        // Also queue for next sync
        let mut pending = self.pending_device_errors.write().await;
        pending
            .entry(device_id.to_string())
            .or_default()
            .push(DeviceErrorSignal {
                device_id: device_id.to_string(),
                errors: errors.to_vec(),
                severity: Severity::Warning,
                suggested_fix: Some("Check data format and retry".to_string()),
                timestamp: Utc::now(),
            });
    }

    /// Get pending error signals for a device (consumed on next sync).
    pub async fn consume_device_errors(&self, device_id: &str) -> Vec<DeviceErrorSignal> {
        let mut pending = self.pending_device_errors.write().await;
        pending.remove(device_id).unwrap_or_default()
    }

    /// Update stage quality metrics.
    pub async fn update_stage_metrics(&self, stage: PipelineStage, metrics: StageMetrics) {
        let mut stage_metrics = self.stage_metrics.write().await;
        stage_metrics.insert(stage, metrics);
    }

    /// Get all stage metrics (for monitoring/observability).
    pub async fn get_all_metrics(&self) -> HashMap<PipelineStage, StageMetrics> {
        let stage_metrics = self.stage_metrics.read().await;
        stage_metrics.clone()
    }

    /// Record an aggregation parameter adjustment.
    pub async fn record_aggregation_adjustment(&self, adjustment: AggregationAdjustment) {
        info!(
            "Aggregation adjustment: {} {} → {} ({})",
            adjustment.parameter, adjustment.old_value, adjustment.new_value, adjustment.reason
        );
        let mut adjustments = self.aggregation_adjustments.write().await;
        adjustments.push(adjustment);
        // Keep last 100 adjustments
        if adjustments.len() > 100 {
            adjustments.remove(0);
        }
    }

    /// Get recent aggregation adjustments.
    pub async fn get_aggregation_adjustments(&self) -> Vec<AggregationAdjustment> {
        let adjustments = self.aggregation_adjustments.read().await;
        adjustments.clone()
    }

    /// Update data collection priorities based on analyzer feedback.
    pub async fn update_collection_priorities(&self, priorities: Vec<CollectionPriority>) {
        info!(
            "Updating collection priorities: {} entries",
            priorities.len()
        );
        let mut stored = self.collection_priorities.write().await;
        *stored = priorities;
    }

    /// Get current data collection priorities.
    pub async fn get_collection_priorities(&self) -> Vec<CollectionPriority> {
        let priorities = self.collection_priorities.read().await;
        priorities.clone()
    }

    /// Process feedback signals for a specific stage (called by stage workers).
    pub async fn process_stage_signals(&self, stage: &PipelineStage) -> Vec<FeedbackSignal> {
        let mut receivers = self.receivers.write().await;
        if let Some(receiver) = receivers.get_mut(stage) {
            let mut signals = Vec::new();
            while let Ok(signal) = receiver.try_recv() {
                signals.push(signal);
            }
            signals
        } else {
            Vec::new()
        }
    }
}

// ─── Feedback Error ───────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum FeedbackError {
    #[error("feedback channel is full")]
    ChannelFull,
    #[error("feedback channel is closed")]
    ChannelClosed,
    #[error("unknown pipeline stage")]
    UnknownStage,
}

// ─── Pipeline Feedback Loop Orchestrator ───────────────────────────────────

/// Orchestrates the feedback loops between pipeline stages.
/// Runs as a background task, processing signals and adjusting parameters.
pub struct PipelineFeedbackLoop {
    channel: Arc<PipelineFeedbackChannel>,
    check_interval: std::time::Duration,
}

impl PipelineFeedbackLoop {
    pub fn new(channel: Arc<PipelineFeedbackChannel>, check_interval: std::time::Duration) -> Self {
        Self {
            channel,
            check_interval,
        }
    }

    /// Start the feedback loop orchestrator.
    pub async fn run(self) {
        let mut tick = tokio::time::interval(self.check_interval);
        info!("Pipeline Feedback Loop: started");

        loop {
            tick.tick().await;

            // Process signals from each stage
            let stages = vec![
                PipelineStage::SyncReceiver,
                PipelineStage::Validator,
                PipelineStage::Aggregator,
                PipelineStage::Analyzer,
                PipelineStage::Intelligence,
                PipelineStage::FederatedLearning,
            ];

            for stage in &stages {
                let signals = self.channel.process_stage_signals(stage).await;
                for signal in signals {
                    self.handle_signal(signal).await;
                }
            }

            // Check stage health and generate adjustment recommendations
            self.check_stage_health().await;
        }
    }

    async fn handle_signal(&self, signal: FeedbackSignal) {
        match signal.signal_type {
            FeedbackType::QualityMetric => {
                info!(
                    "Quality metric from {:?} to {:?}: {:?}",
                    signal.source_stage, signal.target_stage, signal.data
                );
            }
            FeedbackType::ParameterAdjustment => {
                if let Ok(adjustment) =
                    serde_json::from_value::<AggregationAdjustment>(signal.data.clone())
                {
                    self.channel.record_aggregation_adjustment(adjustment).await;
                }
            }
            FeedbackType::PriorityChange => {
                if let Ok(priorities) =
                    serde_json::from_value::<Vec<CollectionPriority>>(signal.data.clone())
                {
                    self.channel.update_collection_priorities(priorities).await;
                }
            }
            FeedbackType::ErrorSignal => {
                warn!(
                    "Error signal from {:?} to {:?}: {:?}",
                    signal.source_stage, signal.target_stage, signal.data
                );
            }
            FeedbackType::CollectionFocus => {
                info!(
                    "Collection focus change from {:?}: {:?}",
                    signal.source_stage, signal.data
                );
            }
            FeedbackType::ModelFeedback => {
                info!(
                    "Model feedback from {:?}: {:?}",
                    signal.source_stage, signal.data
                );
            }
        }
    }

    async fn check_stage_health(&self) {
        let metrics = self.channel.get_all_metrics().await;

        for (stage, m) in &metrics {
            // High error rate warning
            if m.error_rate > 0.1 {
                warn!(
                    "Stage {:?} has high error rate: {:.1}%",
                    stage,
                    m.error_rate * 100.0
                );
            }

            // Low quality score warning
            if m.quality_score < 0.7 {
                warn!(
                    "Stage {:?} has low quality score: {:.2}",
                    stage, m.quality_score
                );
            }

            // High latency warning
            if m.avg_latency_ms > 5000.0 {
                warn!(
                    "Stage {:?} has high latency: {:.0}ms",
                    stage, m.avg_latency_ms
                );
            }
        }
    }
}

// ─── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_pipeline_feedback_channel_send_receive() {
        let channel = PipelineFeedbackChannel::new();

        let signal = FeedbackSignal {
            signal_id: "test-1".to_string(),
            source_stage: PipelineStage::Validator,
            target_stage: PipelineStage::SyncReceiver,
            signal_type: FeedbackType::ErrorSignal,
            severity: Severity::Warning,
            data: serde_json::json!({"device_id": "dev-001", "errors": ["bad format"]}),
            timestamp: Utc::now(),
        };

        channel.send(signal).await.unwrap();

        let signals = channel
            .process_stage_signals(&PipelineStage::SyncReceiver)
            .await;
        assert_eq!(signals.len(), 1);
        assert_eq!(signals[0].signal_id, "test-1");
    }

    #[tokio::test]
    async fn test_device_error_queue() {
        let channel = PipelineFeedbackChannel::new();

        channel
            .send_error("dev-001", &["missing field".to_string()])
            .await;

        let errors = channel.consume_device_errors("dev-001").await;
        assert_eq!(errors.len(), 1);
        assert_eq!(errors[0].device_id, "dev-001");

        // Consumed — should be empty now
        let errors = channel.consume_device_errors("dev-001").await;
        assert!(errors.is_empty());
    }

    #[tokio::test]
    async fn test_aggregation_adjustments() {
        let channel = PipelineFeedbackChannel::new();

        channel
            .record_aggregation_adjustment(AggregationAdjustment {
                parameter: "window_size_hours".to_string(),
                old_value: 24.0,
                new_value: 12.0,
                reason: "High volatility detected".to_string(),
                confidence: 0.8,
            })
            .await;

        let adjustments = channel.get_aggregation_adjustments().await;
        assert_eq!(adjustments.len(), 1);
        assert_eq!(adjustments[0].parameter, "window_size_hours");
    }

    #[tokio::test]
    async fn test_collection_priorities() {
        let channel = PipelineFeedbackChannel::new();

        channel
            .update_collection_priorities(vec![CollectionPriority {
                region: "nairobi-eastlands".to_string(),
                product_category: "vegetables".to_string(),
                priority_score: 0.9,
                reason: "High demand spike detected".to_string(),
            }])
            .await;

        let priorities = channel.get_collection_priorities().await;
        assert_eq!(priorities.len(), 1);
        assert_eq!(priorities[0].region, "nairobi-eastlands");
    }
}
