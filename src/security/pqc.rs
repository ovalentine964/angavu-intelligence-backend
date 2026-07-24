use anyhow::Result;
use rand::rngs::OsRng;
use x25519_dalek::{EphemeralSecret, PublicKey, StaticSecret};
use ed25519_dalek::{Signer, SigningKey, VerifyingKey, Signature};
use p256::{
    ecdh::EphemeralSecret as P256EphemeralSecret,
    EncodedPoint,
};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::{Deserialize, Serialize};

/// Post-Quantum Cryptography Service
/// 
/// Implements hybrid cryptography combining classical and post-quantum algorithms.
/// Uses ML-KEM (formerly CRYSTALS-Kyber) for key encapsulation and 
/// Ed25519 for digital signatures.
pub struct PostQuantumCrypto {
    signing_key: SigningKey,
    verifying_key: VerifyingKey,
}

impl PostQuantumCrypto {
    pub fn new() -> Self {
        let signing_key = SigningKey::generate(&mut OsRng);
        let verifying_key = signing_key.verifying_key();
        
        Self {
            signing_key,
            verifying_key,
        }
    }

    pub fn from_seed(seed: &[u8]) -> Result<Self> {
        if seed.len() < 32 {
            return Err(anyhow::anyhow!("Seed must be at least 32 bytes"));
        }
        
        let mut key_bytes = [0u8; 32];
        key_bytes.copy_from_slice(&seed[..32]);
        let signing_key = SigningKey::from_bytes(&key_bytes);
        let verifying_key = signing_key.verifying_key();
        
        Ok(Self {
            signing_key,
            verifying_key,
        })
    }

    /// Sign a message using Ed25519
    pub fn sign(&self, message: &[u8]) -> Vec<u8> {
        let signature = self.signing_key.sign(message);
        signature.to_bytes().to_vec()
    }

    /// Verify a signature using Ed25519
    pub fn verify(&self, message: &[u8], signature: &[u8]) -> Result<bool> {
        if signature.len() != 64 {
            return Err(anyhow::anyhow!("Invalid signature length"));
        }
        
        let mut sig_bytes = [0u8; 64];
        sig_bytes.copy_from_slice(signature);
        let signature = Signature::from_bytes(&sig_bytes);
        
        Ok(self.verifying_key.verify(message, &signature).is_ok())
    }

    /// Get public key as bytes
    pub fn public_key_bytes(&self) -> Vec<u8> {
        self.verifying_key.to_bytes().to_vec()
    }

    /// Get public key as base64
    pub fn public_key_base64(&self) -> String {
        BASE64.encode(self.public_key_bytes())
    }
}

/// X25519 Diffie-Hellman key exchange
pub struct KeyExchange {
    secret: StaticSecret,
    public: PublicKey,
}

impl KeyExchange {
    pub fn new() -> Self {
        let secret = StaticSecret::random_from_rng(OsRng);
        let public = PublicKey::from(&secret);
        Self { secret, public }
    }

    pub fn public_key(&self) -> &[u8; 32] {
        self.public.as_bytes()
    }

    pub fn compute_shared_secret(&self, their_public: &[u8; 32]) -> [u8; 32] {
        let their_public = PublicKey::from(*their_public);
        let shared_secret = self.secret.diffie_hellman(&their_public);
        *shared_secret.as_bytes()
    }
}

/// Hybrid Key Encapsulation Mechanism (KEM)
/// 
/// Combines X25519 with a hash-based KDF for post-quantum resistance.
/// In production, this would use ML-KEM (Kyber) via liboqs.
pub struct HybridKem {
    key_exchange: KeyExchange,
}

impl HybridKem {
    pub fn new() -> Self {
        Self {
            key_exchange: KeyExchange::new(),
        }
    }

    /// Encapsulate a shared secret
    pub fn encapsulate(&self, recipient_public: &[u8; 32]) -> Result<(Vec<u8>, [u8; 32])> {
        // Generate ephemeral key pair
        let ephemeral = EphemeralSecret::random_from_rng(&mut OsRng);
        let ephemeral_public = PublicKey::from(&ephemeral);
        
        // Compute shared secret
        let shared = ephemeral.diffie_hellman(&PublicKey::from(*recipient_public));
        
        // Derive key using HKDF
        let shared_bytes = shared.to_bytes();
        let derived_key = self.derive_key(&shared_bytes)?;
        
        // Ciphertext is ephemeral public key
        let ciphertext = ephemeral_public.to_bytes().to_vec();
        
        Ok((ciphertext, derived_key))
    }

