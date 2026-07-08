"""
Algorithm registry for crypto-agility.

Allows runtime selection and swapping of cryptographic algorithms without
changing application code. Critical for PQC migration.
"""

import hashlib
import logging
import os
from typing import Dict, Optional

from .crypto_provider import CryptoProvider, CryptoKeyPair, KeyEncapsulationProvider

logger = logging.getLogger(__name__)


class _Aes256GcmProvider(CryptoProvider):
    """AES-256-GCM symmetric encryption provider (quantum-safe)."""

    is_stub: bool = True  # Placeholder — real AES-GCM requires cryptography lib

    @property
    def algorithm_id(self) -> str:
        return "AES-256-GCM"

    @property
    def is_post_quantum(self) -> bool:
        return True  # 256-bit symmetric → 128-bit post-quantum security

    @property
    def security_level(self) -> int:
        return 5

    def get_real_provider(self):
        return None

    def generate_key_pair(self) -> CryptoKeyPair:
        return CryptoKeyPair(
            public_key=os.urandom(32),
            private_key=os.urandom(32),
            algorithm_id=self.algorithm_id,
        )

    def encrypt(self, plaintext: bytes, key: bytes) -> bytes:
        # STUB: XOR with key-derived stream. Real impl uses AES-256-GCM.
        stream = hashlib.sha256(key).digest() * (len(plaintext) // 32 + 1)
        return bytes(a ^ b for a, b in zip(plaintext, stream[:len(plaintext)]))

    def decrypt(self, ciphertext: bytes, key: bytes) -> bytes:
        # STUB: XOR is its own inverse.
        stream = hashlib.sha256(key).digest() * (len(ciphertext) // 32 + 1)
        return bytes(a ^ b for a, b in zip(ciphertext, stream[:len(ciphertext)]))

    def sign(self, data: bytes, private_key: bytes) -> bytes:
        raise NotImplementedError("AES-256-GCM is an encryption algorithm, not a signature algorithm")

    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        raise NotImplementedError("AES-256-GCM is an encryption algorithm, not a signature algorithm")


class _EcdsaP256Provider(CryptoProvider):
    """ECDSA-P256 signature provider (NOT quantum-safe, backward compat)."""

    is_stub: bool = True

    @property
    def algorithm_id(self) -> str:
        return "ECDSA-P256"

    @property
    def is_post_quantum(self) -> bool:
        return False  # Broken by Shor's algorithm

    @property
    def security_level(self) -> int:
        return 1

    def get_real_provider(self):
        return None

    def generate_key_pair(self) -> CryptoKeyPair:
        return CryptoKeyPair(
            public_key=os.urandom(64),
            private_key=os.urandom(32),
            algorithm_id=self.algorithm_id,
        )

    def sign(self, data: bytes, private_key: bytes) -> bytes:
        h = hashlib.sha256(private_key + data).digest()
        return h + os.urandom(32)

    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        if len(signature) < 32:
            return False
        # STUB: re-derive from public_key + data (not real ECDSA)
        expected = hashlib.sha256(public_key[:32] + data).digest()[:16]
        return signature[:16] == expected

    def encrypt(self, plaintext: bytes, key: bytes) -> bytes:
        raise NotImplementedError("ECDSA is a signature algorithm, not encryption")

    def decrypt(self, ciphertext: bytes, key: bytes) -> bytes:
        raise NotImplementedError("ECDSA is a signature algorithm, not encryption")


class AlgorithmRegistry:
    """
    Registry for cryptographic algorithm providers.

    Usage:
        registry = AlgorithmRegistry()
        provider = registry.get_encrypt_provider()  # Default
        provider = registry.get_encrypt_provider("ML-KEM-768")  # Specific
        registry.set_default_encrypt_algorithm("ML-KEM-768")  # Switch
    """

    def __init__(self):
        self._encrypt_providers: Dict[str, CryptoProvider] = {}
        self._signature_providers: Dict[str, CryptoProvider] = {}
        self._kem_providers: Dict[str, KeyEncapsulationProvider] = {}

        self._default_encrypt = "AES-256-GCM"
        self._default_signature = "ML-DSA-65"
        self._default_kem = "ML-KEM-768"

        self._register_classical()
        self._register_pqc()

        logger.info(
            "AlgorithmRegistry initialized: %d encrypt, %d sign, %d KEM providers",
            len(self._encrypt_providers),
            len(self._signature_providers),
            len(self._kem_providers),
        )

    def register_encrypt_provider(self, provider: CryptoProvider):
        self._encrypt_providers[provider.algorithm_id] = provider
        logger.debug("Registered encrypt provider: %s (PQ=%s)", provider.algorithm_id, provider.is_post_quantum)

    def register_signature_provider(self, provider: CryptoProvider):
        self._signature_providers[provider.algorithm_id] = provider
        logger.debug("Registered signature provider: %s (PQ=%s)", provider.algorithm_id, provider.is_post_quantum)

    def register_kem_provider(self, provider: KeyEncapsulationProvider):
        self._kem_providers[provider.algorithm_id] = provider
        logger.debug("Registered KEM provider: %s (PQ=%s)", provider.algorithm_id, provider.is_post_quantum)

    def get_encrypt_provider(self, algorithm_id: Optional[str] = None) -> CryptoProvider:
        aid = algorithm_id or self._default_encrypt
        if aid not in self._encrypt_providers:
            raise ValueError(f"Unknown encrypt algorithm: {aid}. Available: {list(self._encrypt_providers.keys())}")
        return self._encrypt_providers[aid]

    def get_signature_provider(self, algorithm_id: Optional[str] = None) -> CryptoProvider:
        aid = algorithm_id or self._default_signature
        if aid not in self._signature_providers:
            raise ValueError(f"Unknown signature algorithm: {aid}. Available: {list(self._signature_providers.keys())}")
        return self._signature_providers[aid]

    def get_kem_provider(self, algorithm_id: Optional[str] = None) -> KeyEncapsulationProvider:
        aid = algorithm_id or self._default_kem
        if aid not in self._kem_providers:
            raise ValueError(f"Unknown KEM algorithm: {aid}. Available: {list(self._kem_providers.keys())}")
        return self._kem_providers[aid]

    def set_default_encrypt_algorithm(self, algorithm_id: str):
        if algorithm_id not in self._encrypt_providers:
            raise ValueError(f"Cannot set default to unregistered algorithm: {algorithm_id}")
        self._default_encrypt = algorithm_id
        logger.info("Default encrypt algorithm changed to: %s", algorithm_id)

    def set_default_signature_algorithm(self, algorithm_id: str):
        if algorithm_id not in self._signature_providers:
            raise ValueError(f"Cannot set default to unregistered algorithm: {algorithm_id}")
        self._default_signature = algorithm_id
        logger.info("Default signature algorithm changed to: %s", algorithm_id)

    def set_default_kem_algorithm(self, algorithm_id: str):
        if algorithm_id not in self._kem_providers:
            raise ValueError(f"Cannot set default to unregistered algorithm: {algorithm_id}")
        self._default_kem = algorithm_id
        logger.info("Default KEM algorithm changed to: %s", algorithm_id)

    def list_algorithms(self) -> dict:
        return {
            "encrypt": list(self._encrypt_providers.keys()),
            "signature": list(self._signature_providers.keys()),
            "kem": list(self._kem_providers.keys()),
        }

    def list_pq_algorithms(self) -> dict:
        return {
            "encrypt": [k for k, v in self._encrypt_providers.items() if v.is_post_quantum],
            "signature": [k for k, v in self._signature_providers.items() if v.is_post_quantum],
            "kem": [k for k, v in self._kem_providers.items() if v.is_post_quantum],
        }

    def _register_classical(self):
        # AES-256-GCM: quantum-safe symmetric encryption (256-bit key → 128-bit PQ security)
        aes_provider = _Aes256GcmProvider()
        self.register_encrypt_provider(aes_provider)

        # ECDSA-P256: NOT quantum-safe but retained for backward compatibility
        ecdsa_provider = _EcdsaP256Provider()
        self.register_signature_provider(ecdsa_provider)

    def _register_pqc(self):
        from .ml_kem import MlKemProvider, MlKemParameterSet
        from .ml_dsa import MlDsaProvider, MlDsaParameterSet

        # ML-KEM variants
        for param in MlKemParameterSet:
            self.register_kem_provider(MlKemProvider(param))

        # ML-DSA variants
        for param in MlDsaParameterSet:
            self.register_signature_provider(MlDsaProvider(param))
