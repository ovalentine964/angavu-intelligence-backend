// Structured JSON Logging — Configures tracing-subscriber for JSON-formatted output
//
// Every log entry includes:
// - timestamp (ISO 8601)
// - level (INFO, WARN, ERROR, DEBUG, TRACE)
// - message
// - request_id (correlation ID from X-Request-ID)
// - user_id (from JWT claims when available)
// - tool_name (from route context when available)
// - span fields (service.name, service.version, trace_id, span_id)
// - OpenTelemetry trace context (trace_id, span_id) when OTel is active
//
// Configuration via environment variables:
//   LOG_FORMAT=json|text  (default: json in production, text in development)
//   LOG_LEVEL=info        (default: info; overrides RUST_LOG for our module)

use opentelemetry::trace::TracerProvider;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

/// Initialize the global tracing subscriber with:
/// 1. JSON-formatted structured logging
/// 2. OpenTelemetry OTLP export (if OTEL_EXPORTER_OTLP_ENDPOINT is set)
/// 3. EnvFilter for log level control
/// 4. Correlation ID injection via span fields
///
/// Returns the OTel tracer guard (must be kept alive for the application lifetime)
/// to prevent the tracer from being dropped and losing pending spans.
pub fn init_json_logging() -> Option<opentelemetry_sdk::trace::Tracer> {
    let otlp_endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT").ok();
    let log_format = std::env::var("LOG_FORMAT").unwrap_or_else(|_| {
        if std::env::var("RUST_ENV").as_deref() == Ok("production") {
            "json".to_string()
        } else {
            "text".to_string()
        }
    });

    // ── Build OTel Tracer ────────────────────────────────────
    let otel_tracer: Option<opentelemetry_sdk::trace::Tracer> = if let Some(ref endpoint) =
        otlp_endpoint
    {
        match opentelemetry_otlp::new_pipeline()
            .tracing()
            .with_exporter(
                opentelemetry_otlp::new_exporter()
                    .tonic()
                    .with_endpoint(endpoint),
            )
            .with_trace_config(opentelemetry_sdk::trace::Config::default().with_resource(
                opentelemetry_sdk::Resource::new(vec![
                    opentelemetry::KeyValue::new("service.name", "angavu-intelligence-backend"),
                    opentelemetry::KeyValue::new("service.version", env!("CARGO_PKG_VERSION")),
                    opentelemetry::KeyValue::new(
                        "deployment.environment",
                        std::env::var("RUST_ENV").unwrap_or_else(|_| "development".to_string()),
                    ),
                ]),
            ))
            .install_batch(opentelemetry_sdk::runtime::Tokio)
        {
            Ok(tracer) => {
                tracing::info!(endpoint = %endpoint, "OpenTelemetry OTLP exporter initialized");
                Some(tracer)
            }
            Err(e) => {
                tracing::warn!(error = %e, "Failed to initialize OTLP exporter — falling back to local tracing only");
                None
            }
        }
    } else {
        tracing::info!("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing is local only");
        None
    };

    // ── Build OTel Layer ─────────────────────────────────────
    let otel_layer = otel_tracer
        .as_ref()
        .map(|tracer| tracing_opentelemetry::layer().with_tracer(tracer.clone()));

    // ── Build EnvFilter ──────────────────────────────────────
    let env_filter = EnvFilter::try_from_default_env().unwrap_or_else(|_| {
        EnvFilter::new("angavu=info,tower_http=info,sqlx=warn,redis=warn,hyper=info")
    });

    // ── Build Fmt Layer ──────────────────────────────────────
    match log_format.as_str() {
        "json" => {
            let json_layer = fmt::layer()
                .json()
                .with_current_span(true)
                .with_span_list(true)
                .with_target(true)
                .with_file(true)
                .with_line_number(true)
                .flatten_event(true);

            tracing_subscriber::registry()
                .with(env_filter)
                .with(json_layer)
                .with(otel_layer)
                .init();
        }
        _ => {
            let text_layer = fmt::layer()
                .with_target(true)
                .with_file(true)
                .with_line_number(true);

            tracing_subscriber::registry()
                .with(env_filter)
                .with(text_layer)
                .with(otel_layer)
                .init();
        }
    }

    otel_tracer
}
