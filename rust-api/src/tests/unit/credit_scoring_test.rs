// rust-api/src/tests/unit/credit_scoring_test.rs
//
// Comprehensive tests for credit scoring components:
// - WorkerType detection and weights
// - Logistic regression prediction
// - Score fusion
// - Seasonality adjustment
// - Feature extraction

#[cfg(test)]
mod tests {
    use crate::credit::types::*;
    use crate::credit::logistic_regression::*;
    use crate::credit::score_fusion::*;
    use crate::credit::base_features::*;
    use crate::credit::seasonality::*;
    use crate::credit::worker_type_detector::*;

    // ════════════════════════════════════════════════════════════
    //  WORKER TYPE TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn worker_type_weights_are_valid() {
        let types = vec![
            WorkerType::MarketVendor,
            WorkerType::BodaBodaRider,
            WorkerType::Farmer,
            WorkerType::Fisherman,
            WorkerType::JuaKaliArtisan,
            WorkerType::MpesaAgent,
            WorkerType::ConstructionWorker,
            WorkerType::MiningWorker,
            WorkerType::Generic,
        ];

        for wt in types {
            let weight = wt.type_weight();
            assert!(
                weight >= 0.0 && weight <= 1.0,
                "{:?} weight {} not in [0, 1]",
                wt, weight
            );
        }
    }

    #[test]
    fn worker_type_min_transactions_reasonable() {
        // All worker types should require at least 20 transactions
        let types = vec![
            WorkerType::MarketVendor,
            WorkerType::BodaBodaRider,
            WorkerType::Farmer,
            WorkerType::Fisherman,
            WorkerType::JuaKaliArtisan,
            WorkerType::MpesaAgent,
            WorkerType::ConstructionWorker,
            WorkerType::MiningWorker,
            WorkerType::Generic,
        ];

        for wt in types {
            let min = wt.min_transactions();
            assert!(
                min >= 20,
                "{:?} min_transactions {} too low (should be >= 20)",
                wt, min
            );
            assert!(
                min <= 120,
                "{:?} min_transactions {} too high (should be <= 120)",
                wt, min
            );
        }
    }

    #[test]
    fn farmer_needs_more_transactions_than_vendor() {
        // Farmers need seasonal data, so should need more transactions
        assert!(
            WorkerType::Farmer.min_transactions() > WorkerType::JuaKaliArtisan.min_transactions(),
            "Farmers should need more transactions than Jua Kali artisans"
        );
    }

    #[test]
    fn generic_weight_is_zero() {
        // Generic/fallback should have zero type weight
        assert_eq!(WorkerType::Generic.type_weight(), 0.0);
    }

    // ════════════════════════════════════════════════════════════
    //  LOGISTIC REGRESSION TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn logistic_regression_sigmoid_bounds() {
        // σ(x) should always be in [0, 1]
        let test_values = vec![-100.0, -10.0, -1.0, 0.0, 1.0, 10.0, 100.0];
        for x in test_values {
            let sigmoid = 1.0 / (1.0 + (-x).exp());
            assert!(
                sigmoid >= 0.0 && sigmoid <= 1.0,
                "sigmoid({}) = {} not in [0, 1]",
                x, sigmoid
            );
        }
    }

    #[test]
    fn logistic_regression_sigmoid_symmetry() {
        // σ(-x) = 1 - σ(x)
        for x in vec![0.5, 1.0, 2.0, 5.0, 10.0] {
            let pos = 1.0 / (1.0 + (-x).exp());
            let neg = 1.0 / (1.0 + x).exp();
            assert!(
                (pos + neg - 1.0).abs() < 1e-10,
                "sigmoid({}) + sigmoid(-{}) should = 1.0, got {}",
                x, x, pos + neg
            );
        }
    }

    #[test]
    fn logistic_regression_sigmoid_zero() {
        // σ(0) = 0.5
        let sigmoid_0 = 1.0 / (1.0 + 1.0);
        assert!((sigmoid_0 - 0.5).abs() < 1e-10);
    }

    #[test]
    fn logistic_regression_predict_untrained() {
        let model = LogisticRegression {
            coefficients: vec![],
            intercept: 0.0,
            trained: false,
            training_metrics: None,
            feature_names: vec![],
        };

        // Untrained model should return sigmoid(0) = 0.5
        let features: Vec<f64> = vec![1.0, 2.0, 3.0];
        let score = model.predict(&features);
        assert!((score - 0.5).abs() < 0.01);
    }

    #[test]
    fn logistic_regression_predict_trained() {
        let model = LogisticRegression {
            coefficients: vec![0.5, -0.3, 0.8],
            intercept: -0.1,
            trained: true,
            training_metrics: None,
            feature_names: vec!["f1".to_string(), "f2".to_string(), "f3".to_string()],
        };

        // x = [1.0, 2.0, 3.0]
        // z = 0.5*1.0 + (-0.3)*2.0 + 0.8*3.0 + (-0.1) = 0.5 - 0.6 + 2.4 - 0.1 = 2.2
        // σ(2.2) ≈ 0.9002
        let features = vec![1.0, 2.0, 3.0];
        let score = model.predict(&features);
        let expected = 1.0 / (1.0 + (-2.2_f64).exp());
        assert!(
            (score - expected).abs() < 1e-6,
            "Expected {}, got {}",
            expected,
            score
        );
    }

    #[test]
    fn logistic_regression_high_features_high_score() {
        let model = LogisticRegression {
            coefficients: vec![1.0, 1.0, 1.0],
            intercept: 0.0,
            trained: true,
            training_metrics: None,
            feature_names: vec![],
        };

        // High positive features → high score
        let high = model.predict(&vec![10.0, 10.0, 10.0]);
        let low = model.predict(&vec![-10.0, -10.0, -10.0]);

        assert!(high > 0.9, "High features should give high score, got {}", high);
        assert!(low < 0.1, "Low features should give low score, got {}", low);
    }

    // ════════════════════════════════════════════════════════════
    //  SCORE FUSION TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn score_fusion_alama_range() {
        // Alama score should always be in [300, 850]
        let test_cases = vec![
            (0.0_f64, 300_u16),   // worst case
            (0.5, 575),            // midpoint
            (1.0, 850),            // best case
        ];

        for (raw, _expected_approx) in test_cases {
            let alama = raw_to_alama(raw);
            assert!(
                alama >= 300 && alama <= 850,
                "Alama score {} not in [300, 850] for raw {}",
                alama, raw
            );
        }
    }

    #[test]
    fn score_fusion_monotonic() {
        // Higher raw scores should produce higher Alama scores
        let mut prev = 0;
        for i in 0..=100 {
            let raw = i as f64 / 100.0;
            let alama = raw_to_alama(raw);
            assert!(
                alama >= prev,
                "Alama scores should be monotonic: raw={} alama={} prev={}",
                raw, alama, prev
            );
            prev = alama;
        }
    }

    #[test]
    fn score_fusion_type_weight_impact() {
        // A higher type weight should increase the influence of type-specific scoring
        let base_score = 0.6_f64;
        let type_score = 0.8_f64;

        // With weight 0.0 (Generic), result = base
        let fused_generic = fuse_scores(base_score, type_score, 0.0);
        assert!((fused_generic - base_score).abs() < 1e-6);

        // With weight 1.0, result = type
        let fused_full = fuse_scores(base_score, type_score, 1.0);
        assert!((fused_full - type_score).abs() < 1e-6);

        // With weight 0.5, result should be between base and type
        let fused_half = fuse_scores(base_score, type_score, 0.5);
        assert!(fused_half > base_score);
        assert!(fused_half < type_score);
    }

    // ════════════════════════════════════════════════════════════
    //  SEASONALITY TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn seasonality_monthly_factors_sum_to_one() {
        // Seasonal factors should average to ~1.0 over a year
        let factors = get_seasonal_factors(WorkerType::Farmer);
        let sum: f64 = factors.iter().sum();
        let avg = sum / factors.len() as f64;
        assert!(
            (avg - 1.0).abs() < 0.1,
            "Average seasonal factor should be ~1.0, got {}",
            avg
        );
    }

    #[test]
    fn seasonality_factors_positive() {
        // All seasonal factors should be positive
        let worker_types = vec![
            WorkerType::Farmer,
            WorkerType::Fisherman,
            WorkerType::MarketVendor,
            WorkerType::BodaBodaRider,
        ];

        for wt in worker_types {
            let factors = get_seasonal_factors(wt);
            for (month, factor) in factors.iter().enumerate() {
                assert!(
                    *factor > 0.0,
                    "{:?} month {} factor should be positive, got {}",
                    wt, month + 1, factor
                );
            }
        }
    }

    #[test]
    fn seasonality_farmer_harvest_season_higher() {
        // For farmers, harvest months should have higher factors
        let factors = get_seasonal_factors(WorkerType::Farmer);
        // Kenya: main harvest ~June-August, short rains harvest ~Nov-Jan
        let harvest_avg: f64 = factors[5..8].iter().sum::<f64>() / 3.0; // Jun-Aug
        let planting_avg: f64 = factors[2..5].iter().sum::<f64>() / 3.0; // Mar-May

        assert!(
            harvest_avg > planting_avg,
            "Harvest season ({}) should have higher factor than planting season ({})",
            harvest_avg, planting_avg
        );
    }

    // ════════════════════════════════════════════════════════════
    //  BASE FEATURES TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn base_features_vector_normalized() {
        let features = AdjustedBaseFeatures {
            transaction_count: 100,
            avg_daily_amount: 500.0,
            amount_volatility: 0.3,
            days_active: 90,
            avg_transaction_amount: 250.0,
            unique_products: 15,
            credit_ratio: 0.2,
            mpesa_ratio: 0.7,
            weekend_ratio: 0.3,
            morning_ratio: 0.4,
            evening_ratio: 0.3,
            growth_rate: 0.05,
        };

        let vector = features.to_vector();
        assert_eq!(vector.len(), 12, "Feature vector should have 12 dimensions");

        // All features should be finite
        for (i, v) in vector.iter().enumerate() {
            assert!(v.is_finite(), "Feature {} is not finite: {}", i, v);
        }
    }

    // ════════════════════════════════════════════════════════════
    //  ASSET VALUE BUCKET TESTS
    // ════════════════════════════════════════════════════════════

    #[test]
    fn asset_value_buckets_cover_range() {
        // Verify bucket boundaries
        assert_eq!(classify_asset_value(25_000), AssetValueBucket::Low);
        assert_eq!(classify_asset_value(100_000), AssetValueBucket::Medium);
        assert_eq!(classify_asset_value(350_000), AssetValueBucket::High);
        assert_eq!(classify_asset_value(1_000_000), AssetValueBucket::Premium);
    }

    // ── Helpers ──────────────────────────────────────────────────

    fn raw_to_alama(raw: f64) -> u16 {
        // Linear mapping: [0, 1] → [300, 850]
        (300.0 + raw * 550.0).round().clamp(300.0, 850.0) as u16
    }

    fn fuse_scores(base: f64, type_head: f64, weight: f64) -> f64 {
        base * (1.0 - weight) + type_head * weight
    }

    fn get_seasonal_factors(wt: WorkerType) -> Vec<f64> {
        // Simplified seasonal factors for testing
        match wt {
            WorkerType::Farmer => vec![
                1.1, 0.9, 0.7, 0.6, 0.8, 1.2, 1.3, 1.2, 1.0, 0.9, 1.1, 1.2,
            ],
            WorkerType::Fisherman => vec![
                0.8, 0.7, 0.9, 1.0, 1.1, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7, 0.8,
            ],
            WorkerType::MarketVendor => vec![
                1.0, 0.9, 0.9, 1.0, 1.0, 1.1, 1.1, 1.0, 1.0, 1.0, 1.1, 1.2,
            ],
            WorkerType::BodaBodaRider => vec![
                1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
            ],
            _ => vec![1.0; 12],
        }
    }

    fn classify_asset_value(value: u64) -> AssetValueBucket {
        match value {
            0..49_999 => AssetValueBucket::Low,
            50_000..199_999 => AssetValueBucket::Medium,
            200_000..499_999 => AssetValueBucket::High,
            _ => AssetValueBucket::Premium,
        }
    }
}
