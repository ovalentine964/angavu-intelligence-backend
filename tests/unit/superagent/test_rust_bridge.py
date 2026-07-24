"""
Tests for the Rust Bridge — Python fallback functions.

Tests all Python→Rust bridge functions including crypto, phone validation,
input sanitization, transaction processing, M-Pesa parsing, sync/conflict
resolution, and vector operations.
"""

import base64
import json
import math
import pytest
from unittest.mock import patch

try:
    from app.services.rust_bridge import (
        encrypt_aes_gcm,
        decrypt_aes_gcm,
        generate_key,
        sha256_hash,
        validate_phone_ke,
        normalize_phone_ke,
        sanitize_input,
        sanitize_input_batch,
        process_transactions_batch,
        validate_transaction,
        parse_mpesa_sms,
        parse_mpesa_sms_batch,
        resolve_conflicts,
        compute_delta,
        apply_delta,
        cosine_similarity,
        cosine_similarity_batch,
        batch_dot_product,
        batch_normalize,
        is_rust_available,
    )
    RUST_BRIDGE_AVAILABLE = True
except ImportError:
    RUST_BRIDGE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not RUST_BRIDGE_AVAILABLE,
    reason="rust_bridge import failed (missing scipy or other deps)"
)


# ═══════════════════════════════════════════════════════════════════
# CRYPTO TESTS
# ═══════════════════════════════════════════════════════════════════


class TestCrypto:
    """Test AES-GCM encryption/decryption and key generation."""

    def test_encrypt_decrypt_roundtrip(self):
        key = generate_key(32)
        plaintext = "Habari, mimi ni msaidizi wako!"
        ciphertext = encrypt_aes_gcm(plaintext, key)
        decrypted = decrypt_aes_gcm(ciphertext, key)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext(self):
        """Same plaintext encrypted twice should produce different ciphertexts (random nonce)."""
        key = generate_key(32)
        ct1 = encrypt_aes_gcm("test", key)
        ct2 = encrypt_aes_gcm("test", key)
        assert ct1 != ct2

    def test_generate_key_length(self):
        key_b64 = generate_key(32)
        key_bytes = base64.b64decode(key_b64)
        assert len(key_bytes) == 32

    def test_generate_key_16(self):
        key_b64 = generate_key(16)
        key_bytes = base64.b64decode(key_b64)
        assert len(key_bytes) == 16

    def test_sha256_hash_deterministic(self):
        h1 = sha256_hash("hello world")
        h2 = sha256_hash("hello world")
        assert h1 == h2
        assert len(h1) == 64  # hex digest

    def test_sha256_hash_different_inputs(self):
        assert sha256_hash("abc") != sha256_hash("def")

    def test_sha256_empty_string(self):
        h = sha256_hash("")
        assert len(h) == 64


# ═══════════════════════════════════════════════════════════════════
# PHONE VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestPhoneValidation:
    """Test Kenyan phone number validation and normalization."""

    def test_valid_safaricom(self):
        assert validate_phone_ke("0722000000") is True
        assert validate_phone_ke("0712345678") is True

    def test_valid_with_country_code(self):
        assert validate_phone_ke("+254722000000") is True
        assert validate_phone_ke("254722000000") is True

    def test_valid_airtel(self):
        assert validate_phone_ke("0733000000") is True

    def test_invalid_too_short(self):
        assert validate_phone_ke("0722000") is False

    def test_invalid_wrong_prefix(self):
        assert validate_phone_ke("0622000000") is False

    def test_invalid_letters(self):
        assert validate_phone_ke("abcdefghij") is False

    def test_normalize_with_plus(self):
        assert normalize_phone_ke("+254722000000") == "254722000000"

    def test_normalize_with_254(self):
        assert normalize_phone_ke("254722000000") == "254722000000"

    def test_normalize_with_0(self):
        assert normalize_phone_ke("0722000000") == "254722000000"

    def test_normalize_invalid_raises(self):
        with pytest.raises(ValueError):
            normalize_phone_ke("invalid")


