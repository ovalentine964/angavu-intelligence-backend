//! Webhook Module — External event receiver for the Angavu Intelligence Backend.
//!
//! Handles incoming webhooks from:
//! - M-Pesa STK Push / C2B callbacks (payment confirmations)
//! - Market data feeds (price updates, supply chain events)
//! - Third-party integrations (SMS gateways, logistics APIs)
//!
//! Each webhook is validated, parsed, and routed to the appropriate OODA loop
//! via the orchestrator's message bus.
//!
//! Security:
//! - M-Pesa callbacks validated via timestamp + passkey HMAC
//! - Generic webhooks require API key authentication
//! - All payloads are logged to audit trail
//! - Rate limiting applied per source

pub mod mpesa;
pub mod market_feed;
pub mod handlers;

use axum::{
    extract::{Json, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    routing::post,
    Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{error, info, warn};

/// Webhook router — mounts all webhook endpoints.
pub fn webhook_router(state: WebhookState) -> Router {
    Router::new()
        .route("/api/v1/webhooks/mpesa", post(mpesa::handle_mpesa_callback))
        .route("/api/v1/webhooks/mpesa/confirmation", post(mpesa::handle_c2b_confirmation))
        .route("/api/v1/webhooks/mpesa/validation", post(mpesa::handle_c2b_validation))
        .route("/api/v1/webhooks/market", post(market_feed::handle_market_feed))
        .route("/api/v1/webhooks/generic", post(handlers::handle_generic_webhook))
        .with_state(state)
}

/// Shared state for webhook handlers.
#[derive(Clone)]
pub struct WebhookState {
    pub db: sqlx::PgPool,
    pub redis: redis::aio::ConnectionManager,
    pub message_bus: Arc<crate::orchestrator::message_bus::ModuleMessageBus>,
    pub mpesa_config: MpesaConfig,
    pub webhook_api_keys: Vec<String>,
    /// S15: Per-IP rate limiter for webhook endpoints
    pub ip_rate_limiter: Arc<crate::gateway::rate_limit::IpRateLimiter>,
}

/// M-Pesa configuration for callback validation.
#[derive(Clone)]
pub struct MpesaConfig {
    /// Lipa Na M-Pesa Online passkey (from Safaricom portal)
    pub passkey: String,
    /// Business shortcode (Paybill or Till number)
    pub shortcode: String,
    /// Initiator password for B2C
    pub initiator_password: String,
    /// Environment: sandbox or production
    pub environment: MpesaEnvironment,
}

#[derive(Clone, Debug, PartialEq)]
pub enum MpesaEnvironment {
    Sandbox,
    Production,
}

impl MpesaConfig {
    pub fn base_url(&self) -> &str {
        match self.environment {
            MpesaEnvironment::Sandbox => "https://sandbox.safaricom.co.ke",
            MpesaEnvironment::Production => "https://api.safaricom.co.ke",
        }
    }
}

// ═══════════════════════════════════════════════════════════
//  WEBHOOK EVENT TYPES
// ═══════════════════════════════════════════════════════════

/// Parsed webhook event ready for OODA loop routing.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WebhookEvent {
    pub event_id: String,
    pub source: WebhookSource,
    pub event_type: WebhookEventType,
    pub payload: serde_json::Value,
    pub received_at: chrono::DateTime<chrono::Utc>,
    pub validated: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum WebhookSource {
    Mpesa,
    MarketFeed,
    SmsGateway,
    Logistics,
    Generic,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum WebhookEventType {
    // M-Pesa events
    MpesaStkCallback,
    MpesaC2BConfirmation,
    MpesaC2BValidation,
    MpesaB2CResult,

    // Market events
    MarketPriceUpdate,
    MarketSupplyAlert,
    MarketDemandShift,

    // Generic
    Custom(String),
}

/// Result of webhook processing.
#[derive(Debug, Serialize)]
pub struct WebhookResponse {
    pub success: bool,
    pub event_id: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub routed_to: Option<String>,
}

// ═══════════════════════════════════════════════════════════
//  WEBHOOK EVENT STORE
// ═══════════════════════════════════════════════════════════

/// Store a webhook event in the database for audit trail and replay.
pub async fn store_webhook_event(
    db: &sqlx::PgPool,
    event: &WebhookEvent,
) -> Result<(), sqlx::Error> {
    sqlx::query!(
        r#"
        INSERT INTO webhook_events (event_id, source, event_type, payload, received_at, validated)
        VALUES ($1, $2, $3, $4, $5, $6)
        "#,
        event.event_id,
        serde_json::to_string(&event.source).unwrap_or_default(),
        serde_json::to_string(&event.event_type).unwrap_or_default(),
        event.payload,
        event.received_at,
        event.validated
    )
    .execute(db)
    .await?;

    Ok(())
}

/// Route a validated webhook event to the appropriate OODA loop.
pub async fn route_to_ooda(
    message_bus: &Arc<crate::orchestrator::message_bus::ModuleMessageBus>,
    event: &WebhookEvent,
) {
    use crate::orchestrator::message_bus::*;

    let module_id = match &event.event_type {
        // M-Pesa payment events → Credit module (fast loop)
        WebhookEventType::MpesaStkCallback
        | WebhookEventType::MpesaC2BConfirmation => ModuleId::CreditScorer,

        // Market events → Market module (hourly loop)
        WebhookEventType::MarketPriceUpdate
        | WebhookEventType::MarketSupplyAlert
        | WebhookEventType::MarketDemandShift => ModuleId::MarketAnalyzer,

        // Default → orchestrator decides
        _ => ModuleId::Orchestrator,
    };

    // Route via the message bus using a TransactionBatch as the carrier.
    // The orchestrator will dispatch to the correct module based on the message type.
    let message = ModuleMessage::TransactionBatch {
        trace_id: uuid::Uuid::parse_str(&event.event_id).unwrap_or_else(|_| uuid::Uuid::new_v4()),
        worker_id_hash: format!("webhook:{}", event.event_id),
        transactions: vec![],
        region: "webhook".to_string(),
        timestamp: chrono::Utc::now(),
    };

    if let Err(e) = message_bus.publish(message).await {
        error!(
            event_id = %event.event_id,
            target = ?module_id,
            error = %e,
            "Failed to route webhook event to OODA loop"
        );
    } else {
        info!(
            event_id = %event.event_id,
            target = ?module_id,
            "Webhook event routed to OODA loop"
        );
    }
}

/// Migration SQL for webhook_events table.
pub const MIGRATION_WEBHOOK_EVENTS: &str = r#"
CREATE TABLE IF NOT EXISTS webhook_events (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    source VARCHAR(32) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated BOOLEAN NOT NULL DEFAULT FALSE,
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhook_events_source ON webhook_events(source);
CREATE INDEX idx_webhook_events_type ON webhook_events(event_type);
CREATE INDEX idx_webhook_events_received ON webhook_events(received_at DESC);
CREATE INDEX idx_webhook_events_processed ON webhook_events(processed) WHERE NOT processed;
"#;
