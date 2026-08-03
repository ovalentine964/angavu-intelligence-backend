// Angavu Intelligence Backend — Model Version Compatibility
// Checks device model version and prepares compatible updates.
//
// Rules:
// - Devices with model version < MIN_MODEL_VERSION get a full model update
// - Devices with compatible versions get delta patches
// - Devices with current version get no update
// - Version mismatches are handled gracefully with clear messages

use super::*;
use tracing::{info, warn};

pub struct VersionCompatibilityChecker {
    /// Current model version the backend serves
    current_version: semver::Version,
    /// Minimum compatible version
    min_version: semver::Version,
    /// Available model deltas
    available_deltas: Vec<ModelDeltaEntry>,
}

struct ModelDeltaEntry {
    from_version: String,
    to_version: String,
    download_url: String,
    checksum: String,
    size_bytes: u64,
}

impl VersionCompatibilityChecker {
    pub fn new() -> Self {
        Self {
            current_version: semver::Version::parse(CURRENT_MODEL_VERSION).unwrap(),
            min_version: semver::Version::parse(MIN_MODEL_VERSION).unwrap(),
            available_deltas: vec![
                ModelDeltaEntry {
                    from_version: "2.0.0".to_string(),
                    to_version: "2.1.0".to_string(),
                    download_url: "https://models.msaidizi.app/deltas/2.0.0-to-2.1.0.patch"
                        .to_string(),
                    checksum: "sha256:abc123def456".to_string(),
                    size_bytes: 512_000,
                },
                ModelDeltaEntry {
                    from_version: "1.5.0".to_string(),
                    to_version: "2.1.0".to_string(),
                    download_url: "https://models.msaidizi.app/full/model-2.1.0.bin".to_string(),
                    checksum: "sha256:full789model012".to_string(),
                    size_bytes: 15_000_000,
                },
            ],
        }
    }

    /// Check if a device's model version is compatible and prepare a delta if needed.
    ///
    /// Returns:
    /// - None if device is already on current version
    /// - Some(ModelDelta) if an update is available
    pub async fn check_and_prepare_delta(
        &self,
        device_model_version: Option<&str>,
    ) -> Option<ModelDelta> {
        let device_version_str = device_model_version?;
        let device_version = match semver::Version::parse(device_version_str) {
            Ok(v) => v,
            Err(_) => {
                warn!(
                    version = device_model_version,
                    "Invalid model version from device"
                );
                // Return full model for unknown versions
                return Some(ModelDelta {
                    target_version: self.current_version.to_string(),
                    is_full_model: true,
                    download_url: format!(
                        "https://models.msaidizi.app/full/model-{}.bin",
                        self.current_version
                    ),
                    checksum: "unknown".to_string(),
                    size_bytes: 15_000_000,
                    min_protocol_version: SYNC_PROTOCOL_VERSION,
                });
            }
        };

        // Already current
        if device_version >= self.current_version {
            info!(device = %device_version, current = %self.current_version, "Device model is current");
            return None;
        }

        // Below minimum — need full model
        if device_version < self.min_version {
            info!(
                device = %device_version,
                min = %self.min_version,
                "Device model too old, sending full update"
            );
            return Some(ModelDelta {
                target_version: self.current_version.to_string(),
                is_full_model: true,
                download_url: format!(
                    "https://models.msaidizi.app/full/model-{}.bin",
                    self.current_version
                ),
                checksum: "sha256:full_model_checksum".to_string(),
                size_bytes: 15_000_000,
                min_protocol_version: SYNC_PROTOCOL_VERSION,
            });
        }

        // Check for delta patch
        for delta in &self.available_deltas {
            if delta.from_version == device_version_str {
                info!(
                    device = %device_version,
                    target = %delta.to_version,
                    "Delta available for device"
                );
                return Some(ModelDelta {
                    target_version: delta.to_version.clone(),
                    is_full_model: false,
                    download_url: delta.download_url.clone(),
                    checksum: delta.checksum.clone(),
                    size_bytes: delta.size_bytes,
                    min_protocol_version: SYNC_PROTOCOL_VERSION,
                });
            }
        }

        // No specific delta — send full model
        info!(device = %device_version, "No delta available, sending full model");
        Some(ModelDelta {
            target_version: self.current_version.to_string(),
            is_full_model: true,
            download_url: format!(
                "https://models.msaidizi.app/full/model-{}.bin",
                self.current_version
            ),
            checksum: "sha256:full_model_checksum".to_string(),
            size_bytes: 15_000_000,
            min_protocol_version: SYNC_PROTOCOL_VERSION,
        })
    }

    /// Check if a given version string is compatible with the backend
    pub fn is_compatible(&self, version_str: &str) -> bool {
        match semver::Version::parse(version_str) {
            Ok(v) => v >= self.min_version,
            Err(_) => false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_current_version_no_update() {
        let checker = VersionCompatibilityChecker::new();
        let result = checker.check_and_prepare_delta(Some("2.1.0")).await;
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_newer_version_no_update() {
        let checker = VersionCompatibilityChecker::new();
        let result = checker.check_and_prepare_delta(Some("3.0.0")).await;
        assert!(result.is_none());
    }

    #[tokio::test]
    async fn test_old_version_gets_full_model() {
        let checker = VersionCompatibilityChecker::new();
        let result = checker.check_and_prepare_delta(Some("1.0.0")).await;
        assert!(result.is_some());
        let delta = result.unwrap();
        assert!(delta.is_full_model);
    }

    #[tokio::test]
    async fn test_compatible_version_gets_delta() {
        let checker = VersionCompatibilityChecker::new();
        let result = checker.check_and_prepare_delta(Some("2.0.0")).await;
        assert!(result.is_some());
        let delta = result.unwrap();
        assert!(!delta.is_full_model);
        assert_eq!(delta.target_version, "2.1.0");
    }

    #[tokio::test]
    async fn test_invalid_version_gets_full_model() {
        let checker = VersionCompatibilityChecker::new();
        let result = checker.check_and_prepare_delta(Some("not-a-version")).await;
        assert!(result.is_some());
        assert!(result.unwrap().is_full_model);
    }

    #[tokio::test]
    async fn test_none_version_no_update() {
        let checker = VersionCompatibilityChecker::new();
        let result = checker.check_and_prepare_delta(None).await;
        assert!(result.is_none());
    }

    #[test]
    fn test_compatibility_check() {
        let checker = VersionCompatibilityChecker::new();
        assert!(checker.is_compatible("1.5.0"));
        assert!(checker.is_compatible("2.0.0"));
        assert!(checker.is_compatible("2.1.0"));
        assert!(!checker.is_compatible("1.0.0"));
        assert!(!checker.is_compatible("invalid"));
    }
}
