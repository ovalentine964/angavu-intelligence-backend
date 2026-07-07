"""
Algorithm registry for crypto-agility.

Allows runtime selection and swapping of cryptographic algorithms without
changing application code. Critical for PQC migration.
"""

import logging
from typing import Dict, Optional

from .crypto_provider import CryptoProvider, KeyEncapsulationProvider

logger = logging.getLogger(__name__)


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
        from .ml_dsa import MlDsaProvider, MlDsaParameterSet
        # AES-256-GCM is quantum-safe (symmetric), register as placeholder
        # ECDSA is NOT quantum-safe but retained for backward compatibility

    def _register_pqc(self):
        from .ml_kem import MlKemProvider, MlKemParameterSet
        from .ml_dsa import MlDsaProvider, MlDsaParameterSet

        # ML-KEM variants
        for param in MlKemParameterSet:
            self.register_kem_provider(MlKemProvider(param))

        # ML-DSA variants
        for param in MlDsaParameterSet:
            self.register_signature_provider(MlDsaProvider(param))
