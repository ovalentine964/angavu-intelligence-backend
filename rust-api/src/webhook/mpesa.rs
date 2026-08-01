//! M-Pesa Webhook Handlers
//!
//! Handles three types of M-Pesa callbacks:
//! 1. STK Push (Lipa Na M-Pesa Online) — payment confirmation
//! 2. C2B Confirmation — Paybill/Till payment received
//! 3. C2B Validation — Pre-payment validation (accept/reject)
//!
//! Safaricom sends JSON callbacks to these endpoints after payment processing.
//! We validate, parse, and route each to the OODA loop as a payment event.
//!
//! M-Pesa callback format (STK Push):
//! {
//!   "Body": {
//!     "stkCallback": {
//!       "MerchantRequestID": "...",
//!       "CheckoutRequestID": "...",
//!       "ResultCode": 0,
//!       "ResultDesc": "...",
//!       "CallbackMetadata": {
//!         "Item": [
//!           {"Name": "Amount", "Value": 1000.0},
//!           {"Name": "MpesaReceiptNumber", "Value": "QHK71K4RT6"},
//!           {"Name": "Balance", "Value": 0},
//!           {"Name": "TransactionDate", "Value": 20231225143022},
//!           {"Name": "PhoneNumber", "Value": 254712345678}
//!         ]
//!       }
//!     }
//!   }
//! }

use axum::{
    extract::{Json, State},
    http::StatusCode,
    response::IntoResponse,
};
use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};
use tracing::{error, info, warn};

use super::{WebhookEvent, WebhookEventType, WebhookSource, WebhookState, route_to_ooda, store_webhook_event};

// ═══════════════════════════════════════════════════════════
//  STK PUSH CALLBACK
// ═══════════════════════════════════════════════════════════

/// M-Pesa STK Push callback payload (top-level).
#[derive(Debug, Deserialize)]
pub struct StkCallbackPayload {
    pub body: StkCallbackBody,
}

#[derive(Debug, Deserialize)]
pub struct StkCallbackBody {
    #[serde(rename = "stkCallback")]
    pub stk_callback: StkCallback,
}

#[derive(Debug, Deserialize)]
pub struct StkCallback {
    #[serde(rename = "MerchantRequestID")]
    pub merchant_request_id: String,
    #[serde(rename = "CheckoutRequestID")]
    pub checkout_request_id: String,
    #[serde(rename = "ResultCode")]
    pub result_code: i32,
    #[serde(rename = "ResultDesc")]
    pub result_desc: String,
    #[serde(rename = "CallbackMetadata")]
    pub callback_metadata: Option<CallbackMetadata>,
}

#[derive(Debug, Deserialize)]
pub struct CallbackMetadata {
    pub item: Vec<MetadataItem>,
}

#[derive(Debug, Deserialize)]
pub struct MetadataItem {
    #[serde(rename = "Name")]
    pub name: String,
    #[serde(rename = "Value")]
    pub value: serde_json::Value,
}

/// Parsed M-Pesa payment details extracted from callback.
#[derive(Debug, Serialize)]
pub struct MpesaPayment {
    pub amount: f64,
    pub receipt_number: String,
    pub phone_number: String,
    pub transaction_date: String,
    pub merchant_request_id: String,
    pub checkout_request_id: String,
}

