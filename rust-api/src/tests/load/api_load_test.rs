// rust-api/src/tests/load/api_load_test.rs
//
// Load tests for API endpoints using criterion benchmarks.
// Tests throughput and latency under concurrent load.

#[cfg(test)]
mod tests {
    use std::sync::Arc;
    use std::time::{Duration, Instant};
    use tokio::sync::Semaphore;

    // ════════════════════════════════════════════════════════════
    //  CONCURRENT REQUEST HANDLING
    // ════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn load_test_concurrent_message_bus_publish() {
        use crate::orchestrator::message_bus::*;

        let bus = Arc::new(ModuleMessageBus::new(MessageBusConfig::default()));
        let mut handles = vec![];

        let start = Instant::now();

        // Spawn 100 concurrent publishers
        for i in 0..100 {
            let bus_clone = Arc::clone(&bus);
            handles.push(tokio::spawn(async move {
                let msg = ModuleMessage::TransactionBatch {
                    trace_id: uuid::Uuid::new_v4(),
                    worker_id_hash: format!("worker_{}", i),
                    transactions: vec![],
                    region: "nairobi".to_string(),
                    timestamp: chrono::Utc::now(),
                };
                bus_clone.publish(msg).await.unwrap();
            }));
        }

        for handle in handles {
            handle.await.unwrap();
        }

        let elapsed = start.elapsed();
        println!("100 concurrent publishes: {:?}", elapsed);

        // Should complete within 5 seconds
        assert!(
            elapsed < Duration::from_secs(5),
            "100 concurrent publishes took too long: {:?}",
            elapsed
        );
    }

    #[tokio::test]
    async fn load_test_concurrent_subscribers() {
        use crate::orchestrator::message_bus::*;

        let bus = Arc::new(ModuleMessageBus::new(MessageBusConfig::default()));
        let mut receivers = vec![];

        // Create 50 subscribers
        for _ in 0..50 {
            receivers.push(bus.subscribe());
        }

        // Publish a message
        let msg = ModuleMessage::Heartbeat {
            module_id: ModuleId::MarketAnalyzer,
            queue_depth: 0,
            processing_rate: 100.0,
            last_error: None,
            uptime_secs: 3600,
        };

        let start = Instant::now();
        bus.publish(msg).await.unwrap();

        // All subscribers should receive within 1 second
        for mut rx in receivers {
            let received = tokio::time::timeout(Duration::from_secs(1), rx.recv()).await;
            assert!(received.is_ok(), "Subscriber should receive within timeout");
        }

        let elapsed = start.elapsed();
        println!("50 subscribers received: {:?}", elapsed);
    }

    #[tokio::test]
    async fn load_test_message_bus_throughput() {
        use crate::orchestrator::message_bus::*;

        let bus = Arc::new(ModuleMessageBus::new(MessageBusConfig::default()));
        let _rx = bus.subscribe();

        let message_count = 1000;
        let start = Instant::now();

        for i in 0..message_count {
            let msg = ModuleMessage::TransactionBatch {
                trace_id: uuid::Uuid::new_v4(),
                worker_id_hash: format!("worker_{}", i),
                transactions: vec![],
                region: "nairobi".to_string(),
                timestamp: chrono::Utc::now(),
            };
            bus.publish(msg).await.unwrap();
        }

        let elapsed = start.elapsed();
        let throughput = message_count as f64 / elapsed.as_secs_f64();

        println!("Message bus throughput: {:.0} msg/sec", throughput);
        assert!(
            throughput > 100.0,
            "Throughput should be > 100 msg/sec, got {:.0}",
            throughput
        );
    }

    // ════════════════════════════════════════════════════════════
    //  RATE LIMITER TESTS
    // ════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn load_test_rate_limiter_basic() {
        use crate::gateway::rate_limit::*;

        let limiter = RateLimiter::new(RateLimitConfig {
            requests_per_second: 10,
            burst_size: 5,
        });

        // Should allow initial burst
        for _ in 0..5 {
            assert!(limiter.check("client-1").await);
        }

        // After burst, should be rate limited
        let mut allowed = 0;
        for _ in 0..20 {
            if limiter.check("client-1").await {
                allowed += 1;
            }
        }
        assert!(
            allowed <= 10,
            "Should be rate limited after burst, allowed {}",
            allowed
        );
    }

    #[tokio::test]
    async fn load_test_rate_limiter_per_client() {
        use crate::gateway::rate_limit::*;

        let limiter = RateLimiter::new(RateLimitConfig {
            requests_per_second: 10,
            burst_size: 5,
        });

        // Different clients should have independent limits
        assert!(limiter.check("client-a").await);
        assert!(limiter.check("client-b").await);
        assert!(limiter.check("client-c").await);

        // Exhaust client-a's burst
        for _ in 0..5 {
            limiter.check("client-a").await;
        }

        // client-b should still be allowed
        assert!(limiter.check("client-b").await);
    }

    // ════════════════════════════════════════════════════════════
    //  CONCURRENT STREAM HANDLING
    // ════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn load_test_concurrent_stream_processing() {
        let semaphore = Arc::new(Semaphore::new(10)); // Max 10 concurrent
        let mut handles = vec![];

        let start = Instant::now();

        for i in 0..100 {
            let sem = Arc::clone(&semaphore);
            handles.push(tokio::spawn(async move {
                let _permit = sem.acquire().await.unwrap();
                // Simulate processing
                tokio::time::sleep(Duration::from_millis(10)).await;
                i
            }));
        }

        let mut results = vec![];
        for handle in handles {
            results.push(handle.await.unwrap());
        }

        let elapsed = start.elapsed();
        assert_eq!(results.len(), 100);

        // With 10 concurrent and 10ms each, 100 tasks should take ~100ms
        println!("100 tasks with 10 concurrency: {:?}", elapsed);
        assert!(
            elapsed < Duration::from_secs(5),
            "Concurrent processing took too long: {:?}",
            elapsed
        );
    }

    // ════════════════════════════════════════════════════════════
    //  MEMORY PRESSURE TESTS
    // ════════════════════════════════════════════════════════════

    #[tokio::test]
    async fn load_test_large_batch_processing() {
        use crate::orchestrator::message_bus::*;

        let bus = Arc::new(ModuleMessageBus::new(MessageBusConfig::default()));
        let _rx = bus.subscribe();

        // Process a large transaction batch
        let transactions: Vec<_> = (0..1000)
            .map(|i| TransactionRecord {
                id: uuid::Uuid::new_v4(),
                amount: 100.0 + i as f64,
                currency: "KES".to_string(),
                product_category: "vegetables".to_string(),
                product_name: Some("tomatoes".to_string()),
                quantity: Some(5.0),
                unit: Some("kg".to_string()),
                payment_method: "cash".to_string(),
                timestamp: chrono::Utc::now(),
                confidence_score: 0.9,
            })
            .collect();

        let msg = ModuleMessage::TransactionBatch {
            trace_id: uuid::Uuid::new_v4(),
            worker_id_hash: "load-test-worker".to_string(),
            transactions,
            region: "nairobi".to_string(),
            timestamp: chrono::Utc::now(),
        };

        let start = Instant::now();
        bus.publish(msg).await.unwrap();
        let elapsed = start.elapsed();

        println!("1000-transaction batch publish: {:?}", elapsed);
        assert!(
            elapsed < Duration::from_secs(1),
            "Large batch publish took too long: {:?}",
            elapsed
        );
    }
}
