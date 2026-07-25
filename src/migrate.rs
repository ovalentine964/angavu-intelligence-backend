//! Database migration runner binary.
//!
//! Runs all SQL migrations from the `migrations/` directory against the
//! PostgreSQL database specified by the `DATABASE_URL` environment variable.
//!
//! Usage:
//!   DATABASE_URL=postgres://user:pass@host/db cargo run --bin angavu-migrate

use anyhow::{Context, Result};
use sqlx::postgres::PgPoolOptions;
use tracing::info;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()),
        )
        .init();

    let database_url = std::env::var("DATABASE_URL")
        .context("DATABASE_URL environment variable must be set")?;

    info!("Connecting to database…");

    let pool = PgPoolOptions::new()
        .max_connections(5)
        .acquire_timeout(std::time::Duration::from_secs(30))
        .connect(&database_url)
        .await
        .context("Failed to connect to PostgreSQL")?;

    info!("Running migrations from migrations/ directory…");

    let migration_result = sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .context("Failed to run database migrations")?;

    info!(
        migrations_applied = ?migration_result,
        "All migrations applied successfully"
    );

    // Verify connectivity after migration
    let row: (i64,) = sqlx::query_as("SELECT 1")
        .fetch_one(&pool)
        .await
        .context("Post-migration connectivity check failed")?;
    assert_eq!(row.0, 1);
    info!("Post-migration connectivity check passed");

    pool.close().await;
    info!("Database connection closed. Migration complete.");

    Ok(())
}
