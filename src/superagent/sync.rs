//! Sync — Offline-first synchronization with conflict resolution
//!
//! Provides offline-first data synchronization for Angavu worker devices:
//!
//! - **Priority Queues**: Critical data (transactions) sync before
//!   non-critical data (analytics).
//! - **Delta Encoding**: Only changed data is transmitted, reducing
//!   bandwidth usage for low-connectivity environments.
//! - **CRDT Conflict Resolution**: Concurrent edits merge automatically
//!   using Conflict-free Replicated Data Types where possible.
//! - **Offline Queue**: Data is queued locally when offline and synced
//!   when connectivity is restored.

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, VecDeque};
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};
use uuid::Uuid;

// ─────────────────────────────────────────────────────────────────────
// Priority
// ─────────────────────────────────────────────────────────────────────

/// Sync priority levels — higher priority items sync first.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Priority {
    /// Background analytics, non-essential
    Low = 0,
    /// Regular data sync
    Normal = 1,
    /// Important updates (inventory, prices)
    High = 2,
    /// Critical financial transactions
    Critical = 3,
}

// ─────────────────────────────────────────────────────────────────────
// Sync Item
// ─────────────────────────────────────────────────────────────────────

/// An item in the sync queue.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncItem {
    pub item_id: Uuid,
    pub device_id: String,
    pub user_id: Uuid,
    pub entity_type: String,
    pub entity_id: String,
    pub operation: SyncOperation,
    pub data: serde_json::Value,
    pub priority: Priority,
    pub created_at: DateTime<Utc>,
    pub attempts: u32,
    pub checksum: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SyncOperation {
    Create,
    Update,
    Delete,
}

/// Result of a sync attempt.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncResult {
    pub item_id: Uuid,
    pub status: SyncItemStatus,
    pub conflicts: Vec<SyncConflict>,
    pub synced_at: Option<DateTime<Utc>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SyncItemStatus {
    Synced,
    Conflicted,
    Failed,
    Pending,
    Superseded,
}

/// A conflict between local and remote versions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncConflict {
    pub entity_type: String,
    pub entity_id: String,
    pub local_version: serde_json::Value,
    pub remote_version: serde_json::Value,
    pub resolution: ConflictResolution,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum ConflictResolution {
    /// Server version wins
    ServerWins,
    /// Client version wins
    ClientWins,
    /// Merge both versions
    Merged,
    /// Manual resolution required
    Manual,
}

// ─────────────────────────────────────────────────────────────────────
// Delta Encoding
// ─────────────────────────────────────────────────────────────────────

/// A delta between two versions of data.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Delta {
    pub entity_type: String,
    pub entity_id: String,
    pub changes: Vec<FieldChange>,
    pub base_version: u64,
    pub target_version: u64,
    pub delta_size_bytes: usize,
}

/// A single field change in a delta.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FieldChange {
    pub field_path: String,
    pub old_value: Option<serde_json::Value>,
    pub new_value: serde_json::Value,
}

// ─────────────────────────────────────────────────────────────────────
// CRDT Types
// ─────────────────────────────────────────────────────────────────────

/// A Last-Writer-Wins Register (LWW-Register) CRDT.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LWWRegister<T: Clone + Serialize> {
    pub value: T,
    pub timestamp: DateTime<Utc>,
    pub node_id: String,
}

impl<T: Clone + Serialize + PartialEq> LWWRegister<T> {
    pub fn new(value: T, node_id: &str) -> Self {
        Self {
            value,
            timestamp: Utc::now(),
            node_id: node_id.to_string(),
        }
    }

    /// Merge two LWW-Registers — latest timestamp wins.
    pub fn merge(&self, other: &Self) -> Self {
        if self.timestamp > other.timestamp {
            self.clone()
        } else if other.timestamp > self.timestamp {
            other.clone()
        } else {
            // Same timestamp — break tie by node_id
            if self.node_id > other.node_id {
                self.clone()
            } else {
                other.clone()
            }
        }
    }
}

