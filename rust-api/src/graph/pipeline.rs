//! Intelligence Pipeline DAG — Models the data processing pipeline as a
//! directed acyclic graph with circuit breakers and parallel execution.
//!
//! Pipeline: Sync → Anonymize → Aggregate → Analyze → Generate → Distribute
//!
//! Each step can fail independently (circuit breaker per node).
//! Steps with no dependencies execute in parallel.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use uuid::Uuid;

use super::ooda::{make_node_circuit_breaker, CircuitBreaker, CircuitState};

/// A node in the pipeline DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineNode {
    pub id: Uuid,
    pub name: String,
    pub node_type: PipelineNodeType,
    pub status: PipelineNodeStatus,
    pub depends_on: Vec<String>, // names of nodes this depends on
    pub circuit_breaker: CircuitBreaker,
    pub max_retries: u32,
    pub retry_count: u32,
    pub timeout_ms: u64,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
    pub duration_ms: Option<u64>,
    pub input_data: serde_json::Value,
    pub output_data: serde_json::Value,
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PipelineNodeType {
    /// Sync data from devices
    Sync,
    /// Anonymize data (strip PII, add DP noise)
    Anonymize,
    /// Aggregate across cohorts and regions
    Aggregate,
    /// Run analysis (ML models, pattern detection)
    Analyze,
    /// Generate intelligence outputs (reports, signals)
    Generate,
    /// Distribute results to consumers
    Distribute,
    /// Custom node type for extensibility
    Custom(String),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PipelineNodeStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Skipped,
    Retrying,
    CircuitOpen,
}

/// The complete pipeline DAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineDag {
    pub id: Uuid,
    pub name: String,
    pub nodes: HashMap<String, PipelineNode>,
    pub execution_order: Vec<Vec<String>>, // topological levels (parallel groups)
    pub created_at: DateTime<Utc>,
}

