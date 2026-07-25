//! Memory — Four-layer memory system with per-user isolation
//!
//! Implements a hierarchical memory system inspired by cognitive science:
//!
//! 1. **Working Memory** — Current context, active session (< 1 hour)
//! 2. **Episodic Memory** — Specific events and interactions (< 30 days)
//! 3. **Semantic Memory** — Facts, concepts, relationships (permanent)
//! 4. **Procedural Memory** — Learned patterns and procedures (permanent)
//!
//! Each user's memory is isolated — no cross-user memory leakage.
//! Memory entries are promoted between layers based on importance and
//! access frequency.

use anyhow::Result;
use chrono::{DateTime, Duration, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────
// Memory Layer
// ─────────────────────────────────────────────────────────────────────

/// The four memory layers, ordered from most transient to most permanent.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum Layer {
    /// Current context, active session. TTL: 1 hour.
    Working,
    /// Specific events and interactions. TTL: 30 days.
    Episodic,
    /// Facts, concepts, relationships. No TTL.
    Semantic,
    /// Learned patterns and procedures. No TTL.
    Procedural,
}

impl Layer {
    /// Time-to-live for this layer, if any.
    pub fn ttl(&self) -> Option<Duration> {
        match self {
            Self::Working => Some(Duration::hours(1)),
            Self::Episodic => Some(Duration::days(30)),
            Self::Semantic | Self::Procedural => None,
        }
    }

    /// Promotion order (higher = more permanent).
    pub fn permanence(&self) -> u8 {
        match self {
            Self::Working => 0,
            Self::Episodic => 1,
            Self::Semantic => 2,
            Self::Procedural => 3,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────
// Memory Entry
// ─────────────────────────────────────────────────────────────────────

/// A single memory entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryItem {
    pub item_id: Uuid,
    pub user_id: Uuid,
    pub layer: Layer,
    pub content: String,
    pub content_type: ContentType,
    pub importance: f64,
    pub access_count: u32,
    pub last_accessed: DateTime<Utc>,
    pub created_at: DateTime<Utc>,
    pub expires_at: Option<DateTime<Utc>>,
    pub tags: Vec<String>,
    pub source: String,
    pub embedding: Option<Vec<f32>>,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ContentType {
    /// Free-form text
    Text,
    /// Structured data (JSON)
    Structured,
    /// A summary or consolidation of other memories
    Summary,
    /// A learned pattern or procedure
    Pattern,
    /// A fact or relationship
    Fact,
}

/// A query to search memory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryQuery {
    pub text: String,
    pub layers: Option<Vec<Layer>>,
    pub tags: Option<Vec<String>>,
    pub min_importance: Option<f64>,
    pub max_age: Option<Duration>,
    pub limit: usize,
}

/// A search result with relevance score.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemorySearchResult {
    pub item: MemoryItem,
    pub relevance: f64,
}

// ─────────────────────────────────────────────────────────────────────
// Consolidation
// ─────────────────────────────────────────────────────────────────────

/// A consolidation job that promotes memories between layers.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsolidationJob {
    pub job_id: Uuid,
    pub source_layer: Layer,
    pub target_layer: Layer,
    pub strategy: ConsolidationStrategy,
    pub entries_processed: usize,
    pub entries_promoted: usize,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ConsolidationStrategy {
    /// Promote based on importance score
    Importance,
    /// Promote based on access frequency
    Frequency,
    /// Promote based on recency
    Recency,
    /// Combined score (importance * frequency / age)
    Combined,
}

// ─────────────────────────────────────────────────────────────────────
// Memory Engine
// ─────────────────────────────────────────────────────────────────────

/// The memory engine — manages all four layers with per-user isolation.
pub struct MemoryEngine {
    /// Per-user memory stores (user_id → items)
    stores: Arc<RwLock<HashMap<Uuid, Vec<MemoryItem>>>>,
    /// Consolidation history
    consolidation_log: Arc<RwLock<Vec<ConsolidationJob>>>,
    /// Maximum items per user per layer
    max_per_layer: usize,
    /// Minimum importance for promotion
    promotion_threshold: f64,
}

impl MemoryEngine {
    pub fn new() -> Self {
        Self {
            stores: Arc::new(RwLock::new(HashMap::new())),
            consolidation_log: Arc::new(RwLock::new(Vec::new())),
            max_per_layer: 10_000,
            promotion_threshold: 0.7,
        }
    }

    pub fn with_limits(mut self, max_per_layer: usize, promotion_threshold: f64) -> Self {
        self.max_per_layer = max_per_layer;
        self.promotion_threshold = promotion_threshold;
        self
    }

    // ── Store ─────────────────────────────────────────────────────────

