//! GraphQL Schema — async-graphql types and resolvers for the knowledge graph.
//!
//! Exposes queries for nodes, edges, paths, subgraphs, PageRank, communities.

use async_graphql::{Context, EmptyMutation, EmptySubscription, Object, Schema, SimpleObject, ID};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use uuid::Uuid;

use crate::graph::algorithms::{AlgorithmGraph, PageRankResult, Community, CentralityResult, ShortestPathResult};

/// The GraphQL schema type.
pub type AngavuSchema = Schema<QueryRoot, EmptyMutation, EmptySubscription>;

/// Shared state for GraphQL resolvers.
pub struct GraphQLState {
    pub pool: sqlx::PgPool,
    pub redis: redis::aio::ConnectionManager,
}

/// Build the GraphQL schema with resolvers.
pub fn build_schema(state: Arc<GraphQLState>) -> AngavuSchema {
    Schema::build(QueryRoot, EmptyMutation, EmptySubscription)
        .data(state)
        .finish()
}

/// Create a schema with database and Redis connections.
pub async fn create_schema(
    pool: sqlx::PgPool,
    redis: redis::aio::ConnectionManager,
) -> AngavuSchema {
    let state = Arc::new(GraphQLState { pool, redis });
    build_schema(state)
}

// ── GraphQL Types ──────────────────────────────────────────────────────────

#[derive(SimpleObject, Clone, Debug, Serialize, Deserialize)]
pub struct GqlGraphNode {
    pub id: ID,
    pub node_type: String,
    pub label: String,
    pub properties: async_graphql::JsonValue,
}

#[derive(SimpleObject, Clone, Debug, Serialize, Deserialize)]
pub struct GqlGraphEdge {
    pub id: ID,
    pub source_id: ID,
    pub target_id: ID,
    pub edge_type: String,
    pub weight: f64,
    pub confidence: f64,
    pub properties: async_graphql::JsonValue,
}

#[derive(SimpleObject, Clone, Debug)]
pub struct GqlPageRankResult {
    pub node_id: ID,
    pub score: f64,
    pub label: Option<String>,
}

#[derive(SimpleObject, Clone, Debug)]
pub struct GqlCommunity {
    pub id: i64,
    pub members: Vec<ID>,
    pub internal_edges: i64,
    pub modularity_score: f64,
}

#[derive(SimpleObject, Clone, Debug)]
pub struct GqlCentralityResult {
    pub node_id: ID,
    pub degree: i64,
    pub in_degree: i64,
    pub out_degree: i64,
    pub label: Option<String>,
}

#[derive(SimpleObject, Clone, Debug)]
pub struct GqlShortestPath {
    pub path: Vec<ID>,
    pub total_weight: f64,
    pub hop_count: i64,
}

#[derive(SimpleObject, Clone, Debug)]
pub struct GqlSubgraph {
    pub nodes: Vec<GqlGraphNode>,
    pub edges: Vec<GqlGraphEdge>,
    pub node_count: i64,
    pub edge_count: i64,
}

#[derive(SimpleObject, Clone, Debug)]
pub struct GqlGraphStats {
    pub total_nodes: i64,
    pub total_edges: i64,
    pub node_type_counts: Vec<NodeTypeCount>,
}

#[derive(SimpleObject, Clone, Debug)]
pub struct NodeTypeCount {
    pub node_type: String,
    pub count: i64,
}

