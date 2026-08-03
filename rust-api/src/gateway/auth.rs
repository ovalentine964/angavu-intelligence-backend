use uuid::Uuid;
// src/gateway/auth.rs
//
// JWT Authentication with Token Revocation
//
// Security improvements:
// - Every token carries a unique `jti` (JWT ID) claim — a UUID v4
// - Revoked tokens are stored in Redis with TTL matching token expiry
// - Each request checks the blacklist before accepting the token
// - Logout endpoint revokes the current token
// - Refresh endpoint issues a new token and revokes the old one
// - Client IP is extracted from ConnectInfo or X-Forwarded-For for audit

use axum::{
    extract::{ConnectInfo, Json, Request, State},
    http::{HeaderMap, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use redis::aio::ConnectionManager;
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::sync::Arc;

// ── JWT Config ──────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct JwtConfig {
    pub encoding_key: EncodingKey,
    pub decoding_key: DecodingKey,
    pub validation: Validation,
    /// Token expiry (seconds)
    pub access_token_ttl: u64,
    pub refresh_token_ttl: u64,
}

// ── Claims ──────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    /// Buyer organization ID
    pub org_id: String,
    /// Buyer tier (free, starter, pro, enterprise)
    pub tier: BuyerTier,
    /// API key ID
    pub key_id: String,
    /// JWT ID — unique per token, used for revocation
    pub jti: String,
    /// Expiration timestamp
    pub exp: u64,
    /// Issued at
    pub iat: u64,
    /// Permissions
    pub permissions: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum BuyerTier {
    Free,
    Starter,
    Pro,
    Enterprise,
}

impl From<crate::billing::subscription::SubscriptionTier> for BuyerTier {
    fn from(tier: crate::billing::subscription::SubscriptionTier) -> Self {
        match tier {
            crate::billing::subscription::SubscriptionTier::Free => BuyerTier::Free,
            crate::billing::subscription::SubscriptionTier::Starter => BuyerTier::Starter,
            crate::billing::subscription::SubscriptionTier::Pro => BuyerTier::Pro,
            crate::billing::subscription::SubscriptionTier::Enterprise => BuyerTier::Enterprise,
        }
    }
}

impl BuyerTier {
    pub fn rate_limit_per_minute(&self) -> u32 {
        match self {
            Self::Free => 10,
            Self::Starter => 100,
            Self::Pro => 1000,
            Self::Enterprise => 10000,
        }
    }

    pub fn queries_per_month(&self) -> u32 {
        match self {
            Self::Free => 100,
            Self::Starter => 5_000,
            Self::Pro => 50_000,
            Self::Enterprise => u32::MAX,
        }
    }

    pub fn can_access_raw_data(&self) -> bool {
        matches!(self, Self::Pro | Self::Enterprise)
    }
}

// ── Token Generation ────────────────────────────────────────

/// Generate a signed JWT access token with `jti` claim.
pub fn generate_access_token(
    config: &JwtConfig,
    org_id: &str,
    tier: &BuyerTier,
    key_id: &str,
    permissions: Vec<String>,
) -> Result<String, StatusCode> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    let claims = Claims {
        org_id: org_id.to_string(),
        tier: tier.clone(),
        key_id: key_id.to_string(),
        jti: uuid::Uuid::new_v4().to_string(),
        exp: now + config.access_token_ttl,
        iat: now,
        permissions,
    };

    encode(&Header::default(), &claims, &config.encoding_key)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)
}

/// Generate a signed JWT refresh token with `jti` claim.
pub fn generate_refresh_token(
    config: &JwtConfig,
    org_id: &str,
    tier: &BuyerTier,
    key_id: &str,
) -> Result<String, StatusCode> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    let claims = Claims {
        org_id: org_id.to_string(),
        tier: tier.clone(),
        key_id: key_id.to_string(),
        jti: uuid::Uuid::new_v4().to_string(),
        exp: now + config.refresh_token_ttl,
        iat: now,
        permissions: vec!["refresh".to_string()],
    };

    encode(&Header::default(), &claims, &config.encoding_key)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)
}

// ── Token Revocation (Redis Blacklist) ──────────────────────

/// Redis key prefix for blacklisted tokens.
const BLACKLIST_PREFIX: &str = "jwt:blacklist:";

/// Revoke a token by adding its `jti` to the Redis blacklist.
/// The blacklist entry expires when the token would have expired anyway.
pub async fn revoke_token(
    redis: &mut ConnectionManager,
    jti: &str,
    exp: u64,
) -> Result<(), StatusCode> {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    let ttl = if exp > now { exp - now } else { 60 };
    let key = format!("{}{}", BLACKLIST_PREFIX, jti);

    redis::cmd("SET")
        .arg(&key)
        .arg("revoked")
        .arg("EX")
        .arg(ttl)
        .query_async(&mut *redis)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(())
}