    /// Store a new memory item for a user.
    pub async fn store(
        &self,
        user_id: Uuid,
        layer: Layer,
        content: &str,
        content_type: ContentType,
        tags: Vec<String>,
        source: &str,
    ) -> Result<Uuid> {
        let now = Utc::now();
        let item = MemoryItem {
            item_id: Uuid::new_v4(),
            user_id,
            layer: layer.clone(),
            content: content.to_string(),
            content_type,
            importance: 0.5, // Default importance
            access_count: 0,
            last_accessed: now,
            created_at: now,
            expires_at: layer.ttl().map(|ttl| now + ttl),
            tags,
            source: source.to_string(),
            embedding: None,
            metadata: serde_json::json!({}),
        };

        let item_id = item.item_id;

        let mut stores = self.stores.write().await;
        let user_store = stores.entry(user_id).or_insert_with(Vec::new);
        user_store.push(item);

        // Enforce per-layer limits
        self.evict_if_needed(user_store, &layer);

        debug!(
            user_id = %user_id,
            layer = ?layer,
            item_id = %item_id,
            "Memory item stored"
        );

        Ok(item_id)
    }

    /// Store with custom importance.
    pub async fn store_with_importance(
        &self,
        user_id: Uuid,
        layer: Layer,
        content: &str,
        content_type: ContentType,
        importance: f64,
        tags: Vec<String>,
        source: &str,
    ) -> Result<Uuid> {
        let id = self.store(user_id, layer, content, content_type, tags, source).await?;

        let mut stores = self.stores.write().await;
        if let Some(items) = stores.get_mut(&user_id) {
            if let Some(item) = items.iter_mut().find(|i| i.item_id == id) {
                item.importance = importance.clamp(0.0, 1.0);
            }
        }

        Ok(id)
    }

    // ── Retrieve ──────────────────────────────────────────────────────

    /// Get a specific memory item by ID.
    pub async fn get(&self, user_id: Uuid, item_id: Uuid) -> Option<MemoryItem> {
        let stores = self.stores.read().await;
        stores
            .get(&user_id)?
            .iter()
            .find(|i| i.item_id == item_id)
            .cloned()
    }

    /// Get all items in a specific layer for a user.
    pub async fn get_layer(&self, user_id: Uuid, layer: &Layer) -> Vec<MemoryItem> {
        let stores = self.stores.read().await;
        stores
            .get(&user_id)
            .map(|items| {
                items
                    .iter()
                    .filter(|i| &i.layer == layer && !self.is_expired(i))
                    .cloned()
                    .collect()
            })
            .unwrap_or_default()
    }

    // ── Search ────────────────────────────────────────────────────────

    /// Search memory by text relevance (simple keyword matching).
    pub async fn search(
        &self,
        user_id: Uuid,
        query: &MemoryQuery,
    ) -> Result<Vec<MemorySearchResult>> {
        let stores = self.stores.read().await;
        let items = match stores.get(&user_id) {
            Some(items) => items,
            None => return Ok(Vec::new()),
        };

        let query_lower = query.text.to_lowercase();
        let query_words: Vec<&str> = query_lower.split_whitespace().collect();

        let mut results: Vec<MemorySearchResult> = items
            .iter()
            .filter(|item| {
                // Filter expired
                if self.is_expired(item) {
                    return false;
                }

                // Filter by layer
                if let Some(ref layers) = query.layers {
                    if !layers.contains(&item.layer) {
                        return false;
                    }
                }

                // Filter by tags
                if let Some(ref tags) = query.tags {
                    if !tags.iter().any(|t| item.tags.contains(t)) {
                        return false;
                    }
                }

                // Filter by importance
                if let Some(min_imp) = query.min_importance {
                    if item.importance < min_imp {
                        return false;
                    }
                }

                // Filter by age
                if let Some(max_age) = query.max_age {
                    if Utc::now() - item.created_at > max_age {
                        return false;
                    }
                }

                true
            })
            .map(|item| {
                // Compute relevance score
                let content_lower = item.content.to_lowercase();
                let match_score = query_words
                    .iter()
                    .filter(|w| content_lower.contains(**w))
                    .count() as f64
                    / query_words.len().max(1) as f64;

                let tag_bonus = query
                    .tags
                    .as_ref()
                    .map(|tags| {
                        tags.iter()
                            .filter(|t| item.tags.contains(t))
                            .count() as f64
                            * 0.2
                    })
                    .unwrap_or(0.0);

                let relevance = (match_score + tag_bonus + item.importance * 0.3).min(1.0);

                MemorySearchResult {
                    item: item.clone(),
                    relevance,
                }
            })
            .filter(|r| r.relevance > 0.1)
            .collect();

        // Sort by relevance
        results.sort_by(|a, b| b.relevance.partial_cmp(&a.relevance).unwrap_or(std::cmp::Ordering::Equal));

        // Limit results
        results.truncate(query.limit);

        // Update access counts for returned items
        drop(stores);
        let mut stores = self.stores.write().await;
        if let Some(items) = stores.get_mut(&user_id) {
            for result in &results {
                if let Some(item) = items.iter_mut().find(|i| i.item_id == result.item.item_id) {
                    item.access_count += 1;
                    item.last_accessed = Utc::now();
                }
            }
        }

        Ok(results)
    }

