//! Generic Webhook Handler
//!
//! Accepts arbitrary webhook events from third-party integrations.
//! Validates API key, parses the payload, and routes to OODA loop.
//!
//! Supports:
//! - SMS gateway delivery reports
//! - Logistics/delivery status updates
//! - Custom integrations from business partners
//!
//! Authentication: API key in X-Webhook-Key header.

use axum::{
    extract::{Json, State, HeaderMap},
    http::StatusCode,
    response::IntoResponse,
};
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

use super::{WebhookEvent, WebhookEventType, WebhookSource, WebhookState, WebhookResponse, route_to_ooda, store_webhook_event};

/// Generic webhook payload.
#[derive(Debug, Deserialize, garde::Validate)]
pub struct GenericWebhookPayload {
    /// Event type identifier (e.g., "sms.delivery_report", "logistics.status_update")
    #[garde(length(min = 1, max = 128))]
    pub event_type: String,
    /// Event payload (arbitrary JSON)
    pub data: serde_json::Value,
    /// Optional event ID for idempotency
    #[garde(length(max = 128))]
    pub event_id: Option<String>,
    /// Source system identifier
    #[garde(length(max = 64))]
    pub source: Option<String>,
    /// Timestamp from source system
    #[garde(length(max = 64))]
    pub timestamp: Option<String>,
}

/// Handle generic webhook.
///
/// POST /api/v1/webhooks/generic
/// Header: X-Webhook-Key: <api_key>
pub async fn handle_generic_webhook(
    State(state): State<WebhookState>,
    headers: HeaderMap,
    Json(payload): Json<GenericWebhookPayload>,
) -> impl IntoResponse {
    // S15: Rate limiting by IP
    let client_ip = headers
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.split(',').next())
        .unwrap_or("unknown")
        .trim();

    if let Err(retry_after) = state.ip_rate_limiter.check(client_ip) {
        warn!(ip = %client_ip, "Webhook rate limit exceeded");
        let mut response = axum::response::IntoResponse::into_response(
            (StatusCode::TOO_MANY_REQUESTS, Json(serde_json::json!({
                "success": false,
                "message": "Rate limit exceeded. Try again later."
            })))
        );
        if let Ok(val) = retry_after.as_secs().to_string().parse() {
            response.headers_mut().insert("Retry-After", val);
        }
        return response;
    }

    // Validate API key
    let api_key = headers
        .get("X-Webhook-Key")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");

    if !state.webhook_api_keys.iter().any(|k| k == api_key) {
        warn!(
            event_type = %payload.event_type,
            "Webhook rejected: invalid API key"
        );
        return (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "success": false,
                "message": "Invalid API key"
            }))
        ).into_response();
    }

    // S8: Validate input payload
    use garde::Validate;
    if let Err(e) = payload.validate() {
        warn!("Webhook validation failed: {}", e);
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "success": false,
                "message": format!("Validation failed: {}", e)
            }))
        ).into_response();
    }

    let event_id = payload.event_id.clone().unwrap_or_else(|| {
        format!("generic-{}-{}", payload.event_type, chrono::Utc::now().timestamp_millis())
    });

    info!(
        event_id = %event_id,
        event_type = %payload.event_type,
        source = ?payload.source,
        "Generic webhook received"
    );

    // Map event type string to enum
    let webhook_event_type = match payload.event_type.as_str() {
        "sms.delivery_report" => WebhookEventType::Custom("sms_delivery".to_string()),
        "logistics.status_update" => WebhookEventType::Custom("logistics_status".to_string()),
        "market.supply_alert" => WebhookEventType::MarketSupplyAlert,
        "market.demand_shift" => WebhookEventType::MarketDemandShift,
        other => WebhookEventType::Custom(other.to_string()),
    };

    let event = WebhookEvent {
        event_id: event_id.clone(),
        source: WebhookSource::Generic,
        event_type: webhook_event_type,
        payload: serde_json::json!({
            "event_type": payload.event_type,
            "data": payload.data,
            "source": payload.source,
            "timestamp": payload.timestamp,
        }),
        received_at: chrono::Utc::now(),
        validated: true,
    };

    let _ = store_webhook_event(&state.db, &event).await;
    route_to_ooda(&state.message_bus, &event).await;

    (
        StatusCode::OK,
        Json(WebhookResponse {
            success: true,
            event_id,
            message: "Webhook received and queued for processing".to_string(),
            routed_to: Some("ooda_loop".to_string()),
        })
    ).into_response()
}
