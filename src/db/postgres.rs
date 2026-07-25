use anyhow::{Context, Result};
use sqlx::postgres::{PgPool, PgPoolOptions};
use crate::models::DatabaseConfig;

/// Create a PostgreSQL connection pool with retry logic and proper error context.
pub async fn create_pool(config: &DatabaseConfig) -> Result<PgPool> {
    let pool = connect_with_retry(config).await?;

    // Run migrations
    sqlx::migrate!("./migrations")
        .run(&pool)
        .await
        .context("Failed to run database migrations")?;

    Ok(pool)
}

/// Attempt to connect with exponential backoff (3 retries).
async fn connect_with_retry(config: &DatabaseConfig) -> Result<PgPool> {
    let max_retries = 3;
    let mut attempt = 0;

    loop {
        attempt += 1;
        let result = PgPoolOptions::new()
            .max_connections(config.max_connections)
            .min_connections(config.min_connections)
            .acquire_timeout(std::time::Duration::from_secs(config.connect_timeout))
            .idle_timeout(std::time::Duration::from_secs(config.idle_timeout))
            .connect(&config.url)
            .await;

        match result {
            Ok(pool) => {
                tracing::info!("PostgreSQL connection pool established (attempt {attempt})");
                return Ok(pool);
            }
            Err(e) if attempt < max_retries => {
                let backoff = std::time::Duration::from_secs(2u64.pow(attempt as u32));
                tracing::warn!(
                    error = %e,
                    attempt,
                    max_retries,
                    backoff_secs = backoff.as_secs(),
                    "PostgreSQL connection failed, retrying…"
                );
                tokio::time::sleep(backoff).await;
            }
            Err(e) => {
                return Err(e).context(format!(
                    "Failed to connect to PostgreSQL after {max_retries} attempts. \
                     Verify that the database is running and accessible at the configured URL."
                ));
            }
        }
    }
}

// ================================================================
//  USER REPOSITORY
// ================================================================

pub struct UserRepository {
    pool: PgPool,
}

