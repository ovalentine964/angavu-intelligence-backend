use anyhow::Result;
use sqlx::postgres::{PgPool, PgPoolOptions};
use crate::models::DatabaseConfig;

pub async fn create_pool(config: &DatabaseConfig) -> Result<PgPool> {
    let pool = PgPoolOptions::new()
        .max_connections(config.max_connections)
        .min_connections(config.min_connections)
        .acquire_timeout(std::time::Duration::from_secs(config.connect_timeout))
        .idle_timeout(std::time::Duration::from_secs(config.idle_timeout))
        .connect(&config.url)
        .await?;

    // Run migrations
    sqlx::migrate!("./migrations").run(&pool).await?;

    Ok(pool)
}

/// User repository
pub struct UserRepository {
    pool: PgPool,
}

impl UserRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create(&self, email: &str, username: &str, password_hash: &str, role: &str, org_id: uuid::Uuid) -> Result<crate::models::User> {
        let user = sqlx::query_as!(
            crate::models::User,
            r#"
            INSERT INTO users (id, email, username, password_hash, role, organization_id, is_active, created_at, updated_at, metadata)
            VALUES ($1, $2, $3, $4, $5::user_role, $6, true, NOW(), NOW(), '{}')
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            email,
            username,
            password_hash,
            role,
            org_id
        )
        .fetch_one(&self.pool)
        .await?;

        Ok(user)
    }

    pub async fn find_by_email(&self, email: &str) -> Result<Option<crate::models::User>> {
        let user = sqlx::query_as!(
            crate::models::User,
            "SELECT * FROM users WHERE email = $1",
            email
        )
        .fetch_optional(&self.pool)
        .await?;

        Ok(user)
    }

    pub async fn find_by_id(&self, id: uuid::Uuid) -> Result<Option<crate::models::User>> {
        let user = sqlx::query_as!(
            crate::models::User,
            "SELECT * FROM users WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await?;

        Ok(user)
    }

    pub async fn update(&self, id: uuid::Uuid, email: Option<&str>, username: Option<&str>, role: Option<&str>) -> Result<crate::models::User> {
        let user = sqlx::query_as!(
            crate::models::User,
            r#"
            UPDATE users 
            SET email = COALESCE($2, email),
                username = COALESCE($3, username),
                role = COALESCE($4::user_role, role),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            "#,
            id,
            email,
            username,
            role
        )
        .fetch_one(&self.pool)
        .await?;

        Ok(user)
    }

    pub async fn delete(&self, id: uuid::Uuid) -> Result<()> {
        sqlx::query!("DELETE FROM users WHERE id = $1", id)
            .execute(&self.pool)
            .await?;

        Ok(())
    }

    pub async fn list(&self, page: i64, per_page: i64) -> Result<(Vec<crate::models::User>, i64)> {
        let offset = (page - 1) * per_page;
        
        let users = sqlx::query_as!(
            crate::models::User,
            "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            per_page,
            offset
        )
        .fetch_all(&self.pool)
        .await?;

        let total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM users")
            .fetch_one(&self.pool)
            .await?;

        Ok((users, total.0))
    }
}

/// Intelligence repository
pub struct IntelligenceRepository {
    pool: PgPool,
}

impl IntelligenceRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create_task(&self, module: &str, org_id: uuid::Uuid, created_by: uuid::Uuid, input: serde_json::Value) -> Result<crate::models::IntelligenceTask> {
        let task = sqlx::query_as!(
            crate::models::IntelligenceTask,
            r#"
            INSERT INTO intelligence_tasks (id, module, phase, status, input_data, created_at, created_by, organization_id, metadata)
            VALUES ($1, $2::intelligence_module, 'observe', 'pending', $3, NOW(), $4, $5, '{}')
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            module,
            input,
            created_by,
            org_id
        )
        .fetch_one(&self.pool)
        .await?;

