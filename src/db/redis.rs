use anyhow::{Context, Result};
use redis::aio::ConnectionManager;
use redis::{AsyncCommands, RedisResult};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use crate::models::RedisConfig;

/// Create a Redis connection with retry logic and proper error context.
pub async fn create_connection(config: &RedisConfig) -> Result<ConnectionManager> {
    let max_retries = 3;
    let mut attempt = 0;

    loop {
        attempt += 1;
        let result = async {
            let client = redis::Client::open(config.url.as_str())
                .context("Invalid Redis URL")?;
            let manager = ConnectionManager::new(client)
                .await
                .context("Failed to establish Redis connection")?;
            Ok::<_, anyhow::Error>(manager)
        }
        .await;

        match result {
            Ok(manager) => {
                tracing::info!("Redis connection established (attempt {attempt})");
                return Ok(manager);
            }
            Err(e) if attempt < max_retries => {
                let backoff = Duration::from_secs(2u64.pow(attempt as u32));
                tracing::warn!(
                    error = %e,
                    attempt,
                    max_retries,
                    backoff_secs = backoff.as_secs(),
                    "Redis connection failed, retrying…"
                );
                tokio::time::sleep(backoff).await;
            }
            Err(e) => {
                return Err(e).context(format!(
                    "Failed to connect to Redis after {max_retries} attempts. \
                     Verify that Redis is running and accessible at the configured URL."
                ));
            }
        }
    }
}

/// Redis cache wrapper
pub struct RedisCache {
    conn: ConnectionManager,
}

impl RedisCache {
    pub fn new(conn: ConnectionManager) -> Self {
        Self { conn }
    }

    /// Get a value from cache
    pub async fn get<T: for<'de> Deserialize<'de>>(&mut self, key: &str) -> Result<Option<T>> {
        let result: RedisResult<String> = self.conn.get(key).await;
        match result {
            Ok(data) => {
                let value: T = serde_json::from_str(&data)
                    .context("Failed to deserialize cached value")?;
                Ok(Some(value))
            }
            Err(_) => Ok(None),
        }
    }

    /// Set a value in cache with optional TTL
    pub async fn set<T: Serialize>(
        &mut self,
        key: &str,
        value: &T,
        ttl: Option<Duration>,
    ) -> Result<()> {
        let data = serde_json::to_string(value)
            .context("Failed to serialize value for cache")?;
        if let Some(ttl) = ttl {
            self.conn
                .set_ex(key, data, ttl.as_secs())
                .await
                .context("Failed to set cache key with TTL")?;
        } else {
            self.conn
                .set(key, data)
                .await
                .context("Failed to set cache key")?;
        }
        Ok(())
    }

    /// Delete a key from cache
    pub async fn delete(&mut self, key: &str) -> Result<()> {
        self.conn
            .del(key)
            .await
            .context("Failed to delete cache key")?;
        Ok(())
    }

    /// Check if a key exists
    pub async fn exists(&mut self, key: &str) -> Result<bool> {
        let result: bool = self
            .conn
            .exists(key)
            .await
            .context("Failed to check cache key existence")?;
        Ok(result)
    }

    /// Increment a counter
    pub async fn incr(&mut self, key: &str, delta: i64) -> Result<i64> {
        let result: i64 = self
            .conn
            .incr(key, delta)
            .await
            .context("Failed to increment cache counter")?;
        Ok(result)
    }

    /// Set hash field
    pub async fn hset<T: Serialize>(&mut self, key: &str, field: &str, value: &T) -> Result<()> {
        let data = serde_json::to_string(value)
            .context("Failed to serialize hash value")?;
        self.conn
            .hset(key, field, data)
            .await
            .context("Failed to set hash field")?;
        Ok(())
    }

    /// Get hash field
    pub async fn hget<T: for<'de> Deserialize<'de>>(
        &mut self,
        key: &str,
        field: &str,
    ) -> Result<Option<T>> {
        let result: RedisResult<String> = self.conn.hget(key, field).await;
        match result {
            Ok(data) => {
                let value: T = serde_json::from_str(&data)
                    .context("Failed to deserialize hash value")?;
                Ok(Some(value))
            }
            Err(_) => Ok(None),
        }
    }

    /// Get all hash fields
    pub async fn hgetall<T: for<'de> Deserialize<'de>>(
        &mut self,
        key: &str,
    ) -> Result<std::collections::HashMap<String, T>> {
        let result: std::collections::HashMap<String, String> = self
            .conn
            .hgetall(key)
            .await
            .context("Failed to get all hash fields")?;
        let mut map = std::collections::HashMap::new();
        for (k, v) in result {
            let value: T = serde_json::from_str(&v)
                .context("Failed to deserialize hash entry")?;
            map.insert(k, value);
        }
        Ok(map)
    }

    /// Add to sorted set
    pub async fn zadd<T: Serialize>(
        &mut self,
        key: &str,
        member: &T,
        score: f64,
    ) -> Result<()> {
        let data = serde_json::to_string(member)
            .context("Failed to serialize sorted set member")?;
        self.conn
            .zadd(key, data, score)
            .await
            .context("Failed to add to sorted set")?;
        Ok(())
    }

