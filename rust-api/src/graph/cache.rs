//! Graph Cache Layer — Redis-backed caching for expensive graph operations.
//!
//! Caches:
//! - PageRank results (invalidate on edge changes)
//! - Community detection results
//! - Subgraph snapshots (lazy loading with TTL)
//! - Query depth limits to prevent expensive traversals

use serde::{Deserialize, Serialize};
use std::time::Duration;
use uuid::Uuid;

/// Cache key prefixes for different graph operations.
const PREFIX_PAGERANK: &str = "graph:pr:";
const PREFIX_COMMUNITY: &str = "graph:comm:";
const PREFIX_SUBGRAPH: &str = "graph:sub:";
const PREFIX_STATS: &str = "graph:stats:";

/// Default TTLs for cached results.
const TTL_PAGERANK: Duration = Duration::from_secs(3600);       // 1 hour
const TTL_COMMUNITY: Duration = Duration::from_secs(7200);      // 2 hours
const TTL_SUBGRAPH: Duration = Duration::from_secs(300);        // 5 minutes
const TTL_STATS: Duration = Duration::from_secs(600);           // 10 minutes

/// Maximum traversal depth to prevent expensive queries.
pub const MAX_TRAVERSAL_DEPTH: u32 = 10;

/// Maximum nodes returned in a subgraph query.
pub const MAX_SUBGRAPH_NODES: usize = 1000;

/// Maximum edges returned in a single query.
pub const MAX_EDGES_QUERY: usize = 5000;

/// Depth limit error.
#[derive(Debug, thiserror::Error)]
#[error("Query depth {requested} exceeds maximum allowed depth {max}")]
pub struct DepthLimitError {
    pub requested: u32,
    pub max: u32,
}

/// Check if a traversal depth is within limits.
pub fn check_depth_limit(depth: u32) -> Result<u32, DepthLimitError> {
    if depth > MAX_TRAVERSAL_DEPTH {
        Err(DepthLimitError {
            requested: depth,
            max: MAX_TRAVERSAL_DEPTH,
        })
    } else {
        Ok(depth)
    }
}

/// Check if a subgraph size is within limits.
pub fn check_subgraph_limit(node_count: usize) -> usize {
    node_count.min(MAX_SUBGRAPH_NODES)
}

/// Graph cache backed by Redis.
#[derive(Clone)]
pub struct GraphCache {
    redis: redis::aio::ConnectionManager,
}

impl GraphCache {
    pub fn new(redis: redis::aio::ConnectionManager) -> Self {
        Self { redis }
    }

    /// Cache PageRank results.
    pub async fn cache_pagerank(
        &self,
        results: &[super::algorithms::PageRankResult],
    ) -> anyhow::Result<()> {
        let key = format!("{}all", PREFIX_PAGERANK);
        let value = serde_json::to_string(results)?;
        let mut conn = self.redis.clone();
        redis::cmd("SETEX")
            .arg(&key)
            .arg(TTL_PAGERANK.as_secs())
            .arg(&value)
            .query_async::<()>(&mut conn)
            .await?;
        Ok(())
    }

    /// Get cached PageRank results.
    pub async fn get_pagerank(&self) -> anyhow::Result<Option<Vec<super::algorithms::PageRankResult>>> {
        let key = format!("{}all", PREFIX_PAGERANK);
        let mut conn = self.redis.clone();
        let result: Option<String> = redis::cmd("GET")
            .arg(&key)
            .query_async(&mut conn)
            .await?;

        match result {
            Some(data) => Ok(Some(serde_json::from_str(&data)?)),
            None => Ok(None),
        }
    }

    /// Cache community detection results.
    pub async fn cache_communities(
        &self,
        communities: &[super::algorithms::Community],
    ) -> anyhow::Result<()> {
        let key = format!("{}all", PREFIX_COMMUNITY);
        let value = serde_json::to_string(communities)?;
        let mut conn = self.redis.clone();
        redis::cmd("SETEX")
            .arg(&key)
            .arg(TTL_COMMUNITY.as_secs())
            .arg(&value)
            .query_async::<()>(&mut conn)
            .await?;
        Ok(())
    }

    /// Get cached community results.
    pub async fn get_communities(&self) -> anyhow::Result<Option<Vec<super::algorithms::Community>>> {
        let key = format!("{}all", PREFIX_COMMUNITY);
        let mut conn = self.redis.clone();
        let result: Option<String> = redis::cmd("GET")
            .arg(&key)
            .query_async(&mut conn)
            .await?;

        match result {
            Some(data) => Ok(Some(serde_json::from_str(&data)?)),
            None => Ok(None),
        }
    }

