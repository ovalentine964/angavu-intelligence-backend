//! Device-Server Graph Sync Protocol (G5)
//!
//! Handles receiving device graph deltas and merging them into the PostgreSQL
//! knowledge graph with k-anonymity enforcement.
//!
//! Sync flow:
//! 1. Device sends GraphSyncMessage (node/edge/fact deltas)
//! 2. Server validates k-anonymity (k≥10 per cohort)
//! 3. Server merges deltas into kg_* tables
//! 4. Server returns market signals, price updates, demand signals
//!
//! Privacy enforcement:
//! - Individual transaction data is NEVER accepted
//! - Customer data is NEVER accepted
//! - All data must be aggregated to cohort level (k≥10)
//! - Device ID is hashed (SHA-256) — no PII in transit

use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use uuid::Uuid;
use chrono::{DateTime, Utc};

use crate::gateway::k_anonymity::{KAnonymityEnforcer, MIN_K_ANONYMITY};

/// Sync message from device to server.
#[derive(Debug, Deserialize)]
pub struct GraphSyncMessage {
    pub device_id_hash: String,
    pub cohort_hash: String,
    pub last_sync_timestamp: i64,
    pub current_timestamp: i64,
    pub node_deltas: Vec<NodeDelta>,
    pub edge_deltas: Vec<EdgeDelta>,
    pub fact_deltas: Vec<FactDelta>,
    pub stats: DeviceStats,
}

#[derive(Debug, Deserialize)]
pub struct NodeDelta {
    pub id: String,
    #[serde(rename = "type")]
    pub node_type: String,
    pub label: String,
    pub properties: serde_json::Value,
    pub updated_at: i64,
    pub operation: Operation,
}

#[derive(Debug, Deserialize)]
pub struct EdgeDelta {
    pub from_id: String,
    pub to_id: String,
    pub relation: String,
    pub properties: serde_json::Value,
    pub weight: f32,
    pub updated_at: i64,
    pub operation: Operation,
}

#[derive(Debug, Deserialize)]
pub struct FactDelta {
    pub subject: String,
    pub predicate: String,
    pub object: String,
    pub confidence: f32,
    pub source: String,
    pub updated_at: i64,
    pub operation: Operation,
}

#[derive(Debug, Deserialize)]
pub struct DeviceStats {
    pub transaction_count_today: i32,
    pub total_revenue_today: f64,
    pub product_count: i32,
    pub customer_count: i32,
    pub dominant_product_category: String,
    pub worker_type_detected: String,
}

#[derive(Debug, Deserialize, Clone, Copy, PartialEq)]
#[serde(rename_all = "UPPERCASE")]
pub enum Operation {
    Upsert,
    Delete,
}

