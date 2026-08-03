// =============================================================================
// Angavu Intelligence — Autonomous OODA Agent
// LLM-driven agent that extends the OODA loop with autonomous reasoning.
//
// Architecture: ReAct Pattern (Reason → Act → Observe → Reflect)
//
//   ┌─────────────────────────────────────────────────────────────┐
//   │                    Autonomous Agent                          │
//   │                                                             │
//   │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐│
//   │  │  OBSERVE  │──→│  ORIENT  │──→│  DECIDE  │──→│   ACT    ││
//   │  │ (gather)  │   │ (reason) │   │ (select) │   │ (execute)││
//   │  └──────────┘   └──────────┘   └──────────┘   └──────────┘│
//   │       ↑                                          │         │
//   │       └──────────────────────────────────────────┘         │
//   │                    (ReAct loop)                             │
//   │                                                             │
//   │  Circuit Breaker → Max Iterations → Graceful Degradation   │
//   └─────────────────────────────────────────────────────────────┘
//
// The agent uses the LLM for reasoning in the Orient phase, tool selection
// in the Decide phase, and tool execution in the Act phase. Each cycle
// builds on observations from previous cycles via the memory system.
// =============================================================================

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, error, info, warn};

use super::function_calling::{
    ChatCompletionResponse, ChatMessage, FunctionCallParser, FunctionCallingEngine, LlmAction,
    ParsedFunctionCall, SystemPromptBuilder, ToolCallResult, ToolChoice, ToolEnabledRequest,
};
use super::memory::{AgentMemory, MemoryConfig, WorkingMemory};
use super::tool_registry::{ToolRegistry, ToolResult};

// ── Agent Configuration ──────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct AgentConfig {
    /// Maximum ReAct iterations per task
    pub max_iterations: usize,
    /// Maximum tool calls per iteration (parallel execution)
    pub max_tool_calls_per_iteration: usize,
    /// Circuit breaker: consecutive failures before stopping
    pub circuit_breaker_threshold: usize,
    /// Seconds to wait before retrying after circuit open
    pub circuit_breaker_recovery_secs: u64,
    /// Token budget per task
    pub token_budget: usize,
    /// Model to use for reasoning
    pub reasoning_model: String,
    /// Model to use for tool selection (can be faster/cheaper)
    pub tool_selection_model: String,
    /// Temperature for reasoning (lower = more deterministic)
    pub reasoning_temperature: f32,
    /// Temperature for tool selection
    pub tool_selection_temperature: f32,
    /// Whether to enable parallel tool execution
    pub parallel_tools: bool,
    /// Task timeout in seconds
    pub task_timeout_secs: u64,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            max_iterations: 10,
            max_tool_calls_per_iteration: 5,
            circuit_breaker_threshold: 3,
            circuit_breaker_recovery_secs: 60,
            token_budget: 100_000,
            reasoning_model: "deepseek-chat".to_string(),
            tool_selection_model: "deepseek-chat".to_string(),
            reasoning_temperature: 0.3,
            tool_selection_temperature: 0.1,
            parallel_tools: true,
            task_timeout_secs: 300, // 5 minutes
        }
    }
}

// ── Agent State ──────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentState {
    /// Agent is idle, waiting for a task
    Idle,
    /// Agent is actively processing a task
    Running,
    /// Agent is waiting for human approval
    AwaitingApproval,
    /// Agent completed the task successfully
    Completed,
    /// Agent hit the iteration limit
    MaxIterationsReached,
    /// Agent circuit breaker tripped
    CircuitOpen,
    /// Agent encountered an unrecoverable error
    Failed,
}

// ── Task Types ───────────────────────────────────────────────────────────────

