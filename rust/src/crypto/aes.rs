use aes_gcm::{
    aead::{Aead, KeyInit, OsRng},
    Aes256Gcm, Nonce,
};
use base64::{engine::general_purpose::STANDARD as B64, Engine};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Encrypt plaintext with AES-256-GCM.
///
/// Args:
///     plaintext: UTF-8 string to encrypt.
///     key_b64:   Base64-encoded 32-byte key.
///
/// Returns:
///     Base64-encoded ciphertext (nonce prepended, 12 + ciphertext bytes).
#[pyfunction]
pub fn encrypt_aes_gcm(plaintext: &str, key_b64: &str) -> PyResult<String> {
    let key_bytes = B64
        .decode(key_b64)
        .map_err(|e| PyValueError::new_err(format!("Invalid base64 key: {e}")))?;

    if key_bytes.len() != 32 {
        return Err(PyValueError::new_err(format!(
            "Key must be 32 bytes, got {}",
            key_bytes.len()
        )));
    }

    let cipher = Aes256Gcm::new_from_slice(&key_bytes)
        .map_err(|e| PyValueError::new_err(format!("Cipher init failed: {e}")))?;

    // 12-byte random nonce
    let nonce_bytes: [u8; 12] = rand::random();
    let nonce = Nonce::from_slice(&nonce_bytes);

    let ciphertext = cipher
        .encrypt(nonce, plaintext.as_bytes())
        .map_err(|e| PyValueError::new_err(format!("Encryption failed: {e}")))?;

    // Prepend nonce to ciphertext
    let mut output = Vec::with_capacity(12 + ciphertext.len());
    output.extend_from_slice(&nonce_bytes);
    output.extend_from_slice(&ciphertext);

    Ok(B64.encode(&output))
}

/// Decrypt AES-256-GCM ciphertext.
///
/// Args:
///     ciphertext_b64: Base64-encoded ciphertext with prepended nonce.
///     key_b64:        Base64-encoded 32-byte key.
///
/// Returns:
///     Decrypted UTF-8 plaintext.
#[pyfunction]
pub fn decrypt_aes_gcm(ciphertext_b64: &str, key_b64: &str) -> PyResult<String> {
    let key_bytes = B64
        .decode(key_b64)
        .map_err(|e| PyValueError::new_err(format!("Invalid base64 key: {e}")))?;

    if key_bytes.len() != 32 {
        return Err(PyValueError::new_err(format!(
            "Key must be 32 bytes, got {}",
            key_bytes.len()
        )));
    }

    let data = B64
        .decode(ciphertext_b64)
        .map_err(|e| PyValueError::new_err(format!("Invalid base64 ciphertext: {e}")))?;

    if data.len() < 12 {
        return Err(PyValueError::new_err("Ciphertext too short — missing nonce"));
    }

    let (nonce_bytes, ciphertext) = data.split_at(12);
    let nonce = Nonce::from_slice(nonce_bytes);

    let cipher = Aes256Gcm::new_from_slice(&key_bytes)
        .map_err(|e| PyValueError::new_err(format!("Cipher init failed: {e}")))?;

    let plaintext = cipher
        .decrypt(nonce, ciphertext)
        .map_err(|e| PyValueError::new_err(format!("Decryption failed (wrong key or tampered data): {e}")))?;

    String::from_utf8(plaintext)
        .map_err(|e| PyValueError::new_err(format!("Decrypted bytes are not valid UTF-8: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        let key = B64.encode([42u8; 32]);
        let ct = encrypt_aes_gcm("hello world", &key).unwrap();
        let pt = decrypt_aes_gcm(&ct, &key).unwrap();
        assert_eq!(pt, "hello world");
    }

    #[test]
    fn wrong_key_fails() {
        let key1 = B64.encode([1u8; 32]);
        let key2 = B64.encode([2u8; 32]);
        let ct = encrypt_aes_gcm("secret", &key1).unwrap();
        assert!(decrypt_aes_gcm(&ct, &key2).is_err());
    }
}
