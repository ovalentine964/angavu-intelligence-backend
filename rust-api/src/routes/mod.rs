pub mod v1;

use axum::Router;
use crate::AppState;

/// Build all API routes.
pub fn api_routes() -> Router<AppState> {
    Router::new().nest("/api/v1", v1::routes())
}
