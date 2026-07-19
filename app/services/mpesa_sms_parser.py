"""
M-Pesa SMS Parser — Extracts structured transaction data from M-Pesa SMS.

M-Pesa sends standardized SMS confirmations for every transaction.
This parser extracts transaction details from those messages, enabling
automatic bookkeeping from SMS without manual entry.

Supported M-Pesa SMS types:
- STK Push (Lipa Na M-Pesa Online)
- Send Money (Person-to-Person)
- Receive Money
- Withdraw (Agent)
- Pay Bill
- Buy Goods (Till)
- Airtime Purchase
- Fuliza (overdraft)

Academic Foundation:
- ECO 203: Economic Statistics — Transaction classification
- STA 241: Pattern matching under uncertainty
- NLP: Regex-based extraction with fuzzy matching

Data Flow:
    M-Pesa SMS → Parser → TransactionRecord → Pipeline → Intelligence

Example SMS formats:
    "QJ12BC4DEF Confirmed. Ksh500.00 sent to JOHN DOE 0722000000
     on 1/1/24 at 2:30 PM. M-Pesa balance is Ksh1,234.00.
     Transaction cost, Ksh0.00."

    "QJ12BC4DEF Confirmed. You received Ksh1,500.00 from
     JANE SMITH 0733000000 on 1/1/24 at 3:00 PM.
     New M-Pesa balance is Ksh2,734.00."

    "QJ12BC4DEF Confirmed. Ksh200.00 paid to KPLC PREPAID.
     Account number 12345678. on 1/1/24 at 4:00 PM.
     M-Pesa balance is Ksh1,034.00. Transaction cost, Ksh0.00."

Buyer: Self (automatic bookkeeping for Msaidizi app)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constants & Data Classes
# ════════════════════════════════════════════════════════════════════


class MpesaTransactionType(str, Enum):
    """Types of M-Pesa transactions."""
    SEND_MONEY = "send_money"
    RECEIVE_MONEY = "receive_money"
    PAY_BILL = "pay_bill"
    BUY_GOODS = "buy_goods"
    WITHDRAW = "withdraw"
    DEPOSIT = "deposit"
    AIRTIME = "airtime"
    STK_PUSH = "stk_push"
    FULIZA = "fuliza"
    REVERSE = "reverse"
    UNKNOWN = "unknown"


class TransactionDirection(str, Enum):
    """Direction of money flow relative to the user."""
    OUTGOING = "outgoing"  # User pays/sends
    INCOMING = "incoming"  # User receives
    NEUTRAL = "neutral"    # Balance inquiry, etc.


@dataclass
class MpesaTransaction:
    """Parsed M-Pesa transaction from SMS."""
    transaction_id: str = ""                    # e.g., "QJ12BC4DEF"
    transaction_type: MpesaTransactionType = MpesaTransactionType.UNKNOWN
    direction: TransactionDirection = TransactionDirection.NEUTRAL
    amount: float = 0.0                         # KES
    counterparty_name: str = ""                 # Other party's name
    counterparty_phone: str = ""                # Other party's phone (masked)
    account_number: str = ""                    # Pay bill account / till number
    merchant_name: str = ""                     # Business name for pay bill/till
    transaction_cost: float = 0.0               # M-Pesa fee
    balance_after: float = 0.0                  # M-Pesa balance after transaction
    timestamp: datetime | None = None        # Transaction datetime
    raw_sms: str = ""                           # Original SMS text
    confidence: float = 1.0                     # Parser confidence (0-1)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for pipeline consumption."""
        return {
            "transaction_id": self.transaction_id,
            "transaction_type": self.transaction_type.value,
            "direction": self.direction.value,
            "amount": self.amount,
            "counterparty_name": self.counterparty_name,
            "counterparty_phone": self.counterparty_phone,
            "account_number": self.account_number,
            "merchant_name": self.merchant_name,
            "transaction_cost": self.transaction_cost,
            "balance_after": self.balance_after,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "confidence": self.confidence,
            "source": "mpesa_sms",
            **self.metadata,
        }


# ════════════════════════════════════════════════════════════════════
# SMS Pattern Definitions
# ════════════════════════════════════════════════════════════════════

# Common amount pattern: "Ksh1,234.56" or "Ksh 1234.56"
_AMOUNT_RE = r"Ksh\s*([\d,]+(?:\.\d{2})?)"
# Transaction ID: alphanumeric, 10 chars
_TXN_ID_RE = r"([A-Z0-9]{10})"
# Phone number: 07XX or +254
_PHONE_RE = r"(\+?254\d{9}|07\d{8})"
# Date: "1/1/24" or "01/01/2024" or "1 January 2024"
_DATE_RE = r"(\d{1,2}/\d{1,2}/\d{2,4})"
# Time: "2:30 PM" or "14:30"
_TIME_RE = r"(\d{1,2}:\d{2}(?:\s*[APap][Mm])?)"
# Account number: digits, 5-20 chars
_ACCOUNT_RE = r"Account\s+(?:number\s+)?(\d{5,20})"

