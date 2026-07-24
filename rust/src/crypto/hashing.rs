use argon2::{
    password_hash::{rand_core::OsRng, PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
    Argon2,
};
use base64::{engine::general_purpose::STANDARD as B64, Engine};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use sha2::{Digest, Sha256};

/// SHA-256 hash of a UTF-8 string, returned as hex.
#[pyfunction]
pub fn sha256_hash(input: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    hex::encode(hasher.finalize())
}

/// SHA-256 hash of raw bytes (base64 input), returned as hex.
#[pyfunction]
pub fn sha256_hash_bytes(input_b64: &str) -> PyResult<String> {
    let bytes = B64
        .decode(input_b64)
        .map_err(|e| PyValueError::new_err(format!("Invalid base64 input: {e}")))?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    Ok(hex::encode(hasher.finalize()))
}

/// Argon2id hash a password. Returns the PHC-formatted hash string.
///
/// Args:
///     password: The plaintext password.
///     memory_kib: Memory cost in KiB (default 65536 = 64 MiB).
///     iterations: Number of iterations (default 3).
///     parallelism: Degree of parallelism (default 4).
#[pyfunction]
#[pyo3(signature = (password, memory_kib=65536, iterations=3, parallelism=4))]
pub fn argon2_hash(password: &str, memory_kib: u32, iterations: u32, parallelism: u32) -> PyResult<String> {
    let salt = SaltString::generate(&mut OsRng);

    let params = argon2::Params::new(memory_kib, iterations, parallelism, None)
        .map_err(|e| PyValueError::new_err(format!("Invalid Argon2 params: {e}")))?;

    let argon2 = Argon2::new(argon2::Algorithm::Argon2id, argon2::Version::V0x13, params);

    let hash = argon2
        .hash_password(password.as_bytes(), &salt)
        .map_err(|e| PyValueError::new_err(format!("Argon2 hash failed: {e}")))?;

    Ok(hash.to_string())
}

/// Verify a password against an Argon2 PHC hash.
///
/// Returns true if the password matches.
#[pyfunction]
pub fn argon2_verify(password: &str, phc_hash: &str) -> PyResult<bool> {
    let parsed = PasswordHash::new(phc_hash)
        .map_err(|e| PyValueError::new_err(format!("Invalid PHC hash string: {e}")))?;

    Ok(Argon2::default()
        .verify_password(password.as_bytes(), &parsed)
        .is_ok())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sha256_deterministic() {
        let a = sha256_hash("test");
        let b = sha256_hash("test");
        assert_eq!(a, b);
        assert_eq!(a.len(), 64);
    }

    #[test]
    fn argon2_roundtrip() {
        let hash = argon2_hash("hunter2", 1024, 1, 1).unwrap();
        assert!(argon2_verify("hunter2", &hash).unwrap());
        assert!(!argon2_verify("wrong", &hash).unwrap());
    }
}