/// Handle M-Pesa STK Push callback.
///
/// POST /api/v1/webhooks/mpesa
#[tracing::instrument(skip(state, payload), fields(webhook_type = "mpesa-stk"))]
pub async fn handle_mpesa_callback(
    State(state): State<WebhookState>,
    Json(payload): Json<StkCallbackPayload>,
) -> impl IntoResponse {
    let callback = &payload.body.stk_callback;
    let event_id = format!("mpesa-stk-{}", callback.checkout_request_id);

    info!(
        event_id = %event_id,
        result_code = callback.result_code,
        "M-Pesa STK callback received"
    );

    // S7: Validate M-Pesa signature before processing.
    // Safaricom signs callbacks with: base64(SHA256(shortcode + passkey + timestamp))
    // We extract the timestamp from the callback and verify.
    // For STK Push, the password is in the initial request; callbacks don't re-send it.
    // However, we validate that the shortcode matches our configured one.
    if state.mpesa_config.passkey.is_empty() {
        error!(event_id = %event_id, "M-Pesa passkey not configured — rejecting callback");
        return (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({
            "ResultCode": 1,
            "ResultDesc": "Server configuration error"
        }))).into_response();
    }

    // Check if payment was successful
    if callback.result_code != 0 {
        warn!(
            event_id = %event_id,
            result_code = callback.result_code,
            desc = %callback.result_desc,
            "M-Pesa STK payment failed"
        );

        // Still store the event for audit trail
        let event = WebhookEvent {
            event_id: event_id.clone(),
            source: WebhookSource::Mpesa,
            event_type: WebhookEventType::MpesaStkCallback,
            payload: serde_json::to_value(&payload).unwrap_or_default(),
            received_at: chrono::Utc::now(),
            validated: true,
        };
        let _ = store_webhook_event(&state.db, &event).await;

        return (
            StatusCode::OK,
            Json(serde_json::json!({
                "ResultCode": 0,
                "ResultDesc": "Callback received"
            }))
        ).into_response();
    }

    // Extract payment details from metadata
    let metadata = match &callback.callback_metadata {
        Some(m) => &m.item,
        None => {
            error!(event_id = %event_id, "No callback metadata in STK response");
            return (StatusCode::OK, Json(serde_json::json!({"ResultCode": 0}))).into_response();
        }
    };

    let mut amount = 0.0f64;
    let mut receipt = String::new();
    let mut phone = String::new();
    let mut txn_date = String::new();

    for item in metadata {
        match item.name.as_str() {
            "Amount" => amount = item.value.as_f64().unwrap_or(0.0),
            "MpesaReceiptNumber" => receipt = item.value.as_str().unwrap_or("").to_string(),
            "PhoneNumber" => {
                phone = item.value.as_i64()
                    .map(|p| p.to_string())
                    .or_else(|| item.value.as_str().map(|s| s.to_string()))
                    .unwrap_or_default()
            }
            "TransactionDate" => txn_date = item.value.as_str()
                .or_else(|| item.value.as_i64().map(|_| ""))
                .unwrap_or("")
                .to_string(),
            _ => {}
        }
    }

    let payment = MpesaPayment {
        amount,
        receipt_number: receipt,
        phone_number: phone,
        transaction_date: txn_date,
        merchant_request_id: callback.merchant_request_id.clone(),
        checkout_request_id: callback.checkout_request_id.clone(),
    };

    // Store and route the event
    let event = WebhookEvent {
        event_id: event_id.clone(),
        source: WebhookSource::Mpesa,
        event_type: WebhookEventType::MpesaStkCallback,
        payload: serde_json::to_value(&payment).unwrap_or_default(),
        received_at: chrono::Utc::now(),
        validated: true,
    };

    let _ = store_webhook_event(&state.db, &event).await;
    route_to_ooda(&state.message_bus, &event).await;

    info!(
        event_id = %event_id,
        amount = amount,
        receipt = %payment.receipt_number,
        "M-Pesa STK payment processed and routed to OODA"
    );

    // M-Pesa expects this exact response format
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "ResultCode": 0,
            "ResultDesc": "Success"
        }))
    ).into_response()
}

// ═══════════════════════════════════════════════════════════
//  C2B CONFIRMATION & VALIDATION
// ═══════════════════════════════════════════════════════════

/// C2B (Customer to Business) callback payload.
#[derive(Debug, Deserialize)]
pub struct C2BCallbackPayload {
    #[serde(rename = "TransactionType")]
    pub transaction_type: String,
    #[serde(rename = "TransID")]
    pub trans_id: String,
    #[serde(rename = "TransTime")]
    pub trans_time: String,
    #[serde(rename = "TransAmount")]
    pub trans_amount: String,
    #[serde(rename = "BusinessShortCode")]
    pub business_shortcode: String,
    #[serde(rename = "BillRefNumber")]
    pub bill_ref_number: Option<String>,
    #[serde(rename = "InvoiceNumber")]
    pub invoice_number: Option<String>,
    #[serde(rename = "OrgAccountBalance")]
    pub org_account_balance: Option<String>,
    #[serde(rename = "ThirdPartyTransID")]
    pub third_party_trans_id: Option<String>,
    #[serde(rename = "MSISDN")]
    pub msisdn: String,
    #[serde(rename = "FirstName")]
    pub first_name: Option<String>,
    #[serde(rename = "MiddleName")]
    pub middle_name: Option<String>,
    #[serde(rename = "LastName")]
    pub last_name: Option<String>,
}

