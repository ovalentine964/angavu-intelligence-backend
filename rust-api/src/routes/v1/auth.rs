use axum::{
    extract::State,
    Json,
    Router,
    routing::{get, post},
};
use uuid::Uuid;
use chrono::Utc;

use crate::error::{AppError, AppResult};
use crate::middleware::auth::{self, AuthContext};
use crate::models::user::*;
use crate::AppState;

/// Public auth routes (no authentication required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/auth/register", post(register))
        .route("/auth/login", post(login))
        .route("/auth/refresh", post(refresh_token))
}

/// Protected auth routes (authentication required).
pub fn protected_routes() -> Router<AppState> {
    Router::new()
        .route("/auth/me", get(profile))
}

/// POST /auth/register
///
/// Register a new user account.
#[utoipa::path(
    post,
    path = "/api/v1/auth/register",
    request_body = RegisterRequest,
    responses(
        (status = 201, description = "User registered successfully", body = TokenResponse),
        (status = 409, description = "Email already registered"),
        (status = 422, description = "Validation error"),
    ),
    tag = "auth"
)]
pub async fn register(
    State(state): State<AppState>,
    Json(body): Json<RegisterRequest>,
) -> AppResult<(axum::http::StatusCode, Json<serde_json::Value>)> {
    // Validate email format
    if !body.email.contains('@') || body.email.len() < 5 {
        return Err(AppError::Validation("Invalid email format".to_string()));
    }

    // Validate password strength
    if body.password.len() < 8 {
        return Err(AppError::Validation(
            "Password must be at least 8 characters".to_string(),
        ));
    }

    // Validate full name
    if body.full_name.trim().is_empty() {
        return Err(AppError::Validation("Full name is required".to_string()));
    }

    // TODO: Check if email already exists in database
    // TODO: Hash password with argon2
    // TODO: Insert user into database

    let user_id = Uuid::new_v4();
    let now = Utc::now();

    // Generate token pair
    let access_token = auth::create_access_token(
        user_id,
        &body.email,
        "worker",
        &state.config.jwt_secret,
        state.config.jwt_expiry_secs,
    )?;

    let refresh_token = auth::create_refresh_token(
        user_id,
        &body.email,
        "worker",
        &state.config.jwt_secret,
        state.config.jwt_refresh_expiry_secs,
    )?;

    let response = serde_json::json!({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": state.config.jwt_expiry_secs,
        "user": {
            "id": user_id,
            "email": body.email,
            "full_name": body.full_name,
            "role": "worker",
            "created_at": now
        }
    });

    Ok((axum::http::StatusCode::CREATED, Json(response)))
}

/// POST /auth/login
///
/// Authenticate user with email and password.
#[utoipa::path(
    post,
    path = "/api/v1/auth/login",
    request_body = LoginRequest,
    responses(
        (status = 200, description = "Login successful", body = TokenResponse),
        (status = 401, description = "Invalid credentials"),
    ),
    tag = "auth"
)]
pub async fn login(
    State(state): State<AppState>,
    Json(body): Json<LoginRequest>,
) -> AppResult<Json<serde_json::Value>> {
    if body.email.is_empty() || body.password.is_empty() {
        return Err(AppError::Validation(
            "Email and password are required".to_string(),
        ));
    }

    // TODO: Look up user by email in database
    // TODO: Verify password hash
    // For now, return a placeholder indicating the DB layer needs wiring

    // Placeholder: simulate user lookup
    let user_id = Uuid::new_v4();
    let role = "worker";

    let access_token = auth::create_access_token(
        user_id,
        &body.email,
        role,
        &state.config.jwt_secret,
        state.config.jwt_expiry_secs,
    )?;

    let refresh_token = auth::create_refresh_token(
        user_id,
        &body.email,
        role,
        &state.config.jwt_secret,
        state.config.jwt_refresh_expiry_secs,
    )?;

    Ok(Json(serde_json::json!({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": state.config.jwt_expiry_secs
    })))
}

/// POST /auth/refresh
///
/// Refresh an expired access token using a valid refresh token.
#[utoipa::path(
    post,
    path = "/api/v1/auth/refresh",
    request_body = RefreshRequest,
    responses(
        (status = 200, description = "Token refreshed", body = TokenResponse),
        (status = 401, description = "Invalid refresh token"),
    ),
    tag = "auth"
)]
pub async fn refresh_token(
    State(state): State<AppState>,
    Json(body): Json<RefreshRequest>,
) -> AppResult<Json<serde_json::Value>> {
    use jsonwebtoken::{decode, DecodingKey, Validation, Algorithm};

    let token_data = decode::<auth::JwtClaims>(
        &body.refresh_token,
        &DecodingKey::from_secret(state.config.jwt_secret.as_bytes()),
        &Validation::new(Algorithm::HS256),
    )
    .map_err(|e| AppError::Unauthorized(format!("Invalid refresh token: {}", e)))?;

    let claims = token_data.claims;

    if claims.token_type != "refresh" {
        return Err(AppError::Unauthorized(
            "Expected refresh token".to_string(),
        ));
    }

    let access_token = auth::create_access_token(
        claims.sub,
        &claims.email,
        &claims.role,
        &state.config.jwt_secret,
        state.config.jwt_expiry_secs,
    )?;

    let new_refresh_token = auth::create_refresh_token(
        claims.sub,
        &claims.email,
        &claims.role,
        &state.config.jwt_secret,
        state.config.jwt_refresh_expiry_secs,
    )?;

    Ok(Json(serde_json::json!({
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "Bearer",
        "expires_in": state.config.jwt_expiry_secs
    })))
}

/// GET /auth/me
///
/// Get current authenticated user's profile.
#[utoipa::path(
    get,
    path = "/api/v1/auth/me",
    responses(
        (status = 200, description = "User profile", body = UserResponse),
        (status = 401, description = "Unauthorized"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "auth"
)]
pub async fn profile(
    auth_ctx: AuthContext,
) -> AppResult<Json<serde_json::Value>> {
    // TODO: Fetch full user profile from database
    Ok(Json(serde_json::json!({
        "id": auth_ctx.user_id,
        "email": auth_ctx.email,
        "role": auth_ctx.role
    })))
}
