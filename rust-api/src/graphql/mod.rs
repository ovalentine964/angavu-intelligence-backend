//! GraphQL Layer — async-graphql schema and resolvers for the knowledge graph.
//!
//! Provides queries for: nodes, edges, paths, subgraphs, PageRank, communities.

pub mod schema;

use axum::{routing::get, Router};
use async_graphql::http::{playground_source, GraphQLPlaygroundConfig};
use async_graphql_axum::{GraphQLRequest, GraphQLResponse};

pub use schema::{AngavuSchema, build_schema, create_schema};

/// Build the GraphQL Axum router with playground and endpoint.
pub fn graphql_router(schema: AngavuSchema) -> Router {
    Router::new()
        .route("/graphql", get(graphql_playground).post(graphql_handler))
        .route("/graphql/schema", get(graphql_schema_sdl))
        .with_state(schema)
}

/// GraphQL playground (browser UI).
async fn graphql_playground() -> axum::response::Html<String> {
    axum::response::Html(playground_source(
        GraphQLPlaygroundConfig::new("/graphql").title("Angavu Intelligence GraphQL"),
    ))
}

/// GraphQL request handler.
#[tracing::instrument(skip(schema, req))]
async fn graphql_handler(
    axum::extract::State(schema): axum::extract::State<AngavuSchema>,
    req: GraphQLRequest,
) -> GraphQLResponse {
    schema.execute(req.into_inner()).await.into()
}

/// Schema SDL endpoint for introspection.
async fn graphql_schema_sdl(
    axum::extract::State(schema): axum::extract::State<AngavuSchema>,
) -> String {
    schema.sdl()
}
