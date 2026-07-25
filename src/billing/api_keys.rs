//! API key management for Angavu Intelligence billing.
//!
//! Handles key generation, validation, scope-based access control,
//! and per-key rate limiting backed by Redis.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{FromRow, PgPool};
use uuid::Uuid;

use thiserror::Error;

use super::subscription::SubscriptionTier;

// ── Errors ─────────────────────────────────────────────────────────────

#[derive(Debug, Error)]
pub enum ApiKeyError {
    #[error("API key not found")]
    NotFound,
    #[error("API key is revoked")]
    Revoked,
    #[error("API key is expired")]
    Expired,
    #[error("rate limit exceeded — retry after {retry_after_secs}s")]
    RateLimited { retry_after_secs: u64 },
    #[error("endpoint '{endpoint}' not allowed for tier {tier}")]
    EndpointNotAllowed { endpoint: String, tier: String },
    #[error("scope '{scope}' not permitted for this key")]
    ScopeDenied { scope: String },
    #[error("maximum API keys ({max}) reached for tier {tier}")]
    MaxKeysReached { max: u32, tier: String },
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),
    #[error("redis error: {0}")]
    Redis(#[from] redis::RedisError),
}

// ── API Key Scopes ─────────────────────────────────────────────────────

/// Fine-grained scopes that control what an API key can do.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ApiKeyScope {
    /// Read-only intelligence queries
    IntelligenceRead,
    /// Generate reports
    ReportsWrite,
    /// Export raw data
    DataExport,
    /// Access credit scoring
    CreditScoring,
    /// Manage subscription & billing
    BillingManage,
    /// WebSocket streaming access
    Streaming,
    /// Administrative operations
    Admin,
}

impl ApiKeyScope {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::IntelligenceRead => "intelligence:read",
            Self::ReportsWrite => "reports:write",
            Self::DataExport => "data:export",
            Self::CreditScoring => "credit:scoring",
            Self::BillingManage => "billing:manage",
            Self::Streaming => "streaming",
            Self::Admin => "admin",
        }
    }

    /// Default scopes for a given tier.
    pub fn defaults_for_tier(tier: &SubscriptionTier) -> Vec<ApiKeyScope> {
        match tier {
            SubscriptionTier::Free => vec![Self::IntelligenceRead],
            SubscriptionTier::Starter => vec![
                Self::IntelligenceRead,
                Self::ReportsWrite,
            ],
            SubscriptionTier::Pro => vec![
                Self::IntelligenceRead,
                Self::ReportsWrite,
                Self::DataExport,
                Self::CreditScoring,
                Self::Streaming,
            ],
            SubscriptionTier::Enterprise => vec![
                Self::IntelligenceRead,
                Self::ReportsWrite,
                Self::DataExport,
                Self::CreditScoring,
                Self::BillingManage,
                Self::Streaming,
                Self::Admin,
            ],
        }
    }
}

impl std::fmt::Display for ApiKeyScope {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ── API Key Model ──────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, FromRow)]
pub struct ApiKey {
    pub id: Uuid,
    pub org_id: Uuid,
    pub subscription_id: Uuid,
    /// The key prefix shown to users (first 8 chars): `agvk_a1b2`
    pub key_prefix: String,
    /// Argon2id hash of the full key. Full key is NEVER stored in plaintext.
    pub key_hash: String,
    pub name: String,
    pub scopes: Vec<String>,
    pub is_active: bool,
    pub last_used_at: Option<DateTime<Utc>>,
    pub expires_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl ApiKey {
    /// Check whether the key has a given scope.
    pub fn has_scope(&self, scope: &ApiKeyScope) -> bool {
        self.scopes.iter().any(|s| s == scope.as_str())
    }

    /// Check whether the key is usable (active + not expired).
    pub fn is_usable(&self) -> bool {
        if !self.is_active {
            return false;
        }
        if let Some(exp) = self.expires_at {
            if Utc::now() > exp {
                return false;
            }
        }
        true
    }
}

// ── API Key Manager ────────────────────────────────────────────────────

pub struct ApiKeyManager {
    pool: PgPool,
    redis: redis::aio::ConnectionManager,
}

impl ApiKeyManager {
    pub fn new(pool: PgPool, redis: redis::aio::ConnectionManager) -> Self {
        Self { pool, redis }
    }

