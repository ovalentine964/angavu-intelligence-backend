//! Webhook Integration — Connects webhook module routes to the gateway.
//!
//! This module provides the function to mount webhook routes onto the
//! main gateway router, bridging the webhook module with the gateway state.

use axum::Router;
use std::sync::Arc;

use crate::webhook::{self, WebhookState, MpesaConfig, MpesaEnvironment};

/// Create the webhook state from environment variables and shared resources.
pub fn create_webhook_state(
    db: sqlx::PgPool,
    redis: redis::aio::ConnectionManager,
    message_bus: Arc<crate::orchestrator::message_bus::ModuleMessageBus>,
) -> WebhookState {
    let mpesa_config = MpesaConfig {
        passkey: std::env::var("MPESA_PASSKEY")
            .unwrap_or_else(|_| "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919".to_string()),
        shortcode: std::env::var("MPESA_SHORTCODE")
            .unwrap_or_else(|_| "174379".to_string()),
        initiator_password: std::env::var("MPESA_INITIATOR_PASSWORD")
            .unwrap_or_default(),
        environment: match std::env::var("MPESA_ENVIRONMENT").as_deref() {
            Ok("production") => MpesaEnvironment::Production,
            _ => MpesaEnvironment::Sandbox,
        },
    };

    let webhook_api_keys: Vec<String> = std::env::var("WEBHOOK_API_KEYS")
        .unwrap_or_else(|_| "default-webhook-key".to_string())
        .split(',')
        .map(|s| s.trim().to_string())
        .collect();

    WebhookState {
        db,
        redis,
        message_bus,
        mpesa_config,
        webhook_api_keys,
    }
}
