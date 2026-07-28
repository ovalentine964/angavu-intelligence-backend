// rust-api/src/graph/pipeline_tests.rs

#[cfg(test)]
mod pipeline_tests {
    use crate::graph::pipeline::*;

    #[test]
    fn test_pipeline_dag_topological_order() {
        let dag = PipelineDag::standard_intelligence_pipeline();

        // Should have multiple levels
        assert!(dag.execution_order.len() >= 4);

        // Level 0: sync nodes (parallel)
        let level_0 = &dag.execution_order[0];
        assert!(level_0.contains(&"sync_transactions".to_string()));
        assert!(level_0.contains(&"sync_market_data".to_string()));
        assert!(level_0.contains(&"sync_external".to_string()));

        // Last level: distribute
        let last_level = dag.execution_order.last().unwrap();
        assert!(last_level.contains(&"distribute".to_string()));
    }

    #[test]
    fn test_pipeline_ready_nodes() {
        let dag = PipelineDag::standard_intelligence_pipeline();

        // Initially, only sync nodes should be ready (no dependencies)
        let ready = dag.ready_nodes();
        assert_eq!(ready.len(), 3);  // 3 sync nodes
        assert!(ready.iter().all(|n| n.node_type == PipelineNodeType::Sync));
    }

    #[test]
    fn test_pipeline_executor_complete_flow() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);

        // Complete sync nodes
        executor.complete_node("sync_transactions", serde_json::json!({"records": 1000}));
        executor.complete_node("sync_market_data", serde_json::json!({"signals": 50}));
        executor.complete_node("sync_external", serde_json::json!({"weather": "sunny"}));

        // Now anonymize should be ready
        let ready = executor.next_batch();
        assert!(ready.iter().any(|n| n.name == "anonymize"));
    }

    #[test]
    fn test_pipeline_circuit_breaker_isolation() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);

        // Fail sync_transactions 3 times
        executor.fail_node("sync_transactions", "connection timeout".into());
        executor.fail_node("sync_transactions", "connection timeout".into());
        executor.fail_node("sync_transactions", "connection timeout".into());

        // sync_transactions should be failed
        let node = executor.pipeline.nodes.get("sync_transactions").unwrap();
        assert_eq!(node.status, PipelineNodeStatus::Failed);

        // But sync_market_data and sync_external should still work
        let node_market = executor.pipeline.nodes.get("sync_market_data").unwrap();
        assert_eq!(node_market.status, PipelineNodeStatus::Pending);
    }

    #[test]
    fn test_pipeline_validation() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        assert!(dag.validate().is_ok());
    }

    #[test]
    fn test_pipeline_node_count() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        assert_eq!(dag.nodes.len(), 11); // 3 sync + 1 anonymize + 1 aggregate + 3 analyze + 2 generate + 1 distribute
    }

    #[test]
    fn test_pipeline_executor_progress_tracking() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);

        assert_eq!(executor.progress(), 0.0);

        executor.complete_node("sync_transactions", serde_json::json!({}));
        assert!(executor.progress() > 0.0);
        assert!(executor.progress() < 1.0);
    }

    #[test]
    fn test_pipeline_executor_retry_logic() {
        let dag = PipelineDag::standard_intelligence_pipeline();
        let mut executor = PipelineExecutor::new(dag, 4);

        // First failure → retrying (max_retries = 3 for sync nodes)
        executor.fail_node("sync_transactions", "timeout".into());
        let node = executor.pipeline.nodes.get("sync_transactions").unwrap();
        assert_eq!(node.status, PipelineNodeStatus::Retrying);
        assert_eq!(node.retry_count, 1);

        // Second failure → still retrying
        executor.fail_node("sync_transactions", "timeout".into());
        let node = executor.pipeline.nodes.get("sync_transactions").unwrap();
        assert_eq!(node.status, PipelineNodeStatus::Retrying);
        assert_eq!(node.retry_count, 2);

        // Third failure → failed (retries exhausted)
        executor.fail_node("sync_transactions", "timeout".into());
        let node = executor.pipeline.nodes.get("sync_transactions").unwrap();
        assert_eq!(node.status, PipelineNodeStatus::Failed);
    }

    #[test]
    fn test_pipeline_node_depth() {
        let dag = PipelineDag::standard_intelligence_pipeline();

        assert_eq!(dag.node_depth("sync_transactions"), 0);
        assert_eq!(dag.node_depth("anonymize"), 1);
        assert_eq!(dag.node_depth("aggregate"), 2);
        assert_eq!(dag.node_depth("distribute"), 5);
    }
}
