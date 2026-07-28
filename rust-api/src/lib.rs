// Angavu Intelligence Backend — Full Intelligence Platform
// Integrates loop engineering, graph engineering, multi-agent orchestration,
// health metrics, credit scoring, and API gateway.

pub mod loops;
pub mod credit;
pub mod graph;
pub mod orchestrator;
pub mod gateway;
pub mod health;
pub mod service_pricing;
pub mod sync;
pub mod observability;
pub mod webhook;

use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::info;

use loops::ooda_loop::{OodaSupervisor, LoopConfig};
use loops::drift_detection::{DriftDetector, DriftConfig};
use loops::pipeline_feedback::{PipelineFeedbackChannel, PipelineFeedbackLoop};
use loops::circuit_breaker::CircuitBreakerRegistry;
use loops::metrics::LoopMetrics;

/// Initialize and start all loop engineering components.
/// Call this from the application's main/startup function.
pub async fn init_loop_engineering() -> LoopEngineeringHandles {
    info!("Initializing Loop Engineering subsystem...");

    // 1. Shared metrics
    let metrics = Arc::new(RwLock::new(LoopMetrics::default()));

    // 2. Drift detector
    let drift_detector = Arc::new(RwLock::new(
        DriftDetector::new(DriftConfig::default())
    ));

    // 3. Pipeline feedback channel
    let pipeline_feedback = Arc::new(PipelineFeedbackChannel::new());

    // 4. Circuit breaker registry
    let circuit_breakers = Arc::new(CircuitBreakerRegistry::new());
    circuit_breakers.register_defaults().await;

    // 5. OODA Supervisor
    let ooda = Arc::new(OodaSupervisor::new(
        LoopConfig::default(),
        metrics.clone(),
        drift_detector.clone(),
        pipeline_feedback.clone(),
    ));

    // 6. Start pipeline feedback loop
    let feedback_loop = PipelineFeedbackLoop::new(
        pipeline_feedback.clone(),
        std::time::Duration::from_secs(30),
    );
    let feedback_handle = tokio::spawn(feedback_loop.run());

    // 7. Start OODA loops
    let ooda_handles = ooda.clone().start();

    info!("Loop Engineering initialized: 4 OODA loops + feedback loop + circuit breakers");

    LoopEngineeringHandles {
        metrics,
        drift_detector,
        pipeline_feedback,
        circuit_breakers,
        ooda,
        ooda_handles,
        feedback_handle,
    }
}

/// Handles to all loop engineering components.
/// Keep this alive for the application lifetime.
pub struct LoopEngineeringHandles {
    pub metrics: Arc<RwLock<LoopMetrics>>,
    pub drift_detector: Arc<RwLock<DriftDetector>>,
    pub pipeline_feedback: Arc<PipelineFeedbackChannel>,
    pub circuit_breakers: Arc<CircuitBreakerRegistry>,
    pub ooda: Arc<OodaSupervisor>,
    pub ooda_handles: Vec<tokio::task::JoinHandle<()>>,
    pub feedback_handle: tokio::task::JoinHandle<()>,
}

impl LoopEngineeringHandles {
    /// Gracefully shut down all loops.
    pub async fn shutdown(self) {
        info!("Shutting down Loop Engineering...");
        self.ooda.shutdown();
        for handle in self.ooda_handles {
            let _ = handle.await;
        }
        self.feedback_handle.abort();
        info!("Loop Engineering shut down complete");
    }
}
