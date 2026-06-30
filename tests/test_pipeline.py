"""
Tests for the data pipeline.

Tests cover:
- Product name normalization
- Category assignment
- Differential privacy
- k-anonymity enforcement
- Anomaly detection
- Compression utilities
- Encryption utilities
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import numpy as np

from app.services.pipeline import DataPipeline, PRODUCT_NORMALIZATION, CATEGORY_MAP
from app.services.anonymizer import Anonymizer
from app.utils.compression import (
    compress_payload,
    decompress_payload,
    estimate_compression_ratio,
    get_compression_level_for_network,
)
from app.utils.crypto import (
    encrypt_value,
    decrypt_value,
    hash_phone,
    hash_value,
    create_hmac_signature,
    verify_hmac_signature,
)


# =========================================================================
# Product Normalization Tests
# =========================================================================


class TestProductNormalization:
    """Test product name normalization."""

    def test_swahili_to_english(self):
        """Swahili product names should map to English."""
        pipeline = DataPipeline(None)  # No DB needed for this

        assert pipeline.normalize_product_name("mchele") == "rice"
        assert pipeline.normalize_product_name("wali") == "rice"
        assert pipeline.normalize_product_name("unga") == "maize_flour"
        assert pipeline.normalize_product_name("sukari") == "sugar"
        assert pipeline.normalize_product_name("nyanya") == "tomatoes"
        assert pipeline.normalize_product_name("vitunguu") == "onions"

    def test_english_passthrough(self):
        """English names should pass through unchanged."""
        pipeline = DataPipeline(None)

        assert pipeline.normalize_product_name("rice") == "rice"
        assert pipeline.normalize_product_name("sugar") == "sugar"
        assert pipeline.normalize_product_name("custom_item") == "custom_item"

    def test_case_insensitive(self):
        """Normalization should be case-insensitive."""
        pipeline = DataPipeline(None)

        assert pipeline.normalize_product_name("MCHELE") == "rice"
        assert pipeline.normalize_product_name("Sukari") == "sugar"

    def test_none_handling(self):
        """None input should return None."""
        pipeline = DataPipeline(None)
        assert pipeline.normalize_product_name(None) is None
        assert pipeline.normalize_product_name("") is None


class TestCategorization:
    """Test product categorization."""

    def test_food_items(self):
        """Food items should be categorized correctly."""
        pipeline = DataPipeline(None)

        assert pipeline.categorize_product("rice") == "food"
        assert pipeline.categorize_product("tomatoes") == "food"
        assert pipeline.categorize_product("sugar") == "food"

    def test_household_items(self):
        """Household items should be categorized correctly."""
        pipeline = DataPipeline(None)

        assert pipeline.categorize_product("soap") == "household"
        assert pipeline.categorize_product("paraffin") == "household"

    def test_unknown_items(self):
        """Unknown items should be categorized as 'other'."""
        pipeline = DataPipeline(None)

        assert pipeline.categorize_product("custom_widget") == "other"
        assert pipeline.categorize_product("") == "other"


# =========================================================================
# Differential Privacy Tests
# =========================================================================


class TestDifferentialPrivacy:
    """Test differential privacy noise addition."""

    def test_laplace_noise_adds_variation(self):
        """Adding noise should produce different values."""
        pipeline = DataPipeline(None)

        original = 1000.0
        noised_values = [
            pipeline.apply_differential_privacy(original, sensitivity=100)
            for _ in range(100)
        ]

        # All values should be different (with overwhelming probability)
        assert len(set(noised_values)) > 90

        # Mean should be close to original (within 10%)
        mean_noised = np.mean(noised_values)
        assert abs(mean_noised - original) / original < 0.1

    def test_noise_centered_on_true_value(self):
        """Noise should be centered on zero (unbiased)."""
        from app.config import get_settings
        settings = get_settings()

        pipeline = DataPipeline(None)
        original = 5000.0

        # Generate many noised values
        noised = [
            pipeline.apply_differential_privacy(original, sensitivity=500)
            for _ in range(1000)
        ]

        # Check bias is small
        mean_noise = np.mean([v - original for v in noised])
        assert abs(mean_noise) < 100  # Should be close to 0

    def test_k_anonymity_threshold(self):
        """k-anonymity should suppress small groups."""
        pipeline = DataPipeline(None)

        # Below threshold
        k = pipeline.compute_k_anonymity_value(5)
        assert k == 0  # Suppressed

        # At threshold
        k = pipeline.compute_k_anonymity_value(10)
        assert k == 10

        # Above threshold
        k = pipeline.compute_k_anonymity_value(50)
        assert k == 50


# =========================================================================
# Anonymizer Tests
# =========================================================================


class TestAnonymizer:
    """Test PII stripping and anonymization."""

    def test_strip_pii(self):
        """PII fields should be removed."""
        data = {
            "name": "John Doe",
            "phone": "+254712345678",
            "phone_hash": "abc123",
            "amount": 500.0,
            "item": "sukari",
            "location_geohash": "ke001abc123",
            "mpesa_receipt": "QHK123456",
            "customer_phone": "+254798765432",
        }

        cleaned = Anonymizer.strip_pii(data)

        # PII should be removed
        assert "name" not in cleaned
        assert "phone" not in cleaned
        assert "phone_hash" not in cleaned
        assert "mpesa_receipt" not in cleaned
        assert "customer_phone" not in cleaned

        # Non-PII should remain
        assert cleaned["amount"] == 500.0
        assert cleaned["item"] == "sukari"

        # Location should be coarsened to geohash-5
        assert len(cleaned["location_geohash"]) == 5

    def test_product_generalization(self):
        """Products should generalize to broader categories."""
        # Level 0: specific
        assert Anonymizer.generalize_product("tomatoes", level=0) == "tomatoes"

        # Level 1: sub-category
        assert Anonymizer.generalize_product("tomatoes", level=1) == "vegetables"

        # Level 2: category
        assert Anonymizer.generalize_product("tomatoes", level=2) == "food"

        # Level 3: sector
        assert Anonymizer.generalize_product("tomatoes", level=3) == "consumer_goods"

    def test_temporal_minimums(self):
        """Temporal aggregation rules should be enforced."""
        # Ward-level requires weekly minimum
        assert Anonymizer.enforce_temporal_minimums("daily", "ward") is False
        assert Anonymizer.enforce_temporal_minimums("weekly", "ward") is True
        assert Anonymizer.enforce_temporal_minimums("monthly", "ward") is True

        # County allows daily
        assert Anonymizer.enforce_temporal_minimums("daily", "county") is True
        assert Anonymizer.enforce_temporal_minimums("weekly", "county") is True

        # National allows daily
        assert Anonymizer.enforce_temporal_minimums("daily", "national") is True


# =========================================================================
# Compression Tests
# =========================================================================


class TestCompression:
    """Test zstd compression utilities."""

    def test_compress_decompress_roundtrip(self):
        """Compressed data should decompress back to original."""
        data = {
            "device_id": "test-device",
            "transactions": [
                {"item": "sukari", "amount": 500, "type": "SALE"},
                {"item": "nyanya", "amount": 800, "type": "SALE"},
                {"item": "mafuta", "amount": 300, "type": "PURCHASE"},
            ],
            "timestamp": "2026-06-30T14:30:00Z",
        }

        compressed = compress_payload(data)
        decompressed = decompress_payload(compressed)

        assert decompressed == data

    def test_compression_reduces_size(self):
        """Compression should reduce payload size by 50%+."""
        # Simulate a realistic transaction payload
        data = {
            "device_id": "device-uuid-12345",
            "user_hash": "sha256hash",
            "payload": {
                "transactions": [
                    {
                        "type": "SALE",
                        "item": f"product_{i}",
                        "qty": i,
                        "amount": i * 100,
                        "timestamp": f"2026-06-30T{10 + i}:00:00Z",
                    }
                    for i in range(50)
                ],
            },
        }

        compressed = compress_payload(data)
        import json
        original_size = len(json.dumps(data).encode())
        compressed_size = len(compressed)

        ratio = compressed_size / original_size
        assert ratio < 0.5  # Should achieve >50% compression

    def test_network_specific_compression(self):
        """Different networks should get different compression levels."""
        assert get_compression_level_for_network("wifi") < get_compression_level_for_network("mobile_2g")
        assert get_compression_level_for_network("mobile_3g") < get_compression_level_for_network("mobile_2g")

    def test_compression_ratio_estimation(self):
        """Compression ratio estimation should work."""
        data = {"key": "value" * 100}
        ratio = estimate_compression_ratio(data)
        assert 0 < ratio < 1  # Should compress


# =========================================================================
# Encryption Tests
# =========================================================================


class TestEncryption:
    """Test encryption utilities."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypted values should decrypt back to original."""
        values = [
            "+254712345678",
            "John Doe",
            "a very long string with special chars: !@#$%^&*()",
            "unicode: 你好世界",
        ]

        for original in values:
            encrypted = encrypt_value(original)
            decrypted = decrypt_value(encrypted)
            assert decrypted == original

    def test_encrypted_values_are_different(self):
        """Same value encrypted twice should produce different ciphertext (due to random nonce)."""
        value = "+254712345678"
        enc1 = encrypt_value(value)
        enc2 = encrypt_value(value)

        # Different nonces → different ciphertext
        assert enc1 != enc2

        # But both decrypt to the same value
        assert decrypt_value(enc1) == decrypt_value(enc2)

    def test_phone_hashing(self):
        """Phone hashing should be deterministic."""
        phone = "+254712345678"
        hash1 = hash_phone(phone)
        hash2 = hash_phone(phone)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_hmac_signature(self):
        """HMAC signatures should be verifiable."""
        payload = b"test payload data"
        secret = "test-secret-key"

        signature = create_hmac_signature(payload, secret)

        # Valid signature should verify
        assert verify_hmac_signature(payload, signature, secret) is True

        # Invalid signature should fail
        assert verify_hmac_signature(payload, "wrong", secret) is False

        # Wrong payload should fail
        assert verify_hmac_signature(b"wrong payload", signature, secret) is False


# =========================================================================
# Anomaly Detection Tests
# =========================================================================


class TestAnomalyDetection:
    """Test anomaly detection in the pipeline."""

    def test_health_score_calculation(self):
        """Health score should reflect business performance."""
        from app.services.report_gen import ReportGenerator

        gen = ReportGenerator(None)

        # Good metrics
        good_7d = {
            "total_sales": 50000,
            "net_profit": 15000,
            "profit_margin_pct": 30,
            "transaction_count": 100,
            "daily_breakdown": [{"sales": 7000} for _ in range(7)],
        }
        good_30d = {"total_sales": 200000}
        good_trends = {
            "trends": [
                {"metric": "transaction_count", "direction": "up", "change_pct": 15}
            ]
        }

        score = gen._calculate_health_score(good_7d, good_30d, good_trends)
        assert score >= 60  # Should be "good" or better

    def test_health_labels(self):
        """Health labels should map correctly."""
        from app.services.report_gen import ReportGenerator

        assert ReportGenerator._health_label(90) == "excellent"
        assert ReportGenerator._health_label(70) == "good"
        assert ReportGenerator._health_label(50) == "fair"
        assert ReportGenerator._health_label(30) == "needs_attention"
        assert ReportGenerator._health_label(10) == "critical"
