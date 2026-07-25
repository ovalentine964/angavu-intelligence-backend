use serde::{Deserialize, Serialize};
use anyhow::{Result, Context};
use sha2::{Sha256, Digest};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelUpdate {
    pub model_name: String,
    pub version: String,
    pub delta_size_bytes: u64,
    pub checksum: String,
    pub full_size_bytes: u64,
    pub compression_ratio: f64,
    pub delta: Vec<u8>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeltaManifest {
    pub model_name: String,
    pub from_version: String,
    pub to_version: String,
    pub delta_checksum: String,
    pub full_checksum: String,
    pub delta_size: u64,
    pub full_size: u64,
    pub entries: Vec<DeltaEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeltaEntry {
    pub offset: u32,
    pub length: u32,
    pub new_data: Vec<u8>,
}

pub struct ModelDistributor;

impl ModelDistributor {
    pub fn new() -> Self { Self }

    /// Create a sparse delta: encode only changed bytes.
    /// Format: [offset:u32_le][length:u16_le][data...][offset:u32_le][length:u16_le][data...]...
    /// Terminated by offset=0xFFFFFFFF sentinel.
    pub fn create_delta(&self, old_weights: &[u8], new_weights: &[u8]) -> Vec<u8> {
        let mut delta = Vec::new();
        let max_len = old_weights.len().max(new_weights.len());

        let mut i = 0usize;
        while i < max_len {
            let old_byte = if i < old_weights.len() { old_weights[i] } else { 0 };
            let new_byte = if i < new_weights.len() { new_weights[i] } else { 0 };

            if old_byte != new_byte {
                // Find run of changed bytes
                let start = i;
                while i < max_len {
                    let ob = if i < old_weights.len() { old_weights[i] } else { 0 };
                    let nb = if i < new_weights.len() { new_weights[i] } else { 0 };
                    if ob == nb { break; }
                    i += 1;
                }
                let run_len = i - start;

                // Write delta entry: offset(4) + length(2) + data
                delta.extend_from_slice(&(start as u32).to_le_bytes());
                delta.extend_from_slice(&(run_len as u16).to_le_bytes());
                for j in start..i {
                    let b = if j < new_weights.len() { new_weights[j] } else { 0 };
                    delta.push(b);
                }
            } else {
                i += 1;
            }
        }

        // Sentinel
        delta.extend_from_slice(&0xFFFFFFFFu32.to_le_bytes());
        delta
    }

    /// Apply a delta to old weights to reconstruct new weights.
    pub fn apply_delta(&self, old_weights: &[u8], delta: &[u8]) -> Result<Vec<u8>> {
        let mut result = old_weights.to_vec();
        let mut pos = 0usize;

        while pos + 6 <= delta.len() {
            let offset = u32::from_le_bytes([delta[pos], delta[pos+1], delta[pos+2], delta[pos+3]]) as usize;
            if offset == 0xFFFFFFFF {
                break; // Sentinel
            }
            let length = u16::from_le_bytes([delta[pos+4], delta[pos+5]]) as usize;
            pos += 6;

            if pos + length > delta.len() {
                anyhow::bail!("Delta truncated: expected {} bytes at pos {}, have {}", length, pos, delta.len() - pos);
            }

            // Extend result if needed
            if offset + length > result.len() {
                result.resize(offset + length, 0);
            }

            result[offset..offset + length].copy_from_slice(&delta[pos..pos + length]);
            pos += length;
        }

        Ok(result)
    }

    /// Compute SHA-256 hash of data, returned as hex string.
    pub fn sha256_hex(data: &[u8]) -> String {
        let mut hasher = Sha256::new();
        hasher.update(data);
        format!("{:x}", hasher.finalize())
    }

    /// Verify a delta's integrity by checking its SHA-256 hash.
    pub fn verify_delta(&self, delta: &[u8], expected_checksum: &str) -> bool {
        let actual = Self::sha256_hex(delta);
        actual == expected_checksum
    }

    /// Package a model update with delta, checksums, and compression stats.
    pub fn package_update(
        &self,
        model_name: &str,
        version: &str,
        old_weights: &[u8],
        new_weights: &[u8],
    ) -> ModelUpdate {
        let delta = self.create_delta(old_weights, new_weights);
        let checksum = Self::sha256_hex(&delta);
        let full_checksum = Self::sha256_hex(new_weights);
        let compression_ratio = if new_weights.is_empty() {
            0.0
        } else {
            delta.len() as f64 / new_weights.len() as f64
        };

        ModelUpdate {
            model_name: model_name.to_string(),
            version: version.to_string(),
            delta_size_bytes: delta.len() as u64,
            checksum,
            full_size_bytes: new_weights.len() as u64,
            compression_ratio: (compression_ratio * 100.0).round() / 100.0,
            delta,
        }
    }

    /// Create a manifest with full metadata for distribution.
    pub fn create_manifest(
        &self,
        model_name: &str,
        from_version: &str,
        to_version: &str,
        old_weights: &[u8],
        new_weights: &[u8],
    ) -> DeltaManifest {
        let delta = self.create_delta(old_weights, new_weights);

        // Parse delta entries for the manifest
        let mut entries = Vec::new();
        let mut pos = 0usize;
        while pos + 6 <= delta.len() {
            let offset = u32::from_le_bytes([delta[pos], delta[pos+1], delta[pos+2], delta[pos+3]]);
            if offset == 0xFFFFFFFF { break; }
            let length = u16::from_le_bytes([delta[pos+4], delta[pos+5]]) as usize;
            pos += 6;
            if pos + length > delta.len() { break; }
            entries.push(DeltaEntry {
                offset,
                length: length as u32,
                new_data: delta[pos..pos + length].to_vec(),
            });
            pos += length;
        }

        DeltaManifest {
            model_name: model_name.to_string(),
            from_version: from_version.to_string(),
            to_version: to_version.to_string(),
            delta_checksum: Self::sha256_hex(&delta),
            full_checksum: Self::sha256_hex(new_weights),
            delta_size: delta.len() as u64,
            full_size: new_weights.len() as u64,
            entries,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_create_and_apply_delta() {
        let distributor = ModelDistributor::new();
        let old = vec![1u8, 2, 3, 4, 5];
        let new = vec![1u8, 9, 3, 8, 5];

        let delta = distributor.create_delta(&old, &new);
        let reconstructed = distributor.apply_delta(&old, &delta).unwrap();
        assert_eq!(reconstructed, new);
    }

    #[test]
    fn test_delta_no_changes() {
        let distributor = ModelDistributor::new();
        let data = vec![1u8, 2, 3, 4, 5];
        let delta = distributor.create_delta(&data, &data);
        // Should just be the sentinel
        assert_eq!(delta.len(), 4); // 4-byte sentinel only
    }

    #[test]
    fn test_delta_new_longer() {
        let distributor = ModelDistributor::new();
        let old = vec![1u8, 2, 3];
        let new = vec![1u8, 2, 3, 4, 5, 6];

        let delta = distributor.create_delta(&old, &new);
        let reconstructed = distributor.apply_delta(&old, &delta).unwrap();
        assert_eq!(reconstructed, new);
    }

    #[test]
    fn test_delta_old_longer() {
        let distributor = ModelDistributor::new();
        let old = vec![1u8, 2, 3, 4, 5, 6];
        let new = vec![1u8, 2, 3];

        let delta = distributor.create_delta(&old, &new);
        let reconstructed = distributor.apply_delta(&old, &delta).unwrap();
        assert_eq!(reconstructed, new);
    }

    #[test]
    fn test_sha256_hex() {
        let hash = ModelDistributor::sha256_hex(b"hello");
        assert_eq!(hash.len(), 64); // SHA-256 = 32 bytes = 64 hex chars
        // Known hash of "hello"
        assert_eq!(hash, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
    }

    #[test]
    fn test_verify_delta() {
        let distributor = ModelDistributor::new();
        let old = vec![0u8; 100];
        let new = vec![1u8; 100];
        let delta = distributor.create_delta(&old, &new);
        let checksum = ModelDistributor::sha256_hex(&delta);

        assert!(distributor.verify_delta(&delta, &checksum));
        assert!(!distributor.verify_delta(&delta, "deadbeef"));
    }

    #[test]
    fn test_package_update() {
        let distributor = ModelDistributor::new();
        let old = vec![0u8; 1000];
        let new = vec![0u8; 1000];
        let mut new_changed = new.clone();
        new_changed[500] = 42;
        new_changed[501] = 43;

        let update = distributor.package_update("test-model", "1.0.1", &old, &new_changed);
        assert_eq!(update.model_name, "test-model");
        assert_eq!(update.version, "1.0.1");
        assert!(update.delta_size_bytes > 0);
        assert!(update.delta_size_bytes < update.full_size_bytes);
        assert!(update.compression_ratio < 1.0);
        assert_eq!(update.checksum.len(), 64);
    }

    #[test]
    fn test_create_manifest() {
        let distributor = ModelDistributor::new();
        let old = vec![1u8, 2, 3, 4, 5];
        let new = vec![1u8, 9, 3, 8, 5];

        let manifest = distributor.create_manifest("model-a", "v1", "v2", &old, &new);
        assert_eq!(manifest.model_name, "model-a");
        assert_eq!(manifest.from_version, "v1");
        assert_eq!(manifest.to_version, "v2");
        assert!(manifest.delta_checksum.len() == 64);
        assert!(manifest.full_checksum.len() == 64);
        assert_eq!(manifest.entries.len(), 2); // two changed bytes
    }

    #[test]
    fn test_delta_compression_ratio() {
        let distributor = ModelDistributor::new();
        // Large identical data → tiny delta
        let old = vec![0u8; 10000];
        let mut new = old.clone();
        new[9999] = 1; // single byte change

        let update = distributor.package_update("big-model", "2.0", &old, &new);
        // Delta should be much smaller than full weights
        assert!(update.delta_size_bytes < 20, "Delta should be ~10 bytes for 1-byte change, got {}", update.delta_size_bytes);
        assert!(update.compression_ratio < 0.01);
    }

    #[test]
    fn test_apply_delta_roundtrip_large() {
        let distributor = ModelDistributor::new();
        let mut old = vec![0u8; 1000];
        let mut new = vec![0u8; 1000];
        // Random-ish changes
        for i in (0..1000).step_by(7) {
            new[i] = (i % 256) as u8;
        }

        let delta = distributor.create_delta(&old, &new);
        let result = distributor.apply_delta(&old, &delta).unwrap();
        assert_eq!(result, new);
    }
}
