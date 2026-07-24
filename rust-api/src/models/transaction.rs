use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

/// Transaction type categories.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TransactionType {
    Income,
    Expense,
    Transfer,
    Adjustment,
}

/// Transaction category.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum TransactionCategory {
    Sales,
    Services,
    Salary,
    Rent,
    Utilities,
    Supplies,
    Marketing,
    Transport,
    Food,
    Insurance,
    Tax,
    Loan,
    Investment,
    Other,
}

/// Transaction model stored in the database.
#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct Transaction {
    pub id: Uuid,
    pub user_id: Uuid,
    pub transaction_type: TransactionType,
    pub category: TransactionCategory,
    pub amount: f64,
    pub currency: String,
    pub description: String,
    pub notes: Option<String>,
    pub reference: Option<String>,
    pub transaction_date: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    /// Source: manual, voice, sync
    pub source: String,
    /// Whether this has been synced from offline
    pub synced: bool,
}

/// Create transaction request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct CreateTransactionRequest {
    /// Transaction type (income, expense, transfer, adjustment)
    pub transaction_type: TransactionType,
    /// Category
    pub category: TransactionCategory,
    /// Amount (positive value)
    pub amount: f64,
    /// Currency code (default: LKR)
    #[serde(default = "default_currency")]
    pub currency: String,
    /// Description of the transaction
    pub description: String,
    /// Optional notes
    pub notes: Option<String>,
    /// Optional reference number
    pub reference: Option<String>,
    /// Transaction date (defaults to now)
    pub transaction_date: Option<DateTime<Utc>>,
    /// Source of entry (manual, voice, sync)
    #[serde(default = "default_source")]
    pub source: String,
}

fn default_currency() -> String {
    "LKR".to_string()
}

fn default_source() -> String {
    "manual".to_string()
}

/// Update transaction request.
#[derive(Debug, Deserialize, ToSchema)]
pub struct UpdateTransactionRequest {
    pub transaction_type: Option<TransactionType>,
    pub category: Option<TransactionCategory>,
    pub amount: Option<f64>,
    pub description: Option<String>,
    pub notes: Option<String>,
    pub reference: Option<String>,
    pub transaction_date: Option<DateTime<Utc>>,
}

/// Transaction list query parameters.
#[derive(Debug, Deserialize, ToSchema)]
pub struct TransactionQuery {
    /// Filter by type
    pub transaction_type: Option<TransactionType>,
    /// Filter by category
    pub category: Option<TransactionCategory>,
    /// Filter from date (ISO 8601)
    pub from_date: Option<DateTime<Utc>>,
    /// Filter to date (ISO 8601)
    pub to_date: Option<DateTime<Utc>>,
    /// Minimum amount
    pub min_amount: Option<f64>,
    /// Maximum amount
    pub max_amount: Option<f64>,
    /// Search in description
    pub search: Option<String>,
    /// Page number (default: 1)
    #[serde(default = "default_page")]
    pub page: u32,
    /// Items per page (default: 20, max: 100)
    #[serde(default = "default_per_page")]
    pub per_page: u32,
    /// Sort field (default: transaction_date)
    #[serde(default = "default_sort_by")]
    pub sort_by: String,
    /// Sort direction: asc or desc
    #[serde(default = "default_sort_order")]
    pub sort_order: String,
}

fn default_page() -> u32 { 1 }
fn default_per_page() -> u32 { 20 }
fn default_sort_by() -> String { "transaction_date".to_string() }
fn default_sort_order() -> String { "desc".to_string() }

/// Paginated transaction list response.
#[derive(Debug, Serialize, ToSchema)]
pub struct TransactionListResponse {
    pub data: Vec<Transaction>,
    pub total: u64,
    pub page: u32,
    pub per_page: u32,
    pub total_pages: u32,
}

/// Batch sync request for offline transactions.
#[derive(Debug, Deserialize, ToSchema)]
pub struct BatchSyncRequest {
    /// List of transactions to sync
    pub transactions: Vec<CreateTransactionRequest>,
    /// Client device ID
    pub device_id: String,
    /// Client sync timestamp
    pub client_timestamp: DateTime<Utc>,
}

/// Batch sync response.
#[derive(Debug, Serialize, ToSchema)]
pub struct BatchSyncResponse {
    /// Number of transactions synced
    pub synced_count: u32,
    /// List of IDs that failed to sync
    pub failed: Vec<SyncFailure>,
    /// Server sync timestamp
    pub server_timestamp: DateTime<Utc>,
}

/// Individual sync failure.
#[derive(Debug, Serialize, ToSchema)]
pub struct SyncFailure {
    /// Index in the original batch
    pub index: u32,
    /// Error message
    pub error: String,
}
