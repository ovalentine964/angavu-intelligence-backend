// src/gateway/auth.rs

use axum::{
    extract::Request,
    http::{HeaderMap, StatusCode},
    middleware::Next,
    response::Response,
};
use jsonwebtoken::{decode, encode, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct JwtConfig {
    pub encoding_key: EncodingKey,
    pub decoding_key: DecodingKey,
    pub validation: Validation,
    /// Token expiry (seconds)
    pub access_token_ttl: u64,
    pub refresh_token_ttl: u64,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct Claims {
    /// Buyer organization ID
    pub org_id: String,
    /// Buyer tier (free, starter, pro, enterprise)
    pub tier: BuyerTier,
    /// API key ID
    pub key_id: String,
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

/// JWT authentication middleware
pub async fn jwt_auth_middleware(
    State(state): State<super::GatewayState>,
    mut request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let headers = request.headers();

    // Extract token from Authorization header
    let token = extract_bearer_token(headers)
        .ok_or(StatusCode::UNAUTHORIZED)?;

    // Validate JWT
    let claims = decode::<Claims>(
        &token,
        &state.jwt_config.decoding_key,
        &state.jwt_config.validation,
    )
    .map_err(|_| StatusCode::UNAUTHORIZED)?
    .claims;

    // Check expiration
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs();
    if claims.exp < now {
        return Err(StatusCode::UNAUTHORIZED);
    }

    // Inject claims into request extensions for downstream handlers
    request.extensions_mut().insert(claims);

    Ok(next.run(request).await)
}

fn extract_bearer_token(headers: &HeaderMap) -> Option<String> {
    headers
        .get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .map(|s| s.to_string())
}
