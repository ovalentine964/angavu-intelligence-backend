pub mod postgres;
pub mod redis;
pub mod clickhouse;

use std::sync::Arc;
use crate::models::Config;
use crate::superagent::OODAOrchestrator;

/// Application state shared across handlers
pub struct AppState {
    pub db: DatabaseConnections,
    pub orchestrator: Arc<OODAOrchestrator>,
    pub config: Config,
}

/// All database connections
#[derive(Clone)]
pub struct DatabaseConnections {
    pub postgres: sqlx::PgPool,
    pub redis: redis::aio::ConnectionManager,
    pub clickhouse: clickhouse::Client,
}

impl DatabaseConnections {
    pub async fn new(config: &Config) -> anyhow::Result<Self> {
        let postgres = postgres::create_pool(&config.database).await?;
        let redis = redis::create_connection(&config.redis).await?;
        let clickhouse = clickhouse::create_client(&config.clickhouse).await?;

        Ok(Self {
            postgres,
            redis,
            clickhouse,
        })
    }
}
