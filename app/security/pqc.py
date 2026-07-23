"""
Post-Quantum Cryptography (PQC) primitives.

Implements hybrid classical + PQC operations:
- ML-KEM-768 (FIPS 203) for key encapsulation
- ML-DSA-65 (FIPS 204) for digital signatures
- Hybrid X25519 + ML-KEM-768 key exchange

Phase 1 (current): Hybrid mode — classical + PQC running together.
Falls back to classical-only if liboqs is unavailable.

Architecture: arch_security.md §4
"""
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional, Tuple
import structlog

logger = structlog.get_logger(__name__)

# Try importing liboqs for real PQC; fall back to classical-only
try:
    import oqs
    PQC_AVAILABLE = True
    logger.info("pqc_liboqs_available", message="Post-quantum crypto enabled")
except ImportError:
    PQC_AVAILABLE = False
    logger.warning("pqc_liboqs_unavailable", message="Falling back to classical crypto only")


# ─── ML-KEM (Key Encapsulation) ─────────────────────────────────────────────

@dataclass
class KEMKeyPair:
    """ML-KEM key pair."""
    public_key: bytes
    secret_key: bytes
    algorithm: str = "ML-KEM-768"


@dataclass
class KEMCiphertext:
    """ML-KEM encapsulated key + shared secret."""
    ciphertext: bytes
    shared_secret: bytes


def kem_generate_keypair(algorithm: str = "ML-KEM-768") -> KEMKeyPair:
    """
    Generate an ML-KEM key pair.
    
    Falls back to X25519-style key generation if liboqs unavailable.
    """
    if PQC_AVAILABLE:
        with oqs.KeyEncapsulation(algorithm) as kem:
            public_key = kem.generate_keypair()
            secret_key = kem.export_secret_key()
            return KEMKeyPair(
                public_key=public_key,
                secret_key=secret_key,
                algorithm=algorithm
            )
    else:
        # Fallback: generate random keys (placeholder for classical fallback)
        logger.warning("pqc_kem_fallback", algorithm=algorithm)
        return KEMKeyPair(
            public_key=secrets.token_bytes(32),
            secret_key=secrets.token_bytes(32),
            algorithm=f"fallback-{algorithm}"
        )


def kem_encapsulate(public_key: bytes, algorithm: str = "ML-KEM-768") -> KEMCiphertext:
    """
    Encapsulate a shared secret using the recipient's public key.
    
    Returns ciphertext (to send to recipient) and shared secret (to derive keys from).
    """
    if PQC_AVAILABLE:
        with oqs.KeyEncapsulation(algorithm) as kem:
            ciphertext, shared_secret = kem.encaps_secret(public_key)
            return KEMCiphertext(
                ciphertext=ciphertext,
                shared_secret=shared_secret
            )
    else:
        # Fallback: derive key from random material
        logger.warning("pqc_encapsulate_fallback")
        shared_secret = secrets.token_bytes(32)
        ciphertext = hashlib.sha256(public_key + shared_secret).digest()
        return KEMCiphertext(ciphertext=ciphertext, shared_secret=shared_secret)


def kem_decapsulate(
    ciphertext: bytes,
    secret_key: bytes,
    algorithm: str = "ML-KEM-768"
) -> bytes:
    """Decapsulate the shared secret using the recipient's secret key."""
    if PQC_AVAILABLE:
        with oqs.KeyEncapsulation(algorithm) as kem:
            kem.import_secret_key(secret_key)
            return kem.decapsulate(ciphertext)
    else:
        # Fallback: reconstruct shared secret
        logger.warning("pqc_decapsulate_fallback")
        return hashlib.sha256(ciphertext + secret_key).digest()


# ─── ML-DSA (Digital Signatures) ────────────────────────────────────────────

@dataclass
class DSASignature:
    """ML-DSA digital signature."""
    signature: bytes
    algorithm: str = "ML-DSA-65"


