// =============================================================================
// Angavu Intelligence — Tool Registry
// Defines all 26 callable tools with JSON Schema for inputs/outputs,
// descriptions for LLM consumption, and execution dispatch.
//
// Architecture:
//   ToolDefinition (schema + metadata) → ToolRegistry (lookup/dispatch)
//   → ToolExecutor (runtime execution with validation)
//
// Each tool is:
//   1. Declared with a JSON Schema for its parameters (for LLM function calling)
//   2. Registered in a concurrent registry (DashMap)
//   3. Executable via the ToolExecutor trait with input validation
// =============================================================================

use async_trait::async_trait;
use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

// ── Tool Schema Types ────────────────────────────────────────────────────────

/// JSON Schema definition for tool parameters (OpenAI function calling format)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolParameterSchema {
    #[serde(rename = "type")]
    pub schema_type: String,
    pub properties: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub required: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub additional_properties: Option<bool>,
}

/// A tool definition as consumed by the LLM (OpenAI function calling format)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    /// Unique tool name (snake_case)
    pub name: String,
    /// Human-readable description for the LLM
    pub description: String,
    /// JSON Schema for the tool's input parameters
    pub parameters: ToolParameterSchema,
    /// Category for grouping (credit, market, intelligence, system)
    pub category: ToolCategory,
    /// Whether this tool requires human approval before execution
    pub requires_approval: bool,
    /// Risk level of the tool
    pub risk_level: ToolRiskLevel,
    /// Maximum execution time in seconds
    pub timeout_secs: u64,
    /// Whether the tool is read-only (no side effects)
    pub read_only: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolCategory {
    Credit,
    Market,
    Intelligence,
    Data,
    System,
    Federated,
    Billing,
    Health,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolRiskLevel {
    /// Read-only, no side effects
    Low,
    /// Writes data but reversible
    Medium,
    /// External actions, financial impact
    High,
    /// Irreversible, requires approval
    Critical,
}

/// Result of a tool execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    pub success: bool,
    pub output: serde_json::Value,
    pub error: Option<String>,
    pub execution_ms: u64,
    pub tool_name: String,
    /// Metadata about the execution (audit trail)
    pub metadata: ToolExecutionMetadata,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolExecutionMetadata {
    pub executed_at: chrono::DateTime<chrono::Utc>,
    pub input_hash: String,
    pub circuit_breaker_state: String,
    pub from_cache: bool,
}

// ── Tool Executor Trait ──────────────────────────────────────────────────────

/// Trait for executing a tool. Each tool implements this.
#[async_trait]
pub trait ToolExecutor: Send + Sync {
    /// Execute the tool with validated input
    async fn execute(&self, input: serde_json::Value) -> Result<serde_json::Value, ToolError>;

    /// Validate input without executing (dry run)
    fn validate_input(&self, input: &serde_json::Value) -> Result<(), ToolError>;

    /// Tool name (must match the registry name)
    fn name(&self) -> &str;
}

#[derive(Debug, thiserror::Error)]
pub enum ToolError {
    #[error("Invalid input: {0}")]
    InvalidInput(String),
    #[error("Execution failed: {0}")]
    ExecutionFailed(String),
    #[error("Timeout after {0}s")]
    Timeout(u64),
    #[error("Rate limited: {0}")]
    RateLimited(String),
    #[error("Unauthorized: {0}")]
    Unauthorized(String),
    #[error("Circuit breaker open for tool: {0}")]
    CircuitOpen(String),
    #[error("Tool not found: {0}")]
    NotFound(String),
    #[error("Human approval required")]
    ApprovalRequired,
}

// ── Tool Registry ────────────────────────────────────────────────────────────

/// Concurrent registry of all tools with their definitions and executors
pub struct ToolRegistry {
    definitions: DashMap<String, ToolDefinition>,
    executors: DashMap<String, Arc<dyn ToolExecutor>>,
}

impl ToolRegistry {
    pub fn new() -> Self {
        Self {
            definitions: DashMap::new(),
            executors: DashMap::new(),
        }
    }

    /// Register a tool with its definition and executor
    pub fn register(&self, definition: ToolDefinition, executor: Arc<dyn ToolExecutor>) {
        let name = definition.name.clone();
        self.definitions.insert(name.clone(), definition);
        self.executors.insert(name, executor);
    }

    /// Get a tool definition by name
    pub fn get_definition(&self, name: &str) -> Option<ToolDefinition> {
        self.definitions.get(name).map(|r| r.value().clone())
    }

    /// Get an executor by name
    pub fn get_executor(&self, name: &str) -> Option<Arc<dyn ToolExecutor>> {
        self.executors.get(name).map(|r| r.value().clone())
    }

    /// List all tool names
    pub fn list_names(&self) -> Vec<String> {
        self.definitions.iter().map(|r| r.key().clone()).collect()
    }

    /// Get all definitions (for LLM system prompt construction)
    pub fn all_definitions(&self) -> Vec<ToolDefinition> {
        self.definitions.iter().map(|r| r.value().clone()).collect()
    }

    /// Get definitions formatted for OpenAI function calling
    pub fn openai_functions(&self) -> Vec<serde_json::Value> {
        self.definitions
            .iter()
            .map(|entry| {
                let def = entry.value();
                serde_json::json!({
                    "type": "function",
                    "function": {
                        "name": def.name,
                        "description": def.description,
                        "parameters": def.parameters,
                    }
                })
            })
            .collect()
    }

    /// Get definitions by category
    pub fn by_category(&self, category: ToolCategory) -> Vec<ToolDefinition> {
        self.definitions
            .iter()
            .filter(|r| r.value().category == category)
            .map(|r| r.value().clone())
            .collect()
    }

    /// Execute a tool by name with input validation
    pub async fn execute_tool(&self, name: &str, input: serde_json::Value) -> ToolResult {
        let start = std::time::Instant::now();

        // Look up definition
        let definition = match self.definitions.get(name) {
            Some(d) => d.clone(),
            None => {
                return ToolResult {
                    success: false,
                    output: serde_json::Value::Null,
                    error: Some(format!("Tool not found: {}", name)),
                    execution_ms: start.elapsed().as_millis() as u64,
                    tool_name: name.to_string(),
                    metadata: ToolExecutionMetadata {
                        executed_at: chrono::Utc::now(),
                        input_hash: format!("{:x}", md5::compute(input.to_string().as_bytes())),
                        circuit_breaker_state: "n/a".to_string(),
                        from_cache: false,
                    },
                };
            }
        };

        // Check if approval required
        if definition.requires_approval {
            return ToolResult {
                success: false,
                output: serde_json::Value::Null,
                error: Some("Human approval required before execution".to_string()),
                execution_ms: start.elapsed().as_millis() as u64,
                tool_name: name.to_string(),
                metadata: ToolExecutionMetadata {
                    executed_at: chrono::Utc::now(),
                    input_hash: format!("{:x}", md5::compute(input.to_string().as_bytes())),
                    circuit_breaker_state: "approval_pending".to_string(),
                    from_cache: false,
                },
            };
        }

        // Look up executor
        let executor = match self.executors.get(name) {
            Some(e) => e.clone(),
            None => {
                return ToolResult {
                    success: false,
                    output: serde_json::Value::Null,
                    error: Some(format!("No executor registered for tool: {}", name)),
                    execution_ms: start.elapsed().as_millis() as u64,
                    tool_name: name.to_string(),
                    metadata: ToolExecutionMetadata {
                        executed_at: chrono::Utc::now(),
                        input_hash: format!("{:x}", md5::compute(input.to_string().as_bytes())),
                        circuit_breaker_state: "n/a".to_string(),
                        from_cache: false,
                    },
                };
            }
        };

        // Validate input
        if let Err(e) = executor.validate_input(&input) {
            return ToolResult {
                success: false,
                output: serde_json::Value::Null,
                error: Some(format!("Input validation failed: {}", e)),
                execution_ms: start.elapsed().as_millis() as u64,
                tool_name: name.to_string(),
                metadata: ToolExecutionMetadata {
                    executed_at: chrono::Utc::now(),
                    input_hash: format!("{:x}", md5::compute(input.to_string().as_bytes())),
                    circuit_breaker_state: "n/a".to_string(),
                    from_cache: false,
                },
            };
        }

        // Execute with timeout
        let timeout = std::time::Duration::from_secs(definition.timeout_secs);
        let result = tokio::time::timeout(timeout, executor.execute(input.clone())).await;

        match result {
            Ok(Ok(output)) => ToolResult {
                success: true,
                output,
                error: None,
                execution_ms: start.elapsed().as_millis() as u64,
                tool_name: name.to_string(),
                metadata: ToolExecutionMetadata {
                    executed_at: chrono::Utc::now(),
                    input_hash: format!("{:x}", md5::compute(input.to_string().as_bytes())),
                    circuit_breaker_state: "closed".to_string(),
                    from_cache: false,
                },
            },
            Ok(Err(e)) => ToolResult {
                success: false,
                output: serde_json::Value::Null,
                error: Some(e.to_string()),
                execution_ms: start.elapsed().as_millis() as u64,
                tool_name: name.to_string(),
                metadata: ToolExecutionMetadata {
                    executed_at: chrono::Utc::now(),
                    input_hash: format!("{:x}", md5::compute(input.to_string().as_bytes())),
                    circuit_breaker_state: "closed".to_string(),
                    from_cache: false,
                },
            },
            Err(_) => ToolResult {
                success: false,
                output: serde_json::Value::Null,
                error: Some(format!(
                    "Tool execution timed out after {}s",
                    definition.timeout_secs
                )),
                execution_ms: start.elapsed().as_millis() as u64,
                tool_name: name.to_string(),
                metadata: ToolExecutionMetadata {
                    executed_at: chrono::Utc::now(),
                    input_hash: format!("{:x}", md5::compute(input.to_string().as_bytes())),
                    circuit_breaker_state: "timeout".to_string(),
                    from_cache: false,
                },
            },
        }
    }
}

impl Default for ToolRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ── Tool Definition Builders ─────────────────────────────────────────────────

/// Build all 26 tool definitions. Call this during startup to populate the registry.
pub fn build_all_tool_definitions() -> Vec<ToolDefinition> {
    vec![
        // ── Credit Tools (8) ─────────────────────────────────────────────
        credit_score_compute(),
        credit_score_history(),
        credit_risk_assessment(),
        credit_decision_recommend(),
        credit_batch_score(),
        credit_cohort_analysis(),
        credit_default_predict(),
        credit_seasonality_adjust(),
        // ── Market Tools (6) ─────────────────────────────────────────────
        market_analysis(),
        market_price_lookup(),
        market_demand_forecast(),
        market_trend_detect(),
        market_opportunity_scan(),
        market_competitor_analysis(),
        // ── Intelligence Tools (4) ───────────────────────────────────────
        intelligence_report_generate(),
        intelligence_anomaly_detect(),
        intelligence_pattern_mine(),
        intelligence_knowledge_query(),
        // ── Data Tools (4) ───────────────────────────────────────────────
        data_transaction_query(),
        data_cohort_lookup(),
        data_aggregate(),
        data_export(),
        // ── Federated Learning Tools (2) ─────────────────────────────────
        federated_status(),
        federated_trigger_round(),
        // ── System Tools (2) ─────────────────────────────────────────────
        system_health_check(),
        system_model_status(),
    ]
}

// ── Individual Tool Definitions ──────────────────────────────────────────────

fn credit_score_compute() -> ToolDefinition {
    ToolDefinition {
        name: "credit_score_compute".to_string(),
        description: "Compute the Alama credit score for a worker cohort. Returns a score from 300-850 with risk tier, default probability, and component breakdown. Requires cohort_hash and worker_type.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "SHA-256 hash identifying the anonymized worker cohort"
                },
                "worker_type": {
                    "type": "string",
                    "enum": ["farmer", "fisherman", "boda_boda", "mpesa_agent", "vendor", "jua_kali", "casual_laborer", "construction", "food_service", "livestock", "mining", "digital_worker", "artisan", "agent_broker", "service_provider", "community_care"],
                    "description": "Type of informal sector worker"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region (e.g., 'nairobi', 'mombasa', 'kisumu')"
                },
                "transaction_history_months": {
                    "type": "integer",
                    "description": "Months of transaction history to consider (default: 6)",
                    "minimum": 1,
                    "maximum": 24
                },
                "include_components": {
                    "type": "boolean",
                    "description": "Whether to include score component breakdown (default: true)"
                }
            }),
            required: Some(vec!["cohort_hash".to_string(), "worker_type".to_string(), "region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: false,
        risk_level: ToolRiskLevel::Medium,
        timeout_secs: 15,
        read_only: true,
    }
}

