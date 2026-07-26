// tests/unit/message_bus_test.rs

#[cfg(test)]
mod tests {
    use super::*;
    use angavu_intelligence_backend::orchestrator::message_bus::*;

    #[tokio::test]
    async fn test_broadcast_publish_subscribe() {
        let bus = ModuleMessageBus::new(MessageBusConfig::default());
        let mut rx1 = bus.subscribe();
        let mut rx2 = bus.subscribe();

        let msg = ModuleMessage::MarketSignal {
            trace_id: Uuid::new_v4(),
            region: "nairobi".to_string(),
            product_category: "vegetables".to_string(),
            demand_index: 1.5,
            price_trend: PriceTrend::Rising { rate_pct: 8.0 },
            volatility: 0.15,
            sample_size: 100,
            confidence: 0.85,
        };

        bus.publish(msg.clone()).await.unwrap();

        // Both subscribers should receive
        let received1 = rx1.recv().await.unwrap();
        let received2 = rx2.recv().await.unwrap();

        match (received1, received2) {
            (ModuleMessage::MarketSignal { region: r1, .. },
             ModuleMessage::MarketSignal { region: r2, .. }) => {
                assert_eq!(r1, "nairobi");
                assert_eq!(r2, "nairobi");
            }
            _ => panic!("Wrong message type"),
        }
    }

    #[tokio::test]
    async fn test_point_to_point_dispatch() {
        let bus = ModuleMessageBus::new(MessageBusConfig::default());
        let mut rx = bus.register_module(ModuleId::MarketAnalyzer);

        let msg = ModuleMessage::TransactionBatch {
            trace_id: Uuid::new_v4(),
            worker_id_hash: "hash123".to_string(),
            transactions: vec![],
            region: "nairobi".to_string(),
            timestamp: Utc::now(),
        };

        bus.send_to_module(ModuleId::MarketAnalyzer, msg).await.unwrap();

        let received = rx.recv().await.unwrap();
        assert!(matches!(received, ModuleMessage::TransactionBatch { .. }));
    }

    #[tokio::test]
    async fn test_audit_logging() {
        let bus = ModuleMessageBus::new(MessageBusConfig {
            audit_enabled: true,
            ..Default::default()
        });

        let msg = ModuleMessage::Heartbeat {
            module_id: ModuleId::MarketAnalyzer,
            queue_depth: 0,
            processing_rate: 100.0,
            last_error: None,
            uptime_secs: 3600,
        };

        bus.publish(msg).await.unwrap();

        let entries = bus.flush_audit().await;
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].message_type, "Heartbeat");
    }
}