    // ── Consolidation ─────────────────────────────────────────────────

    /// Consolidate memories — promote items between layers based on
    /// importance and access patterns.
    pub async fn consolidate(
        &self,
        user_id: Uuid,
        strategy: ConsolidationStrategy,
    ) -> Result<ConsolidationJob> {
        let now = Utc::now();
        let mut job = ConsolidationJob {
            job_id: Uuid::new_v4(),
            source_layer: Layer::Working,
            target_layer: Layer::Episodic,
            strategy: strategy.clone(),
            entries_processed: 0,
            entries_promoted: 0,
            started_at: now,
            completed_at: None,
        };

        let mut stores = self.stores.write().await;
        let items = match stores.get_mut(&user_id) {
            Some(items) => items,
            None => {
                job.completed_at = Some(Utc::now());
                return Ok(job);
            }
        };

        // Working → Episodic
        let working_to_episodic: Vec<Uuid> = items
            .iter()
            .filter(|i| i.layer == Layer::Working && !self.is_expired(i))
            .filter(|i| self.should_promote(i, &strategy))
            .map(|i| i.item_id)
            .collect();

        for item_id in &working_to_episodic {
            if let Some(item) = items.iter_mut().find(|i| &i.item_id == item_id) {
                item.layer = Layer::Episodic;
                item.expires_at = Layer::Episodic.ttl().map(|ttl| now + ttl);
                job.entries_promoted += 1;
            }
        }

        // Episodic → Semantic
        let episodic_to_semantic: Vec<Uuid> = items
            .iter()
            .filter(|i| i.layer == Layer::Episodic && !self.is_expired(i))
            .filter(|i| self.should_promote(i, &strategy))
            .map(|i| i.item_id)
            .collect();

        for item_id in &episodic_to_semantic {
            if let Some(item) = items.iter_mut().find(|i| &i.item_id == item_id) {
                item.layer = Layer::Semantic;
                item.expires_at = None;
                job.entries_promoted += 1;
            }
        }

        // Semantic → Procedural (only for patterns)
        let semantic_to_procedural: Vec<Uuid> = items
            .iter()
            .filter(|i| i.layer == Layer::Semantic)
            .filter(|i| i.content_type == ContentType::Pattern && i.importance > 0.9)
            .map(|i| i.item_id)
            .collect();

        for item_id in &semantic_to_procedural {
            if let Some(item) = items.iter_mut().find(|i| &i.item_id == item_id) {
                item.layer = Layer::Procedural;
                job.entries_promoted += 1;
            }
        }

        job.entries_processed = working_to_episodic.len()
            + episodic_to_semantic.len()
            + semantic_to_procedural.len();
        job.completed_at = Some(Utc::now());

        // Log consolidation
        let mut log = self.consolidation_log.write().await;
        log.push(job.clone());
        if log.len() > 1000 {
            log.drain(0..500);
        }

        info!(
            user_id = %user_id,
            processed = job.entries_processed,
            promoted = job.entries_promoted,
            strategy = ?strategy,
            "Memory consolidation complete"
        );

        Ok(job)
    }

    // ── Cleanup ───────────────────────────────────────────────────────

    /// Remove expired memory items for a user.
    pub async fn cleanup_expired(&self, user_id: Uuid) -> usize {
        let mut stores = self.stores.write().await;
        let items = match stores.get_mut(&user_id) {
            Some(items) => items,
            None => return 0,
        };

        let before = items.len();
        items.retain(|i| !self.is_expired(i));
        let removed = before - items.len();

        if removed > 0 {
            debug!(user_id = %user_id, removed = removed, "Expired memories cleaned up");
        }

        removed
    }

    // ── Statistics ────────────────────────────────────────────────────