# ═══════════════════════════════════════════════════════════════════
# INPUT SANITIZATION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestSanitization:
    """Test SQL injection, XSS, and path traversal prevention."""

    def test_normal_text_passes(self):
        assert sanitize_input("Hello, how are you?") == "Hello, how are you?"

    def test_strips_null_bytes(self):
        assert "\0" not in sanitize_input("test\0value")

    def test_strips_sql_keywords(self):
        result = sanitize_input("SELECT * FROM users")
        assert "SELECT" not in result
        assert "FROM" not in result

    def test_strips_sql_comments(self):
        result = sanitize_input("test -- comment")
        assert "--" not in result

    def test_escapes_html_tags(self):
        result = sanitize_input("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;" in result

    def test_strips_path_traversal(self):
        result = sanitize_input("../../etc/passwd")
        assert "../" not in result

    def test_batch_sanitization(self):
        inputs = ["normal", "<b>bold</b>", "SELECT * FROM x"]
        results = sanitize_input_batch(inputs)
        assert len(results) == 3
        assert "<b>" not in results[1]
        assert "SELECT" not in results[2]


# ═══════════════════════════════════════════════════════════════════
# TRANSACTION PROCESSING TESTS
# ═══════════════════════════════════════════════════════════════════


class TestTransactionProcessing:
    """Test transaction batch processing and validation."""

    def test_process_sent_transaction(self):
        txns = [{"id": "1", "amount": 500, "tx_type": "sent"}]
        result = process_transactions_batch(txns)
        assert len(result) == 1
        assert result[0]["category"] == "transfer_out"
        assert result[0]["risk_score"] >= 0

    def test_process_received_transaction(self):
        txns = [{"id": "1", "amount": 1500, "tx_type": "received"}]
        result = process_transactions_batch(txns)
        assert result[0]["category"] == "transfer_in"

    def test_process_high_value_flag(self):
        txns = [{"id": "1", "amount": 80000, "tx_type": "sent"}]
        result = process_transactions_batch(txns)
        assert "high_value" in result[0]["flags"]
        assert result[0]["risk_score"] >= 0.3

    def test_process_credit_transaction(self):
        txns = [{"id": "1", "amount": 2000, "tx_type": "loan"}]
        result = process_transactions_batch(txns)
        assert result[0]["category"] == "credit"
        assert "credit" in result[0]["flags"]

    def test_process_paybill(self):
        txns = [{"id": "1", "amount": 3000, "tx_type": "pay_bill"}]
        result = process_transactions_batch(txns)
        assert result[0]["category"] == "bill_payment"

    def test_process_buygoods(self):
        txns = [{"id": "1", "amount": 200, "tx_type": "buy_goods"}]
        result = process_transactions_batch(txns)
        assert result[0]["category"] == "merchant_payment"

    def test_validate_transaction_valid(self):
        result = validate_transaction(500, "sent", "0722000000")
        assert result["valid"] is True
        assert result["errors"] == []

    def test_validate_transaction_negative_amount(self):
        result = validate_transaction(-100, "sent")
        assert result["valid"] is False
        assert "amount must be positive" in result["errors"]

    def test_validate_transaction_exceeds_limit(self):
        result = validate_transaction(1000000, "sent")
        assert result["valid"] is False
        assert "exceeds" in result["errors"][0]

    def test_validate_transaction_unknown_type(self):
        result = validate_transaction(500, "magic_beans")
        assert result["valid"] is False
        assert "unknown tx_type" in result["errors"][0]

    def test_validate_transaction_invalid_phone(self):
        result = validate_transaction(500, "sent", "invalid")
        assert result["valid"] is False
        assert "invalid Kenyan phone" in result["errors"][0]


# ═══════════════════════════════════════════════════════════════════
# M-PESA SMS PARSING TESTS (rust_bridge fallback)
# ═══════════════════════════════════════════════════════════════════


class TestMpesaSmsParsing:
    """Test M-Pesa SMS parsing with real-world examples."""

    def test_parse_sent_money(self):
        sms = "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN DOE 0722000000 on 1/1/24 at 2:30 PM. M-Pesa balance is Ksh1,234.00. Transaction cost, Ksh0.00."
        result = parse_mpesa_sms(sms)
        assert result["tx_code"] == "QJ12BC4DEF"
        assert result["amount"] == 500.0
        assert result["phone"] == "0722000000"
        assert result["tx_type"] == "sent"

    def test_parse_received_money(self):
        sms = "QJ12BC4DEF Confirmed. You received Ksh1,500.00 from JANE SMITH 0733000000 on 1/1/24 at 3:00 PM. New M-Pesa balance is Ksh2,734.00."
        result = parse_mpesa_sms(sms)
        assert result["amount"] == 1500.0
        assert result["phone"] == "0733000000"
        assert result["tx_type"] == "received"

    def test_parse_paybill(self):
        sms = "QJ12BC4DEF Confirmed. Ksh200.00 paid to KPLC PREPAID. Account number 12345678. on 1/1/24 at 4:00 PM. M-Pesa balance is Ksh1,034.00. Transaction cost, Ksh0.00."
        result = parse_mpesa_sms(sms)
        assert result["amount"] == 200.0
        assert result["tx_type"] == "paybill"

    def test_parse_withdraw(self):
        sms = "QJ12BC4DEF Confirmed. Ksh3000.00 withdrawn from AGENT JOHN 0722000000 on 1/1/24. M-Pesa balance is Ksh500.00."
        result = parse_mpesa_sms(sms)
        assert result["amount"] == 3000.0
        assert result["tx_type"] == "withdraw"

    def test_parse_deposit(self):
        sms = "QJ12BC4DEF Confirmed. Ksh5000.00 deposited to your M-Pesa account on 1/1/24. New M-Pesa balance is Ksh7000.00."
        result = parse_mpesa_sms(sms)
        assert result["amount"] == 5000.0
        assert result["tx_type"] == "deposit"

    def test_parse_buy_goods(self):
        sms = "QJ12BC4DEF Confirmed. Ksh150.00 paid to SUPERMARKET on 1/1/24. M-Pesa balance is Ksh350.00."
        result = parse_mpesa_sms(sms)
        assert result["amount"] == 150.0
        assert result["tx_type"] == "buygoods"

    def test_parse_unknown_format(self):
        sms = "Your M-Pesa PIN was changed successfully."
        result = parse_mpesa_sms(sms)
        assert result["tx_type"] == "unknown"

    def test_parse_amount_with_commas(self):
        sms = "QJ12BC4DEF Confirmed. Ksh12,500.00 sent to JOHN on 1/1/24. M-Pesa balance is Ksh50,000.00."
        result = parse_mpesa_sms(sms)
        assert result["amount"] == 12500.0

    def test_batch_parsing(self):
        sms_list = [
            "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN 0722000000 on 1/1/24. M-Pesa balance is Ksh1000.00.",
            "QJ12BC4DEF Confirmed. You received Ksh2000.00 from JANE 0733000000 on 1/1/24. M-Pesa balance is Ksh3000.00.",
        ]
        results = parse_mpesa_sms_batch(sms_list)
        assert len(results) == 2
        assert results[0]["tx_type"] == "sent"
        assert results[1]["tx_type"] == "received"


# ═══════════════════════════════════════════════════════════════════
# SYNC / CONFLICT RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestConflictResolution:
    """Test last-write-wins conflict resolution."""

    def test_local_wins_when_newer(self):
        local = [{"id": "1", "updated_at": "2024-01-02", "data": "local"}]
        remote = [{"id": "1", "updated_at": "2024-01-01", "data": "remote"}]
        result = resolve_conflicts(local, remote)
        assert len(result) == 1
        assert result[0]["_source"] == "local"

    def test_remote_wins_when_newer(self):
        local = [{"id": "1", "updated_at": "2024-01-01", "data": "local"}]
        remote = [{"id": "1", "updated_at": "2024-01-02", "data": "remote"}]
        result = resolve_conflicts(local, remote)
        assert result[0]["_source"] == "remote"

    def test_local_only_record(self):
        local = [{"id": "1", "updated_at": "2024-01-01"}]
        remote = []
        result = resolve_conflicts(local, remote)
        assert len(result) == 1
        assert result[0]["_source"] == "local"

    def test_remote_only_record(self):
        local = []
        remote = [{"id": "1", "updated_at": "2024-01-01"}]
        result = resolve_conflicts(local, remote)
        assert len(result) == 1
        assert result[0]["_source"] == "remote"

    def test_mixed_records(self):
        local = [
            {"id": "1", "updated_at": "2024-01-02"},
            {"id": "2", "updated_at": "2024-01-01"},
        ]
        remote = [
            {"id": "2", "updated_at": "2024-01-03"},
            {"id": "3", "updated_at": "2024-01-01"},
        ]
        result = resolve_conflicts(local, remote)
        assert len(result) == 3
        by_id = {r["id"]: r for r in result}
        assert by_id["1"]["_source"] == "local"
        assert by_id["2"]["_source"] == "remote"
        assert by_id["3"]["_source"] == "remote"


class TestDeltaOperations:
    """Test JSON delta computation and application."""

    def test_compute_delta_additions(self):
        base = json.dumps({"a": 1})
        target = json.dumps({"a": 1, "b": 2})
        delta = json.loads(compute_delta(base, target))
        assert delta == {"b": 2}

    def test_compute_delta_changes(self):
        base = json.dumps({"a": 1, "b": 2})
        target = json.dumps({"a": 1, "b": 5})
        delta = json.loads(compute_delta(base, target))
        assert delta == {"b": 5}

    def test_compute_delta_deletions(self):
        base = json.dumps({"a": 1, "b": 2})
        target = json.dumps({"a": 1})
        delta = json.loads(compute_delta(base, target))
        assert delta == {"b": None}

    def test_apply_delta_addition(self):
        base = json.dumps({"a": 1})
        delta = json.dumps({"b": 2})
        result = json.loads(apply_delta(base, delta))
        assert result == {"a": 1, "b": 2}

    def test_apply_delta_deletion(self):
        base = json.dumps({"a": 1, "b": 2})
        delta = json.dumps({"b": None})
        result = json.loads(apply_delta(base, delta))
        assert result == {"a": 1}

    def test_delta_roundtrip(self):
        base = json.dumps({"x": 10, "y": 20})
        target = json.dumps({"x": 10, "y": 30, "z": 40})
        delta = compute_delta(base, target)
        result = json.loads(apply_delta(base, delta))
        assert result == json.loads(target)


# ═══════════════════════════════════════════════════════════════════
# VECTOR OPERATIONS TESTS
# ═══════════════════════════════════════════════════════════════════


class TestVectorOperations:
    """Test cosine similarity, dot product, and normalization."""

    def test_cosine_similarity_identical(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-10

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-10

    def test_cosine_similarity_opposite(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-10

    def test_cosine_similarity_empty(self):
        assert cosine_similarity([], []) == 0.0

    def test_cosine_similarity_zero_vector(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_cosine_similarity_dimension_mismatch(self):
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0])

    def test_cosine_similarity_batch(self):
        query = [1.0, 0.0]
        candidates = [[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]]
        results = cosine_similarity_batch(query, candidates)
        assert len(results) == 3
        assert abs(results[0] - 1.0) < 1e-10
        assert abs(results[1]) < 1e-10
        assert abs(results[2] - (-1.0)) < 1e-10

    def test_batch_dot_product(self):
        query = [2.0, 3.0]
        candidates = [[1.0, 1.0], [0.0, 1.0]]
        results = batch_dot_product(query, candidates)
        assert results[0] == 5.0  # 2*1 + 3*1
        assert results[1] == 3.0  # 2*0 + 3*1

    def test_batch_normalize(self):
        vectors = [[3.0, 4.0], [1.0, 0.0]]
        result = batch_normalize(vectors)
        # [3,4] normalized: [0.6, 0.8]
        assert abs(result[0][0] - 0.6) < 1e-10
        assert abs(result[0][1] - 0.8) < 1e-10
        # [1,0] normalized: [1, 0]
        assert abs(result[1][0] - 1.0) < 1e-10
        assert abs(result[1][1]) < 1e-10

    def test_batch_normalize_zero_vector(self):
        result = batch_normalize([[0.0, 0.0]])
        assert result[0] == [0.0, 0.0]


class TestRustAvailability:
    """Test the Rust availability flag."""

    def test_is_rust_available_returns_bool(self):
        result = is_rust_available()
        assert isinstance(result, bool)