# ── Pattern matchers for each SMS type ──

_PATTERNS: list[tuple[str, MpesaTransactionType, TransactionDirection, list[str]]] = [
    # STK Push / Lipa Na M-Pesa Online
    (
        r"Confirmed\.\s*.*?" + _AMOUNT_RE + r"\s+sent to\s+(.+?)\s+on\s+",
        MpesaTransactionType.SEND_MONEY,
        TransactionDirection.OUTGOING,
        ["amount", "counterparty"],
    ),
    # Send Money (P2P)
    (
        r"Confirmed\.\s*" + _AMOUNT_RE + r"\s+sent to\s+(.+?)\s+" + _PHONE_RE + r"\s+on\s+",
        MpesaTransactionType.SEND_MONEY,
        TransactionDirection.OUTGOING,
        ["amount", "counterparty", "phone"],
    ),
    # Receive Money
    (
        r"Confirmed\.\s*[Yy]ou received\s+" + _AMOUNT_RE + r"\s+from\s+(.+?)\s+" + _PHONE_RE + r"\s+on\s+",
        MpesaTransactionType.RECEIVE_MONEY,
        TransactionDirection.INCOMING,
        ["amount", "counterparty", "phone"],
    ),
    # Receive Money (without phone)
    (
        r"Confirmed\.\s*[Yy]ou received\s+" + _AMOUNT_RE + r"\s+from\s+(.+?)\s+on\s+",
        MpesaTransactionType.RECEIVE_MONEY,
        TransactionDirection.INCOMING,
        ["amount", "counterparty"],
    ),
    # Pay Bill
    (
        r"Confirmed\.\s*" + _AMOUNT_RE + r"\s+paid to\s+(.+?)\.\s*" + _ACCOUNT_RE,
        MpesaTransactionType.PAY_BILL,
        TransactionDirection.OUTGOING,
        ["amount", "merchant", "account"],
    ),
    # Buy Goods (Till)
    (
        r"Confirmed\.\s*" + _AMOUNT_RE + r"\s+paid to\s+(.+?)\s+on\s+",
        MpesaTransactionType.BUY_GOODS,
        TransactionDirection.OUTGOING,
        ["amount", "merchant"],
    ),
    # Withdraw from agent
    (
        r"Confirmed\.\s*" + _AMOUNT_RE + r"\s+withdrawn from\s+(.+?)\s+on\s+",
        MpesaTransactionType.WITHDRAW,
        TransactionDirection.OUTGOING,
        ["amount", "merchant"],
    ),
    # Deposit at agent
    (
        r"Confirmed\.\s*" + _AMOUNT_RE + r"\s+deposited to\s+(.+?)\s+on\s+",
        MpesaTransactionType.DEPOSIT,
        TransactionDirection.INCOMING,
        ["amount", "merchant"],
    ),
    # Airtime purchase
    (
        r"Confirmed\.\s*" + _AMOUNT_RE + r"\s+(?:airtime|Airtime)\s+(?:purchase|bought)",
        MpesaTransactionType.AIRTIME,
        TransactionDirection.OUTGOING,
        ["amount"],
    ),
    # Fuliza overdraft
    (
        r"Confirmed\.\s*[Yy]ou have used\s+" + _AMOUNT_RE + r"\s+from Fuliza",
        MpesaTransactionType.FULIZA,
        TransactionDirection.INCOMING,
        ["amount"],
    ),
]

# Balance pattern: "M-Pesa balance is Ksh1,234.00" or "New M-Pesa balance is Ksh..."
_BALANCE_RE = r"(?:New\s+)?M-Pesa balance is\s+" + _AMOUNT_RE

# Transaction cost pattern: "Transaction cost, Ksh0.00" or "Transaction cost Ksh..."
_COST_RE = r"Transaction cost,?\s*" + _AMOUNT_RE


# ════════════════════════════════════════════════════════════════════
# Parser Implementation
# ════════════════════════════════════════════════════════════════════


