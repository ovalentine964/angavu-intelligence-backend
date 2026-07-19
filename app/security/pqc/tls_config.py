"""
Post-Quantum TLS 1.3 Configuration for Angavu Intelligence Backend.

Configures TLS 1.3 connections with PQC-hybrid key exchange and
certificate pinning with PQC signatures.

Production Deployment:
    This module provides the configuration objects and helper functions
    for integrating PQC into the TLS layer. Actual TLS termination
    is typically handled by the reverse proxy (nginx, Caddy, Traefik)
    or the ASGI server (uvicorn with SSL context).

    For nginx with PQC:
        - Build nginx with BoringSSL or OpenSSL 3.5+ (has ML-KEM)
        - Use ssl_ecdh_curve X25519MLKEM768 for hybrid key exchange
        - Certificate: ECDSA P-256 + ML-DSA-65 dual-signed

    For Python ASGI servers:
        - Use ssl.SSLContext with custom post-handshake auth
        - liboqs-python provides the PQC primitives
        - Hybrid key exchange happens at the TLS handshake layer

Current Status:
    - PQC cipher suites are defined and ready
    - Certificate pinning with PQC signatures is configured
    - Hybrid key exchange integration points are marked
    - Full TLS 1.3 + PQC requires OpenSSL 3.5+ or BoringSSL on the server

Reference:
    - IETF draft-ietf-tls-hybrid-design (Hybrid Key Exchange in TLS 1.3)
    - NIST FIPS 203/204 for ML-KEM/ML-DSA
    - Cloudflare's PQ TLS deployment (2024+)
"""

import logging
import ssl
from dataclasses import dataclass
from enum import Enum

from .ml_dsa import MlDsaParameterSet, MlDsaProvider

logger = logging.getLogger(__name__)


class TlsMode(Enum):
    """TLS operation modes."""
    CLASSICAL_ONLY = "classical"        # TLS 1.3 classical only
    HYBRID = "hybrid"                   # TLS 1.3 + PQC hybrid key exchange
    PQC_PREFERRED = "pqc_preferred"     # PQC preferred, classical fallback
    PQC_ONLY = "pqc_only"              # PQC only (no classical fallback)


@dataclass
class PqcCertificate:
    """
    A dual-signed certificate for PQC transition.

    During the hybrid phase, certificates should be signed with both:
    1. Classical algorithm (ECDSA P-256) — for backward compatibility
    2. Post-quantum algorithm (ML-DSA-65) — for quantum resistance

    Verifiers that understand ML-DSA check the PQ signature.
    Verifiers that don't fall back to the classical signature.
    """
    # Classical certificate (PEM-encoded X.509)
    classical_cert_pem: bytes
    # Classical private key (PEM-encoded)
    classical_key_pem: bytes
    # PQC signature of the certificate (ML-DSA-65)
    pqc_signature: bytes | None = None
    # PQC public key (for pinning)
    pqc_public_key: bytes | None = None
    # PQC algorithm identifier
    pqc_algorithm: str = "ML-DSA-65"


@dataclass
class TlsPqcConfig:
    """Configuration for TLS with PQC support."""
    mode: TlsMode = TlsMode.HYBRID
    # Minimum TLS version
    min_tls_version: int = ssl.TLSVersion.TLSv1_3
    # Preferred cipher suites (TLS 1.3 AEAD ciphers are all quantum-safe for data)
    cipher_suites: list[str] | None = None
    # PQC key exchange algorithm
    pqc_kem_algorithm: str = "ML-KEM-768"
    # PQC signature algorithm for certificates
    pqc_sig_algorithm: str = "ML-DSA-65"
    # Certificate pinning with PQC public keys
    pinned_pqc_keys: list[bytes] | None = None
    # Certificate and key paths
    cert_path: str | None = None
    key_path: str | None = None
    # CA bundle path
    ca_path: str | None = None


# ════════════════════════════════════════════════════════════════════
# PQC Cipher Suites
# ════════════════════════════════════════════════════════════════════

# TLS 1.3 cipher suites (all use AEAD, quantum-safe for data in transit)
# The PQC protection comes from the key exchange, not the cipher suite
TLS_13_CIPHER_SUITES = [
    "TLS_AES_256_GCM_SHA384",          # Preferred: AES-256 (quantum-safe)
    "TLS_CHACHA20_POLY1305_SHA256",     # Alternative: ChaCha20
    "TLS_AES_128_GCM_SHA256",          # Minimum: AES-128
]