fn credit_score_history() -> ToolDefinition {
    ToolDefinition {
        name: "credit_score_history".to_string(),
        description: "Retrieve historical credit scores for a cohort over time. Shows score trajectory, trend direction, and volatility.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "Cohort identifier hash"
                },
                "months_back": {
                    "type": "integer",
                    "description": "Number of months of history to retrieve (default: 12)",
                    "minimum": 1,
                    "maximum": 36
                }
            }),
            required: Some(vec!["cohort_hash".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 10,
        read_only: true,
    }
}

fn credit_risk_assessment() -> ToolDefinition {
    ToolDefinition {
        name: "credit_risk_assessment".to_string(),
        description: "Deep risk assessment for a cohort combining transaction patterns, market conditions, seasonal factors, and peer comparison. Returns risk factors, mitigation recommendations, and confidence score.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "Cohort identifier hash"
                },
                "worker_type": {
                    "type": "string",
                    "description": "Worker sector type"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region"
                },
                "loan_amount_kes": {
                    "type": "number",
                    "description": "Proposed loan amount in KES (optional, for affordability check)"
                }
            }),
            required: Some(vec!["cohort_hash".to_string(), "worker_type".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 20,
        read_only: true,
    }
}

fn credit_decision_recommend() -> ToolDefinition {
    ToolDefinition {
        name: "credit_decision_recommend".to_string(),
        description: "Generate a credit approval/rejection recommendation with reasoning. Combines score, risk assessment, market context, and seasonal factors into a decision with confidence level.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "Cohort identifier hash"
                },
                "worker_type": {
                    "type": "string",
                    "description": "Worker sector type"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region"
                },
                "loan_amount_kes": {
                    "type": "number",
                    "description": "Requested loan amount in KES"
                },
                "loan_purpose": {
                    "type": "string",
                    "description": "Purpose of the loan (e.g., 'inventory', 'equipment', 'expansion')"
                }
            }),
            required: Some(vec!["cohort_hash".to_string(), "worker_type".to_string(), "region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: true,
        risk_level: ToolRiskLevel::High,
        timeout_secs: 30,
        read_only: false,
    }
}

