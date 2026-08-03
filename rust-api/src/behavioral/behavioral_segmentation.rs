/// Behavioral Segmentation Module
///
/// Clusters informal workers by their behavioral patterns rather than
/// demographics. This enables targeted nudges and personalized financial
/// products.
///
/// Uses k-means-style clustering on behavioral features:
///   - Savings rate (proportion of income saved)
///   - Spending volatility (coefficient of variation)
///   - Present bias index (hyperbolic discount rate)
///   - Loss aversion coefficient
///   - Financial literacy score
///   - Risk attitude score
///   - Social engagement (chama participation, peer influence)
///
/// Reference: Mullainathan & Shafir (2013), "Scarcity: Why Having
///            Too Little Means So Much"
use serde::{Deserialize, Serialize};

/// Behavioral features extracted from worker transaction data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BehavioralFeatures {
    /// Worker identifier
    pub worker_id: String,
    /// Proportion of income saved (0.0 - 1.0)
    pub savings_rate: f64,
    /// Coefficient of variation of daily spending
    pub spending_volatility: f64,
    /// Present bias index (>1 = present biased, 1 = time-consistent)
    pub present_bias_index: f64,
    /// Loss aversion coefficient (λ, typically 2.0-2.5)
    pub loss_aversion_lambda: f64,
    /// Financial literacy score (0-100)
    pub financial_literacy: f64,
    /// Risk attitude score (-1 to 1, negative = risk averse)
    pub risk_attitude: f64,
    /// Chama participation rate (0-1)
    pub social_engagement: f64,
    /// Average transaction amount (KES)
    pub avg_transaction: f64,
    /// Transaction frequency (per week)
    pub transaction_frequency: f64,
}

/// A behavioral segment (cluster)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BehavioralSegment {
    /// Segment identifier
    pub segment_id: usize,
    /// Segment name (human-readable)
    pub name: String,
    /// Segment description
    pub description: String,
    /// Centroid features
    pub centroid: Vec<f64>,
    /// Workers in this segment
    pub worker_count: usize,
    /// Recommended nudge types for this segment
    pub recommended_nudges: Vec<String>,
    /// Risk profile
    pub risk_profile: String,
}

/// Behavioral segmentation engine
pub struct BehavioralSegmentationEngine {
    /// Number of segments (k)
    k: usize,
    /// Maximum iterations
    max_iterations: usize,
    /// Convergence threshold
    convergence_threshold: f64,
    /// Learned centroids
    centroids: Vec<Vec<f64>>,
    /// Segment definitions
    segments: Vec<BehavioralSegment>,
}

impl BehavioralSegmentationEngine {
    /// Create a new segmentation engine
    pub fn new(k: usize) -> Self {
        Self {
            k,
            max_iterations: 100,
            convergence_threshold: 0.001,
            centroids: Vec::new(),
            segments: Vec::new(),
        }
    }

    /// Create with custom settings
    pub fn with_config(k: usize, max_iterations: usize, convergence_threshold: f64) -> Self {
        Self {
            k,
            max_iterations,
            convergence_threshold,
            centroids: Vec::new(),
            segments: Vec::new(),
        }
    }

    /// Convert behavioral features to a feature vector for clustering
    fn features_to_vec(f: &BehavioralFeatures) -> Vec<f64> {
        vec![
            f.savings_rate,
            f.spending_volatility,
            f.present_bias_index,
            f.loss_aversion_lambda / 3.0, // normalize to ~0-1
            f.financial_literacy / 100.0,
            (f.risk_attitude + 1.0) / 2.0, // normalize -1..1 to 0..1
            f.social_engagement,
            (f.avg_transaction / 10000.0).min(1.0), // normalize
            (f.transaction_frequency / 20.0).min(1.0), // normalize
        ]
    }

    /// Compute Euclidean distance between two feature vectors
    fn distance(a: &[f64], b: &[f64]) -> f64 {
        a.iter()
            .zip(b.iter())
            .map(|(x, y)| (x - y).powi(2))
            .sum::<f64>()
            .sqrt()
    }

    /// Assign each worker to the nearest centroid
    fn assign_clusters(features: &[Vec<f64>], centroids: &[Vec<f64>]) -> Vec<usize> {
        features
            .iter()
            .map(|f| {
                centroids
                    .iter()
                    .enumerate()
                    .min_by(|(_, a), (_, b)| {
                        Self::distance(f, a)
                            .partial_cmp(&Self::distance(f, b))
                            .unwrap()
                    })
                    .map(|(i, _)| i)
                    .unwrap_or(0)
            })
            .collect()
    }

    /// Recompute centroids from cluster assignments
    fn update_centroids(features: &[Vec<f64>], assignments: &[usize], k: usize) -> Vec<Vec<f64>> {
        let dim = features.first().map(|f| f.len()).unwrap_or(0);
        let mut new_centroids = vec![vec![0.0; dim]; k];
        let mut counts = vec![0usize; k];

        for (f, &cluster) in features.iter().zip(assignments.iter()) {
            counts[cluster] += 1;
            for (j, val) in f.iter().enumerate() {
                new_centroids[cluster][j] += val;
            }
        }

        for (centroid, count) in new_centroids.iter_mut().zip(counts.iter()) {
            if *count > 0 {
                for val in centroid.iter_mut() {
                    *val /= *count as f64;
                }
            }
        }

        new_centroids
    }

