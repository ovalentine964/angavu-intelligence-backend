use serde::{Deserialize, Serialize};
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize)]
pub struct ModelUpdate {
    pub model_name: String,
    pub version: String,
    pub delta_size_bytes: u64,
    pub checksum: String,
}

pub struct ModelDistributor;

impl ModelDistributor {
    pub fn new() -> Self { Self }

    pub fn create_delta(&self, old_weights: &[f8], new_weights: &[f8]) -> Vec<u8> {
        // Sparse delta encoding — only changed weights
        new_weights.iter().zip(old_weights.iter())
            .enumerate()
            .filter(|(_, (n, o))| n != o)
            .map(|(i, (n, _))| (i as u16, *n))
            .flat_map(|(idx, val)| idx.to_le_bytes().into_iter().chain(std::iter::once(val)))
            .collect()
    }

    pub fn package_update(&self, model_name: &str, version: &str, delta: &[u8]) -> ModelUpdate {
        ModelUpdate {
            model_name: model_name.to_string(),
            version: version.to_string(),
            delta_size_bytes: delta.len() as u64,
            checksum: format!("{:x}", md5::compute(delta)),
        }
    }
}
