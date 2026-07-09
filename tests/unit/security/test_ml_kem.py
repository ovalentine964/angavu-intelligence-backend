"""Tests for ML-KEM (Module-Lattice Key Encapsulation Mechanism) provider.

Requires liboqs to be installed. Tests are skipped if oqs is unavailable.
"""

import pytest

try:
    import oqs

    _HAS_OQS = True
except ImportError:
    _HAS_OQS = False

from app.security.pqc.ml_kem import MlKemParameterSet, MlKemProvider
from app.security.pqc.crypto_provider import CryptoKeyPair, EncapsulatedKey

pytestmark = pytest.mark.skipif(not _HAS_OQS, reason="liboqs not installed")


class TestMlKemProvider:
    def test_init_default(self):
        provider = MlKemProvider()
        assert provider.algorithm_id == "ML_KEM_768"
        assert provider.is_post_quantum is True
        assert provider.is_stub is False

    def test_init_ml_kem_512(self):
        provider = MlKemProvider(MlKemParameterSet.ML_KEM_512)
        assert provider.algorithm_id == "ML_KEM_512"
        assert provider.security_level == 1

    def test_init_ml_kem_768(self):
        provider = MlKemProvider(MlKemParameterSet.ML_KEM_768)
        assert provider.security_level == 3

    def test_init_ml_kem_1024(self):
        provider = MlKemProvider(MlKemParameterSet.ML_KEM_1024)
        assert provider.algorithm_id == "ML_KEM_1024"
        assert provider.security_level == 5

    def test_generate_key_pair(self):
        provider = MlKemProvider()
        kp = provider.generate_key_pair()
        assert isinstance(kp, CryptoKeyPair)
        assert len(kp.public_key) > 0
        assert len(kp.private_key) > 0
        assert kp.algorithm_id == "ML_KEM_768"

    def test_encapsulate_decapsulate_roundtrip(self):
        provider = MlKemProvider()
        kp = provider.generate_key_pair()

        encap = provider.encapsulate(kp.public_key)
        assert isinstance(encap, EncapsulatedKey)
        assert len(encap.ciphertext) > 0
        assert len(encap.shared_secret) > 0
        assert encap.algorithm_id == "ML_KEM_768"

        recovered = provider.decapsulate(encap.ciphertext, kp.private_key)
        assert recovered == encap.shared_secret

    def test_multiple_encapsulations_differ(self):
        """Each encapsulation should produce different ciphertext (randomized)."""
        provider = MlKemProvider()
        kp = provider.generate_key_pair()

        encap1 = provider.encapsulate(kp.public_key)
        encap2 = provider.encapsulate(kp.public_key)

        # Ciphertexts should differ (randomized encapsulation)
        assert encap1.ciphertext != encap2.ciphertext
        # Shared secrets should also differ
        assert encap1.shared_secret != encap2.shared_secret

    def test_wrong_key_decapsulation_fails(self):
        """Decapsulating with wrong key should not recover the secret."""
        provider = MlKemProvider()
        kp1 = provider.generate_key_pair()
        kp2 = provider.generate_key_pair()

        encap = provider.encapsulate(kp1.public_key)
        recovered = provider.decapsulate(encap.ciphertext, kp2.private_key)

        assert recovered != encap.shared_secret

    def test_shared_secret_size(self):
        provider = MlKemProvider()
        kp = provider.generate_key_pair()
        encap = provider.encapsulate(kp.public_key)
        assert len(encap.shared_secret) == 32

    def test_all_parameter_sets(self):
        """All parameter sets should work end-to-end."""
        for param in MlKemParameterSet:
            provider = MlKemProvider(param)
            kp = provider.generate_key_pair()
            encap = provider.encapsulate(kp.public_key)
            recovered = provider.decapsulate(encap.ciphertext, kp.private_key)
            assert recovered == encap.shared_secret, f"Failed for {param}"

    def test_get_real_provider(self):
        provider = MlKemProvider()
        real = provider.get_real_provider()
        assert real is provider

    def test_encrypt_raises(self):
        provider = MlKemProvider()
        with pytest.raises(NotImplementedError):
            provider.encrypt(b"test", b"key")

    def test_decrypt_raises(self):
        provider = MlKemProvider()
        with pytest.raises(NotImplementedError):
            provider.decrypt(b"test", b"key")

    def test_sign_raises(self):
        provider = MlKemProvider()
        with pytest.raises(NotImplementedError):
            provider.sign(b"test", b"key")

    def test_verify_raises(self):
        provider = MlKemProvider()
        with pytest.raises(NotImplementedError):
            provider.verify(b"test", b"sig", b"key")