    /// Cache a subgraph snapshot.
    pub async fn cache_subgraph(
        &self,
        center: Uuid,
        hops: u32,
        data: &serde_json::Value,
    ) -> anyhow::Result<()> {
        let key = format!("{}{}:{}", PREFIX_SUBGRAPH, center, hops);
        let value = serde_json::to_string(data)?;
        let mut conn = self.redis.clone();
        redis::cmd("SETEX")
            .arg(&key)
            .arg(TTL_SUBGRAPH.as_secs())
            .arg(&value)
            .query_async::<()>(&mut conn)
            .await?;
        Ok(())
    }

    /// Get cached subgraph.
    pub async fn get_subgraph(
        &self,
        center: Uuid,
        hops: u32,
    ) -> anyhow::Result<Option<serde_json::Value>> {
        let key = format!("{}{}:{}", PREFIX_SUBGRAPH, center, hops);
        let mut conn = self.redis.clone();
        let result: Option<String> = redis::cmd("GET")
            .arg(&key)
            .query_async(&mut conn)
            .await?;

        match result {
            Some(data) => Ok(Some(serde_json::from_str(&data)?)),
            None => Ok(None),
        }
    }

    /// Cache graph statistics.
    pub async fn cache_stats(&self, stats: &serde_json::Value) -> anyhow::Result<()> {
        let key = format!("{}global", PREFIX_STATS);
        let value = serde_json::to_string(stats)?;
        let mut conn = self.redis.clone();
        redis::cmd("SETEX")
            .arg(&key)
            .arg(TTL_STATS.as_secs())
            .arg(&value)
            .query_async::<()>(&mut conn)
            .await?;
        Ok(())
    }

    /// Get cached graph stats.
    pub async fn get_stats(&self) -> anyhow::Result<Option<serde_json::Value>> {
        let key = format!("{}global", PREFIX_STATS);
        let mut conn = self.redis.clone();
        let result: Option<String> = redis::cmd("GET")
            .arg(&key)
            .query_async(&mut conn)
            .await?;

        match result {
            Some(data) => Ok(Some(serde_json::from_str(&data)?)),
            None => Ok(None),
        }
    }

    /// Invalidate all graph caches (call after edge/node mutations).
    pub async fn invalidate_all(&self) -> anyhow::Result<()> {
        let mut conn = self.redis.clone();
        let patterns = [
            format!("{}*", PREFIX_PAGERANK),
            format!("{}*", PREFIX_COMMUNITY),
            format!("{}*", PREFIX_SUBGRAPH),
            format!("{}*", PREFIX_STATS),
        ];

        for pattern in &patterns {
            // S13: Use SCAN instead of KEYS to avoid blocking Redis
            let mut cursor: u64 = 0;
            loop {
                let result: (u64, Vec<String>) = redis::cmd("SCAN")
                    .arg(cursor)
                    .arg("MATCH")
                    .arg(pattern)
                    .arg("COUNT")
                    .arg(100)
                    .query_async(&mut conn)
                    .await
                    .unwrap_or((0, vec![]));

                cursor = result.0;
                let keys = result.1;

                if !keys.is_empty() {
                    redis::cmd("DEL")
                        .arg(&keys)
                        .query_async::<()>(&mut conn)
                        .await?;
                }

                if cursor == 0 {
                    break;
                }
            }
        }

        Ok(())
    }

    /// Invalidate PageRank cache only.
    pub async fn invalidate_pagerank(&self) -> anyhow::Result<()> {
        let key = format!("{}all", PREFIX_PAGERANK);
        let mut conn = self.redis.clone();
        redis::cmd("DEL")
            .arg(&key)
            .query_async::<()>(&mut conn)
            .await?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_depth_limit_within() {
        assert!(check_depth_limit(5).is_ok());
        assert!(check_depth_limit(MAX_TRAVERSAL_DEPTH).is_ok());
    }

    #[test]
    fn test_depth_limit_exceeded() {
        let result = check_depth_limit(MAX_TRAVERSAL_DEPTH + 1);
        assert!(result.is_err());
        assert_eq!(result.unwrap_err().max, MAX_TRAVERSAL_DEPTH);
    }

    #[test]
    fn test_subgraph_limit() {
        assert_eq!(check_subgraph_limit(500), 500);
        assert_eq!(check_subgraph_limit(2000), MAX_SUBGRAPH_NODES);
    }
}
