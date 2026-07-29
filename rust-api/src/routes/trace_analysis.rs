//! API routes for trace analysis and harness improvement recommendations.

use axum::{
    extract::{Query, State},
    http::StatusCode,
    response::IntoResponse,
    Json,
};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use chrono::{Duration, Utc};
use std::sync::Arc;
use tracing::info;

use crate::loops::trace_analysis::TraceAnalyzer;

/// Query parameters for the analysis endpoint.
#[derive(Debug, Deserialize)]
pub struct AnalysisQuery {
    /// Analysis window in hours (default: 24)
    pub window_hours: Option<i64>,
}

/// POST /api/v1/traces/analyze — Run trace analysis
pub async fn run_analysis(
    State(db): State<Arc<PgPool>>,
    Query(query): Query<AnalysisQuery>,
) -> impl IntoResponse {
    let window_hours = query.window_hours.unwrap_or(24);
    let window_end = Utc::now();
    let window_start = window_end - Duration::hours(window_hours);

    let analyzer = TraceAnalyzer::new((*db).clone());

    match analyzer.analyze(window_start, window_end).await {
        Ok(report) => {
            // Store the report
            if let Err(e) = analyzer.store_report(&report).await {
                tracing::warn!("Failed to store analysis report: {}", e);
            }

            info!(
                "Analysis complete: {} traces, {} recommendations",
                report.total_traces_analyzed,
                report.recommendations.len()
            );

            (StatusCode::OK, Json(serde_json::json!(report))).into_response()
        }
        Err(e) => {
            tracing::error!("Analysis failed: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({
                "error": format!("Analysis failed: {}", e)
            }))).into_response()
        }
    }
}

/// GET /api/v1/traces/recommendations — Get latest recommendations
pub async fn get_recommendations(
    State(db): State<Arc<PgPool>>,
) -> impl IntoResponse {
    let analyzer = TraceAnalyzer::new((*db).clone());

    match analyzer.get_latest_report().await {
        Ok(Some(report)) => (StatusCode::OK, Json(serde_json::json!({
            "report_id": report.report_id,
            "generated_at": report.generated_at,
            "total_traces": report.total_traces_analyzed,
            "recommendations": report.recommendations,
            "intent_stats": report.intent_stats,
            "tool_patterns": report.tool_patterns,
        }))).into_response(),
        Ok(None) => (StatusCode::OK, Json(serde_json::json!({
            "message": "No analysis reports yet. Run /api/v1/traces/analyze first.",
            "recommendations": [],
        }))).into_response(),
        Err(e) => {
            tracing::error!("Failed to get recommendations: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({
                "error": format!("Failed to get recommendations: {}", e)
            }))).into_response()
        }
    }
}

/// GET /api/v1/traces/stats — Get trace collection statistics
pub async fn get_trace_stats(
    State(db): State<Arc<PgPool>>,
) -> impl IntoResponse {
    let stats: Result<(i64, i64, Option<f64>), _> = sqlx::query_as(
        r#"
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE needs_sync = false) as synced,
            AVG(total_latency_ms) as avg_latency
        FROM agent_traces
        WHERE created_at > NOW() - INTERVAL '7 days'
        "#,
    )
    .fetch_one(&*db)
    .await;

    match stats {
        Ok((total, synced, avg_latency)) => (StatusCode::OK, Json(serde_json::json!({
            "total_traces_7d": total,
            "synced_traces_7d": synced,
            "avg_latency_ms": avg_latency.unwrap_or(0.0),
        }))).into_response(),
        Err(e) => {
            tracing::error!("Failed to get trace stats: {}", e);
            (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({
                "error": format!("Failed to get stats: {}", e)
            }))).into_response()
        }
    }
}
