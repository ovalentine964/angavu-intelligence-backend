"""
Rust bridge — transparent fallback layer.

Imports the compiled Rust extension (`angavu_rust`) when available.
If the extension is not installed (e.g. during development or in environments
without a Rust toolchain), every function falls back to a pure-Python
implementation so the backend keeps working.

Usage:
    from app.services.rust_bridge import (
        encrypt_aes_gcm,
        decrypt_aes_gcm,
        generate_key,
        sha256_hash,
        argon2_hash,
        argon2_verify,
        validate_phone_ke,
        normalize_phone_ke,
        sanitize_input,
        sanitize_input_batch,
        parse_mpesa_sms,
        parse_mpesa_sms_batch,
        process_transactions_batch,
        validate_transaction,
        resolve_conflicts,
        compute_delta,
        apply_delta,
        cosine_similarity,
        cosine_similarity_batch,
        batch_dot_product,
        batch_normalize,
    )
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import secrets
from typing import Any

# ── Try importing the Rust extension ──────────────────────────────

_RUST_AVAILABLE = False

try:
    import angavu_rust as _rust  # type: ignore[import-untyped]

    _RUST_AVAILABLE = True
except ImportError:
    _rust = None  # type: ignore[assignment]


def is_rust_available() -> bool:
    """Return True if the compiled Rust extension is loaded."""
    return _RUST_AVAILABLE


# ═══════════════════════════════════════════════════════════════════
#  CRYPTO
# ═══════════════════════════════════════════════════════════════════


def encrypt_aes_gcm(plaintext: str, key_b64: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM. Returns base64(nonce ‖ ciphertext)."""
    if _RUST_AVAILABLE:
        return _rust.encrypt_aes_gcm(plaintext, key_b64)

    # Pure-Python fallback
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(key_b64)
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def decrypt_aes_gcm(ciphertext_b64: str, key_b64: str) -> str:
    """Decrypt AES-256-GCM ciphertext produced by *encrypt_aes_gcm*."""
    if _RUST_AVAILABLE:
        return _rust.decrypt_aes_gcm(ciphertext_b64, key_b64)

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(key_b64)
    data = base64.b64decode(ciphertext_b64)
    nonce, ct = data[:12], data[12:]
    pt = AESGCM(key).decrypt(nonce, ct, None)
    return pt.decode()


def generate_key(length: int = 32) -> str:
    """Generate a random key of *length* bytes, returned as base64."""
    if _RUST_AVAILABLE:
        return _rust.generate_key(length)
    return base64.b64encode(secrets.token_bytes(length)).decode()


def sha256_hash(input_str: str) -> str:
    """SHA-256 hex digest of *input_str*."""
    if _RUST_AVAILABLE:
        return _rust.sha256_hash(input_str)
    return hashlib.sha256(input_str.encode()).hexdigest()


def argon2_hash(password: str, memory_kib: int = 65536, iterations: int = 3, parallelism: int = 4) -> str:
    """Argon2id hash. Returns PHC-format string."""
    if _RUST_AVAILABLE:
        return _rust.argon2_hash(password, memory_kib, iterations, parallelism)

    import argon2

    return argon2.PasswordHasher(
        time_cost=iterations,
        memory_cost=memory_kib,
        parallelism=parallelism,
    ).hash(password)


def argon2_verify(password: str, phc_hash: str) -> bool:
    """Verify *password* against a PHC-format Argon2 hash."""
    if _RUST_AVAILABLE:
        return _rust.argon2_verify(password, phc_hash)

    import argon2

    try:
        return argon2.PasswordHasher().verify(phc_hash, password)
    except argon2.exceptions.VerifyMismatchError:
        return False


# ═══════════════════════════════════════════════════════════════════
#  PHONE VALIDATION
# ═══════════════════════════════════════════════════════════════════

_KE_PHONE_RE = re.compile(r"^(\+?254[017]\d{8}|0[017]\d{8})$")


def validate_phone_ke(phone: str) -> bool:
    """Return True if *phone* is a valid Kenyan number."""
    if _RUST_AVAILABLE:
        return _rust.validate_phone_ke(phone)
    return bool(_KE_PHONE_RE.match(phone))


def normalize_phone_ke(phone: str) -> str:
    """Normalize to 2547XXXXXXXX form. Raises ValueError on bad input."""
    if _RUST_AVAILABLE:
        return _rust.normalize_phone_ke(phone)

    if not validate_phone_ke(phone):
        raise ValueError(f"Invalid Kenyan phone number: {phone}")
    clean = re.sub(r"[^\d+]", "", phone)
    if clean.startswith("+254"):
        return clean[1:]
    if clean.startswith("254"):
        return clean
    if clean.startswith("0"):
        return "254" + clean[1:]
    raise ValueError(f"Cannot normalize: {phone}")


