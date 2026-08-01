// Billing Module — Revenue Collection System for Angavu Intelligence Backend
//
// Implements the complete billing lifecycle:
// 1. Usage metering (API call tracking per user per billing cycle)
// 2. Subscription lifecycle (Trial → Active → PastDue → Suspended → Cancelled)
// 3. M-Pesa STK Push payment integration (Safaricom Daraja API)
// 4. Invoice generation and delivery
//
// Architecture:
// - Redis: Hot storage for real-time usage counters (fast reads, atomic increments)
// - PostgreSQL: Persistent storage for subscriptions, invoices, payment records
// - ClickHouse: Analytics storage for usage event logs (OLAP queries)

pub mod metering;
pub mod subscription;
pub mod mpesa;
pub mod invoice;

use axum::{
    extract::State,
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post, put},
    Json, Router,
};
use serde::{Deserialize, Serialize};

use crate::gateway::auth::Claims;
use crate::gateway::error::ErrorResponse;
use crate::gateway::GatewayState;

/// Build the billing API router.
/// All routes require JWT authentication (enforced by parent router).
pub fn billing_router() -> Router<GatewayState> {
    Router::new()
        // Subscription management
        .route("/api/v1/billing/subscriptions", post(create_subscription))
        .route("/api/v1/billing/subscriptions/me", get(get_my_subscription))
        .route("/api/v1/billing/subscriptions/cancel", post(cancel_subscription))
        .route("/api/v1/billing/subscriptions/reactivate", post(reactivate_subscription))
        // Usage
        .route("/api/v1/billing/usage", get(get_my_usage))
        // Payments (M-Pesa STK Push)
        .route("/api/v1/billing/payments/initiate", post(initiate_payment))
        .route("/api/v1/billing/payments/{txn_id}/status", get(check_payment_status))
        // Invoices
        .route("/api/v1/billing/invoices", get(list_invoices))
        .route("/api/v1/billing/invoices/{invoice_id}", get(get_invoice))
        .route("/api/v1/billing/invoices/{invoice_id}/pdf", get(download_invoice_pdf))
}

// ═══════════════════════════════════════════════════════════
//  HANDLERS
// ═══════════════════════════════════════════════════════════

/// POST /api/v1/billing/subscriptions
/// Create a new subscription for the authenticated user's org.
async fn create_subscription(
    State(state): State<GatewayState>,
    claims: Claims,
    Json(req): Json<subscription::CreateSubscriptionRequest>,
) -> impl IntoResponse {
    match subscription::create_subscription(&state.db, &state.redis, &claims.org_id, req).await {
        Ok(sub) => (StatusCode::CREATED, Json(serde_json::to_value(sub).unwrap())).into_response(),
        Err(e) => {
            tracing::error!(error = %e, org_id = %claims.org_id, "Failed to create subscription");
            ErrorResponse::internal().into_response()
        }
    }
}

/// GET /api/v1/billing/subscriptions/me
/// Get the current subscription for the authenticated user's org.
async fn get_my_subscription(
    State(state): State<GatewayState>,
    claims: Claims,
) -> impl IntoResponse {
    match subscription::get_active_subscription(&state.db, &claims.org_id).await {
        Ok(Some(sub)) => Json(serde_json::to_value(sub).unwrap()).into_response(),
        Ok(None) => ErrorResponse::not_found("Subscription").into_response(),
        Err(e) => {
            tracing::error!(error = %e, org_id = %claims.org_id, "Failed to get subscription");
            ErrorResponse::internal().into_response()
        }
    }
}

/// POST /api/v1/billing/subscriptions/cancel
/// Cancel the current subscription (takes effect at end of billing cycle).
async fn cancel_subscription(
    State(state): State<GatewayState>,
    claims: Claims,
) -> impl IntoResponse {
    match subscription::cancel_subscription(&state.db, &claims.org_id).await {
        Ok(sub) => Json(serde_json::to_value(sub).unwrap()).into_response(),
        Err(e) => {
            tracing::error!(error = %e, org_id = %claims.org_id, "Failed to cancel subscription");
            ErrorResponse::internal().into_response()
        }
    }
}

/// POST /api/v1/billing/subscriptions/reactivate
/// Reactivate a cancelled subscription before the end of the billing cycle.
async fn reactivate_subscription(
    State(state): State<GatewayState>,
    claims: Claims,
) -> impl IntoResponse {
    match subscription::reactivate_subscription(&state.db, &claims.org_id).await {
        Ok(sub) => Json(serde_json::to_value(sub).unwrap()).into_response(),
        Err(e) => {
            tracing::error!(error = %e, org_id = %claims.org_id, "Failed to reactivate subscription");
            ErrorResponse::internal().into_response()
        }
    }
}

