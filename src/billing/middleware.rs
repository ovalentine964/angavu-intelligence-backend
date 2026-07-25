//! Billing middleware: API key extraction and usage enforcement.
//!
//! Provides an Axum extractor that validates API keys from the
//! `Authorization: Bearer agvk_...` header, checks rate limits,
//! and enforces per-tier access control.

use axum::{
    extract::FromRequestParts,
    http::{request::Parts, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use std::sync::Arc;
use uuid::Uuid;

use crate::billing::api_keys::{ApiKey, ApiKeyManager};
use crate::billing::subscription::{Subscription, SubscriptionManager, SubscriptionTier};
use crate::db::AppState;

/// Extracted from a request after API key validation.
/// Contains the authenticated key, the org's subscription, and the tier.
pub struct AuthenticatedBilling {
    pub api_key: ApiKey,
    pub subscription: Subscription,
    pub tier: SubscriptionTier,
}

/// Rejection type for billing auth failures.
pub struct BillingRejection {
    pub status: StatusCode,
    pub message: String,
}

impl IntoResponse for BillingRejection {
    fn into_response(self) -> Response {
        let body = Json(serde_json::json!({
            "error": self.message,
            "code": "billing_auth_failed",
        }));
        (self.status, body).into_response()
    }
}

impl<S> FromRequestParts<S> for AuthenticatedBilling
where
    S: Send + Sync,
    Arc<AppState>: axum::extract::FromRef<S>,
{
    type Rejection = BillingRejection;

    async fn from_request_parts(parts: &mut Parts, state: &S) -> Result<Self, Self::Rejection> {
        let app_state = Arc::<AppState>::from_ref(state);

        // Extract Bearer token
        let auth_header = parts
            .headers
            .get("authorization")
            .and_then(|v| v.to_str().ok())
            .ok_or(BillingRejection {
                status: StatusCode::UNAUTHORIZED,
                message: "missing Authorization header".to_string(),
            })?;

        let token = auth_header
            .strip_prefix("Bearer ")
            .ok_or(BillingRejection {
                status: StatusCode::UNAUTHORIZED,
                message: "Authorization header must be 'Bearer <api_key>'".to_string(),
            })?;

        // Validate key
        let key_manager =
            ApiKeyManager::new(app_state.db.postgres.clone(), app_state.db.redis.clone());

        let api_key = key_manager.validate(token).await.map_err(|e| {
            let status = match e {
                crate::billing::api_keys::ApiKeyError::NotFound => StatusCode::UNAUTHORIZED,
                crate::billing::api_keys::ApiKeyError::Revoked => StatusCode::FORBIDDEN,
                crate::billing::api_keys::ApiKeyError::Expired => StatusCode::UNAUTHORIZED,
                _ => StatusCode::INTERNAL_SERVER_ERROR,
            };
            BillingRejection {
                status,
                message: e.to_string(),
            }
        })?;

        // Get subscription
        let sub_manager = SubscriptionManager::new(app_state.db.postgres.clone());
        let subscription = sub_manager
            .get_for_org(api_key.org_id)
            .await
            .map_err(|e| BillingRejection {
                status: StatusCode::INTERNAL_SERVER_ERROR,
                message: e.to_string(),
            })?
            .ok_or(BillingRejection {
                status: StatusCode::FORBIDDEN,
                message: "no active subscription for this organization".to_string(),
            })?;

        if !subscription.is_usable() {
            return Err(BillingRejection {
                status: StatusCode::PAYMENT_REQUIRED,
                message: "subscription is not active — please renew or upgrade".to_string(),
            });
        }

        let tier = subscription.tier_enum();

        // Rate limit check
        key_manager
            .check_rate_limit(api_key.id, &tier)
            .await
            .map_err(|e| {
                let retry_after = match &e {
                    crate::billing::api_keys::ApiKeyError::RateLimited { retry_after_secs } => {
                        *retry_after_secs
                    }
                    _ => 60,
                };
                BillingRejection {
                    status: StatusCode::TOO_MANY_REQUESTS,
                    message: format!("{} (retry after {}s)", e, retry_after),
                }
            })?;

        // Touch last_used_at (fire and forget)
        let _ = key_manager.touch(api_key.id).await;

        Ok(AuthenticatedBilling {
            api_key,
            subscription,
            tier,
        })
    }
}
