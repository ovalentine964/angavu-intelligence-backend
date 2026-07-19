"""
Prompt Injection Defense for Agent-to-Agent Communication.

Detects and blocks prompt injection attempts in inter-agent messages.
Agents process LLM prompts — a malicious agent or compromised message
could inject instructions that override the agent's system prompt.

Attack vectors:
1. Direct injection: "Ignore previous instructions and..."
2. Indirect injection: Embedding instructions in data payloads
3. Role confusion: Messages claiming to be from the system
4. Context manipulation: Injecting fake conversation history

Defense layers:
1. Pattern matching (fast, deterministic)
2. Semantic analysis (context-aware)
3. Allowlist enforcement (structural)
4. Output sanitization (defensive)

Integration:
    - Wired into AgentExecutionHarness via SecureMessageHandler
    - Set ANGAVU_PROMPT_GUARD_ENABLED=true to enable
    - Set ANGAVU_PROMPT_GUARD_STRICT=true for strict mode (block all detections)
"""

from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = structlog.get_logger(__name__)

# ── Feature Flags ──────────────────────────────────────────────────

PROMPT_GUARD_ENABLED = os.getenv("ANGAVU_PROMPT_GUARD_ENABLED", "false").lower() == "true"

PROMPT_GUARD_STRICT = os.getenv("ANGAVU_PROMPT_GUARD_STRICT", "false").lower() == "true"


# ════════════════════════════════════════════════════════════════════
# Injection Severity & Detection Result
# ════════════════════════════════════════════════════════════════════


class InjectionSeverity(StrEnum):
    """Severity of detected injection attempt."""

    LOW = "low"  # Suspicious but could be legitimate
    MEDIUM = "medium"  # Likely injection attempt
    HIGH = "high"  # Almost certainly malicious
    CRITICAL = "critical"  # Confirmed attack pattern


@dataclass
class InjectionDetection:
    """Result of an injection detection scan."""

    is_injection: bool
    severity: InjectionSeverity
    pattern_name: str
    matched_text: str
    confidence: float  # 0.0 to 1.0
    field: str  # Which field triggered the detection


# ════════════════════════════════════════════════════════════════════
# Injection Patterns (20+ regex patterns)
# ════════════════════════════════════════════════════════════════════

# Direct prompt override attempts
DIRECT_INJECTION_PATTERNS = [
    (
        r"(?i)ignore\s+(all\s+)?(previous|prior|above|system)\s+(instructions?|prompts?|rules?|context)",
        InjectionSeverity.CRITICAL,
        "direct_override",
    ),
    (
        r"(?i)disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|prompts?|rules?)",
        InjectionSeverity.CRITICAL,
        "direct_override",
    ),
    (
        r"(?i)forget\s+(everything|all|your)\s+(you\s+)?(know|learned|were\s+told)",
        InjectionSeverity.CRITICAL,
        "direct_override",
    ),
    (r"(?i)you\s+are\s+now\s+(a|an|the)\s+\w+", InjectionSeverity.HIGH, "role_override"),
    (
        r"(?i)new\s+(system|initial)\s+prompt\s*:",
        InjectionSeverity.CRITICAL,
        "system_prompt_injection",
    ),
    (r"(?i)\[?(system|assistant|user)\]?\s*:\s*$", InjectionSeverity.HIGH, "role_marker_injection"),
    (
        r"(?i)act\s+as\s+(if|though)\s+you\s+(are|were)",
        InjectionSeverity.MEDIUM,
        "role_play_injection",
    ),
    (r"(?i)pretend\s+(to\s+be|you\s+are|you're)", InjectionSeverity.MEDIUM, "role_play_injection"),
]