fn credit_batch_score() -> ToolDefinition {
    ToolDefinition {
        name: "credit_batch_score".to_string(),
        description: "Batch compute credit scores for multiple cohorts at once. Used for portfolio analysis, bulk lending decisions, or market-wide risk assessment.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hashes": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "List of cohort hashes to score",
                    "maxItems": 100
                },
                "worker_type_filter": {
                    "type": "string",
                    "description": "Optional filter by worker type"
                },
                "region_filter": {
                    "type": "string",
                    "description": "Optional filter by region"
                }
            }),
            required: Some(vec!["cohort_hashes".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 60,
        read_only: true,
    }
}

fn credit_cohort_analysis() -> ToolDefinition {
    ToolDefinition {
        name: "credit_cohort_analysis".to_string(),
        description: "Analyze a specific worker cohort: size, transaction patterns, revenue distribution, peer ranking, seasonal behavior, and growth trajectory.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "Cohort identifier hash"
                },
                "analysis_depth": {
                    "type": "string",
                    "enum": ["summary", "standard", "deep"],
                    "description": "Depth of analysis (default: standard)"
                }
            }),
            required: Some(vec!["cohort_hash".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 20,
        read_only: true,
    }
}

fn credit_default_predict() -> ToolDefinition {
    ToolDefinition {
        name: "credit_default_predict".to_string(),
        description: "Predict default probability for a cohort using logistic regression model with transaction features, seasonal adjustment, and market context.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "Cohort identifier hash"
                },
                "loan_amount_kes": {
                    "type": "number",
                    "description": "Loan amount for affordability analysis"
                },
                "repayment_period_weeks": {
                    "type": "integer",
                    "description": "Proposed repayment period in weeks",
                    "minimum": 1,
                    "maximum": 52
                }
            }),
            required: Some(vec!["cohort_hash".to_string(), "loan_amount_kes".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 15,
        read_only: true,
    }
}

