// M-Pesa STK Push Integration — Safaricom Daraja API
//
// Integrates with Safaricom's M-Pesa Daraja API for mobile money payments.
//
// Flow:
// 1. Client calls POST /api/v1/billing/payments/initiate with phone + amount
// 2. Backend generates password (shortcode + passkey + timestamp), calls Daraja STK Push API
// 3. Safaricom sends STK Push prompt to user's phone
// 4. User enters M-Pesa PIN to authorize
// 5. Safaricom sends callback to POST /api/v1/webhooks/mpesa
// 6. Backend confirms payment, activates/renews subscription
//
// API Endpoints:
// - Sandbox:    https://sandbox.safaricom.co.ke
// - Production: https://api.safaricom.co.ke
//
// Authentication:
// - OAuth 2.0: POST /oauth/v1/generate?grant_type=client_credentials
// - Headers: Authorization: Basic base64(consumer_key:consumer_secret)
//
// STK Push:
// - POST /mpesa/stkpush/v1/processrequest
// - Password: base64(shortcode + passkey + timestamp)

use chrono::Utc;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::webhook::{MpesaConfig, MpesaEnvironment};

// ═══════════════════════════════════════════════════════════
//  TYPES
// ═══════════════════════════════════════════════════════════

/// Client request to initiate an STK Push payment.
#[derive(Debug, Deserialize)]
pub struct StkPushRequest {
    /// Phone number in format 254XXXXXXXXX.
    pub phone_number: String,
    /// Amount in KES.
    pub amount: u32,
    /// Account reference (e.g., org_id or invoice_id).
    pub account_reference: String,
    /// Transaction description.
    pub description: String,
}

/// Response from the STK Push initiation.
#[derive(Debug, Serialize)]
pub struct StkPushResponse {
    pub checkout_request_id: String,
    pub merchant_request_id: String,
    pub response_code: String,
    pub response_description: String,
    pub customer_message: String,
    /// Our internal transaction ID for tracking.
    pub transaction_id: String,
}

/// Response from Safaricom STK Push API.
#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct DarajaStkResponse {
    #[serde(rename = "MerchantRequestID")]
    merchant_request_id: Option<String>,
    #[serde(rename = "CheckoutRequestID")]
    checkout_request_id: Option<String>,
    #[serde(rename = "ResponseCode")]
    response_code: Option<String>,
    #[serde(rename = "ResponseDescription")]
    response_description: Option<String>,
    #[serde(rename = "CustomerMessage")]
    customer_message: Option<String>,
    #[serde(rename = "errorCode")]
    error_code: Option<String>,
    #[serde(rename = "errorMessage")]
    error_message: Option<String>,
}

/// OAuth token response from Daraja.
#[derive(Debug, Deserialize)]
struct OAuthResponse {
    access_token: Option<String>,
    expires_in: Option<String>,
    #[serde(rename = "errorCode")]
    error_code: Option<String>,
    #[serde(rename = "errorMessage")]
    error_message: Option<String>,
}

/// Payment status for client polling.
#[derive(Debug, Serialize)]
pub struct PaymentStatus {
    pub transaction_id: String,
    pub org_id: String,
    pub status: PaymentState,
    pub amount: u32,
    pub phone_number: String,
    pub mpesa_receipt: Option<String>,
    pub checkout_request_id: Option<String>,
    pub error_message: Option<String>,
    pub created_at: chrono::DateTime<chrono::Utc>,
    pub updated_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, Serialize, Deserialize, PartialEq)]
pub enum PaymentState {
    Pending,
    Success,
    Failed,
    Cancelled,
}

impl PaymentState {
    pub fn as_str(&self) -> &str {
        match self {
            Self::Pending => "pending",
            Self::Success => "success",
            Self::Failed => "failed",
            Self::Cancelled => "cancelled",
        }
    }

    pub fn from_str(s: &str) -> Self {
        match s {
            "pending" => Self::Pending,
            "success" => Self::Success,
            "failed" => Self::Failed,
            "cancelled" => Self::Cancelled,
            _ => Self::Pending,
        }
    }
}