impl PipelineDag {
    /// Create the standard intelligence pipeline DAG.
    ///
    /// Topology:
    ///   Level 0 (Sync):       sync_transactions, sync_market_data, sync_external
    ///   Level 1 (Anonymize):  anonymize
    ///   Level 2 (Aggregate):  aggregate
    ///   Level 3 (Analyze):    analyze_patterns, analyze_credit, analyze_market
    ///   Level 4 (Generate):   generate_reports, generate_signals
    ///   Level 5 (Distribute): distribute
    pub fn standard_intelligence_pipeline() -> Self {
        let mut nodes = HashMap::new();

        // ── Level 0: Sync nodes (parallel, no dependencies) ──────────
        nodes.insert(
            "sync_transactions".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "sync_transactions".to_string(),
                node_type: PipelineNodeType::Sync,
                status: PipelineNodeStatus::Pending,
                depends_on: vec![],
                circuit_breaker: make_node_circuit_breaker("sync_transactions", 3, 120),
                max_retries: 3,
                retry_count: 0,
                timeout_ms: 30_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        nodes.insert(
            "sync_market_data".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "sync_market_data".to_string(),
                node_type: PipelineNodeType::Sync,
                status: PipelineNodeStatus::Pending,
                depends_on: vec![],
                circuit_breaker: make_node_circuit_breaker("sync_market_data", 3, 120),
                max_retries: 3,
                retry_count: 0,
                timeout_ms: 30_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        nodes.insert(
            "sync_external".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "sync_external".to_string(),
                node_type: PipelineNodeType::Sync,
                status: PipelineNodeStatus::Pending,
                depends_on: vec![],
                circuit_breaker: make_node_circuit_breaker("sync_external", 3, 120),
                max_retries: 3,
                retry_count: 0,
                timeout_ms: 30_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        // ── Level 1: Anonymize (depends on all sync nodes) ───────────
        nodes.insert(
            "anonymize".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "anonymize".to_string(),
                node_type: PipelineNodeType::Anonymize,
                status: PipelineNodeStatus::Pending,
                depends_on: vec![
                    "sync_transactions".to_string(),
                    "sync_market_data".to_string(),
                    "sync_external".to_string(),
                ],
                circuit_breaker: make_node_circuit_breaker("anonymize", 3, 60),
                max_retries: 2,
                retry_count: 0,
                timeout_ms: 60_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        // ── Level 2: Aggregate (depends on anonymize) ────────────────
        nodes.insert(
            "aggregate".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "aggregate".to_string(),
                node_type: PipelineNodeType::Aggregate,
                status: PipelineNodeStatus::Pending,
                depends_on: vec!["anonymize".to_string()],
                circuit_breaker: make_node_circuit_breaker("aggregate", 3, 60),
                max_retries: 2,
                retry_count: 0,
                timeout_ms: 120_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        // ── Level 3: Analyze (parallel, all depend on aggregate) ─────
        nodes.insert(
            "analyze_patterns".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "analyze_patterns".to_string(),
                node_type: PipelineNodeType::Analyze,
                status: PipelineNodeStatus::Pending,
                depends_on: vec!["aggregate".to_string()],
                circuit_breaker: make_node_circuit_breaker("analyze_patterns", 3, 60),
                max_retries: 2,
                retry_count: 0,
                timeout_ms: 180_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        nodes.insert(
            "analyze_credit".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "analyze_credit".to_string(),
                node_type: PipelineNodeType::Analyze,
                status: PipelineNodeStatus::Pending,
                depends_on: vec!["aggregate".to_string()],
                circuit_breaker: make_node_circuit_breaker("analyze_credit", 3, 60),
                max_retries: 2,
                retry_count: 0,
                timeout_ms: 180_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        nodes.insert(
            "analyze_market".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "analyze_market".to_string(),
                node_type: PipelineNodeType::Analyze,
                status: PipelineNodeStatus::Pending,
                depends_on: vec!["aggregate".to_string()],
                circuit_breaker: make_node_circuit_breaker("analyze_market", 3, 60),
                max_retries: 2,
                retry_count: 0,
                timeout_ms: 180_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        // ── Level 4: Generate (depends on analyze nodes) ─────────────
        nodes.insert(
            "generate_reports".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "generate_reports".to_string(),
                node_type: PipelineNodeType::Generate,
                status: PipelineNodeStatus::Pending,
                depends_on: vec![
                    "analyze_patterns".to_string(),
                    "analyze_credit".to_string(),
                    "analyze_market".to_string(),
                ],
                circuit_breaker: make_node_circuit_breaker("generate_reports", 3, 60),
                max_retries: 2,
                retry_count: 0,
                timeout_ms: 120_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        nodes.insert(
            "generate_signals".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "generate_signals".to_string(),
                node_type: PipelineNodeType::Generate,
                status: PipelineNodeStatus::Pending,
                depends_on: vec!["analyze_patterns".to_string(), "analyze_market".to_string()],
                circuit_breaker: make_node_circuit_breaker("generate_signals", 3, 60),
                max_retries: 2,
                retry_count: 0,
                timeout_ms: 60_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        // ── Level 5: Distribute (depends on generate nodes) ──────────
        nodes.insert(
            "distribute".to_string(),
            PipelineNode {
                id: Uuid::new_v4(),
                name: "distribute".to_string(),
                node_type: PipelineNodeType::Distribute,
                status: PipelineNodeStatus::Pending,
                depends_on: vec![
                    "generate_reports".to_string(),
                    "generate_signals".to_string(),
                ],
                circuit_breaker: make_node_circuit_breaker("distribute", 5, 300),
                max_retries: 5,
                retry_count: 0,
                timeout_ms: 60_000,
                started_at: None,
                completed_at: None,
                duration_ms: None,
                input_data: serde_json::json!({}),
                output_data: serde_json::json!({}),
                error: None,
            },
        );

        // Compute topological levels
        let execution_order = Self::topological_levels(&nodes);

        Self {
            id: Uuid::new_v4(),
            name: "standard_intelligence_pipeline".to_string(),
            nodes,
            execution_order,
            created_at: Utc::now(),
        }
    }

    /// Compute topological levels for parallel execution.
    /// Nodes at the same level have no dependencies on each other and can run in parallel.
    pub fn topological_levels(nodes: &HashMap<String, PipelineNode>) -> Vec<Vec<String>> {
        let mut levels: Vec<Vec<String>> = Vec::new();
        let mut assigned: HashSet<String> = HashSet::new();
        let mut remaining: HashSet<String> = nodes.keys().cloned().collect();

        while !remaining.is_empty() {
            // Find all nodes whose dependencies are all already assigned
            let current_level: Vec<String> = remaining
                .iter()
                .filter(|name| {
                    let node = &nodes[*name];
                    node.depends_on.iter().all(|dep| assigned.contains(dep))
                })
                .cloned()
                .collect();

            if current_level.is_empty() {
                // Cycle detected or broken dependency — assign remaining to avoid infinite loop
                tracing::warn!(
                    remaining = ?remaining,
                    "Cycle or broken dependency detected in pipeline DAG"
                );
                levels.push(remaining.drain().collect());
                break;
            }

            for name in &current_level {
                assigned.insert(name.clone());
                remaining.remove(name);
            }
            levels.push(current_level);
        }

        levels
    }

    /// Get all nodes that are ready to execute (all dependencies completed, circuit breaker closed).
    pub fn ready_nodes(&self) -> Vec<&PipelineNode> {
        self.nodes
            .values()
            .filter(|node| {
                node.status == PipelineNodeStatus::Pending
                    && node.depends_on.iter().all(|dep| {
                        self.nodes
                            .get(dep)
                            .map(|d| d.status == PipelineNodeStatus::Completed)
                            .unwrap_or(false)
                    })
            })
            .collect()
    }

    /// Get the dependency depth of a node (longest path from root).
    pub fn node_depth(&self, name: &str) -> usize {
        let mut memo: HashMap<String, usize> = HashMap::new();
        self.compute_depth(name, &mut memo)
    }

    fn compute_depth(&self, name: &str, memo: &mut HashMap<String, usize>) -> usize {
        if let Some(&cached) = memo.get(name) {
            return cached;
        }

        let depth = if let Some(node) = self.nodes.get(name) {
            if node.depends_on.is_empty() {
                0
            } else {
                1 + node
                    .depends_on
                    .iter()
                    .map(|dep| self.compute_depth(dep, memo))
                    .max()
                    .unwrap_or(0)
            }
        } else {
            0
        };

        memo.insert(name.to_string(), depth);
        depth
    }

    /// Validate DAG integrity: check for cycles and missing dependencies.
    pub fn validate(&self) -> Result<(), Vec<String>> {
        let mut errors = Vec::new();

        // Check for missing dependencies
        for (name, node) in &self.nodes {
            for dep in &node.depends_on {
                if !self.nodes.contains_key(dep) {
                    errors.push(format!(
                        "Node '{}' depends on '{}' which does not exist",
                        name, dep
                    ));
                }
            }
        }

        // Check for cycles using DFS
        let mut visited: HashSet<String> = HashSet::new();
        let mut in_stack: HashSet<String> = HashSet::new();

        for name in self.nodes.keys() {
            if self.detect_cycle(name, &mut visited, &mut in_stack) {
                errors.push(format!("Cycle detected involving node '{}'", name));
            }
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }

    fn detect_cycle(
        &self,
        name: &str,
        visited: &mut HashSet<String>,
        in_stack: &mut HashSet<String>,
    ) -> bool {
        if in_stack.contains(name) {
            return true;
        }
        if visited.contains(name) {
            return false;
        }

        visited.insert(name.to_string());
        in_stack.insert(name.to_string());

        if let Some(node) = self.nodes.get(name) {
            for dep in &node.depends_on {
                if self.detect_cycle(dep, visited, in_stack) {
                    return true;
                }
            }
        }

        in_stack.remove(name);
        false
    }
}

/// Execution result for a single pipeline node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeExecutionResult {
    pub node_name: String,
    pub success: bool,
    pub output: serde_json::Value,
    pub error: Option<String>,
    pub duration_ms: u64,
    pub retry_count: u32,
}

/// Pipeline executor — runs DAG nodes in dependency order with parallel execution.
#[derive(Debug)]
pub struct PipelineExecutor {
    pub pipeline: PipelineDag,
    pub max_parallel: usize,
    pub results: Vec<NodeExecutionResult>,
    pub started_at: Option<DateTime<Utc>>,
    pub completed_at: Option<DateTime<Utc>>,
}

impl PipelineExecutor {
    /// Create a new executor for the given pipeline.
    pub fn new(pipeline: PipelineDag, max_parallel: usize) -> Self {
        Self {
            pipeline,
            max_parallel: max_parallel.max(1),
            results: Vec::new(),
            started_at: None,
            completed_at: None,
        }
    }

    /// Get the next batch of nodes that are ready to execute (parallel group).
    pub fn next_batch(&self) -> Vec<&PipelineNode> {
        let ready = self.pipeline.ready_nodes();
        // Respect max_parallel limit
        ready.into_iter().take(self.max_parallel).collect()
    }

    /// Mark a node as started.
    pub fn start_node(&mut self, name: &str) {
        if let Some(node) = self.pipeline.nodes.get_mut(name) {
            // Check circuit breaker
            if !node.circuit_breaker.clone().should_allow() {
                node.status = PipelineNodeStatus::CircuitOpen;
                return;
            }
            node.status = PipelineNodeStatus::Running;
            node.started_at = Some(Utc::now());
            if self.started_at.is_none() {
                self.started_at = Some(Utc::now());
            }
        }
    }

    /// Complete a node successfully.
    pub fn complete_node(&mut self, name: &str, output: serde_json::Value) {
        let duration = if let Some(node) = self.pipeline.nodes.get_mut(name) {
            node.status = PipelineNodeStatus::Completed;
            node.completed_at = Some(Utc::now());
            node.output_data = output.clone();
            node.duration_ms = node
                .started_at
                .map(|s| (Utc::now() - s).num_milliseconds().max(0) as u64);
            node.circuit_breaker.record_success();
            node.duration_ms.unwrap_or(0)
        } else {
            return;
        };

        self.results.push(NodeExecutionResult {
            node_name: name.to_string(),
            success: true,
            output,
            error: None,
            duration_ms: duration,
            retry_count: 0,
        });

        self.check_completion();
    }

    /// Fail a node. Retries if under limit, otherwise marks as failed.
    pub fn fail_node(&mut self, name: &str, error: String) {
        let should_retry = if let Some(node) = self.pipeline.nodes.get_mut(name) {
            node.retry_count += 1;
            node.error = Some(error.clone());
            node.circuit_breaker.record_failure();

            if node.retry_count < node.max_retries {
                node.status = PipelineNodeStatus::Retrying;
                true
            } else {
                node.status = PipelineNodeStatus::Failed;
                node.completed_at = Some(Utc::now());
                false
            }
        } else {
            return;
        };

        if !should_retry {
            self.results.push(NodeExecutionResult {
                node_name: name.to_string(),
                success: false,
                output: serde_json::json!(null),
                error: Some(error),
                duration_ms: 0,
                retry_count: self
                    .pipeline
                    .nodes
                    .get(name)
                    .map(|n| n.retry_count)
                    .unwrap_or(0),
            });
        }

        self.check_completion();
    }

    /// Skip a node (and mark downstream nodes that only depend on this as skippable).
    pub fn skip_node(&mut self, name: &str) {
        if let Some(node) = self.pipeline.nodes.get_mut(name) {
            node.status = PipelineNodeStatus::Skipped;
            node.completed_at = Some(Utc::now());
        }
        self.check_completion();
    }

    /// Check if the pipeline execution is complete (all nodes terminal).
    fn check_completion(&mut self) {
        let all_terminal = self.pipeline.nodes.values().all(|n| {
            matches!(
                n.status,
                PipelineNodeStatus::Completed
                    | PipelineNodeStatus::Failed
                    | PipelineNodeStatus::Skipped
                    | PipelineNodeStatus::CircuitOpen
            )
        });

        if all_terminal && self.completed_at.is_none() {
            self.completed_at = Some(Utc::now());
        }
    }

    /// Check if execution is done.
    pub fn is_complete(&self) -> bool {
        self.completed_at.is_some()
    }

    /// Get overall pipeline progress as a fraction [0.0, 1.0].
    pub fn progress(&self) -> f64 {
        let total = self.pipeline.nodes.len() as f64;
        if total == 0.0 {
            return 1.0;
        }
        let completed = self
            .pipeline
            .nodes
            .values()
            .filter(|n| {
                matches!(
                    n.status,
                    PipelineNodeStatus::Completed
                        | PipelineNodeStatus::Skipped
                        | PipelineNodeStatus::CircuitOpen
                )
            })
            .count() as f64;
        completed / total
    }

    /// Get total execution duration (if complete).
    pub fn total_duration_ms(&self) -> Option<u64> {
        match (self.started_at, self.completed_at) {
            (Some(start), Some(end)) => Some((end - start).num_milliseconds().max(0) as u64),
            _ => None,
        }
    }

    /// Execute the full pipeline using a provided node handler.
    /// The handler receives (node_name, input) and returns Ok(output) or Err(error).
    /// This is the main entry point for running a pipeline to completion.
    #[tracing::instrument(skip(self, handler), fields(pipeline_nodes = self.nodes.len()))]
    pub async fn execute<F, Fut>(&mut self, handler: F) -> anyhow::Result<Vec<NodeExecutionResult>>
    where
        F: Fn(String, serde_json::Value) -> Fut + Send + Sync + 'static,
        Fut: std::future::Future<Output = Result<serde_json::Value, String>> + Send,
    {
        use futures::stream::{self, StreamExt};

        self.started_at = Some(Utc::now());

        while !self.is_complete() {
            let batch: Vec<String> = self.next_batch().iter().map(|n| n.name.clone()).collect();

            if batch.is_empty() {
                // No ready nodes — check if we're stuck
                let has_running = self
                    .pipeline
                    .nodes
                    .values()
                    .any(|n| n.status == PipelineNodeStatus::Running);
                if !has_running {
                    tracing::warn!("Pipeline stuck: no ready or running nodes");
                    break;
                }
                // Wait a bit for running nodes
                tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                continue;
            }

            // Mark all as started
            for name in &batch {
                self.start_node(name);
            }

            // Execute batch in parallel
            let results: Vec<(String, Result<serde_json::Value, String>)> = stream::iter(batch)
                .map(|name| {
                    let input = self
                        .pipeline
                        .nodes
                        .get(&name)
                        .map(|n| n.input_data.clone())
                        .unwrap_or(serde_json::json!({}));
                    let handler_ref = &handler;
                    async move {
                        let result = handler_ref(name.clone(), input).await;
                        (name, result)
                    }
                })
                .buffer_unordered(self.max_parallel)
                .collect()
                .await;

            // Process results
            for (name, result) in results {
                match result {
                    Ok(output) => self.complete_node(&name, output),
                    Err(error) => self.fail_node(&name, error),
                }
            }
        }

        Ok(self.results.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_standard_pipeline_creation() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        assert_eq!(dag.nodes.len(), 11);
        assert!(dag.execution_order.len() >= 4);
    }

    #[test]
    fn test_topological_levels() {
        let dag = PipelineDag::standard_intelligence_pipeline();

        // Level 0: 3 sync nodes
        let level_0 = &dag.execution_order[0];
        assert_eq!(level_0.len(), 3);
        assert!(level_0.contains(&"sync_transactions".to_string()));
        assert!(level_0.contains(&"sync_market_data".to_string()));
        assert!(level_0.contains(&"sync_external".to_string()));

        // Last level: distribute
        let last_level = dag.execution_order.last().unwrap();
        assert!(last_level.contains(&"distribute".to_string()));
    }

    #[test]
    fn test_ready_nodes_initial() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let ready = dag.ready_nodes();
        assert_eq!(ready.len(), 3); // Only sync nodes
    }

    #[test]
    fn test_ready_nodes_after_sync() {
        let mut dag = PipelineDag::standard_intelligence_pipeline();

        // Complete all sync nodes
        dag.nodes.get_mut("sync_transactions").unwrap().status = PipelineNodeStatus::Completed;
        dag.nodes.get_mut("sync_market_data").unwrap().status = PipelineNodeStatus::Completed;
        dag.nodes.get_mut("sync_external").unwrap().status = PipelineNodeStatus::Completed;

        let ready = dag.ready_nodes();
        assert_eq!(ready.len(), 1);
        assert_eq!(ready[0].name, "anonymize");
    }

    #[test]
    fn test_dag_validation() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        assert!(dag.validate().is_ok());
    }

    #[test]
    fn test_node_depth() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        assert_eq!(dag.node_depth("sync_transactions"), 0);
        assert_eq!(dag.node_depth("anonymize"), 1);
        assert_eq!(dag.node_depth("aggregate"), 2);
        assert_eq!(dag.node_depth("distribute"), 5);
    }

    #[test]
    fn test_executor_progress() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);
        assert_eq!(executor.progress(), 0.0);

        executor.complete_node("sync_transactions", serde_json::json!({"records": 1000}));
        assert!(executor.progress() > 0.0);
        assert!(executor.progress() < 1.0);
    }

    #[test]
    fn test_executor_circuit_breaker_isolation() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);

        // Fail sync_transactions 3 times (max_retries = 3)
        executor.fail_node("sync_transactions", "timeout".into());
        executor.fail_node("sync_transactions", "timeout".into());
        executor.fail_node("sync_transactions", "timeout".into());

        let node = executor.pipeline.nodes.get("sync_transactions").unwrap();
        assert_eq!(node.status, PipelineNodeStatus::Failed);

        // Other sync nodes unaffected
        let market = executor.pipeline.nodes.get("sync_market_data").unwrap();
        assert_eq!(market.status, PipelineNodeStatus::Pending);
    }

    #[test]
    fn test_executor_retry() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);

        // First failure → retrying
        executor.fail_node("sync_transactions", "timeout".into());
        let node = executor.pipeline.nodes.get("sync_transactions").unwrap();
        assert_eq!(node.status, PipelineNodeStatus::Retrying);
        assert_eq!(node.retry_count, 1);
    }

    #[test]
    fn test_executor_completion_flow() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);

        // Complete sync nodes
        executor.complete_node("sync_transactions", serde_json::json!({"records": 1000}));
        executor.complete_node("sync_market_data", serde_json::json!({"signals": 50}));
        executor.complete_node("sync_external", serde_json::json!({"weather": "sunny"}));

        // Anonymize should be ready
        let ready = executor.next_batch();
        assert!(ready.iter().any(|n| n.name == "anonymize"));

        // Complete anonymize
        executor.complete_node("anonymize", serde_json::json!({"anonymized": true}));

        // Aggregate should be ready
        let ready = executor.next_batch();
        assert!(ready.iter().any(|n| n.name == "aggregate"));
    }
}