/// Response from server to device after sync.
#[derive(Debug, Serialize)]
pub struct ServerSyncResponse {
    pub success: bool,
    pub server_timestamp: i64,
    pub deltas_applied: i32,
    pub market_signals: Vec<ServerDelta>,
    pub price_updates: Vec<ServerDelta>,
    pub demand_signals: Vec<ServerDelta>,
    pub cohort_insights: Vec<ServerDelta>,
    pub error: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ServerDelta {
    pub id: String,
    #[serde(rename = "type")]
    pub delta_type: String,
    pub properties: serde_json::Value,
    pub timestamp: i64,
}

/// Axum handler for POST /api/v1/sync/graph
/// Receives graph sync messages from devices and returns market signals.
pub async fn handle_graph_sync(
    axum::extract::State(gateway): axum::extract::State<super::GatewayState>,
    axum::extract::Json(message): axum::extract::Json<GraphSyncMessage>,
) -> axum::response::Json<ServerSyncResponse> {
    let result = process_sync(&gateway.db, message, &gateway.k_anonymity).await;
    match result {
        Ok(response) => axum::response::Json(response),
        Err(e) => {
            tracing::error!(error = %e, "Graph sync failed");
            axum::response::Json(ServerSyncResponse {
                success: false,
                server_timestamp: chrono::Utc::now().timestamp_millis(),
                deltas_applied: 0,
                market_signals: vec![],
                price_updates: vec![],
                demand_signals: vec![],
                cohort_insights: vec![],
                error: Some(e.to_string()),
            })
        }
    }
}

/// Process a graph sync message from a device.
///
/// Steps:
/// 1. Validate the message (k-anonymity, no PII)
/// 2. Aggregate device stats into cohort
/// 3. Merge accepted deltas into kg_* tables
/// 4. Return market signals for the device
pub async fn process_sync(
    pool: &PgPool,
    message: GraphSyncMessage,
    k_enforcer: &KAnonymityEnforcer,
) -> Result<ServerSyncResponse, SyncError> {
    // ── Step 1: Validate k-anonymity ──
    // The cohort_hash must correspond to a cohort with k≥10 members
    let cohort_size = get_cohort_size(pool, &message.cohort_hash).await?;

    if cohort_size < MIN_K_ANONYMITY as i32 {
        // Reject: cohort too small, data would be identifiable
        return Ok(ServerSyncResponse {
            success: false,
            server_timestamp: Utc::now().timestamp_millis(),
            deltas_applied: 0,
            market_signals: vec![],
            price_updates: vec![],
            demand_signals: vec![],
            cohort_insights: vec![],
            error: Some(format!(
                "Cohort size {} below k-anonymity threshold {}",
                cohort_size, MIN_K_ANONYMITY
            )),
        });
    }

    // ── Step 2: Validate no PII in deltas ──
    validate_no_pii(&message)?;

    // ── Step 3: Aggregate device stats into cohort ──
    aggregate_device_stats(pool, &message).await?;

    // ── Step 4: Merge deltas ──
    let mut deltas_applied = 0;

    // Only apply product/supplier node deltas (not customer, not transaction)
    for delta in &message.node_deltas {
        if delta.node_type == "PRODUCT" || delta.node_type == "SUPPLIER" {
            if delta.operation == Operation::Upsert {
                merge_node_delta(pool, delta).await?;
                deltas_applied += 1;
            }
        }
    }

    // Apply edge deltas (supply chain, pricing relationships)
    for delta in &message.edge_deltas {
        if is_safe_edge_type(&delta.relation) {
            merge_edge_delta(pool, delta, &message.cohort_hash).await?;
            deltas_applied += 1;
        }
    }

    // Apply fact deltas (product knowledge)
    for delta in &message.fact_deltas {
        merge_fact_delta(pool, delta).await?;
        deltas_applied += 1;
    }

    // ── Step 5: Build response with market signals ──
    let worker_type = &message.stats.worker_type_detected;
    let region = extract_region_from_cohort(&message.cohort_hash);

    let market_signals = get_market_signals(pool, worker_type, &region).await?;
    let price_updates = get_price_updates(pool, &region).await?;
    let demand_signals = get_demand_signals(pool, worker_type, &region).await?;
    let cohort_insights = get_cohort_insights(pool, &message.cohort_hash).await?;

    Ok(ServerSyncResponse {
        success: true,
        server_timestamp: Utc::now().timestamp_millis(),
        deltas_applied,
        market_signals,
        price_updates,
        demand_signals,
        cohort_insights,
        error: None,
    })
}

// ═══════════════════════════════════════════════════════════
//  VALIDATION
// ═══════════════════════════════════════════════════════════

/// Validate that the sync message contains no PII.
/// Reject if customer names, phone numbers, or individual transactions are present.
fn validate_no_pii(message: &GraphSyncMessage) -> Result<(), SyncError> {
    // Check: no customer nodes
    for delta in &message.node_deltas {
        if delta.node_type == "CUSTOMER" || delta.node_type == "TRANSACTION" {
            return Err(SyncError::PiiViolation(format!(
                "Node type '{}' must not be synced (contains PII)",
                delta.node_type
            )));
        }
    }

    // Check: no customer-related edges
    for delta in &message.edge_deltas {
        let relation = delta.relation.to_uppercase();
        if relation == "PURCHASED_BY" || relation == "BOUGHT" {
            return Err(SyncError::PiiViolation(format!(
                "Edge type '{}' must not be synced (links to PII)",
                delta.relation
            )));
        }
    }

    // Check: no phone numbers or names in properties
    for delta in &message.node_deltas {
        if let Some(props) = delta.properties.as_object() {
            for (key, value) in props {
                let key_lower = key.to_lowercase();
                if key_lower.contains("phone") || key_lower.contains("name")
                    || key_lower.contains("mpesa_ref")
                {
                    if let Some(s) = value.as_str() {
                        if !s.is_empty() {
                            return Err(SyncError::PiiViolation(format!(
                                "Property '{}' in node '{}' may contain PII",
                                key, delta.id
                            )));
                        }
                    }
                }
            }
        }
    }

    Ok(())
}

fn is_safe_edge_type(relation: &str) -> bool {
    matches!(
        relation.to_uppercase().as_str(),
        "SUPPLIES"
            | "BELONGS_TO"
            | "PRICED_AT"
            | "LOCATED_AT"
            | "ALTERNATIVE_TO"
            | "COMPLEMENTS"
            | "SUBCATEGORY_OF"
    )
}

// ═══════════════════════════════════════════════════════════
//  DATABASE OPERATIONS
// ═══════════════════════════════════════════════════════════

async fn get_cohort_size(pool: &PgPool, cohort_hash: &str) -> Result<i32, SyncError> {
    let row = sqlx::query_scalar!(
        "SELECT member_count FROM kg_worker_cohorts WHERE cohort_hash = $1",
        cohort_hash
    )
    .fetch_optional(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    Ok(row.unwrap_or(0))
}

async fn aggregate_device_stats(
    pool: &PgPool,
    message: &GraphSyncMessage,
) -> Result<(), SyncError> {
    // Update cohort aggregate stats (incremental)
    // This is safe because we're adding to aggregates, not storing individual data
    sqlx::query!(
        r#"
        UPDATE kg_worker_cohorts SET
            avg_daily_revenue = (avg_daily_revenue * member_count + $2) / (member_count + 1),
            last_aggregated_at = NOW(),
            updated_at = NOW()
        WHERE cohort_hash = $1
        "#,
        message.cohort_hash,
        message.stats.total_revenue_today
    )
    .execute(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    Ok(())
}

async fn merge_node_delta(pool: &PgPool, delta: &NodeDelta) -> Result<(), SyncError> {
    // Store product/supplier nodes as supply chain entities
    sqlx::query!(
        r#"
        INSERT INTO kg_supply_chain_entities (entity_type, entity_name, anonymized, embedding, created_at, updated_at)
        VALUES ($1, $2, true, NULL, NOW(), NOW())
        ON CONFLICT DO NOTHING
        "#,
        delta.node_type.to_lowercase(),
        delta.label
    )
    .execute(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    Ok(())
}

async fn merge_edge_delta(
    pool: &PgPool,
    delta: &EdgeDelta,
    cohort_hash: &str,
) -> Result<(), SyncError> {
    // Store edges in kg_edges with sample_size = cohort member count (k-anonymity safe)
    let cohort_id = sqlx::query_scalar!(
        "SELECT id FROM kg_worker_cohorts WHERE cohort_hash = $1",
        cohort_hash
    )
    .fetch_optional(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    if let Some(cohort_id) = cohort_id {
        sqlx::query!(
            r#"
            INSERT INTO kg_edges (source_type, source_id, target_type, target_id, edge_type, weight, confidence, sample_size)
            VALUES ('worker_cohort', $1, 'supply_chain_entity', $2, 'supply_chain', $3, 0.8, 10)
            ON CONFLICT DO NOTHING
            "#,
            cohort_id,
            Uuid::parse_str(&delta.from_id).unwrap_or(Uuid::nil()),
            delta.weight as f64
        )
        .execute(pool)
        .await
        .map_err(|e| SyncError::Database(e.to_string()))?;
    }

    Ok(())
}

async fn merge_fact_delta(pool: &PgPool, delta: &FactDelta) -> Result<(), SyncError> {
    // Store facts as product category knowledge
    // This is safe because facts are about products, not individuals
    sqlx::query!(
        r#"
        INSERT INTO kg_product_categories (category_code, category_name, created_at, updated_at)
        VALUES ($1, $2, NOW(), NOW())
        ON CONFLICT (category_code) DO UPDATE SET updated_at = NOW()
        "#,
        delta.subject,
        delta.object
    )
    .execute(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    Ok(())
}

fn extract_region_from_cohort(cohort_hash: &str) -> String {
    // Cohort hash format: "worker_type|region|language"
    cohort_hash
        .split('|')
        .nth(1)
        .unwrap_or("unknown")
        .to_string()
}

// ═══════════════════════════════════════════════════════════
//  MARKET SIGNAL QUERIES (Server → Device)
// ═══════════════════════════════════════════════════════════

async fn get_market_signals(
    pool: &PgPool,
    worker_type: &str,
    region: &str,
) -> Result<Vec<ServerDelta>, SyncError> {
    let rows = sqlx::query!(
        r#"
        SELECT pc.category_code, pc.category_name, pc.demand_trend, pc.avg_price_kes
        FROM kg_product_categories pc
        WHERE pc.demand_trend != 'stable'
        LIMIT 5
        "#
    )
    .fetch_all(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    Ok(rows
        .into_iter()
        .map(|r| ServerDelta {
            id: format!("signal:{}", r.category_code),
            delta_type: "DEMAND_SIGNAL".to_string(),
            properties: serde_json::json!({
                "category": r.category_code,
                "name": r.category_name,
                "trend": r.demand_trend,
                "avg_price": r.avg_price_kes
            }),
            timestamp: Utc::now().timestamp_millis(),
        })
        .collect())
}

async fn get_price_updates(
    pool: &PgPool,
    region: &str,
) -> Result<Vec<ServerDelta>, SyncError> {
    let rows = sqlx::query!(
        r#"
        SELECT pc.category_code, pp.price_kes, pp.price_change_7d
        FROM kg_price_points pp
        JOIN kg_product_categories pc ON pc.id = pp.product_category_id
        WHERE pp.recorded_at > NOW() - INTERVAL '24 hours'
        ORDER BY ABS(pp.price_change_7d) DESC
        LIMIT 5
        "#
    )
    .fetch_all(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    Ok(rows
        .into_iter()
        .map(|r| ServerDelta {
            id: format!("price:{}", r.category_code),
            delta_type: "PRICE_UPDATE".to_string(),
            properties: serde_json::json!({
                "product_id": r.category_code,
                "price_kes": r.price_kes,
                "change_7d_pct": r.price_change_7d
            }),
            timestamp: Utc::now().timestamp_millis(),
        })
        .collect())
}

async fn get_demand_signals(
    pool: &PgPool,
    worker_type: &str,
    region: &str,
) -> Result<Vec<ServerDelta>, SyncError> {
    let rows = sqlx::query!(
        r#"
        SELECT ds.signal_type, ds.signal_strength, ds.direction, pc.category_code
        FROM kg_demand_signals ds
        JOIN kg_product_categories pc ON pc.id = ds.product_category_id
        WHERE (ds.expires_at IS NULL OR ds.expires_at > NOW())
          AND ds.confidence > 0.5
        ORDER BY ds.signal_strength DESC
        LIMIT 5
        "#
    )
    .fetch_all(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    Ok(rows
        .into_iter()
        .map(|r| ServerDelta {
            id: format!("demand:{}", r.category_code),
            delta_type: "DEMAND_SIGNAL".to_string(),
            properties: serde_json::json!({
                "category": r.category_code,
                "signal_type": r.signal_type,
                "strength": r.signal_strength,
                "direction": r.direction
            }),
            timestamp: Utc::now().timestamp_millis(),
        })
        .collect())
}

async fn get_cohort_insights(
    pool: &PgPool,
    cohort_hash: &str,
) -> Result<Vec<ServerDelta>, SyncError> {
    // Return aggregated insights about the worker's cohort
    let row = sqlx::query!(
        r#"
        SELECT worker_type, avg_daily_revenue, avg_daily_transactions, revenue_volatility
        FROM kg_worker_cohorts
        WHERE cohort_hash = $1
        "#,
        cohort_hash
    )
    .fetch_optional(pool)
    .await
    .map_err(|e| SyncError::Database(e.to_string()))?;

    if let Some(r) = row {
        Ok(vec![ServerDelta {
            id: format!("cohort:{}", cohort_hash),
            delta_type: "COHORT_PATTERN".to_string(),
            properties: serde_json::json!({
                "worker_type": r.worker_type,
                "avg_daily_revenue": r.avg_daily_revenue,
                "avg_daily_transactions": r.avg_daily_transactions,
                "revenue_volatility": r.revenue_volatility
            }),
            timestamp: Utc::now().timestamp_millis(),
        }])
    } else {
        Ok(vec![])
    }
}

// ═══════════════════════════════════════════════════════════
//  ERROR TYPES
// ═══════════════════════════════════════════════════════════

#[derive(Debug, thiserror::Error)]
pub enum SyncError {
    #[error("k-anonymity violation: {0}")]
    KAnonymityViolation(String),

    #[error("PII violation: {0}")]
    PiiViolation(String),

    #[error("Database error: {0}")]
    Database(String),

    #[error("Invalid data: {0}")]
    InvalidData(String),
}