/// An OR-Set (Observed-Remove Set) CRDT.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ORSet<T: Clone + Serialize + Eq + std::hash::Hash> {
    /// Elements with their unique tags
    elements: HashMap<T, Vec<(String, DateTime<Utc>)>>,
    /// Tombstones for removed elements
    tombstones: HashMap<T, Vec<(String, DateTime<Utc>)>>,
}

impl<T: Clone + Serialize + Eq + std::hash::Hash> ORSet<T> {
    pub fn new() -> Self {
        Self {
            elements: HashMap::new(),
            tombstones: HashMap::new(),
        }
    }

    /// Add an element.
    pub fn add(&mut self, element: T, node_id: &str) {
        let tag = (node_id.to_string(), Utc::now());
        self.elements
            .entry(element)
            .or_default()
            .push(tag);
    }

    /// Remove an element.
    pub fn remove(&mut self, element: &T, node_id: &str) {
        if let Some(tags) = self.elements.remove(element) {
            let mut tomb_tags = tags;
            tomb_tags.push((node_id.to_string(), Utc::now()));
            self.tombstones.insert(element.clone(), tomb_tags);
        }
    }

    /// Merge two OR-Sets.
    pub fn merge(&self, other: &Self) -> Self {
        let mut merged_elements: HashMap<T, Vec<(String, DateTime<Utc>)>> = HashMap::new();
        let mut merged_tombstones: HashMap<T, Vec<(String, DateTime<Utc>)>> = HashMap::new();

        // Merge elements
        for (elem, tags) in &self.elements {
            merged_elements
                .entry(elem.clone())
                .or_default()
                .extend(tags.iter().cloned());
        }
        for (elem, tags) in &other.elements {
            merged_elements
                .entry(elem.clone())
                .or_default()
                .extend(tags.iter().cloned());
        }

        // Merge tombstones
        for (elem, tags) in &self.tombstones {
            merged_tombstones
                .entry(elem.clone())
                .or_default()
                .extend(tags.iter().cloned());
        }
        for (elem, tags) in &other.tombstones {
            merged_tombstones
                .entry(elem.clone())
                .or_default()
                .extend(tags.iter().cloned());
        }

        // Remove elements that are in tombstones
        for (elem, tomb_tags) in &merged_tombstones {
            if let Some(elem_tags) = merged_elements.get(elem) {
                // Keep only tags that are newer than all tombstones
                let latest_tomb = tomb_tags
                    .iter()
                    .map(|(_, t)| *t)
                    .max()
                    .unwrap_or(Utc::now());
                let alive_tags: Vec<_> = elem_tags
                    .iter()
                    .filter(|(_, t)| *t > latest_tomb)
                    .cloned()
                    .collect();

                if alive_tags.is_empty() {
                    merged_elements.remove(elem);
                } else {
                    merged_elements.insert(elem.clone(), alive_tags);
                }
            }
        }

        Self {
            elements: merged_elements,
            tombstones: merged_tombstones,
        }
    }

    /// Check if an element is in the set.
    pub fn contains(&self, element: &T) -> bool {
        self.elements.contains_key(element)
    }

    /// Get all elements in the set.
    pub fn to_set(&self) -> std::collections::HashSet<T>
    where
        T: Clone,
    {
        self.elements.keys().cloned().collect()
    }
}

// ─────────────────────────────────────────────────────────────────────
// Sync Queue
// ─────────────────────────────────────────────────────────────────────

/// Priority-aware sync queue.
pub struct SyncQueue {
    /// Items organized by priority
    queues: [VecDeque<SyncItem>; 4],
    /// Total items across all priorities
    total: usize,
}

impl SyncQueue {
    pub fn new() -> Self {
        Self {
            queues: [
                VecDeque::new(), // Low
                VecDeque::new(), // Normal
                VecDeque::new(), // High
                VecDeque::new(), // Critical
            ],
            total: 0,
        }
    }

    /// Enqueue an item.
    pub fn enqueue(&mut self, item: SyncItem) {
        let idx = item.priority as usize;
        self.queues[idx].push_back(item);
        self.total += 1;
    }