/// Types of autonomous tasks the agent can perform
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AgentTask {
    /// Analyze credit risk for a cohort
    CreditAnalysis {
        cohort_hash: String,
        worker_type: String,
        region: String,
        loan_amount: Option<f64>,
    },
    /// Market intelligence gathering
    MarketIntelligence {
        category: String,
        region: String,
        depth: AnalysisDepth,
    },
    /// Generate an intelligence report
    IntelligenceReport {
        report_type: String,
        scope: ReportScope,
    },
    /// Investigate an anomaly
    AnomalyInvestigation {
        anomaly_description: String,
        scope: String,
    },
    /// General-purpose query (free-form)
    GeneralQuery { query: String },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AnalysisDepth {
    Quick,
    Standard,
    Deep,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReportScope {
    pub region: Option<String>,
    pub categories: Vec<String>,
    pub timeframe_days: Option<i32>,
}

/// Result of an agent task execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentResult {
    pub task: AgentTask,
    pub state: AgentState,
    pub final_response: String,
    pub iterations_used: usize,
    pub tool_calls_made: usize,
    pub total_execution_ms: u64,
    pub reasoning_trace: Vec<ReasoningTraceEntry>,
    pub observations: Vec<String>,
    pub confidence: f64,
    pub memory_snapshot: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReasoningTraceEntry {
    pub iteration: usize,
    pub phase: String,
    pub thought: String,
    pub action: Option<String>,
    pub observation: Option<String>,
    pub timestamp: DateTime<Utc>,
}

// ── Autonomous Agent ─────────────────────────────────────────────────────────

/// The autonomous OODA agent — LLM-driven reasoning with tool use
pub struct AutonomousAgent {
    config: AgentConfig,
    engine: Arc<FunctionCallingEngine>,
    memory: Arc<AgentMemory>,
    state: RwLock<AgentState>,
    /// LLM client for making API calls
    llm_client: Arc<LlmClientAdapter>,
    // Metrics
    tasks_completed: AtomicU64,
    tasks_failed: AtomicU64,
    total_iterations: AtomicU64,
    total_tool_calls: AtomicU64,
}

/// Adapter to bridge with the existing LLM client
pub struct LlmClientAdapter {
    http: reqwest::Client,
    api_key: Option<String>,
    base_url: String,
}

impl LlmClientAdapter {
    pub fn new(api_key: Option<String>, base_url: String) -> Self {
        Self {
            http: reqwest::Client::new(),
            api_key,
            base_url,
        }
    }

    /// Call the LLM API with tools
    pub async fn chat_completion(
        &self,
        model: &str,
        messages: &[serde_json::Value],
        tools: &[serde_json::Value],
        temperature: f32,
    ) -> Result<ChatCompletionResponse, AgentError> {
        let api_key = self
            .api_key
            .as_ref()
            .ok_or_else(|| AgentError::LlmUnavailable("No API key configured".to_string()))?;

        let url = format!("{}/chat/completions", self.base_url);

        let body = serde_json::json!({
            "model": model,
            "messages": messages,
            "tools": if tools.is_empty() { serde_json::Value::Null } else { serde_json::json!(tools) },
            "temperature": temperature,
            "max_tokens": 4096,
        });

        let response = self
            .http
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await
            .map_err(|e| AgentError::LlmUnavailable(format!("HTTP error: {}", e)))?;

        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(AgentError::LlmUnavailable(format!(
                "LLM API error {}: {}",
                status, body
            )));
        }

        response
            .json::<ChatCompletionResponse>()
            .await
            .map_err(|e| AgentError::LlmUnavailable(format!("Parse error: {}", e)))
    }
}

impl AutonomousAgent {
    pub fn new(
        config: AgentConfig,
        registry: Arc<ToolRegistry>,
        llm_client: Arc<LlmClientAdapter>,
    ) -> Self {
        let engine = Arc::new(FunctionCallingEngine::new(
            registry.clone(),
            config.max_iterations,
        ));
        let memory = Arc::new(AgentMemory::new(MemoryConfig {
            token_budget_per_task: config.token_budget,
            ..Default::default()
        }));

        Self {
            config,
            engine,
            memory,
            state: RwLock::new(AgentState::Idle),
            llm_client,
            tasks_completed: AtomicU64::new(0),
            tasks_failed: AtomicU64::new(0),
            total_iterations: AtomicU64::new(0),
            total_tool_calls: AtomicU64::new(0),
        }
    }

    /// Execute an autonomous task using the ReAct pattern
    pub async fn execute_task(&self, task: AgentTask) -> AgentResult {
        let start = std::time::Instant::now();
        let mut reasoning_trace: Vec<ReasoningTraceEntry> = Vec::new();
        let mut observations: Vec<String> = Vec::new();
        let mut tool_calls_count: usize = 0;

        // Set state
        *self.state.write().await = AgentState::Running;

        // Reset memory for new task
        let task_description = Self::task_to_description(&task);
        self.memory.reset_for_new_task(&task_description).await;

        // Build system prompt with tool definitions
        let tools = self.engine.registry().openai_functions();
        let context = self.memory.full_context().await;
        let system_prompt = SystemPromptBuilder::build(self.engine.registry(), Some(&context));

        // Initialize conversation
        self.memory.short_term.add("system", &system_prompt).await;

        // Build the initial user prompt from the task
        let user_prompt = Self::build_initial_prompt(&task);
        self.memory.short_term.add("user", &user_prompt).await;

        // ── ReAct Loop ──────────────────────────────────────────────────
        let mut circuit_failures: usize = 0;
        let mut final_response = String::new();

        for iteration in 0..self.config.max_iterations {
            // Check circuit breaker
            if circuit_failures >= self.config.circuit_breaker_threshold {
                warn!(
                    "Circuit breaker open after {} consecutive failures",
                    circuit_failures
                );
                *self.state.write().await = AgentState::CircuitOpen;
                final_response =
                    "Agent stopped: too many consecutive tool failures. Please retry later."
                        .to_string();
                break;
            }

            // Update working memory
            self.memory
                .working
                .add_reasoning_step(&format!("Iteration {} starting", iteration + 1), None)
                .await;

            // ── ORIENT (LLM Reasoning) ──────────────────────────────────
            let messages = self.memory.short_term.as_messages().await;

            let llm_result = self
                .llm_client
                .chat_completion(
                    &self.config.reasoning_model,
                    &messages,
                    &tools,
                    self.config.reasoning_temperature,
                )
                .await;

            let response = match llm_result {
                Ok(r) => r,
                Err(e) => {
                    error!("LLM call failed: {}", e);
                    circuit_failures += 1;
                    reasoning_trace.push(ReasoningTraceEntry {
                        iteration,
                        phase: "orient".to_string(),
                        thought: format!("LLM call failed: {}", e),
                        action: None,
                        observation: None,
                        timestamp: Utc::now(),
                    });
                    continue;
                }
            };

            // Reset circuit on success
            circuit_failures = 0;

            // ── DECIDE (Parse LLM Action) ───────────────────────────────
            let action = FunctionCallParser::parse(&response);

            match action {
                LlmAction::ToolCalls(calls) => {
                    // LLM wants to use tools
                    let assistant_content = response
                        .choices
                        .first()
                        .and_then(|c| c.message.content.clone())
                        .unwrap_or_default();

                    // Record assistant message with tool calls
                    self.memory
                        .short_term
                        .add_assistant_with_tools(&assistant_content)
                        .await;

                    reasoning_trace.push(ReasoningTraceEntry {
                        iteration,
                        phase: "decide".to_string(),
                        thought: assistant_content.clone(),
                        action: Some(format!(
                            "Calling {} tools: {}",
                            calls.len(),
                            calls
                                .iter()
                                .map(|c| c.tool_name.as_str())
                                .collect::<Vec<_>>()
                                .join(", ")
                        )),
                        observation: None,
                        timestamp: Utc::now(),
                    });

                    // Limit tool calls per iteration
                    let calls_to_execute: Vec<_> = calls
                        .into_iter()
                        .take(self.config.max_tool_calls_per_iteration)
                        .collect();

                    // ── ACT (Execute Tools) ─────────────────────────────
                    let results = if self.config.parallel_tools {
                        self.engine.execute_calls(&calls_to_execute).await
                    } else {
                        let mut results = Vec::new();
                        for call in &calls_to_execute {
                            results.push(self.engine.execute_call(call).await);
                        }
                        results
                    };

                    tool_calls_count += results.len();

                    // Process results and add to conversation
                    for result in &results {
                        let tool_msg = FunctionCallingEngine::build_tool_result_message(result);
                        self.memory
                            .short_term
                            .add_tool_result(
                                &result.tool_call_id,
                                &result.tool_name,
                                tool_msg.content.as_deref().unwrap_or(""),
                            )
                            .await;

                        // Add to working memory observations
                        let obs_content = if result.success {
                            format!(
                                "[{}] {}",
                                result.tool_name,
                                serde_json::to_string(&result.output).unwrap_or_default()
                            )
                        } else {
                            format!(
                                "[{}] Error: {}",
                                result.tool_name,
                                result.error_message.as_deref().unwrap_or("unknown")
                            )
                        };
                        observations.push(obs_content.clone());
                        self.memory
                            .working
                            .add_observation(
                                &result.tool_name,
                                &obs_content,
                                Some(&result.tool_name),
                            )
                            .await;

                        reasoning_trace.push(ReasoningTraceEntry {
                            iteration,
                            phase: "act".to_string(),
                            thought: format!("Executed {}", result.tool_name),
                            action: Some(format!("{}({})", result.tool_name, result.tool_call_id)),
                            observation: Some(if result.success {
                                format!("Success ({}ms)", result.execution_ms)
                            } else {
                                format!(
                                    "Failed: {}",
                                    result.error_message.as_deref().unwrap_or("unknown")
                                )
                            }),
                            timestamp: Utc::now(),
                        });
                    }

                    // Check for any critical failures
                    let failures = results.iter().filter(|r| !r.success).count();
                    if failures == results.len() && !results.is_empty() {
                        circuit_failures += 1;
                    }
                }

                LlmAction::FinalResponse(text) => {
                    // LLM produced a final answer — task complete
                    final_response = text.clone();
                    self.memory.short_term.add("assistant", &text).await;

                    reasoning_trace.push(ReasoningTraceEntry {
                        iteration,
                        phase: "reflect".to_string(),
                        thought: text.clone(),
                        action: None,
                        observation: Some("Final response generated".to_string()),
                        timestamp: Utc::now(),
                    });

                    self.memory
                        .working
                        .record_decision("final_response", &text, 0.8)
                        .await;

                    *self.state.write().await = AgentState::Completed;
                    break;
                }

                LlmAction::Empty => {
                    warn!("LLM returned empty response at iteration {}", iteration);
                    reasoning_trace.push(ReasoningTraceEntry {
                        iteration,
                        phase: "orient".to_string(),
                        thought: "LLM returned empty response".to_string(),
                        action: None,
                        observation: None,
                        timestamp: Utc::now(),
                    });

                    // Nudge the LLM to respond
                    self.memory
                        .short_term
                        .add(
                            "user",
                            "Please continue your analysis and provide a response.",
                        )
                        .await;
                }
            }

            self.total_iterations.fetch_add(1, Ordering::Relaxed);
        }

        // Handle max iterations
        if final_response.is_empty() {
            let current_state = *self.state.read().await;
            if current_state == AgentState::Running {
                *self.state.write().await = AgentState::MaxIterationsReached;
                final_response = format!(
                    "Analysis reached maximum iterations ({}). Partial results from {} tool calls:\n\n{}",
                    self.config.max_iterations,
                    tool_calls_count,
                    observations.join("\n")
                );
            }
        }

        let elapsed = start.elapsed().as_millis() as u64;

        // Update metrics
        let state = *self.state.read().await;
        match state {
            AgentState::Completed => {
                self.tasks_completed.fetch_add(1, Ordering::Relaxed);
            }
            _ => {
                self.tasks_failed.fetch_add(1, Ordering::Relaxed);
            }
        }
        self.total_tool_calls
            .fetch_add(tool_calls_count as u64, Ordering::Relaxed);

        // Store successful strategy in long-term memory
        if state == AgentState::Completed && tool_calls_count > 0 {
            let tools_used: Vec<String> = reasoning_trace
                .iter()
                .filter_map(|t| {
                    t.action
                        .as_ref()
                        .filter(|a| !a.starts_with("Calling"))
                        .cloned()
                })
                .collect();

            if !tools_used.is_empty() {
                self.memory
                    .long_term
                    .store_strategy(super::memory::SuccessfulStrategy {
                        id: format!("strat_{}", Utc::now().timestamp()),
                        task_type: Self::task_type_name(&task),
                        strategy_description: format!(
                            "Completed with {} iterations, {} tool calls",
                            reasoning_trace.len(),
                            tool_calls_count
                        ),
                        tools_used,
                        reasoning_pattern: "ReAct".to_string(),
                        success_count: 1,
                        failure_count: 0,
                        avg_confidence: 0.8,
                        last_used: Utc::now(),
                    });
            }
        }

        info!(
            task = %task_description,
            state = ?state,
            iterations = reasoning_trace.len(),
            tool_calls = tool_calls_count,
            elapsed_ms = elapsed,
            "Agent task completed"
        );

        AgentResult {
            task,
            state,
            final_response,
            iterations_used: reasoning_trace.len(),
            tool_calls_made: tool_calls_count,
            total_execution_ms: elapsed,
            reasoning_trace,
            observations,
            confidence: if state == AgentState::Completed {
                0.85
            } else {
                0.5
            },
            memory_snapshot: self.memory.stats().await,
        }
    }

    /// Get current agent state
    pub async fn state(&self) -> AgentState {
        *self.state.read().await
    }

    /// Get agent metrics
    pub fn metrics(&self) -> AgentMetrics {
        AgentMetrics {
            tasks_completed: self.tasks_completed.load(Ordering::Relaxed),
            tasks_failed: self.tasks_failed.load(Ordering::Relaxed),
            total_iterations: self.total_iterations.load(Ordering::Relaxed),
            total_tool_calls: self.total_tool_calls.load(Ordering::Relaxed),
        }
    }

    /// Access memory for inspection/debugging
    pub fn memory(&self) -> &Arc<AgentMemory> {
        &self.memory
    }

    // ── Private Helpers ─────────────────────────────────────────────────

    fn task_to_description(task: &AgentTask) -> String {
        match task {
            AgentTask::CreditAnalysis {
                cohort_hash,
                worker_type,
                region,
                ..
            } => {
                format!(
                    "Credit analysis for {} cohort {} in {}",
                    worker_type,
                    &cohort_hash[..8],
                    region
                )
            }
            AgentTask::MarketIntelligence {
                category, region, ..
            } => {
                format!("Market intelligence: {} in {}", category, region)
            }
            AgentTask::IntelligenceReport { report_type, scope } => {
                format!("Generate {} report for {:?}", report_type, scope.region)
            }
            AgentTask::AnomalyInvestigation {
                anomaly_description,
                scope,
            } => {
                format!("Investigate anomaly: {} ({})", anomaly_description, scope)
            }
            AgentTask::GeneralQuery { query } => {
                format!("Query: {}", query)
            }
        }
    }

    fn task_type_name(task: &AgentTask) -> String {
        match task {
            AgentTask::CreditAnalysis { .. } => "credit_analysis".to_string(),
            AgentTask::MarketIntelligence { .. } => "market_intelligence".to_string(),
            AgentTask::IntelligenceReport { .. } => "intelligence_report".to_string(),
            AgentTask::AnomalyInvestigation { .. } => "anomaly_investigation".to_string(),
            AgentTask::GeneralQuery { .. } => "general_query".to_string(),
        }
    }

    fn build_initial_prompt(task: &AgentTask) -> String {
        match task {
            AgentTask::CreditAnalysis {
                cohort_hash,
                worker_type,
                region,
                loan_amount,
            } => {
                let mut prompt = format!(
                    "Perform a comprehensive credit risk analysis for the following:\n\n\
                     - Cohort: {}\n\
                     - Worker type: {}\n\
                     - Region: {}\n",
                    cohort_hash, worker_type, region
                );
                if let Some(amount) = loan_amount {
                    prompt.push_str(&format!("- Proposed loan amount: KES {}\n", amount));
                }
                prompt.push_str("\nSteps:\n");
                prompt.push_str("1. Compute the current credit score\n");
                prompt.push_str("2. Retrieve score history for trend analysis\n");
                prompt.push_str("3. Perform deep risk assessment\n");
                prompt.push_str("4. Check market conditions in the region\n");
                prompt.push_str("5. Provide a credit decision recommendation with reasoning\n");
                prompt
            }
            AgentTask::MarketIntelligence {
                category,
                region,
                depth,
            } => {
                format!(
                    "Conduct {:?}-depth market intelligence analysis:\n\n\
                     - Category: {}\n\
                     - Region: {}\n\n\
                     Steps:\n\
                     1. Analyze current market conditions\n\
                     2. Look up price data and trends\n\
                     3. Generate demand forecast\n\
                     4. Detect emerging trends\n\
                     5. Scan for opportunities\n\
                     6. Synthesize findings into actionable intelligence",
                    depth, category, region
                )
            }
            AgentTask::IntelligenceReport { report_type, scope } => {
                let mut prompt = format!("Generate a {} intelligence report.\n\n", report_type);
                if let Some(ref region) = scope.region {
                    prompt.push_str(&format!("Region: {}\n", region));
                }
                if !scope.categories.is_empty() {
                    prompt.push_str(&format!("Categories: {}\n", scope.categories.join(", ")));
                }
                prompt.push_str("\nSteps:\n");
                prompt.push_str("1. Detect anomalies in the relevant scope\n");
                prompt.push_str("2. Mine patterns across dimensions\n");
                prompt.push_str("3. Check system and model health\n");
                prompt.push_str("4. Generate the report with findings and recommendations\n");
                prompt
            }
            AgentTask::AnomalyInvestigation {
                anomaly_description,
                scope,
            } => {
                format!(
                    "Investigate the following anomaly:\n\n\
                     Description: {}\n\
                     Scope: {}\n\n\
                     Steps:\n\
                     1. Query recent transaction data for the affected area\n\
                     2. Check market conditions that might explain the anomaly\n\
                     3. Look for correlated patterns across dimensions\n\
                     4. Assess impact and recommend response actions",
                    anomaly_description, scope
                )
            }
            AgentTask::GeneralQuery { query } => {
                format!(
                    "Answer the following query using available intelligence tools:\n\n{}\n\n\
                     Use the most relevant tools to gather data before responding.",
                    query
                )
            }
        }
    }
}

// ── Agent Metrics ────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct AgentMetrics {
    pub tasks_completed: u64,
    pub tasks_failed: u64,
    pub total_iterations: u64,
    pub total_tool_calls: u64,
}