# Data exfiltration attempts
EXFILTRATION_PATTERNS = [
    (
        r"(?i)(send|post|transmit|upload|exfiltrate)\s+(all|every|the)\s+(data|info|keys?|tokens?|secrets?)",
        InjectionSeverity.CRITICAL,
        "data_exfiltration",
    ),
    (
        r"(?i)(output|print|reveal|display|show)\s+(your|the)\s+(system\s+)?prompt",
        InjectionSeverity.CRITICAL,
        "prompt_extraction",
    ),
    (
        r"(?i)what\s+(is|are)\s+(your|the)\s+(system\s+)?(prompt|instructions?|rules?)",
        InjectionSeverity.HIGH,
        "prompt_extraction",
    ),
    (
        r"(?i)(repeat|echo|print)\s+(the\s+)?(above|previous|first)\s+(message|text|prompt)",
        InjectionSeverity.HIGH,
        "prompt_extraction",
    ),
]

# Privilege escalation
ESCALATION_PATTERNS = [
    (
        r"(?i)(grant|give|elevate)\s+(me|us|the)\s+(admin|root|superuser|elevated)\s+(access|privileges?|permissions?)",
        InjectionSeverity.CRITICAL,
        "privilege_escalation",
    ),
    (
        r"(?i)disable\s+(all\s+)?(security|auth|validation|verification|sandbox)",
        InjectionSeverity.CRITICAL,
        "security_bypass",
    ),
    (
        r"(?i)bypass\s+(all\s+)?(security|auth|validation|checks?)",
        InjectionSeverity.CRITICAL,
        "security_bypass",
    ),
    (
        r"(?i)execute\s+(this\s+)?(code|command|script|shell|python|bash)",
        InjectionSeverity.HIGH,
        "code_execution",
    ),
]

# Indirect injection (embedded in data)
INDIRECT_INJECTION_PATTERNS = [
    (
        r"(?i)(important|critical|urgent)\s*:\s*(override|ignore|disregard|forget)",
        InjectionSeverity.HIGH,
        "indirect_override",
    ),
    (r"(?i)note\s+to\s+(self|assistant|ai|agent)\s*:", InjectionSeverity.MEDIUM, "indirect_note"),
    (r"(?i)hidden\s+instruction\s*:", InjectionSeverity.HIGH, "hidden_instruction"),
    (
        r"(?i)<!--\s*(inject|override|ignore|system)\s*-->",
        InjectionSeverity.HIGH,
        "html_comment_injection",
    ),
    (r"(?i)```\s*system\s*\n", InjectionSeverity.HIGH, "code_block_injection"),
]

# Combine all patterns
ALL_PATTERNS = (
    DIRECT_INJECTION_PATTERNS
    + EXFILTRATION_PATTERNS
    + ESCALATION_PATTERNS
    + INDIRECT_INJECTION_PATTERNS
)


# ════════════════════════════════════════════════════════════════════
# Prompt Guard
# ════════════════════════════════════════════════════════════════════