# ═══════════════════════════════════════════════════════════════════
#  INPUT SANITIZATION
# ═══════════════════════════════════════════════════════════════════

_SQL_KEYWORDS = re.compile(
    r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE)\b"
)
_SQL_COMMENT = re.compile(r"(?i)(--|/\*|\*/)")
_SQL_TAUTOLOGY = re.compile(r"(?i)(\b(OR|AND)\b\s+\d+\s*=\s*\d+)")


def sanitize_input(input_str: str) -> str:
    """Strip SQL injection, XSS, path traversal, and null bytes."""
    if _RUST_AVAILABLE:
        return _rust.sanitize_input(input_str)

    out = input_str.replace("\0", "")
    out = _SQL_KEYWORDS.sub("", out)
    out = _SQL_COMMENT.sub("", out)
    out = _SQL_TAUTOLOGY.sub("", out)
    out = out.replace("'", "").replace('"', "").replace("\\", "")
    out = out.replace(";", "")
    out = out.replace("<", "&lt;").replace(">", "&gt;")
    out = out.replace('"', "&quot;").replace("'", "&#x27;")
    out = re.sub(r"\.\./", "", out)
    out = re.sub(r"\s{3,}", "  ", out)
    return out


def sanitize_input_batch(inputs: list[str]) -> list[str]:
    """Sanitize a list of strings."""
    if _RUST_AVAILABLE:
        return _rust.sanitize_input_batch(inputs)
    return [sanitize_input(s) for s in inputs]


# ═══════════════════════════════════════════════════════════════════
#  TRANSACTION PROCESSING
# ═══════════════════════════════════════════════════════════════════


def process_transactions_batch(transactions: list[dict]) -> list[dict]:
    """Enrich a batch of transaction dicts with category, risk_score, flags."""
    if _RUST_AVAILABLE:
        return _rust.process_transactions_batch(transactions)

    results = []
    for tx in transactions:
        amount = tx.get("amount", 0)
        tx_type = tx.get("tx_type", "unknown")
        flags: list[str] = []
        risk = 0.0

        if amount > 70_000:
            flags.append("high_value")
            risk += 0.3

        cat_map = {
            "sent": "transfer_out",
            "send": "transfer_out",
            "received": "transfer_in",
            "receive": "transfer_in",
            "paybill": "bill_payment",
            "pay_bill": "bill_payment",
            "buygoods": "merchant_payment",
            "buy_goods": "merchant_payment",
            "till": "merchant_payment",
            "withdraw": "cash_withdrawal",
            "deposit": "cash_deposit",
            "loan": "credit",
            "fuliza": "credit",
            "kcb_mpesa": "credit",
        }
        category = cat_map.get(tx_type.lower(), "other")
        if category == "credit":
            risk += 0.2
            flags.append("credit")
        if category == "transfer_out" and amount > 50_000:
            risk += 0.1

        results.append(
            {
                "id": tx.get("id"),
                "amount": amount,
                "tx_type": tx_type,
                "category": category,
                "risk_score": min(risk, 1.0),
                "flags": flags,
            }
        )
    return results


def validate_transaction(
    amount: float,
    tx_type: str,
    phone: str | None = None,
    timestamp: str | None = None,
) -> dict:
    """Validate a transaction. Returns {"valid": bool, "errors": list[str]}."""
    if _RUST_AVAILABLE:
        return _rust.validate_transaction(amount, tx_type, phone, timestamp)

    errors: list[str] = []
    if amount <= 0:
        errors.append("amount must be positive")
    if amount > 999_999:
        errors.append("amount exceeds M-Pesa single-transaction limit (KES 999,999)")

    valid_types = {
        "sent", "received", "paybill", "buygoods", "withdraw", "deposit",
        "loan", "fuliza", "send", "receive", "pay_bill", "buy_goods",
    }
    if tx_type.lower() not in valid_types:
        errors.append(f"unknown tx_type: '{tx_type}'")

    if phone and not validate_phone_ke(phone):
        errors.append(f"invalid Kenyan phone number: {phone}")

    if timestamp is not None and not timestamp:
        errors.append("timestamp is empty")

    return {"valid": len(errors) == 0, "errors": errors}