// ── Agent Error ──────────────────────────────────────────────────────────────

#[derive(Debug, thiserror::Error)]
pub enum AgentError {
    #[error("LLM unavailable: {0}")]
    LlmUnavailable(String),
    #[error("Task timeout after {0}s")]
    TaskTimeout(u64),
    #[error("Circuit breaker open")]
    CircuitOpen,
    #[error("Internal error: {0}")]
    Internal(String),
}

// ── Credit Decision Agent (Specialized) ──────────────────────────────────────

/// Specialized agent for credit decisions — the primary use case.
/// Pre-configured with credit-specific prompts and constraints.
pub struct CreditDecisionAgent {
    inner: AutonomousAgent,
}

impl CreditDecisionAgent {
    pub fn new(registry: Arc<ToolRegistry>, llm_client: Arc<LlmClientAdapter>) -> Self {
        let config = AgentConfig {
            max_iterations: 8,
            max_tool_calls_per_iteration: 4,
            reasoning_model: "deepseek-chat".to_string(),
            reasoning_temperature: 0.2, // Lower for financial decisions
            task_timeout_secs: 120,
            ..Default::default()
        };

        Self {
            inner: AutonomousAgent::new(config, registry, llm_client),
        }
    }

    /// Make a credit decision for a cohort
    pub async fn decide(
        &self,
        cohort_hash: &str,
        worker_type: &str,
        region: &str,
        loan_amount: Option<f64>,
    ) -> AgentResult {
        let task = AgentTask::CreditAnalysis {
            cohort_hash: cohort_hash.to_string(),
            worker_type: worker_type.to_string(),
            region: region.to_string(),
            loan_amount,
        };
        self.inner.execute_task(task).await
    }