    /// Generate a new API key. Returns the full plaintext key (shown once)
    /// and the persisted `ApiKey` record.
    ///
    /// Key format: `agvk_` + 48 hex chars (24 random bytes).
    pub async fn create(
        &self,
        org_id: Uuid,
        subscription_id: Uuid,
        tier: &SubscriptionTier,
        name: &str,
        scopes: Vec<ApiKeyScope>,
    ) -> Result<(String, ApiKey), ApiKeyError> {
        // Enforce max keys per tier
        let existing_count: (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM api_keys WHERE org_id = $1 AND is_active = true",
        )
        .bind(org_id)
        .fetch_one(&self.pool)
        .await?;

        let max = tier.max_api_keys() as i64;
        if existing_count.0 >= max {
            return Err(ApiKeyError::MaxKeysReached {
                max: tier.max_api_keys(),
                tier: tier.to_string(),
            });
        }

        // Validate scopes against tier
        let allowed = ApiKeyScope::defaults_for_tier(tier);
        for scope in &scopes {
            if !allowed.contains(scope) {
                return Err(ApiKeyError::ScopeDenied {
                    scope: scope.to_string(),
                });
            }
        }

        // Generate key
        let random_bytes: Vec<u8> = (0..24).map(|_| rand::random::<u8>()).collect();
        let hex_body = hex::encode(&random_bytes);
        let full_key = format!("agvk_{}", hex_body);
        let key_prefix = format!("agvk_{}", &hex_body[..8]);

        // Hash with Argon2id
        let key_hash = argon2::Argon2::default()
            .password_hash(
                full_key.as_bytes(),
                &argon2::password_salt::SaltString::generate(&mut rand::thread_rng()),
            )
            .map_err(|e| ApiKeyError::Database(sqlx::Error::Protocol(e.to_string())))?
            .to_string();

        let now = Utc::now();
        let expires_at = match tier {
            SubscriptionTier::Enterprise => None, // no expiry
            _ => Some(now + chrono::Duration::days(365)),
        };

        let scope_strings: Vec<String> = scopes.iter().map(|s| s.to_string()).collect();

        let key = sqlx::query_as::<_, ApiKey>(
            r#"
            INSERT INTO api_keys (id, org_id, subscription_id, key_prefix, key_hash,
                                  name, scopes, is_active, last_used_at, expires_at,
                                  created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, true, NULL, $8, $9, $9)
            RETURNING *
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(org_id)
        .bind(subscription_id)
        .bind(&key_prefix)
        .bind(&key_hash)
        .bind(name)
        .bind(&scope_strings)
        .bind(expires_at)
        .bind(now)
        .fetch_one(&self.pool)
        .await?;

        tracing::info!(
            org_id = %org_id,
            key_id = %key.id,
            key_prefix = %key_prefix,
            name = %name,
            "API key created"
        );

        Ok((full_key, key))
    }

    /// Validate an API key against the full plaintext value.
    /// Returns the `ApiKey` record if valid.
    pub async fn validate(&self, full_key: &str) -> Result<ApiKey, ApiKeyError> {
        // Extract prefix to narrow lookup
        if full_key.len() < 13 {
            return Err(ApiKeyError::NotFound);
        }
        let prefix = &full_key[..13]; // "agvk_" + 8 chars

        let candidates = sqlx::query_as::<_, ApiKey>(
            "SELECT * FROM api_keys WHERE key_prefix = $1 AND is_active = true",
        )
        .bind(prefix)
        .fetch_all(&self.pool)
        .await?;

        for key in candidates {
            // Verify hash
            let parsed_hash = argon2::PasswordHash::new(&key.key_hash)
                .map_err(|e| ApiKeyError::Database(sqlx::Error::Protocol(e.to_string())))?;
            if argon2::Argon2::default()
                .verify_password(full_key.as_bytes(), &parsed_hash)
                .is_ok()
            {
                if !key.is_usable() {
                    if key.is_active {
                        return Err(ApiKeyError::Expired);
                    }
                    return Err(ApiKeyError::Revoked);
                }
                return Ok(key);
            }
        }

        Err(ApiKeyError::NotFound)
    }

    /// Check rate limit for a key using Redis sliding window.
    /// Returns `Ok(())` if allowed, `Err(RateLimited)` if exceeded.
    pub async fn check_rate_limit(
        &self,
        key_id: Uuid,
        tier: &SubscriptionTier,
    ) -> Result<(), ApiKeyError> {
        let limit = tier.rate_limit_per_minute() as i64;
        let window_secs = 60;
        let redis_key = format!("ratelimit:apikey:{}", key_id);
        let now = Utc::now().timestamp_millis();
        let window_start = now - (window_secs * 1000);

        let mut conn = self.redis.clone();

        // Redis sorted set sliding window
        let count: i64 = redis::cmd("ZREMRANGEBYSCORE")
            .arg(&redis_key)
            .arg(0)
            .arg(window_start)
            .query_async(&mut conn)
            .await
            .unwrap_or(0);

        let count: i64 = redis::cmd("ZCARD")
            .arg(&redis_key)
            .query_async(&mut conn)
            .await
            .unwrap_or(0);

        if count >= limit {
            let retry_after = 60u64; // simplify: wait until window resets
            return Err(ApiKeyError::RateLimited { retry_after_secs: retry_after });
        }

        // Add current request
        let _: () = redis::cmd("ZADD")
            .arg(&redis_key)
            .arg(now)
            .arg(now)
            .query_async(&mut conn)
            .await
            .unwrap_or(());

        // Set expiry on the key
        let _: () = redis::cmd("EXPIRE")
            .arg(&redis_key)
            .arg(window_secs)
            .query_async(&mut conn)
            .await
            .unwrap_or(());

        Ok(())
    }

    /// Verify that a key has access to a specific endpoint.
    pub fn check_endpoint_access(
        key: &ApiKey,
        endpoint: &str,
        tier: &SubscriptionTier,
    ) -> Result<(), ApiKeyError> {
        let allowed = tier.allowed_endpoints();
        if allowed.iter().any(|e| endpoint.starts_with(e)) {
            Ok(())
        } else {
            Err(ApiKeyError::EndpointNotAllowed {
                endpoint: endpoint.to_string(),
                tier: tier.to_string(),
            })
        }
    }

    /// Update last_used_at timestamp.
    pub async fn touch(&self, key_id: Uuid) -> Result<(), ApiKeyError> {
        sqlx::query("UPDATE api_keys SET last_used_at = $1 WHERE id = $1")
            .bind(Utc::now())
            .bind(key_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    /// Revoke (deactivate) an API key.
    pub async fn revoke(&self, key_id: Uuid) -> Result<(), ApiKeyError> {
        let now = Utc::now();
        sqlx::query(
            "UPDATE api_keys SET is_active = false, updated_at = $1 WHERE id = $2",
        )
        .bind(now)
        .bind(key_id)
        .execute(&self.pool)
        .await?;

        tracing::info!(key_id = %key_id, "API key revoked");
        Ok(())
    }

    /// List all active keys for an org.
    pub async fn list_for_org(&self, org_id: Uuid) -> Result<Vec<ApiKey>, ApiKeyError> {
        let keys = sqlx::query_as::<_, ApiKey>(
            "SELECT * FROM api_keys WHERE org_id = $1 AND is_active = true ORDER BY created_at DESC",
        )
        .bind(org_id)
        .fetch_all(&self.pool)
        .await?;
        Ok(keys)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scope_display() {
        assert_eq!(ApiKeyScope::IntelligenceRead.as_str(), "intelligence:read");
        assert_eq!(ApiKeyScope::CreditScoring.as_str(), "credit:scoring");
    }

    #[test]
    fn free_tier_scopes() {
        let scopes = ApiKeyScope::defaults_for_tier(&SubscriptionTier::Free);
        assert_eq!(scopes.len(), 1);
        assert!(scopes.contains(&ApiKeyScope::IntelligenceRead));
    }

    #[test]
    fn enterprise_tier_scopes() {
        let scopes = ApiKeyScope::defaults_for_tier(&SubscriptionTier::Enterprise);
        assert!(scopes.contains(&ApiKeyScope::Admin));
        assert!(scopes.contains(&ApiKeyScope::BillingManage));
    }

    #[test]
    fn key_usability() {
        let key = ApiKey {
            id: Uuid::new_v4(),
            org_id: Uuid::new_v4(),
            subscription_id: Uuid::new_v4(),
            key_prefix: "agvk_test12".to_string(),
            key_hash: "hash".to_string(),
            name: "test".to_string(),
            scopes: vec!["intelligence:read".to_string()],
            is_active: true,
            last_used_at: None,
            expires_at: None,
            created_at: Utc::now(),
            updated_at: Utc::now(),
        };
        assert!(key.is_usable());
        assert!(key.has_scope(&ApiKeyScope::IntelligenceRead));
        assert!(!key.has_scope(&ApiKeyScope::Admin));
    }
}
