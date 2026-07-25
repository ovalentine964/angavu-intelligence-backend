use anyhow::Result;
use clickhouse::Client;
use serde::{Deserialize, Serialize};
use crate::models::ClickHouseConfig;

pub fn create_client(config: &ClickHouseConfig) -> Result<Client> {
    let client = Client::default()
        .with_url(&config.url)
        .with_database(&config.database)
        .with_user(&config.user)
        .with_password(&config.password);

    Ok(client)
}

/// Run ClickHouse schema migrations (CREATE TABLE IF NOT EXISTS)
pub async fn run_migrations(client: &Client) -> Result<()> {
    let statements = vec![
        // Revenue events
        r#"
        CREATE TABLE IF NOT EXISTS revenue_events (
            event_id String,
            organization_id String,
            customer_id String,
            amount Float64,
            currency String,
            event_type String,
            event_time DateTime,
            metadata String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(event_time)
        ORDER BY (organization_id, event_time)
        TTL event_time + INTERVAL 2 YEAR
        "#,
        // Customer events
        r#"
        CREATE TABLE IF NOT EXISTS customer_events (
            event_id String,
            organization_id String,
            customer_id String,
            event_type String,
            event_data String,
            event_time DateTime,
            session_id String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(event_time)
        ORDER BY (organization_id, customer_id, event_time)
        TTL event_time + INTERVAL 2 YEAR
        "#,
        // Intelligence metrics
        r#"
        CREATE TABLE IF NOT EXISTS intelligence_metrics (
            metric_id String,
            organization_id String,
            module String,
            metric_name String,
            metric_value Float64,
            metric_time DateTime,
            metadata String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(metric_time)
        ORDER BY (organization_id, module, metric_time)
        TTL metric_time + INTERVAL 1 YEAR
        "#,
        // System events
        r#"
        CREATE TABLE IF NOT EXISTS system_events (
            event_id String,
            event_type String,
            component String,
            severity String,
            message String,
            duration_ms UInt64,
            event_time DateTime,
            metadata String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(event_time)
        ORDER BY (event_type, event_time)
        TTL event_time + INTERVAL 6 MONTH
        "#,
        // Federated metrics
        r#"
        CREATE TABLE IF NOT EXISTS federated_metrics (
            metric_id String,
            model_id String,
            round_number UInt32,
            participant_count UInt32,
            avg_loss Float64,
            avg_accuracy Float64,
            convergence_rate Float64,
            metric_time DateTime
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(metric_time)
        ORDER BY (model_id, round_number, metric_time)
        TTL metric_time + INTERVAL 1 YEAR
        "#,
    ];

    for stmt in statements {
        client.query(stmt).execute().await?;
    }

    Ok(())
}

/// Analytics repository for OLAP queries
pub struct AnalyticsRepository {
    client: Client,
}

impl AnalyticsRepository {
    pub fn new(client: Client) -> Self {
        Self { client }
    }

    /// Store revenue event
    pub async fn store_revenue_event(&self, event: &RevenueEvent) -> Result<()> {
        let mut insert = self.client.insert("revenue_events")?;
        insert.write(event).await?;
        insert.end().await?;
        Ok(())
    }

    /// Get revenue by period — parameterized to prevent SQL injection
    pub async fn get_revenue_by_period(
        &self,
        org_id: &str,
        start: chrono::NaiveDateTime,
        end: chrono::NaiveDateTime,
    ) -> Result<Vec<RevenueAggregation>> {
        let query = r#"
            SELECT 
                toStartOfDay(event_time) as period,
                sum(amount) as total_revenue,
                count() as transaction_count,
                avg(amount) as avg_transaction
            FROM revenue_events
            WHERE organization_id = ?
            AND event_time BETWEEN ? AND ?
            GROUP BY period
            ORDER BY period
        "#;

        let result = self.client
            .query(query)
            .bind(org_id)
            .bind(start)
            .bind(end)
            .fetch_all::<RevenueAggregation>()
            .await?;
        Ok(result)
    }

    /// Store customer event
    pub async fn store_customer_event(&self, event: &CustomerEvent) -> Result<()> {
        let mut insert = self.client.insert("customer_events")?;
        insert.write(event).await?;
        insert.end().await?;
        Ok(())
    }

    /// Get customer behavior patterns — parameterized to prevent SQL injection
    pub async fn get_customer_patterns(
        &self,
        org_id: &str,
        days: i32,
    ) -> Result<Vec<CustomerPattern>> {
        let query = r#"
            SELECT 
                customer_id,
                count() as event_count,
                uniq(event_type) as unique_events,
                min(event_time) as first_seen,
                max(event_time) as last_seen,
                sum(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) as purchases
            FROM customer_events
            WHERE organization_id = ?
            AND event_time >= now() - INTERVAL ? DAY
            GROUP BY customer_id
            ORDER BY event_count DESC
        "#;

        let result = self.client
            .query(query)
            .bind(org_id)
            .bind(days)
            .fetch_all::<CustomerPattern>()
            .await?;
        Ok(result)
    }

    /// Store intelligence metric
    pub async fn store_intelligence_metric(&self, metric: &IntelligenceMetric) -> Result<()> {
        let mut insert = self.client.insert("intelligence_metrics")?;
        insert.write(metric).await?;
        insert.end().await?;
        Ok(())
    }

    /// Get intelligence metrics over time — parameterized to prevent SQL injection
    pub async fn get_intelligence_metrics(
        &self,
        org_id: &str,
        module: &str,
        hours: i32,
    ) -> Result<Vec<IntelligenceMetric>> {
        let query = r#"
            SELECT *
            FROM intelligence_metrics
            WHERE organization_id = ?
            AND module = ?
            AND metric_time >= now() - INTERVAL ? HOUR
            ORDER BY metric_time DESC
        "#;

        let result = self.client
            .query(query)
            .bind(org_id)
            .bind(module)
            .bind(hours)
            .fetch_all::<IntelligenceMetric>()
            .await?;
        Ok(result)
    }

    /// Store system event
    pub async fn store_system_event(&self, event: &SystemEvent) -> Result<()> {
        let mut insert = self.client.insert("system_events")?;
        insert.write(event).await?;
        insert.end().await?;
        Ok(())
    }

    /// Get system health metrics — parameterized to prevent SQL injection
    pub async fn get_system_health(
        &self,
        hours: i32,
    ) -> Result<Vec<SystemHealthMetric>> {
        let query = r#"
            SELECT 
                toStartOfHour(event_time) as hour,
                event_type,
                count() as event_count,
                avg(duration_ms) as avg_duration,
                quantile(0.95)(duration_ms) as p95_duration
            FROM system_events
            WHERE event_time >= now() - INTERVAL ? HOUR
            GROUP BY hour, event_type
            ORDER BY hour DESC, event_type
        "#;

        let result = self.client
            .query(query)
            .bind(hours)
            .fetch_all::<SystemHealthMetric>()
            .await?;
        Ok(result)
    }

    /// Store federated learning metrics
    pub async fn store_federated_metric(&self, metric: &FederatedMetric) -> Result<()> {
        let mut insert = self.client.insert("federated_metrics")?;
        insert.write(metric).await?;
        insert.end().await?;
        Ok(())
    }
}

/// ClickHouse data models
#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct RevenueEvent {
    pub event_id: String,
    pub organization_id: String,
    pub customer_id: String,
    pub amount: f64,
    pub currency: String,
    pub event_type: String,
    pub event_time: chrono::NaiveDateTime,
    pub metadata: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct RevenueAggregation {
    pub period: chrono::NaiveDateTime,
    pub total_revenue: f64,
    pub transaction_count: u64,
    pub avg_transaction: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct CustomerEvent {
    pub event_id: String,
    pub organization_id: String,
    pub customer_id: String,
    pub event_type: String,
    pub event_data: String,
    pub event_time: chrono::NaiveDateTime,
    pub session_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct CustomerPattern {
    pub customer_id: String,
    pub event_count: u64,
    pub unique_events: u64,
    pub first_seen: chrono::NaiveDateTime,
    pub last_seen: chrono::NaiveDateTime,
    pub purchases: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct IntelligenceMetric {
    pub metric_id: String,
    pub organization_id: String,
    pub module: String,
    pub metric_name: String,
    pub metric_value: f64,
    pub metric_time: chrono::NaiveDateTime,
    pub metadata: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct SystemEvent {
    pub event_id: String,
    pub event_type: String,
    pub component: String,
    pub severity: String,
    pub message: String,
    pub duration_ms: u64,
    pub event_time: chrono::NaiveDateTime,
    pub metadata: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct SystemHealthMetric {
    pub hour: chrono::NaiveDateTime,
    pub event_type: String,
    pub event_count: u64,
    pub avg_duration: f64,
    pub p95_duration: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, clickhouse::Row)]
pub struct FederatedMetric {
    pub metric_id: String,
    pub model_id: String,
    pub round_number: u32,
    pub participant_count: u32,
    pub avg_loss: f64,
    pub avg_accuracy: f64,
    pub convergence_rate: f64,
    pub metric_time: chrono::NaiveDateTime,
}
