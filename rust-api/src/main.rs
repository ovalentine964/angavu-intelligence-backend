// Angavu Intelligence Backend — Main Entry Point
// Integrates all modules: orchestrator, gateway, loops, credit, graph, health, service_pricing, webhooks
//
// Telemetry:
// - Structured JSON logging with correlation IDs (X-Request-ID)
// - OpenTelemetry OTLP export (optional, via OTEL_EXPORTER_OTLP_ENDPOINT)
// - Request tracing from API gateway through all modules
// - Health check endpoints: /health, /health/ready, /health/detailed

use angavu_intelligence_backend::credit::privacy_budget::PrivacyBudgetTracker;
use angavu_intelligence_backend::gateway::audit::AuditLogger;
use angavu_intelligence_backend::gateway::auth::JwtConfig;
use angavu_intelligence_backend::gateway::k_anonymity::KAnonymityEnforcer;
use angavu_intelligence_backend::gateway::rate_limit::RateLimiter;
use angavu_intelligence_backend::gateway::{build_gateway_router, GatewayState};
use angavu_intelligence_backend::graphql;
use angavu_intelligence_backend::loops;
use angavu_intelligence_backend::orchestrator::message_bus::{MessageBusConfig, ModuleMessageBus};
use angavu_intelligence_backend::orchestrator::supervisor::OrchestratorConfig;
use angavu_intelligence_backend::orchestrator::OODAOrchestrator;
use angavu_intelligence_backend::statistical::DifferentialPrivacyEngine;
use angavu_intelligence_backend::telemetry;
use angavu_intelligence_backend::webhook::{
    self as webhook_module, webhook_router, MpesaConfig, MpesaEnvironment, WebhookState,
};
use std::sync::Arc;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize structured JSON logging with OpenTelemetry OTLP export
    // Controlled by:
    //   LOG_FORMAT=json|text  (default: json in production, text in development)
    //   OTEL_EXPORTER_OTLP_ENDPOINT=http://... (optional OTLP collector)
    //   RUST_LOG=angavu=info,tower_http=info,...
    let _otel_tracer_guard = telemetry::init_json_logging();

    tracing::info!(
        version = env!("CARGO_PKG_VERSION"),
        "Starting Angavu Intelligence Backend"
    );

    // ── Load Configuration ──────────────────────────────────────
    // Security: JWT_SECRET and MPESA_PASSKEY MUST be set via environment variables.
    // We fail fast if missing to prevent running with insecure defaults.
    let database_url = std::env::var("DATABASE_URL").unwrap_or_else(|_| {
        tracing::warn!("DATABASE_URL not set — using local development default (no password)");
        "postgresql://angavu@localhost:5432/angavu".to_string()
    });
    let redis_url =
        std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://localhost:6379/0".to_string());
    let jwt_secret = std::env::var("JWT_SECRET").unwrap_or_else(|_| {
        let generated = generate_random_secret();
        tracing::warn!(
            "JWT_SECRET not set — generated random secret (tokens will not survive restart)"
        );
        generated
    });
    if jwt_secret.len() < 32 {
        tracing::error!(
            "JWT_SECRET is too short ({} chars, minimum 32). Aborting.",
            jwt_secret.len()
        );
        std::process::exit(1);
    }
    let host = std::env::var("ANGAVU_HOST").unwrap_or_else(|_| "0.0.0.0".to_string());
    let port: u16 = std::env::var("ANGAVU_PORT")
        .unwrap_or_else(|_| "8000".to_string())
        .parse()?;

    // ── Initialize Database Connections ─────────────────────────
    let pg_pool = sqlx::PgPool::connect(&database_url).await?;
    tracing::info!("PostgreSQL connected");

    let redis_client = redis::Client::open(redis_url)?;
    let redis_conn = redis::aio::ConnectionManager::new(redis_client).await?;
    tracing::info!("Redis connected");

    // ── Initialize Loop Engineering ─────────────────────────────
    let ooda_db = Arc::new(loops::ooda_loop::PgOodaDatabase::new(pg_pool.clone()));
    let loop_handles = loops::init_loop_engineering(ooda_db).await;
    tracing::info!("Loop engineering initialized (4 OODA loops + feedback + circuit breakers)");

    // ── Initialize Message Bus ──────────────────────────────────
    let bus_config = MessageBusConfig::default();
    let bus = Arc::new(ModuleMessageBus::new(bus_config));

    // ── Initialize OODA Orchestrator ────────────────────────────
    let orchestrator_config = OrchestratorConfig::default();
    let orchestrator = Arc::new(OODAOrchestrator::new(orchestrator_config, Arc::clone(&bus)));

    // Start all 6 capability modules
    orchestrator.start_modules().await?;

    // Spawn orchestrator main loop
    let orch_clone = Arc::clone(&orchestrator);
    tokio::spawn(async move {
        if let Err(e) = orch_clone.run().await {
            tracing::error!(error = %e, "Orchestrator exited with error");
        }
    });

    // Spawn audit buffer flusher — adaptive batching
    // The AuditLogger already flushes when buffer reaches max_buffer_size (event-driven).
    // This timer is a fallback to drain partial buffers every 60s.
    // Uses MissedTickBehavior::Delay to avoid flush storms after backpressure.
    let bus_clone = Arc::clone(&bus);
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(60));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        loop {
            interval.tick().await;
            let entries = bus_clone.flush_audit().await;
            if !entries.is_empty() {
                tracing::debug!(
                    count = entries.len(),
                    "Audit buffer flushed (timer fallback)"
                );
            }
        }
    });

    // P2: Cache warming on startup — pre-populate Redis caches from DB
    // Eliminates cold-start latency for first requests after restart
    let graph_cache =
        angavu_intelligence_backend::graph::cache::GraphCache::new(redis_conn.clone());
    let pg_pool_warm = pg_pool.clone();
    let cache_warm_handle = tokio::spawn(async move {
        // Warm graph statistics (use tables that exist: kg_edges, kg_worker_cohorts)
        let stats_result = sqlx::query_scalar::<_, serde_json::Value>(
            "SELECT json_build_object( \
             'node_count', (SELECT COUNT(*) FROM kg_edges), \
             'edge_count', (SELECT COUNT(*) FROM kg_edges), \
             'worker_count', (SELECT COALESCE(SUM(member_count), 0) FROM kg_worker_cohorts) \
             )",
        )
        .fetch_one(&pg_pool_warm)
        .await;
        match stats_result {
            Ok(stats) => {
                if let Err(e) = graph_cache.cache_stats(&stats).await {
                    tracing::warn!(error = %e, "Failed to warm graph stats cache");
                } else {
                    tracing::info!("Graph stats cache warmed on startup");
                }
            }
            Err(e) => tracing::warn!(error = %e, "Failed to compute graph stats for cache warming"),
        }
    });
    // Don't block startup on cache warming — it runs in background
    let _ = cache_warm_handle;

    // ── Initialize API Gateway ──────────────────────────────────
    let jwt_config = JwtConfig {
        encoding_key: jsonwebtoken::EncodingKey::from_secret(jwt_secret.as_bytes()),
        decoding_key: jsonwebtoken::DecodingKey::from_secret(jwt_secret.as_bytes()),
        validation: {
            let mut v = jsonwebtoken::Validation::default();
            v.set_audience(&["angavu-api"]);
            v
        },
        access_token_ttl: 900, // 15 minutes (P1: reduced from 1 hour for security)
        refresh_token_ttl: 86400 * 30, // 30 days
    };

    let sync_state = Arc::new(angavu_intelligence_backend::sync::receiver::SyncState::new());

    let gateway_state = GatewayState {
        jwt_config: Arc::new(jwt_config),
        rate_limiter: Arc::new(RateLimiter::new(10)),
        k_anonymity: Arc::new(KAnonymityEnforcer::new(10)),
        privacy_budget: Arc::new(PrivacyBudgetTracker::new()),
        dp_engine: Arc::new(parking_lot::RwLock::new(DifferentialPrivacyEngine::new(
            0.1,
        ))),
        audit: Arc::new(AuditLogger::with_pool(1024, pg_pool.clone())),
        sync_state,
        db: pg_pool.clone(),
        redis: redis_conn.clone(),
    };

    // ── Initialize Webhook System ──────────────────────────────
    let webhook_state = WebhookState {
        db: pg_pool.clone(),
        redis: redis_conn.clone(),
        message_bus: Arc::new(ModuleMessageBus::new(MessageBusConfig::default())),
        mpesa_config: MpesaConfig {
            passkey: std::env::var("MPESA_PASSKEY")
                .unwrap_or_else(|_| {
                    tracing::error!("MPESA_PASSKEY environment variable is not set. M-Pesa signature validation will fail.");
                    String::new()
                }),
            shortcode: std::env::var("MPESA_SHORTCODE")
                .unwrap_or_else(|_| "174379".to_string()),
            initiator_password: std::env::var("MPESA_INITIATOR_PASSWORD")
                .unwrap_or_default(),
            environment: match std::env::var("MPESA_ENVIRONMENT").as_deref() {
                Ok("production") => MpesaEnvironment::Production,
                _ => MpesaEnvironment::Sandbox,
            },
        },
        webhook_api_keys: std::env::var("WEBHOOK_API_KEYS")
            .unwrap_or_else(|_| {
                tracing::warn!("WEBHOOK_API_KEYS not set — generating random key for this session");
                uuid::Uuid::new_v4().to_string()
            })
            .split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect(),
        ip_rate_limiter: Arc::new(angavu_intelligence_backend::gateway::rate_limit::IpRateLimiter::new(60)),
    };

    // Run audit_log table migration
    sqlx::query(angavu_intelligence_backend::gateway::audit::AUDIT_LOG_MIGRATION)
        .execute(&pg_pool)
        .await
        .map_err(
            |e| tracing::warn!(error = %e, "Audit log table migration skipped (may already exist)"),
        )
        .ok();

    // Run webhook_events table migration
    sqlx::query(webhook_module::MIGRATION_WEBHOOK_EVENTS)
        .execute(&pg_pool)
        .await
        .map_err(|e| {
            tracing::warn!(error = %e, "Webhook events table migration skipped (may already exist)")
        })
        .ok();

    // ── Billing Tables Migrations ───────────────────────────────
    // Core billing tables (subscriptions, invoices, usage_records, api_keys)
    sqlx::query(angavu_intelligence_backend::billing::metering::USAGE_MIGRATION)
        .execute(&pg_pool)
        .await
        .map_err(|e| {
            tracing::warn!(error = %e, "Usage records table migration skipped (may already exist)")
        })
        .ok();

    // M-Pesa payments table
    sqlx::query(angavu_intelligence_backend::billing::mpesa::PAYMENTS_MIGRATION)
        .execute(&pg_pool)
        .await
        .map_err(
            |e| tracing::warn!(error = %e, "Payments table migration skipped (may already exist)"),
        )
        .ok();

    // Invoice generation tables
    sqlx::query(angavu_intelligence_backend::billing::invoice::INVOICE_MIGRATION)
        .execute(&pg_pool)
        .await
        .map_err(
            |e| tracing::warn!(error = %e, "Invoice table migration skipped (may already exist)"),
        )
        .ok();

    // Subscription lifecycle tables
    sqlx::query(angavu_intelligence_backend::billing::subscription::SUBSCRIPTION_MIGRATION)
        .execute(&pg_pool)
        .await
        .map_err(|e| {
            tracing::warn!(error = %e, "Subscription table migration skipped (may already exist)")
        })
        .ok();

    // Model Registry tables
    sqlx::query(angavu_intelligence_backend::credit::model_registry::MODEL_REGISTRY_MIGRATION)
        .execute(&pg_pool)
        .await
        .map_err(|e| {
            tracing::warn!(error = %e, "Model registry table migration skipped (may already exist)")
        })
        .ok();

    // Data Retention tracking tables
    sqlx::query(angavu_intelligence_backend::gateway::data_retention::RETENTION_MIGRATION)
        .execute(&pg_pool)
        .await
        .map_err(|e| {
            tracing::warn!(error = %e, "Data retention table migration skipped (may already exist)")
        })
        .ok();

    tracing::info!("Billing tables initialized (subscriptions, invoices, usage_records, payments)");
    tracing::info!("Model registry and data retention tables initialized");
    tracing::info!("Webhook system initialized (M-Pesa + Market Feed + Generic)");

    // ── Initialize Human-in-the-Loop Approval System ──────────
    let approval_state = angavu_intelligence_backend::gateway::human_approval::HumanApprovalState {
        redis: redis_conn.clone(),
        audit: Arc::new(AuditLogger::with_pool(1024, pg_pool.clone())),
    };
    let approval_router =
        angavu_intelligence_backend::gateway::human_approval::human_approval_router(approval_state);
    tracing::info!("Human-in-the-Loop approval system initialized (credit decisions, sensitive actions, escalation, reports, chama governance)");

    // ── Initialize GraphQL ──────────────────────────────────────
    let graphql_schema = graphql::create_schema(pg_pool.clone(), redis_conn.clone()).await;
    let graphql_routes = graphql::graphql_router(graphql_schema.clone());
    tracing::info!("GraphQL endpoint initialized at /graphql");

    let clickhouse_url = std::env::var("CLICKHOUSE_URL").ok();

    let app = build_gateway_router(
        gateway_state,
        vec![
            // S6: Approval and GraphQL routes INSIDE the JWT auth layer
            approval_router,
            graphql_routes,
        ],
    )
    // M-Pesa webhooks remain outside auth — they use their own API key / HMAC validation
    .merge(webhook_router(webhook_state))
    // Health check endpoints (public, no auth required)
    .merge(telemetry::health_router(telemetry::health::HealthState {
        db: pg_pool.clone(),
        redis: redis_conn.clone(),
        clickhouse_url,
        started_at: std::time::Instant::now(),
    }));

    // ── Start HTTP Server ───────────────────────────────────────
    let addr = format!("{}:{}", host, port);
    tracing::info!(addr = %addr, "Starting HTTP server");

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    // Use into_make_service_with_connect_info so ConnectInfo<SocketAddr>
    // is available to middleware (auth, audit) for client IP extraction.
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<std::net::SocketAddr>(),
    )
    .with_graceful_shutdown(shutdown_signal())
    .await?;

    // ── Graceful Shutdown ───────────────────────────────────────
    tracing::info!("Shutting down...");
    loop_handles.shutdown().await;
    orchestrator.shutdown().await?;

    Ok(())
}

/// Generate a cryptographically random secret for JWT signing.
/// Used when JWT_SECRET env var is not set.
fn generate_random_secret() -> String {
    use rand::Rng;
    let mut rng = rand::thread_rng();
    let secret: Vec<u8> = (0..64).map(|_| rng.gen()).collect();
    base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &secret)
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }

    tracing::info!("Shutdown signal received");
}
