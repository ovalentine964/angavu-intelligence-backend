// credit/worker_type_detector.rs

use super::types::{WorkerType, WorkerTypeDetection, DetectionSignal};
use crate::loops::credit_feedback::CreditFeatures;

/// Detects worker type (12 archetypes) from transaction patterns.
/// No manual input required — purely data-driven.
///
/// Detection signals are organized by archetype:
/// - Vendor: high counterparty diversity, small transaction sizes
/// - FoodService: ingredient purchases, fuel purchases (charcoal/gas)
/// - Artisan: material purchases + project-based income
/// - ServiceProvider: appointment patterns, service pricing
/// - TransportOperator: fuel purchases, route-based fares
/// - CropFarmer: periodic income spikes, input purchases
/// - LivestockKeeper: daily production patterns, feed purchases
/// - Fisher: catch patterns, lake/ocean keywords
/// - AgentBroker: float turnover, commission patterns
/// - DigitalWorker: platform payments, internet costs
/// - CasualLaborer: irregular wage payments, few payers
/// - CommunityCareWorker: event-based income, equipment purchases
pub struct WorkerTypeDetector {
    /// Thresholds for each detection signal
    config: DetectorConfig,
}

struct DetectorConfig {
    /// Minimum unique counterparties for vendor classification
    vendor_min_counterparties: u32,
    /// Fuel purchase frequency threshold for transport
    transport_fuel_frequency: f64,
    /// Income periodicity threshold for farmer
    farmer_periodicity_threshold: f64,
    /// Float turnover threshold for agent/broker
    agent_float_turnover: f64,
    /// Material purchase frequency threshold for artisan
    artisan_material_frequency: f64,
    /// Feed purchase frequency threshold for livestock
    livestock_feed_frequency: f64,
    /// Small transaction ratio threshold for vendor
    vendor_small_txn_ratio: f64,
    /// Irregular wage pattern threshold for casual laborer
    casual_irregular_threshold: f64,
}

impl Default for DetectorConfig {
    fn default() -> Self {
        Self {
            vendor_min_counterparties: 20,
            transport_fuel_frequency: 0.7,      // 70% of days have fuel purchases
            farmer_periodicity_threshold: 0.6,
            agent_float_turnover: 3.0,           // 3x daily float turnover
            artisan_material_frequency: 0.2,      // 20% of transactions are materials
            livestock_feed_frequency: 0.5,        // 50% of days have feed purchases
            vendor_small_txn_ratio: 0.6,          // 60% of transactions < 500 KES
            casual_irregular_threshold: 0.5,      // high revenue volatility
        }
    }
}

impl WorkerTypeDetector {
    pub fn new() -> Self {
        Self { config: DetectorConfig::default() }
    }

