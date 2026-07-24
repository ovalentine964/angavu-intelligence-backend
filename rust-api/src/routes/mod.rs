pub mod v1;

use axum::Router;

/// Build all API routes.
pub fn api_routes() -> Router {
    Router::new().nest("/api/v1", v1::routes())
}
