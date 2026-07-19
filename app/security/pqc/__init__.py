"""
Post-Quantum Cryptography module for Angavu Intelligence Backend.

Provides crypto-agility and PQC readiness for server-side operations:
- ML-KEM (Kyber) key encapsulation for secure session establishment
- ML-DSA (Dilithium) document signing for transaction receipts
- Hybrid key exchange combining classical + PQC
- PQC TLS configuration for secure connections
- PQC-encrypted federated learning gradient transport
- Crypto audit logging for compliance
- Algorithm registry for runtime algorithm swapping

All implementations use real cryptographic primitives:
- ML-KEM/ML-DSA via liboqs-python (Open Quantum Safe)
- AES-256-GCM via cryptography library
- X25519 via cryptography library

Per White House EO 14412 (June 2026) and NIST FIPS 203/204.
"""

from .algorithm_registry import AlgorithmRegistry
from .audit import AuditEventType, AuditSeverity, CryptoAuditLogger
from .config import PqcConfig
from .crypto_provider import CryptoKeyPair, CryptoProvider, EncapsulatedKey
from .fl_encryption import (
    EncryptedGradientPayload,
    FlPqcDecryptor,
    FlPqcEncryptor,
)
from .hybrid_key_exchange import HybridKeyExchange
from .ml_dsa import MlDsaParameterSet, MlDsaProvider
from .ml_kem import MlKemParameterSet, MlKemProvider
from .tls_config import (
    PqcCertificate,
    PqcCertificatePinner,
    TlsMode,
    TlsPqcConfig,
    create_pqc_ssl_context,
    create_server_ssl_context,
    generate_pqc_signed_certificate,
)

__all__ = [
    "AlgorithmRegistry",
    "AuditEventType",
    "AuditSeverity",
    "CryptoAuditLogger",
    "CryptoKeyPair",
    "CryptoProvider",
    "EncapsulatedKey",
    "EncryptedGradientPayload",
    "FlPqcDecryptor",
    "FlPqcEncryptor",
    "HybridKeyExchange",
    "MlDsaParameterSet",
    "MlDsaProvider",
    "MlKemParameterSet",
    "MlKemProvider",
    "PqcCertificate",
    "PqcCertificatePinner",
    "PqcConfig",
    "TlsMode",
    "TlsPqcConfig",
    "create_pqc_ssl_context",
    "create_server_ssl_context",
    "generate_pqc_signed_certificate",
]