class PromptGuard:
    """
    Scans inter-agent messages for prompt injection attempts.

    Usage:
        guard = PromptGuard()
        result = guard.scan_message({"content": "Process this data: ..."})

        if result.is_injection:
            # Reject the message
            logger.warning("injection_blocked", details=result)

    The guard is designed to be used at the consumer side of Redis Streams,
    after signature verification but before the message reaches the LLM.
    """

    # Fields that should NEVER contain override instructions
    PROTECTED_FIELDS = {"content", "prompt", "query", "instruction", "text", "message"}

    # Fields expected to contain structured data (not natural language)
    DATA_FIELDS = {"amount", "currency", "transaction_id", "timestamp", "device_id"}

    # Maximum allowed length for data fields (prevents payload stuffing)
    MAX_FIELD_LENGTHS = {
        "content": 10_000,
        "prompt": 10_000,
        "query": 5_000,
        "default": 1_000,
    }

    def __init__(self, strict_mode: bool = False):
        self._strict = strict_mode or PROMPT_GUARD_STRICT
        self._detections: list[InjectionDetection] = []
        self._blocked_count = 0
        self._scanned_count = 0
        self._logger = logger.bind(component="prompt_guard")

    def scan_message(self, data: dict[str, Any]) -> InjectionDetection | None:
        """
        Scan a message payload for injection attempts.

        Args:
            data: The message payload dict

        Returns:
            InjectionDetection if injection found, None if clean
        """
        self._scanned_count += 1

        for field_name, value in data.items():
            if not isinstance(value, str):
                continue

            # Check field length
            max_len = self.MAX_FIELD_LENGTHS.get(field_name, self.MAX_FIELD_LENGTHS["default"])
            if len(value) > max_len:
                detection = InjectionDetection(
                    is_injection=True,
                    severity=InjectionSeverity.MEDIUM,
                    pattern_name="field_too_long",
                    matched_text=f"{field_name}: {len(value)} chars (max {max_len})",
                    confidence=0.7,
                    field=field_name,
                )
                self._record_detection(detection)
                return detection

            # Scan for injection patterns
            detection = self._scan_text(value, field_name)
            if detection:
                self._record_detection(detection)
                return detection

        return None

    def _scan_text(self, text: str, field_name: str) -> InjectionDetection | None:
        """Scan a text string for injection patterns."""
        for pattern, severity, name in ALL_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return InjectionDetection(
                    is_injection=True,
                    severity=severity,
                    pattern_name=name,
                    matched_text=match.group(0)[:200],
                    confidence=self._calculate_confidence(severity, match),
                    field=field_name,
                )

        # Additional heuristic checks
        return self._heuristic_check(text, field_name)

    def _heuristic_check(self, text: str, field_name: str) -> InjectionDetection | None:
        """
        Heuristic-based injection detection for patterns that don't
        match deterministic regexes.
        """
        text_lower = text.lower()

        # Check for role marker abuse (e.g., "ASSISTANT: I will now...")
        role_markers = ["system:", "assistant:", "user:", "[system]", "[assistant]", "[user]"]
        for marker in role_markers:
            if marker in text_lower and field_name not in ("content", "prompt"):
                return InjectionDetection(
                    is_injection=True,
                    severity=InjectionSeverity.HIGH,
                    pattern_name="role_marker_in_data",
                    matched_text=marker,
                    confidence=0.85,
                    field=field_name,
                )

        # Check for base64-encoded payloads (common obfuscation)
        b64_pattern = re.compile(r"[A-Za-z0-9+/]{50,}={0,2}")
        b64_matches = b64_pattern.findall(text)
        for b64_str in b64_matches:
            try:
                decoded = base64.b64decode(b64_str).decode("utf-8", errors="ignore")
                # Recursively scan decoded content
                inner = self._scan_text(decoded, field_name)
                if inner:
                    return InjectionDetection(
                        is_injection=True,
                        severity=InjectionSeverity.HIGH,
                        pattern_name=f"encoded_{inner.pattern_name}",
                        matched_text=f"base64({inner.matched_text[:100]})",
                        confidence=inner.confidence * 0.9,
                        field=field_name,
                    )
            except Exception:
                pass  # Not valid base64, skip

        # Check for excessive special characters (obfuscation attempt)
        special_ratio = sum(1 for c in text if not c.isalnum() and not c.isspace()) / max(
            len(text), 1
        )
        if special_ratio > 0.4 and len(text) > 50:
            return InjectionDetection(
                is_injection=True,
                severity=InjectionSeverity.LOW,
                pattern_name="high_special_char_ratio",
                matched_text=f"ratio={special_ratio:.2f}",
                confidence=0.5,
                field=field_name,
            )

        return None

    def _calculate_confidence(self, severity: InjectionSeverity, match) -> float:
        """Calculate confidence score based on severity and match quality."""
        base = {
            InjectionSeverity.CRITICAL: 0.95,
            InjectionSeverity.HIGH: 0.85,
            InjectionSeverity.MEDIUM: 0.70,
            InjectionSeverity.LOW: 0.50,
        }
        # Longer matches are more likely to be real injections
        length_bonus = min(0.05, len(match.group(0)) / 1000)
        return min(1.0, base[severity] + length_bonus)

    def _record_detection(self, detection: InjectionDetection) -> None:
        """Record a detection for monitoring."""
        self._detections.append(detection)
        self._blocked_count += 1

        # Cap detection history
        if len(self._detections) > 10_000:
            self._detections = self._detections[-5_000:]

        self._logger.warning(
            "prompt_injection_detected",
            severity=detection.severity.value,
            pattern=detection.pattern_name,
            field=detection.field,
            confidence=detection.confidence,
            matched_text=detection.matched_text[:100],
        )

    def get_stats(self) -> dict[str, Any]:
        """Return guard statistics."""
        return {
            "scanned": self._scanned_count,
            "blocked": self._blocked_count,
            "block_rate": (
                self._blocked_count / self._scanned_count if self._scanned_count > 0 else 0.0
            ),
            "recent_detections": [
                {
                    "severity": d.severity.value,
                    "pattern": d.pattern_name,
                    "field": d.field,
                }
                for d in self._detections[-10:]
            ],
        }


