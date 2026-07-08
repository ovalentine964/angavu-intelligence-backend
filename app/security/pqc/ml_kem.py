"""
ML-KEM (Module-Lattice-Based Key Encapsulation Mechanism) provider.

Implements NIST FIPS 203 (formerly CRYSTALS-Kyber).
ML-KEM provides IND-CCA2 secure key encapsulation resistant to quantum attacks.

╔══════════════════════════════════════════════════════════════╗
║  ⚠️  STUB IMPLEMENTATION — NOT REAL CRYPTOGRAPHY  ⚠️        ║
╠══════════════════════════════════════════════════════════════╣
║  This implementation uses os.urandom() for keys and         ║
║  hashlib for derivation. It provides ZERO quantum-resistant  ║
║  security. DO NOT use for production encryption.             ║
║                                                              ║
║  Production: install liboqs-python or pqcrypto              ║
║  Fallback: use AES-256-GCM (real encryption)                ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    provider = MlKemProvider(MlKemParameterSet.ML_KEM_768)
    if provider.is_stub:
        # Fall back to AES-256-GCM — real encryption
        use_aes_gcm_instead()
    else:
        key_pair = provider.generate_key_pair()
        encap = provider.encapsulate(key_pair.public_key)
        shared = provider.decapsulate(encap.ciphertext, key_pair.private_key)

See: https://csrc.nist.gov/pubs/fips/203/final
"""

import hashlib
import os
from dataclasses import dataclass
from enum import Enum

from .crypto_provider import CryptoKeyPair, EncapsulatedKey, KeyEncapsulationProvider


class MlKemParameterSet(Enum):
    """ML-KEM parameter sets per NIST FIPS 203."""
    ML_KEM_512 = (1, 800, 768)     # NIST Level 1, pub_key_size, ciphertext_size
    ML_KEM_768 = (3, 1184, 1088)   # NIST Level 3 — recommended
    ML_KEM_1024 = (5, 1568, 1568)  # NIST Level 5

    def __init__(self, security_level: int, pub_key_size: int, ct_size: int):
        self.security_level = security_level
        self.pub_key_size = pub_key_size
        self.ct_size = ct_size


SHARED_SECRET_SIZE = 32


class MlKemProvider(KeyEncapsulationProvider):
    """
    ML-KEM key encapsulation provider.

    ╔══════════════════════════════════════════════════════════════╗
    ║  ⚠️  STUB IMPLEMENTATION — NOT REAL CRYPTOGRAPHY  ⚠️        ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  This implementation uses os.urandom() for keys and         ║
    ║  hashlib for derivation. It provides ZERO quantum-resistant  ║
    ║  security. DO NOT use for production encryption.             ║
    ║                                                              ║
    ║  Production: install liboqs-python or pqcrypto              ║
    ║  Fallback: use AES-256-GCM (real encryption)                ║
    ╚══════════════════════════════════════════════════════════════╝

    Replace with native ML-KEM when liboqs-python or pqcrypto is available:

        pip install liboqs-python
        # or
        pip install pqcrypto

    The interface is production-ready; only the implementation needs swapping.
    """

    is_stub: bool = True  # Callers MUST check this before use

    def __init__(self, parameter_set: MlKemParameterSet = MlKemParameterSet.ML_KEM_768):
        self._param_set = parameter_set

    @property
    def algorithm_id(self) -> str:
        return self._param_set.name

    @property
    def is_post_quantum(self) -> bool:
        return True

    @property
    def security_level(self) -> int:
        return self._param_set.security_level

    def get_real_provider(self):
        """STUB: No real provider available. Callers must fall back to AES-256-GCM."""
        return None

    def generate_key_pair(self) -> CryptoKeyPair:
        """Generate an ML-KEM key pair (STUB — NOT REAL CRYPTOGRAPHY)."""
        # Store a deterministic seed in the private key so decapsulation can
        # recover the shared secret derived during encapsulation.
        seed = os.urandom(32)
        public_key = os.urandom(self._param_set.pub_key_size)
        private_key = seed + os.urandom(self._param_set.pub_key_size * 2 - 32)
        return CryptoKeyPair(
            public_key=public_key,
            private_key=private_key,
            algorithm_id=self.algorithm_id,
        )

    def encapsulate(self, public_key: bytes) -> EncapsulatedKey:
        """Encapsulate a shared secret for a public key (STUB — NOT REAL CRYPTOGRAPHY)."""
        if len(public_key) != self._param_set.pub_key_size:
            raise ValueError(
                f"Invalid public key size for {self._param_set.name}: "
                f"{len(public_key)}, expected {self._param_set.pub_key_size}"
            )
        # Embed a deterministic seed in the ciphertext prefix so that
        # decapsulate() can recover the same shared secret.
        seed = os.urandom(32)
        ciphertext = seed + os.urandom(self._param_set.ct_size - 32)
        shared_secret = self._derive_shared_secret(seed, ciphertext)
        return EncapsulatedKey(
            ciphertext=ciphertext,
            shared_secret=shared_secret,
            algorithm_id=self.algorithm_id,
        )

    def decapsulate(self, ciphertext: bytes, private_key: bytes) -> bytes:
        """Decapsulate to recover the shared secret (STUB — NOT REAL CRYPTOGRAPHY)."""
        if len(ciphertext) != self._param_set.ct_size:
            raise ValueError(
                f"Invalid ciphertext size for {self._param_set.name}: "
                f"{len(ciphertext)}, expected {self._param_set.ct_size}"
            )
        # Extract the seed from the ciphertext prefix (first 32 bytes)
        # and derive the same shared secret as encapsulate().
        seed = ciphertext[:32]
        return self._derive_shared_secret(seed, ciphertext)

    def _derive_shared_secret(self, seed: bytes, ciphertext: bytes) -> bytes:
        """Deterministic shared secret derivation (same in encapsulate & decapsulate)."""
        return hashlib.sha256(seed + ciphertext).digest()[:SHARED_SECRET_SIZE]