fn credit_seasonality_adjust() -> ToolDefinition {
    ToolDefinition {
        name: "credit_seasonality_adjust".to_string(),
        description: "Apply seasonal adjustment to credit metrics based on worker type and region. Accounts for harvest cycles, holiday effects, and regional economic patterns.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "worker_type": {
                    "type": "string",
                    "description": "Worker sector type"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region"
                },
                "metric_value": {
                    "type": "number",
                    "description": "Raw metric value to adjust"
                },
                "metric_type": {
                    "type": "string",
                    "enum": ["revenue", "transactions", "credit_score", "default_rate"],
                    "description": "Type of metric being adjusted"
                },
                "current_month": {
                    "type": "integer",
                    "description": "Current month (1-12) for seasonal calculation",
                    "minimum": 1,
                    "maximum": 12
                }
            }),
            required: Some(vec!["worker_type".to_string(), "region".to_string(), "metric_value".to_string(), "metric_type".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Credit,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 5,
        read_only: true,
    }
}

fn market_analysis() -> ToolDefinition {
    ToolDefinition {
        name: "market_analysis".to_string(),
        description: "Comprehensive market analysis for a product category in a region. Returns price trends, demand signals, supply status, opportunities, and risks.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "category": {
                    "type": "string",
                    "description": "Product category (e.g., 'tomatoes', 'maize', 'electronics')"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region"
                },
                "timeframe_days": {
                    "type": "integer",
                    "description": "Analysis timeframe in days (default: 30)",
                    "minimum": 1,
                    "maximum": 365
                }
            }),
            required: Some(vec!["category".to_string(), "region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Market,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 15,
        read_only: true,
    }
}

