// Telemetry Module — Structured JSON logging, correlation IDs, OpenTelemetry integration
//
// Provides:
// - JSON-formatted structured logging with correlation IDs
// - Request tracing middleware (X-Request-ID propagation)
// - OTel span instrumentation for all OODA phases
// - DB query and Redis operation tracing layers

pub mod correlation;
pub mod json_logging;
pub mod request_trace;
pub mod db_tracing;
pub mod health;

pub use correlation::CorrelationId;
pub use json_logging::init_json_logging;
pub use request_trace::request_trace_middleware;
pub use health::health_router;