    /// Classify worker from base features + raw transaction metadata
    pub fn detect(
        &self,
        features: &CreditFeatures,
        transaction_meta: &TransactionMetadata,
    ) -> WorkerTypeDetection {
        let mut signals = Vec::new();
        let mut scores: std::collections::HashMap<WorkerType, f64> = 
            std::collections::HashMap::new();

        // ─── Signal 1: High unique counterparty count + small transactions → Vendor ───
        if features.transaction_count_90d > 100 {
            let counterparty_ratio = transaction_meta.unique_counterparties as f64 
                / features.transaction_count_90d as f64;
            if counterparty_ratio > 0.5 {
                *scores.entry(WorkerType::Vendor).or_insert(0.0) += 0.3;
                *scores.entry(WorkerType::MarketVendor).or_insert(0.0) += 0.4;
                signals.push(DetectionSignal {
                    signal_name: "high_counterparty_diversity".to_string(),
                    weight: 0.4,
                    value: format!("{:.0}%", counterparty_ratio * 100.0),
                });
            }
        }

        // Small transaction ratio → Vendor
        if transaction_meta.small_transaction_ratio > self.config.vendor_small_txn_ratio {
            *scores.entry(WorkerType::Vendor).or_insert(0.0) += 0.2;
            signals.push(DetectionSignal {
                signal_name: "small_transaction_ratio".to_string(),
                weight: 0.2,
                value: format!("{:.0}%", transaction_meta.small_transaction_ratio * 100.0),
            });
        }

        // ─── Signal 2: Regular fuel purchases → Transport Operator ───
        if transaction_meta.fuel_purchase_frequency > self.config.transport_fuel_frequency {
            *scores.entry(WorkerType::TransportOperator).or_insert(0.0) += 0.5;
            *scores.entry(WorkerType::BodaBodaRider).or_insert(0.0) += 0.6;
            signals.push(DetectionSignal {
                signal_name: "fuel_purchase_pattern".to_string(),
                weight: 0.6,
                value: format!("{:.0}% of days", transaction_meta.fuel_purchase_frequency * 100.0),
            });
        }

        // ─── Signal 3: Periodic income spikes → Farmer or Fisher ───
        if transaction_meta.income_periodicity_score > self.config.farmer_periodicity_threshold {
            if transaction_meta.product_categories.contains(&"fish".to_string()) 
                || transaction_meta.product_categories.contains(&"samaki".to_string()) {
                *scores.entry(WorkerType::Fisher).or_insert(0.0) += 0.5;
                *scores.entry(WorkerType::Fisherman).or_insert(0.0) += 0.5;
            } else {
                *scores.entry(WorkerType::CropFarmer).or_insert(0.0) += 0.5;
                *scores.entry(WorkerType::Farmer).or_insert(0.0) += 0.5;
            }
            signals.push(DetectionSignal {
                signal_name: "periodic_income_pattern".to_string(),
                weight: 0.5,
                value: format!("periodicity={:.2}", transaction_meta.income_periodicity_score),
            });
        }

        // ─── Signal 4: Float turnover pattern → Agent/Broker ───
        if transaction_meta.float_turnover_ratio > self.config.agent_float_turnover {
            *scores.entry(WorkerType::AgentBroker).or_insert(0.0) += 0.6;
            *scores.entry(WorkerType::MpesaAgent).or_insert(0.0) += 0.7;
            signals.push(DetectionSignal {
                signal_name: "high_float_turnover".to_string(),
                weight: 0.7,
                value: format!("{:.1}x daily turnover", transaction_meta.float_turnover_ratio),
            });
        }

        // ─── Signal 5: Irregular large payments from few sources → Casual Laborer ───
        if transaction_meta.avg_transaction_size > 1000.0 
            && transaction_meta.unique_counterparties < 5
            && features.revenue_volatility > self.config.casual_irregular_threshold {
            *scores.entry(WorkerType::CasualLaborer).or_insert(0.0) += 0.4;
            *scores.entry(WorkerType::ConstructionWorker).or_insert(0.0) += 0.4;
            signals.push(DetectionSignal {
                signal_name: "irregular_wage_pattern".to_string(),
                weight: 0.4,
                value: "few_payers_high_variance".to_string(),
            });
        }

        // ─── Signal 6: Material purchases + project-based income → Artisan ───
        if transaction_meta.material_purchase_frequency > self.config.artisan_material_frequency 
            && features.revenue_volatility > 0.4 {
            *scores.entry(WorkerType::Artisan).or_insert(0.0) += 0.4;
            *scores.entry(WorkerType::JuaKaliArtisan).or_insert(0.0) += 0.4;
            signals.push(DetectionSignal {
                signal_name: "material_project_pattern".to_string(),
                weight: 0.4,
                value: format!("material_freq={:.0}%", transaction_meta.material_purchase_frequency * 100.0),
            });
        }

        // ─── Signal 7: Feed purchases + daily production → Livestock Keeper ───
        if transaction_meta.feed_purchase_frequency > self.config.livestock_feed_frequency {
            *scores.entry(WorkerType::LivestockKeeper).or_insert(0.0) += 0.5;
            signals.push(DetectionSignal {
                signal_name: "feed_purchase_pattern".to_string(),
                weight: 0.5,
                value: format!("{:.0}% of days", transaction_meta.feed_purchase_frequency * 100.0),
            });
        }

        // ─── Signal 8: Ingredient purchases + cooking fuel → Food Service ───
        if transaction_meta.ingredient_purchase_frequency > 0.3
            && transaction_meta.cooking_fuel_frequency > 0.3 {
            *scores.entry(WorkerType::FoodService).or_insert(0.0) += 0.5;
            signals.push(DetectionSignal {
                signal_name: "food_service_pattern".to_string(),
                weight: 0.5,
                value: format!("ingredients={:.0}%, fuel={:.0}%", 
                    transaction_meta.ingredient_purchase_frequency * 100.0,
                    transaction_meta.cooking_fuel_frequency * 100.0),
            });
        }

        // ─── Signal 9: Platform payments + internet costs → Digital Worker ───
        if transaction_meta.platform_payment_frequency > 0.2
            && transaction_meta.internet_cost_frequency > 0.1 {
            *scores.entry(WorkerType::DigitalWorker).or_insert(0.0) += 0.4;
            signals.push(DetectionSignal {
                signal_name: "digital_platform_pattern".to_string(),
                weight: 0.4,
                value: format!("platform={:.0}%, internet={:.0}%",
                    transaction_meta.platform_payment_frequency * 100.0,
                    transaction_meta.internet_cost_frequency * 100.0),
            });
        }

        // ─── Signal 10: Service pricing patterns → Service Provider ───
        if transaction_meta.service_pricing_frequency > 0.3
            && features.revenue_volatility < 0.4 {
            *scores.entry(WorkerType::ServiceProvider).or_insert(0.0) += 0.4;
            signals.push(DetectionSignal {
                signal_name: "service_pricing_pattern".to_string(),
                weight: 0.4,
                value: format!("service_freq={:.0}%", transaction_meta.service_pricing_frequency * 100.0),
            });
        }

        // ─── Signal 11: Event-based irregular income → Community/Care Worker ───
        if transaction_meta.event_income_frequency > 0.1
            && features.revenue_volatility > 0.6 {
            *scores.entry(WorkerType::CommunityCareWorker).or_insert(0.0) += 0.3;
            signals.push(DetectionSignal {
                signal_name: "event_income_pattern".to_string(),
                weight: 0.3,
                value: format!("event_freq={:.0}%", transaction_meta.event_income_frequency * 100.0),
            });
        }

        // Select highest scoring type
        let (best_type, best_score) = scores.iter()
            .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
            .map(|(t, s)| (*t, *s))
            .unwrap_or((WorkerType::Generic, 0.0));

        let confidence = best_score.min(1.0);

        // If confidence < 0.6, fall back to Generic
        let final_type = if confidence < 0.6 {
            WorkerType::Generic
        } else {
            best_type
        };

        WorkerTypeDetection {
            worker_type: final_type,
            confidence,
            signals,
        }
    }
}

