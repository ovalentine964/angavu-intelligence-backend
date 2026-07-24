use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    Json,
    Router,
    routing::{get, post},
};
use chrono::Utc;
use uuid::Uuid;

use crate::error::{AppError, AppResult};
use crate::middleware::AuthContext;
use crate::models::transaction::*;
use crate::AppState;

/// Mount transaction routes (auth required).
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/transactions", post(create_transaction).get(list_transactions))
        .route("/transactions/summary", get(summary))
        .route("/transactions/{id}", get(get_transaction))
}

/// POST /transactions
///
/// Record a new transaction.
#[utoipa::path(
    post,
    path = "/api/v1/transactions",
    request_body = CreateTransactionRequest,
    responses(
        (status = 201, description = "Transaction created", body = Transaction),
        (status = 422, description = "Validation error"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "transactions"
)]
async fn create_transaction(
    State(state): State<AppState>,
    auth_ctx: AuthContext,
    Json(body): Json<CreateTransactionRequest>,
) -> AppResult<(StatusCode, Json<serde_json::Value>)> {
    // Validate amount
    if body.amount <= 0.0 {
        return Err(AppError::Validation("Amount must be positive".to_string()));
    }

    if body.description.trim().is_empty() {
        return Err(AppError::Validation("Description is required".to_string()));
    }

    // Validate source
    let valid_sources = ["manual", "voice", "sync"];
    if !valid_sources.contains(&body.source.as_str()) {
        return Err(AppError::Validation(format!(
            "Invalid source '{}'. Must be one of: {:?}",
            body.source, valid_sources
        )));
    }

    // TODO: Insert into database
    let now = Utc::now();
    let transaction = Transaction {
        id: Uuid::new_v4(),
        user_id: auth_ctx.user_id,
        transaction_type: body.transaction_type,
        category: body.category,
        amount: body.amount,
        currency: body.currency,
        description: body.description,
        notes: body.notes,
        reference: body.reference,
        transaction_date: body.transaction_date.unwrap_or(now),
        created_at: now,
        updated_at: now,
        source: body.source,
        synced: false,
    };

    tracing::info!(
        user_id = %auth_ctx.user_id,
        transaction_id = %transaction.id,
        amount = transaction.amount,
        "Transaction created"
    );

    Ok((StatusCode::CREATED, Json(serde_json::json!(transaction))))
}

/// GET /transactions
///
/// List transactions for the authenticated user with filtering and pagination.
#[utoipa::path(
    get,
    path = "/api/v1/transactions",
    params(
        ("transaction_type" = Option<TransactionType>, Query, description = "Filter by type"),
        ("category" = Option<TransactionCategory>, Query, description = "Filter by category"),
        ("from_date" = Option<String>, Query, description = "From date (ISO 8601)"),
        ("to_date" = Option<String>, Query, description = "To date (ISO 8601)"),
        ("min_amount" = Option<f64>, Query, description = "Minimum amount"),
        ("max_amount" = Option<f64>, Query, description = "Maximum amount"),
        ("search" = Option<String>, Query, description = "Search description"),
        ("page" = Option<u32>, Query, description = "Page number"),
        ("per_page" = Option<u32>, Query, description = "Items per page"),
        ("sort_by" = Option<String>, Query, description = "Sort field"),
        ("sort_order" = Option<String>, Query, description = "Sort direction"),
    ),
    responses(
        (status = 200, description = "Paginated transaction list", body = TransactionListResponse),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "transactions"
)]
async fn list_transactions(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Query(params): Query<TransactionQuery>,
) -> AppResult<Json<serde_json::Value>> {
    // Clamp per_page to 1..=100
    let per_page = params.per_page.clamp(1, 100);
    let page = params.page.max(1);

    // TODO: Build SQL query from filters and execute against database
    tracing::info!(
        user_id = %auth_ctx.user_id,
        page = page,
        per_page = per_page,
        "Listing transactions"
    );

    // Placeholder: empty result set until DB is wired
    let response = TransactionListResponse {
        data: vec![],
        total: 0,
        page,
        per_page,
        total_pages: 0,
    };

    Ok(Json(serde_json::json!(response)))
}

/// GET /transactions/{id}
///
/// Get a single transaction by ID.
#[utoipa::path(
    get,
    path = "/api/v1/transactions/{id}",
    params(
        ("id" = Uuid, Path, description = "Transaction ID"),
    ),
    responses(
        (status = 200, description = "Transaction details", body = Transaction),
        (status = 404, description = "Transaction not found"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "transactions"
)]
async fn get_transaction(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Path(id): Path<Uuid>,
) -> AppResult<Json<serde_json::Value>> {
    // TODO: Fetch from database by id + user_id
    tracing::info!(
        user_id = %auth_ctx.user_id,
        transaction_id = %id,
        "Fetching transaction"
    );

    // Placeholder — in production, return 404 if not found:
    // return Err(AppError::NotFound(format!("Transaction {} not found", id)));

    Err(AppError::NotFound(format!("Transaction {} not found", id)))
}

/// GET /transactions/summary
///
/// Business flow summary: income vs expenses, top categories, daily totals.
#[utoipa::path(
    get,
    path = "/api/v1/transactions/summary",
    params(
        ("from_date" = Option<String>, Query, description = "From date (ISO 8601)"),
        ("to_date" = Option<String>, Query, description = "To date (ISO 8601)"),
    ),
    responses(
        (status = 200, description = "Transaction summary"),
    ),
    security(
        ("bearer_auth" = [])
    ),
    tag = "transactions"
)]
async fn summary(
    State(_state): State<AppState>,
    auth_ctx: AuthContext,
    Query(params): Query<SummaryQuery>,
) -> AppResult<Json<serde_json::Value>> {
    // TODO: Aggregate transactions in the date range from database
    tracing::info!(
        user_id = %auth_ctx.user_id,
        "Fetching transaction summary"
    );

    let now = Utc::now();
    let from = params.from_date.unwrap_or_else(|| now - chrono::Duration::days(30));
    let to = params.to_date.unwrap_or(now);

    Ok(Json(serde_json::json!({
        "period": {
            "from": from,
            "to": to,
        },
        "total_income": 0.0,
        "total_expenses": 0.0,
        "net_flow": 0.0,
        "transaction_count": 0,
        "top_categories": [],
        "daily_totals": [],
    })))
}

/// Query parameters for the summary endpoint.
#[derive(Debug, serde::Deserialize)]
pub struct SummaryQuery {
    pub from_date: Option<chrono::DateTime<Utc>>,
    pub to_date: Option<chrono::DateTime<Utc>>,
}
