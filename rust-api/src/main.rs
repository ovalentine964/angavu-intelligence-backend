mod config;
mod error;
mod middleware;
mod models;
mod routes;

use std::net::SocketAddr;
use std::sync::Arc;

use tokio::signal;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

use config::AppConfig;
use middleware::{cors_layer, rate_limit_layer, request_id_layer, RateLimiter};

/// Shared application state available to all handlers via `State(state)`.
#[derive(Debug, Clone)]
pub struct AppState {
    /// Application configuration.
    pub config: Arc<AppConfig>,
    /// Rate limiter instance.
    pub rate_limiter: RateLimiter,
    // TODO: Add database pool when wired:
    // pub db: PgPool,
    // TODO: Add HTTP client for LLM proxy:
    // pub http_client: reqwest::Client,
}

#[tokio::main]
async fn main() {
    // ── Load configuration ────────────────────────────────────────────
    let config = AppConfig::from_env();

    // ── Initialize tracing / logging ──────────────────────────────────
    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(&config.log_level));

    tracing_subscriber::registry()
        .with(env_filter)
        .with(tracing_subscriber::fmt::layer().json())
        .init();

    tracing::info!(
        environment = %config.environment,
        host = %config.host,
        port = config.port,
        "Starting Angavu Intelligence API"
    );

    // ── Build shared state ────────────────────────────────────────────
    let rate_limiter = rate_limit_layer(
        config.rate_limit_max_requests,
        config.rate_limit_window_secs,
    );

    let state = AppState {
        config: Arc::new(config.clone()),
        rate_limiter,
    };

    // ── Build the application router ──────────────────────────────────
    // Middleware is applied bottom-up: outermost first.
    // The JWT secret is injected as a request extension so the auth
    // middleware (applied inside v1::routes) can read it.
    let app = routes::api_routes()
        .with_state(state)
        .layer(cors_layer(&config.cors_allowed_origins))
        .layer(request_id_layer())
        .layer(TraceLayer::new_for_http())
        .layer(axum::middleware::from_fn(inject_jwt_secret));

    // ── Bind and serve ────────────────────────────────────────────────
    let addr = SocketAddr::new(
        config.host.parse().expect("Invalid HOST address"),
        config.port,
    );

    tracing::info!(%addr, "Listening");

    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("Failed to bind TCP listener");

    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .expect("Server error");

    tracing::info!("Server shut down gracefully");
}

/// Middleware that injects the JWT secret into request extensions
/// so the auth middleware can retrieve it.
async fn inject_jwt_secret(
    mut req: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    // AppState is already in extensions via with_state(); extract the secret.
    let jwt_secret = req
        .extensions()
        .get::<AppState>()
        .map(|s| s.config.jwt_secret.clone())
        .unwrap_or_default();

    req.extensions_mut().insert(jwt_secret);
    next.run(req).await
}

/// Wait for a termination signal (SIGINT / SIGTERM) to trigger graceful shutdown.
async fn shutdown_signal() {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .expect("Failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())
            .expect("Failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {
            tracing::info!("Received Ctrl+C, shutting down…");
        }
        _ = terminate => {
            tracing::info!("Received SIGTERM, shutting down…");
        }
    }
}