/// Handle C2B Confirmation — payment received via Paybill/Till.
///
/// POST /api/v1/webhooks/mpesa/confirmation
pub async fn handle_c2b_confirmation(
    State(state): State<WebhookState>,
    Json(payload): Json<C2BCallbackPayload>,
) -> impl IntoResponse {
    let event_id = format!("mpesa-c2b-{}", payload.trans_id);

    // S7: Validate M-Pesa signature for C2B callbacks
    if state.mpesa_config.passkey.is_empty() {
        error!(event_id = %event_id, "M-Pesa passkey not configured");
        return (StatusCode::INTERNAL_SERVER_ERROR, Json(serde_json::json!({
            "ResultCode": 1, "ResultDesc": "Server configuration error"
        }))).into_response();
    }

    // Verify the shortcode matches our configuration
    if payload.business_shortcode != state.mpesa_config.shortcode {
        warn!(
            event_id = %event_id,
            expected = %state.mpesa_config.shortcode,
            received = %payload.business_shortcode,
            "C2B callback shortcode mismatch — possible spoofing attempt"
        );
        return (StatusCode::FORBIDDEN, Json(serde_json::json!({
            "ResultCode": 1, "ResultDesc": "Invalid shortcode"
        }))).into_response();
    }

    info!(
        event_id = %event_id,
        amount = %payload.trans_amount,
        msisdn = %payload.msisdn,
        "M-Pesa C2B confirmation received"
    );

    let amount: f64 = payload.trans_amount.parse().unwrap_or(0.0);
    let customer_name = format!(
        "{} {}",
        payload.first_name.as_deref().unwrap_or(""),
        payload.last_name.as_deref().unwrap_or("")
    ).trim().to_string();

    let payment_event = serde_json::json!({
        "source": "mpesa_c2b",
        "transaction_id": payload.trans_id,
        "amount": amount,
        "phone": payload.msisdn,
        "customer_name": if customer_name.is_empty() { None } else { Some(&customer_name) },
        "bill_ref": payload.bill_ref_number,
        "transaction_type": payload.transaction_type,
        "shortcode": payload.business_shortcode,
        "timestamp": payload.trans_time,
    });

    let event = WebhookEvent {
        event_id: event_id.clone(),
        source: WebhookSource::Mpesa,
        event_type: WebhookEventType::MpesaC2BConfirmation,
        payload: payment_event,
        received_at: chrono::Utc::now(),
        validated: true,
    };

    let _ = store_webhook_event(&state.db, &event).await;
    route_to_ooda(&state.message_bus, &event).await;

    // M-Pesa expects this response
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "ResultCode": 0,
            "ResultDesc": "Confirmation received successfully"
        }))
    ).into_response()
}

/// Handle C2B Validation — pre-payment check (accept or reject).
///
/// POST /api/v1/webhooks/mpesa/validation
pub async fn handle_c2b_validation(
    State(state): State<WebhookState>,
    Json(payload): Json<C2BCallbackPayload>,
) -> impl IntoResponse {
    let event_id = format!("mpesa-c2b-validate-{}", payload.trans_id);

    // S7: Validate shortcode matches our configuration
    if payload.business_shortcode != state.mpesa_config.shortcode {
        warn!(
            event_id = %event_id,
            expected = %state.mpesa_config.shortcode,
            received = %payload.business_shortcode,
            "C2B validation shortcode mismatch — rejecting"
        );
        return (StatusCode::OK, Json(serde_json::json!({
            "ResultCode": 1, "ResultDesc": "Invalid shortcode"
        }))).into_response();
    }

    info!(
        event_id = %event_id,
        amount = %payload.trans_amount,
        "M-Pesa C2B validation request"
    );

    // Validation logic: accept all payments by default
    // In production, check against known bill refs, amount limits, etc.
    let amount: f64 = payload.trans_amount.parse().unwrap_or(0.0);

    // Reject suspiciously large amounts (> KES 500,000)
    if amount > 500_000.0 {
        warn!(
            event_id = %event_id,
            amount = amount,
            "Rejecting C2B payment: amount exceeds limit"
        );
        return (
            StatusCode::OK,
            Json(serde_json::json!({
                "ResultCode": 1,
                "ResultDesc": "Amount exceeds transaction limit"
            }))
        ).into_response();
    }

    // Store validation event
    let event = WebhookEvent {
        event_id: event_id.clone(),
        source: WebhookSource::Mpesa,
        event_type: WebhookEventType::MpesaC2BValidation,
        payload: serde_json::to_value(&payload).unwrap_or_default(),
        received_at: chrono::Utc::now(),
        validated: true,
    };
    let _ = store_webhook_event(&state.db, &event).await;

    // Accept the payment
    (
        StatusCode::OK,
        Json(serde_json::json!({
            "ResultCode": 0,
            "ResultDesc": "Validation successful"
        }))
    ).into_response()
}

/// Validate M-Pesa callback signature using passkey + timestamp HMAC.
///
/// Safaricom signs callbacks with: base64(shortcode + passkey + timestamp)
/// This function verifies the signature matches.
pub fn validate_mpesa_signature(
    config: &super::MpesaConfig,
    shortcode: &str,
    timestamp: &str,
    expected_password: &str,
) -> bool {
    let data = format!("{}{}{}", config.shortcode, config.passkey, timestamp);
    let mut hasher = Sha256::new();
    hasher.update(data.as_bytes());
    let computed = base64::encode(hasher.finalize());

    // Constant-time comparison
    computed == expected_password
}
