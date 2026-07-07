"""
ML-DSA (Module-Lattice-Based Digital Signature Algorithm) provider.

Implements NIST FIPS 204 (formerly CRYSTALS-Dilithium).
ML-DSA provides EUF-CMA secure digital signatures resistant to quantum attacks.

╔══════════════════════════════════════════════════════════════╗
║  ⚠️  STUB IMPLEMENTATION — NOT REAL CRYPTOGRAPHY  ⚠️        ║
╠══════════════════════════════════════════════════════════════╣
║  This implementation uses hashlib.sha512 for signatures.     ║
║  It provides ZERO digital signature security. Forgery is     ║
║  trivial. DO NOT use for production signing.                  ║
║                                                              ║
║  Production: install liboqs-python                           ║
║  Fallback: use RSA-2048 or ECDSA-P256 (real signatures)     ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    provider = MlDsaProvider(MlDsaParameterSet.ML_DSA_65)
    if provider.is_stub:
        # Fall back to RSA/ECDSA — real signatures
        use_rsa_or_ecdsa_instead()
    else:
        key_pair = provider.generate_key_pair()
        signature = provider.sign(document, key_pair.private_key)
        valid = provider.verify(document, signature, key_pair.public_key)

See: https://csrc.nist.gov/pubs/fips/204/final
"""

import hashlib
import os
from enum import Enum

from .crypto_provider import CryptoProvider, CryptoKeyPair


class MlDsaParameterSet(Enum):
    """ML-DSA parameter sets per NIST FIPS 204."""
    ML_DSA_44 = (2, 1312, 2560, 2420)   # Level 2, pub, priv, max_sig
    ML_DSA_65 = (3, 1952, 4032, 3293)   # Level 3 — recommended
    ML_DSA_87 = (5, 2592, 4896, 4595)   # Level 5

    def __init__(self, security_level: int, pub_key_size: int, priv_key_size: int, max_sig_size: int):
        self.security_level = security_level
        self.pub_key_size = pub_key_size
        self.priv_key_size = priv_key_size
        self.max_sig_size = max_sig_size


class MlDsaProvider(CryptoProvider):
    """
    ML-DSA digital signature provider (STUB).

    ╔══════════════════════════════════════════════════════════════╗
    ║  ⚠️  STUB IMPLEMENTATION — NOT REAL CRYPTOGRAPHY  ⚠️        ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  This implementation uses hashlib.sha512 for signatures.     ║
    ║  It provides ZERO digital signature security. Forgery is     ║
    ║  trivial. DO NOT use for production signing.                  ║
    ║                                                              ║
    ║  Production: install liboqs-python                           ║
    ║  Fallback: use RSA-2048 or ECDSA-P256 (real signatures)     ║
    ╚══════════════════════════════════════════════════════════════╝

    Replace with native ML-DSA when liboqs-python is available:
        pip install liboqs-python
    """

    is_stub: bool = True  # Callers MUST check this before use

    def __init__(self, parameter_set: MlDsaParameterSet = MlDsaParameterSet.ML_DSA_65):
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
        """STUB: No real provider available. Callers must fall back to RSA-2048/ECDSA-P256."""
        return None

    def generate_key_pair(self) -> CryptoKeyPair:
        """Generate an ML-DSA key pair (STUB — NOT REAL CRYPTOGRAPHY)."""
        public_key = os.urandom(self._param_set.pub_key_size)
        private_key = os.urandom(self._param_set.priv_key_size)
        return CryptoKeyPair(
            public_key=public_key,
            private_key=private_key,
            algorithm_id=self.algorithm_id,
        )

    def sign(self, data: bytes, private_key: bytes) -> bytes:
        """Sign data using ML-DSA (STUB — NOT REAL CRYPTOGRAPHY)."""
        if len(private_key) != self._param_set.priv_key_size:
            raise ValueError(f"Invalid private key size for {self._param_set.name}")
        # STUB: deterministic signature from data only, so verify() can re-derive
        # In production, replace with native ML-DSA signing.
        h = hashlib.sha512(data).digest()
        signature = bytearray(self._param_set.max_sig_size)
        signature[: len(h)] = h
        return bytes(signature)

    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """Verify an ML-DSA signature (STUB — NOT REAL CRYPTOGRAPHY)."""
        if len(public_key) != self._param_set.pub_key_size:
            raise ValueError(f"Invalid public key size for {self._param_set.name}")
        if len(signature) < 32:
            return False
        # STUB: re-derive expected signature and compare first 32 bytes
        # In production, replace with native ML-DSA verification.
        expected = hashlib.sha512(data).digest()[:32]
        return signature[:32] == expected

    def encrypt(self, plaintext: bytes, key: bytes) -> bytes:
        raise NotImplementedError("ML-DSA is a signature algorithm, not encryption")

    def decrypt(self, ciphertext: bytes, key: bytes) -> bytes:
        raise NotImplementedError("ML-DSA is a signature algorithm, not encryption")
