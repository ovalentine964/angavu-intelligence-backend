//! SyncReceiver — Receives data from devices
//!
//! Handles encrypted data batches from Angavu worker devices, validates integrity,
//! stores anonymized data, and manages sync state.

use anyhow::{anyhow, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use uuid::Uuid;

use crate::db::DatabaseConnections;
use crate::models::{SyncStatus, SyncPayload, SyncResponse, SyncChange, SyncConflict};

/// Encrypted batch from a device
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceBatch {
    pub device_id: String,
    pub user_id: Uuid,
    pub batch_id: Uuid,
    pub encrypted_payload: Vec<u8>,
    pub checksum: String,
    pub sequence_number: u64,
    pub compression: CompressionType,
    pub submitted_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum CompressionType {
    None,
    Zstd,
    Lz4,
    Gzip,
}

/// Sync acknowledgment
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncAck {
    pub batch_id: Uuid,
    pub status: SyncStatus,
    pub server_version: i64,
    pub conflicts: Vec<SyncConflict>,
    pub next_expected_sequence: u64,
    pub processed_at: DateTime<Utc>,
}

/// The SyncReceiver tool
pub struct SyncReceiver {
    db: DatabaseConnections,
    max_batch_size_bytes: usize,
    max_sequence_gap: u64,
}

impl SyncReceiver {
    pub fn new(db: DatabaseConnections) -> Self {
        Self {
            db,
            max_batch_size_bytes: 10 * 1024 * 1024, // 10MB
            max_sequence_gap: 100,
        }
    }

    /// Receive and process an encrypted batch from a device
    pub async fn receive_batch(&self, batch: &DeviceBatch) -> Result<SyncAck> {
        // 1. Validate batch size
        if batch.encrypted_payload.len() > self.max_batch_size_bytes {
            return Err(anyhow!(
                "Batch size {} exceeds maximum {}",
                batch.encrypted_payload.len(),
                self.max_batch_size_bytes
            ));
        }

        // 2. Validate integrity (checksum)
        self.validate_integrity(batch)?;

        // 3. Validate sequence number
        let last_sequence = self.get_last_sequence(&batch.device_id).await?;
        if batch.sequence_number <= last_sequence {
            // Duplicate or out-of-order — acknowledge but skip
            return Ok(SyncAck {
                batch_id: batch.batch_id,
                status: SyncStatus::Synced,
                server_version: self.get_server_version().await?,
                conflicts: vec![],
                next_expected_sequence: last_sequence + 1,
                processed_at: Utc::now(),
            });
        }

        if batch.sequence_number > last_sequence + self.max_sequence_gap {
            return Err(anyhow!(
                "Sequence gap too large: got {}, expected <= {}",
                batch.sequence_number,
                last_sequence + self.max_sequence_gap
            ));
        }

        // 4. Decrypt payload
        let payload = self.decrypt_payload(batch)?;

        // 5. Store anonymized data
        let conflicts = self.store_anonymized(&batch.device_id, &payload).await?;

        // 6. Update sync state
        let server_version = self.update_sync_state(
            &batch.device_id,
            batch.user_id,
            batch.sequence_number,
        )
        .await?;

        // 7. Record in Redis for real-time access
        self.record_sync_event(batch).await?;

        Ok(SyncAck {
            batch_id: batch.batch_id,
            status: if conflicts.is_empty() {
                SyncStatus::Synced
            } else {
                SyncStatus::Conflict
            },
            server_version,
            conflicts,
            next_expected_sequence: batch.sequence_number + 1,
            processed_at: Utc::now(),
        })
    }

    /// Validate data integrity via checksum
    pub fn validate_integrity(&self, batch: &DeviceBatch) -> Result<()> {
        let mut hasher = Sha256::new();
        hasher.update(&batch.encrypted_payload);
        hasher.update(batch.device_id.as_bytes());
        hasher.update(&batch.sequence_number.to_le_bytes());
        let computed = hex::encode(hasher.finalize());

        if computed != batch.checksum {
            return Err(anyhow!(
                "Checksum mismatch: expected {}, got {}",
                batch.checksum,
                computed
            ));
        }

        Ok(())
    }

    /// Store anonymized data from the batch
    pub async fn store_anonymized(
        &self,
        device_id: &str,
        payload: &SyncPayload,
    ) -> Result<Vec<SyncConflict>> {
        let mut conflicts = Vec::new();

        for change in &payload.changes {
            // Anonymize: hash the entity_id to break linkability
            let anonymized_id = self.anonymize_entity_id(&change.entity_id.to_string());

            // Check for conflicts
            let existing = self
                .get_existing_version(device_id, &change.entity_type, &anonymized_id)
                .await?;

            if let Some((existing_version, existing_data)) = existing {
                if existing_version >= change.version {
                    conflicts.push(SyncConflict {
                        entity_type: change.entity_type.clone(),
                        entity_id: change.entity_id,
                        local_version: existing_data,
                        remote_version: change.data.clone(),
                        resolution: crate::models::ConflictResolution::RemoteWins,
                    });
                    continue;
                }
            }

            // Store in ClickHouse for analytics
            #[derive(clickhouse::Row, Serialize)]
            struct SyncDataRow {
                event_id: String,
                device_id: String,
                entity_type: String,
                anonymized_id: String,
                operation: String,
                data: String,
                version: u64,
                event_time: chrono::NaiveDateTime,
            }

            let row = SyncDataRow {
                event_id: Uuid::new_v4().to_string(),
                device_id: device_id.to_string(),
                entity_type: change.entity_type.clone(),
                anonymized_id,
                operation: format!("{:?}", change.operation),
                data: serde_json::to_string(&change.data).unwrap_or_default(),
                version: change.version as u64,
                event_time: change.timestamp.naive_utc(),
            };

            if let Ok(mut insert) = self.db.clickhouse.insert("sync_data") {
                let _ = insert.write(&row).await;
                let _ = insert.end().await;
            }
        }

        Ok(conflicts)
    }

    // Private helpers

    fn anonymize_entity_id(&self, entity_id: &str) -> String {
        let mut hasher = Sha256::new();
        hasher.update(b"angavu-anonymization-v1");
        hasher.update(entity_id.as_bytes());
        hex::encode(hasher.finalize())
    }

    fn decrypt_payload(&self, batch: &DeviceBatch) -> Result<SyncPayload> {
        // In production: use device key exchange to decrypt
        // For now, attempt JSON deserialization
        serde_json::from_slice(&batch.encrypted_payload)
            .map_err(|e| anyhow!("Failed to decrypt/deserialize payload: {}", e))
    }

    async fn get_last_sequence(&self, device_id: &str) -> Result<u64> {
        let mut conn = self.db.redis.clone();
        use redis::AsyncCommands;

        let key = format!("sync:seq:{}", device_id);
        let seq: Option<u64> = conn.get(&key).await?;
        Ok(seq.unwrap_or(0))
    }

    async fn get_server_version(&self) -> Result<i64> {
        let mut conn = self.db.redis.clone();
        use redis::AsyncCommands;

        let version: Option<i64> = conn.get("sync:server_version").await?;
        Ok(version.unwrap_or(0))
    }

    async fn update_sync_state(
        &self,
        device_id: &str,
        user_id: Uuid,
        sequence: u64,
    ) -> Result<i64> {
        let mut conn = self.db.redis.clone();
        use redis::AsyncCommands;

        // Update sequence
        let key = format!("sync:seq:{}", device_id);
        conn.set::<_, _, ()>(&key, sequence).await?;

        // Increment server version
        let new_version: i64 = conn.incr("sync:server_version", 1).await?;

        // Update last sync time
        let ts_key = format!("sync:last_sync:{}", device_id);
        conn.set::<_, _, ()>(&ts_key, Utc::now().to_rfc3339()).await?;

        Ok(new_version)
    }

    async fn record_sync_event(&self, batch: &DeviceBatch) -> Result<()> {
        let mut conn = self.db.redis.clone();
        use redis::AsyncCommands;

        let key = format!("sync:event:{}", Uuid::new_v4());
        let event = serde_json::json!({
            "device_id": batch.device_id,
            "batch_id": batch.batch_id,
            "sequence": batch.sequence_number,
            "payload_size": batch.encrypted_payload.len(),
            "timestamp": Utc::now(),
        });

        conn.set_ex::<_, _, ()>(&key, serde_json::to_string(&event)?, 3600)
            .await?;

        Ok(())
    }

    async fn get_existing_version(
        &self,
        device_id: &str,
        entity_type: &str,
        anonymized_id: &str,
    ) -> Result<Option<(u64, serde_json::Value)>> {
        let mut conn = self.db.redis.clone();
        use redis::AsyncCommands;

        let key = format!("sync:entity:{}:{}:{}", device_id, entity_type, anonymized_id);
        let data: Option<String> = conn.get(&key).await?;

        match data {
            Some(d) => {
                let val: serde_json::Value = serde_json::from_str(&d)?;
                let version = val["version"].as_u64().unwrap_or(0);
                Ok(Some((version, val["data"].clone())))
            }
            None => Ok(None),
        }
    }
}
