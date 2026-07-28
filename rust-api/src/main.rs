// Angavu Intelligence Backend — Main Entry Point
// Integrates all modules: orchestrator, gateway, loops, credit, graph, health, service_pricing, webhooks

use angavu_intelligence_backend::orchestrator::message_bus::{ModuleMessageBus, MessageBusConfig};
use angavu_intelligence_backend::webhook::{self as webhook_module, WebhookState, MpesaConfig, MpesaEnvironment, webhook_router};
use angavu_intelligence_backend::orchestrator::OODAOrchestrator;
use angavu_intelligence_backend::orchestrator::supervisor::OrchestratorConfig;
use angavu_intelligence_backend::gateway::{GatewayState, build_gateway_router};
use angavu_intelligence_backend::gateway::auth::JwtConfig;
use angavu_intelligence_backend::gateway::rate_limit::RateLimiter;
use angavu_intelligence_backend::gateway::k_anonymity::KAnonymityEnforcer;
use angavu_intelligence_backend::gateway::audit::AuditLogger;
use angavu_intelligence_backend::loops;
use std::sync::Arc;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "angavu=info,tower_http=info".into()))
        .with(tracing_subscriber::fmt::layer())
        .init();

    tracing::info!("Starting Angavu Intelligence Backend");

    // ── Load Configuration ──────────────────────────────────────
    let database_url = std::env::var("DATABASE_URL")
        .unwrap_or_else(|_| "postgresql://angavu:angavu_secret@localhost:5432/angavu".to_string());
    let redis_url = std::env::var("REDIS_URL")
        .unwrap_or_else(|_| "redis://localhost:6379/0".to_string());
    let jwt_secret = std::env::var("JWT_SECRET")
        .unwrap_or_else(|_| "change-me-in-production".to_string());
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
    let loop_handles = loops::init_loop_engineering().await;
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

    // Spawn audit buffer flusher
    let bus_clone = Arc::clone(&bus);
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(60));
        loop {
            interval.tick().await;
            let entries = bus_clone.flush_audit().await;
            if !entries.is_empty() {
                tracing::debug!(count = entries.len(), "Audit buffer flushed");
            }
        }
    });

    // ── Initialize API Gateway ──────────────────────────────────
    let jwt_config = JwtConfig {
        encoding_key: jsonwebtoken::EncodingKey::from_secret(jwt_secret.as_bytes()),
        decoding_key: jsonwebtoken::DecodingKey::from_secret(jwt_secret.as_bytes()),
        validation: {
            let mut v = jsonwebtoken::Validation::default();
            v.set_audience(&["angavu-api"]);
            v
        },
        access_token_ttl: 3600,       // 1 hour
        refresh_token_ttl: 86400 * 30, // 30 days
    };

    let sync_state = Arc::new(angavu_intelligence_backend::sync::receiver::SyncState::new());

    let gateway_state = GatewayState {
        jwt_config: Arc::new(jwt_config),
        rate_limiter: Arc::new(RateLimiter::new(10)),
        k_anonymity: Arc::new(KAnonymityEnforcer::new(10)),
        audit: Arc::new(AuditLogger::new(1024)),
        sync_state,
    };

    // ── Initialize Webhook System ──────────────────────────────
    let webhook_state = WebhookState {
        db: pg_pool.clone(),
        redis: redis_conn.clone(),
        message_bus: Arc::new(ModuleMessageBus::new(MessageBusConfig::default())),
        mpesa_config: MpesaConfig {
            passkey: std::env::var("MPESA_PASSKEY")
                .unwrap_or_else(|_| "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919".to_string()),
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
            .unwrap_or_else(|_| "default-webhook-key".to_string())
            .split(',')
            .map(|s| s.trim().to_string())
            .collect(),
    };

    // Run webhook_events table migration
    sqlx::query(webhook_module::MIGRATION_WEBHOOK_EVENTS)
        .execute(&pg_pool)
        .await
        .map_err(|e| {
            tracing::warn!(error = %e, "Webhook events table migration skipped (may already exist)")
        })
        .ok();

    tracing::info!("Webhook system initialized (M-Pesa + Market Feed + Generic)");

    // ── Initialize Human-in-the-Loop Approval System ──────────
    let approval_state = angavu_intelligence_backend::gateway::human_approval::HumanApprovalState {
        redis: redis_conn.clone(),
        audit: Arc::new(AuditLogger::new(1024)),
    };
    let approval_router = angavu_intelligence_backend::gateway::human_approval::human_approval_router(approval_state);
    tracing::info!("Human-in-the-Loop approval system initialized (credit decisions, sensitive actions, escalation, reports, chama governance)");

    let app = build_gateway_router(gateway_state)
        .merge(webhook_router(webhook_state))
        .merge(approval_router);

    // ── Start HTTP Server ───────────────────────────────────────
    let addr = format!("{}:{}", host, port);
    tracing::info!(addr = %addr, "Starting HTTP server");

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    // ── Graceful Shutdown ───────────────────────────────────────
    tracing::info!("Shutting down...");
    loop_handles.shutdown().await;
    orchestrator.shutdown().await?;

    Ok(())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c().await.expect("failed to install Ctrl+C handler");
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