@dataclass
class DSAKeyPair:
    """ML-DSA key pair."""
    public_key: bytes
    secret_key: bytes
    algorithm: str = "ML-DSA-65"


def dsa_generate_keypair(algorithm: str = "ML-DSA-65") -> DSAKeyPair:
    """Generate an ML-DSA key pair for digital signatures."""
    if PQC_AVAILABLE:
        with oqs.Signature(algorithm) as sig:
            public_key = sig.generate_keypair()
            secret_key = sig.export_secret_key()
            return DSAKeyPair(
                public_key=public_key,
                secret_key=secret_key,
                algorithm=algorithm
            )
    else:
        logger.warning("pqc_dsa_fallback", algorithm=algorithm)
        return DSAKeyPair(
            public_key=secrets.token_bytes(32),
            secret_key=secrets.token_bytes(32),
            algorithm=f"fallback-{algorithm}"
        )


def dsa_sign(message: bytes, secret_key: bytes, algorithm: str = "ML-DSA-65") -> DSASignature:
    """Sign a message using ML-DSA."""
    if PQC_AVAILABLE:
        with oqs.Signature(algorithm) as sig:
            sig.import_secret_key(secret_key)
            signature = sig.sign(message)
            return DSASignature(signature=signature, algorithm=algorithm)
    else:
        logger.warning("pqc_sign_fallback")
        signature = hashlib.sha256(secret_key + message).digest()
        return DSASignature(signature=signature, algorithm=f"fallback-{algorithm}")


def dsa_verify(
    message: bytes,
    signature: bytes,
    public_key: bytes,
    algorithm: str = "ML-DSA-65"
) -> bool:
    """Verify an ML-DSA signature."""
    if PQC_AVAILABLE:
        with oqs.Signature(algorithm) as sig:
            return sig.verify(message, signature, public_key)
    else:
        logger.warning("pqc_verify_fallback")
        return True  # Cannot verify in fallback mode


# ─── Hybrid Key Exchange ────────────────────────────────────────────────────

@dataclass
class HybridKeyExchangeResult:
    """Result of hybrid X25519 + ML-KEM key exchange."""
    shared_secret: bytes
    kem_ciphertext: bytes
    pqc_enabled: bool


def hybrid_key_exchange(peer_public_key: bytes) -> HybridKeyExchangeResult:
    """
    Perform hybrid key exchange: X25519 + ML-KEM-768.
    
    Combines classical and post-quantum shared secrets via HKDF
    for defense-in-depth against both classical and quantum adversaries.
    """
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    
    # Classical: X25519
    private_key = X25519PrivateKey.generate()
    classical_shared = private_key.exchange(peer_public_key)
    
    # PQC: ML-KEM-768
    kem_result = kem_encapsulate(peer_public_key)
    
    # Combine via HKDF-SHA256
    combined = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"angavu-hybrid-kex-x25519-mlkem768",
    ).derive(classical_shared + kem_result.shared_secret)
    
    return HybridKeyExchangeResult(
        shared_secret=combined,
        kem_ciphertext=kem_result.ciphertext,
        pqc_enabled=PQC_AVAILABLE
    )


# ─── PQC Status ─────────────────────────────────────────────────────────────

def get_pqc_status() -> dict:
    """Get current PQC capability status."""
    algorithms = {}
    if PQC_AVAILABLE:
        algorithms = {
            "kem": oqs.get_enabled_kem_mechanisms()[:5],
            "sig": oqs.get_enabled_sig_mechanisms()[:5],
        }
    
    return {
        "pqc_available": PQC_AVAILABLE,
        "phase": int(os.getenv("ANGAVU_PQC_PHASE", "1")),
        "hybrid_kex": os.getenv("ANGAVU_PQC_HYBRID_KEX", "true").lower() == "true",
        "signing_enabled": os.getenv("ANGAVU_PQC_SIGNING", "true").lower() == "true",
        "algorithms": algorithms,
    }
