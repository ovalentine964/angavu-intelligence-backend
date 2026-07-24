use base64::{engine::general_purpose::STANDARD as B64, Engine};
use pyo3::prelude::*;

/// Generate a cryptographically secure random key.
///
/// Args:
///     length: Key length in bytes (default 32 for AES-256).
///
/// Returns:
///     Base64-encoded key string.
#[pyfunction]
#[pyo3(signature = (length=32))]
pub fn generate_key(length: usize) -> String {
    let mut key = vec![0u8; length];
    for byte in key.iter_mut() {
        *byte = rand::random();
    }
    B64.encode(&key)
}

/// Generate a pair of hex-encoded random keys (e.g. for signing + encryption).
///
/// Returns:
///     Tuple of two hex strings, each 64 hex chars (32 bytes).
#[pyfunction]
pub fn generate_key_pair_hex() -> (String, String) {
    let k1: [u8; 32] = rand::random();
    let k2: [u8; 32] = rand::random();
    (hex::encode(k1), hex::encode(k2))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn key_length() {
        let k = generate_key(32);
        let bytes = B64.decode(&k).unwrap();
        assert_eq!(bytes.len(), 32);
    }

    #[test]
    fn pair_different() {
        let (a, b) = generate_key_pair_hex();
        assert_ne!(a, b);
        assert_eq!(a.len(), 64);
    }
}