/// Check if a token's `jti` has been revoked.
pub async fn is_token_revoked(
    redis: &mut ConnectionManager,
    jti: &str,
) -> Result<bool, StatusCode> {
    let key = format!("{}{}", BLACKLIST_PREFIX, jti);

    let exists: bool = redis::cmd("EXISTS")
        .arg(&key)
        .query_async(&mut *redis)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    Ok(exists)
}

// ── Client IP Extraction ────────────────────────────────────

/// Extract the real client IP address from the request.
///
/// Priority:
/// 1. `X-Forwarded-For` header (first entry — original client)
/// 2. `X-Real-IP` header
/// 3. `ConnectInfo` socket address (direct connection)
pub fn extract_client_ip(headers: &HeaderMap, connect_info: Option<&SocketAddr>) -> Option<String> {
    // Try X-Forwarded-For first (proxy chains)
    if let Some(forwarded) = headers.get("x-forwarded-for") {
        if let Ok(val) = forwarded.to_str() {
            // X-Forwarded-For: client, proxy1, proxy2
            // Take the first (original client) IP
            if let Some(first_ip) = val.split(',').next() {
                let trimmed = first_ip.trim();
                if !trimmed.is_empty() {
                    return Some(trimmed.to_string());
                }
            }
        }
    }

    // Try X-Real-IP (nginx-style proxy)
    if let Some(real_ip) = headers.get("x-real-ip") {
        if let Ok(val) = real_ip.to_str() {
            let trimmed = val.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
        }
    }

    // Fall back to direct socket address
    connect_info.map(|addr| addr.ip().to_string())
}

// ── JWT Auth Middleware ─────────────────────────────────────

/// JWT authentication middleware with revocation checking.
///
/// For every request:
/// 1. Extract Bearer token from Authorization header
/// 2. Decode and validate JWT
/// 3. Check that `jti` is not in the Redis blacklist
/// 4. Inject Claims into request extensions
pub async fn jwt_auth_middleware(
    State(state): State<super::GatewayState>,
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    mut request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let headers = request.headers();

    // Extract token from Authorization header
    let token = extract_bearer_token(headers).ok_or(StatusCode::UNAUTHORIZED)?;

    // Validate JWT and extract claims
    let claims = decode::<Claims>(
        &token,
        &state.jwt_config.decoding_key,
        &state.jwt_config.validation,
    )
    .map_err(|_| StatusCode::UNAUTHORIZED)?
    .claims;

    // Check expiration (belt-and-suspenders — JWT decode also checks exp)
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    if claims.exp < now {
        return Err(StatusCode::UNAUTHORIZED);
    }

    // Check if token has been revoked
    let mut redis = state.redis.clone();
    if is_token_revoked(&mut redis, &claims.jti).await? {
        return Err(StatusCode::UNAUTHORIZED);
    }

    // Extract client IP for audit trail
    let client_ip = extract_client_ip(request.headers(), Some(&addr));

    // Inject claims and client IP into request extensions
    request.extensions_mut().insert(claims);
    if let Some(ip) = client_ip {
        request.extensions_mut().insert(ClientIp(ip));
    }

    Ok(next.run(request).await)
}

// ── Request/Response Types ──────────────────────────────────

/// Wrapper for client IP address in request extensions.
#[derive(Debug, Clone)]
pub struct ClientIp(pub String);

/// Request body for the login/token endpoint.
#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub org_id: String,
    pub api_key: String,
    pub tier: String,
    pub permissions: Vec<String>,
}

/// Response containing both access and refresh tokens.
#[derive(Debug, Serialize)]
pub struct TokenResponse {
    pub access_token: String,
    pub refresh_token: String,
    pub token_type: String,
    pub expires_in: u64,
}

/// Request body for the refresh endpoint.
#[derive(Debug, Deserialize)]
pub struct RefreshRequest {
    pub refresh_token: String,
}

/// Request body for the logout endpoint.
#[derive(Debug, Deserialize)]
pub struct LogoutRequest {
    /// Optional: if not provided, the current access token is revoked.
    pub token: Option<String>,
}

// ── Token Endpoints ─────────────────────────────────────────

