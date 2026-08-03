// Angavu Intelligence Backend — Data Freshness Checks
// Ensures market data and scores distributed to devices are fresh.
//
// Rules:
// - Market data: fresh if < 1 hour old
// - Score data: fresh if < 24 hours old
// - Stale data triggers a "pull for fresh data" indicator
// - Very stale data (> 7 days) triggers an alert

use super::receiver::AlamaScoreUpdate;
use super::*;
use chrono::Utc;

/// Market data freshness threshold (1 hour in ms)
const MARKET_FRESH_THRESHOLD_MS: i64 = 60 * 60 * 1000;

/// Score data freshness threshold (24 hours in ms)
const SCORE_FRESH_THRESHOLD_MS: i64 = 24 * 60 * 60 * 1000;

/// Very stale threshold (7 days in ms)
const VERY_STALE_THRESHOLD_MS: i64 = 7 * 24 * 60 * 60 * 1000;

pub struct FreshnessChecker;

impl FreshnessChecker {
    pub fn new() -> Self {
        Self
    }

    /// Check freshness of data being sent to a device.
    ///
    /// Parameters:
    /// - last_server_timestamp: The last server timestamp the device knows about
    /// - market_data: The market intelligence being sent (if any)
    /// - score_update: The score update being sent (if any)
    pub async fn check_freshness(
        &self,
        last_server_timestamp: Option<i64>,
        market_data: Option<&MarketIntelligence>,
        score_update: Option<&AlamaScoreUpdate>,
    ) -> FreshnessMetadata {
        let now = Utc::now().timestamp_millis();

        // Check market data freshness
        let market_data_fresh = market_data
            .map(|m| {
                let age = now - m.data_timestamp;
                age < MARKET_FRESH_THRESHOLD_MS
            })
            .unwrap_or(false);

        // Check score data freshness
        let score_data_fresh = score_update
            .map(|s| {
                let age = now - s.computed_at;
                age < SCORE_FRESH_THRESHOLD_MS
            })
            .unwrap_or(false);

        // Determine overall staleness
        let staleness = match last_server_timestamp {
            Some(last_ts) => {
                let age = now - last_ts;
                if age < MARKET_FRESH_THRESHOLD_MS {
                    "fresh".to_string()
                } else if age < VERY_STALE_THRESHOLD_MS {
                    "stale".to_string()
                } else {
                    "very_stale".to_string()
                }
            }
            None => "unknown".to_string(),
        };

        FreshnessMetadata {
            server_timestamp: now,
            market_data_fresh,
            score_data_fresh,
            staleness,
        }
    }

    /// Check if market data for a specific ward/category needs refreshing.
    /// Returns true if the data is stale and should be refreshed.
    pub fn needs_market_refresh(data_timestamp: i64) -> bool {
        let now = Utc::now().timestamp_millis();
        let age = now - data_timestamp;
        age > MARKET_FRESH_THRESHOLD_MS
    }

    /// Check if a score needs recomputation.
    /// Returns true if the score is stale.
    pub fn needs_score_refresh(computed_at: i64) -> bool {
        let now = Utc::now().timestamp_millis();
        let age = now - computed_at;
        age > SCORE_FRESH_THRESHOLD_MS
    }

    /// Generate a freshness alert for stale data
    pub fn generate_staleness_alert(
        staleness: &str,
        last_server_timestamp: Option<i64>,
    ) -> Option<SyncAlert> {
        let now = Utc::now().timestamp_millis();

        match staleness {
            "very_stale" => Some(SyncAlert {
                alert_type: "data_stale".to_string(),
                severity: "warning".to_string(),
                title: "Your data is outdated".to_string(),
                body: format!(
                    "It's been over 7 days since your last sync. \
                     Pull to refresh for the latest market data and score updates."
                ),
                timestamp: now,
                action_url: Some("msaidizi://sync/pull".to_string()),
            }),
            "stale" => Some(SyncAlert {
                alert_type: "data_stale".to_string(),
                severity: "info".to_string(),
                title: "Fresh data available".to_string(),
                body: "New market data and score updates are available. Pull to refresh."
                    .to_string(),
                timestamp: now,
                action_url: Some("msaidizi://sync/pull".to_string()),
            }),
            _ => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_fresh_market_data() {
        let checker = FreshnessChecker::new();
        let now = Utc::now().timestamp_millis();

        let market = MarketIntelligence {
            ward: "Test".to_string(),
            price_trends: std::collections::HashMap::new(),
            demand_signals: vec![],
            data_timestamp: now, // just now
            ttl_seconds: 3600,
        };

        let freshness = checker.check_freshness(None, Some(&market), None).await;
        assert!(freshness.market_data_fresh);
    }

    #[tokio::test]
    async fn test_stale_market_data() {
        let checker = FreshnessChecker::new();
        let now = Utc::now().timestamp_millis();

        let market = MarketIntelligence {
            ward: "Test".to_string(),
            price_trends: std::collections::HashMap::new(),
            demand_signals: vec![],
            data_timestamp: now - 2 * 60 * 60 * 1000, // 2 hours ago
            ttl_seconds: 3600,
        };

        let freshness = checker.check_freshness(None, Some(&market), None).await;
        assert!(!freshness.market_data_fresh);
    }

    #[tokio::test]
    async fn test_freshness_unknown_without_timestamp() {
        let checker = FreshnessChecker::new();

        let freshness = checker.check_freshness(None, None, None).await;
        assert_eq!(freshness.staleness, "unknown");
    }

    #[tokio::test]
    async fn test_staleness_detection() {
        let checker = FreshnessChecker::new();
        let now = Utc::now().timestamp_millis();

        // Recent sync
        let freshness = checker.check_freshness(Some(now - 1000), None, None).await;
        assert_eq!(freshness.staleness, "fresh");

        // 2 days ago
        let freshness = checker
            .check_freshness(Some(now - 2 * 86400 * 1000), None, None)
            .await;
        assert_eq!(freshness.staleness, "stale");

        // 10 days ago
        let freshness = checker
            .check_freshness(Some(now - 10 * 86400 * 1000), None, None)
            .await;
        assert_eq!(freshness.staleness, "very_stale");
    }

    #[test]
    fn test_needs_refresh() {
        let now = Utc::now().timestamp_millis();
        assert!(!FreshnessChecker::needs_market_refresh(now));
        assert!(FreshnessChecker::needs_market_refresh(
            now - 2 * 60 * 60 * 1000
        ));
        assert!(!FreshnessChecker::needs_score_refresh(now));
        assert!(FreshnessChecker::needs_score_refresh(
            now - 25 * 60 * 60 * 1000
        ));
    }

    #[test]
    fn test_staleness_alert_generation() {
        let alert = FreshnessChecker::generate_staleness_alert("very_stale", None);
        assert!(alert.is_some());
        assert_eq!(alert.unwrap().severity, "warning");

        let alert = FreshnessChecker::generate_staleness_alert("stale", None);
        assert!(alert.is_some());
        assert_eq!(alert.unwrap().severity, "info");

        let alert = FreshnessChecker::generate_staleness_alert("fresh", None);
        assert!(alert.is_none());
    }
}
