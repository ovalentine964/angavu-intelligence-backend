//! Angavu Intelligence Backend
//! 
//! A superagent-powered revenue intelligence platform built in Rust with Axum.
//! Python is used ONLY for LLM inference via PyO3.

use anyhow::Result;
use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post, put, delete},
    Json, Router,
};
use clap::Parser;
use std::sync::Arc;
use tokio::net::TcpListener;
use tower::ServiceBuilder;
use tower_http::{
    compression::CompressionLayer,
    cors::{Any, CorsLayer},
    limit::RequestBodyLimitLayer,
    timeout::TimeoutLayer,
    trace::TraceLayer,
};
use tracing::{info, warn};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod api;
mod billing;
mod db;
mod models;
mod security;
mod tools;
mod superagent;

use crate::db::{AppState, DatabaseConnections};
use crate::superagent::OODAOrchestrator;

/// CLI arguments
#[derive(Parser, Debug)]
#[command(name = "angavu-server", about = "Angavu Intelligence Backend Server")]
struct Args {
    /// Server host
    #[arg(long, default_value = "0.0.0.0")]
    host: String,

    /// Server port
    #[arg(long, default_value_t = 8080)]
    port: u16,

    /// Config file path
    #[arg(long, default_value = "config.toml")]
    config: String,

    /// Log level
    #[arg(long, default_value = "info")]
    log_level: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| "angavu=debug,tower_http=debug".into()))
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    let args = Args::parse();
    info!("Starting Angavu Intelligence Backend on {}:{}", args.host, args.port);

    // Load configuration
    let config = load_config(&args.config)?;
    
    // Initialize database connections
    let db_conns = DatabaseConnections::new(&config).await?;
    info!("Database connections established");

    // Build application state with all 26 tools wired in
    let state = AppState::new(db_conns, config.clone()).await?;
    info!("All 26 tools + OODA orchestrator initialized");

    // Build router
    let app = build_router(state);

    // Start server
    let listener = TcpListener::bind(format!("{}:{}", args.host, args.port)).await?;
    info!("Listening on {}", listener.local_addr()?);
    
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;

    Ok(())
}

fn build_router(state: Arc<AppState>) -> Router {
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);

    Router::new()
        // Health & Status
        .route("/health", get(health_check))
        .route("/ready", get(readiness_check))
        .route("/metrics", get(metrics_handler))
        
        // API v1
        .nest("/api/v1", api::v1::router())
        
        // WebSocket — TODO: uncomment when api::ws is implemented
        // .route("/ws", get(api::ws::websocket_handler))
        
        // Superagent endpoints
        .nest("/superagent", superagent::router())
        
        // Middleware
        .layer(
            ServiceBuilder::new()
                .layer(TraceLayer::new_for_http())
                .layer(cors)
                .layer(CompressionLayer::new())
                .layer(TimeoutLayer::new(std::time::Duration::from_secs(30)))
                .layer(RequestBodyLimitLayer::new(10 * 1024 * 1024)) // 10MB
        )
        .with_state(state)
}

async fn health_check() -> impl IntoResponse {
    Json(serde_json::json!({
        "status": "healthy",
        "service": "angavu-intelligence-backend",
        "version": env!("CARGO_PKG_VERSION"),
        "timestamp": chrono::Utc::now().to_rfc3339(),
    }))
}

async fn readiness_check(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let pg_ok = state.db.postgres.acquire().await.is_ok();
    let redis_ok = redis::cmd("PING")
        .query_async::<String>(&mut state.db.redis.clone())
        .await
        .is_ok();
    
    if pg_ok && redis_ok {
        (StatusCode::OK, Json(serde_json::json!({
            "status": "ready",
            "postgres": "connected",
            "redis": "connected",
        })))
    } else {
        (StatusCode::SERVICE_UNAVAILABLE, Json(serde_json::json!({
            "status": "not_ready",
            "postgres": if pg_ok { "connected" } else { "disconnected" },
            "redis": if redis_ok { "connected" } else { "disconnected" },
        })))
    }
}

async fn metrics_handler() -> impl IntoResponse {
    // Prometheus metrics endpoint
    let metrics = metrics_exporter_prometheus::PrometheusBuilder::new();
    "Metrics endpoint"
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

    warn!("Shutdown signal received, starting graceful shutdown");
}

fn load_config(path: &str) -> Result<models::Config> {
    let config_content = std::fs::read_to_string(path).unwrap_or_else(|_| {
        warn!("Config file not found, using defaults");
        String::new()
    });
    
    let config: models::Config = toml::from_str(&config_content).unwrap_or_default();
    Ok(config)
}
