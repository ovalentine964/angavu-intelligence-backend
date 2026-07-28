// rust-api/src/tests/unit/sync_verification_test.rs
//
// Tests for sync boundary verification — validates data integrity
// before accepting transactions from devices.

#[cfg(test)]
mod tests {
    use crate::sync::verification::*;
    use chrono::Utc;

    #[test]
    fn sync_verifier_valid_transaction_accepted() {
        let verifier = SyncVerifier::new();
        let request = make_sync_request(vec![
            make_transaction("sale", 500.0, "tomatoes"),
        ]);
        let device_state = make_device_state();

        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(verifier.verify_sync(&request, &device_state));

        assert_eq!(result.accepted, 1);
        assert_eq!(result.rejected, 0);
    }

    #[test]
    fn sync_verifier_invalid_category_rejected() {
        let verifier = SyncVerifier::new();
        let request = make_sync_request(vec![
            make_transaction("invalid_category", 500.0, "tomatoes"),
        ]);
        let device_state = make_device_state();

        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(verifier.verify_sync(&request, &device_state));

        assert_eq!(result.rejected, 1);
        assert!(result.rejection_reasons.iter().any(|r| r.reason.contains("category")));
    }

    #[test]
    fn sync_verifier_implausible_amount_rejected() {
        let verifier = SyncVerifier::new();
        // 10x the median for "sale" category (median=500, max=50000)
        let request = make_sync_request(vec![
            make_transaction("sale", 100_000.0, "tomatoes"),
        ]);
        let device_state = make_device_state();

        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(verifier.verify_sync(&request, &device_state));

        assert_eq!(result.rejected, 1);
    }

    #[test]
    fn sync_verifier_batch_size_limit() {
        let verifier = SyncVerifier::new();
        // Create a batch exceeding MAX_TRANSACTIONS_PER_SYNC (500)
        let transactions: Vec<_> = (0..600)
            .map(|i| make_transaction("sale", 100.0, &format!("product_{}", i)))
            .collect();
        let request = make_sync_request(transactions);
        let device_state = make_device_state();

        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(verifier.verify_sync(&request, &device_state));

        // Should reject the entire batch or flag it
        assert!(result.rejected > 0 || result.rejection_reasons.len() > 0);
    }

    #[test]
    fn sync_verifier_valid_payment_methods() {
        let verifier = SyncVerifier::new();
        let valid_methods = vec!["cash", "mpesa", "bank", "credit", "airtel"];

        for method in valid_methods {
            let mut tx = make_transaction("sale", 100.0, "test");
            tx.payment_method = method.to_string();
            let request = make_sync_request(vec![tx]);
            let device_state = make_device_state();

            let rt = tokio::runtime::Runtime::new().unwrap();
            let result = rt.block_on(verifier.verify_sync(&request, &device_state));

            assert_eq!(
                result.accepted, 1,
                "Payment method '{}' should be accepted",
                method
            );
        }
    }

    #[test]
    fn sync_verifier_invalid_payment_method_rejected() {
        let verifier = SyncVerifier::new();
        let mut tx = make_transaction("sale", 100.0, "test");
        tx.payment_method = "bitcoin".to_string();
        let request = make_sync_request(vec![tx]);
        let device_state = make_device_state();

        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(verifier.verify_sync(&request, &device_state));

        assert_eq!(result.rejected, 1);
    }

    #[test]
    fn sync_verifier_mixed_valid_invalid() {
        let verifier = SyncVerifier::new();
        let request = make_sync_request(vec![
            make_transaction("sale", 500.0, "tomatoes"),      // valid
            make_transaction("invalid", 100.0, "test"),       // invalid category
            make_transaction("expense", 200.0, "transport"),  // valid
            make_transaction("sale", 200_000.0, "test"),      // implausible amount
        ]);
        let device_state = make_device_state();

        let rt = tokio::runtime::Runtime::new().unwrap();
        let result = rt.block_on(verifier.verify_sync(&request, &device_state));

        assert_eq!(result.accepted, 2);
        assert_eq!(result.rejected, 2);
    }

    // ── Helpers ──────────────────────────────────────────────────

    fn make_transaction(category: &str, amount: f64, product: &str) -> SyncTransaction {
        SyncTransaction {
            id: uuid::Uuid::new_v4().to_string(),
            category: category.to_string(),
            amount,
            product: product.to_string(),
            payment_method: "cash".to_string(),
            timestamp: Utc::now(),
            quantity: Some(1.0),
            customer: None,
            notes: None,
        }
    }

    fn make_sync_request(transactions: Vec<SyncTransaction>) -> SyncRequest {
        SyncRequest {
            device_id: "test-device-001".to_string(),
            worker_id_hash: "test-worker-hash".to_string(),
            app_version: "1.0.0".to_string(),
            transactions,
            timestamp: Utc::now(),
        }
    }

    fn make_device_state() -> DeviceState {
        DeviceState {
            device_id: "test-device-001".to_string(),
            last_sync: Utc::now(),
            sync_count: 10,
            is_healthy: true,
        }
    }
}
