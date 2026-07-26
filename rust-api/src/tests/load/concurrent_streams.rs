// tests/load/concurrent_streams.rs

#[cfg(test)]
mod tests {
    use angavu_intelligence_backend::orchestrator::message_bus::*;

    #[tokio::test]
    async fn test_100k_concurrent_messages() {
        let bus = ModuleMessageBus::new(MessageBusConfig {
            broadcast_capacity: 131_072, // 128K buffer
            module_queue_capacity: 32_768,
            ..Default::default()
        });

        let mut rx = bus.subscribe();

        // Spawn 100K message producers
        let bus = Arc::new(bus);
        let start = std::time::Instant::now();

        let handles: Vec<_> = (0..100_000).map(|i| {
            let bus = Arc::clone(&bus);
            tokio::spawn(async move {
                let msg = ModuleMessage::TransactionBatch {
                    trace_id: Uuid::new_v4(),
                    worker_id_hash: format!("worker_{}", i % 10_000),
                    transactions: vec![TransactionRecord {
                        id: Uuid::new_v4(),
                        amount: 100.0,
                        currency: "KES".to_string(),
                        product_category: "test".to_string(),
                        product_name: None,
                        quantity: None,
                        unit: None,
                        payment_method: "cash".to_string(),
                        timestamp: Utc::now(),
                        confidence_score: 1.0,
                    }],
                    region: "test".to_string(),
                    timestamp: Utc::now(),
                };
                bus.publish(msg).await.unwrap();
            })
        }).collect();

        // Wait for all producers
        for handle in handles {
            handle.await.unwrap();
        }

        let elapsed = start.elapsed();
        let metrics = bus.metrics();

        println!("Published {} messages in {:?}", metrics.messages_published, elapsed);
        println!("Rate: {} msg/sec", metrics.messages_published as f64 / elapsed.as_secs_f64());

        assert!(elapsed.as_secs() < 10, "Should handle 100K messages in <10 seconds");
    }
}