#[derive(async_graphql::InputObject)]
pub struct NodeFilter {
    pub node_type: Option<String>,
    pub label_contains: Option<String>,
    pub region: Option<String>,
    pub worker_type: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

#[derive(async_graphql::InputObject)]
pub struct EdgeFilter {
    pub edge_type: Option<String>,
    pub source_id: Option<ID>,
    pub target_id: Option<ID>,
    pub min_weight: Option<f64>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

// ── Query Root ─────────────────────────────────────────────────────────────

pub struct QueryRoot;

#[Object]
impl QueryRoot {
    /// Get a node by ID (from any node table).
    async fn node(&self, ctx: &Context<'_>, id: ID) -> async_graphql::Result<Option<GqlGraphNode>> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let uuid = Uuid::parse_str(&id)?;

        // Try worker cohorts first
        if let Some(row) = sqlx::query!(
            "SELECT id, cohort_hash, worker_type, region_id, member_count, avg_daily_revenue
             FROM kg_worker_cohorts WHERE id = $1",
            uuid
        )
        .fetch_optional(&state.pool)
        .await?
        {
            return Ok(Some(GqlGraphNode {
                id: id.clone(),
                node_type: "worker_cohort".to_string(),
                label: format!("cohort:{}:{}", row.worker_type, row.cohort_hash),
                properties: serde_json::json!({
                    "worker_type": row.worker_type,
                    "region_id": row.region_id,
                    "member_count": row.member_count,
                    "avg_daily_revenue": row.avg_daily_revenue,
                })
                .into(),
            }));
        }

        // Try product categories
        if let Some(row) = sqlx::query!(
            "SELECT id, category_code, category_name, demand_trend, avg_price_kes
             FROM kg_product_categories WHERE id = $1",
            uuid
        )
        .fetch_optional(&state.pool)
        .await?
        {
            return Ok(Some(GqlGraphNode {
                id: id.clone(),
                node_type: "product_category".to_string(),
                label: format!("product:{}", row.category_code),
                properties: serde_json::json!({
                    "category_code": row.category_code,
                    "category_name": row.category_name,
                    "demand_trend": row.demand_trend,
                    "avg_price_kes": row.avg_price_kes,
                })
                .into(),
            }));
        }

        // Try regional markets
        if let Some(row) = sqlx::query!(
            "SELECT id, region_code, region_name, region_level, population_estimate
             FROM kg_regional_markets WHERE id = $1",
            uuid
        )
        .fetch_optional(&state.pool)
        .await?
        {
            return Ok(Some(GqlGraphNode {
                id: id.clone(),
                node_type: "regional_market".to_string(),
                label: format!("region:{}", row.region_code),
                properties: serde_json::json!({
                    "region_code": row.region_code,
                    "region_name": row.region_name,
                    "region_level": row.region_level,
                    "population_estimate": row.population_estimate,
                })
                .into(),
            }));
        }

        // Try economic indicators
        if let Some(row) = sqlx::query!(
            "SELECT id, indicator_code, indicator_name, current_value, trend
             FROM kg_economic_indicators WHERE id = $1",
            uuid
        )
        .fetch_optional(&state.pool)
        .await?
        {
            return Ok(Some(GqlGraphNode {
                id: id.clone(),
                node_type: "economic_indicator".to_string(),
                label: format!("indicator:{}", row.indicator_code),
                properties: serde_json::json!({
                    "indicator_code": row.indicator_code,
                    "indicator_name": row.indicator_name,
                    "current_value": row.current_value,
                    "trend": row.trend,
                })
                .into(),
            }));
        }

        // Try demand signals
        if let Some(row) = sqlx::query!(
            "SELECT id, signal_type, signal_strength, direction, confidence
             FROM kg_demand_signals WHERE id = $1",
            uuid
        )
        .fetch_optional(&state.pool)
        .await?
        {
            return Ok(Some(GqlGraphNode {
                id: id.clone(),
                node_type: "demand_signal".to_string(),
                label: format!("signal:{}", row.signal_type),
                properties: serde_json::json!({
                    "signal_type": row.signal_type,
                    "signal_strength": row.signal_strength,
                    "direction": row.direction,
                    "confidence": row.confidence,
                })
                .into(),
            }));
        }

        Ok(None)
    }

    /// List nodes with optional filters.
    async fn nodes(
        &self,
        ctx: &Context<'_>,
        filter: Option<NodeFilter>,
    ) -> async_graphql::Result<Vec<GqlGraphNode>> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let f = filter.unwrap_or(NodeFilter {
            node_type: None,
            label_contains: None,
            region: None,
            worker_type: None,
            limit: Some(50),
            offset: Some(0),
        });
        let limit = f.limit.unwrap_or(50).min(500);
        let offset = f.offset.unwrap_or(0);

        let mut results: Vec<GqlGraphNode> = Vec::new();

        if f.node_type.as_deref() == Some("worker_cohort") || f.node_type.is_none() {
            let rows = sqlx::query!(
                "SELECT id, cohort_hash, worker_type, region_id, member_count, avg_daily_revenue
                 FROM kg_worker_cohorts
                 WHERE ($1::text IS NULL OR worker_type = $1)
                   AND ($2::text IS NULL OR region_id = $2)
                 ORDER BY member_count DESC
                 LIMIT $3 OFFSET $4",
                f.worker_type,
                f.region,
                limit,
                offset,
            )
            .fetch_all(&state.pool)
            .await?;

            for row in rows {
                results.push(GqlGraphNode {
                    id: ID::from(row.id.to_string()),
                    node_type: "worker_cohort".to_string(),
                    label: format!("cohort:{}:{}", row.worker_type, row.cohort_hash),
                    properties: serde_json::json!({
                        "worker_type": row.worker_type,
                        "region_id": row.region_id,
                        "member_count": row.member_count,
                        "avg_daily_revenue": row.avg_daily_revenue,
                    })
                    .into(),
                });
            }
        }

