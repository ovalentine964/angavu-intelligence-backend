use axum::{
    extract::{FromRequestParts, Request},
    http::{header, request::Parts},
    middleware::Next,
    response::Response,
};
use jsonwebtoken::{decode, DecodingKey, Validation, Algorithm};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::error::AppError;

/// JWT claims structure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JwtClaims {
    /// Subject (user ID)
    pub sub: Uuid,
    /// User email
    pub email: String,
    /// User role
    pub role: String,
    /// Expiration time (unix timestamp)
    pub exp: u64,
    /// Issued at (unix timestamp)
    pub iat: u64,
    /// Token type: "access" or "refresh"
    pub token_type: String,
}

/// Authenticated user context extracted from JWT.
#[derive(Debug, Clone)]
pub struct AuthContext {
    pub user_id: Uuid,
    pub email: String,
    pub role: String,
}

/// Implement `FromRequestParts` so `AuthContext` can be used directly
/// as a handler parameter. The auth middleware must have run first to
/// insert it into request extensions.
#[axum::async_trait]
impl<S: Send + Sync> FromRequestParts<S> for AuthContext {
    type Rejection = AppError;

    async fn from_request_parts(
        parts: &mut Parts,
        _state: &S,
    ) -> Result<Self, Self::Rejection> {
        parts
            .extensions
            .get::<AuthContext>()
            .cloned()
            .ok_or_else(|| {
                AppError::Unauthorized(
                    "Authentication required".to_string(),
                )
            })
    }
}

/// Axum middleware that validates JWT from the Authorization header.
/// Attaches `AuthContext` to request extensions on success.
pub async fn auth_middleware(
    mut request: Request,
    next: Next,
) -> Result<Response, AppError> {
    let auth_header = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .ok_or_else(|| AppError::Unauthorized("Missing Authorization header".to_string()))?;

    let token = auth_header
        .strip_prefix("Bearer ")
        .ok_or_else(|| AppError::Unauthorized("Invalid Authorization header format. Expected 'Bearer <token>'".to_string()))?;

    if token.is_empty() {
        return Err(AppError::Unauthorized("Empty token".to_string()));
    }

    // Get the JWT secret from the extension (set during app init)
    let jwt_secret = request
        .extensions()
        .get::<String>()
        .cloned()
        .unwrap_or_default();

    let token_data = decode::<JwtClaims>(
        token,
        &DecodingKey::from_secret(jwt_secret.as_bytes()),
        &Validation::new(Algorithm::HS256),
    )
    .map_err(|e| {
        AppError::Unauthorized(format!("Invalid token: {}", e))
    })?;

    let claims = token_data.claims;

    // Only accept access tokens
    if claims.token_type != "access" {
        return Err(AppError::Unauthorized(
            "Expected access token, got refresh token".to_string(),
        ));
    }

    let auth_ctx = AuthContext {
        user_id: claims.sub,
        email: claims.email,
        role: claims.role,
    };

    request.extensions_mut().insert(auth_ctx);
    Ok(next.run(request).await)
}

/// Create a JWT access token.
pub fn create_access_token(
    user_id: Uuid,
    email: &str,
    role: &str,
    secret: &str,
    expiry_secs: u64,
) -> Result<String, AppError> {
    create_token(user_id, email, role, "access", secret, expiry_secs)
}

/// Create a JWT refresh token.
pub fn create_refresh_token(
    user_id: Uuid,
    email: &str,
    role: &str,
    secret: &str,
    expiry_secs: u64,
) -> Result<String, AppError> {
    create_token(user_id, email, role, "refresh", secret, expiry_secs)
}

fn create_token(
    user_id: Uuid,
    email: &str,
    role: &str,
    token_type: &str,
    secret: &str,
    expiry_secs: u64,
) -> Result<String, AppError> {
    let now = chrono::Utc::now().timestamp() as u64;
    let claims = JwtClaims {
        sub: user_id,
        email: email.to_string(),
        role: role.to_string(),
        exp: now + expiry_secs,
        iat: now,
        token_type: token_type.to_string(),
    };

    jsonwebtoken::encode(
        &jsonwebtoken::Header::default(),
        &claims,
        &EncodingKey::from_secret(secret.as_bytes()),
    )
    .map_err(|e| AppError::Internal(format!("Failed to create token: {}", e)))
}

use jsonwebtoken::EncodingKey;