    /// Get memory statistics for a user.
    pub async fn stats(&self, user_id: Uuid) -> MemoryStats {
        let stores = self.stores.read().await;
        let items = match stores.get(&user_id) {
            Some(items) => items,
            None => {
                return MemoryStats {
                    total_items: 0,
                    items_by_layer: HashMap::new(),
                    total_size_bytes: 0,
                    avg_importance: 0.0,
                }
            }
        };

        let mut items_by_layer = HashMap::new();
        let mut total_size = 0usize;
        let mut total_importance = 0.0f64;

        for item in items {
            if !self.is_expired(item) {
                *items_by_layer.entry(item.layer.clone()).or_insert(0usize) += 1;
                total_size += item.content.len();
                total_importance += item.importance;
            }
        }

        let active_count = items_by_layer.values().sum::<usize>();

        MemoryStats {
            total_items: active_count,
            items_by_layer,
            total_size_bytes: total_size,
            avg_importance: if active_count > 0 {
                total_importance / active_count as f64
            } else {
                0.0
            },
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────

    fn is_expired(&self, item: &MemoryItem) -> bool {
        item.expires_at
            .map(|exp| Utc::now() > exp)
            .unwrap_or(false)
    }

    fn should_promote(&self, item: &MemoryItem, strategy: &ConsolidationStrategy) -> bool {
        match strategy {
            ConsolidationStrategy::Importance => item.importance >= self.promotion_threshold,
            ConsolidationStrategy::Frequency => item.access_count >= 5,
            ConsolidationStrategy::Recency => {
                Utc::now().signed_duration_since(item.last_accessed) < Duration::hours(24)
            }
            ConsolidationStrategy::Combined => {
                let age_hours = Utc::now()
                    .signed_duration_since(item.created_at)
                    .num_hours()
                    .max(1) as f64;
                let score = item.importance * (item.access_count as f64 + 1.0) / age_hours;
                score >= self.promotion_threshold * 0.5
            }
        }
    }

    fn evict_if_needed(&self, store: &mut Vec<MemoryItem>, layer: &Layer) {
        let layer_count = store.iter().filter(|i| &i.layer == layer).count();
        if layer_count <= self.max_per_layer {
            return;
        }

        // Remove lowest-importance items in this layer
        let to_remove = layer_count - self.max_per_layer;
        let mut indices: Vec<usize> = store
            .iter()
            .enumerate()
            .filter(|(_, i)| &i.layer == layer)
            .map(|(idx, _)| idx)
            .collect();

        indices.sort_by(|&a, &b| {
            store[a]
                .importance
                .partial_cmp(&store[b].importance)
                .unwrap_or(std::cmp::Ordering::Equal)
        });

        for idx in indices.into_iter().take(to_remove) {
            store.swap_remove(idx);
        }
    }
}

/// Memory statistics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryStats {
    pub total_items: usize,
    pub items_by_layer: HashMap<Layer, usize>,
    pub total_size_bytes: usize,
    pub avg_importance: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_store_and_retrieve() {
        let engine = MemoryEngine::new();
        let user_id = Uuid::new_v4();

        let id = engine
            .store(
                user_id,
                Layer::Working,
                "User searched for milk prices in Nairobi",
                ContentType::Text,
                vec!["search".to_string(), "milk".to_string()],
                "api",
            )
            .await
            .unwrap();

        let item = engine.get(user_id, id).await.unwrap();
        assert_eq!(item.layer, Layer::Working);
        assert!(item.content.contains("milk"));
    }

    #[tokio::test]
    async fn test_search() {
        let engine = MemoryEngine::new();
        let user_id = Uuid::new_v4();

        engine
            .store(
                user_id,
                Layer::Episodic,
                "Revenue increased by 15% in Nairobi region",
                ContentType::Text,
                vec!["revenue".to_string()],
                "system",
            )
            .await
            .unwrap();

        engine
            .store(
                user_id,
                Layer::Episodic,
                "Customer feedback indicates satisfaction with delivery",
                ContentType::Text,
                vec!["feedback".to_string()],
                "system",
            )
            .await
            .unwrap();

        let results = engine
            .search(
                user_id,
                &MemoryQuery {
                    text: "revenue Nairobi".to_string(),
                    layers: None,
                    tags: None,
                    min_importance: None,
                    max_age: None,
                    limit: 10,
                },
            )
            .await
            .unwrap();

        assert!(!results.is_empty());
        assert!(results[0].item.content.contains("Revenue"));
    }

    #[tokio::test]
    async fn test_consolidation() {
        let engine = MemoryEngine::new().with_limits(1000, 0.6);
        let user_id = Uuid::new_v4();

        // Store high-importance item
        engine
            .store_with_importance(
                user_id,
                Layer::Working,
                "Important pattern: demand spikes on Mondays",
                ContentType::Pattern,
                0.9,
                vec!["pattern".to_string()],
                "system",
            )
            .await
            .unwrap();

        let job = engine
            .consolidate(user_id, ConsolidationStrategy::Importance)
            .await
            .unwrap();

        assert!(job.entries_promoted >= 1, "High-importance item should be promoted");

        let episodic = engine.get_layer(user_id, &Layer::Episodic).await;
        assert!(!episodic.is_empty());
    }
}