def parse_mpesa_sms(sms: str) -> dict:
    """Parse a single M-Pesa SMS into a structured dict."""
    if _RUST_AVAILABLE:
        return _rust.parse_mpesa_sms(sms)

    # Lightweight Python fallback
    tx_code = None
    m = re.search(r"\b([A-Z0-9]{8,10})\b", sms)
    if m:
        tx_code = m.group(1)

    amount = None
    m = re.search(r"(?i)(?:KSH|KES)\s*([\d,]+(?:\.\d{1,2})?)", sms)
    if m:
        amount = float(m.group(1).replace(",", ""))

    phone = None
    m = re.search(r"(\+?254[17]\d{8}|0[17]\d{8})", sms)
    if m:
        phone = m.group(1)

    upper = sms.upper()
    if "SENT TO" in upper or "SEND MONEY" in upper:
        tx_type = "sent"
    elif "RECEIVED" in upper:
        tx_type = "received"
    elif "WITHDRAW" in upper:
        tx_type = "withdraw"
    elif "DEPOSIT" in upper:
        tx_type = "deposit"
    elif "PAY BILL" in upper or "PAYBILL" in upper:
        tx_type = "paybill"
    elif "BUY GOODS" in upper or "TILL NUMBER" in upper:
        tx_type = "buygoods"
    else:
        tx_type = "unknown"

    return {
        "tx_code": tx_code,
        "amount": amount,
        "phone": phone,
        "name": None,
        "tx_date": None,
        "balance": None,
        "tx_type": tx_type,
    }


def parse_mpesa_sms_batch(sms_list: list[str]) -> list[dict]:
    """Parse a batch of M-Pesa SMS strings."""
    if _RUST_AVAILABLE:
        return _rust.parse_mpesa_sms_batch(sms_list)
    return [parse_mpesa_sms(s) for s in sms_list]


# ═══════════════════════════════════════════════════════════════════
#  SYNC / CONFLICT RESOLUTION
# ═══════════════════════════════════════════════════════════════════


def resolve_conflicts(local_records: list[dict], remote_records: list[dict]) -> list[dict]:
    """Last-write-wins conflict resolution on record dicts with ``id`` and ``updated_at``."""
    if _RUST_AVAILABLE:
        return _rust.resolve_conflicts(local_records, remote_records)

    remote_map = {r["id"]: r for r in remote_records}
    seen: set[str] = set()
    resolved: list[dict] = []

    for rec in local_records:
        rid = rec["id"]
        seen.add(rid)
        if rid in remote_map:
            remote = remote_map[rid]
            if rec.get("updated_at", "") >= remote.get("updated_at", ""):
                winner = {**rec, "_source": "local"}
            else:
                winner = {**remote, "_source": "remote"}
            resolved.append(winner)
        else:
            resolved.append({**rec, "_source": "local"})

    for rec in remote_records:
        if rec["id"] not in seen:
            resolved.append({**rec, "_source": "remote"})

    return resolved


def compute_delta(base_json: str, target_json: str) -> str:
    """Compute a JSON delta (additions, changes, deletions as null)."""
    if _RUST_AVAILABLE:
        return _rust.compute_delta(base_json, target_json)

    base = json.loads(base_json)
    target = json.loads(target_json)
    delta: dict[str, Any] = {}

    for k, v in target.items():
        if base.get(k) != v:
            delta[k] = v
    for k in base:
        if k not in target:
            delta[k] = None

    return json.dumps(delta)


def apply_delta(base_json: str, delta_json: str) -> str:
    """Apply a delta to a base JSON object."""
    if _RUST_AVAILABLE:
        return _rust.apply_delta(base_json, delta_json)

    base = json.loads(base_json)
    delta = json.loads(delta_json)
    for k, v in delta.items():
        if v is None:
            base.pop(k, None)
        else:
            base[k] = v
    return json.dumps(base)


# ═══════════════════════════════════════════════════════════════════
#  VECTOR OPERATIONS
# ═══════════════════════════════════════════════════════════════════


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    if _RUST_AVAILABLE:
        return _rust.cosine_similarity(a, b)

    if len(a) != len(b):
        raise ValueError(f"Dimension mismatch: {len(a)} vs {len(b)}")
    if not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def cosine_similarity_batch(query: list[float], candidates: list[list[float]]) -> list[float]:
    """Cosine similarity of *query* against each candidate vector."""
    if _RUST_AVAILABLE:
        return _rust.cosine_similarity_batch(query, candidates)
    return [cosine_similarity(query, c) for c in candidates]


def batch_dot_product(query: list[float], candidates: list[list[float]]) -> list[float]:
    """Dot product of *query* against each candidate."""
    if _RUST_AVAILABLE:
        return _rust.batch_dot_product(query, candidates)
    return [sum(x * y for x, y in zip(query, c)) for c in candidates]


def batch_normalize(vectors: list[list[float]]) -> list[list[float]]:
    """L2-normalize each vector in the batch."""
    if _RUST_AVAILABLE:
        return _rust.batch_normalize(vectors)
    result = []
    for v in vectors:
        norm = math.sqrt(sum(x * x for x in v))
        result.append([x / norm for x in v] if norm > 0 else list(v))
    return result