    /// Fit the model on a set of behavioral features
    pub fn fit(&mut self, workers: &[BehavioralFeatures]) {
        if workers.is_empty() || self.k == 0 {
            return;
        }

        let features: Vec<Vec<f64>> = workers.iter().map(Self::features_to_vec).collect();

        // Initialize centroids using k-means++ style
        self.centroids = self.initialize_centroids(&features);

        // Lloyd's algorithm
        let mut assignments = Vec::new();
        for _ in 0..self.max_iterations {
            let new_assignments = Self::assign_clusters(&features, &self.centroids);

            // Check convergence
            if !assignments.is_empty()
                && assignments
                    .iter()
                    .zip(new_assignments.iter())
                    .all(|(a, b)| a == b)
            {
                break;
            }

            assignments = new_assignments;
            self.centroids = Self::update_centroids(&features, &assignments, self.k);
        }

        // Build segment definitions
        self.segments = self.build_segments(workers, &assignments);
    }

    /// Initialize centroids (k-means++ style)
    fn initialize_centroids(&self, features: &[Vec<f64>]) -> Vec<Vec<f64>> {
        if features.is_empty() {
            return Vec::new();
        }

        let dim = features[0].len();
        let mut centroids = Vec::with_capacity(self.k);

        // First centroid: random (use first feature as seed)
        centroids.push(features[0].clone());

        // Subsequent centroids: proportional to distance from nearest existing centroid
        while centroids.len() < self.k {
            let distances: Vec<f64> = features
                .iter()
                .map(|f| {
                    centroids
                        .iter()
                        .map(|c| Self::distance(f, c))
                        .min_by(|a, b| a.partial_cmp(b).unwrap())
                        .unwrap_or(0.0)
                })
                .collect();

            let total_dist: f64 = distances.iter().sum();
            if total_dist == 0.0 {
                // All points are the same, just add a slightly perturbed copy
                let mut new_centroid = features[0].clone();
                if let Some(val) = new_centroid.first_mut() {
                    *val += 0.1;
                }
                centroids.push(new_centroid);
                continue;
            }

            // Pick the point with maximum distance (deterministic k-means++)
            let max_idx = distances
                .iter()
                .enumerate()
                .max_by(|(_, a), (_, b)| a.partial_cmp(b).unwrap())
                .map(|(i, _)| i)
                .unwrap_or(0);

            centroids.push(features[max_idx].clone());
        }

        centroids
    }

    /// Build human-readable segment definitions
    fn build_segments(
        &self,
        workers: &[BehavioralFeatures],
        assignments: &[usize],
    ) -> Vec<BehavioralSegment> {
        let mut segments = Vec::new();

        for cluster_id in 0..self.k {
            let cluster_workers: Vec<&BehavioralFeatures> = workers
                .iter()
                .zip(assignments.iter())
                .filter(|(_, &c)| c == cluster_id)
                .map(|(w, _)| w)
                .collect();

            if cluster_workers.is_empty() {
                continue;
            }

            let avg_savings: f64 = cluster_workers.iter().map(|w| w.savings_rate).sum::<f64>()
                / cluster_workers.len() as f64;
            let avg_present_bias: f64 = cluster_workers
                .iter()
                .map(|w| w.present_bias_index)
                .sum::<f64>()
                / cluster_workers.len() as f64;
            let avg_risk: f64 = cluster_workers.iter().map(|w| w.risk_attitude).sum::<f64>()
                / cluster_workers.len() as f64;
            let avg_literacy: f64 = cluster_workers
                .iter()
                .map(|w| w.financial_literacy)
                .sum::<f64>()
                / cluster_workers.len() as f64;
            let avg_social: f64 = cluster_workers
                .iter()
                .map(|w| w.social_engagement)
                .sum::<f64>()
                / cluster_workers.len() as f64;

            let (name, description, nudges, risk_profile) = Self::classify_segment(
                avg_savings,
                avg_present_bias,
                avg_risk,
                avg_literacy,
                avg_social,
            );

            segments.push(BehavioralSegment {
                segment_id: cluster_id,
                name,
                description,
                centroid: self.centroids[cluster_id].clone(),
                worker_count: cluster_workers.len(),
                recommended_nudges: nudges,
                risk_profile,
            });
        }

        segments
    }

