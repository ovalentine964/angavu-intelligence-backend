// rust-api/src/graph/pipeline_tests.rs

#[cfg(test)]
mod pipeline_tests {
    use super::pipeline::*;

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
}
