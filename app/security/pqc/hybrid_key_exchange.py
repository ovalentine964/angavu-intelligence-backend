"""
Hybrid key exchange combining classical (X25519/ECDHE) with post-quantum (ML-KEM).

Follows the approach used by Cloudflare, Google Chrome, and Meta:
    shared_secret = HKDF(ECDHE_secret || ML-KEM_secret)

If ML-KEM is broken, classical ECDHE still protects the connection.
If classical ECDHE is broken by quantum computers, ML-KEM still protects it.

╔══════════════════════════════════════════════════════════════╗
║  ⚠️  STUB IMPLEMENTATION — NOT REAL CRYPTOGRAPHY  ⚠️        ║
╠══════════════════════════════════════════════════════════════╣
║  Both X25519 and ML-KEM components are stubs. The HKDF      ║
║  combination logic is correct but inputs are random bytes.   ║
║  This provides ZERO cryptographic security.                   ║
║                                                              ║
║  For production: use AES-256-GCM with proper key derivation. ║
║  PQC hybrid exchange will be enabled when liboqs is ready.   ║
╚══════════════════════════════════════════════════════════════╝
"""

import hashlib
import hmac
import os

from .crypto_provider import CryptoKeyPair
from .ml_kem import MlKemProvider, MlKemParameterSet


HKDF_ALGORITHM = "sha256"
HYBRID_ALGORITHM_ID = "X25519+ML-KEM-768"
HYBRID_SHARED_SECRET_SIZE = 32


class HybridKeyExchangeResult:
    """Result of a hybrid key exchange initiation."""

    def __init__(
        self,
        ecdh_public_key: bytes,
        ml_kem_ciphertext: bytes,
        shared_secret: bytes,
        algorithm_id: str = HYBRID_ALGORITHM_ID,
    ):
        self.ecdh_public_key = ecdh_public_key
        self.ml_kem_ciphertext = ml_kem_ciphertext
        self.shared_secret = shared_secret
        self.algorithm_id = algorithm_id


class HybridKeyExchange:
    """
    Hybrid key exchange combining classical ECDHE with ML-KEM.

    ⚠️  STUB IMPLEMENTATION — NOT REAL CRYPTOGRAPHY.

    Both X25519 and ML-KEM components are stubs.
    For production, use AES-256-GCM with proper key derivation.
    PQC hybrid exchange will be enabled when liboqs is available.

    Usage (client side):
        kex = HybridKeyExchange()
        if kex.is_stub:
            # Fall back to TLS 1.3 with AES-256-GCM
            use_tls_instead()
        else:
            result = kex.initiate(peer_ml_kem_public_key)
            # Use result.shared_secret for AES-256-GCM encryption

    Usage (server side):
        kex = HybridKeyExchange()
        shared_secret = kex.complete(peer_ecdh_pub, ml_kem_ct, ml_kem_priv)
    """

    is_stub: bool = True  # Callers MUST check this before use

    def __init__(self, ml_kem_provider: MlKemProvider | None = None):
        self._ml_kem = ml_kem_provider or MlKemProvider(MlKemParameterSet.ML_KEM_768)

    def get_real_provider(self):
        """STUB: No real provider available. Fall back to TLS 1.3 + AES-256-GCM."""
        return None

    def initiate(self, peer_ml_kem_public_key: bytes) -> HybridKeyExchangeResult:
        """
        Initiate a hybrid key exchange (client side).

        ⚠️  STUB — both ECDHE and ML-KEM components are simulated.
        """
        # Step 1: Generate ECDHE ephemeral key pair (X25519 stub)
        ecdh_key_pair = self._generate_x25519_key_pair()

        # Step 2: ML-KEM encapsulation (STUB)
        ml_kem_result = self._ml_kem.encapsulate(peer_ml_kem_public_key)

        # Step 3: Derive ECDH shared secret (STUB)
        ecdh_secret = self._derive_ecdh_secret(ecdh_key_pair.private_key, peer_ml_kem_public_key)

        # Step 4: Combine using HKDF (correct algorithm, stub inputs)
        combined_secret = self._combine_secrets(ecdh_secret, ml_kem_result.shared_secret)

        return HybridKeyExchangeResult(
            ecdh_public_key=ecdh_key_pair.public_key,
            ml_kem_ciphertext=ml_kem_result.ciphertext,
            shared_secret=combined_secret,
        )

    def complete(
        self,
        peer_ecdh_public_key: bytes,
        ml_kem_ciphertext: bytes,
        ml_kem_private_key: bytes,
    ) -> bytes:
        """
        Complete a hybrid key exchange (server side).

        ⚠️  STUB — both ECDHE and ML-KEM components are simulated.
        """
        # Step 1: ECDH shared secret (STUB)
        ecdh_secret = self._derive_ecdh_secret(ml_kem_private_key, peer_ecdh_public_key)

        # Step 2: ML-KEM decapsulation (STUB)
        ml_kem_secret = self._ml_kem.decapsulate(ml_kem_ciphertext, ml_kem_private_key)

        # Step 3: Combine using HKDF
        return self._combine_secrets(ecdh_secret, ml_kem_secret)

    def _combine_secrets(self, ecdh_secret: bytes, ml_kem_secret: bytes) -> bytes:
        """Combine ECDHE and ML-KEM shared secrets using HKDF."""
        ikm = ecdh_secret + ml_kem_secret
        salt = HYBRID_ALGORITHM_ID.encode("utf-8")
        info = HYBRID_ALGORITHM_ID.encode("utf-8")

        # HKDF-Extract: PRK = HMAC-Hash(salt, IKM)
        prk = hmac.new(salt, ikm, hashlib.sha256).digest()

        # HKDF-Expand: OKM = HMAC-Hash(PRK, info || 0x01)
        okm = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()

        return okm[:HYBRID_SHARED_SECRET_SIZE]

    def _generate_x25519_key_pair(self) -> CryptoKeyPair:
        """Generate X25519 ephemeral key pair (STUB — uses random bytes)."""
        return CryptoKeyPair(
            public_key=os.urandom(32),
            private_key=os.urandom(32),
            algorithm_id="X25519",
        )

    def _derive_ecdh_secret(self, private_key: bytes, peer_public_key: bytes) -> bytes:
        """Derive ECDH shared secret (STUB)."""
        return hashlib.sha256(private_key + peer_public_key).digest()