impl UserRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create(
        &self,
        email: &str,
        username: &str,
        password_hash: &str,
        role: &str,
        org_id: uuid::Uuid,
    ) -> Result<crate::models::User> {
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
        .await
        .context("Failed to create user")?;

        Ok(user)
    }

    pub async fn find_by_email(&self, email: &str) -> Result<Option<crate::models::User>> {
        let user = sqlx::query_as!(
            crate::models::User,
            "SELECT * FROM users WHERE email = $1",
            email
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to find user by email")?;

        Ok(user)
    }

    pub async fn find_by_id(&self, id: uuid::Uuid) -> Result<Option<crate::models::User>> {
        let user = sqlx::query_as!(
            crate::models::User,
            "SELECT * FROM users WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to find user by id")?;

        Ok(user)
    }

    pub async fn update(
        &self,
        id: uuid::Uuid,
        email: Option<&str>,
        username: Option<&str>,
        role: Option<&str>,
    ) -> Result<crate::models::User> {
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
        .await
        .context("Failed to update user")?;

        Ok(user)
    }

    pub async fn delete(&self, id: uuid::Uuid) -> Result<()> {
        sqlx::query!("DELETE FROM users WHERE id = $1", id)
            .execute(&self.pool)
            .await
            .context("Failed to delete user")?;
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
        .await
        .context("Failed to list users")?;

        let total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM users")
            .fetch_one(&self.pool)
            .await
            .context("Failed to count users")?;

        Ok((users, total.0))
    }

    pub async fn list_by_org(
        &self,
        org_id: uuid::Uuid,
        page: i64,
        per_page: i64,
    ) -> Result<(Vec<crate::models::User>, i64)> {
        let offset = (page - 1) * per_page;

        let users = sqlx::query_as!(
            crate::models::User,
            "SELECT * FROM users WHERE organization_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            org_id,
            per_page,
            offset
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to list users by organization")?;

        let total: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM users WHERE organization_id = $1")
                .bind(org_id)
                .fetch_one(&self.pool)
                .await
                .context("Failed to count users by organization")?;

        Ok((users, total.0))
    }
}

// ================================================================
//  ORGANIZATION REPOSITORY
// ================================================================

pub struct OrganizationRepository {
    pool: PgPool,
}

impl OrganizationRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create(
        &self,
        name: &str,
        slug: &str,
        plan: &str,
        max_users: i32,
        max_api_calls: i64,
    ) -> Result<crate::models::Organization> {
        let org = sqlx::query_as!(
            crate::models::Organization,
            r#"
            INSERT INTO organizations (id, name, slug, plan, max_users, max_api_calls, created_at, updated_at, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW(), '{}')
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            name,
            slug,
            plan,
            max_users,
            max_api_calls
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to create organization")?;

        Ok(org)
    }

    pub async fn find_by_id(&self, id: uuid::Uuid) -> Result<Option<crate::models::Organization>> {
        let org = sqlx::query_as!(
            crate::models::Organization,
            "SELECT * FROM organizations WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to find organization by id")?;

        Ok(org)
    }

    pub async fn find_by_slug(
        &self,
        slug: &str,
    ) -> Result<Option<crate::models::Organization>> {
        let org = sqlx::query_as!(
            crate::models::Organization,
            "SELECT * FROM organizations WHERE slug = $1",
            slug
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to find organization by slug")?;

        Ok(org)
    }

    pub async fn update(
        &self,
        id: uuid::Uuid,
        name: Option<&str>,
        plan: Option<&str>,
        max_users: Option<i32>,
        max_api_calls: Option<i64>,
    ) -> Result<crate::models::Organization> {
        let org = sqlx::query_as!(
            crate::models::Organization,
            r#"
            UPDATE organizations
            SET name = COALESCE($2, name),
                plan = COALESCE($3, plan),
                max_users = COALESCE($4, max_users),
                max_api_calls = COALESCE($5, max_api_calls),
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
            "#,
            id,
            name,
            plan,
            max_users,
            max_api_calls
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to update organization")?;

        Ok(org)
    }

    pub async fn delete(&self, id: uuid::Uuid) -> Result<()> {
        sqlx::query!("DELETE FROM organizations WHERE id = $1", id)
            .execute(&self.pool)
            .await
            .context("Failed to delete organization")?;
        Ok(())
    }

    pub async fn list(&self, page: i64, per_page: i64) -> Result<(Vec<crate::models::Organization>, i64)> {
        let offset = (page - 1) * per_page;

        let orgs = sqlx::query_as!(
            crate::models::Organization,
            "SELECT * FROM organizations ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            per_page,
            offset
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to list organizations")?;

        let total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM organizations")
            .fetch_one(&self.pool)
            .await
            .context("Failed to count organizations")?;

        Ok((orgs, total.0))
    }
}

// ================================================================
//  INTELLIGENCE REPOSITORY
// ================================================================

pub struct IntelligenceRepository {
    pool: PgPool,
}

impl IntelligenceRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create_task(
        &self,
        module: &str,
        org_id: uuid::Uuid,
        created_by: uuid::Uuid,
        input: serde_json::Value,
    ) -> Result<crate::models::IntelligenceTask> {
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
        .await
        .context("Failed to create intelligence task")?;

        Ok(task)
    }

    pub async fn update_task_status(
        &self,
        id: uuid::Uuid,
        status: &str,
        output: Option<serde_json::Value>,
        error: Option<&str>,
    ) -> Result<()> {
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
        .await
        .context("Failed to update task status")?;

        Ok(())
    }

    pub async fn get_task_by_id(
        &self,
        id: uuid::Uuid,
    ) -> Result<Option<crate::models::IntelligenceTask>> {
        let task = sqlx::query_as!(
            crate::models::IntelligenceTask,
            "SELECT * FROM intelligence_tasks WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to get task by id")?;

        Ok(task)
    }

    pub async fn get_tasks_by_org(
        &self,
        org_id: uuid::Uuid,
        page: i64,
        per_page: i64,
    ) -> Result<Vec<crate::models::IntelligenceTask>> {
        let offset = (page - 1) * per_page;

        let tasks = sqlx::query_as!(
            crate::models::IntelligenceTask,
            "SELECT * FROM intelligence_tasks WHERE organization_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            org_id,
            per_page,
            offset
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to get tasks by organization")?;

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
        .await
        .context("Failed to save revenue forecast")?;

        Ok(())
    }

    pub async fn save_churn_prediction(
        &self,
        prediction: &crate::models::ChurnPrediction,
    ) -> Result<()> {
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
            &prediction.retention_actions,
            prediction.predicted_churn_date,
            prediction.created_at
        )
        .execute(&self.pool)
        .await
        .context("Failed to save churn prediction")?;

        Ok(())
    }

    pub async fn save_customer_behavior(
        &self,
        behavior: &crate::models::CustomerBehavior,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO customer_behaviors (id, customer_id, organization_id, behavior_type, score, features, segments, risk_level, analyzed_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            "#,
            behavior.id,
            behavior.customer_id,
            behavior.organization_id,
            behavior.behavior_type,
            behavior.score,
            behavior.features,
            &behavior.segments,
            behavior.risk_level,
            behavior.analyzed_at,
            behavior.created_at
        )
        .execute(&self.pool)
        .await
        .context("Failed to save customer behavior")?;

        Ok(())
    }

    pub async fn save_market_analysis(
        &self,
        analysis: &crate::models::MarketAnalysis,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO market_analyses (id, organization_id, market_segment, analysis_type, metrics, insights, recommendations, confidence_score, period, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            "#,
            analysis.id,
            analysis.organization_id,
            analysis.market_segment,
            analysis.analysis_type,
            analysis.metrics,
            &analysis.insights,
            &analysis.recommendations,
            analysis.confidence_score,
            analysis.period,
            analysis.created_at
        )
        .execute(&self.pool)
        .await
        .context("Failed to save market analysis")?;

        Ok(())
    }

    pub async fn save_risk_assessment(
        &self,
        assessment: &crate::models::RiskAssessment,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO risk_assessments (id, organization_id, entity_type, entity_id, risk_score, risk_level, risk_factors, mitigation_strategies, assessed_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            "#,
            assessment.id,
            assessment.organization_id,
            assessment.entity_type,
            assessment.entity_id,
            assessment.risk_score,
            assessment.risk_level,
            assessment.risk_factors,
            &assessment.mitigation_strategies,
            assessment.assessed_at,
            assessment.created_at
        )
        .execute(&self.pool)
        .await
        .context("Failed to save risk assessment")?;

        Ok(())
    }

    pub async fn save_pricing_optimization(
        &self,
        pricing: &crate::models::PricingOptimization,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO pricing_optimizations (id, organization_id, product_id, current_price, recommended_price, expected_revenue_impact, elasticity, competitive_position, confidence, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            "#,
            pricing.id,
            pricing.organization_id,
            pricing.product_id,
            pricing.current_price,
            pricing.recommended_price,
            pricing.expected_revenue_impact,
            pricing.elasticity,
            pricing.competitive_position,
            pricing.confidence,
            pricing.created_at
        )
        .execute(&self.pool)
        .await
        .context("Failed to save pricing optimization")?;

        Ok(())
    }
}

// ================================================================
//  INTELLIGENCE INSIGHT REPOSITORY
// ================================================================

pub struct InsightRepository {
    pool: PgPool,
}

impl InsightRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create(
        &self,
        insight: &crate::models::IntelligenceInsight,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO intelligence_insights (id, organization_id, module, insight_type, title, description, severity, confidence, data, actionable, acknowledged, acknowledged_by, acknowledged_at, created_at)
            VALUES ($1, $2, $3::intelligence_module, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            "#,
            insight.id,
            insight.organization_id,
            insight.module as crate::models::IntelligenceModule,
            insight.insight_type,
            insight.title,
            insight.description,
            insight.severity,
            insight.confidence,
            insight.data,
            insight.actionable,
            insight.acknowledged,
            insight.acknowledged_by,
            insight.acknowledged_at,
            insight.created_at
        )
        .execute(&self.pool)
        .await
        .context("Failed to create intelligence insight")?;

        Ok(())
    }

    pub async fn list_by_org(
        &self,
        org_id: uuid::Uuid,
        page: i64,
        per_page: i64,
    ) -> Result<Vec<crate::models::IntelligenceInsight>> {
        let offset = (page - 1) * per_page;

        let insights = sqlx::query_as!(
            crate::models::IntelligenceInsight,
            "SELECT * FROM intelligence_insights WHERE organization_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            org_id,
            per_page,
            offset
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to list insights by organization")?;

        Ok(insights)
    }

    pub async fn acknowledge(
        &self,
        id: uuid::Uuid,
        acknowledged_by: uuid::Uuid,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            UPDATE intelligence_insights
            SET acknowledged = true, acknowledged_by = $2, acknowledged_at = NOW()
            WHERE id = $1
            "#,
            id,
            acknowledged_by
        )
        .execute(&self.pool)
        .await
        .context("Failed to acknowledge insight")?;

        Ok(())
    }
}

// ================================================================
//  AGENT REPOSITORY
// ================================================================

pub struct AgentRepository {
    pool: PgPool,
}

impl AgentRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create(
        &self,
        agent_type: &str,
        name: &str,
        description: &str,
        capabilities: &[String],
        config: serde_json::Value,
    ) -> Result<crate::models::Agent> {
        let agent = sqlx::query_as!(
            crate::models::Agent,
            r#"
            INSERT INTO agents (id, agent_type, name, description, status, capabilities, config, last_heartbeat, created_at, updated_at, metadata)
            VALUES ($1, $2, $3, $4, 'idle', $5, $6, NOW(), NOW(), NOW(), '{}')
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            agent_type,
            name,
            description,
            capabilities,
            config
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to create agent")?;

        Ok(agent)
    }

    pub async fn find_by_id(&self, id: uuid::Uuid) -> Result<Option<crate::models::Agent>> {
        let agent = sqlx::query_as!(
            crate::models::Agent,
            "SELECT * FROM agents WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to find agent by id")?;

        Ok(agent)
    }

    pub async fn update_status(&self, id: uuid::Uuid, status: &str) -> Result<()> {
        sqlx::query!(
            "UPDATE agents SET status = $2, updated_at = NOW(), last_heartbeat = NOW() WHERE id = $1",
            id,
            status
        )
        .execute(&self.pool)
        .await
        .context("Failed to update agent status")?;

        Ok(())
    }

    pub async fn heartbeat(&self, id: uuid::Uuid) -> Result<()> {
        sqlx::query!(
            "UPDATE agents SET last_heartbeat = NOW() WHERE id = $1",
            id
        )
        .execute(&self.pool)
        .await
        .context("Failed to update agent heartbeat")?;

        Ok(())
    }

    pub async fn list_active(&self) -> Result<Vec<crate::models::Agent>> {
        let agents = sqlx::query_as!(
            crate::models::Agent,
            "SELECT * FROM agents WHERE status != 'shutdown' ORDER BY last_heartbeat DESC"
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to list active agents")?;

        Ok(agents)
    }

    pub async fn create_task(
        &self,
        agent_id: uuid::Uuid,
        task_type: &str,
        priority: i32,
        input: serde_json::Value,
        created_by: uuid::Uuid,
    ) -> Result<crate::models::AgentTask> {
        let task = sqlx::query_as!(
            crate::models::AgentTask,
            r#"
            INSERT INTO agent_tasks (id, agent_id, task_type, priority, status, input, retry_count, max_retries, created_at, created_by)
            VALUES ($1, $2, $3, $4, 'pending', $5, 0, 3, NOW(), $6)
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            agent_id,
            task_type,
            priority,
            input,
            created_by
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to create agent task")?;

        Ok(task)
    }

    pub async fn update_task_status(
        &self,
        id: uuid::Uuid,
        status: &str,
        output: Option<serde_json::Value>,
        error: Option<&str>,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            UPDATE agent_tasks
            SET status = $2::task_status,
                output = $3,
                error = $4,
                started_at = CASE WHEN $2 = 'running' AND started_at IS NULL THEN NOW() ELSE started_at END,
                completed_at = CASE WHEN $2 IN ('completed', 'failed') THEN NOW() ELSE completed_at END
            WHERE id = $1
            "#,
            id,
            status,
            output,
            error
        )
        .execute(&self.pool)
        .await
        .context("Failed to update agent task status")?;

        Ok(())
    }

    pub async fn get_tasks_by_agent(
        &self,
        agent_id: uuid::Uuid,
        page: i64,
        per_page: i64,
    ) -> Result<Vec<crate::models::AgentTask>> {
        let offset = (page - 1) * per_page;

        let tasks = sqlx::query_as!(
            crate::models::AgentTask,
            "SELECT * FROM agent_tasks WHERE agent_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            agent_id,
            per_page,
            offset
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to get agent tasks")?;

        Ok(tasks)
    }
}

// ================================================================
//  MEMORY REPOSITORY
// ================================================================

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
        .await
        .context("Failed to store memory entry")?;

        Ok(())
    }

    pub async fn search(
        &self,
        user_id: uuid::Uuid,
        query_embedding: &[f32],
        limit: i32,
    ) -> Result<Vec<crate::models::MemoryEntry>> {
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
        .await
        .context("Failed to search memory entries")?;

        Ok(entries)
    }

    pub async fn get_by_layer(
        &self,
        user_id: uuid::Uuid,
        layer: &str,
    ) -> Result<Vec<crate::models::MemoryEntry>> {
        let entries = sqlx::query_as!(
            crate::models::MemoryEntry,
            "SELECT * FROM memory_entries WHERE user_id = $1 AND layer = $2::memory_layer ORDER BY importance_score DESC",
            user_id,
            layer
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to get memory entries by layer")?;

        Ok(entries)
    }

    pub async fn consolidate(
        &self,
        source_layer: &str,
        target_layer: &str,
        max_entries: i32,
    ) -> Result<i32> {
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
        .await
        .context("Failed to consolidate memory entries")?;

        Ok(result.rows_affected() as i32)
    }
}

// ================================================================
//  FEDERATED MODEL REPOSITORY
// ================================================================

pub struct FederatedModelRepository {
    pool: PgPool,
}

impl FederatedModelRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create(
        &self,
        model_name: &str,
        model_version: &str,
        global_weights: &[f32],
        participants: &[uuid::Uuid],
    ) -> Result<crate::models::FederatedModel> {
        let model = sqlx::query_as!(
            crate::models::FederatedModel,
            r#"
            INSERT INTO federated_models (id, model_name, model_version, global_weights, participants, round_number, status, metrics, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, 0, 'collecting', '{}', NOW(), NOW())
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            model_name,
            model_version,
            global_weights,
            participants
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to create federated model")?;

        Ok(model)
    }

    pub async fn find_by_id(
        &self,
        id: uuid::Uuid,
    ) -> Result<Option<crate::models::FederatedModel>> {
        let model = sqlx::query_as!(
            crate::models::FederatedModel,
            "SELECT * FROM federated_models WHERE id = $1",
            id
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to find federated model")?;

        Ok(model)
    }

    pub async fn update_status(&self, id: uuid::Uuid, status: &str) -> Result<()> {
        sqlx::query!(
            "UPDATE federated_models SET status = $2, updated_at = NOW() WHERE id = $1",
            id,
            status
        )
        .execute(&self.pool)
        .await
        .context("Failed to update federated model status")?;

        Ok(())
    }

    pub async fn update_round(
        &self,
        id: uuid::Uuid,
        round_number: i32,
        weights: &[f32],
        metrics: serde_json::Value,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            UPDATE federated_models 
            SET round_number = $2, global_weights = $3, metrics = $4, updated_at = NOW()
            WHERE id = $1
            "#,
            id,
            round_number,
            weights,
            metrics
        )
        .execute(&self.pool)
        .await
        .context("Failed to update federated model round")?;

        Ok(())
    }

    pub async fn list_active(&self) -> Result<Vec<crate::models::FederatedModel>> {
        let models = sqlx::query_as!(
            crate::models::FederatedModel,
            "SELECT * FROM federated_models WHERE status NOT IN ('completed', 'failed') ORDER BY updated_at DESC"
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to list active federated models")?;

        Ok(models)
    }

    pub async fn add_participant(
        &self,
        participant: &crate::models::FederatedParticipant,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            INSERT INTO federated_participants (id, model_id, user_id, device_id, local_weights, gradient_norm, data_samples, status, submitted_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::participant_status, $9, $10)
            "#,
            participant.id,
            participant.model_id,
            participant.user_id,
            participant.device_id,
            participant.local_weights.as_deref(),
            participant.gradient_norm,
            participant.data_samples,
            participant.status as crate::models::ParticipantStatus,
            participant.submitted_at,
            participant.created_at
        )
        .execute(&self.pool)
        .await
        .context("Failed to add federated participant")?;

        Ok(())
    }

    pub async fn update_participant_weights(
        &self,
        id: uuid::Uuid,
        weights: &[f32],
        gradient_norm: f64,
    ) -> Result<()> {
        sqlx::query!(
            r#"
            UPDATE federated_participants
            SET local_weights = $2, gradient_norm = $3, status = 'submitted', submitted_at = NOW()
            WHERE id = $1
            "#,
            id,
            weights,
            gradient_norm
        )
        .execute(&self.pool)
        .await
        .context("Failed to update participant weights")?;

        Ok(())
    }

    pub async fn get_participants(
        &self,
        model_id: uuid::Uuid,
    ) -> Result<Vec<crate::models::FederatedParticipant>> {
        let participants = sqlx::query_as!(
            crate::models::FederatedParticipant,
            "SELECT * FROM federated_participants WHERE model_id = $1 ORDER BY created_at",
            model_id
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to get federated participants")?;

        Ok(participants)
    }
}

// ================================================================
//  DEVICE SYNC REPOSITORY
// ================================================================

pub struct DeviceSyncRepository {
    pool: PgPool,
}

impl DeviceSyncRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn upsert(
        &self,
        user_id: uuid::Uuid,
        device_id: &str,
        device_type: &str,
        device_name: &str,
    ) -> Result<crate::models::DeviceSync> {
        let sync = sqlx::query_as!(
            crate::models::DeviceSync,
            r#"
            INSERT INTO device_syncs (id, user_id, device_id, device_type, device_name, last_sync, sync_version, status, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW(), 0, 'pending', '{}', NOW(), NOW())
            ON CONFLICT (user_id, device_id) DO UPDATE
            SET last_sync = NOW(), updated_at = NOW()
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            user_id,
            device_id,
            device_type,
            device_name
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to upsert device sync")?;

        Ok(sync)
    }

    pub async fn get_by_user(
        &self,
        user_id: uuid::Uuid,
    ) -> Result<Vec<crate::models::DeviceSync>> {
        let syncs = sqlx::query_as!(
            crate::models::DeviceSync,
            "SELECT * FROM device_syncs WHERE user_id = $1 ORDER BY last_sync DESC",
            user_id
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to get device syncs by user")?;

        Ok(syncs)
    }

    pub async fn update_version(
        &self,
        id: uuid::Uuid,
        version: i64,
        status: &str,
    ) -> Result<()> {
        sqlx::query!(
            "UPDATE device_syncs SET sync_version = $2, status = $3, last_sync = NOW(), updated_at = NOW() WHERE id = $1",
            id,
            version,
            status
        )
        .execute(&self.pool)
        .await
        .context("Failed to update device sync version")?;

        Ok(())
    }
}

// ================================================================
//  KNOWLEDGE GRAPH REPOSITORY
// ================================================================

pub struct KnowledgeRepository {
    pool: PgPool,
}

impl KnowledgeRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create_node(
        &self,
        org_id: uuid::Uuid,
        node_type: &str,
        label: &str,
        properties: serde_json::Value,
        embedding: Option<Vec<f32>>,
    ) -> Result<crate::models::KnowledgeNode> {
        let node = sqlx::query_as!(
            crate::models::KnowledgeNode,
            r#"
            INSERT INTO knowledge_nodes (id, organization_id, node_type, label, properties, embedding, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            org_id,
            node_type,
            label,
            properties,
            embedding
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to create knowledge node")?;

        Ok(node)
    }

    pub async fn create_edge(
        &self,
        source_id: uuid::Uuid,
        target_id: uuid::Uuid,
        relationship: &str,
        weight: f64,
        properties: serde_json::Value,
    ) -> Result<crate::models::KnowledgeEdge> {
        let edge = sqlx::query_as!(
            crate::models::KnowledgeEdge,
            r#"
            INSERT INTO knowledge_edges (id, source_node_id, target_node_id, relationship, weight, properties, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            source_id,
            target_id,
            relationship,
            weight,
            properties
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to create knowledge edge")?;

        Ok(edge)
    }

    pub async fn get_neighbors(
        &self,
        node_id: uuid::Uuid,
    ) -> Result<Vec<crate::models::KnowledgeNode>> {
        let nodes = sqlx::query_as!(
            crate::models::KnowledgeNode,
            r#"
            SELECT DISTINCT kn.* FROM knowledge_nodes kn
            INNER JOIN knowledge_edges ke ON (
                (ke.source_node_id = $1 AND ke.target_node_id = kn.id)
                OR (ke.target_node_id = $1 AND ke.source_node_id = kn.id)
            )
            WHERE kn.id != $1
            "#,
            node_id
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to get knowledge node neighbors")?;

        Ok(nodes)
    }

    pub async fn get_nodes_by_org(
        &self,
        org_id: uuid::Uuid,
        node_type: Option<&str>,
    ) -> Result<Vec<crate::models::KnowledgeNode>> {
        let nodes = match node_type {
            Some(nt) => {
                sqlx::query_as!(
                    crate::models::KnowledgeNode,
                    "SELECT * FROM knowledge_nodes WHERE organization_id = $1 AND node_type = $2 ORDER BY created_at DESC",
                    org_id,
                    nt
                )
                .fetch_all(&self.pool)
                .await
            }
            None => {
                sqlx::query_as!(
                    crate::models::KnowledgeNode,
                    "SELECT * FROM knowledge_nodes WHERE organization_id = $1 ORDER BY created_at DESC",
                    org_id
                )
                .fetch_all(&self.pool)
                .await
            }
        }
        .context("Failed to get knowledge nodes by organization")?;

        Ok(nodes)
    }

    pub async fn search_by_embedding(
        &self,
        org_id: uuid::Uuid,
        query_embedding: &[f32],
        limit: i32,
    ) -> Result<Vec<crate::models::KnowledgeNode>> {
        let nodes = sqlx::query_as!(
            crate::models::KnowledgeNode,
            r#"
            SELECT * FROM knowledge_nodes
            WHERE organization_id = $1 AND embedding IS NOT NULL
            ORDER BY embedding <=> $2
            LIMIT $3
            "#,
            org_id,
            query_embedding,
            limit
        )
        .fetch_all(&self.pool)
        .await
        .context("Failed to search knowledge nodes by embedding")?;

        Ok(nodes)
    }
}

// ================================================================
//  CONVERSATION CONTEXT REPOSITORY
// ================================================================

pub struct ConversationRepository {
    pool: PgPool,
}

impl ConversationRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn create(
        &self,
        user_id: uuid::Uuid,
        session_id: uuid::Uuid,
        messages: serde_json::Value,
    ) -> Result<crate::models::ConversationContext> {
        let ctx = sqlx::query_as!(
            crate::models::ConversationContext,
            r#"
            INSERT INTO conversation_contexts (id, user_id, session_id, messages, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            RETURNING *
            "#,
            uuid::Uuid::new_v4(),
            user_id,
            session_id,
            messages
        )
        .fetch_one(&self.pool)
        .await
        .context("Failed to create conversation context")?;

        Ok(ctx)
    }

    pub async fn get_by_session(
        &self,
        session_id: uuid::Uuid,
    ) -> Result<Option<crate::models::ConversationContext>> {
        let ctx = sqlx::query_as!(
            crate::models::ConversationContext,
            "SELECT * FROM conversation_contexts WHERE session_id = $1 ORDER BY updated_at DESC LIMIT 1",
            session_id
        )
        .fetch_optional(&self.pool)
        .await
        .context("Failed to get conversation context")?;

        Ok(ctx)
    }

    pub async fn update_messages(
        &self,
        id: uuid::Uuid,
        messages: serde_json::Value,
        summary: Option<&str>,
    ) -> Result<()> {
        sqlx::query!(
            "UPDATE conversation_contexts SET messages = $2, summary = COALESCE($3, summary), updated_at = NOW() WHERE id = $1",
            id,
            messages,
            summary
        )
        .execute(&self.pool)
        .await
        .context("Failed to update conversation messages")?;

        Ok(())
    }
}