/// Metadata extracted from raw transaction stream
/// (before feature engineering, used for type detection)
pub struct TransactionMetadata {
    pub unique_counterparties: u32,
    pub fuel_purchase_frequency: f64,
    pub income_periodicity_score: f64,
    pub float_turnover_ratio: f64,
    pub avg_transaction_size: f64,
    pub material_purchase_frequency: f64,
    pub product_categories: Vec<String>,
    /// Fraction of transactions < 500 KES (vendor signal)
    pub small_transaction_ratio: f64,
    /// Fraction of days with animal feed purchases (livestock signal)
    pub feed_purchase_frequency: f64,
    /// Fraction of transactions for ingredients (food service signal)
    pub ingredient_purchase_frequency: f64,
    /// Fraction of days with cooking fuel purchases (food service signal)
    pub cooking_fuel_frequency: f64,
    /// Fraction of transactions from digital platforms (digital worker signal)
    pub platform_payment_frequency: f64,
    /// Fraction of transactions for internet/data costs (digital worker signal)
    pub internet_cost_frequency: f64,
    /// Fraction of transactions with service-type pricing patterns
    pub service_pricing_frequency: f64,
    /// Fraction of income from irregular event-based payments
    pub event_income_frequency: f64,
}

// ═══════════════════════════════════════════════════════════════
// k-means Clustering Enhancement for Worker Type Detection
// ═══════════════════════════════════════════════════════════════