fn market_price_lookup() -> ToolDefinition {
    ToolDefinition {
        name: "market_price_lookup".to_string(),
        description: "Look up current and historical prices for a product in a region. Returns price series, volatility metrics, and comparison to regional averages.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "category": {
                    "type": "string",
                    "description": "Product category"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region"
                },
                "days_back": {
                    "type": "integer",
                    "description": "Days of price history (default: 30)",
                    "minimum": 1,
                    "maximum": 365
                }
            }),
            required: Some(vec!["category".to_string(), "region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Market,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 10,
        read_only: true,
    }
}

fn market_demand_forecast() -> ToolDefinition {
    ToolDefinition {
        name: "market_demand_forecast".to_string(),
        description: "Forecast demand for a product category using historical transaction patterns, day-of-week seasonality, and trend analysis. Returns daily predictions with confidence intervals.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "category": {
                    "type": "string",
                    "description": "Product category to forecast"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region"
                },
                "horizon_days": {
                    "type": "integer",
                    "description": "Forecast horizon in days (default: 14)",
                    "minimum": 1,
                    "maximum": 90
                }
            }),
            required: Some(vec!["category".to_string(), "region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Market,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 20,
        read_only: true,
    }
}

fn market_trend_detect() -> ToolDefinition {
    ToolDefinition {
        name: "market_trend_detect".to_string(),
        description: "Detect emerging market trends across categories and regions. Identifies rising/falling prices, volume spikes, and cross-category correlations.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "region": {
                    "type": "string",
                    "description": "Geographic region to analyze"
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum trend confidence threshold (0.0-1.0, default: 0.6)",
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "categories": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Specific categories to analyze (empty = all)"
                }
            }),
            required: Some(vec!["region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Market,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 30,
        read_only: true,
    }
}

