//! Queuing Theory — M/M/1 and M/M/c Models.
//!
//! Models for request scheduling, customer service, and resource planning.
//!
//! M/M/1: Single server, Poisson arrivals, exponential service times.
//! M/M/c: Multiple servers (e.g., parallel API workers).
//!
//! Use cases:
//! - API request scheduling and capacity planning
//! - Customer service staffing
//! - Transaction processing throughput

use serde::{Deserialize, Serialize};

/// Statistics for a queuing system.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueueStats {
    /// Average number of customers in system (L)
    pub avg_customers_in_system: f64,
    /// Average number of customers in queue (Lq)
    pub avg_customers_in_queue: f64,
    /// Average time in system (W) — wait + service
    pub avg_time_in_system: f64,
    /// Average time in queue (Wq) — wait only
    pub avg_time_in_queue: f64,
    /// Server utilization (ρ)
    pub utilization: f64,
    /// Probability system is empty (P0)
    pub prob_idle: f64,
    /// Probability of waiting (all servers busy)
    pub prob_waiting: f64,
}

/// M/M/1 Queue — Single server model.
///
/// Arrivals: Poisson(λ), Service: Exponential(μ)
/// Stability requires: ρ = λ/μ < 1
#[derive(Debug, Clone)]
pub struct MM1Queue {
    /// Arrival rate (λ) — customers per unit time
    pub arrival_rate: f64,
    /// Service rate (μ) — customers per unit time per server
    pub service_rate: f64,
}

impl MM1Queue {
    /// Create a new M/M/1 queue.
    pub fn new(arrival_rate: f64, service_rate: f64) -> Self {
        Self { arrival_rate, service_rate }
    }

    /// Compute queue statistics.
    /// Returns None if system is unstable (ρ ≥ 1).
    pub fn stats(&self) -> Option<QueueStats> {
        let lambda = self.arrival_rate;
        let mu = self.service_rate;

        if mu <= 0.0 || lambda < 0.0 {
            return None;
        }

        let rho = lambda / mu;

        if rho >= 1.0 {
            return None; // Unstable queue
        }

        let l = rho / (1.0 - rho);            // Avg customers in system
        let lq = rho * rho / (1.0 - rho);     // Avg customers in queue
        let w = 1.0 / (mu - lambda);           // Avg time in system
        let wq = rho / (mu - lambda);          // Avg time in queue

        Some(QueueStats {
            avg_customers_in_system: l,
            avg_customers_in_queue: lq,
            avg_time_in_system: w,
            avg_time_in_queue: wq,
            utilization: rho,
            prob_idle: 1.0 - rho,
            prob_waiting: rho, // In M/M/1, prob of waiting = utilization
        })
    }

    /// Probability of exactly k customers in system.
    pub fn prob_k_customers(&self, k: usize) -> Option<f64> {
        let rho = self.arrival_rate / self.service_rate;
        if rho >= 1.0 {
            return None;
        }
        Some((1.0 - rho) * rho.powi(k as i32))
    }

    /// Probability of more than k customers in system.
    pub fn prob_more_than_k(&self, k: usize) -> Option<f64> {
        let rho = self.arrival_rate / self.service_rate;
        if rho >= 1.0 {
            return None;
        }
        Some(rho.powi((k + 1) as i32))
    }

    /// Percentile of time spent in system.
    /// P(W ≤ t) = 1 - e^(-(μ-λ)t)
    pub fn time_percentile(&self, percentile: f64) -> Option<f64> {
        let rho = self.arrival_rate / self.service_rate;
        if rho >= 1.0 || percentile <= 0.0 || percentile >= 1.0 {
            return None;
        }
        let mu_minus_lambda = self.service_rate - self.arrival_rate;
        Some(-(1.0 - percentile).ln() / mu_minus_lambda)
    }
}

/// M/M/c Queue — Multiple server model.
///
/// Arrivals: Poisson(λ), Service: Exponential(μ), c servers
/// Stability requires: ρ = λ/(c*μ) < 1
#[derive(Debug, Clone)]
pub struct MMcQueue {
    /// Arrival rate (λ)
    pub arrival_rate: f64,
    /// Service rate per server (μ)
    pub service_rate: f64,
    /// Number of servers (c)
    pub num_servers: usize,
}

impl MMcQueue {
    /// Create a new M/M/c queue.
    pub fn new(arrival_rate: f64, service_rate: f64, num_servers: usize) -> Self {
        Self {
            arrival_rate,
            service_rate,
            num_servers: num_servers.max(1),
        }
    }