/// k-means clustering for unsupervised worker type discovery.
///
/// Uses Lloyd's algorithm with k-means++ initialization to cluster
/// worker profiles into behavioral groups without labels.
/// Complements the rule-based `WorkerTypeDetector` by discovering
/// natural groupings in the data.
///
/// Academic reference: STA 343 (Multivariate Analysis)
/// Algorithm: Lloyd's k-means with k-means++ initialization
///   1. Initialize centroids via k-means++ (distance-weighted sampling)
///   2. Assign each point to nearest centroid
///   3. Update centroids to cluster means
///   4. Repeat until convergence
pub struct KMeansClusterer {
    k: usize,
    max_iterations: usize,
    tolerance: f64,
}

impl KMeansClusterer {
    /// Create a new k-means clusterer.
    ///
    /// # Arguments
    /// * `k` - Number of clusters
    /// * `max_iterations` - Maximum iterations (default 100)
    /// * `tolerance` - Convergence tolerance (default 1e-6)
    pub fn new(k: usize, max_iterations: usize, tolerance: f64) -> Self {
        Self { k, max_iterations, tolerance }
    }

    /// Fit k-means to feature matrix (n workers × p features).
    ///
    /// Returns cluster assignments and centroids.
    pub fn fit(&self, data: &[Vec<f64>]) -> KMeansResult {
        let n = data.len();
        let p = data[0].len();
        let k = self.k.min(n);

        // k-means++ initialization
        let mut centroids = self.kmeans_pp_init(data, k);
        let mut assignments = vec![0usize; n];

        for _iter in 0..self.max_iterations {
            // Assignment step
            let mut changed = false;
            for i in 0..n {
                let nearest = (0..k)
                    .min_by(|&a, &b| {
                        euclidean_dist(&data[i], &centroids[a])
                            .partial_cmp(&euclidean_dist(&data[i], &centroids[b]))
                            .unwrap_or(std::cmp::Ordering::Equal)
                    })
                    .unwrap_or(0);
                if nearest != assignments[i] {
                    assignments[i] = nearest;
                    changed = true;
                }
            }

            if !changed {
                break;
            }

            // Update step
            for c in 0..k {
                let members: Vec<usize> = (0..n).filter(|&i| assignments[i] == c).collect();
                if !members.is_empty() {
                    for j in 0..p {
                        centroids[c][j] = members.iter().map(|&i| data[i][j]).sum::<f64>()
                            / members.len() as f64;
                    }
                }
            }
        }

        // Compute WCSS
        let wcss: f64 = (0..n)
            .map(|i| euclidean_dist_sq(&data[i], &centroids[assignments[i]]))
            .sum();

        // Cluster sizes
        let mut cluster_sizes = vec![0usize; k];
        for &a in &assignments {
            cluster_sizes[a] += 1;
        }

        KMeansResult {
            k,
            assignments,
            centroids,
            cluster_sizes,
            wcss,
            iterations: self.max_iterations,
        }
    }