        if f.node_type.as_deref() == Some("product_category") || f.node_type.is_none() {
            let rows = sqlx::query!(
                "SELECT id, category_code, category_name, demand_trend, avg_price_kes
                 FROM kg_product_categories
                 WHERE ($1::text IS NULL OR category_name ILIKE '%' || $1 || '%')
                 ORDER BY category_code
                 LIMIT $2 OFFSET $3",
                f.label_contains,
                limit,
                offset,
            )
            .fetch_all(&state.pool)
            .await?;

            for row in rows {
                results.push(GqlGraphNode {
                    id: ID::from(row.id.to_string()),
                    node_type: "product_category".to_string(),
                    label: format!("product:{}", row.category_code),
                    properties: serde_json::json!({
                        "category_code": row.category_code,
                        "category_name": row.category_name,
                        "demand_trend": row.demand_trend,
                        "avg_price_kes": row.avg_price_kes,
                    })
                    .into(),
                });
            }
        }

        Ok(results)
    }

    /// Get edges with optional filters.
    async fn edges(
        &self,
        ctx: &Context<'_>,
        filter: Option<EdgeFilter>,
    ) -> async_graphql::Result<Vec<GqlGraphEdge>> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let f = filter.unwrap_or(EdgeFilter {
            edge_type: None,
            source_id: None,
            target_id: None,
            min_weight: None,
            limit: Some(100),
            offset: Some(0),
        });
        let limit = f.limit.unwrap_or(100).min(1000);
        let offset = f.offset.unwrap_or(0);

        let source_uuid = f.source_id.as_ref().map(|id| Uuid::parse_str(id)).transpose()?;
        let target_uuid = f.target_id.as_ref().map(|id| Uuid::parse_str(id)).transpose()?;

        let rows = sqlx::query!(
            "SELECT id, source_type, source_id, target_type, target_id,
                    edge_type, weight, confidence, properties
             FROM kg_edges
             WHERE ($1::text IS NULL OR edge_type::text = $1)
               AND ($2::uuid IS NULL OR source_id = $2)
               AND ($3::uuid IS NULL OR target_id = $3)
               AND ($4::float IS NULL OR weight >= $4)
               AND valid_until IS NULL
             ORDER BY weight DESC
             LIMIT $5 OFFSET $6",
            f.edge_type,
            source_uuid,
            target_uuid,
            f.min_weight,
            limit,
            offset,
        )
        .fetch_all(&state.pool)
        .await?;

        let edges = rows
            .into_iter()
            .map(|row| GqlGraphEdge {
                id: ID::from(row.id.to_string()),
                source_id: ID::from(row.source_id.to_string()),
                target_id: ID::from(row.target_id.to_string()),
                edge_type: format!("{:?}", row.edge_type),
                weight: row.weight,
                confidence: row.confidence,
                properties: async_graphql::JsonValue(row.properties),
            })
            .collect();

        Ok(edges)
    }

    /// Find shortest path between two nodes using Dijkstra.
    async fn shortest_path(
        &self,
        ctx: &Context<'_>,
        from: ID,
        to: ID,
        max_depth: Option<i64>,
    ) -> async_graphql::Result<Option<GqlShortestPath>> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let from_uuid = Uuid::parse_str(&from)?;
        let to_uuid = Uuid::parse_str(&to)?;
        let _max = max_depth.unwrap_or(10).min(20);

        // Build in-memory graph from DB
        let graph = crate::graph::algorithms::build_graph_from_db(&state.pool, None).await?;