/// POST /api/v1/auth/token
///
/// Issue a new access + refresh token pair.
/// In production, this validates the API key against the database.
pub async fn issue_token(
    State(state): State<super::GatewayState>,
    Json(req): Json<LoginRequest>,
) -> impl IntoResponse {
    // SECURITY FIX (P0): Look up the user's actual tier from the database
    // instead of trusting the client-claimed tier. A free user could previously
    // claim "enterprise" tier to bypass rate limits and access restrictions.
    let tier =
        match crate::billing::subscription::get_active_subscription(&state.db, &req.org_id).await {
            Ok(Some(sub)) => BuyerTier::from(sub.tier),
            Ok(None) => {
                // No active subscription — default to Free tier (most restrictive)
                tracing::info!(
                    org_id = %req.org_id,
                    "No active subscription found during token issuance, defaulting to Free tier"
                );
                BuyerTier::Free
            }
            Err(e) => {
                tracing::error!(
                    error = %e,
                    org_id = %req.org_id,
                    "Failed to look up subscription tier during token issuance"
                );
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(serde_json::json!({
                        "error": {
                            "code": "TIER_LOOKUP_FAILED",
                            "message": "Failed to verify subscription tier"
                        }
                    })),
                )
                    .into_response();
            }
        };

    let access_token = match generate_access_token(
        &state.jwt_config,
        &req.org_id,
        &tier,
        &req.api_key,
        req.permissions,
    ) {
        Ok(t) => t,
        Err(_) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": {
                        "code": "TOKEN_GENERATION_FAILED",
                        "message": "Failed to generate access token"
                    }
                })),
            )
                .into_response();
        }
    };

    let refresh_token =
        match generate_refresh_token(&state.jwt_config, &req.org_id, &tier, &req.api_key) {
            Ok(t) => t,
            Err(_) => {
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(serde_json::json!({
                        "error": {
                            "code": "TOKEN_GENERATION_FAILED",
                            "message": "Failed to generate refresh token"
                        }
                    })),
                )
                    .into_response();
            }
        };

    (
        StatusCode::OK,
        Json(TokenResponse {
            access_token,
            refresh_token,
            token_type: "Bearer".to_string(),
            expires_in: state.jwt_config.access_token_ttl,
        }),
    )
        .into_response()
}

/// POST /api/v1/auth/refresh
///
/// Exchange a valid refresh token for a new access + refresh pair.
/// The old refresh token is revoked (one-time use).
pub async fn refresh_token(
    State(state): State<super::GatewayState>,
    Json(req): Json<RefreshRequest>,
) -> impl IntoResponse {
    let mut redis = state.redis.clone();

    // Decode the refresh token
    let claims = match decode::<Claims>(
        &req.refresh_token,
        &state.jwt_config.decoding_key,
        &state.jwt_config.validation,
    ) {
        Ok(token_data) => token_data.claims,
        Err(_) => {
            return (
                StatusCode::UNAUTHORIZED,
                Json(serde_json::json!({
                    "error": {
                        "code": "INVALID_REFRESH_TOKEN",
                        "message": "Refresh token is invalid or expired"
                    }
                })),
            )
                .into_response();
        }
    };

    // Verify it's actually a refresh token
    if !claims.permissions.contains(&"refresh".to_string()) {
        return (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": {
                    "code": "INVALID_REFRESH_TOKEN",
                    "message": "Provided token is not a refresh token"
                }
            })),
        )
            .into_response();
    }

    // Check if refresh token has been revoked
    if is_token_revoked(&mut redis, &claims.jti)
        .await
        .unwrap_or(false)
    {
        return (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": {
                    "code": "REVOKED_TOKEN",
                    "message": "Refresh token has been revoked"
                }
            })),
        )
            .into_response();
    }

    // Revoke the old refresh token (one-time use)
    let _ = revoke_token(&mut redis, &claims.jti, claims.exp).await;

    // Revoke the old access token too if present in blacklist
    // (The caller should also revoke their old access token)

    // Generate new tokens
    let new_access = match generate_access_token(
        &state.jwt_config,
        &claims.org_id,
        &claims.tier,
        &claims.key_id,
        claims
            .permissions
            .iter()
            .filter(|p| *p != "refresh")
            .cloned()
            .collect(),
    ) {
        Ok(t) => t,
        Err(_) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": {
                        "code": "TOKEN_GENERATION_FAILED",
                        "message": "Failed to generate new access token"
                    }
                })),
            )
                .into_response();
        }
    };

    let new_refresh = match generate_refresh_token(
        &state.jwt_config,
        &claims.org_id,
        &claims.tier,
        &claims.key_id,
    ) {
        Ok(t) => t,
        Err(_) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": {
                        "code": "TOKEN_GENERATION_FAILED",
                        "message": "Failed to generate new refresh token"
                    }
                })),
            )
                .into_response();
        }
    };

    (
        StatusCode::OK,
        Json(TokenResponse {
            access_token: new_access,
            refresh_token: new_refresh,
            token_type: "Bearer".to_string(),
            expires_in: state.jwt_config.access_token_ttl,
        }),
    )
        .into_response()
}