    /// Classify a segment based on its centroid features
    fn classify_segment(
        savings: f64,
        present_bias: f64,
        risk: f64,
        literacy: f64,
        social: f64,
    ) -> (String, String, Vec<String>, String) {
        let mut nudges = Vec::new();

        let name = if savings > 0.15 && literacy > 0.6 && present_bias < 1.3 {
            nudges.push("social_proof".to_string());
            nudges.push("default_effect".to_string());
            (
                "Disciplined Saver".to_string(),
                "High savings rate, good financial literacy, low present bias. Likely to respond to optimization nudges.".to_string(),
                nudges,
                "moderate".to_string(),
            )
        } else if present_bias > 2.0 && savings < 0.05 {
            nudges.push("commitment_device".to_string());
            nudges.push("loss_framing".to_string());
            nudges.push("concrete_comparison".to_string());
            (
                "Present Biased".to_string(),
                "Strong present bias, very low savings. Needs commitment devices and concrete framing to overcome immediate gratification.".to_string(),
                nudges,
                "risk_seeking".to_string(),
            )
        } else if risk < -0.3 && savings < 0.10 {
            nudges.push("framing".to_string());
            nudges.push("social_proof".to_string());
            nudges.push("simplification".to_string());
            (
                "Cautious Non-Saver".to_string(),
                "Risk-averse but doesn't save. Fear of loss prevents both investing and saving. Needs reframing.".to_string(),
                nudges,
                "risk_averse".to_string(),
            )
        } else if social > 0.5 && savings > 0.08 {
            nudges.push("social_proof".to_string());
            nudges.push("commitment_device".to_string());
            (
                "Social Saver".to_string(),
                "Active in chamas, moderate savings. Responds well to social nudges and group commitment.".to_string(),
                nudges,
                "moderate".to_string(),
            )
        } else if literacy < 0.3 {
            nudges.push("financial_literacy".to_string());
            nudges.push("simplification".to_string());
            nudges.push("concrete_comparison".to_string());
            (
                "Financial Novice".to_string(),
                "Low financial literacy, needs education before behavior change. Simple, concrete messages work best.".to_string(),
                nudges,
                "unknown".to_string(),
            )
        } else {
            nudges.push("framing".to_string());
            nudges.push("default_effect".to_string());
            (
                "Typical Worker".to_string(),
                "Average across behavioral dimensions. Standard nudge package applies.".to_string(),
                nudges,
                "moderate".to_string(),
            )
        };

        (name, description, nudges, risk_profile)
    }

    /// Predict segment for a new worker
    pub fn predict(&self, features: &BehavioralFeatures) -> Option<usize> {
        if self.centroids.is_empty() {
            return None;
        }
        let vec = Self::features_to_vec(features);
        self.centroids
            .iter()
            .enumerate()
            .min_by(|(_, a), (_, b)| {
                Self::distance(&vec, a)
                    .partial_cmp(&Self::distance(&vec, b))
                    .unwrap()
            })
            .map(|(i, _)| i)
    }

    /// Get all segments
    pub fn segments(&self) -> &[BehavioralSegment] {
        &self.segments
    }

    /// Get centroids
    pub fn centroids(&self) -> &[Vec<f64>] {
        &self.centroids
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_worker(
        id: &str,
        savings: f64,
        volatility: f64,
        present_bias: f64,
        risk: f64,
        literacy: f64,
    ) -> BehavioralFeatures {
        BehavioralFeatures {
            worker_id: id.to_string(),
            savings_rate: savings,
            spending_volatility: volatility,
            present_bias_index: present_bias,
            loss_aversion_lambda: 2.25,
            financial_literacy: literacy,
            risk_attitude: risk,
            social_engagement: 0.3,
            avg_transaction: 500.0,
            transaction_frequency: 5.0,
        }
    }

    #[test]
    fn test_segmentation_basic() {
        let workers = vec![
            // Disciplined savers
            make_worker("w1", 0.20, 0.3, 1.1, 0.0, 70.0),
            make_worker("w2", 0.18, 0.25, 1.2, 0.1, 65.0),
            make_worker("w3", 0.22, 0.35, 1.0, -0.1, 75.0),
            // Present biased
            make_worker("w4", 0.02, 0.8, 2.5, 0.5, 30.0),
            make_worker("w5", 0.01, 0.9, 2.8, 0.6, 25.0),
            make_worker("w6", 0.03, 0.7, 2.3, 0.4, 35.0),
        ];

        let mut engine = BehavioralSegmentationEngine::new(2);
        engine.fit(&workers);

        assert_eq!(engine.segments().len(), 2);
        assert!(engine.centroids().len() == 2);

        // All workers should be assigned
        for w in &workers {
            assert!(engine.predict(w).is_some());
        }
    }

    #[test]
    fn test_empty_input() {
        let mut engine = BehavioralSegmentationEngine::new(3);
        engine.fit(&[]);
        assert!(engine.segments().is_empty());
    }

    #[test]
    fn test_predict_new_worker() {
        let workers = vec![
            make_worker("w1", 0.20, 0.3, 1.1, 0.0, 70.0),
            make_worker("w2", 0.02, 0.8, 2.5, 0.5, 30.0),
        ];

        let mut engine = BehavioralSegmentationEngine::new(2);
        engine.fit(&workers);

        let new_worker = make_worker("new", 0.19, 0.28, 1.15, 0.05, 68.0);
        let segment = engine.predict(&new_worker);
        assert!(segment.is_some());
        // Should be closest to the disciplined saver
        assert_eq!(segment.unwrap(), 0);
    }
}
