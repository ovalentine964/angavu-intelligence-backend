"""
ML-DSA (Module-Lattice-Based Digital Signature Algorithm) provider.

Implements NIST FIPS 204 (formerly CRYSTALS-Dilithium) using liboqs-python.
ML-DSA provides EUF-CMA secure digital signatures resistant to quantum attacks.

This is a REAL implementation backed by liboqs (Open Quantum Safe).
No stubs, no SHA-512 hash placeholders.

Usage:
    provider = MlDsaProvider(MlDsaParameterSet.ML_DSA_65)
    key_pair = provider.generate_key_pair()
    signature = provider.sign(document, key_pair.private_key)
    valid = provider.verify(document, signature, key_pair.public_key)

See: https://csrc.nist.gov/pubs/fips/204/final
"""

from enum import Enum

import oqs

from .crypto_provider import CryptoKeyPair, CryptoProvider


class MlDsaParameterSet(Enum):
    """ML-DSA parameter sets per NIST FIPS 204."""
    ML_DSA_44 = "ML-DSA-44"  # NIST Level 2
    ML_DSA_65 = "ML-DSA-65"  # NIST Level 3 — recommended
    ML_DSA_87 = "ML-DSA-87"  # NIST Level 5


# Map parameter set names to liboQS signature algorithm names
_PARAM_TO_OQS = {
    MlDsaParameterSet.ML_DSA_44: "ML-DSA-44",
    MlDsaParameterSet.ML_DSA_65: "ML-DSA-65",
    MlDsaParameterSet.ML_DSA_87: "ML-DSA-87",
}


class MlDsaProvider(CryptoProvider):
    """
    ML-DSA digital signature provider using liboqs.

    This is a REAL implementation. Key generation, signing, and verification
    all use the NIST-approved ML-DSA algorithm via the liboqs library
    (Open Quantum Safe project).

    Supported parameter sets:
    - ML-DSA-44: NIST Level 2 (128-bit post-quantum security)
    - ML-DSA-65: NIST Level 3 (192-bit post-quantum security) — recommended
    - ML-DSA-87: NIST Level 5 (256-bit post-quantum security)
    """

    is_stub: bool = False  # REAL implementation

    def __init__(self, parameter_set: MlDsaParameterSet = MlDsaParameterSet.ML_DSA_65):
        self._param_set = parameter_set
        self._oqs_name = _PARAM_TO_OQS[parameter_set]

        # Verify liboqs supports this algorithm
        enabled_sigs = oqs.get_enabled_sig_mechanisms()
        if self._oqs_name not in enabled_sigs:
            raise RuntimeError(
                f"liboqs does not support {self._oqs_name}. "
                f"Available sigs: {enabled_sigs}"
            )

    @property
    def algorithm_id(self) -> str:
        return self._param_set.name

    @property
    def is_post_quantum(self) -> bool:
        return True

    @property
    def security_level(self) -> int:
        levels = {
            MlDsaParameterSet.ML_DSA_44: 2,
            MlDsaParameterSet.ML_DSA_65: 3,
            MlDsaParameterSet.ML_DSA_87: 5,
        }
        return levels[self._param_set]

    def get_real_provider(self):
        """This IS the real provider."""
        return self

    def generate_key_pair(self) -> CryptoKeyPair:
        """Generate an ML-DSA key pair using liboqs."""
        with oqs.Signature(self._oqs_name) as sig:
            public_key = sig.generate_keypair()
            secret_key = sig.export_secret_key()

        return CryptoKeyPair(
            public_key=public_key,
            private_key=secret_key,
            algorithm_id=self.algorithm_id,
        )

    def sign(self, data: bytes, private_key: bytes) -> bytes:
        """
        Sign data using ML-DSA.

        The signature is hedged (randomized) per FIPS 204, Section 5.4.
        Each call produces a different signature for the same data,
        which is a security advantage over deterministic schemes.

        Args:
            data: The data to sign
            private_key: The signer's ML-DSA private key bytes

        Returns:
            ML-DSA signature bytes

        Raises:
            ValueError: If private_key size is invalid
        """
        with oqs.Signature(self._oqs_name) as sig:
            sig.import_secret_key(private_key)
            signature = sig.sign(data)

        return signature

    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """
        Verify an ML-DSA signature.

        Returns True if and only if the signature was produced by the
        holder of the private key corresponding to this public key.

        Args:
            data: The original data
            signature: The ML-DSA signature to verify
            public_key: The signer's ML-DSA public key bytes

        Returns:
            True if the signature is valid, False otherwise
        """
        with oqs.Signature(self._oqs_name) as sig:
            is_valid = sig.verify(data, signature, public_key)

        return is_valid

    def encrypt(self, plaintext: bytes, key: bytes) -> bytes:
        raise NotImplementedError(
            "ML-DSA is a digital signature algorithm, not an encryption algorithm. "
            "Use ML-KEM for key exchange + AES-256-GCM for encryption."
        )

    def decrypt(self, ciphertext: bytes, key: bytes) -> bytes:
        raise NotImplementedError(
            "ML-DSA is a digital signature algorithm. Use ML-KEM + AES-256-GCM."
        )