    /// Access the inner agent
    pub fn agent(&self) -> &AutonomousAgent {
        &self.inner
    }
}

// ── Market Intelligence Agent (Specialized) ──────────────────────────────────

/// Specialized agent for market intelligence gathering
pub struct MarketIntelligenceAgent {
    inner: AutonomousAgent,
}

impl MarketIntelligenceAgent {
    pub fn new(registry: Arc<ToolRegistry>, llm_client: Arc<LlmClientAdapter>) -> Self {
        let config = AgentConfig {
            max_iterations: 10,
            max_tool_calls_per_iteration: 5,
            reasoning_model: "deepseek-chat".to_string(),
            reasoning_temperature: 0.4,
            task_timeout_secs: 180,
            ..Default::default()
        };

        Self {
            inner: AutonomousAgent::new(config, registry, llm_client),
        }
    }

    /// Gather market intelligence for a category/region
    pub async fn analyze(&self, category: &str, region: &str, depth: AnalysisDepth) -> AgentResult {
        let task = AgentTask::MarketIntelligence {
            category: category.to_string(),
            region: region.to_string(),
            depth,
        };
        self.inner.execute_task(task).await
    }

    pub fn agent(&self) -> &AutonomousAgent {
        &self.inner
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agent::tool_registry::{
        ToolCategory, ToolDefinition, ToolError, ToolExecutor, ToolParameterSchema, ToolRiskLevel,
    };
    use async_trait::async_trait;

    struct MockExecutor;
    #[async_trait]
    impl ToolExecutor for MockExecutor {
        async fn execute(&self, input: serde_json::Value) -> Result<serde_json::Value, ToolError> {
            Ok(serde_json::json!({"status": "ok", "input_received": input}))
        }
        fn validate_input(&self, _: &serde_json::Value) -> Result<(), ToolError> {
            Ok(())
        }
        fn name(&self) -> &str {
            "mock"
        }
    }

    fn make_test_registry() -> Arc<ToolRegistry> {
        let registry = ToolRegistry::new();
        registry.register(
            ToolDefinition {
                name: "test_analyze".to_string(),
                description: "Test analysis tool".to_string(),
                parameters: ToolParameterSchema {
                    schema_type: "object".to_string(),
                    properties: serde_json::json!({"query": {"type": "string"}}),
                    required: Some(vec!["query".to_string()]),
                    additional_properties: None,
                },
                category: ToolCategory::Intelligence,
                requires_approval: false,
                risk_level: ToolRiskLevel::Low,
                timeout_secs: 10,
                read_only: true,
            },
            Arc::new(MockExecutor),
        );
        Arc::new(registry)
    }

    #[test]
    fn test_agent_config_default() {
        let config = AgentConfig::default();
        assert_eq!(config.max_iterations, 10);
        assert!(config.parallel_tools);
    }

    #[test]
    fn test_task_description() {
        let task = AgentTask::CreditAnalysis {
            cohort_hash: "abc123def456".to_string(),
            worker_type: "farmer".to_string(),
            region: "nairobi".to_string(),
            loan_amount: Some(50000.0),
        };
        let desc = AutonomousAgent::task_to_description(&task);
        assert!(desc.contains("farmer"));
        assert!(desc.contains("nairobi"));
    }

    #[test]
    fn test_initial_prompt_credit() {
        let task = AgentTask::CreditAnalysis {
            cohort_hash: "abc123".to_string(),
            worker_type: "boda_boda".to_string(),
            region: "mombasa".to_string(),
            loan_amount: Some(25000.0),
        };
        let prompt = AutonomousAgent::build_initial_prompt(&task);
        assert!(prompt.contains("boda_boda"));
        assert!(prompt.contains("KES 25000"));
        assert!(prompt.contains("credit score"));
    }

    #[test]
    fn test_initial_prompt_market() {
        let task = AgentTask::MarketIntelligence {
            category: "tomatoes".to_string(),
            region: "kisumu".to_string(),
            depth: AnalysisDepth::Deep,
        };
        let prompt = AutonomousAgent::build_initial_prompt(&task);
        assert!(prompt.contains("tomatoes"));
        assert!(prompt.contains("kisumu"));
        assert!(prompt.contains("Deep"));
    }

    #[test]
    fn test_agent_metrics_initial() {
        let registry = make_test_registry();
        let llm = Arc::new(LlmClientAdapter::new(None, "http://localhost".to_string()));
        let agent = AutonomousAgent::new(AgentConfig::default(), registry, llm);
        let metrics = agent.metrics();
        assert_eq!(metrics.tasks_completed, 0);
        assert_eq!(metrics.total_tool_calls, 0);
    }
}
