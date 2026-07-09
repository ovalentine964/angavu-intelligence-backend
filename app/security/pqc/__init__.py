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

from .crypto_provider import CryptoProvider, CryptoKeyPair, EncapsulatedKey
from .ml_kem import MlKemProvider, MlKemParameterSet
from .ml_dsa import MlDsaProvider, MlDsaParameterSet
from .hybrid_key_exchange import HybridKeyExchange
from .algorithm_registry import AlgorithmRegistry
from .audit import CryptoAuditLogger, AuditEventType, AuditSeverity
from .config import PqcConfig
from .tls_config import (
    TlsMode,
    TlsPqcConfig,
    PqcCertificate,
    PqcCertificatePinner,
    create_pqc_ssl_context,
    create_server_ssl_context,
    generate_pqc_signed_certificate,
)
from .fl_encryption import (
    FlPqcEncryptor,
    FlPqcDecryptor,
    EncryptedGradientPayload,
)

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
    "TlsMode",
    "TlsPqcConfig",
    "PqcCertificate",
    "PqcCertificatePinner",
    "create_pqc_ssl_context",
    "create_server_ssl_context",
    "generate_pqc_signed_certificate",
    "FlPqcEncryptor",
    "FlPqcDecryptor",
    "EncryptedGradientPayload",
]