// ═══════════════════════════════════════════════════════════
//  STK PUSH INITIATION
// ═══════════════════════════════════════════════════════════

/// Initiate an M-Pesa STK Push payment.
///
/// 1. Get OAuth token from Daraja
/// 2. Generate STK Push password
/// 3. Call STK Push API
/// 4. Store payment record in PostgreSQL
/// 5. Return checkout details for client polling
pub async fn initiate_stk_push(
    db: &sqlx::PgPool,
    redis: &redis::aio::ConnectionManager,
    config: &MpesaConfig,
    org_id: &str,
    req: StkPushRequest,
) -> Result<StkPushResponse, anyhow::Error> {
    // Validate phone number
    let phone = normalize_phone(&req.phone_number)?;
    if req.amount == 0 {
        anyhow::bail!("Amount must be greater than 0");
    }

    // Generate internal transaction ID
    let txn_id = uuid::Uuid::new_v4().to_string();

    // Get OAuth token
    let access_token = get_oauth_token(config, redis).await?;

    // Generate STK Push password
    let timestamp = Utc::now().format("%Y%m%d%H%M%S").to_string();
    let password = generate_stk_password(config, &timestamp);

    // Build callback URL
    let base_url = std::env::var("ANGAVU_PUBLIC_URL")
        .unwrap_or_else(|_| "https://api.angavu.co.ke".to_string());
    let callback_url = format!("{}/api/v1/webhooks/mpesa", base_url);

    // Build STK Push request
    let stk_body = serde_json::json!({
        "BusinessShortCode": config.shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": req.amount,
        "PartyA": phone,
        "PartyB": config.shortcode,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": req.account_reference,
        "TransactionDesc": req.description,
    });

    // Call Daraja STK Push API
    let client = reqwest::Client::new();
    let url = format!("{}/mpesa/stkpush/v1/processrequest", config.base_url());

    let response = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .header("Content-Type", "application/json")
        .json(&stk_body)
        .send()
        .await?;

    let status = response.status();
    let body: DarajaStkResponse = response.json().await?;

    if !status.is_success() || body.error_code.is_some() {
        let error_msg = body
            .error_message
            .or_else(|| body.response_description.clone())
            .unwrap_or_else(|| format!("Daraja API error: HTTP {}", status));

        // Store failed payment
        store_payment(
            db,
            &txn_id,
            org_id,
            &phone,
            req.amount,
            PaymentState::Failed,
            &error_msg,
            None,
            None,
        )
        .await?;

        anyhow::bail!("STK Push failed: {}", error_msg);
    }

    let checkout_id = body.checkout_request_id.clone().unwrap_or_default();
    let merchant_id = body.merchant_request_id.clone().unwrap_or_default();

    // Store pending payment
    store_payment(
        db,
        &txn_id,
        org_id,
        &phone,
        req.amount,
        PaymentState::Pending,
        "",
        Some(&checkout_id),
        Some(&merchant_id),
    )
    .await?;

    // Cache in Redis for fast callback lookup
    let cache_key = format!("payment:checkout:{}", checkout_id);
    let _ = redis::cmd("SET")
        .arg(&cache_key)
        .arg(&txn_id)
        .arg("EX")
        .arg(3600i64) // 1 hour
        .query_async::<_, ()>(&mut redis.clone())
        .await;

    tracing::info!(
        txn_id = %txn_id,
        org_id = %org_id,
        phone = %phone,
        amount = req.amount,
        checkout_id = %checkout_id,
        "STK Push initiated"
    );

    Ok(StkPushResponse {
        checkout_request_id: checkout_id,
        merchant_request_id: merchant_id,
        response_code: body.response_code.unwrap_or_default(),
        response_description: body.response_description.unwrap_or_default(),
        customer_message: body.customer_message.unwrap_or_default(),
        transaction_id: txn_id,
    })
}

// ═══════════════════════════════════════════════════════════
//  PAYMENT STATUS
// ═══════════════════════════════════════════════════════════