        Ok(task)
    }

    pub async fn update_task_status(&self, id: uuid::Uuid, status: &str, output: Option<serde_json::Value>, error: Option<&str>) -> Result<()> {
        sqlx::query!(
            r#"
            UPDATE intelligence_tasks 
            SET status = $2::task_status,
                output_data = $3,
                error = $4,
                completed_at = CASE WHEN $2 IN ('completed', 'failed') THEN NOW() ELSE completed_at END
            WHERE id = $1
            "#,
            id,
            status,
            output,
            error
        )
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn get_tasks_by_org(&self, org_id: uuid::Uuid, page: i64, per_page: i64) -> Result<Vec<crate::models::IntelligenceTask>> {
        let offset = (page - 1) * per_page;
        
        let tasks = sqlx::query_as!(
            crate::models::IntelligenceTask,
            "SELECT * FROM intelligence_tasks WHERE organization_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            org_id,
            per_page,
            offset
        )
        .fetch_all(&self.pool)
        .await?;

        Ok(tasks)
    }

    pub async fn save_forecast(&self, forecast: &crate::models::RevenueForecast) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO revenue_forecasts (id, organization_id, forecast_date, period_start, period_end, predicted_revenue, confidence_lower, confidence_upper, confidence_level, model_version, features_used, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            "#,
            forecast.id,
            forecast.organization_id,
            forecast.forecast_date,
            forecast.period_start,
            forecast.period_end,
            forecast.predicted_revenue,
            forecast.confidence_lower,
            forecast.confidence_upper,
            forecast.confidence_level,
            forecast.model_version,
            forecast.features_used,
            forecast.created_at
        )
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn save_churn_prediction(&self, prediction: &crate::models::ChurnPrediction) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO churn_predictions (id, customer_id, organization_id, churn_probability, churn_risk, key_factors, retention_actions, predicted_churn_date, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            "#,
            prediction.id,
            prediction.customer_id,
            prediction.organization_id,
            prediction.churn_probability,
            prediction.churn_risk,
            prediction.key_factors,
            prediction.retention_actions,
            prediction.predicted_churn_date,
            prediction.created_at
        )
        .execute(&self.pool)
        .await?;

        Ok(())
    }
}

/// Memory repository
pub struct MemoryRepository {
    pool: PgPool,
}

impl MemoryRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn store(&self, entry: &crate::models::MemoryEntry) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO memory_entries (id, user_id, organization_id, layer, content, embedding, importance_score, access_count, last_accessed, expires_at, metadata, tags, source, created_at, updated_at)
            VALUES ($1, $2, $3, $4::memory_layer, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            "#,
            entry.id,
            entry.user_id,
            entry.organization_id,
            entry.layer as crate::models::MemoryLayer,
            entry.content,
            entry.embedding.as_deref(),
            entry.importance_score,
            entry.access_count,
            entry.last_accessed,
            entry.expires_at,
            entry.metadata,
            &entry.tags,
            entry.source,
            entry.created_at,
            entry.updated_at
        )
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn search(&self, user_id: uuid::Uuid, query_embedding: &[f32], limit: i32) -> Result<Vec<crate::models::MemoryEntry>> {
        let entries = sqlx::query_as!(
            crate::models::MemoryEntry,
            r#"
            SELECT * FROM memory_entries 
            WHERE user_id = $1 
            AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY embedding <=> $2
            LIMIT $3
            "#,
            user_id,
            query_embedding,
            limit
        )
        .fetch_all(&self.pool)
        .await?;

        Ok(entries)
    }

    pub async fn get_by_layer(&self, user_id: uuid::Uuid, layer: &str) -> Result<Vec<crate::models::MemoryEntry>> {
        let entries = sqlx::query_as!(
            crate::models::MemoryEntry,
            "SELECT * FROM memory_entries WHERE user_id = $1 AND layer = $2::memory_layer ORDER BY importance_score DESC",
            user_id,
            layer
        )
        .fetch_all(&self.pool)
        .await?;

        Ok(entries)
    }

    pub async fn consolidate(&self, source_layer: &str, target_layer: &str, max_entries: i32) -> Result<i32> {
        let result = sqlx::query!(
            r#"
            UPDATE memory_entries 
            SET layer = $2::memory_layer, updated_at = NOW()
            WHERE id IN (
                SELECT id FROM memory_entries 
                WHERE layer = $1::memory_layer 
                ORDER BY importance_score DESC 
                LIMIT $3
            )
            "#,
            source_layer,
            target_layer,
            max_entries
        )
        .execute(&self.pool)
        .await?;

        Ok(result.rows_affected() as i32)
    }
}
