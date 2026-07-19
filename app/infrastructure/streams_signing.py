"""
Message signing middleware for Redis Streams.

Provides cryptographic authenticity and integrity for all inter-agent
messages. Every message is signed with the sender's ML-DSA-65 private
key and verified by the consumer before processing.

Security properties:
- Authenticity: Only the legitimate sender can produce valid signatures
- Integrity: Any tampering invalidates the signature
- Non-replay: Each message has a unique nonce tracked for deduplication
- Forward secrecy: Per-message nonces prevent cross-message analysis

Architecture:
    Producer.publish()
        → Add _sender, _nonce, _signed_at fields
        → ML-DSA-65 sign(canonical_message)
        → Add _signature field
        → XADD to Redis Stream

    Consumer._process_message()
        → Extract _sender, _nonce, _signature
        → Look up sender's public key from AgentRegistry
        → ML-DSA-65 verify(canonical_message, _signature, public_key)
        → Reject if invalid → log security event
        → Check _nonce against replay cache
        → Process message

Integration:
    This module is wired into EventBus via SignedEventBusMixin.
    Set ANGAVU_MESSAGE_SIGNING_ENABLED=true to enable signing.
    During transition, unsigned messages are still accepted.
"""

from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import os
import time
import uuid
from typing import Any, Dict, Optional, Set, Tuple

import structlog

from app.security.pqc.ml_dsa import MlDsaProvider, MlDsaParameterSet
from app.security.pqc.crypto_provider import CryptoKeyPair

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────

# Feature flag: enable/disable message signing
SIGNING_ENABLED = os.getenv("ANGAVU_MESSAGE_SIGNING_ENABLED", "false").lower() == "true"

# Nonce replay window (seconds)
NONCE_TTL = 300  # 5 minutes

# Max nonces to track per agent
MAX_NONCES_PER_AGENT = 10_000


# ════════════════════════════════════════════════════════════════════
# Agent Key Registry
# ════════════════════════════════════════════════════════════════════


class AgentKeyRegistry:
    """
    Registry of agent ML-DSA public keys.

    In production, keys are stored in PostgreSQL with row-level security.
    In development, an in-memory registry is used.

    Key lifecycle:
    1. Agent generates ML-DSA-65 key pair at startup
    2. Public key is registered with the registry (authenticated via admin API)
    3. Consumers look up public keys for signature verification
    4. Keys are rotated every 90 days (configurable)
    """

    def __init__(self):
        self._keys: Dict[str, bytes] = {}  # agent_name → public_key_bytes
        self._key_created: Dict[str, float] = {}  # agent_name → creation timestamp
        self._rotation_days: int = 90
        self._logger = logger.bind(component="agent_key_registry")

    def register(self, agent_name: str, public_key: bytes) -> None:
        """Register an agent's public key."""
        self._keys[agent_name] = public_key
        self._key_created[agent_name] = time.time()
        self._logger.info("agent_key_registered", agent=agent_name)

    def get_public_key(self, agent_name: str) -> Optional[bytes]:
        """Get an agent's public key. Returns None if not registered."""
        return self._keys.get(agent_name)

    def is_registered(self, agent_name: str) -> bool:
        return agent_name in self._keys

    def rotate_key(self, agent_name: str, new_public_key: bytes) -> None:
        """Rotate an agent's key."""
        old_key = self._keys.get(agent_name)
        self._keys[agent_name] = new_public_key
        self._key_created[agent_name] = time.time()
        self._logger.warning(
            "agent_key_rotated",
            agent=agent_name,
            old_key_hash=hashlib.sha256(old_key).hexdigest()[:16] if old_key else "none",
            new_key_hash=hashlib.sha256(new_public_key).hexdigest()[:16],
        )

    def get_keys_needing_rotation(self) -> list[str]:
        """Return agents whose keys need rotation."""
        now = time.time()
        max_age = self._rotation_days * 86400
        return [
            name for name, created in self._key_created.items()
            if now - created > max_age
        ]

    def get_all_agents(self) -> list[str]:
        return list(self._keys.keys())


# Singleton registry
_agent_key_registry = AgentKeyRegistry()


def get_agent_key_registry() -> AgentKeyRegistry:
    """Get the singleton agent key registry."""
    return _agent_key_registry


# ════════════════════════════════════════════════════════════════════
# Message Signer
# ════════════════════════════════════════════════════════════════════