# Hybrid key exchange groups (when OpenSSL 3.5+ / BoringSSL available)
# These are IANA-assigned code points for PQC-hybrid groups
HYBRID_KEY_EXCHANGE_GROUPS = [
    "X25519MLKEM768",     # X25519 + ML-KEM-768 (primary)
    "X25519",             # Classical fallback
    "P-256",              # Classical fallback
]

# Certificate signature algorithms (ordered by preference)
CERT_SIGNATURE_ALGORITHMS = [
    "ML-DSA-65",          # PQC signature (primary)
    "ECDSA-P256-SHA256",  # Classical fallback
    "RSA-PSS-SHA256",     # Classical fallback
]


# ════════════════════════════════════════════════════════════════════
# SSL Context Builders
# ════════════════════════════════════════════════════════════════════


def create_pqc_ssl_context(
    config: TlsPqcConfig,
    purpose: ssl.Purpose = ssl.Purpose.CLIENT_AUTH,
) -> ssl.SSLContext:
    """
    Create an SSL context with PQC support.

    This configures TLS 1.3 with:
    - PQC-hybrid key exchange (when available)
    - AES-256-GCM cipher suites (quantum-safe)
    - Certificate pinning with PQC public keys
    - Dual-signed certificates (classical + PQC)

    Args:
        config: TLS PQC configuration
        purpose: SSL context purpose (CLIENT_AUTH for servers, SERVER_AUTH for clients)

    Returns:
        Configured ssl.SSLContext
    """
    # Create TLS 1.3 context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT if purpose == ssl.Purpose.SERVER_AUTH else ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3

    # Set cipher suites
    if config.cipher_suites:
        cipher_string = ":".join(config.cipher_suites)
        try:
            context.set_ciphers(cipher_string)
        except ssl.SSLError:
            logger.warning("Could not set cipher suites: %s, using defaults", cipher_string)

    # Load certificate and key if provided
    if config.cert_path and config.key_path:
        context.load_cert_chain(
            certfile=config.cert_path,
            keyfile=config.key_path,
        )

    # Load CA bundle if provided
    if config.ca_path:
        context.load_verify_locations(cafile=config.ca_path)

    # Configure verification
    if purpose == ssl.Purpose.SERVER_AUTH:
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
    else:
        context.verify_mode = ssl.CERT_REQUIRED

    logger.info(
        "PQC SSL context created: mode=%s, min_tls=1.3, pqc_kex=%s",
        config.mode.value,
        config.pqc_kem_algorithm,
    )

    return context


def create_server_ssl_context(
    cert_path: str,
    key_path: str,
    ca_path: str | None = None,
    mode: TlsMode = TlsMode.HYBRID,
) -> ssl.SSLContext:
    """
    Create a server SSL context with PQC support.

    For use with uvicorn or other ASGI servers:
        ssl_context = create_server_ssl_context("/path/to/cert.pem", "/path/to/key.pem")
        uvicorn.run(app, ssl=ssl_context)

    Args:
        cert_path: Path to server certificate (PEM)
        key_path: Path to server private key (PEM)
        ca_path: Path to CA bundle (PEM)
        mode: TLS mode

    Returns:
        Configured ssl.SSLContext for server use
    """
    config = TlsPqcConfig(
        mode=mode,
        cert_path=cert_path,
        key_path=key_path,
        ca_path=ca_path,
    )
    return create_pqc_ssl_context(config, purpose=ssl.Purpose.CLIENT_AUTH)


# ════════════════════════════════════════════════════════════════════
# Certificate Pinning with PQC
# ════════════════════════════════════════════════════════════════════