/// Get the status of a payment transaction.
pub async fn get_payment_status(
    db: &sqlx::PgPool,
    org_id: &str,
    txn_id: &str,
) -> Result<Option<PaymentStatus>, anyhow::Error> {
    let row = sqlx::query_as::<_, PaymentRow>(
        r#"
        SELECT id, org_id, phone_number, amount, status, mpesa_receipt,
               checkout_request_id, merchant_request_id, error_message,
               created_at, updated_at
        FROM payments
        WHERE id = $1 AND org_id = $2
        "#,
    )
    .bind(txn_id)
    .bind(org_id)
    .fetch_optional(db)
    .await?;

    Ok(row.map(|r| PaymentStatus {
        transaction_id: r.id,
        org_id: r.org_id,
        status: PaymentState::from_str(&r.status),
        amount: r.amount as u32,
        phone_number: r.phone_number,
        mpesa_receipt: r.mpesa_receipt,
        checkout_request_id: r.checkout_request_id,
        error_message: r.error_message,
        created_at: r.created_at,
        updated_at: r.updated_at,
    }))
}

// ═══════════════════════════════════════════════════════════
//  CALLBACK PROCESSING (called from webhook handler)
// ═══════════════════════════════════════════════════════════

/// Process an M-Pesa STK Push callback.
/// Called from the webhook handler when Safaricom sends the callback.
pub async fn process_stk_callback(
    db: &sqlx::PgPool,
    redis: &redis::aio::ConnectionManager,
    checkout_request_id: &str,
    result_code: i32,
    result_desc: &str,
    amount: Option<f64>,
    receipt: Option<&str>,
    phone: Option<&str>,
) -> Result<(), anyhow::Error> {
    // Look up the transaction by checkout_request_id
    let txn_id: Option<String> = redis::cmd("GET")
        .arg(format!("payment:checkout:{}", checkout_request_id))
        .query_async::<_, Option<String>>(&mut redis.clone())
        .await
        .ok()
        .flatten();

    let txn_id = match txn_id {
        Some(id) => id,
        None => {
            // Fallback: query PostgreSQL
            sqlx::query_scalar::<_, String>(
                "SELECT id FROM payments WHERE checkout_request_id = $1 LIMIT 1",
            )
            .bind(checkout_request_id)
            .fetch_optional(db)
            .await?
            .ok_or_else(|| {
                anyhow::anyhow!("Payment not found for checkout: {}", checkout_request_id)
            })?
        }
    };

    if result_code == 0 {
        // Payment successful — wrap in transaction for atomicity
        let receipt_str = receipt.unwrap_or("");
        let amount_val = amount.unwrap_or(0.0);

        let mut tx = db.begin().await?;

        // Update payment status
        sqlx::query(
            r#"
            UPDATE payments
            SET status = 'success', mpesa_receipt = $1, updated_at = NOW()
            WHERE id = $2
            "#,
        )
        .bind(receipt_str)
        .bind(&txn_id)
        .execute(&mut *tx)
        .await?;

        // Get the org_id from the payment record
        let org_id: String = sqlx::query_scalar("SELECT org_id FROM payments WHERE id = $1")
            .bind(&txn_id)
            .fetch_one(&mut *tx)
            .await?;

        // Confirm the subscription payment (updates subscription status)
        super::subscription::confirm_payment_tx(&mut tx, &org_id, receipt_str, amount_val).await?;

        tx.commit().await?;

        // Invalidate Redis cache (best-effort, non-transactional)
        let cache_key = format!("subscription:{}", org_id);
        let _ = redis::cmd("DEL")
            .arg(&cache_key)
            .query_async::<_, ()>(&mut redis.clone())
            .await;

        tracing::info!(
            txn_id = %txn_id,
            receipt = %receipt_str,
            amount = amount_val,
            "Payment confirmed via callback"
        );
    } else {
        // Payment failed or cancelled
        let state = if result_code == 1032 {
            PaymentState::Cancelled // user cancelled
        } else {
            PaymentState::Failed
        };

        sqlx::query(
            r#"
            UPDATE payments
            SET status = $1, error_message = $2, updated_at = NOW()
            WHERE id = $3
            "#,
        )
        .bind(state.as_str())
        .bind(result_desc)
        .bind(&txn_id)
        .execute(db)
        .await?;

        tracing::warn!(
            txn_id = %txn_id,
            result_code = result_code,
            desc = %result_desc,
            "Payment failed via callback"
        );
    }

    Ok(())
}