fn market_opportunity_scan() -> ToolDefinition {
    ToolDefinition {
        name: "market_opportunity_scan".to_string(),
        description: "Scan for market opportunities: underserved categories, price arbitrage, seasonal windows, and supply gaps. Prioritized by estimated impact.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "region": {
                    "type": "string",
                    "description": "Geographic region to scan"
                },
                "worker_type": {
                    "type": "string",
                    "description": "Worker type to tailor opportunities for (optional)"
                },
                "min_impact": {
                    "type": "number",
                    "description": "Minimum estimated impact score (0.0-1.0, default: 0.3)",
                    "minimum": 0.0,
                    "maximum": 1.0
                }
            }),
            required: Some(vec!["region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Market,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 20,
        read_only: true,
    }
}

fn market_competitor_analysis() -> ToolDefinition {
    ToolDefinition {
        name: "market_competitor_analysis".to_string(),
        description: "Analyze competitive landscape for a product category: market concentration, pricing strategies, distribution patterns, and market share estimates.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "category": {
                    "type": "string",
                    "description": "Product category"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region"
                }
            }),
            required: Some(vec!["category".to_string(), "region".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Market,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 20,
        read_only: true,
    }
}

fn intelligence_report_generate() -> ToolDefinition {
    ToolDefinition {
        name: "intelligence_report_generate".to_string(),
        description: "Generate a comprehensive intelligence report combining market analysis, credit trends, anomaly summary, and actionable recommendations. Available types: daily_brief, weekly_deep_dive, market_pulse, risk_alert.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "report_type": {
                    "type": "string",
                    "enum": ["daily_brief", "weekly_deep_dive", "market_pulse", "risk_alert"],
                    "description": "Type of report to generate"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic focus (optional, default: all regions)"
                },
                "categories": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Product categories to include (optional, default: all)"
                }
            }),
            required: Some(vec!["report_type".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Intelligence,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 60,
        read_only: true,
    }
}

fn intelligence_anomaly_detect() -> ToolDefinition {
    ToolDefinition {
        name: "intelligence_anomaly_detect".to_string(),
        description: "Detect anomalies in transaction patterns, price movements, or credit behavior. Returns severity-ranked anomalies with context and recommended actions.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "scope": {
                    "type": "string",
                    "enum": ["transactions", "prices", "credit", "all"],
                    "description": "What to scan for anomalies (default: all)"
                },
                "region": {
                    "type": "string",
                    "description": "Geographic region (optional)"
                },
                "sensitivity": {
                    "type": "number",
                    "description": "Detection sensitivity 0.0-1.0 (default: 0.7)",
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "lookback_hours": {
                    "type": "integer",
                    "description": "Hours of data to analyze (default: 24)",
                    "minimum": 1,
                    "maximum": 168
                }
            }),
            required: Some(vec!["scope".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Intelligence,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 30,
        read_only: true,
    }
}

fn intelligence_pattern_mine() -> ToolDefinition {
    ToolDefinition {
        name: "intelligence_pattern_mine".to_string(),
        description: "Mine cross-dimensional patterns in transaction, market, and credit data. Discovers correlations, causal relationships, and predictive signals across data dimensions.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "dimensions": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Data dimensions to analyze (e.g., ['category', 'region', 'time'])"
                },
                "min_strength": {
                    "type": "number",
                    "description": "Minimum pattern strength (0.0-1.0, default: 0.5)",
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "max_patterns": {
                    "type": "integer",
                    "description": "Maximum patterns to return (default: 20)",
                    "minimum": 1,
                    "maximum": 100
                }
            }),
            required: Some(vec!["dimensions".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Intelligence,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 45,
        read_only: true,
    }
}

