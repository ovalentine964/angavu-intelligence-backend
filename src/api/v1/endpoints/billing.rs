//! Billing API endpoints for Angavu Intelligence.
//!
//! Exposes subscription management, API key operations, usage queries,
//! and invoice retrieval over HTTP via Axum.

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use uuid::Uuid;

use crate::billing::{
    api_keys::{ApiKeyManager, ApiKeyScope},
    invoice::{InvoiceGenerator, InvoiceStatus},
    subscription::{SubscriptionManager, SubscriptionStatus, SubscriptionTier},
    usage::{UsageMeter, UsageMetric},
};
use crate::db::AppState;

// ── Error Response ─────────────────────────────────────────────────────

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    code: String,
}

fn bad_request(msg: &str) -> (StatusCode, Json<ErrorResponse>) {
    (
        StatusCode::BAD_REQUEST,
        Json(ErrorResponse {
            error: msg.to_string(),
            code: "bad_request".to_string(),
        }),
    )
}

fn not_found(msg: &str) -> (StatusCode, Json<ErrorResponse>) {
    (
        StatusCode::NOT_FOUND,
        Json(ErrorResponse {
            error: msg.to_string(),
            code: "not_found".to_string(),
        }),
    )
}

fn internal_error(msg: &str) -> (StatusCode, Json<ErrorResponse>) {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(ErrorResponse {
            error: msg.to_string(),
            code: "internal_error".to_string(),
        }),
    )
}

