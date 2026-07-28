//! API routes for trace analysis and harness improvement recommendations.

use actix_web::{web, HttpResponse, Responder};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use chrono::{Duration, Utc};
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
    db: web::Data<PgPool>,
    query: web::Query<AnalysisQuery>,
) -> impl Responder {
    let window_hours = query.window_hours.unwrap_or(24);
    let window_end = Utc::now();
    let window_start = window_end - Duration::hours(window_hours);

    let analyzer = TraceAnalyzer::new(db.get_ref().clone());

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

            HttpResponse::Ok().json(report)
        }
        Err(e) => {
            tracing::error!("Analysis failed: {}", e);
            HttpResponse::InternalServerError().json(serde_json::json!({
                "error": format!("Analysis failed: {}", e)
            }))
        }
    }
}

/// GET /api/v1/traces/recommendations — Get latest recommendations
pub async fn get_recommendations(
    db: web::Data<PgPool>,
) -> impl Responder {
    let analyzer = TraceAnalyzer::new(db.get_ref().clone());

    match analyzer.get_latest_report().await {
        Ok(Some(report)) => HttpResponse::Ok().json(serde_json::json!({
            "report_id": report.report_id,
            "generated_at": report.generated_at,
            "total_traces": report.total_traces_analyzed,
            "recommendations": report.recommendations,
            "intent_stats": report.intent_stats,
            "tool_patterns": report.tool_patterns,
        })),
        Ok(None) => HttpResponse::Ok().json(serde_json::json!({
            "message": "No analysis reports yet. Run /api/v1/traces/analyze first.",
            "recommendations": [],
        })),
        Err(e) => {
            tracing::error!("Failed to get recommendations: {}", e);
            HttpResponse::InternalServerError().json(serde_json::json!({
                "error": format!("Failed to get recommendations: {}", e)
            }))
        }
    }
}

/// GET /api/v1/traces/stats — Get trace collection statistics
pub async fn get_trace_stats(
    db: web::Data<PgPool>,
) -> impl Responder {
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
    .fetch_one(db.get_ref())
    .await;

    match stats {
        Ok((total, synced, avg_latency)) => HttpResponse::Ok().json(serde_json::json!({
            "total_traces_7d": total,
            "synced_traces_7d": synced,
            "avg_latency_ms": avg_latency.unwrap_or(0.0),
        })),
        Err(e) => {
            tracing::error!("Failed to get trace stats: {}", e);
            HttpResponse::InternalServerError().json(serde_json::json!({
                "error": format!("Failed to get stats: {}", e)
            }))
        }
    }
}