fn intelligence_knowledge_query() -> ToolDefinition {
    ToolDefinition {
        name: "intelligence_knowledge_query".to_string(),
        description: "Query the knowledge graph for relationships, facts, and derived insights. Supports natural language queries about market entities, worker cohorts, and economic indicators.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "query": {
                    "type": "string",
                    "description": "Natural language query about the knowledge graph"
                },
                "entity_type": {
                    "type": "string",
                    "enum": ["cohort", "product", "region", "market", "indicator"],
                    "description": "Filter by entity type (optional)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10)",
                    "minimum": 1,
                    "maximum": 50
                }
            }),
            required: Some(vec!["query".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Intelligence,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 15,
        read_only: true,
    }
}

fn data_transaction_query() -> ToolDefinition {
    ToolDefinition {
        name: "data_transaction_query".to_string(),
        description: "Query anonymized transaction data with filters. Returns aggregated transaction metrics (never individual transactions). Supports grouping by category, region, time period.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "Cohort identifier (optional)"
                },
                "region": {
                    "type": "string",
                    "description": "Region filter (optional)"
                },
                "category": {
                    "type": "string",
                    "description": "Transaction category filter (optional)"
                },
                "date_from": {
                    "type": "string",
                    "description": "Start date ISO-8601 (optional)"
                },
                "date_to": {
                    "type": "string",
                    "description": "End date ISO-8601 (optional)"
                },
                "group_by": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Group results by dimensions (e.g., ['day', 'category'])"
                }
            }),
            required: Some(vec![]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Data,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 15,
        read_only: true,
    }
}

fn data_cohort_lookup() -> ToolDefinition {
    ToolDefinition {
        name: "data_cohort_lookup".to_string(),
        description: "Look up cohort metadata: size, worker type distribution, geographic spread, activity level, and k-anonymity compliance status.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "cohort_hash": {
                    "type": "string",
                    "description": "Cohort identifier hash"
                },
                "include_members": {
                    "type": "boolean",
                    "description": "Include member count details (default: false, k-anonymity permitting)"
                }
            }),
            required: Some(vec!["cohort_hash".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Data,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 10,
        read_only: true,
    }
}

fn data_aggregate() -> ToolDefinition {
    ToolDefinition {
        name: "data_aggregate".to_string(),
        description: "Run aggregation queries across the data warehouse. Supports sum, avg, count, percentile calculations with flexible grouping and filtering.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "table": {
                    "type": "string",
                    "enum": ["transactions", "credit_scores", "market_prices", "worker_cohorts"],
                    "description": "Table to aggregate"
                },
                "metric": {
                    "type": "string",
                    "enum": ["count", "sum", "avg", "min", "max", "percentile_50", "percentile_90", "percentile_99"],
                    "description": "Aggregation function"
                },
                "field": {
                    "type": "string",
                    "description": "Field to aggregate (e.g., 'amount_kes', 'alama_score')"
                },
                "filters": {
                    "type": "object",
                    "description": "Filter conditions as key-value pairs"
                },
                "group_by": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Fields to group by"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum result rows (default: 100)",
                    "minimum": 1,
                    "maximum": 1000
                }
            }),
            required: Some(vec!["table".to_string(), "metric".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Data,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 20,
        read_only: true,
    }
}

fn data_export() -> ToolDefinition {
    ToolDefinition {
        name: "data_export".to_string(),
        description: "Export aggregated data in CSV or JSON format. Only exports anonymized, k-anonymity-compliant data. Maximum 10,000 rows per export.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "query": {
                    "type": "object",
                    "description": "Query specification (table, filters, fields)"
                },
                "format": {
                    "type": "string",
                    "enum": ["csv", "json"],
                    "description": "Export format (default: json)"
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Maximum rows to export (default: 1000, max: 10000)",
                    "minimum": 1,
                    "maximum": 10000
                }
            }),
            required: Some(vec!["query".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Data,
        requires_approval: false,
        risk_level: ToolRiskLevel::Medium,
        timeout_secs: 30,
        read_only: true,
    }
}