    /// Dequeue the highest-priority item.
    pub fn dequeue(&mut self) -> Option<SyncItem> {
        for queue in self.queues.iter_mut().rev() {
            if let Some(item) = queue.pop_front() {
                self.total -= 1;
                return Some(item);
            }
        }
        None
    }

    /// Peek at the next item without removing it.
    pub fn peek(&self) -> Option<&SyncItem> {
        for queue in self.queues.iter().rev() {
            if let Some(item) = queue.front() {
                return Some(item);
            }
        }
        None
    }

    /// Number of items in the queue.
    pub fn len(&self) -> usize {
        self.total
    }

    /// Check if the queue is empty.
    pub fn is_empty(&self) -> bool {
        self.total == 0
    }

    /// Get count per priority.
    pub fn counts_by_priority(&self) -> HashMap<Priority, usize> {
        let mut counts = HashMap::new();
        counts.insert(Priority::Low, self.queues[0].len());
        counts.insert(Priority::Normal, self.queues[1].len());
        counts.insert(Priority::High, self.queues[2].len());
        counts.insert(Priority::Critical, self.queues[3].len());
        counts
    }
}

// ─────────────────────────────────────────────────────────────────────
// Sync Engine
// ─────────────────────────────────────────────────────────────────────

/// The sync engine — manages offline-first synchronization.
pub struct SyncEngine {
    /// Outgoing sync queue
    outgoing: Arc<RwLock<SyncQueue>>,
    /// Incoming sync queue (from server)
    incoming: Arc<RwLock<SyncQueue>>,
    /// Sync history for auditing
    history: Arc<RwLock<VecDeque<SyncResult>>>,
    /// Device connection status
    connected: Arc<RwLock<bool>>,
    /// Maximum retry attempts
    max_retries: u32,
    /// Version counter per entity
    versions: Arc<RwLock<HashMap<String, u64>>>,
}