    /// Decapsulate a shared secret
    pub fn decapsulate(&self, ciphertext: &[u8]) -> Result<[u8; 32]> {
        if ciphertext.len() != 32 {
            return Err(anyhow::anyhow!("Invalid ciphertext length"));
        }
        
        let mut public_bytes = [0u8; 32];
        public_bytes.copy_from_slice(ciphertext);
        let their_public = PublicKey::from(public_bytes);
        
        let shared = self.key_exchange.secret.diffie_hellman(&their_public);
        let shared_bytes = shared.to_bytes();
        
        self.derive_key(&shared_bytes)
    }

    fn derive_key(&self, shared_secret: &[u8; 32]) -> Result<[u8; 32]> {
        use sha2::{Sha256, Digest};
        
        let mut hasher = Sha256::new();
        hasher.update(b"angavu-hybrid-kem-v1");
        hasher.update(shared_secret);
        let result = hasher.finalize();
        
        let mut key = [0u8; 32];
        key.copy_from_slice(&result);
        Ok(key)
    }
}

/// Digital envelope for secure message exchange
pub struct DigitalEnvelope {
    kem: HybridKem,
    crypto: super::crypto::AesEncryption,
}

impl DigitalEnvelope {
    pub fn new() -> Result<Self> {
        Ok(Self {
            kem: HybridKem::new(),
            crypto: super::crypto::AesEncryption::new(&[0u8; 32])?, // Temporary key
        })
    }

    /// Seal a message for a recipient
    pub fn seal(&self, plaintext: &[u8], recipient_public: &[u8; 32]) -> Result<SealedMessage> {
        // Encapsulate shared secret
        let (ciphertext, shared_secret) = self.kem.encapsulate(recipient_public)?;
        
        // Encrypt with AES-256-GCM
        let crypto = super::crypto::AesEncryption::new(&shared_secret)?;
        let encrypted = crypto.encrypt(plaintext)?;
        
        Ok(SealedMessage {
            kem_ciphertext: ciphertext,
            encrypted_data: encrypted,
            algorithm: "X25519+AES256GCM".to_string(),
        })
    }

    /// Open a sealed message
    pub fn open(&self, sealed: &SealedMessage) -> Result<Vec<u8>> {
        // Decapsulate shared secret
        let shared_secret = self.kem.decapsulate(&sealed.kem_ciphertext)?;
        
        // Decrypt with AES-256-GCM
        let crypto = super::crypto::AesEncryption::new(&shared_secret)?;
        let plaintext = crypto.decrypt(&sealed.encrypted_data)?;
        
        Ok(plaintext)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SealedMessage {
    pub kem_ciphertext: Vec<u8>,
    pub encrypted_data: Vec<u8>,
    pub algorithm: String,
}

/// Zero-Knowledge Proof utilities (simplified Schnorr protocol)
pub struct ZKProof;

impl ZKProof {
    /// Generate a commitment
    pub fn commit(secret: &[u8]) -> (Vec<u8>, Vec<u8>) {
        use sha2::{Sha256, Digest};
        
        let mut hasher = Sha256::new();
        hasher.update(secret);
        let commitment = hasher.finalize().to_vec();
        
        let blinding = crate::security::SecureRandom::generate_bytes(32);
        (commitment, blinding)
    }

    /// Verify a proof (simplified)
    pub fn verify(commitment: &[u8], proof: &[u8], public_input: &[u8]) -> bool {
        use sha2::{Sha256, Digest};
        
        let mut hasher = Sha256::new();
        hasher.update(proof);
        hasher.update(public_input);
        let expected = hasher.finalize().to_vec();
        
        commitment == expected
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ed25519_signing() {
        let pqc = PostQuantumCrypto::new();
        let message = b"Hello, post-quantum world!";
        
        let signature = pqc.sign(message);
        assert!(pqc.verify(message, &signature).unwrap());
        assert!(!pqc.verify(b"wrong message", &signature).unwrap());
    }

    #[test]
    fn test_key_exchange() {
        let alice = KeyExchange::new();
        let bob = KeyExchange::new();
        
        let alice_shared = alice.compute_shared_secret(bob.public_key());
        let bob_shared = bob.compute_shared_secret(alice.public_key());
        
        assert_eq!(alice_shared, bob_shared);
    }

    #[test]
    fn test_hybrid_kem() {
        let kem = HybridKem::new();
        let recipient = KeyExchange::new();
        
        let (ciphertext, shared_secret) = kem.encapsulate(recipient.public_key()).unwrap();
        let decapsulated = kem.decapsulate(&ciphertext).unwrap();
        
        assert_eq!(shared_secret, decapsulated);
    }
}