    /// Compute queue statistics.
    pub fn stats(&self) -> Option<QueueStats> {
        let lambda = self.arrival_rate;
        let mu = self.service_rate;
        let c = self.num_servers;

        if mu <= 0.0 || lambda < 0.0 || c == 0 {
            return None;
        }

        let rho = lambda / (c as f64 * mu);
        if rho >= 1.0 {
            return None; // Unstable
        }

        // Erlang C formula: probability of waiting
        let a = lambda / mu; // offered load (Erlangs)

        // Compute P0 (probability all servers idle)
        let p0 = self.compute_p0()?;
        let prob_wait = self.erlang_c(a, c, p0)?;

        // Average number in queue
        let lq = prob_wait * rho / (1.0 - rho);
        // Average number in system
        let l = lq + a;
        // Average time in queue
        let wq = lq / lambda;
        // Average time in system
        let w = l / lambda;

        Some(QueueStats {
            avg_customers_in_system: l,
            avg_customers_in_queue: lq,
            avg_time_in_system: w,
            avg_time_in_queue: wq,
            utilization: rho,
            prob_idle: p0,
            prob_waiting: prob_wait,
        })
    }

    /// Compute P0 using the Erlang C formula.
    fn compute_p0(&self) -> Option<f64> {
        let lambda = self.arrival_rate;
        let mu = self.service_rate;
        let c = self.num_servers;
        let a = lambda / mu;

        let mut sum = 0.0;
        for k in 0..c {
            sum += a.powi(k as i32) / factorial(k);
        }

        let last_term = a.powi(c as i32) / (factorial(c) * (1.0 - a / c as f64));
        let p0 = 1.0 / (sum + last_term);

        Some(p0)
    }

    /// Erlang C probability: P(wait | all servers busy).
    fn erlang_c(&self, a: f64, c: usize, p0: f64) -> Option<f64> {
        let rho = a / c as f64;
        let pc = a.powi(c as i32) / (factorial(c)) * p0;
        let prob_wait = pc / (1.0 - rho);
        Some(prob_wait)
    }

    /// Find minimum number servers needed for target utilization.
    pub fn min_servers_for_utilization(&self, target_utilization: f64) -> usize {
        let a = self.arrival_rate / self.service_rate;
        // ρ = a/c, so c = a/ρ
        (a / target_utilization).ceil() as usize
    }

    /// Find minimum servers for target response time.
    pub fn min_servers_for_response_time(&self, target_w: f64) -> Option<usize> {
        for c in 1..1000 {
            let queue = MMcQueue::new(self.arrival_rate, self.service_rate, c);
            if let Some(stats) = queue.stats() {
                if stats.avg_time_in_system <= target_w {
                    return Some(c);
                }
            }
        }
        None
    }
}

fn factorial(n: usize) -> f64 {
    if n <= 1 {
        1.0
    } else if n > 20 {
        // Stirling's approximation
        let dn = n as f64;
        (2.0 * std::f64::consts::PI * dn).sqrt() * (dn / std::f64::consts::E).powf(dn)
    } else {
        (2..=n).fold(1.0, |acc, x| acc * x as f64)
    }
}



#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mm1_stable() {
        let queue = MM1Queue::new(3.0, 5.0);
        let stats = queue.stats().unwrap();

        assert!((stats.utilization - 0.6).abs() < 0.01);
        assert!((stats.avg_customers_in_system - 1.5).abs() < 0.01);
        assert!(stats.avg_time_in_system > 0.0);
    }

    #[test]
    fn test_mm1_unstable() {
        let queue = MM1Queue::new(10.0, 5.0);
        assert!(queue.stats().is_none());
    }

    #[test]
    fn test_mm1_prob_k() {
        let queue = MM1Queue::new(3.0, 5.0);
        let p0 = queue.prob_k_customers(0).unwrap();
        assert!((p0 - 0.4).abs() < 0.01);
    }

    #[test]
    fn test_mmc_two_servers() {
        let queue = MMcQueue::new(8.0, 5.0, 2);
        let stats = queue.stats().unwrap();

        assert!(stats.utilization < 1.0);
        assert!(stats.avg_time_in_system > 0.0);
        assert!(stats.prob_waiting > 0.0);
    }

    #[test]
    fn test_mmc_min_servers() {
        let queue = MMcQueue::new(10.0, 5.0, 1);
        let min = queue.min_servers_for_utilization(0.8);
        assert!(min >= 3); // Need at least 3 servers for 80% utilization
    }

    #[test]
    fn test_mmc_single_server_same_as_mm1() {
        let mm1 = MM1Queue::new(3.0, 5.0);
        let mmc = MMcQueue::new(3.0, 5.0, 1);

        let s1 = mm1.stats().unwrap();
        let s2 = mmc.stats().unwrap();

        assert!((s1.avg_customers_in_system - s2.avg_customers_in_system).abs() < 0.01);
    }
}