// ═══════════════════════════════════════════════════════════
//  OAUTH TOKEN
// ═══════════════════════════════════════════════════════════

/// Get or refresh the M-Pesa OAuth access token.
/// Cached in Redis with a 50-minute TTL (tokens expire in 1 hour).
async fn get_oauth_token(
    config: &MpesaConfig,
    redis: &redis::aio::ConnectionManager,
) -> Result<String, anyhow::Error> {
    let cache_key = "mpesa:oauth_token";

    // Check Redis cache
    if let Ok(Some(token)) = redis::cmd("GET")
        .arg(cache_key)
        .query_async::<_, Option<String>>(&mut redis.clone())
        .await
    {
        return Ok(token);
    }

    // Fetch new token from Daraja
    let consumer_key = std::env::var("MPESA_CONSUMER_KEY")
        .map_err(|_| anyhow::anyhow!("MPESA_CONSUMER_KEY not set"))?;
    let consumer_secret = std::env::var("MPESA_CONSUMER_SECRET")
        .map_err(|_| anyhow::anyhow!("MPESA_CONSUMER_SECRET not set"))?;

    let credentials = base64::Engine::encode(
        &base64::engine::general_purpose::STANDARD,
        format!("{}:{}", consumer_key, consumer_secret),
    );

    let client = reqwest::Client::new();
    let url = format!(
        "{}/oauth/v1/generate?grant_type=client_credentials",
        config.base_url()
    );

    let response = client
        .get(&url)
        .header("Authorization", format!("Basic {}", credentials))
        .send()
        .await?;

    let body: OAuthResponse = response.json().await?;

    let token = body.access_token.ok_or_else(|| {
        let err = body
            .error_message
            .unwrap_or_else(|| "Unknown OAuth error".to_string());
        anyhow::anyhow!("OAuth failed: {}", err)
    })?;

    // Cache for 50 minutes (token expires in 60 minutes)
    let _ = redis::cmd("SET")
        .arg(cache_key)
        .arg(&token)
        .arg("EX")
        .arg(3000i64) // 50 minutes
        .query_async::<_, ()>(&mut redis.clone())
        .await;

    Ok(token)
}

// ═══════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════

/// Generate the STK Push password.
/// Format: base64(BusinessShortCode + Passkey + Timestamp)
fn generate_stk_password(config: &MpesaConfig, timestamp: &str) -> String {
    let data = format!("{}{}{}", config.shortcode, config.passkey, timestamp);
    base64::Engine::encode(&base64::engine::general_purpose::STANDARD, data.as_bytes())
}

/// Normalize phone number to 254XXXXXXXXX format.
fn normalize_phone(phone: &str) -> Result<String, anyhow::Error> {
    let cleaned: String = phone.chars().filter(|c| c.is_ascii_digit()).collect();

    let normalized = if cleaned.starts_with("254") && cleaned.len() == 12 {
        cleaned
    } else if cleaned.starts_with("0") && cleaned.len() == 10 {
        format!("254{}", &cleaned[1..])
    } else if cleaned.starts_with("7") && cleaned.len() == 9 {
        format!("254{}", cleaned)
    } else if cleaned.starts_with("1") && cleaned.len() == 9 {
        format!("254{}", cleaned)
    } else if cleaned.len() == 10 && !cleaned.starts_with("0") {
        format!("254{}", cleaned)
    } else {
        anyhow::bail!(
            "Invalid phone number format: {}. Expected 254XXXXXXXXX",
            phone
        );
    };

    // Validate prefix (Safaricom: 254[710-729, 740-749, 757-759, 768-769, 790-799, 110-119])
    if !normalized.starts_with("2547") && !normalized.starts_with("2541") {
        anyhow::bail!("Phone number must be a Safaricom number (2547xx or 2541xx)");
    }

    Ok(normalized)
}