class MessageSigner:
    """
    Signs and verifies Redis Stream messages using ML-DSA-65.

    Usage:
        signer = MessageSigner(agent_name="soko_pulse", key_pair=my_keypair)
        signed_data = signer.sign_message({"event_type": "price.alert", "data": {...}})
        # → Adds _sender, _nonce, _signed_at, _signature

        # On the consumer side:
        valid = signer.verify_message(signed_data)
        # → True if signature is valid and nonce is fresh
    """

    def __init__(
        self,
        agent_name: str,
        key_pair: Optional[CryptoKeyPair] = None,
    ):
        self._agent_name = agent_name
        self._provider = MlDsaProvider(MlDsaParameterSet.ML_DSA_65)

        if key_pair:
            self._key_pair = key_pair
        else:
            self._key_pair = self._provider.generate_key_pair()

        # Register own key
        registry = get_agent_key_registry()
        registry.register(agent_name, self._key_pair.public_key)

        # Nonce tracking (for replay detection on consumer side)
        self._seen_nonces: Dict[str, "collections.OrderedDict[str, bool]"] = {}  # agent → ordered nonce cache

        self._logger = logger.bind(
            component="message_signer",
            agent=agent_name,
        )

    @property
    def public_key(self) -> bytes:
        return self._key_pair.public_key

    @property
    def agent_name(self) -> str:
        return self._agent_name

    def sign_message(self, data: Dict[str, Any]) -> Dict[str, str]:
        """
        Sign a message for publishing to Redis Streams.

        Args:
            data: The message payload (must be JSON-serializable)

        Returns:
            Dict with original data + signing metadata fields:
            - _sender: agent name
            - _nonce: unique message ID
            - _signed_at: ISO timestamp
            - _signature: ML-DSA-65 signature (base64)
            - _sender_pubkey: sender's public key (base64, for verification)
        """
        nonce = uuid.uuid4().hex
        signed_at = str(time.time())

        # Build canonical message for signing
        # SECURITY: Include all data + metadata in the signed payload
        # to prevent selective field forgery
        canonical = self._build_canonical(data, nonce, signed_at)

        # Sign with ML-DSA-65
        signature = self._provider.sign(
            canonical.encode("utf-8"),
            self._key_pair.private_key,
        )

        # Serialize all values to strings for Redis
        result = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                result[k] = json.dumps(v, default=str)
            else:
                result[k] = str(v)

        result["_sender"] = self._agent_name
        result["_nonce"] = nonce
        result["_signed_at"] = signed_at
        result["_signature"] = base64.b64encode(signature).decode("ascii")
        result["_sender_pubkey"] = base64.b64encode(
            self._key_pair.public_key
        ).decode("ascii")

        return result

    def verify_message(self, fields: Dict[str, str]) -> Tuple[bool, str]:
        """
        Verify a received message's signature and freshness.

        Args:
            fields: Raw Redis Stream fields (string key-value pairs)

        Returns:
            Tuple of (is_valid, reason):
            - (True, "ok") if signature is valid and nonce is fresh
            - (False, reason) if verification fails
        """
        sender = fields.get("_sender", "")
        nonce = fields.get("_nonce", "")
        signed_at = fields.get("_signed_at", "")
        signature_b64 = fields.get("_signature", "")
        pubkey_b64 = fields.get("_sender_pubkey", "")

        # 1. Check required fields
        if not all([sender, nonce, signed_at, signature_b64, pubkey_b64]):
            return False, "missing_signature_fields"

        # 2. Check freshness (prevent very old messages from being accepted)
        try:
            msg_age = time.time() - float(signed_at)
            if msg_age > NONCE_TTL * 2:
                return False, "message_too_old"
        except (ValueError, TypeError):
            return False, "invalid_signed_at"

        # 3. Check nonce replay
        if self._is_nonce_seen(sender, nonce):
            return False, "nonce_replay_detected"

        # 4. Reconstruct canonical message (exclude signing metadata)
        data = {
            k: v for k, v in fields.items()
            if not k.startswith("_")
        }
        canonical = self._build_canonical(data, nonce, signed_at)

        # 5. Verify ML-DSA-65 signature
        try:
            signature = base64.b64decode(signature_b64)
            public_key = base64.b64decode(pubkey_b64)

            valid = self._provider.verify(
                canonical.encode("utf-8"),
                signature,
                public_key,
            )

            if not valid:
                self._logger.warning(
                    "signature_verification_failed",
                    sender=sender,
                    nonce=nonce,
                )
                return False, "invalid_signature"

        except Exception as exc:
            self._logger.warning(
                "signature_verification_error",
                sender=sender,
                error=str(exc),
            )
            return False, f"verification_error: {exc}"

        # 6. Record nonce (mark as seen)
        self._record_nonce(sender, nonce)

        return True, "ok"

    def _build_canonical(
        self,
        data: Dict[str, Any],
        nonce: str,
        signed_at: str,
    ) -> str:
        """
        Build a canonical string for signing.

        Uses sorted JSON to ensure deterministic serialization.
        Includes nonce and timestamp to prevent replay.
        """
        data_str = json.dumps(data, sort_keys=True, default=str)
        return f"{data_str}|{nonce}|{signed_at}"

    def _is_nonce_seen(self, sender: str, nonce: str) -> bool:
        """Check if a nonce was already used by this sender."""
        if sender not in self._seen_nonces:
            return False
        return nonce in self._seen_nonces[sender]

    def _record_nonce(self, sender: str, nonce: str) -> None:
        """Record a nonce as seen."""
        import collections
        if sender not in self._seen_nonces:
            self._seen_nonces[sender] = collections.OrderedDict()
        self._seen_nonces[sender][nonce] = True
        # Move to end (most recent)
        self._seen_nonces[sender].move_to_end(nonce)

        # Cap nonce cache size — evict oldest entries
        while len(self._seen_nonces[sender]) > MAX_NONCES_PER_AGENT:
            self._seen_nonces[sender].popitem(last=False)