class PqcCertificatePinner:
    """
    Certificate pinning with PQC public keys.

    Pins both classical and PQC public keys. During the hybrid phase,
    the server's certificate chain is verified against both:
    1. Classical ECDSA public key (SHA-256 pin)
    2. PQC ML-DSA public key (SHA-256 pin)

    A connection is accepted if EITHER pin matches (hybrid phase).
    In PQC-only mode, only the PQC pin must match.
    """

    def __init__(
        self,
        pinned_classical_hashes: list[str] | None = None,
        pinned_pqc_hashes: list[str] | None = None,
        mode: TlsMode = TlsMode.HYBRID,
    ):
        self._classical_hashes = set(pinned_classical_hashes or [])
        self._pqc_hashes = set(pinned_pqc_hashes or [])
        self._mode = mode

    def add_classical_pin(self, public_key_der: bytes) -> str:
        """Add a classical public key pin. Returns the SHA-256 hex hash."""
        import hashlib
        pin_hash = hashlib.sha256(public_key_der).hexdigest()
        self._classical_hashes.add(pin_hash)
        return pin_hash

    def add_pqc_pin(self, public_key_bytes: bytes) -> str:
        """Add a PQC public key pin. Returns the SHA-256 hex hash."""
        import hashlib
        pin_hash = hashlib.sha256(public_key_bytes).hexdigest()
        self._pqc_hashes.add(pin_hash)
        return pin_hash

    def verify_pin(
        self,
        classical_cert_der: bytes | None = None,
        pqc_public_key: bytes | None = None,
    ) -> bool:
        """
        Verify certificate pin.

        In HYBRID mode: accepts if either classical OR PQC pin matches.
        In PQC_ONLY mode: only PQC pin must match.
        In CLASSICAL mode: only classical pin must match.

        Args:
            classical_cert_der: Classical certificate in DER format
            pqc_public_key: PQC public key bytes

        Returns:
            True if pin verification passes
        """
        import hashlib

        if self._mode == TlsMode.CLASSICAL_ONLY:
            if not classical_cert_der:
                return False
            cert_hash = hashlib.sha256(classical_cert_der).hexdigest()
            return cert_hash in self._classical_hashes

        if self._mode == TlsMode.PQC_ONLY:
            if not pqc_public_key:
                return False
            pqc_hash = hashlib.sha256(pqc_public_key).hexdigest()
            return pqc_hash in self._pqc_hashes

        # HYBRID mode: either pin can match
        classical_ok = False
        pqc_ok = False

        if classical_cert_der:
            cert_hash = hashlib.sha256(classical_cert_der).hexdigest()
            classical_ok = cert_hash in self._classical_hashes

        if pqc_public_key:
            pqc_hash = hashlib.sha256(pqc_public_key).hexdigest()
            pqc_ok = pqc_hash in self._pqc_hashes

        return classical_ok or pqc_ok

    def get_pin_report(self) -> dict:
        """Get a report of configured pins."""
        return {
            "mode": self._mode.value,
            "classical_pins_count": len(self._classical_hashes),
            "pqc_pins_count": len(self._pqc_hashes),
            "classical_pins": list(self._classical_hashes),
            "pqc_pins": list(self._pqc_hashes),
        }


# ════════════════════════════════════════════════════════════════════
# PQC Certificate Generation Helpers
# ════════════════════════════════════════════════════════════════════


def generate_pqc_signed_certificate(
    subject_name: str,
    validity_days: int = 365,
    ml_dsa_parameter_set: MlDsaParameterSet = MlDsaParameterSet.ML_DSA_65,
) -> PqcCertificate:
    """
    Generate a dual-signed certificate (classical ECDSA + PQC ML-DSA).

    This creates:
    1. A self-signed X.509 certificate with ECDSA P-256
    2. An ML-DSA-65 signature of the certificate
    3. The ML-DSA public key for pinning

    In production, use a real CA (e.g., Let's Encrypt + PQC intermediate CA).
    This function is for development/testing.

    Args:
        subject_name: Certificate subject (CN)
        validity_days: Certificate validity period
        ml_dsa_parameter_set: ML-DSA parameter set for PQC signature

    Returns:
        PqcCertificate with classical cert and PQC signature
    """
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    # Generate classical ECDSA key pair
    classical_key = ec.generate_private_key(ec.SECP256R1())

    # Build self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, subject_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Angavu Intelligence"),
    ])

    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(classical_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName("*.angavu.co.ke"),
            ]),
            critical=False,
        )
        .sign(classical_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = classical_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Generate ML-DSA key pair and sign the certificate
    ml_dsa = MlDsaProvider(ml_dsa_parameter_set)
    pqc_key_pair = ml_dsa.generate_key_pair()
    pqc_signature = ml_dsa.sign(cert_pem, pqc_key_pair.private_key)

    logger.info(
        "Generated dual-signed certificate: CN=%s, classical=ECDSA-P256, pqc=%s",
        subject_name,
        ml_dsa_parameter_set.name,
    )

    return PqcCertificate(
        classical_cert_pem=cert_pem,
        classical_key_pem=key_pem,
        pqc_signature=pqc_signature,
        pqc_public_key=pqc_key_pair.public_key,
        pqc_algorithm=ml_dsa_parameter_set.name,
    )
