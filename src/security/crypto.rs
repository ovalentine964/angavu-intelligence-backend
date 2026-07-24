use aes_gcm::{
    aead::{Aead, KeyInit, OsRng},
    Aes256Gcm, Nonce, Key,
};
use argon2::{
    password_hash::{rand_core::RngCore, PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
    Argon2,
};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use rand::Rng;
use sha2::{Digest, Sha256, Sha512};
use anyhow::Result;

/// AES-256-GCM encryption
pub struct AesEncryption {
    cipher: Aes256Gcm,
}

impl AesEncryption {
    pub fn new(key: &[u8]) -> Result<Self> {
        let key = Key::<Aes256Gcm>::from_slice(key);
        let cipher = Aes256Gcm::new(key);
        Ok(Self { cipher })
    }

    pub fn encrypt(&self, plaintext: &[u8]) -> Result<Vec<u8>> {
        let mut nonce_bytes = [0u8; 12];
        OsRng.fill_bytes(&mut nonce_bytes);
        let nonce = Nonce::from_slice(&nonce_bytes);
        
        let ciphertext = self.cipher.encrypt(nonce, plaintext)
            .map_err(|e| anyhow::anyhow!("Encryption failed: {}", e))?;
        
        let mut result = nonce_bytes.to_vec();
        result.extend_from_slice(&ciphertext);
        Ok(result)
    }

    pub fn decrypt(&self, data: &[u8]) -> Result<Vec<u8>> {
        if data.len() < 12 {
            return Err(anyhow::anyhow!("Invalid ciphertext"));
        }
        
        let (nonce_bytes, ciphertext) = data.split_at(12);
        let nonce = Nonce::from_slice(nonce_bytes);
        
        let plaintext = self.cipher.decrypt(nonce, ciphertext)
            .map_err(|e| anyhow::anyhow!("Decryption failed: {}", e))?;
        
        Ok(plaintext)
    }

    pub fn encrypt_to_base64(&self, plaintext: &[u8]) -> Result<String> {
        let encrypted = self.encrypt(plaintext)?;
        Ok(BASE64.encode(encrypted))
    }

    pub fn decrypt_from_base64(&self, data: &str) -> Result<Vec<u8>> {
        let encrypted = BASE64.decode(data)?;
        self.decrypt(&encrypted)
    }
}

/// Password hashing with Argon2
pub struct PasswordHasherService {
    argon2: Argon2<'static>,
}

impl PasswordHasherService {
    pub fn new() -> Self {
        Self {
            argon2: Argon2::default(),
        }
    }

    pub fn hash_password(&self, password: &str) -> Result<String> {
        let salt = SaltString::generate(&mut OsRng);
        let password_hash = self.argon2
            .hash_password(password.as_bytes(), &salt)
            .map_err(|e| anyhow::anyhow!("Password hashing failed: {}", e))?;
        Ok(password_hash.to_string())
    }

    pub fn verify_password(&self, password: &str, hash: &str) -> Result<bool> {
        let parsed_hash = PasswordHash::new(hash)
            .map_err(|e| anyhow::anyhow!("Invalid password hash: {}", e))?;
        
        let valid = self.argon2
            .verify_password(password.as_bytes(), &parsed_hash)
            .is_ok();
        
        Ok(valid)
    }
}

/// SHA-256/512 hashing
pub struct HashService;

impl HashService {
    pub fn sha256(data: &[u8]) -> Vec<u8> {
        let mut hasher = Sha256::new();
        hasher.update(data);
        hasher.finalize().to_vec()
    }

    pub fn sha512(data: &[u8]) -> Vec<u8> {
        let mut hasher = Sha512::new();
        hasher.update(data);
        hasher.finalize().to_vec()
    }

    pub fn sha256_hex(data: &[u8]) -> String {
        hex::encode(Self::sha256(data))
    }

    pub fn sha512_hex(data: &[u8]) -> String {
        hex::encode(Self::sha512(data))
    }
}

/// HMAC authentication
pub struct HmacService {
    key: Vec<u8>,
}

impl HmacService {
    pub fn new(key: &[u8]) -> Self {
        Self { key: key.to_vec() }
    }

    pub fn sign(&self, data: &[u8]) -> Vec<u8> {
        use hmac::{Hmac, Mac};
        type HmacSha256 = Hmac<Sha256>;
        
        let mut mac = HmacSha256::new_from_slice(&self.key)
            .expect("HMAC can take key of any size");
        mac.update(data);
        mac.finalize().into_bytes().to_vec()
    }

    pub fn verify(&self, data: &[u8], signature: &[u8]) -> bool {
        use hmac::{Hmac, Mac};
        type HmacSha256 = Hmac<Sha256>;
        
        let mut mac = HmacSha256::new_from_slice(&self.key)
            .expect("HMAC can take key of any size");
        mac.update(data);
        mac.verify_slice(signature).is_ok()
    }
}

/// Secure random generation
pub struct SecureRandom;

impl SecureRandom {
    pub fn generate_bytes(len: usize) -> Vec<u8> {
        let mut bytes = vec![0u8; len];
        OsRng.fill_bytes(&mut bytes);
        bytes
    }

    pub fn generate_string(len: usize) -> String {
        let bytes = Self::generate_bytes(len);
        BASE64.encode(bytes)[..len].to_string()
    }

    pub fn generate_api_key() -> String {
        let bytes = Self::generate_bytes(32);
        format!("av_{}", BASE64.encode(bytes))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_aes_encryption() {
        let key = SecureRandom::generate_bytes(32);
        let encryptor = AesEncryption::new(&key).unwrap();
        
        let plaintext = b"Hello, World!";
        let encrypted = encryptor.encrypt(plaintext).unwrap();
        let decrypted = encryptor.decrypt(&encrypted).unwrap();
        
        assert_eq!(plaintext.to_vec(), decrypted);
    }

    #[test]
    fn test_password_hashing() {
        let hasher = PasswordHasherService::new();
        let password = "secure_password_123";
        
        let hash = hasher.hash_password(password).unwrap();
        assert!(hasher.verify_password(password, &hash).unwrap());
        assert!(!hasher.verify_password("wrong_password", &hash).unwrap());
    }

    #[test]
    fn test_hmac() {
        let key = SecureRandom::generate_bytes(32);
        let hmac = HmacService::new(&key);
        
        let data = b"test data";
        let signature = hmac.sign(data);
        
        assert!(hmac.verify(data, &signature));
        assert!(!hmac.verify(b"wrong data", &signature));
    }
}
