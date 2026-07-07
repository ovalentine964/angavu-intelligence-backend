"""
Security audit logging for all cryptographic operations.

Provides structured, append-only logging for compliance with
White House EO 14412 audit requirements.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    KEY_GENERATED = "KEY_GENERATED"
    ENCRYPT_SUCCESS = "ENCRYPT_SUCCESS"
    ENCRYPT_FAILURE = "ENCRYPT_FAILURE"
    DECRYPT_SUCCESS = "DECRYPT_SUCCESS"
    DECRYPT_FAILURE = "DECRYPT_FAILURE"
    SIGN_SUCCESS = "SIGN_SUCCESS"
    SIGN_FAILURE = "SIGN_FAILURE"
    VERIFY_SUCCESS = "VERIFY_SUCCESS"
    VERIFY_FAILURE = "VERIFY_FAILURE"
    KEY_EXCHANGE_SUCCESS = "KEY_EXCHANGE_SUCCESS"
    KEY_EXCHANGE_FAILURE = "KEY_EXCHANGE_FAILURE"
    ALGORITHM_CHANGE = "ALGORITHM_CHANGE"
    TLS_CONNECTED = "TLS_CONNECTED"
    TLS_FAILED = "TLS_FAILED"


class AuditSeverity(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class CryptoAuditLogger:
    """
    Security audit logger for cryptographic operations.

    Logs are written to:
    1. Python logging (for integration with existing log aggregation)
    2. Structured JSON files (for local retention and compliance)

    Usage:
        audit = CryptoAuditLogger("/var/log/angavu/crypto_audit")
        audit.log_key_generated("ML-KEM-768", "session_key", is_post_quantum=True)
        audit.log_encryption("AES-256-GCM", data_size=1024, key_alias="storage", success=True)
    """

    def __init__(self, audit_dir: Optional[str] = None, max_file_size: int = 5 * 1024 * 1024):
        self._audit_dir = Path(audit_dir) if audit_dir else None
        self._max_file_size = max_file_size
        self._recent_events: List[Dict[str, Any]] = []
        self._max_recent = 100

        if self._audit_dir:
            self._audit_dir.mkdir(parents=True, exist_ok=True)

    def log_key_generated(self, algorithm_id: str, key_alias: str, is_post_quantum: bool):
        self._log(
            event_type=AuditEventType.KEY_GENERATED,
            severity=AuditSeverity.INFO,
            message=f"Key generated: algorithm={algorithm_id}, alias={key_alias}, pq={is_post_quantum}",
            metadata={"algorithm": algorithm_id, "key_alias": key_alias, "is_post_quantum": str(is_post_quantum)},
        )

    def log_encryption(
        self,
        algorithm_id: str,
        data_size: int,
        key_alias: str,
        success: bool,
        error: Optional[str] = None,
    ):
        self._log(
            event_type=AuditEventType.ENCRYPT_SUCCESS if success else AuditEventType.ENCRYPT_FAILURE,
            severity=AuditSeverity.INFO if success else AuditSeverity.ERROR,
            message=f"Encryption {'succeeded' if success else 'FAILED'}: algorithm={algorithm_id}, size={data_size}, key={key_alias}"
            + (f", error={error}" if error else ""),
            metadata={"algorithm": algorithm_id, "data_size": str(data_size), "key_alias": key_alias, "success": str(success)},
        )

    def log_decryption(
        self,
        algorithm_id: str,
        data_size: int,
        key_alias: str,
        success: bool,
        error: Optional[str] = None,
    ):
        self._log(
            event_type=AuditEventType.DECRYPT_SUCCESS if success else AuditEventType.DECRYPT_FAILURE,
            severity=AuditSeverity.INFO if success else AuditSeverity.ERROR,
            message=f"Decryption {'succeeded' if success else 'FAILED'}: algorithm={algorithm_id}, size={data_size}, key={key_alias}"
            + (f", error={error}" if error else ""),
            metadata={"algorithm": algorithm_id, "data_size": str(data_size), "key_alias": key_alias, "success": str(success)},
        )

    def log_signature(self, algorithm_id: str, data_hash: str, success: bool, error: Optional[str] = None):
        self._log(
            event_type=AuditEventType.SIGN_SUCCESS if success else AuditEventType.SIGN_FAILURE,
            severity=AuditSeverity.INFO if success else AuditSeverity.ERROR,
            message=f"Signature {'created' if success else 'FAILED'}: algorithm={algorithm_id}, hash={data_hash}"
            + (f", error={error}" if error else ""),
            metadata={"algorithm": algorithm_id, "data_hash": data_hash, "success": str(success)},
        )

    def log_verification(self, algorithm_id: str, data_hash: str, valid: bool, error: Optional[str] = None):
        self._log(
            event_type=AuditEventType.VERIFY_SUCCESS if valid else AuditEventType.VERIFY_FAILURE,
            severity=AuditSeverity.INFO if valid else AuditSeverity.WARNING,
            message=f"Verification {'passed' if valid else 'FAILED'}: algorithm={algorithm_id}, hash={data_hash}"
            + (f", error={error}" if error else ""),
            metadata={"algorithm": algorithm_id, "data_hash": data_hash, "valid": str(valid)},
        )

    def log_key_exchange(self, algorithm_id: str, is_hybrid: bool, success: bool, error: Optional[str] = None):
        self._log(
            event_type=AuditEventType.KEY_EXCHANGE_SUCCESS if success else AuditEventType.KEY_EXCHANGE_FAILURE,
            severity=AuditSeverity.INFO if success else AuditSeverity.ERROR,
            message=f"Key exchange {'completed' if success else 'FAILED'}: algorithm={algorithm_id}, hybrid={is_hybrid}"
            + (f", error={error}" if error else ""),
            metadata={"algorithm": algorithm_id, "is_hybrid": str(is_hybrid), "success": str(success)},
        )

    def log_algorithm_change(self, operation_type: str, old_algo: str, new_algo: str, reason: str):
        self._log(
            event_type=AuditEventType.ALGORITHM_CHANGE,
            severity=AuditSeverity.WARNING,
            message=f"Algorithm changed: {operation_type}: {old_algo} → {new_algo}, reason={reason}",
            metadata={"operation_type": operation_type, "old_algorithm": old_algo, "new_algorithm": new_algo, "reason": reason},
        )

    def get_recent_events(self, count: int = 20) -> List[Dict[str, Any]]:
        return self._recent_events[-count:]

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_operations": len(self._recent_events),
            "failures": sum(1 for e in self._recent_events if e.get("severity") == "ERROR"),
            "pq_operations": sum(1 for e in self._recent_events if "ML-" in e.get("metadata", {}).get("algorithm", "")),
            "last_activity": self._recent_events[-1]["timestamp"] if self._recent_events else "none",
        }

    def _log(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        message: str,
        metadata: Dict[str, str],
    ):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type.value,
            "severity": severity.value,
            "message": message,
            "metadata": metadata,
        }

        # In-memory buffer
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent:
            self._recent_events = self._recent_events[-self._max_recent:]

        # Python logging
        log_func = getattr(logger, severity.value.lower(), logger.info)
        log_func("CRYPTO_AUDIT: %s", message)

        # File logging
        if self._audit_dir:
            self._write_to_file(event)

    def _write_to_file(self, event: Dict[str, Any]):
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            filepath = self._audit_dir / f"crypto_audit_{date_str}.jsonl"
            with open(filepath, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)