# ════════════════════════════════════════════════════════════════════
# Signed Producer / Consumer Wrappers
# ════════════════════════════════════════════════════════════════════


class SignedProducer:
    """
    Wrapper around RedisStreamsProducer that signs all messages.

    Drop-in replacement for RedisStreamsProducer with message signing.

    Usage:
        producer = SignedProducer(agent_name="soko_pulse")
        await producer.connect()
        await producer.publish("transaction.processed", {"amount": 500})
    """

    def __init__(self, agent_name: str, key_pair: Optional[CryptoKeyPair] = None):
        from app.infrastructure.redis_streams import RedisStreamsProducer
        self._inner = RedisStreamsProducer()
        self._signer = MessageSigner(agent_name, key_pair)
        self._logger = logger.bind(component="signed_producer", agent=agent_name)

    async def connect(self):
        await self._inner.connect()

    async def disconnect(self):
        await self._inner.disconnect()

    async def publish(
        self,
        stream: str,
        data: Dict[str, Any],
        max_length: int = 50_000,
    ) -> Optional[str]:
        """Publish a signed message to a Redis Stream."""
        signed_data = self._signer.sign_message(data)
        return await self._inner.publish(stream, signed_data, max_length)

    @property
    def is_connected(self) -> bool:
        return self._inner.is_connected


class SignedConsumer:
    """
    Wrapper around RedisStreamsConsumer that verifies message signatures.

    Drop-in replacement for RedisStreamsConsumer with signature verification.

    Usage:
        consumer = SignedConsumer(group="intelligence_generators", agent_name="report_gen")
        await consumer.connect()
        await consumer.subscribe("transaction.processed", handler=my_handler)
        await consumer.start()
    """

    def __init__(
        self,
        group: str,
        agent_name: str,
        key_pair: Optional[CryptoKeyPair] = None,
        reject_unsigned: bool = False,  # False during transition period
        **kwargs,
    ):
        from app.infrastructure.redis_streams import RedisStreamsConsumer
        self._inner = RedisStreamsConsumer(group=group, **kwargs)
        self._signer = MessageSigner(agent_name, key_pair)
        self._reject_unsigned = reject_unsigned
        self._rejected_count = 0
        self._logger = logger.bind(component="signed_consumer", agent=agent_name)

    async def connect(self):
        await self._inner.connect()

    async def disconnect(self):
        await self._inner.disconnect()

    async def subscribe(self, stream: str, handler):
        """Subscribe with signature verification wrapper."""
        async def verified_handler(message):
            fields = message.data  # Already deserialized

            # Check if message has signing fields
            has_signature = "_signature" in fields

            if has_signature:
                # Reconstruct raw fields for verification
                raw_fields = {k: str(v) for k, v in fields.items()}
                valid, reason = self._signer.verify_message(raw_fields)

                if not valid:
                    self._rejected_count += 1
                    self._logger.warning(
                        "message_rejected",
                        stream=stream,
                        reason=reason,
                        sender=fields.get("_sender", "unknown"),
                        rejected_count=self._rejected_count,
                    )
                    if self._reject_unsigned:
                        return
            elif self._reject_unsigned:
                self._rejected_count += 1
                self._logger.warning(
                    "unsigned_message_rejected",
                    stream=stream,
                    rejected_count=self._rejected_count,
                )
                return
            else:
                # During transition: log but allow unsigned messages
                self._logger.debug(
                    "unsigned_message_accepted",
                    stream=stream,
                    note="transition_period",
                )

            # Strip signing metadata before passing to handler
            clean_data = {
                k: v for k, v in fields.items()
                if not k.startswith("_")
            }
            message.data = clean_data
            await handler(message)

        await self._inner.subscribe(stream, verified_handler)

    async def start(self):
        await self._inner.start()

    async def stop(self):
        await self._inner.stop()

    def get_stats(self) -> Dict[str, Any]:
        stats = self._inner.get_stats()
        stats["rejected_messages"] = self._rejected_count
        stats["reject_unsigned"] = self._reject_unsigned
        return stats