    /// k-means++ initialization: distance-weighted centroid selection.
    fn kmeans_pp_init(&self, data: &[Vec<f64>], k: usize) -> Vec<Vec<f64>> {
        let n = data.len();
        let p = data[0].len();
        let mut centroids = Vec::with_capacity(k);

        // First centroid: random (use index 0 as seed)
        centroids.push(data[0].clone());

        for _ in 1..k {
            // Compute distances to nearest existing centroid
            let dists: Vec<f64> = data
                .iter()
                .map(|point| {
                    centroids
                        .iter()
                        .map(|c| euclidean_dist_sq(point, c))
                        .fold(f64::INFINITY, f64::min)
                })
                .collect();

            // Select proportional to distance²
            let total: f64 = dists.iter().sum();
            if total < 1e-15 {
                // All points are the same, pick next index
                centroids.push(data[centroids.len() % n].clone());
                continue;
            }

            // Deterministic: pick the point with maximum distance
            let max_idx = dists
                .iter()
                .enumerate()
                .max_by(|a, b| a.1.partial_cmp(b.1).unwrap_or(std::cmp::Ordering::Equal))
                .map(|(i, _)| i)
                .unwrap_or(0);
            centroids.push(data[max_idx].clone());
        }

        centroids
    }
}

/// Result from k-means clustering.
#[derive(Debug, Clone)]
pub struct KMeansResult {
    pub k: usize,
    pub assignments: Vec<usize>,
    pub centroids: Vec<Vec<f64>>,
    pub cluster_sizes: Vec<usize>,
    pub wcss: f64,
    pub iterations: usize,
}

impl KMeansResult {
    /// Get the cluster assignment for a specific worker.
    pub fn cluster_of(&self, worker_idx: usize) -> Option<usize> {
        self.assignments.get(worker_idx).copied()
    }

    /// Get all worker indices in a specific cluster.
    pub fn members_of(&self, cluster: usize) -> Vec<usize> {
        self.assignments
            .iter()
            .enumerate()
            .filter(|(_, &c)| c == cluster)
            .map(|(i, _)| i)
            .collect()
    }

    /// Compute silhouette score for cluster quality assessment.
    /// Returns value in [-1, 1] where higher is better.
    pub fn silhouette_score(&self, data: &[Vec<f64>]) -> f64 {
        let n = data.len();
        if n < 2 || self.k < 2 {
            return 0.0;
        }

        let mut total_score = 0.0;
        for i in 0..n {
            let my_cluster = self.assignments[i];

            // a(i): mean distance to same cluster
            let same_cluster: Vec<usize> = (0..n)
                .filter(|&j| j != i && self.assignments[j] == my_cluster)
                .collect();
            let a_i = if same_cluster.is_empty() {
                0.0
            } else {
                same_cluster.iter().map(|&j| euclidean_dist(&data[i], &data[j])).sum::<f64>()
                    / same_cluster.len() as f64
            };

            // b(i): min mean distance to other clusters
            let b_i = (0..self.k)
                .filter(|&c| c != my_cluster)
                .map(|c| {
                    let others: Vec<usize> = (0..n)
                        .filter(|&j| self.assignments[j] == c)
                        .collect();
                    if others.is_empty() {
                        f64::INFINITY
                    } else {
                        others.iter().map(|&j| euclidean_dist(&data[i], &data[j])).sum::<f64>()
                            / others.len() as f64
                    }
                })
                .fold(f64::INFINITY, f64::min);

            let s_i = if a_i.max(b_i) > 0.0 {
                (b_i - a_i) / a_i.max(b_i)
            } else {
                0.0
            };
            total_score += s_i;
        }

        total_score / n as f64
    }
}

/// Euclidean distance between two points.
fn euclidean_dist(a: &[f64], b: &[f64]) -> f64 {
    a.iter()
        .zip(b.iter())
        .map(|(x, y)| (x - y).powi(2))
        .sum::<f64>()
        .sqrt()
}

/// Squared Euclidean distance.
fn euclidean_dist_sq(a: &[f64], b: &[f64]) -> f64 {
    a.iter()
        .zip(b.iter())
        .map(|(x, y)| (x - y).powi(2))
        .sum()
}
