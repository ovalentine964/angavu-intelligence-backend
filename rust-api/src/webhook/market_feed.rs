//! Market Data Feed Webhook Handler
//!
//! Receives market price updates from external data providers and
//! routes them to the Market module's OODA loop.
//!
//! Supports:
//! - Wholesale market price feeds (Wakulima, Gikomba, etc.)
//! - Commodity price indices
//! - Supply chain disruption alerts
//! - Regional price variations
//!
//! Feed format is normalized from provider-specific formats into
//! a standard MarketFeedEvent before routing.

use axum::{
    extract::{Json, State},
    http::StatusCode,
    response::IntoResponse,
};
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

use super::{WebhookEvent, WebhookEventType, WebhookSource, WebhookState, route_to_ooda, store_webhook_event};

// ═══════════════════════════════════════════════════════════
//  MARKET FEED PAYLOAD
// ═══════════════════════════════════════════════════════════

/// Incoming market feed payload (provider-agnostic).
#[derive(Debug, Deserialize)]
pub struct MarketFeedPayload {
    /// Provider identifier (e.g., "nafis", "kephis", "manual")
    pub provider: String,
    /// Feed items (batch of price updates)
    pub items: Vec<MarketFeedItem>,
    /// Feed timestamp from provider
    pub timestamp: Option<String>,
    /// Optional signature for verification
    pub signature: Option<String>,
}

/// A single market price update.
#[derive(Debug, Deserialize, Serialize)]
pub struct MarketFeedItem {
    /// Product name (normalized: "tomatoes", "sukuma wiki", etc.)
    pub product: String,
    /// Product category
    pub category: Option<String>,
    /// Market location (e.g., "Wakulima Market, Nairobi")
    pub market: String,
    /// Region/county
    pub region: String,
    /// Current price per unit (KES)
    pub price_per_unit: f64,
    /// Unit of measure ("kg", "bunch", "piece", "litre")
    pub unit: String,
    /// Previous price (for change calculation)
    pub previous_price: Option<f64>,
    /// Supply level ("abundant", "normal", "low", "critical")
    pub supply_level: Option<String>,
    /// Quality grade ("A", "B", "C")
    pub quality_grade: Option<String>,
}

/// Normalized market event for OODA routing.
#[derive(Debug, Serialize)]
pub struct MarketEvent {
    pub product: String,
    pub category: String,
    pub market: String,
    pub region: String,
    pub price_current: f64,
    pub price_previous: Option<f64>,
    pub price_change_pct: Option<f64>,
    pub unit: String,
    pub supply_level: String,
    pub provider: String,
}

// ═══════════════════════════════════════════════════════════
//  HANDLER
// ═══════════════════════════════════════════════════════════

/// Handle incoming market data feed.
///
/// POST /api/v1/webhooks/market
pub async fn handle_market_feed(
    State(state): State<WebhookState>,
    Json(payload): Json<MarketFeedPayload>,
) -> impl IntoResponse {
    let event_id = format!("market-{}-{}", payload.provider, chrono::Utc::now().timestamp_millis());

    info!(
        event_id = %event_id,
        provider = %payload.provider,
        items = payload.items.len(),
        "Market feed received"
    );

    if payload.items.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({
                "success": false,
                "message": "No items in feed"
            }))
        ).into_response();
    }

    // Process each feed item
    let mut processed = 0;
    let mut alerts = Vec::new();

    for item in &payload.items {
        let price_change_pct = item.previous_price.map(|prev| {
            if prev > 0.0 {
                ((item.price_per_unit - prev) / prev) * 100.0
            } else {
                0.0
            }
        });

        let market_event = MarketEvent {
            product: item.product.clone(),
            category: item.category.clone().unwrap_or_else(|| "general".to_string()),
            market: item.market.clone(),
            region: item.region.clone(),
            price_current: item.price_per_unit,
            price_previous: item.previous_price,
            price_change_pct,
            unit: item.unit.clone(),
            supply_level: item.supply_level.clone().unwrap_or_else(|| "normal".to_string()),
            provider: payload.provider.clone(),
        };

        // Detect significant price changes (>10%) for alerts
        if let Some(change) = price_change_pct {
            if change.abs() > 10.0 {
                alerts.push(serde_json::json!({
                    "product": item.product,
                    "market": item.market,
                    "change_pct": change,
                    "direction": if change > 0.0 { "up" } else { "down" },
                    "old_price": item.previous_price,
                    "new_price": item.price_per_unit,
                }));
            }
        }

        // Detect supply disruptions
        if let Some(ref supply) = item.supply_level {
            if supply == "critical" || supply == "low" {
                alerts.push(serde_json::json!({
                    "type": "supply_alert",
                    "product": item.product,
                    "market": item.market,
                    "supply_level": supply,
                }));
            }
        }

        // Store and route each item
        let webhook_event = WebhookEvent {
            event_id: format!("{}-{}", event_id, processed),
            source: WebhookSource::MarketFeed,
            event_type: WebhookEventType::MarketPriceUpdate,
            payload: serde_json::to_value(&market_event).unwrap_or_default(),
            received_at: chrono::Utc::now(),
            validated: true,
        };

        let _ = store_webhook_event(&state.db, &webhook_event).await;
        route_to_ooda(&state.message_bus, &webhook_event).await;
        processed += 1;
    }

    // Store batch-level event with alerts
    let batch_event = WebhookEvent {
        event_id: event_id.clone(),
        source: WebhookSource::MarketFeed,
        event_type: WebhookEventType::MarketPriceUpdate,
        payload: serde_json::json!({
            "provider": payload.provider,
            "items_count": payload.items.len(),
            "processed": processed,
            "alerts": alerts,
        }),
        received_at: chrono::Utc::now(),
        validated: true,
    };
    let _ = store_webhook_event(&state.db, &batch_event).await;

    info!(
        event_id = %event_id,
        processed = processed,
        alerts = alerts.len(),
        "Market feed processed"
    );

    (
        StatusCode::OK,
        Json(serde_json::json!({
            "success": true,
            "event_id": event_id,
            "processed": processed,
            "alerts_triggered": alerts.len(),
        }))
    ).into_response()
}
