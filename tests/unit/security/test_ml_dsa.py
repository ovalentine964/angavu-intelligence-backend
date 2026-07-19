"""Tests for ML-DSA (Module-Lattice Digital Signature Algorithm) provider.

Requires liboqs to be installed. Tests are skipped if oqs is unavailable.
"""

import pytest

try:
    import oqs

    _HAS_OQS = True
except ImportError:
    _HAS_OQS = False

from app.security.pqc.crypto_provider import CryptoKeyPair
from app.security.pqc.ml_dsa import MlDsaParameterSet, MlDsaProvider

pytestmark = pytest.mark.skipif(not _HAS_OQS, reason="liboqs not installed")


class TestMlDsaProvider:
    def test_init_default(self):
        provider = MlDsaProvider()
        assert provider.algorithm_id == "ML_DSA_65"
        assert provider.is_post_quantum is True
        assert provider.is_stub is False

    def test_init_ml_dsa_44(self):
        provider = MlDsaProvider(MlDsaParameterSet.ML_DSA_44)
        assert provider.algorithm_id == "ML_DSA_44"
        assert provider.security_level == 2

    def test_init_ml_dsa_65(self):
        provider = MlDsaProvider(MlDsaParameterSet.ML_DSA_65)
        assert provider.security_level == 3

    def test_init_ml_dsa_87(self):
        provider = MlDsaProvider(MlDsaParameterSet.ML_DSA_87)
        assert provider.algorithm_id == "ML_DSA_87"
        assert provider.security_level == 5

    def test_generate_key_pair(self):
        provider = MlDsaProvider()
        kp = provider.generate_key_pair()
        assert isinstance(kp, CryptoKeyPair)
        assert len(kp.public_key) > 0
        assert len(kp.private_key) > 0
        assert kp.algorithm_id == "ML_DSA_65"

    def test_sign_verify_roundtrip(self):
        provider = MlDsaProvider()
        kp = provider.generate_key_pair()
        message = b"Hello, post-quantum world!"

        signature = provider.sign(message, kp.private_key)
        assert len(signature) > 0

        is_valid = provider.verify(message, signature, kp.public_key)
        assert is_valid is True

    def test_verify_wrong_message(self):
        provider = MlDsaProvider()
        kp = provider.generate_key_pair()

        signature = provider.sign(b"correct message", kp.private_key)
        is_valid = provider.verify(b"wrong message", signature, kp.public_key)
        assert is_valid is False

    def test_verify_wrong_key(self):
        provider = MlDsaProvider()
        kp1 = provider.generate_key_pair()
        kp2 = provider.generate_key_pair()

        signature = provider.sign(b"test", kp1.private_key)
        is_valid = provider.verify(b"test", signature, kp2.public_key)
        assert is_valid is False

    def test_verify_corrupted_signature(self):
        provider = MlDsaProvider()
        kp = provider.generate_key_pair()

        signature = provider.sign(b"test", kp.private_key)
        corrupted = bytearray(signature)
        corrupted[0] ^= 0xFF
        corrupted = bytes(corrupted)

        is_valid = provider.verify(b"test", corrupted, kp.public_key)
        assert is_valid is False

    def test_multiple_signatures_differ(self):
        """ML-DSA signatures are hedged (randomized), so each should differ."""
        provider = MlDsaProvider()
        kp = provider.generate_key_pair()
        message = b"same message"

        sig1 = provider.sign(message, kp.private_key)
        sig2 = provider.sign(message, kp.private_key)

        assert sig1 != sig2

    def test_all_parameter_sets(self):
        """All parameter sets should work end-to-end."""
        for param in MlDsaParameterSet:
            provider = MlDsaProvider(param)
            kp = provider.generate_key_pair()
            message = b"test message"
            signature = provider.sign(message, kp.private_key)
            is_valid = provider.verify(message, signature, kp.public_key)
            assert is_valid, f"Failed for {param}"

    def test_get_real_provider(self):
        provider = MlDsaProvider()
        real = provider.get_real_provider()
        assert real is provider

    def test_encrypt_raises(self):
        provider = MlDsaProvider()
        with pytest.raises(NotImplementedError):
            provider.encrypt(b"test", b"key")

    def test_decrypt_raises(self):
        provider = MlDsaProvider()
        with pytest.raises(NotImplementedError):
            provider.decrypt(b"test", b"key")