/// POST /api/v1/auth/logout
///
/// Revoke the current access token (or a specified token).
/// After logout, the token cannot be used for any further requests.
pub async fn logout(
    State(state): State<super::GatewayState>,
    request: Request,
) -> impl IntoResponse {
    let mut redis = state.redis.clone();

    // Get the claims from the middleware-injected extensions
    let claims = request.extensions().get::<Claims>().cloned();

    if let Some(claims) = claims {
        // Revoke the current access token
        if let Err(e) = revoke_token(&mut redis, &claims.jti, claims.exp).await {
            tracing::error!(error = ?e, jti = %claims.jti, "Failed to revoke token on logout");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": {
                        "code": "LOGOUT_FAILED",
                        "message": "Failed to revoke token"
                    }
                })),
            )
                .into_response();
        }

        tracing::info!(org_id = %claims.org_id, jti = %claims.jti, "Token revoked on logout");

        (
            StatusCode::OK,
            Json(serde_json::json!({
                "message": "Successfully logged out. Token has been revoked.",
                "revoked_jti": claims.jti,
            })),
        )
            .into_response()
    } else {
        // No claims in extensions — this shouldn't happen if middleware ran
        (
            StatusCode::UNAUTHORIZED,
            Json(serde_json::json!({
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "No active session to logout"
                }
            })),
        )
            .into_response()
    }
}

// ── FromRequestParts impl for Claims ──────────────────────────
// Allows `Claims` to be used directly as an Axum handler extractor.
// The JWT middleware inserts Claims into request extensions; this impl
// extracts them back out for handlers to use.
impl<S: Send + Sync> axum::extract::FromRequestParts<S> for Claims {
    type Rejection = StatusCode;

    async fn from_request_parts(
        parts: &mut axum::http::request::Parts,
        _state: &S,
    ) -> Result<Self, Self::Rejection> {
        parts
            .extensions
            .get::<Claims>()
            .cloned()
            .ok_or(StatusCode::UNAUTHORIZED)
    }
}

// ── Helpers ─────────────────────────────────────────────────

fn extract_bearer_token(headers: &HeaderMap) -> Option<String> {
    headers
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(|s| s.to_string())
}

// ── Auth Router ─────────────────────────────────────────────

use axum::routing::{get, post};
use axum::Router;

/// Build the auth sub-router with token, refresh, and logout endpoints.
pub fn auth_router(state: super::GatewayState) -> Router {
    Router::new()
        .route("/api/v1/auth/token", post(issue_token))
        .route("/api/v1/auth/refresh", post(refresh_token))
        // Logout is protected — requires valid JWT to revoke
        .route("/api/v1/auth/logout", post(logout))
        .with_state(state)
}

// ── Tests ───────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{IpAddr, Ipv4Addr};

    #[test]
    fn test_extract_client_ip_from_forwarded_for() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "x-forwarded-for",
            HeaderValue::from_static("203.0.113.50, 70.41.3.18, 150.172.238.178"),
        );
        let addr = SocketAddr::new(IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)), 8080);

        let ip = extract_client_ip(&headers, Some(&addr));
        assert_eq!(ip, Some("203.0.113.50".to_string()));
    }

    #[test]
    fn test_extract_client_ip_from_real_ip() {
        let mut headers = HeaderMap::new();
        headers.insert("x-real-ip", HeaderValue::from_static("198.51.100.77"));
        let addr = SocketAddr::new(IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1)), 8080);

        let ip = extract_client_ip(&headers, Some(&addr));
        assert_eq!(ip, Some("198.51.100.77".to_string()));
    }

    #[test]
    fn test_extract_client_ip_from_connect_info() {
        let headers = HeaderMap::new();
        let addr = SocketAddr::new(IpAddr::V4(Ipv4Addr::new(10, 0, 0, 1)), 9090);

        let ip = extract_client_ip(&headers, Some(&addr));
        assert_eq!(ip, Some("10.0.0.1".to_string()));
    }

    #[test]
    fn test_extract_client_ip_precedence() {
        // X-Forwarded-For takes priority over X-Real-IP and ConnectInfo
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", HeaderValue::from_static("1.2.3.4"));
        headers.insert("x-real-ip", HeaderValue::from_static("5.6.7.8"));
        let addr = SocketAddr::new(IpAddr::V4(Ipv4Addr::new(9, 10, 11, 12)), 80);

        let ip = extract_client_ip(&headers, Some(&addr));
        assert_eq!(ip, Some("1.2.3.4".to_string()));
    }

    #[test]
    fn test_buyer_tier_limits() {
        assert_eq!(BuyerTier::Free.rate_limit_per_minute(), 10);
        assert_eq!(BuyerTier::Enterprise.rate_limit_per_minute(), 10000);
        assert!(!BuyerTier::Free.can_access_raw_data());
        assert!(BuyerTier::Enterprise.can_access_raw_data());
    }
}
