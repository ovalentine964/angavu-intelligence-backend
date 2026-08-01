// =============================================================================
// Angavu Intelligence — Agent Memory System
// Three-tier memory architecture for autonomous agent operation:
//   1. Short-term (conversation context) — current LLM conversation
//   2. Working memory (task state) — current OODA cycle state
//   3. Long-term (learned patterns) — persistent knowledge across sessions
//
// Memory is the substrate for agent continuity. Without it, every LLM call
// starts from zero. With it, the agent builds understanding over time.
// =============================================================================

use chrono::{DateTime, Duration, Utc};
use dashmap::DashMap;
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info};

// ── Short-Term Memory (Conversation Context) ────────────────────────────────

/// Rolling window of conversation messages for the current LLM interaction.
/// This is the "context window" that gets sent with each LLM call.
pub struct ShortTermMemory {
    messages: RwLock<VecDeque<ConversationEntry>>,
    max_messages: usize,
    max_tokens_estimate: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationEntry {
    pub role: String,
    pub content: String,
    pub timestamp: DateTime<Utc>,
    pub token_estimate: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_name: Option<String>,
}

impl ShortTermMemory {
    pub fn new(max_messages: usize) -> Self {
        Self {
            messages: RwLock::new(VecDeque::with_capacity(max_messages)),
            max_messages,
            max_tokens_estimate: max_messages * 500, // rough estimate
        }
    }

    /// Add a message to the conversation context
    pub async fn add(&self, role: &str, content: &str) {
        let entry = ConversationEntry {
            role: role.to_string(),
            content: content.to_string(),
            timestamp: Utc::now(),
            token_estimate: Self::estimate_tokens(content),
            tool_call_id: None,
            tool_name: None,
        };
        self.add_entry(entry).await;
    }

    /// Add a tool result message
    pub async fn add_tool_result(&self, tool_call_id: &str, tool_name: &str, content: &str) {
        let entry = ConversationEntry {
            role: "tool".to_string(),
            content: content.to_string(),
            timestamp: Utc::now(),
            token_estimate: Self::estimate_tokens(content),
            tool_call_id: Some(tool_call_id.to_string()),
            tool_name: Some(tool_name.to_string()),
        };
        self.add_entry(entry).await;
    }

    /// Add an assistant message with tool calls
    pub async fn add_assistant_with_tools(&self, content: &str) {
        let entry = ConversationEntry {
            role: "assistant".to_string(),
            content: content.to_string(),
            timestamp: Utc::now(),
            token_estimate: Self::estimate_tokens(content),
            tool_call_id: None,
            tool_name: None,
        };
        self.add_entry(entry).await;
    }

    async fn add_entry(&self, entry: ConversationEntry) {
        let mut messages = self.messages.write().await;

        // Evict oldest if at capacity
        while messages.len() >= self.max_messages {
            messages.pop_front();
        }

        messages.push_back(entry);
    }

    /// Get all messages as LLM-compatible format
    pub async fn as_messages(&self) -> Vec<serde_json::Value> {
        let messages = self.messages.read().await;
        messages
            .iter()
            .map(|entry| {
                let mut msg = serde_json::json!({
                    "role": entry.role,
                    "content": entry.content,
                });
                if let Some(ref tc_id) = entry.tool_call_id {
                    msg["tool_call_id"] = serde_json::Value::String(tc_id.clone());
                }
                msg
            })
            .collect()
    }

    /// Get the current conversation summary (for long context compression)
    pub async fn summarize(&self) -> String {
        let messages = self.messages.read().await;
        let total_tokens: usize = messages.iter().map(|e| e.token_estimate).sum();

        format!(
            "Conversation: {} messages, ~{} tokens, {} tool calls",
            messages.len(),
            total_tokens,
            messages.iter().filter(|e| e.role == "tool").count()
        )
    }

    /// Clear conversation context
    pub async fn clear(&self) {
        self.messages.write().await.clear();
    }

    /// Get message count
    pub async fn len(&self) -> usize {
        self.messages.read().await.len()
    }

