pub mod auth;
pub mod transactions;
pub mod workers;
pub mod intelligence;
pub mod credit;
pub mod goals;
pub mod sync;
pub mod voice;
pub mod outcomes;
pub mod health;

use axum::{
    middleware,
    Router,
};

use crate::middleware::auth_middleware;
use crate::AppState;

/// Build v1 API routes.
pub fn routes() -> Router<AppState> {
    // Public routes (no auth required)
    let public_routes = Router::new()
        .merge(auth::routes())
        .merge(health::routes());

    // Protected routes (auth required)
    let protected_routes = Router::new()
        .merge(auth::protected_routes())
        .merge(transactions::routes())
        .merge(workers::routes())
        .merge(intelligence::routes())
        .merge(credit::routes())
        .merge(goals::routes())
        .merge(sync::routes())
        .merge(voice::routes())
        .merge(outcomes::routes())
        .layer(middleware::from_fn(auth_middleware));

    Router::new()
        .merge(public_routes)
        .merge(protected_routes)
}