fn federated_status() -> ToolDefinition {
    ToolDefinition {
        name: "federated_status".to_string(),
        description: "Get federated learning system status: active nodes, current round, model version, privacy budget, and participating cohorts.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({}),
            required: Some(vec![]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Federated,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 5,
        read_only: true,
    }
}

fn federated_trigger_round() -> ToolDefinition {
    ToolDefinition {
        name: "federated_trigger_round".to_string(),
        description: "Trigger a new federated learning round. Initiates model training across participating nodes with current data. Requires human approval.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "model_type": {
                    "type": "string",
                    "enum": ["credit_scoring", "demand_forecast", "anomaly_detection"],
                    "description": "Type of model to train"
                },
                "participating_regions": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Regions to include (empty = all)"
                },
                "privacy_epsilon": {
                    "type": "number",
                    "description": "Differential privacy epsilon (default: 1.0)",
                    "minimum": 0.1,
                    "maximum": 10.0
                }
            }),
            required: Some(vec!["model_type".to_string()]),
            additional_properties: Some(false),
        },
        category: ToolCategory::Federated,
        requires_approval: true,
        risk_level: ToolRiskLevel::Critical,
        timeout_secs: 300,
        read_only: false,
    }
}

fn system_health_check() -> ToolDefinition {
    ToolDefinition {
        name: "system_health_check".to_string(),
        description: "Check system health: database connectivity, cache status, LLM provider availability, circuit breaker states, and resource utilization.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "component": {
                    "type": "string",
                    "enum": ["database", "cache", "llm", "circuit_breakers", "all"],
                    "description": "Specific component to check (default: all)"
                }
            }),
            required: Some(vec![]),
            additional_properties: Some(false),
        },
        category: ToolCategory::System,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 10,
        read_only: true,
    }
}

fn system_model_status() -> ToolDefinition {
    ToolDefinition {
        name: "system_model_status".to_string(),
        description: "Get ML model status: version, last training date, performance metrics, drift detection status, and next scheduled retrain.".to_string(),
        parameters: ToolParameterSchema {
            schema_type: "object".to_string(),
            properties: serde_json::json!({
                "model_name": {
                    "type": "string",
                    "description": "Specific model to query (optional, returns all if omitted)"
                }
            }),
            required: Some(vec![]),
            additional_properties: Some(false),
        },
        category: ToolCategory::System,
        requires_approval: false,
        risk_level: ToolRiskLevel::Low,
        timeout_secs: 10,
        read_only: true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_all_26_tools_defined() {
        let tools = build_all_tool_definitions();
        assert_eq!(tools.len(), 26, "Expected 26 tools, got {}", tools.len());
    }

    #[test]
    fn test_unique_tool_names() {
        let tools = build_all_tool_definitions();
        let names: Vec<&str> = tools.iter().map(|t| t.name.as_str()).collect();
        let unique: std::collections::HashSet<&str> = names.iter().copied().collect();
        assert_eq!(names.len(), unique.len(), "Duplicate tool names found");
    }

    #[test]
    fn test_openai_function_format() {
        let registry = ToolRegistry::new();
        let tools = build_all_tool_definitions();
        for def in tools {
            registry.register(def, Arc::new(NoOpExecutor));
        }
        let functions = registry.openai_functions();
        assert_eq!(functions.len(), 26);
        for f in &functions {
            assert_eq!(f["type"], "function");
            assert!(f["function"]["name"].is_string());
            assert!(f["function"]["description"].is_string());
            assert!(f["function"]["parameters"].is_object());
        }
    }

    /// No-op executor for testing
    struct NoOpExecutor;
    #[async_trait]
    impl ToolExecutor for NoOpExecutor {
        async fn execute(&self, _: serde_json::Value) -> Result<serde_json::Value, ToolError> {
            Ok(serde_json::json!({"status": "noop"}))
        }
        fn validate_input(&self, _: &serde_json::Value) -> Result<(), ToolError> {
            Ok(())
        }
        fn name(&self) -> &str {
            "noop"
        }
    }
}