    /// Check if empty
    pub async fn is_empty(&self) -> bool {
        self.messages.read().await.is_empty()
    }

    /// Rough token estimate (4 chars ≈ 1 token)
    fn estimate_tokens(text: &str) -> usize {
        (text.len() + 3) / 4
    }
}

// ── Working Memory (Current Task State) ──────────────────────────────────────

/// State for the current OODA cycle / agent task.
/// This is the "scratchpad" the agent uses during reasoning.
pub struct WorkingMemory {
    state: RwLock<WorkingState>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkingState {
    /// Current task description
    pub current_task: Option<String>,
    /// Current OODA phase
    pub current_phase: String,
    /// Iteration count within current task
    pub iteration: usize,
    /// Collected observations from tool calls
    pub observations: Vec<Observation>,
    /// Intermediate reasoning steps
    pub reasoning_chain: Vec<ReasoningStep>,
    /// Hypotheses being tested
    pub hypotheses: Vec<Hypothesis>,
    /// Decisions made
    pub decisions: Vec<Decision>,
    /// Task started at
    pub started_at: DateTime<Utc>,
    /// Key-value scratchpad for temporary data
    pub scratchpad: serde_json::Value,
    /// Token budget remaining for this task
    pub token_budget_remaining: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Observation {
    pub source: String,
    pub content: String,
    pub timestamp: DateTime<Utc>,
    pub confidence: f64,
    pub tool_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReasoningStep {
    pub step_number: usize,
    pub thought: String,
    pub action: Option<String>,
    pub observation_summary: Option<String>,
    pub timestamp: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Hypothesis {
    pub id: String,
    pub statement: String,
    pub supporting_evidence: Vec<String>,
    pub contradicting_evidence: Vec<String>,
    pub confidence: f64,
    pub status: HypothesisStatus,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HypothesisStatus {
    Active,
    Confirmed,
    Rejected,
    Inconclusive,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Decision {
    pub action: String,
    pub reasoning: String,
    pub confidence: f64,
    pub alternatives_rejected: Vec<String>,
    pub timestamp: DateTime<Utc>,
}

impl WorkingMemory {
    pub fn new(token_budget: usize) -> Self {
        Self {
            state: RwLock::new(WorkingState {
                current_task: None,
                current_phase: "observe".to_string(),
                iteration: 0,
                observations: Vec::new(),
                reasoning_chain: Vec::new(),
                hypotheses: Vec::new(),
                decisions: Vec::new(),
                started_at: Utc::now(),
                scratchpad: serde_json::json!({}),
                token_budget_remaining: token_budget,
            }),
        }
    }

    /// Start a new task
    pub async fn begin_task(&self, task: &str, phase: &str) {
        let mut state = self.state.write().await;
        *state = WorkingState {
            current_task: Some(task.to_string()),
            current_phase: phase.to_string(),
            iteration: 0,
            observations: Vec::new(),
            reasoning_chain: Vec::new(),
            hypotheses: Vec::new(),
            decisions: Vec::new(),
            started_at: Utc::now(),
            scratchpad: serde_json::json!({}),
            token_budget_remaining: state.token_budget_remaining,
        };
    }

    /// Add an observation from a tool call
    pub async fn add_observation(&self, source: &str, content: &str, tool_name: Option<&str>) {
        let mut state = self.state.write().await;
        state.observations.push(Observation {
            source: source.to_string(),
            content: content.to_string(),
            timestamp: Utc::now(),
            confidence: 1.0,
            tool_name: tool_name.map(|s| s.to_string()),
        });
    }

    /// Add a reasoning step (ReAct pattern)
    pub async fn add_reasoning_step(&self, thought: &str, action: Option<&str>) {
        let mut state = self.state.write().await;
        state.iteration += 1;
        state.reasoning_chain.push(ReasoningStep {
            step_number: state.iteration,
            thought: thought.to_string(),
            action: action.map(|s| s.to_string()),
            observation_summary: None,
            timestamp: Utc::now(),
        });
    }

    /// Add or update a hypothesis
    pub async fn add_hypothesis(&self, statement: &str, confidence: f64) -> String {
        let mut state = self.state.write().await;
        let id = format!("hyp_{}", state.hypotheses.len());
        state.hypotheses.push(Hypothesis {
            id: id.clone(),
            statement: statement.to_string(),
            supporting_evidence: Vec::new(),
            contradicting_evidence: Vec::new(),
            confidence,
            status: HypothesisStatus::Active,
        });
        id
    }

    /// Add evidence to a hypothesis
    pub async fn add_evidence(&self, hypothesis_id: &str, evidence: &str, supports: bool) {
        let mut state = self.state.write().await;
        if let Some(hyp) = state.hypotheses.iter_mut().find(|h| h.id == hypothesis_id) {
            if supports {
                hyp.supporting_evidence.push(evidence.to_string());
            } else {
                hyp.contradicting_evidence.push(evidence.to_string());
            }
        }
    }

    /// Record a decision
    pub async fn record_decision(&self, action: &str, reasoning: &str, confidence: f64) {
        let mut state = self.state.write().await;
        state.decisions.push(Decision {
            action: action.to_string(),
            reasoning: reasoning.to_string(),
            confidence,
            alternatives_rejected: Vec::new(),
            timestamp: Utc::now(),
        });
    }

    /// Set scratchpad value
    pub async fn set_scratchpad(&self, key: &str, value: serde_json::Value) {
        let mut state = self.state.write().await;
        if let Some(obj) = state.scratchpad.as_object_mut() {
            obj.insert(key.to_string(), value);
        }
    }

    /// Get the current working state (for context injection)
    pub async fn snapshot(&self) -> WorkingState {
        self.state.read().await.clone()
    }

    /// Get a text summary of the current working state (for LLM context)
    pub async fn context_summary(&self) -> String {
        let state = self.state.read().await;
        let mut summary = String::new();

        if let Some(ref task) = state.current_task {
            summary.push_str(&format!("## Current Task\n{}\n\n", task));
        }

        summary.push_str(&format!("Phase: {} | Iteration: {}\n\n", state.current_phase, state.iteration));

        if !state.observations.is_empty() {
            summary.push_str("## Observations\n");
            for (i, obs) in state.observations.iter().enumerate().rev().take(5) {
                summary.push_str(&format!("{}. [{}] {}\n", i + 1, obs.source, obs.content));
            }
            summary.push('\n');
        }

        if !state.reasoning_chain.is_empty() {
            summary.push_str("## Reasoning Chain\n");
            for step in state.reasoning_chain.iter().rev().take(3) {
                summary.push_str(&format!("Step {}: {}\n", step.step_number, step.thought));
                if let Some(ref action) = step.action {
                    summary.push_str(&format!("  → Action: {}\n", action));
                }
            }
            summary.push('\n');
        }

        if !state.hypotheses.is_empty() {
            summary.push_str("## Active Hypotheses\n");
            for hyp in state.hypotheses.iter().filter(|h| h.status == HypothesisStatus::Active) {
                summary.push_str(&format!(
                    "- {} (confidence: {:.0}%): {} supporting, {} contradicting\n",
                    hyp.statement,
                    hyp.confidence * 100.0,
                    hyp.supporting_evidence.len(),
                    hyp.contradicting_evidence.len()
                ));
            }
            summary.push('\n');
        }

        summary
    }

    /// Check if iteration limit is reached
    pub async fn iteration_count(&self) -> usize {
        self.state.read().await.iteration
    }
}

// ── Long-Term Memory (Learned Patterns) ──────────────────────────────────────

/// Persistent memory across agent sessions. Stores learned patterns,
/// successful strategies, and domain knowledge.
pub struct LongTermMemory {
    patterns: DashMap<String, LearnedPattern>,
    strategies: DashMap<String, SuccessfulStrategy>,
    domain_knowledge: DashMap<String, DomainFact>,
    max_entries: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LearnedPattern {
    pub id: String,
    pub pattern_type: PatternType,
    pub description: String,
    pub conditions: Vec<String>,
    pub outcomes: Vec<String>,
    pub confidence: f64,
    pub times_observed: u32,
    pub last_observed: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PatternType {
    /// Market behavior pattern
    MarketPattern,
    /// Credit risk pattern
    CreditPattern,
    /// Seasonal pattern
    SeasonalPattern,
    /// Operational pattern (system behavior)
    OperationalPattern,
    /// Cross-dimensional correlation
    CorrelationPattern,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SuccessfulStrategy {
    pub id: String,
    pub task_type: String,
    pub strategy_description: String,
    pub tools_used: Vec<String>,
    pub reasoning_pattern: String,
    pub success_count: u32,
    pub failure_count: u32,
    pub avg_confidence: f64,
    pub last_used: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainFact {
    pub key: String,
    pub fact: String,
    pub source: String,
    pub confidence: f64,
    pub last_verified: DateTime<Utc>,
    pub times_referenced: u32,
}

impl LongTermMemory {
    pub fn new(max_entries: usize) -> Self {
        Self {
            patterns: DashMap::with_capacity(max_entries),
            strategies: DashMap::with_capacity(max_entries),
            domain_knowledge: DashMap::with_capacity(max_entries),
            max_entries,
        }
    }

    /// Store a learned pattern
    pub fn store_pattern(&self, pattern: LearnedPattern) {
        if self.patterns.len() >= self.max_entries {
            self.evict_oldest_pattern();
        }
        self.patterns.insert(pattern.id.clone(), pattern);
    }

    /// Store a successful strategy
    pub fn store_strategy(&self, strategy: SuccessfulStrategy) {
        if self.strategies.len() >= self.max_entries {
            self.evict_oldest_strategy();
        }
        self.strategies.insert(strategy.id.clone(), strategy);
    }

    /// Store a domain fact
    pub fn store_fact(&self, fact: DomainFact) {
        if self.domain_knowledge.len() >= self.max_entries {
            self.evict_oldest_fact();
        }
        self.domain_knowledge.insert(fact.key.clone(), fact);
    }

    /// Find patterns matching given conditions
    pub fn find_patterns(&self, pattern_type: Option<PatternType>, min_confidence: f64) -> Vec<LearnedPattern> {
        self.patterns
            .iter()
            .filter(|entry| {
                let p = entry.value();
                (pattern_type.is_none() || Some(p.pattern_type) == pattern_type)
                    && p.confidence >= min_confidence
            })
            .map(|entry| entry.value().clone())
            .collect()
    }

    /// Find strategies for a task type
    pub fn find_strategies(&self, task_type: &str) -> Vec<SuccessfulStrategy> {
        self.strategies
            .iter()
            .filter(|entry| entry.value().task_type == task_type)
            .map(|entry| entry.value().clone())
            .collect()
    }

    /// Look up a domain fact
    pub fn lookup_fact(&self, key: &str) -> Option<DomainFact> {
        self.domain_knowledge.get(key).map(|entry| {
            let mut fact = entry.value().clone();
            fact.times_referenced += 1;
            fact
        })
    }

    /// Get memory statistics
    pub fn stats(&self) -> MemoryStats {
        MemoryStats {
            patterns_count: self.patterns.len(),
            strategies_count: self.strategies.len(),
            facts_count: self.domain_knowledge.len(),
            total_entries: self.patterns.len() + self.strategies.len() + self.domain_knowledge.len(),
        }
    }

    /// Serialize all memory to JSON (for persistence)
    pub fn to_json(&self) -> serde_json::Value {
        let patterns: Vec<&LearnedPattern> = self.patterns.iter().map(|e| e.value()).collect();
        let strategies: Vec<&SuccessfulStrategy> = self.strategies.iter().map(|e| e.value()).collect();
        let facts: Vec<&DomainFact> = self.domain_knowledge.iter().map(|e| e.value()).collect();

        serde_json::json!({
            "patterns": patterns,
            "strategies": strategies,
            "domain_facts": facts,
            "stats": self.stats(),
        })
    }

    /// Load memory from JSON (for persistence restoration)
    pub fn from_json(data: &serde_json::Value) -> Self {
        let memory = Self::new(10_000);

        if let Some(patterns) = data.get("patterns").and_then(|p| p.as_array()) {
            for p in patterns {
                if let Ok(pattern) = serde_json::from_value::<LearnedPattern>(p.clone()) {
                    memory.patterns.insert(pattern.id.clone(), pattern);
                }
            }
        }

        if let Some(strategies) = data.get("strategies").and_then(|s| s.as_array()) {
            for s in strategies {
                if let Ok(strategy) = serde_json::from_value::<SuccessfulStrategy>(s.clone()) {
                    memory.strategies.insert(strategy.id.clone(), strategy);
                }
            }
        }

        if let Some(facts) = data.get("domain_facts").and_then(|f| f.as_array()) {
            for f in facts {
                if let Ok(fact) = serde_json::from_value::<DomainFact>(f.clone()) {
                    memory.domain_knowledge.insert(fact.key.clone(), fact);
                }
            }
        }

        memory
    }

    fn evict_oldest_pattern(&self) {
        if let Some(oldest_key) = self.patterns.iter()
            .min_by_key(|e| e.value().last_observed)
            .map(|e| e.key().clone())
        {
            self.patterns.remove(&oldest_key);
        }
    }

    fn evict_oldest_strategy(&self) {
        if let Some(oldest_key) = self.strategies.iter()
            .min_by_key(|e| e.value().last_used)
            .map(|e| e.key().clone())
        {
            self.strategies.remove(&oldest_key);
        }
    }

    fn evict_oldest_fact(&self) {
        if let Some(oldest_key) = self.domain_knowledge.iter()
            .min_by_key(|e| e.value().last_verified)
            .map(|e| e.key().clone())
        {
            self.domain_knowledge.remove(&oldest_key);
        }
    }
}

#[derive(Debug, Serialize)]
pub struct MemoryStats {
    pub patterns_count: usize,
    pub strategies_count: usize,
    pub facts_count: usize,
    pub total_entries: usize,
}

// ── Agent Memory (Unified Interface) ─────────────────────────────────────────

/// Unified memory system combining all three tiers
pub struct AgentMemory {
    pub short_term: Arc<ShortTermMemory>,
    pub working: Arc<WorkingMemory>,
    pub long_term: Arc<LongTermMemory>,
}

impl AgentMemory {
    pub fn new(config: MemoryConfig) -> Self {
        Self {
            short_term: Arc::new(ShortTermMemory::new(config.max_conversation_messages)),
            working: Arc::new(WorkingMemory::new(config.token_budget_per_task)),
            long_term: Arc::new(LongTermMemory::new(config.max_long_term_entries)),
        }
    }

    /// Get a combined context summary for the LLM
    pub async fn full_context(&self) -> String {
        let mut context = String::new();

        // Working memory context (most relevant)
        let working_summary = self.working.context_summary().await;
        if !working_summary.is_empty() {
            context.push_str(&working_summary);
        }

        // Relevant long-term patterns
        let patterns = self.long_term.find_patterns(None, 0.7);
        if !patterns.is_empty() {
            context.push_str("## Relevant Patterns\n");
            for pattern in patterns.iter().take(5) {
                context.push_str(&format!("- {}: {} (observed {} times)\n",
                    pattern.pattern_type_str(), pattern.description, pattern.times_observed));
            }
            context.push('\n');
        }

        context
    }

    /// Reset for a new task (preserves long-term memory)
    pub async fn reset_for_new_task(&self, task: &str) {
        self.short_term.clear().await;
        self.working.begin_task(task, "observe").await;
    }

    /// Get memory statistics across all tiers
    pub async fn stats(&self) -> serde_json::Value {
        serde_json::json!({
            "short_term": {
                "messages": self.short_term.len().await,
                "summary": self.short_term.summarize().await,
            },
            "working": {
                "iteration": self.working.iteration_count().await,
            },
            "long_term": self.long_term.stats(),
        })
    }
}

impl LearnedPattern {
    fn pattern_type_str(&self) -> &'static str {
        match self.pattern_type {
            PatternType::MarketPattern => "Market",
            PatternType::CreditPattern => "Credit Risk",
            PatternType::SeasonalPattern => "Seasonal",
            PatternType::OperationalPattern => "Operational",
            PatternType::CorrelationPattern => "Correlation",
        }
    }
}

/// Configuration for the memory system
#[derive(Debug, Clone)]
pub struct MemoryConfig {
    /// Maximum messages in conversation context
    pub max_conversation_messages: usize,
    /// Token budget per task (working memory)
    pub token_budget_per_task: usize,
    /// Maximum entries in long-term memory
    pub max_long_term_entries: usize,
}

impl Default for MemoryConfig {
    fn default() -> Self {
        Self {
            max_conversation_messages: 50,
            token_budget_per_task: 100_000,
            max_long_term_entries: 10_000,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_short_term_memory_eviction() {
        let mem = ShortTermMemory::new(3);
        mem.add("user", "msg1").await;
        mem.add("assistant", "msg2").await;
        mem.add("user", "msg3").await;
        mem.add("assistant", "msg4").await; // should evict msg1

        assert_eq!(mem.len().await, 3);
        let messages = mem.as_messages().await;
        assert_eq!(messages[0]["content"], "msg2");
    }

    #[tokio::test]
    async fn test_working_memory_lifecycle() {
        let wm = WorkingMemory::new(100_000);
        wm.begin_task("Analyze tomatoes market", "observe").await;

        wm.add_observation("market_tool", "Prices rising 15%", Some("market_analysis")).await;
        wm.add_reasoning_step("Prices are rising, likely due to supply shortage", Some("check_supply")).await;
        wm.add_hypothesis("Supply disruption caused by drought", 0.7).await;

        let snapshot = wm.snapshot().await;
        assert_eq!(snapshot.observations.len(), 1);
        assert_eq!(snapshot.reasoning_chain.len(), 1);
        assert_eq!(snapshot.hypotheses.len(), 1);
        assert_eq!(snapshot.iteration, 1);
    }

    #[test]
    fn test_long_term_memory_pattern_search() {
        let ltm = LongTermMemory::new(1000);
        ltm.store_pattern(LearnedPattern {
            id: "p1".to_string(),
            pattern_type: PatternType::SeasonalPattern,
            description: "Tomato prices peak in Jan-Feb".to_string(),
            conditions: vec!["month == january".to_string()],
            outcomes: vec!["price +30%".to_string()],
            confidence: 0.85,
            times_observed: 12,
            last_observed: Utc::now(),
            created_at: Utc::now(),
        });

        let results = ltm.find_patterns(Some(PatternType::SeasonalPattern), 0.8);
        assert_eq!(results.len(), 1);

        let results = ltm.find_patterns(Some(PatternType::MarketPattern), 0.8);
        assert_eq!(results.len(), 0);
    }

    #[test]
    fn test_long_term_memory_serialization() {
        let ltm = LongTermMemory::new(1000);
        ltm.store_fact(DomainFact {
            key: "nairobi_population".to_string(),
            fact: "Nairobi metro area population ~5 million".to_string(),
            source: "KNBS 2023".to_string(),
            confidence: 0.95,
            last_verified: Utc::now(),
            times_referenced: 0,
        });

        let json = ltm.to_json();
        let restored = LongTermMemory::from_json(&json);
        let fact = restored.lookup_fact("nairobi_population").unwrap();
        assert!(fact.fact.contains("Nairobi"));
    }

    #[tokio::test]
    async fn test_agent_memory_reset() {
        let mem = AgentMemory::new(MemoryConfig::default());
        mem.short_term.add("user", "hello").await;
        mem.working.begin_task("old task", "act").await;

        mem.reset_for_new_task("new task").await;

        assert!(mem.short_term.is_empty().await);
        let snapshot = mem.working.snapshot().await;
        assert_eq!(snapshot.current_task, Some("new task".to_string()));
        assert_eq!(snapshot.iteration, 0);
    }
}