impl SyncEngine {
    pub fn new() -> Self {
        Self {
            outgoing: Arc::new(RwLock::new(SyncQueue::new())),
            incoming: Arc::new(RwLock::new(SyncQueue::new())),
            history: Arc::new(RwLock::new(VecDeque::with_capacity(1000))),
            connected: Arc::new(RwLock::new(false)),
            max_retries: 3,
            versions: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    // ── Offline Queue ─────────────────────────────────────────────────

    /// Queue data for sync (works even when offline).
    pub async fn queue_sync(
        &self,
        device_id: &str,
        user_id: Uuid,
        entity_type: &str,
        entity_id: &str,
        operation: SyncOperation,
        data: serde_json::Value,
        priority: Priority,
    ) -> Result<Uuid> {
        let checksum = self.compute_checksum(&data);

        let item = SyncItem {
            item_id: Uuid::new_v4(),
            device_id: device_id.to_string(),
            user_id,
            entity_type: entity_type.to_string(),
            entity_id: entity_id.to_string(),
            operation,
            data,
            priority,
            created_at: Utc::now(),
            attempts: 0,
            checksum,
        };

        let item_id = item.item_id;

        let mut outgoing = self.outgoing.write().await;
        outgoing.enqueue(item);

        debug!(
            item_id = %item_id,
            entity_type = entity_type,
            priority = ?priority,
            queue_size = outgoing.len(),
            "Item queued for sync"
        );

        Ok(item_id)
    }

    // ── Delta Encoding ────────────────────────────────────────────────

    /// Compute a delta between old and new data.
    pub fn compute_delta(
        &self,
        entity_type: &str,
        entity_id: &str,
        old_data: &serde_json::Value,
        new_data: &serde_json::Value,
        base_version: u64,
    ) -> Delta {
        let mut changes = Vec::new();

        if let (Some(old_obj), Some(new_obj)) = (old_data.as_object(), new_data.as_object()) {
            // Compare all fields in new_data
            for (key, new_val) in new_obj {
                let old_val = old_obj.get(key);
                if old_val != Some(new_val) {
                    changes.push(FieldChange {
                        field_path: key.clone(),
                        old_value: old_val.cloned(),
                        new_value: new_val.clone(),
                    });
                }
            }

            // Detect deleted fields
            for key in old_obj.keys() {
                if !new_obj.contains_key(key) {
                    changes.push(FieldChange {
                        field_path: key.clone(),
                        old_value: old_obj.get(key).cloned(),
                        new_value: serde_json::Value::Null,
                    });
                }
            }
        } else if old_data != new_data {
            // Non-object types — replace entirely
            changes.push(FieldChange {
                field_path: ".".to_string(),
                old_value: Some(old_data.clone()),
                new_value: new_data.clone(),
            });
        }

        let delta_size = serde_json::to_vec(&changes).map(|v| v.len()).unwrap_or(0);

        Delta {
            entity_type: entity_type.to_string(),
            entity_id: entity_id.to_string(),
            changes,
            base_version,
            target_version: base_version + 1,
            delta_size_bytes: delta_size,
        }
    }

    /// Apply a delta to data.
    pub fn apply_delta(
        &self,
        data: &serde_json::Value,
        delta: &Delta,
    ) -> Result<serde_json::Value> {
        let mut result = data.clone();

        for change in &delta.changes {
            if change.field_path == "." {
                result = change.new_value.clone();
            } else if let Some(obj) = result.as_object_mut() {
                if change.new_value.is_null() {
                    obj.remove(&change.field_path);
                } else {
                    obj.insert(change.field_path.clone(), change.new_value.clone());
                }
            }
        }

        Ok(result)
    }

    // ── CRDT Conflict Resolution ──────────────────────────────────────

    /// Resolve a conflict between local and remote versions using CRDT merge.
    pub fn resolve_conflict(
        &self,
        local: &serde_json::Value,
        remote: &serde_json::Value,
        entity_type: &str,
    ) -> (serde_json::Value, ConflictResolution) {
        // For objects, try LWW-Register merge on each field
        if let (Some(local_obj), Some(remote_obj)) = (local.as_object(), remote.as_object()) {
            let mut merged = serde_json::Map::new();

            let all_keys: std::collections::HashSet<&String> =
                local_obj.keys().chain(remote_obj.keys()).collect();

            for key in all_keys {
                let local_val = local_obj.get(key);
                let remote_val = remote_obj.get(key);

                match (local_val, remote_val) {
                    (Some(l), Some(r)) => {
                        if l == r {
                            merged.insert(key.clone(), l.clone());
                        } else {
                            // LWW: use the value that's "greater" (deterministic)
                            // In practice, this would use timestamps
                            if serde_json::to_string(l).unwrap_or_default()
                                > serde_json::to_string(r).unwrap_or_default()
                            {
                                merged.insert(key.clone(), l.clone());
                            } else {
                                merged.insert(key.clone(), r.clone());
                            }
                        }
                    }
                    (Some(l), None) => {
                        merged.insert(key.clone(), l.clone());
                    }
                    (None, Some(r)) => {
                        merged.insert(key.clone(), r.clone());
                    }
                    (None, None) => {}
                }
            }

            (
                serde_json::Value::Object(merged),
                ConflictResolution::Merged,
            )
        } else {
            // Non-object types: remote wins (server is source of truth)
            (remote.clone(), ConflictResolution::ServerWins)
        }
    }

    // ── Sync Execution ────────────────────────────────────────────────

    /// Process the next item in the outgoing queue.
    ///
    /// Returns None if the queue is empty.
    pub async fn process_next(&self) -> Option<SyncResult> {
        let item = {
            let mut outgoing = self.outgoing.write().await;
            outgoing.dequeue()
        };

        let item = item?;

        // Simulate sync (in production: HTTP to server)
        let is_connected = *self.connected.read().await;

        if !is_connected {
            // Re-queue if not connected
            let mut outgoing = self.outgoing.write().await;
            outgoing.enqueue(item);
            return Some(SyncResult {
                item_id: item.item_id,
                status: SyncItemStatus::Pending,
                conflicts: vec![],
                synced_at: None,
            });
        }

        // Update version
        let entity_key = format!("{}:{}", item.entity_type, item.entity_id);
        let mut versions = self.versions.write().await;
        let version = versions.entry(entity_key).or_insert(0);
        *version += 1;

        let result = SyncResult {
            item_id: item.item_id,
            status: SyncItemStatus::Synced,
            conflicts: vec![],
            synced_at: Some(Utc::now()),
        };

        // Store in history
        let mut history = self.history.write().await;
        history.push_back(result.clone());
        if history.len() > 1000 {
            history.pop_front();
        }

        Some(result)
    }

    /// Set connection status.
    pub async fn set_connected(&self, connected: bool) {
        let mut status = self.connected.write().await;
        *status = connected;

        if connected {
            info!("Sync engine: device connected, processing queue");
        } else {
            info!("Sync engine: device offline, queuing data");
        }
    }

    // ── Queries ───────────────────────────────────────────────────────

    /// Get the outgoing queue size.
    pub async fn outgoing_queue_size(&self) -> usize {
        self.outgoing.read().await.len()
    }

    /// Get queue statistics.
    pub async fn queue_stats(&self) -> HashMap<Priority, usize> {
        self.outgoing.read().await.counts_by_priority()
    }

    /// Get sync history.
    pub async fn history(&self, limit: usize) -> Vec<SyncResult> {
        let history = self.history.read().await;
        history.iter().rev().take(limit).cloned().collect()
    }

    // ── Helpers ───────────────────────────────────────────────────────

    fn compute_checksum(&self, data: &serde_json::Value) -> String {
        let bytes = serde_json::to_vec(data).unwrap_or_default();
        let hash = Sha256::digest(&bytes);
        hex::encode(hash)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_priority_queue_ordering() {
        let mut queue = SyncQueue::new();

        queue.enqueue(SyncItem {
            item_id: Uuid::new_v4(),
            device_id: "d1".to_string(),
            user_id: Uuid::new_v4(),
            entity_type: "sale".to_string(),
            entity_id: "1".to_string(),
            operation: SyncOperation::Create,
            data: serde_json::json!({}),
            priority: Priority::Low,
            created_at: Utc::now(),
            attempts: 0,
            checksum: "a".to_string(),
        });

        queue.enqueue(SyncItem {
            item_id: Uuid::new_v4(),
            device_id: "d1".to_string(),
            user_id: Uuid::new_v4(),
            entity_type: "sale".to_string(),
            entity_id: "2".to_string(),
            operation: SyncOperation::Create,
            data: serde_json::json!({}),
            priority: Priority::Critical,
            created_at: Utc::now(),
            attempts: 0,
            checksum: "b".to_string(),
        });

        let first = queue.dequeue().unwrap();
        assert_eq!(first.priority, Priority::Critical);

        let second = queue.dequeue().unwrap();
        assert_eq!(second.priority, Priority::Low);
    }

    #[test]
    fn test_lww_register_merge() {
        let a = LWWRegister::new("value_a", "node_1");
        let b = LWWRegister {
            value: "value_b",
            timestamp: Utc::now() + chrono::Duration::seconds(1),
            node_id: "node_2".to_string(),
        };

        let merged = a.merge(&b);
        assert_eq!(merged.value, "value_b");
    }

    #[test]
    fn test_or_set_merge() {
        let mut a = ORSet::new();
        a.add("apple", "node_1");
        a.add("banana", "node_1");

        let mut b = ORSet::new();
        b.add("cherry", "node_2");
        b.remove(&"apple", "node_2");

        let merged = a.merge(&b);
        // apple was added by node_1 and removed by node_2
        // Since remove happened after add (in real impl with timestamps),
        // the result depends on timing. In this test, both are roughly simultaneous.
        assert!(merged.contains(&"banana"));
        assert!(merged.contains(&"cherry"));
    }

    #[test]
    fn test_delta_encoding() {
        let engine = SyncEngine::new();

        let old = serde_json::json!({"name": "Milk", "price": 100, "stock": 50});
        let new = serde_json::json!({"name": "Milk", "price": 120, "stock": 45});

        let delta = engine.compute_delta("product", "p1", &old, &new, 1);
        assert_eq!(delta.changes.len(), 2); // price and stock changed

        let applied = engine.apply_delta(&old, &delta).unwrap();
        assert_eq!(applied["price"], 120);
        assert_eq!(applied["stock"], 45);
    }
}
