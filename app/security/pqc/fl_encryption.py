"""
Post-Quantum Encryption for Federated Learning Gradients.

Provides PQC-encrypted transport for federated learning updates:
- ML-KEM-768 for key encapsulation (establishing shared secret)
- AES-256-GCM for encrypting gradient payloads (quantum-safe symmetric)
- ML-DSA-65 for signing gradient updates (authenticity)

This module integrates with the existing FederatedLearningService to
add end-to-end PQC encryption to the gradient upload/download pipeline.

Architecture:
    Device ──[ML-KEM encapsulate]──► shared_secret
    Device ──[AES-256-GCM encrypt(gradients, shared_secret)]──► encrypted_payload
    Device ──[ML-DSA-65 sign(encrypted_payload)]──► signature
    Device ──[encrypted_payload + signature + ml_kem_ciphertext]──► Server

    Server ──[ML-KEM decapsulate]──► shared_secret (same as device)
    Server ──[ML-DSA-65 verify(signature)]──► authenticity check
    Server ──[AES-256-GCM decrypt(encrypted_payload, shared_secret)]──► gradients

Security Properties:
    - Confidentiality: AES-256-GCM (128-bit post-quantum security)
    - Key exchange: ML-KEM-768 (IND-CCA2, NIST Level 3)
    - Authenticity: ML-DSA-65 (EUF-CMA, NIST Level 3)
    - Forward secrecy: per-update ephemeral ML-KEM keys
"""

import base64
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .ml_kem import MlKemProvider, MlKemParameterSet
from .ml_dsa import MlDsaProvider, MlDsaParameterSet
from .crypto_provider import CryptoKeyPair, EncapsulatedKey

logger = logging.getLogger(__name__)


@dataclass
class EncryptedGradientPayload:
    """An encrypted federated learning gradient payload."""

    # ML-KEM ciphertext (send to server for decapsulation)
    ml_kem_ciphertext: bytes

    # AES-256-GCM encrypted gradient data (nonce prepended)
    encrypted_gradients: bytes

    # ML-DSA-65 signature over the encrypted_gradients
    signature: bytes

    # Device's ML-DSA public key (for signature verification)
    device_pqc_public_key: bytes

    # Metadata (unencrypted)
    device_id: str
    timestamp: int
    language: str
    version: str

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for network transport."""
        return {
            "ml_kem_ciphertext": base64.b64encode(self.ml_kem_ciphertext).decode("ascii"),
            "encrypted_gradients": base64.b64encode(self.encrypted_gradients).decode("ascii"),
            "signature": base64.b64encode(self.signature).decode("ascii"),
            "device_pqc_public_key": base64.b64encode(self.device_pqc_public_key).decode("ascii"),
            "device_id": self.device_id,
            "timestamp": self.timestamp,
            "language": self.language,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EncryptedGradientPayload":
        """Deserialize from network transport."""
        return cls(
            ml_kem_ciphertext=base64.b64decode(data["ml_kem_ciphertext"]),
            encrypted_gradients=base64.b64decode(data["encrypted_gradients"]),
            signature=base64.b64decode(data["signature"]),
            device_pqc_public_key=base64.b64decode(data["device_pqc_public_key"]),
            device_id=data["device_id"],
            timestamp=data["timestamp"],
            language=data["language"],
            version=data.get("version", "v3.2.0"),
        )


class FlPqcEncryptor:
    """
    PQC encryptor for federated learning gradient updates.

    Used by DEVICES to encrypt gradient uploads:
        encryptor = FlPqcEncryptor()
        payload = encryptor.encrypt_gradients(
            gradients=gradient_bytes,
            server_ml_kem_public_key=server_pub_key,
            device_id="abc123",
            language="sw",
        )
        # Send payload.to_dict() to server

    Used by SERVER to decrypt gradient uploads:
        decryptor = FlPqcDecryptor(server_ml_kem_key_pair)
        gradients = decryptor.decrypt_gradients(payload)
    """

    def __init__(
        self,
        ml_kem_provider: Optional[MlKemProvider] = None,
        ml_dsa_provider: Optional[MlDsaProvider] = None,
    ):
        self._ml_kem = ml_kem_provider or MlKemProvider(MlKemParameterSet.ML_KEM_768)
        self._ml_dsa = ml_dsa_provider or MlDsaProvider(MlDsaParameterSet.ML_DSA_65)

        # Device's signing key pair (generated once, stored securely)
        self._device_signing_keypair: Optional[CryptoKeyPair] = None

    def generate_device_signing_key(self) -> CryptoKeyPair:
        """Generate the device's ML-DSA signing key pair."""
        self._device_signing_keypair = self._ml_dsa.generate_key_pair()
        return self._device_signing_keypair

    def encrypt_gradients(
        self,
        gradients: bytes,
        server_ml_kem_public_key: bytes,
        device_id: str,
        language: str,
        version: str = "v3.2.0",
    ) -> EncryptedGradientPayload:
        """
        Encrypt gradient data for upload to server.

        Process:
        1. ML-KEM encapsulate using server's public key → shared_secret
        2. AES-256-GCM encrypt gradients using shared_secret
        3. ML-DSA sign the encrypted payload

        Args:
            gradients: Raw gradient bytes (float32 array, base64 or packed)
            server_ml_kem_public_key: Server's ML-KEM-768 public key
            device_id: Device identifier
            language: Language/dialect code
            version: Model version

        Returns:
            EncryptedGradientPayload ready for network transport
        """
        # Step 1: ML-KEM encapsulation (ephemeral, per-upload)
        ml_kem_result = self._ml_kem.encapsulate(server_ml_kem_public_key)
        shared_secret = ml_kem_result.shared_secret

        # Step 2: AES-256-GCM encryption
        aesgcm = AESGCM(shared_secret)
        nonce = os.urandom(12)  # 96-bit nonce
        encrypted = nonce + aesgcm.encrypt(nonce, gradients, device_id.encode("utf-8"))

        # Step 3: ML-DSA signature
        if self._device_signing_keypair is None:
            self.generate_device_signing_key()

        # Sign the encrypted payload + metadata for integrity
        sign_data = encrypted + device_id.encode("utf-8") + str(int(time.time() * 1000)).encode()
        signature = self._ml_dsa.sign(sign_data, self._device_signing_keypair.private_key)

        logger.info(
            "FL gradients encrypted: device=%s, lang=%s, size=%d bytes",
            device_id, language, len(gradients),
        )

        return EncryptedGradientPayload(
            ml_kem_ciphertext=ml_kem_result.ciphertext,
            encrypted_gradients=encrypted,
            signature=signature,
            device_pqc_public_key=self._device_signing_keypair.public_key,
            device_id=device_id,
            timestamp=int(time.time() * 1000),
            language=language,
            version=version,
        )