/// GET /api/v1/billing/usage
/// Get current billing cycle usage for the authenticated user's org.
async fn get_my_usage(
    State(state): State<GatewayState>,
    claims: Claims,
) -> impl IntoResponse {
    match metering::get_usage_summary(&state.redis, &state.db, &claims.org_id, &claims.tier).await {
        Ok(usage) => Json(serde_json::to_value(usage).unwrap()).into_response(),
        Err(e) => {
            tracing::error!(error = %e, org_id = %claims.org_id, "Failed to get usage");
            ErrorResponse::internal().into_response()
        }
    }
}

/// POST /api/v1/billing/payments/initiate
/// Initiate an M-Pesa STK Push payment.
async fn initiate_payment(
    State(state): State<GatewayState>,
    claims: Claims,
    Json(req): Json<mpesa::StkPushRequest>,
) -> impl IntoResponse {
    // Load M-Pesa config from webhook state (shared config)
    let mpesa_config = crate::webhook::MpesaConfig {
        passkey: std::env::var("MPESA_PASSKEY").unwrap_or_default(),
        shortcode: std::env::var("MPESA_SHORTCODE")
            .unwrap_or_else(|_| "174379".to_string()),
        initiator_password: std::env::var("MPESA_INITIATOR_PASSWORD").unwrap_or_default(),
        environment: match std::env::var("MPESA_ENVIRONMENT").as_deref() {
            Ok("production") => crate::webhook::MpesaEnvironment::Production,
            _ => crate::webhook::MpesaEnvironment::Sandbox,
        },
    };

    match mpesa::initiate_stk_push(&state.db, &state.redis, &mpesa_config, &claims.org_id, req).await {
        Ok(resp) => (StatusCode::ACCEPTED, Json(serde_json::to_value(resp).unwrap())).into_response(),
        Err(e) => {
            tracing::error!(error = %e, org_id = %claims.org_id, "Failed to initiate payment");
            ErrorResponse::internal().into_response()
        }
    }
}

/// GET /api/v1/billing/payments/{txn_id}/status
/// Check the status of an M-Pesa payment.
async fn check_payment_status(
    State(state): State<GatewayState>,
    claims: Claims,
    axum::extract::Path(txn_id): axum::extract::Path<String>,
) -> impl IntoResponse {
    match mpesa::get_payment_status(&state.db, &claims.org_id, &txn_id).await {
        Ok(Some(status)) => Json(serde_json::to_value(status).unwrap()).into_response(),
        Ok(None) => ErrorResponse::not_found("Payment").into_response(),
        Err(e) => {
            tracing::error!(error = %e, txn_id = %txn_id, "Failed to check payment status");
            ErrorResponse::internal().into_response()
        }
    }
}

/// GET /api/v1/billing/invoices
/// List invoices for the authenticated user's org.
async fn list_invoices(
    State(state): State<GatewayState>,
    claims: Claims,
    axum::extract::Query(params): axum::extract::Query<invoice::InvoiceListParams>,
) -> impl IntoResponse {
    match invoice::list_invoices(&state.db, &claims.org_id, params).await {
        Ok(invoices) => Json(serde_json::json!({ "invoices": invoices })).into_response(),
        Err(e) => {
            tracing::error!(error = %e, org_id = %claims.org_id, "Failed to list invoices");
            ErrorResponse::internal().into_response()
        }
    }
}

/// GET /api/v1/billing/invoices/{invoice_id}
/// Get a specific invoice.
async fn get_invoice(
    State(state): State<GatewayState>,
    claims: Claims,
    axum::extract::Path(invoice_id): axum::extract::Path<String>,
) -> impl IntoResponse {
    match invoice::get_invoice(&state.db, &claims.org_id, &invoice_id).await {
        Ok(Some(inv)) => Json(serde_json::to_value(inv).unwrap()).into_response(),
        Ok(None) => ErrorResponse::not_found("Invoice").into_response(),
        Err(e) => {
            tracing::error!(error = %e, invoice_id = %invoice_id, "Failed to get invoice");
            ErrorResponse::internal().into_response()
        }
    }
}

/// GET /api/v1/billing/invoices/{invoice_id}/pdf
/// Download invoice as PDF.
async fn download_invoice_pdf(
    State(state): State<GatewayState>,
    claims: Claims,
    axum::extract::Path(invoice_id): axum::extract::Path<String>,
) -> impl IntoResponse {
    match invoice::generate_invoice_pdf(&state.db, &claims.org_id, &invoice_id).await {
        Ok(pdf_bytes) => {
            let headers = [
                (axum::http::header::CONTENT_TYPE, "application/pdf".to_string()),
                (
                    axum::http::header::CONTENT_DISPOSITION,
                    format!("attachment; filename=\"invoice-{}.pdf\"", invoice_id),
                ),
            ];
            (StatusCode::OK, headers, pdf_bytes).into_response()
        }
        Err(e) => {
            tracing::error!(error = %e, invoice_id = %invoice_id, "Failed to generate PDF");
            ErrorResponse::internal().into_response()
        }
    }
}