        Ok(graph.shortest_path(from_uuid, to_uuid).map(|r| GqlShortestPath {
            path: r.path.iter().map(|id| ID::from(id.to_string())).collect(),
            total_weight: r.total_weight,
            hop_count: r.hop_count as i64,
        }))
    }

    /// Get a subgraph centered on a node within N hops.
    async fn subgraph(
        &self,
        ctx: &Context<'_>,
        center: ID,
        max_hops: Option<i64>,
        limit: Option<i64>,
    ) -> async_graphql::Result<GqlSubgraph> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let center_uuid = Uuid::parse_str(&center)?;
        let hops = max_hops.unwrap_or(2).min(5) as u32;
        let node_limit = limit.unwrap_or(200).min(1000) as usize;

        let graph = crate::graph::algorithms::build_graph_from_db(&state.pool, None).await?;
        let neighborhood = graph.neighborhood(center_uuid, hops);

        let node_ids: Vec<Uuid> = neighborhood.iter().take(node_limit).map(|(id, _)| *id).collect();
        let node_id_set: std::collections::HashSet<Uuid> = node_ids.iter().cloned().collect();

        // Fetch node details
        let mut nodes = Vec::new();
        for &node_id in &node_ids {
            // Try to resolve from DB
            if let Some(row) = sqlx::query!(
                "SELECT id, cohort_hash, worker_type, region_id, member_count
                 FROM kg_worker_cohorts WHERE id = $1",
                node_id
            )
            .fetch_optional(&state.pool)
            .await?
            {
                nodes.push(GqlGraphNode {
                    id: ID::from(row.id.to_string()),
                    node_type: "worker_cohort".to_string(),
                    label: format!("cohort:{}:{}", row.worker_type, row.cohort_hash),
                    properties: serde_json::json!({
                        "worker_type": row.worker_type,
                        "region_id": row.region_id,
                        "member_count": row.member_count,
                    })
                    .into(),
                });
            }
        }

        // Fetch edges between these nodes
        let edges = sqlx::query!(
            "SELECT id, source_type, source_id, target_type, target_id,
                    edge_type, weight, confidence, properties
             FROM kg_edges
             WHERE source_id = ANY($1) AND target_id = ANY($1) AND valid_until IS NULL",
            &node_ids
        )
        .fetch_all(&state.pool)
        .await?;

        let gql_edges: Vec<GqlGraphEdge> = edges
            .into_iter()
            .filter(|e| node_id_set.contains(&e.source_id) && node_id_set.contains(&e.target_id))
            .map(|row| GqlGraphEdge {
                id: ID::from(row.id.to_string()),
                source_id: ID::from(row.source_id.to_string()),
                target_id: ID::from(row.target_id.to_string()),
                edge_type: format!("{:?}", row.edge_type),
                weight: row.weight,
                confidence: row.confidence,
                properties: async_graphql::JsonValue(row.properties),
            })
            .collect();

        let node_count = nodes.len() as i64;
        let edge_count = gql_edges.len() as i64;

        Ok(GqlSubgraph {
            nodes,
            edges: gql_edges,
            node_count,
            edge_count,
        })
    }

    /// Compute PageRank for knowledge graph nodes.
    async fn pagerank(
        &self,
        ctx: &Context<'_>,
        iterations: Option<i64>,
        damping: Option<f64>,
        limit: Option<i64>,
    ) -> async_graphql::Result<Vec<GqlPageRankResult>> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let iters = iterations.unwrap_or(30).min(100) as u32;
        let d = damping.unwrap_or(0.85);
        let top_k = limit.unwrap_or(50).min(500) as usize;

        let graph = crate::graph::algorithms::build_graph_from_db(&state.pool, None).await?;
        let results = graph.pagerank(iters, d);

        Ok(results
            .into_iter()
            .take(top_k)
            .map(|r| GqlPageRankResult {
                node_id: ID::from(r.node_id.to_string()),
                score: r.score,
                label: r.label,
            })
            .collect())
    }

    /// Detect communities in the knowledge graph.
    async fn communities(
        &self,
        ctx: &Context<'_>,
        min_size: Option<i64>,
    ) -> async_graphql::Result<Vec<GqlCommunity>> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let min = min_size.unwrap_or(2) as usize;

        let graph = crate::graph::algorithms::build_graph_from_db(&state.pool, None).await?;
        let communities = graph.detect_communities();

        Ok(communities
            .into_iter()
            .filter(|c| c.members.len() >= min)
            .map(|c| GqlCommunity {
                id: c.id as i64,
                members: c.members.iter().map(|id| ID::from(id.to_string())).collect(),
                internal_edges: c.internal_edges as i64,
                modularity_score: c.modularity_score,
            })
            .collect())
    }

    /// Get degree centrality (most connected nodes).
    async fn degree_centrality(
        &self,
        ctx: &Context<'_>,
        top_k: Option<i64>,
    ) -> async_graphql::Result<Vec<GqlCentralityResult>> {
        let state = ctx.data::<Arc<GraphQLState>>()?;
        let k = top_k.unwrap_or(20).min(200) as usize;

        let graph = crate::graph::algorithms::build_graph_from_db(&state.pool, None).await?;
        let results = graph.degree_centrality(k);

        Ok(results
            .into_iter()
            .map(|r| GqlCentralityResult {
                node_id: ID::from(r.node_id.to_string()),
                degree: r.degree as i64,
                in_degree: r.in_degree as i64,
                out_degree: r.out_degree as i64,
                label: r.label,
            })
            .collect())
    }

    /// Get overall graph statistics.
    async fn graph_stats(&self, ctx: &Context<'_>) -> async_graphql::Result<GqlGraphStats> {
        let state = ctx.data::<Arc<GraphQLState>>()?;

        let rows = sqlx::query!(
            "SELECT node_type, node_count, represented_workers
             FROM kg_graph_stats"
        )
        .fetch_all(&state.pool)
        .await?;

        let mut total_nodes: i64 = 0;
        let mut total_edges: i64 = 0;
        let mut counts = Vec::new();

        for row in &rows {
            let count = row.node_count.unwrap_or(0);
            if row.node_type == "total_edges" {
                total_edges = count;
            } else {
                total_nodes += count;
                counts.push(NodeTypeCount {
                    node_type: row.node_type.clone().unwrap_or_default(),
                    count,
                });
            }
        }

        Ok(GqlGraphStats {
            total_nodes,
            total_edges,
            node_type_counts: counts,
        })
    }
}
