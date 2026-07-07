"""
Post-Quantum Cryptography module for Angavu Intelligence Backend.

Provides crypto-agility and PQC readiness for server-side operations:
- ML-KEM (Kyber) key encapsulation for secure session establishment
- ML-DSA (Dilithium) document signing for transaction receipts
- Hybrid key exchange combining classical + PQC
- Crypto audit logging for compliance
- Algorithm registry for runtime algorithm swapping

Per White House EO 14412 (June 2026) and NIST FIPS 203/204.
"""

from .crypto_provider import CryptoProvider, CryptoKeyPair, EncapsulatedKey
from .ml_kem import MlKemProvider, MlKemParameterSet
from .ml_dsa import MlDsaProvider, MlDsaParameterSet
from .hybrid_key_exchange import HybridKeyExchange
from .algorithm_registry import AlgorithmRegistry
from .audit import CryptoAuditLogger, AuditEventType, AuditSeverity
from .config import PqcConfig

__all__ = [
    "CryptoProvider",
    "CryptoKeyPair",
    "EncapsulatedKey",
    "MlKemProvider",
    "MlKemParameterSet",
    "MlDsaProvider",
    "MlDsaParameterSet",
    "HybridKeyExchange",
    "AlgorithmRegistry",
    "CryptoAuditLogger",
    "AuditEventType",
    "AuditSeverity",
    "PqcConfig",
]
