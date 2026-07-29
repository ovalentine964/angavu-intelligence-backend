// ═══════════════════════════════════════════════════════════════════════════
// DEPRECATED: This file is NOT compiled (not listed in Cargo.toml).
// The canonical entry point is main.rs (binary: angavu-server).
// This file is kept for historical reference only.
// ═══════════════════════════════════════════════════════════════════════════
//
// src/main.rs
//
// mod orchestrator;
// mod gateway;
//
// ... (original code preserved below for reference)

use orchestrator::message_bus::{ModuleMessageBus, MessageBusConfig};
use orchestrator::OODAOrchestrator;
use orchestrator::supervisor::OrchestratorConfig;
use gateway::{GatewayState, build_gateway_router};
use gateway::auth::JwtConfig;
use gateway::rate_limit::RateLimiter;
use gateway::k_anonymity::KAnonymityEnforcer;
use gateway::audit::AuditLogger;
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

    let app = build_gateway_router(gateway_state);

    // ── Start HTTP Server ───────────────────────────────────────
    let addr = format!("{}:{}", host, port);
    tracing::info!(addr = %addr, "Starting HTTP server");

    let listener = tokio::net::TcpListener::bind(&addr).await?;
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    // ── Graceful Shutdown ───────────────────────────────────────
    tracing::info!("Shutting down...");
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