/// Store a payment record in PostgreSQL.
async fn store_payment(
    db: &sqlx::PgPool,
    txn_id: &str,
    org_id: &str,
    phone: &str,
    amount: u32,
    status: PaymentState,
    error_message: &str,
    checkout_request_id: Option<&str>,
    merchant_request_id: Option<&str>,
) -> Result<(), anyhow::Error> {
    sqlx::query(
        r#"
        INSERT INTO payments (id, org_id, phone_number, amount, status, error_message,
                              checkout_request_id, merchant_request_id, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
        ON CONFLICT (id) DO UPDATE
        SET status = EXCLUDED.status, error_message = EXCLUDED.error_message, updated_at = NOW()
        "#,
    )
    .bind(txn_id)
    .bind(org_id)
    .bind(phone)
    .bind(amount as i32)
    .bind(status.as_str())
    .bind(error_message)
    .bind(checkout_request_id)
    .bind(merchant_request_id)
    .execute(db)
    .await?;

    Ok(())
}

// ═══════════════════════════════════════════════════════════
//  DB ROW MAPPING
// ═══════════════════════════════════════════════════════════

#[derive(Debug, sqlx::FromRow)]
struct PaymentRow {
    id: String,
    org_id: String,
    phone_number: String,
    amount: i32,
    status: String,
    mpesa_receipt: Option<String>,
    checkout_request_id: Option<String>,
    merchant_request_id: Option<String>,
    error_message: Option<String>,
    created_at: chrono::DateTime<chrono::Utc>,
    updated_at: chrono::DateTime<chrono::Utc>,
}

// ═══════════════════════════════════════════════════════════
//  MIGRATION SQL
// ═══════════════════════════════════════════════════════════

pub const PAYMENTS_MIGRATION: &str = r#"
CREATE TABLE IF NOT EXISTS payments (
    id VARCHAR(64) PRIMARY KEY,
    org_id VARCHAR(128) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    amount INT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    mpesa_receipt VARCHAR(64),
    checkout_request_id VARCHAR(128),
    merchant_request_id VARCHAR(128),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payments_org ON payments(org_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_checkout ON payments(checkout_request_id);
CREATE INDEX IF NOT EXISTS idx_payments_created ON payments(created_at DESC);
"#;

// ═══════════════════════════════════════════════════════════
//  TESTS
// ═══════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_phone() {
        // Standard 254 format
        assert_eq!(normalize_phone("254712345678").unwrap(), "254712345678");

        // 0-prefix
        assert_eq!(normalize_phone("0712345678").unwrap(), "254712345678");

        // Without prefix
        assert_eq!(normalize_phone("712345678").unwrap(), "254712345678");

        // Invalid
        assert!(normalize_phone("123").is_err());
        assert!(normalize_phone("+14155552671").is_err());
    }

    #[test]
    fn test_payment_state_roundtrip() {
        let states = vec![
            PaymentState::Pending,
            PaymentState::Success,
            PaymentState::Failed,
            PaymentState::Cancelled,
        ];
        for s in states {
            assert_eq!(PaymentState::from_str(s.as_str()), s);
        }
    }

    #[test]
    fn test_stk_password_generation() {
        let config = MpesaConfig {
            passkey: "test_passkey".to_string(),
            shortcode: "174379".to_string(),
            initiator_password: String::new(),
            environment: MpesaEnvironment::Sandbox,
        };
        let timestamp = "20260801205300";
        let password = generate_stk_password(&config, timestamp);
        // Should be base64 of "174379test_passkey20260801205300"
        assert!(!password.is_empty());
        // Verify it's valid base64
        assert!(
            base64::Engine::decode(&base64::engine::general_purpose::STANDARD, &password).is_ok()
        );
    }
}