def _parse_amount(amount_str: str) -> float:
    """Parse KES amount from string like '1,234.56'."""
    try:
        return float(amount_str.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _parse_datetime(date_str: str, time_str: str) -> datetime | None:
    """
    Parse M-Pesa date+time strings into datetime.

    Handles formats:
    - "1/1/24" + "2:30 PM"
    - "01/01/2024" + "14:30"
    """
    try:
        # Try common date formats
        for date_fmt in ["%d/%m/%y", "%d/%m/%Y", "%m/%d/%y", "%m/%d/%Y"]:
            try:
                parsed_date = datetime.strptime(date_str.strip(), date_fmt)
                break
            except ValueError:
                continue
        else:
            return None

        # Parse time
        time_str = time_str.strip().upper()
        for time_fmt in ["%I:%M %p", "%I:%M%p", "%H:%M"]:
            try:
                parsed_time = datetime.strptime(time_str, time_fmt)
                parsed_date = parsed_date.replace(
                    hour=parsed_time.hour,
                    minute=parsed_time.minute,
                )
                return parsed_date
            except ValueError:
                continue

        return parsed_date
    except Exception:
        return None


def _extract_transaction_id(sms: str) -> str:
    """Extract M-Pesa transaction ID (10-char alphanumeric code)."""
    match = re.search(_TXN_ID_RE, sms)
    return match.group(1) if match else ""


def _extract_balance(sms: str) -> float:
    """Extract M-Pesa balance after transaction."""
    match = re.search(_BALANCE_RE, sms)
    return _parse_amount(match.group(1)) if match else 0.0


def _extract_cost(sms: str) -> float:
    """Extract transaction cost/fee."""
    match = re.search(_COST_RE, sms)
    return _parse_amount(match.group(1)) if match else 0.0


def _extract_datetime(sms: str) -> datetime | None:
    """Extract transaction datetime from SMS."""
    date_match = re.search(r"on\s+" + _DATE_RE, sms)
    time_match = re.search(_TIME_RE, sms)
    if date_match and time_match:
        return _parse_datetime(date_match.group(1), time_match.group(1))
    elif date_match:
        return _parse_datetime(date_match.group(1), "12:00 PM")
    return None


def _mask_phone(phone: str) -> str:
    """
    Mask phone number for privacy: 0722000000 → 0722***000.

    Preserves first 4 and last 3 digits for counterparty matching
    while protecting PII.
    """
    if len(phone) >= 10:
        return phone[:4] + "***" + phone[-3:]
    return "***"


def parse_mpesa_sms(sms: str) -> MpesaTransaction:
    """
    Parse a single M-Pesa SMS into a structured transaction.

    Attempts to match the SMS against known M-Pesa message templates.
    Falls back to generic extraction if no template matches.

    Args:
        sms: Raw M-Pesa SMS text

    Returns:
        MpesaTransaction with extracted fields (confidence=0.5 if fallback)
    """
    sms = sms.strip()
    if not sms:
        return MpesaTransaction(raw_sms=sms, confidence=0.0)

    txn = MpesaTransaction(
        raw_sms=sms,
        transaction_id=_extract_transaction_id(sms),
        balance_after=_extract_balance(sms),
        transaction_cost=_extract_cost(sms),
        timestamp=_extract_datetime(sms),
    )

    # Try each pattern
    for pattern, txn_type, direction, field_names in _PATTERNS:
        match = re.search(pattern, sms, re.IGNORECASE)
        if match:
            txn.transaction_type = txn_type
            txn.direction = direction
            txn.confidence = 0.95

            # Extract named fields from match groups
            groups = match.groups()
            for i, field_name in enumerate(field_names):
                if i < len(groups):
                    value = groups[i]
                    if field_name == "amount":
                        txn.amount = _parse_amount(value)
                    elif field_name == "counterparty":
                        txn.counterparty_name = value.strip()
                    elif field_name == "phone":
                        txn.counterparty_phone = _mask_phone(value)
                    elif field_name == "merchant":
                        txn.merchant_name = value.strip()
                    elif field_name == "account":
                        txn.account_number = value.strip()

            break
    else:
        # Fallback: try to extract at least the amount
        amount_match = re.search(_AMOUNT_RE, sms)
        if amount_match:
            txn.amount = _parse_amount(amount_match.group(1))
            txn.confidence = 0.5
            txn.transaction_type = MpesaTransactionType.UNKNOWN

            # Guess direction from keywords
            sms_lower = sms.lower()
            if any(kw in sms_lower for kw in ["sent to", "paid to", "withdrawn"]):
                txn.direction = TransactionDirection.OUTGOING
            elif any(kw in sms_lower for kw in ["received", "deposited"]):
                txn.direction = TransactionDirection.INCOMING

    # Classify for intelligence pipeline
    _classify_transaction(txn)

    return txn


def _classify_transaction(txn: MpesaTransaction) -> None:
    """
    Classify parsed transaction for the intelligence pipeline.

    Adds category metadata based on transaction type and merchant
    information to enable downstream analytics.
    """
    category = "other"
    item_category = "services"

    if txn.transaction_type in (MpesaTransactionType.SEND_MONEY, MpesaTransactionType.RECEIVE_MONEY):
        category = "transfer"
        item_category = "transfer"
    elif txn.transaction_type == MpesaTransactionType.PAY_BILL:
        category = "bill_payment"
        # Classify common billers
        merchant_lower = txn.merchant_name.lower() if txn.merchant_name else ""
        if any(kw in merchant_lower for kw in ["kplc", "kenya power", "electricity"]):
            item_category = "utilities"
        elif any(kw in merchant_lower for kw in ["safaricom", "airtel", "telkom"]):
            item_category = "telecommunications"
        elif any(kw in merchant_lower for kw in ["nairobi water", "water"]):
            item_category = "utilities"
        elif any(kw in merchant_lower for kw in ["dstv", "gotv", "startimes"]):
            item_category = "entertainment"
        else:
            item_category = "services"
    elif txn.transaction_type == MpesaTransactionType.BUY_GOODS:
        category = "purchase"
        item_category = "retail"
    elif txn.transaction_type == MpesaTransactionType.WITHDRAW:
        category = "cash_withdrawal"
        item_category = "financial_services"
    elif txn.transaction_type == MpesaTransactionType.DEPOSIT:
        category = "cash_deposit"
        item_category = "financial_services"
    elif txn.transaction_type == MpesaTransactionType.AIRTIME:
        category = "airtime"
        item_category = "telecommunications"
    elif txn.transaction_type == MpesaTransactionType.FULIZA:
        category = "credit"
        item_category = "financial_services"

    txn.metadata["category"] = category
    txn.metadata["item_category"] = item_category


def parse_mpesa_sms_batch(sms_list: list[str]) -> list[MpesaTransaction]:
    """
    Parse a batch of M-Pesa SMS messages.

    Args:
        sms_list: List of raw M-Pesa SMS texts

    Returns:
        List of parsed transactions (skips empty/invalid messages)
    """
    results = []
    for sms in sms_list:
        if not sms or not sms.strip():
            continue
        try:
            txn = parse_mpesa_sms(sms)
            if txn.amount > 0:
                results.append(txn)
        except Exception as e:
            logger.warning(
                "mpesa_sms_parse_failed",
                error=str(e),
                sms_preview=sms[:50] if sms else "",
            )
    return results


def extract_mpesa_transactions_from_device(
    sms_list: list[str],
    user_id: str = "",
    device_id: str = "",
) -> list[dict[str, Any]]:
    """
    Parse M-Pesa SMS and format for the BiasharaSync pipeline.

    Converts parsed SMS into the AnonymizedTransaction format
    used by the Biashara Sync endpoint.

    Args:
        sms_list: Raw M-Pesa SMS messages
        user_id: User ID (for logging only, not in output)
        device_id: Device ID (for logging only)

    Returns:
        List of dicts compatible with AnonymizedTransaction schema
    """
    parsed = parse_mpesa_sms_batch(sms_list)
    transactions = []

    for txn in parsed:
        # Only include spending/income (not transfers between own accounts)
        if txn.transaction_type in (
            MpesaTransactionType.SEND_MONEY,
            MpesaTransactionType.PAY_BILL,
            MpesaTransactionType.BUY_GOODS,
            MpesaTransactionType.WITHDRAW,
            MpesaTransactionType.AIRTIME,
            MpesaTransactionType.RECEIVE_MONEY,
            MpesaTransactionType.DEPOSIT,
        ):
            # Map direction to transaction type for the pipeline
            txn_type = "SALE" if txn.direction == TransactionDirection.INCOMING else "PURCHASE"
            if txn.transaction_type in (
                MpesaTransactionType.WITHDRAW,
                MpesaTransactionType.DEPOSIT,
            ):
                txn_type = "EXPENSE"

            transactions.append({
                "type": txn_type,
                "category": txn.metadata.get("item_category", "other"),
                "amount": txn.amount,
                "quantity": 1,
                "timestamp": int(txn.timestamp.timestamp()) if txn.timestamp else 0,
                "confidence": txn.confidence,
                "payment_method": "mpesa",
                "metadata": {
                    "mpesa_txn_id": txn.transaction_id,
                    "mpesa_type": txn.transaction_type.value,
                    "counterparty": txn.counterparty_name or txn.merchant_name,
                    "transaction_cost": txn.transaction_cost,
                    "source": "mpesa_sms_parser",
                },
            })

    logger.info(
        "mpesa_batch_parsed",
        total_sms=len(sms_list),
        parsed=len(parsed),
        transactions=len(transactions),
        user_id=user_id[:8] + "..." if user_id else "",
    )

    return transactions


# ════════════════════════════════════════════════════════════════════
# Convenience: Singleton parser instance
# ════════════════════════════════════════════════════════════════════

mpesa_parser = parse_mpesa_sms
mpesa_batch_parser = parse_mpesa_sms_batch
mpesa_pipeline_adapter = extract_mpesa_transactions_from_device