fn conflict(msg: &str) -> (StatusCode, Json<ErrorResponse>) {
    (
        StatusCode::CONFLICT,
        Json(ErrorResponse {
            error: msg.to_string(),
            code: "conflict".to_string(),
        }),
    )
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// SUBSCRIPTION ENDPOINTS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[derive(Deserialize)]
pub struct CreateSubscriptionRequest {
    pub org_id: Uuid,
    pub tier: String,
}

#[derive(Deserialize)]
pub struct ChangeTierRequest {
    pub new_tier: String,
}

/// POST /billing/subscriptions — Create a new subscription
pub async fn create_subscription(
    State(state): State<Arc<AppState>>,
    Json(req): Json<CreateSubscriptionRequest>,
) -> Result<(StatusCode, Json<serde_json::Value>), (StatusCode, Json<ErrorResponse>)> {
    let tier: SubscriptionTier = req
        .tier
        .parse()
        .map_err(|_| bad_request("invalid tier; must be free, starter, pro, or enterprise"))?;

    let manager = SubscriptionManager::new(state.db.postgres.clone());

    match manager.create(req.org_id, tier).await {
        Ok(sub) => Ok((
            StatusCode::CREATED,
            Json(serde_json::json!({
                "status": "ok",
                "subscription": {
                    "id": sub.id,
                    "org_id": sub.org_id,
                    "tier": sub.tier,
                    "status": sub.status,
                    "current_period_start": sub.current_period_start,
                    "current_period_end": sub.current_period_end,
                    "trial_end": sub.trial_end,
                }
            })),
        )),
        Err(e) => {
            tracing::error!(error = %e, "Failed to create subscription");
            if e.to_string().contains("AlreadyActive") {
                return Err(conflict(&e.to_string()));
            }
            Err(internal_error(&e.to_string()))
        }
    }
}

/// GET /billing/subscriptions/:org_id — Get subscription for an org
pub async fn get_subscription(
    State(state): State<Arc<AppState>>,
    Path(org_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let manager = SubscriptionManager::new(state.db.postgres.clone());

    match manager.get_for_org(org_id).await {
        Ok(Some(sub)) => Ok(Json(serde_json::json!({
            "status": "ok",
            "subscription": {
                "id": sub.id,
                "org_id": sub.org_id,
                "tier": sub.tier,
                "status": sub.status,
                "current_period_start": sub.current_period_start,
                "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "trial_end": sub.trial_end,
                "query_limit": sub.effective_query_limit(),
            }
        }))),
        Ok(None) => Err(not_found("no active subscription for this org")),
        Err(e) => {
            tracing::error!(error = %e, "Failed to fetch subscription");
            Err(internal_error(&e.to_string()))
        }
    }
}

/// PUT /billing/subscriptions/:id/tier — Change subscription tier
pub async fn change_tier(
    State(state): State<Arc<AppState>>,
    Path(subscription_id): Path<Uuid>,
    Json(req): Json<ChangeTierRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let new_tier: SubscriptionTier = req
        .new_tier
        .parse()
        .map_err(|_| bad_request("invalid tier"))?;

    let manager = SubscriptionManager::new(state.db.postgres.clone());

    match manager.change_tier(subscription_id, new_tier).await {
        Ok(sub) => Ok(Json(serde_json::json!({
            "status": "ok",
            "subscription": {
                "id": sub.id,
                "tier": sub.tier,
                "updated_at": sub.updated_at,
            }
        }))),
        Err(e) => {
            tracing::error!(error = %e, "Failed to change tier");
            Err(internal_error(&e.to_string()))
        }
    }
}

/// POST /billing/subscriptions/:id/cancel — Cancel at period end
pub async fn cancel_subscription(
    State(state): State<Arc<AppState>>,
    Path(subscription_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let manager = SubscriptionManager::new(state.db.postgres.clone());

    match manager.cancel_at_period_end(subscription_id).await {
        Ok(sub) => Ok(Json(serde_json::json!({
            "status": "ok",
            "message": "subscription will be canceled at end of current billing period",
            "current_period_end": sub.current_period_end,
        }))),
        Err(e) => {
            tracing::error!(error = %e, "Failed to cancel subscription");
            Err(internal_error(&e.to_string()))
        }
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// API KEY ENDPOINTS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#[derive(Deserialize)]
pub struct CreateApiKeyRequest {
    pub org_id: Uuid,
    pub subscription_id: Uuid,
    pub name: String,
    pub scopes: Vec<String>,
}

/// POST /billing/api-keys — Generate a new API key
pub async fn create_api_key(
    State(state): State<Arc<AppState>>,
    Json(req): Json<CreateApiKeyRequest>,
) -> Result<(StatusCode, Json<serde_json::Value>), (StatusCode, Json<ErrorResponse>)> {
    // Resolve tier from subscription
    let sub_manager = SubscriptionManager::new(state.db.postgres.clone());
    let sub = sub_manager
        .get_by_id(req.subscription_id)
        .await
        .map_err(|e| internal_error(&e.to_string()))?;

    let tier = sub.tier_enum();

    // Parse scopes
    let scopes: Vec<ApiKeyScope> = req
        .scopes
        .iter()
        .filter_map(|s| match s.as_str() {
            "intelligence:read" => Some(ApiKeyScope::IntelligenceRead),
            "reports:write" => Some(ApiKeyScope::ReportsWrite),
            "data:export" => Some(ApiKeyScope::DataExport),
            "credit:scoring" => Some(ApiKeyScope::CreditScoring),
            "billing:manage" => Some(ApiKeyScope::BillingManage),
            "streaming" => Some(ApiKeyScope::Streaming),
            "admin" => Some(ApiKeyScope::Admin),
            _ => None,
        })
        .collect();

    let manager = ApiKeyManager::new(state.db.postgres.clone(), state.db.redis.clone());

    match manager
        .create(req.org_id, req.subscription_id, &tier, &req.name, scopes)
        .await
    {
        Ok((full_key, key)) => Ok((
            StatusCode::CREATED,
            Json(serde_json::json!({
                "status": "ok",
                "api_key": {
                    "id": key.id,
                    "key": full_key,
                    "key_prefix": key.key_prefix,
                    "name": key.name,
                    "scopes": key.scopes,
                    "expires_at": key.expires_at,
                    "created_at": key.created_at,
                },
                "warning": "Store this key securely — it will NOT be shown again."
            })),
        )),
        Err(e) => {
            tracing::error!(error = %e, "Failed to create API key");
            Err(internal_error(&e.to_string()))
        }
    }
}

/// GET /billing/api-keys/:org_id — List API keys for an org
pub async fn list_api_keys(
    State(state): State<Arc<AppState>>,
    Path(org_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let manager = ApiKeyManager::new(state.db.postgres.clone(), state.db.redis.clone());

    match manager.list_for_org(org_id).await {
        Ok(keys) => {
            let key_list: Vec<serde_json::Value> = keys
                .iter()
                .map(|k| {
                    serde_json::json!({
                        "id": k.id,
                        "key_prefix": k.key_prefix,
                        "name": k.name,
                        "scopes": k.scopes,
                        "is_active": k.is_active,
                        "last_used_at": k.last_used_at,
                        "expires_at": k.expires_at,
                        "created_at": k.created_at,
                    })
                })
                .collect();

            Ok(Json(serde_json::json!({
                "status": "ok",
                "keys": key_list,
                "total": key_list.len(),
            })))
        }
        Err(e) => {
            tracing::error!(error = %e, "Failed to list API keys");
            Err(internal_error(&e.to_string()))
        }
    }
}

/// DELETE /billing/api-keys/:id — Revoke an API key
pub async fn revoke_api_key(
    State(state): State<Arc<AppState>>,
    Path(key_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let manager = ApiKeyManager::new(state.db.postgres.clone(), state.db.redis.clone());

    match manager.revoke(key_id).await {
        Ok(()) => Ok(Json(serde_json::json!({
            "status": "ok",
            "message": "API key revoked",
        }))),
        Err(e) => {
            tracing::error!(error = %e, "Failed to revoke API key");
            Err(internal_error(&e.to_string()))
        }
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// USAGE ENDPOINTS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/// GET /billing/usage/:org_id — Get usage summary for current billing period
pub async fn get_usage(
    State(state): State<Arc<AppState>>,
    Path(org_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let sub_manager = SubscriptionManager::new(state.db.postgres.clone());
    let sub = match sub_manager.get_for_org(org_id).await {
        Ok(Some(s)) => s,
        Ok(None) => return Err(not_found("no active subscription")),
        Err(e) => return Err(internal_error(&e.to_string())),
    };

    let usage_meter = UsageMeter::new(state.db.postgres.clone(), state.db.redis.clone());

    match usage_meter.get_summary(org_id, &sub).await {
        Ok(summary) => Ok(Json(serde_json::json!({
            "status": "ok",
            "usage": {
                "org_id": summary.org_id,
                "period_start": summary.period_start,
                "period_end": summary.period_end,
                "queries": {
                    "used": summary.queries_used,
                    "limit": summary.queries_limit,
                    "remaining": summary.queries_limit.map(|l| l.saturating_sub(summary.queries_used)),
                },
                "reports": {
                    "used": summary.reports_used,
                    "limit": summary.reports_limit,
                    "remaining": summary.reports_limit.map(|l| l.saturating_sub(summary.reports_used)),
                },
                "exports": {
                    "used": summary.exports_used,
                    "limit": summary.exports_limit,
                    "remaining": summary.exports_limit.map(|l| l.saturating_sub(summary.exports_used)),
                },
                "streaming_minutes": summary.streaming_minutes_used,
                "credit_scores": summary.credit_scores_used,
                "total_cost_cents": summary.total_cost_cents,
            }
        }))),
        Err(e) => {
            tracing::error!(error = %e, "Failed to fetch usage");
            Err(internal_error(&e.to_string()))
        }
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// INVOICE ENDPOINTS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/// GET /billing/invoices/:org_id — List invoices for an org
pub async fn list_invoices(
    State(state): State<Arc<AppState>>,
    Path(org_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let generator = InvoiceGenerator::new(state.db.postgres.clone());

    match generator.list_for_org(org_id).await {
        Ok(invoices) => {
            let invoice_list: Vec<serde_json::Value> = invoices
                .iter()
                .map(|inv| {
                    serde_json::json!({
                        "id": inv.id,
                        "invoice_number": inv.invoice_number,
                        "status": inv.status,
                        "currency": inv.currency,
                        "subtotal_cents": inv.subtotal_cents,
                        "tax_cents": inv.tax_cents,
                        "total_cents": inv.total_cents,
                        "period_start": inv.period_start,
                        "period_end": inv.period_end,
                        "due_date": inv.due_date,
                        "paid_at": inv.paid_at,
                        "line_items": inv.parsed_line_items(),
                        "created_at": inv.created_at,
                    })
                })
                .collect();

            Ok(Json(serde_json::json!({
                "status": "ok",
                "invoices": invoice_list,
                "total": invoice_list.len(),
            })))
        }
        Err(e) => {
            tracing::error!(error = %e, "Failed to list invoices");
            Err(internal_error(&e.to_string()))
        }
    }
}

/// GET /billing/invoices/detail/:id — Get a single invoice
pub async fn get_invoice(
    State(state): State<Arc<AppState>>,
    Path(invoice_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let generator = InvoiceGenerator::new(state.db.postgres.clone());

    match generator.get_by_id(invoice_id).await {
        Ok(inv) => Ok(Json(serde_json::json!({
            "status": "ok",
            "invoice": {
                "id": inv.id,
                "org_id": inv.org_id,
                "subscription_id": inv.subscription_id,
                "invoice_number": inv.invoice_number,
                "status": inv.status,
                "currency": inv.currency,
                "subtotal_cents": inv.subtotal_cents,
                "tax_cents": inv.tax_cents,
                "total_cents": inv.total_cents,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "due_date": inv.due_date,
                "paid_at": inv.paid_at,
                "line_items": inv.parsed_line_items(),
                "notes": inv.notes,
                "created_at": inv.created_at,
            }
        }))),
        Err(e) => {
            tracing::error!(error = %e, "Failed to fetch invoice");
            Err(not_found(&e.to_string()))
        }
    }
}

/// POST /billing/invoices/:id/finalize — Finalize a draft invoice
pub async fn finalize_invoice(
    State(state): State<Arc<AppState>>,
    Path(invoice_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let generator = InvoiceGenerator::new(state.db.postgres.clone());

    match generator.finalize(invoice_id).await {
        Ok(inv) => Ok(Json(serde_json::json!({
            "status": "ok",
            "invoice_id": inv.id,
            "invoice_number": inv.invoice_number,
            "total_cents": inv.total_cents,
        }))),
        Err(e) => {
            tracing::error!(error = %e, "Failed to finalize invoice");
            Err(internal_error(&e.to_string()))
        }
    }
}

/// POST /billing/invoices/:id/pay — Mark an invoice as paid
pub async fn pay_invoice(
    State(state): State<Arc<AppState>>,
    Path(invoice_id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, Json<ErrorResponse>)> {
    let generator = InvoiceGenerator::new(state.db.postgres.clone());

    match generator.mark_paid(invoice_id).await {
        Ok(inv) => Ok(Json(serde_json::json!({
            "status": "ok",
            "invoice_id": inv.id,
            "paid_at": inv.paid_at,
        }))),
        Err(e) => {
            tracing::error!(error = %e, "Failed to mark invoice as paid");
            Err(internal_error(&e.to_string()))
        }
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// TIER INFO ENDPOINT (public, no auth required)
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/// GET /billing/tiers — List all available tiers and their features
pub async fn list_tiers(
    State(_state): State<Arc<AppState>>,
) -> Json<serde_json::Value> {
    let tiers = vec![
        serde_json::json!({
            "tier": "free",
            "monthly_price": "$0",
            "query_limit": 100,
            "report_limit": 2,
            "export_limit": 0,
            "max_api_keys": 1,
            "rate_limit_per_minute": 10,
            "streaming": false,
            "custom_reports": false,
            "sla": false,
        }),
        serde_json::json!({
            "tier": "starter",
            "monthly_price": "$299",
            "query_limit": 5000,
            "report_limit": 20,
            "export_limit": 5,
            "max_api_keys": 3,
            "rate_limit_per_minute": 60,
            "streaming": false,
            "custom_reports": false,
            "sla": false,
        }),
        serde_json::json!({
            "tier": "pro",
            "monthly_price": "$1,499",
            "query_limit": 50000,
            "report_limit": 100,
            "export_limit": 50,
            "max_api_keys": 10,
            "rate_limit_per_minute": 300,
            "streaming": true,
            "custom_reports": true,
            "sla": false,
        }),
        serde_json::json!({
            "tier": "enterprise",
            "monthly_price": "Custom",
            "query_limit": null,
            "report_limit": null,
            "export_limit": null,
            "max_api_keys": 100,
            "rate_limit_per_minute": 2000,
            "streaming": true,
            "custom_reports": true,
            "sla": true,
        }),
    ];

    Json(serde_json::json!({
        "status": "ok",
        "tiers": tiers,
    }))
}
