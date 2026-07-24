"""
Tests for the full M-Pesa SMS Parser (app.services.mpesa_sms_parser).

Tests structured transaction extraction from real M-Pesa SMS formats
including all transaction types, edge cases, and the pipeline adapter.
"""

import pytest
from datetime import datetime

try:
    from app.services.mpesa_sms_parser import (
        MpesaTransactionType,
        TransactionDirection,
        MpesaTransaction,
        parse_mpesa_sms,
        parse_mpesa_sms_batch,
        extract_mpesa_transactions_from_device,
        _parse_amount,
        _mask_phone,
        _extract_transaction_id,
        _extract_balance,
        _extract_cost,
    )
    MPESA_PARSER_AVAILABLE = True
except ImportError:
    MPESA_PARSER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not MPESA_PARSER_AVAILABLE,
    reason="mpesa_sms_parser import failed (missing scipy or other deps)"
)


# ═══════════════════════════════════════════════════════════════════
# SEND MONEY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestSendMoney:
    """Test parsing Send Money (P2P) SMS."""

    def test_send_money_with_phone(self):
        sms = (
            "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN DOE 0722000000 "
            "on 1/1/24 at 2:30 PM. M-Pesa balance is Ksh1,234.00. "
            "Transaction cost, Ksh0.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.SEND_MONEY
        assert txn.direction == TransactionDirection.OUTGOING
        assert txn.amount == 500.0
        assert txn.counterparty_name == "JOHN DOE"
        assert txn.counterparty_phone == "0722***000"
        assert txn.balance_after == 1234.0
        assert txn.transaction_cost == 0.0
        assert txn.confidence == 0.95

    def test_send_money_large_amount(self):
        sms = (
            "ABC1234567 Confirmed. Ksh15,000.00 sent to MAMA NINA 0733000111 "
            "on 15/6/26 at 10:00 AM. M-Pesa balance is Ksh25,000.00. "
            "Transaction cost, Ksh25.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.amount == 15000.0
        assert txn.counterparty_name == "MAMA NINA"
        assert txn.transaction_cost == 25.0

    def test_send_money_stk_push(self):
        """STK Push / Lipa Na M-Pesa Online format."""
        sms = (
            "XYZ9876543 Confirmed. Ksh1,200.00 sent to SAFARICOM PAYBILL "
            "on 10/3/24 at 4:15 PM. M-Pesa balance is Ksh800.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.SEND_MONEY
        assert txn.amount == 1200.0


# ═══════════════════════════════════════════════════════════════════
# RECEIVE MONEY TESTS
# ═══════════════════════════════════════════════════════════════════


class TestReceiveMoney:
    """Test parsing Receive Money SMS."""

    def test_receive_money_with_phone(self):
        sms = (
            "QJ12BC4DEF Confirmed. You received Ksh1,500.00 from "
            "JANE SMITH 0733000000 on 1/1/24 at 3:00 PM. "
            "New M-Pesa balance is Ksh2,734.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.RECEIVE_MONEY
        assert txn.direction == TransactionDirection.INCOMING
        assert txn.amount == 1500.0
        assert txn.counterparty_name == "JANE SMITH"
        assert txn.balance_after == 2734.0

    def test_receive_money_without_phone(self):
        sms = (
            "QJ12BC4DEF Confirmed. You received Ksh5,000.00 from "
            "COMPANY LTD on 5/3/24 at 9:00 AM. "
            "New M-Pesa balance is Ksh10,000.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.RECEIVE_MONEY
        assert txn.direction == TransactionDirection.INCOMING
        assert txn.amount == 5000.0
        assert txn.counterparty_name == "COMPANY LTD"


# ═══════════════════════════════════════════════════════════════════
# PAY BILL TESTS
# ═══════════════════════════════════════════════════════════════════


class TestPayBill:
    """Test parsing Pay Bill SMS."""

    def test_pay_bill_kplc(self):
        sms = (
            "QJ12BC4DEF Confirmed. Ksh200.00 paid to KPLC PREPAID. "
            "Account number 12345678. on 1/1/24 at 4:00 PM. "
            "M-Pesa balance is Ksh1,034.00. Transaction cost, Ksh0.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.PAY_BILL
        assert txn.direction == TransactionDirection.OUTGOING
        assert txn.amount == 200.0
        assert txn.merchant_name == "KPLC PREPAID"
        assert txn.account_number == "12345678"
        assert txn.metadata["category"] == "bill_payment"
        assert txn.metadata["item_category"] == "utilities"

    def test_pay_bill_safaricom(self):
        sms = (
            "ABC1234567 Confirmed. Ksh1,000.00 paid to SAFARICOM LIMITED. "
            "Account number 0722000000. on 15/1/24 at 10:00 AM. "
            "M-Pesa balance is Ksh2,000.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.metadata["item_category"] == "telecommunications"


# ═══════════════════════════════════════════════════════════════════
# BUY GOODS / TILL TESTS
# ═══════════════════════════════════════════════════════════════════


class TestBuyGoods:
    """Test parsing Buy Goods (Till) SMS."""

    def test_buy_goods(self):
        sms = (
            "QJ12BC4DEF Confirmed. Ksh150.00 paid to SUPERMARKET LTD "
            "on 1/1/24 at 5:00 PM. M-Pesa balance is Ksh350.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.BUY_GOODS
        assert txn.direction == TransactionDirection.OUTGOING
        assert txn.amount == 150.0
        assert txn.merchant_name == "SUPERMARKET LTD"
        assert txn.metadata["category"] == "purchase"


# ═══════════════════════════════════════════════════════════════════
# WITHDRAW / DEPOSIT TESTS
# ═══════════════════════════════════════════════════════════════════


class TestWithdrawDeposit:
    """Test parsing Withdraw and Deposit SMS."""

    def test_withdraw(self):
        sms = (
            "QJ12BC4DEF Confirmed. Ksh3,000.00 withdrawn from AGENT JOHN "
            "0722000000 on 1/1/24 at 6:00 PM. M-Pesa balance is Ksh500.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.WITHDRAW
        assert txn.direction == TransactionDirection.OUTGOING
        assert txn.amount == 3000.0
        assert txn.metadata["category"] == "cash_withdrawal"

    def test_deposit(self):
        sms = (
            "QJ12BC4DEF Confirmed. Ksh5,000.00 deposited to your M-Pesa "
            "account on 1/1/24. New M-Pesa balance is Ksh7,000.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.DEPOSIT
        assert txn.direction == TransactionDirection.INCOMING
        assert txn.amount == 5000.0
        assert txn.metadata["category"] == "cash_deposit"


# ═══════════════════════════════════════════════════════════════════
# AIRTIME / FULIZA TESTS
# ═══════════════════════════════════════════════════════════════════


class TestAirtimeFuliza:
    """Test parsing Airtime and Fuliza SMS."""

    def test_airtime_purchase(self):
        sms = (
            "QJ12BC4DEF Confirmed. Ksh100.00 Airtime purchase for 0722000000 "
            "on 1/1/24. M-Pesa balance is Ksh400.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.AIRTIME
        assert txn.direction == TransactionDirection.OUTGOING
        assert txn.amount == 100.0
        assert txn.metadata["category"] == "airtime"

    def test_fuliza(self):
        sms = (
            "QJ12BC4DEF Confirmed. You have used Ksh500.00 from Fuliza M-Pesa. "
            "M-Pesa balance is Ksh500.00."
        )
        txn = parse_mpesa_sms(sms)

        assert txn.transaction_type == MpesaTransactionType.FULIZA
        assert txn.direction == TransactionDirection.INCOMING
        assert txn.amount == 500.0
        assert txn.metadata["category"] == "credit"


# ═══════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and unusual inputs."""

    def test_empty_sms(self):
        txn = parse_mpesa_sms("")
        assert txn.confidence == 0.0
        assert txn.amount == 0.0

    def test_whitespace_only(self):
        txn = parse_mpesa_sms("   ")
        assert txn.confidence == 0.0

    def test_unknown_format_with_amount(self):
        sms = "Ksh200.00 was deducted from your account."
        txn = parse_mpesa_sms(sms)
        assert txn.amount == 200.0
        assert txn.transaction_type == MpesaTransactionType.UNKNOWN
        assert txn.confidence == 0.5

    def test_phone_masking(self):
        assert _mask_phone("0722000000") == "0722***000"
        assert _mask_phone("0733111222") == "0733***222"

    def test_phone_masking_short(self):
        assert _mask_phone("123") == "***"

    def test_parse_amount_with_commas(self):
        assert _parse_amount("1,234.56") == 1234.56
        assert _parse_amount("12,500") == 12500.0
        assert _parse_amount("500") == 500.0

    def test_parse_amount_invalid(self):
        assert _parse_amount("abc") == 0.0
        assert _parse_amount("") == 0.0

    def test_transaction_id_extraction(self):
        sms = "ABC1234567 Confirmed. Ksh100.00 sent to TEST."
        assert _extract_transaction_id(sms) == "ABC1234567"

    def test_transaction_id_missing(self):
        assert _extract_transaction_id("no id here") == ""

    def test_balance_extraction(self):
        sms = "M-Pesa balance is Ksh1,234.00"
        assert _extract_balance(sms) == 1234.0

    def test_balance_missing(self):
        assert _extract_balance("no balance info") == 0.0

    def test_cost_extraction(self):
        sms = "Transaction cost, Ksh25.00"
        assert _extract_cost(sms) == 25.0

    def test_cost_missing(self):
        assert _extract_cost("no cost info") == 0.0


# ═══════════════════════════════════════════════════════════════════
# BATCH & PIPELINE TESTS
# ═══════════════════════════════════════════════════════════════════


class TestBatchAndPipeline:
    """Test batch parsing and pipeline adapter."""

    def test_batch_skips_empty(self):
        sms_list = [
            "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN 0722000000 on 1/1/24. M-Pesa balance is Ksh1000.00.",
            "",
            "   ",
            "QJ12BC4DEF Confirmed. You received Ksh2000.00 from JANE 0733000000 on 1/1/24. M-Pesa balance is Ksh3000.00.",
        ]
        results = parse_mpesa_sms_batch(sms_list)
        assert len(results) == 2

    def test_batch_skips_zero_amount(self):
        sms_list = [
            "Some random text without amount.",
        ]
        results = parse_mpesa_sms_batch(sms_list)
        assert len(results) == 0

    def test_pipeline_adapter_output_format(self):
        sms_list = [
            "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN 0722000000 on 1/1/24 at 2:30 PM. M-Pesa balance is Ksh1000.00.",
        ]
        transactions = extract_mpesa_transactions_from_device(sms_list, user_id="test_user")

        assert len(transactions) == 1
        tx = transactions[0]
        assert tx["type"] == "PURCHASE"  # outgoing = PURCHASE
        assert tx["amount"] == 500.0
        assert tx["payment_method"] == "mpesa"
        assert tx["confidence"] == 0.95
        assert "mpesa_txn_id" in tx["metadata"]
        assert tx["metadata"]["source"] == "mpesa_sms_parser"

    def test_pipeline_adapter_incoming_is_sale(self):
        sms_list = [
            "QJ12BC4DEF Confirmed. You received Ksh1500.00 from JANE 0733000000 on 1/1/24 at 3:00 PM. M-Pesa balance is Ksh3000.00.",
        ]
        transactions = extract_mpesa_transactions_from_device(sms_list)
        assert len(transactions) == 1
        assert transactions[0]["type"] == "SALE"

    def test_to_dict_output(self):
        sms = (
            "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN DOE 0722000000 "
            "on 1/1/24 at 2:30 PM. M-Pesa balance is Ksh1,234.00. "
            "Transaction cost, Ksh0.00."
        )
        txn = parse_mpesa_sms(sms)
        d = txn.to_dict()

        assert d["transaction_type"] == "send_money"
        assert d["direction"] == "outgoing"
        assert d["amount"] == 500.0
        assert d["source"] == "mpesa_sms"


# ═══════════════════════════════════════════════════════════════════
# CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════════


class TestClassification:
    """Test transaction classification for the intelligence pipeline."""

    def test_send_money_classified_as_transfer(self):
        sms = "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN 0722000000 on 1/1/24. M-Pesa balance is Ksh1000.00."
        txn = parse_mpesa_sms(sms)
        assert txn.metadata["category"] == "transfer"
        assert txn.metadata["item_category"] == "transfer"

    def test_pay_bill_classified_by_merchant(self):
        # KPLC = utilities
        sms = "QJ12BC4DEF Confirmed. Ksh200.00 paid to KPLC PREPAID. Account number 12345678. on 1/1/24. M-Pesa balance is Ksh1000.00."
        txn = parse_mpesa_sms(sms)
        assert txn.metadata["item_category"] == "utilities"

    def test_buy_goods_classified_as_retail(self):
        sms = "QJ12BC4DEF Confirmed. Ksh150.00 paid to SUPERMARKET on 1/1/24. M-Pesa balance is Ksh500.00."
        txn = parse_mpesa_sms(sms)
        assert txn.metadata["category"] == "purchase"
        assert txn.metadata["item_category"] == "retail"