    /// Get range from sorted set
    pub async fn zrange<T: for<'de> Deserialize<'de>>(
        &mut self,
        key: &str,
        start: isize,
        stop: isize,
    ) -> Result<Vec<T>> {
        let result: Vec<String> = self
            .conn
            .zrange(key, start, stop)
            .await
            .context("Failed to get sorted set range")?;
        let mut values = Vec::new();
        for data in result {
            let value: T = serde_json::from_str(&data)
                .context("Failed to deserialize sorted set entry")?;
            values.push(value);
        }
        Ok(values)
    }

    /// Publish to a channel
    pub async fn publish<T: Serialize>(&mut self, channel: &str, message: &T) -> Result<()> {
        let data = serde_json::to_string(message)
            .context("Failed to serialize pub/sub message")?;
        self.conn
            .publish(channel, data)
            .await
            .context("Failed to publish message")?;
        Ok(())
    }

    /// Set with pattern-based expiration
    pub async fn set_with_pattern(
        &mut self,
        pattern: &str,
        key: &str,
        value: &str,
        ttl: Duration,
    ) -> Result<()> {
        let full_key = format!("{}:{}", pattern, key);
        self.conn
            .set_ex(full_key, value, ttl.as_secs())
            .await
            .context("Failed to set pattern key")?;
        Ok(())
    }

    /// Rate limiting using sliding window
    pub async fn check_rate_limit(
        &mut self,
        key: &str,
        limit: i64,
        window: Duration,
    ) -> Result<bool> {
        let now = chrono::Utc::now().timestamp();
        let window_start = now - window.as_secs() as i64;

        // Remove old entries
        self.conn
            .zrembyscore(key, "-inf", window_start)
            .await
            .context("Failed to clean expired rate limit entries")?;

        // Count current entries
        let count: i64 = self
            .conn
            .zcard(key)
            .await
            .context("Failed to count rate limit entries")?;

        if count >= limit {
            return Ok(false);
        }

        // Add current request
        self.conn
            .zadd(key, now.to_string(), now as f64)
            .await
            .context("Failed to add rate limit entry")?;

        // Set expiry on the key
        self.conn
            .expire(key, window.as_secs() as usize)
            .await
            .context("Failed to set rate limit expiry")?;

        Ok(true)
    }
}

/// Session store
pub struct SessionStore {
    conn: ConnectionManager,
}

impl SessionStore {
    pub fn new(conn: ConnectionManager) -> Self {
        Self { conn }
    }

    pub async fn create_session(
        &mut self,
        user_id: uuid::Uuid,
        session_data: &serde_json::Value,
        ttl: Duration,
    ) -> Result<String> {
        let session_id = uuid::Uuid::new_v4().to_string();
        let key = format!("session:{}", session_id);
        let data = serde_json::to_string(session_data)
            .context("Failed to serialize session data")?;
        self.conn
            .set_ex(&key, &data, ttl.as_secs())
            .await
            .context("Failed to create session")?;

        // Map user to session
        let user_key = format!("user_sessions:{}", user_id);
        self.conn
            .sadd(&user_key, &session_id)
            .await
            .context("Failed to map user to session")?;

        Ok(session_id)
    }

    pub async fn get_session(
        &mut self,
        session_id: &str,
    ) -> Result<Option<serde_json::Value>> {
        let key = format!("session:{}", session_id);
        let result: RedisResult<String> = self.conn.get(&key).await;
        match result {
            Ok(data) => {
                let value: serde_json::Value = serde_json::from_str(&data)
                    .context("Failed to deserialize session data")?;
                Ok(Some(value))
            }
            Err(_) => Ok(None),
        }
    }

    pub async fn delete_session(&mut self, session_id: &str) -> Result<()> {
        let key = format!("session:{}", session_id);
        self.conn
            .del(&key)
            .await
            .context("Failed to delete session")?;
        Ok(())
    }

    pub async fn extend_session(&mut self, session_id: &str, ttl: Duration) -> Result<()> {
        let key = format!("session:{}", session_id);
        self.conn
            .expire(&key, ttl.as_secs() as usize)
            .await
            .context("Failed to extend session")?;
        Ok(())
    }
}

/// Pub/Sub manager
pub struct PubSubManager {
    conn: ConnectionManager,
}

impl PubSubManager {
    pub fn new(conn: ConnectionManager) -> Self {
        Self { conn }
    }

    pub async fn publish_intelligence_update(
        &mut self,
        org_id: uuid::Uuid,
        update: &serde_json::Value,
    ) -> Result<()> {
        let channel = format!("intelligence:updates:{}", org_id);
        self.conn
            .publish(&channel, serde_json::to_string(update)?)
            .await
            .context("Failed to publish intelligence update")?;
        Ok(())
    }

    pub async fn publish_task_status(
        &mut self,
        task_id: uuid::Uuid,
        status: &str,
    ) -> Result<()> {
        let channel = format!("task:status:{}", task_id);
        self.conn
            .publish(&channel, status)
            .await
            .context("Failed to publish task status")?;
        Ok(())
    }
}