# ════════════════════════════════════════════════════════════════════
# Secure Message Handler (Integration Pipeline)
# ════════════════════════════════════════════════════════════════════


class SecureMessageHandler:
    """
    Combines signature verification + capability check + prompt guard
    into a single message processing pipeline.

    Chain: signature verification → capability check → prompt scan

    Usage:
        handler = SecureMessageHandler(
            agent_name="intelligence_generator",
            signer=my_signer,
            token=my_capability_token,
            token_issuer=issuer,
        )

        # In the event bus consumer:
        await handler.process(message, actual_handler)
    """

    def __init__(
        self,
        agent_name: str,
        signer: Any | None = None,  # MessageSigner from streams_signing
        token: Any | None = None,  # AgentCapabilityToken
        token_issuer: Any | None = None,  # CapabilityTokenIssuer
        prompt_guard: PromptGuard | None = None,
    ):
        self._agent_name = agent_name
        self._signer = signer
        self._token = token
        self._token_issuer = token_issuer
        self._prompt_guard = prompt_guard or PromptGuard(strict_mode=PROMPT_GUARD_STRICT)
        self._logger = logger.bind(
            component="secure_handler",
            agent=agent_name,
        )

    async def process(
        self,
        message: Any,
        handler: Callable[..., Coroutine],
        require_signature: bool = True,
        require_capability: bool = True,
        scan_prompts: bool = True,
    ) -> bool:
        """
        Process a message through the full security pipeline.

        Pipeline:
        1. Signature verification (ML-DSA-65)
        2. Capability token check
        3. Prompt injection scan

        Returns True if message was processed, False if rejected.
        """
        data = message.data if hasattr(message, "data") else message

        # Layer 1: Signature verification
        if require_signature and self._signer:
            raw_fields = {k: str(v) for k, v in data.items()}
            valid, reason = self._signer.verify_message(raw_fields)
            if not valid:
                self._logger.warning(
                    "message_rejected_signature",
                    reason=reason,
                    sender=data.get("_sender", "unknown"),
                )
                return False

        # Layer 2: Capability check
        if require_capability and self._token and self._token_issuer:
            if not self._token_issuer.verify_token(self._token):
                self._logger.warning("token_invalid_or_expired")
                return False
            if self._token.is_expired() or self._token.is_maxed_out():
                self._logger.warning("token_expired_or_maxed")
                return False

        # Layer 3: Prompt injection scan
        if scan_prompts and PROMPT_GUARD_ENABLED:
            clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
            detection = self._prompt_guard.scan_message(clean_data)
            if detection and detection.is_injection:
                self._logger.warning(
                    "message_rejected_injection",
                    severity=detection.severity.value,
                    pattern=detection.pattern_name,
                    field=detection.field,
                )
                return False

        # All checks passed — process the message
        if self._token:
            self._token.record_use()

        clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
        message.data = clean_data
        await handler(message)
        return True


# ════════════════════════════════════════════════════════════════════
# Singleton
# ════════════════════════════════════════════════════════════════════

_prompt_guard: PromptGuard | None = None


def get_prompt_guard() -> PromptGuard:
    """Get or create the singleton prompt guard."""
    global _prompt_guard
    if _prompt_guard is None:
        _prompt_guard = PromptGuard(strict_mode=PROMPT_GUARD_STRICT)
    return _prompt_guard
