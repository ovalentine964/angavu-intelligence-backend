use std::env;

/// Application configuration loaded from environment variables.
#[derive(Debug, Clone)]
pub struct AppConfig {
    /// Server bind address (e.g., "0.0.0.0")
    pub host: String,
    /// Server port
    pub port: u16,
    /// Database connection URL
    pub database_url: String,
    /// JWT signing secret
    pub jwt_secret: String,
    /// JWT token expiry in seconds (default: 3600 = 1 hour)
    pub jwt_expiry_secs: u64,
    /// JWT refresh token expiry in seconds (default: 604800 = 7 days)
    pub jwt_refresh_expiry_secs: u64,
    /// Rate limit: max requests per window
    pub rate_limit_max_requests: u64,
    /// Rate limit window in seconds
    pub rate_limit_window_secs: u64,
    /// Python LLM inference service URL
    pub llm_service_url: String,
    /// Allowed CORS origins (comma-separated)
    pub cors_allowed_origins: Vec<String>,
    /// Log level (trace, debug, info, warn, error)
    pub log_level: String,
    /// Environment (development, staging, production)
    pub environment: String,
}

impl AppConfig {
    /// Load configuration from environment variables.
    /// Panics if required variables are missing.
    pub fn from_env() -> Self {
        dotenvy::dotenv().ok();

        Self {
            host: env::var("HOST").unwrap_or_else(|_| "0.0.0.0".to_string()),
            port: env::var("PORT")
                .unwrap_or_else(|_| "8080".to_string())
                .parse()
                .expect("PORT must be a valid u16"),
            database_url: env::var("DATABASE_URL")
                .expect("DATABASE_URL is required"),
            jwt_secret: env::var("JWT_SECRET")
                .expect("JWT_SECRET is required"),
            jwt_expiry_secs: env::var("JWT_EXPIRY_SECS")
                .unwrap_or_else(|_| "3600".to_string())
                .parse()
                .expect("JWT_EXPIRY_SECS must be a valid u64"),
            jwt_refresh_expiry_secs: env::var("JWT_REFRESH_EXPIRY_SECS")
                .unwrap_or_else(|_| "604800".to_string())
                .parse()
                .expect("JWT_REFRESH_EXPIRY_SECS must be a valid u64"),
            rate_limit_max_requests: env::var("RATE_LIMIT_MAX_REQUESTS")
                .unwrap_or_else(|_| "100".to_string())
                .parse()
                .expect("RATE_LIMIT_MAX_REQUESTS must be a valid u64"),
            rate_limit_window_secs: env::var("RATE_LIMIT_WINDOW_SECS")
                .unwrap_or_else(|_| "60".to_string())
                .parse()
                .expect("RATE_LIMIT_WINDOW_SECS must be a valid u64"),
            llm_service_url: env::var("LLM_SERVICE_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:5000".to_string()),
            cors_allowed_origins: env::var("CORS_ALLOWED_ORIGINS")
                .unwrap_or_else(|_| "*".to_string())
                .split(',')
                .map(|s| s.trim().to_string())
                .collect(),
            log_level: env::var("LOG_LEVEL")
                .unwrap_or_else(|_| "info".to_string()),
            environment: env::var("ENVIRONMENT")
                .unwrap_or_else(|_| "development".to_string()),
        }
    }

    /// Check if running in production mode.
    pub fn is_production(&self) -> bool {
        self.environment == "production"
    }
}
