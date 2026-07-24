use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// User roles in the system.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum UserRole {
    Admin,
    Manager,
    Worker,
    Viewer,
}

impl std::fmt::Display for UserRole {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            UserRole::Admin => write!(f, "admin"),
            UserRole::Manager => write!(f, "manager"),
            UserRole::Worker => write!(f, "worker"),
            UserRole::Viewer => write!(f, "viewer"),
        }
    }
}

/// User model stored in the database.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct User {
    pub id: Uuid,
    pub email: String,
    #[serde(skip_serializing)]
    pub password_hash: String,
    pub full_name: String,
    pub role: UserRole,
    pub phone: Option<String>,
    pub avatar_url: Option<String>,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Registration request body.
#[derive(Debug, Deserialize, ToSchema)]
pub struct RegisterRequest {
    /// User email address
    pub email: String,
    /// Password (min 8 characters)
    pub password: String,
    /// Full name
    pub full_name: String,
    /// Optional phone number
    pub phone: Option<String>,
}

/// Login request body.
#[derive(Debug, Deserialize, ToSchema)]
pub struct LoginRequest {
    /// User email address
    pub email: String,
    /// User password
    pub password: String,
}

/// Token pair response.
#[derive(Debug, Serialize, ToSchema)]
pub struct TokenResponse {
    /// JWT access token
    pub access_token: String,
    /// JWT refresh token
    pub refresh_token: String,
    /// Token type (always "Bearer")
    pub token_type: String,
    /// Access token expiry in seconds
    pub expires_in: u64,
}

/// Refresh token request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct RefreshRequest {
    /// Refresh token
    pub refresh_token: String,
}

/// User profile response (public fields only).
#[derive(Debug, Serialize, ToSchema)]
pub struct UserResponse {
    pub id: Uuid,
    pub email: String,
    pub full_name: String,
    pub role: UserRole,
    pub phone: Option<String>,
    pub avatar_url: Option<String>,
    pub is_active: bool,
    pub created_at: DateTime<Utc>,
}

impl From<User> for UserResponse {
    fn from(u: User) -> Self {
        Self {
            id: u.id,
            email: u.email,
            full_name: u.full_name,
            role: u.role,
            phone: u.phone,
            avatar_url: u.avatar_url,
            is_active: u.is_active,
            created_at: u.created_at,
        }
    }
}

/// Update user profile request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateUserRequest {
    pub full_name: Option<String>,
    pub phone: Option<String>,
    pub avatar_url: Option<String>,
}