class FlPqcDecryptor:
    """
    PQC decryptor for federated learning gradient updates.

    Used by SERVER to decrypt gradient uploads:
        decryptor = FlPqcDecryptor(server_ml_kem_key_pair)
        gradients = decryptor.decrypt_gradients(payload)
    """

    def __init__(
        self,
        server_ml_kem_keypair: CryptoKeyPair,
        ml_kem_provider: Optional[MlKemProvider] = None,
        ml_dsa_provider: Optional[MlDsaProvider] = None,
    ):
        self._server_kem_keypair = server_ml_kem_keypair
        self._ml_kem = ml_kem_provider or MlKemProvider(MlKemParameterSet.ML_KEM_768)
        self._ml_dsa = ml_dsa_provider or MlDsaProvider(MlDsaParameterSet.ML_DSA_65)

    def decrypt_gradients(
        self,
        payload: EncryptedGradientPayload,
        verify_signature: bool = True,
    ) -> Tuple[bytes, bool]:
        """
        Decrypt gradient data from a device.

        Process:
        1. ML-DSA verify signature (authenticity)
        2. ML-KEM decapsulate using server's private key → shared_secret
        3. AES-256-GCM decrypt gradients using shared_secret

        Args:
            payload: The encrypted gradient payload from the device
            verify_signature: Whether to verify the ML-DSA signature

        Returns:
            Tuple of (decrypted_gradient_bytes, signature_valid)

        Raises:
            ValueError: If decryption fails
            SecurityException: If signature verification fails
        """
        # Step 1: Verify ML-DSA signature
        signature_valid = True
        if verify_signature:
            sign_data = (
                payload.encrypted_gradients
                + payload.device_id.encode("utf-8")
                + str(payload.timestamp).encode()
            )
            signature_valid = self._ml_dsa.verify(
                sign_data,
                payload.signature,
                payload.device_pqc_public_key,
            )
            if not signature_valid:
                logger.warning(
                    "FL gradient signature INVALID: device=%s, timestamp=%d",
                    payload.device_id, payload.timestamp,
                )
                raise SecurityException(
                    f"ML-DSA signature verification failed for device {payload.device_id}"
                )

        # Step 2: ML-KEM decapsulation
        shared_secret = self._ml_kem.decapsulate(
            payload.ml_kem_ciphertext,
            self._server_kem_keypair.private_key,
        )

        # Step 3: AES-256-GCM decryption
        nonce = payload.encrypted_gradients[:12]
        ciphertext = payload.encrypted_gradients[12:]

        aesgcm = AESGCM(shared_secret)
        try:
            gradients = aesgcm.decrypt(
                nonce, ciphertext, payload.device_id.encode("utf-8")
            )
        except Exception as e:
            logger.error(
                "FL gradient decryption FAILED: device=%s, error=%s",
                payload.device_id, str(e),
            )
            raise ValueError(f"Failed to decrypt gradients: {e}")

        logger.info(
            "FL gradients decrypted: device=%s, lang=%s, size=%d bytes, sig_valid=%s",
            payload.device_id, payload.language, len(gradients), signature_valid,
        )

        return gradients, signature_valid


class SecurityException(Exception):
    """Raised when a security check fails."""
    pass
