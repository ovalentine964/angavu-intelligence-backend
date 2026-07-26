// tests/integration/orchestrator_test.rs

#[cfg(test)]
mod tests {
    use angavu_intelligence_backend::orchestrator::*;
    use angavu_intelligence_backend::orchestrator::message_bus::*;
    use std::sync::Arc;

    #[tokio::test]
    async fn test_full_ooda_cycle() {
        let bus = Arc::new(ModuleMessageBus::new(MessageBusConfig::default()));
        let config = OrchestratorConfig {
            cycle_interval_ms: 100, // Fast for testing
            ..Default::default()
        };
        let orchestrator = OODAOrchestrator::new(config, Arc::clone(&bus));

        // Start modules
        orchestrator.start_modules().await.unwrap();

        // Publish a transaction batch
        let msg = ModuleMessage::TransactionBatch {
            trace_id: Uuid::new_v4(),
            worker_id_hash: "test_worker".to_string(),
            transactions: (0..50).map(|i| TransactionRecord {
                id: Uuid::new_v4(),
                amount: 100.0 + i as f64 * 10.0,
                currency: "KES".to_string(),
                product_category: "vegetables".to_string(),
                product_name: Some("tomatoes".to_string()),
                quantity: Some(5.0),
                unit: Some("kg".to_string()),
                payment_method: "cash".to_string(),
                timestamp: Utc::now(),
                confidence_score: 0.9,
            }).collect(),
            region: "nairobi-eastlands".to_string(),
            timestamp: Utc::now(),
        };

        bus.publish(msg).await.unwrap();

        // Let modules process
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;

        // Run one OODA cycle
        let result = orchestrator.run_cycle().await.unwrap();
        assert_eq!(result.cycle_number, 1);

        // Shutdown
        orchestrator.shutdown().await.unwrap();
    }

    #[tokio::test]
    async fn test_module_restart_on_failure() {
        let bus = Arc::new(ModuleMessageBus::new(MessageBusConfig::default()));
        let config = OrchestratorConfig::default();
        let orchestrator = OODAOrchestrator::new(config, Arc::clone(&bus));

        orchestrator.start_modules().await.unwrap();

        // Simulate module failure
        let result = orchestrator.handle_module_failure(
            ModuleId::MarketAnalyzer,
            "test failure".to_string(),
        ).await;

        assert!(result.is_ok());

        let state = orchestrator.state().await;
        let health = state.module_health.get(&ModuleId::MarketAnalyzer).unwrap();
        assert_eq!(health.status, HealthStatus::Healthy);
        assert_eq!(health.restart_count, 1);
    }
}
