"""
Agent Capability Tokens — Fine-grained authorization for inter-agent actions.

Each agent receives a capability token that defines:
- What actions it can perform (read, write, execute, delegate)
- What resources it can access (streams, data domains, APIs)
- What other agents it can communicate with
- Expiry time (tokens are short-lived, rotated hourly)

Tokens are signed with ML-DSA-65 by the governance agent and verified
by any agent before accepting a request.

Capability model (inspired by Zanzibar/SpiceDB):
    Agent → Capability → Resource → Action

Examples:
    soko_pulse → READ → transaction.* → all
    alama_score → WRITE → credit_score.* → own_tenant
    report_gen → READ → intelligence.* → all
    meta_agent → DELEGATE → * → all

Integration:
    - Wired into SecurityMiddleware via AgentCapabilityMiddleware
    - Set ANGAVU_CAPABILITY_TOKENS_ENABLED=true to enable
    - Feature flag per swarm via ANGAVU_CAPABILITY_SWARM_<NAME>=true
"""

from __future__ import annotations

import fnmatch
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import structlog

from app.security.pqc.ml_dsa import MlDsaParameterSet, MlDsaProvider

logger = structlog.get_logger(__name__)

# ── Feature Flags ──────────────────────────────────────────────────

CAPABILITY_TOKENS_ENABLED = os.getenv(
    "ANGAVU_CAPABILITY_TOKENS_ENABLED", "false"
).lower() == "true"

# Per-swarm feature flags (all enabled by default when master flag is on)
SWARM_FLAGS = {
    "intelligence": os.getenv("ANGAVU_CAPABILITY_SWARM_INTELLIGENCE", "true").lower() == "true",
    "revenue_ops": os.getenv("ANGAVU_CAPABILITY_SWARM_REVENUE_OPS", "true").lower() == "true",
    "governance": os.getenv("ANGAVU_CAPABILITY_SWARM_GOVERNANCE", "true").lower() == "true",
    "data_pipeline": os.getenv("ANGAVU_CAPABILITY_SWARM_DATA_PIPELINE", "true").lower() == "true",
    "research": os.getenv("ANGAVU_CAPABILITY_SWARM_RESEARCH", "true").lower() == "true",
    "communication": os.getenv("ANGAVU_CAPABILITY_SWARM_COMMUNICATION", "true").lower() == "true",
}


def is_swarm_capability_enabled(swarm: str) -> bool:
    """Check if capability tokens are enabled for a specific swarm."""
    if not CAPABILITY_TOKENS_ENABLED:
        return False
    return SWARM_FLAGS.get(swarm, True)


# ════════════════════════════════════════════════════════════════════
# Enums & Data Classes
# ════════════════════════════════════════════════════════════════════


class Action(StrEnum):
    """Permitted actions for agents."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELEGATE = "delegate"
    PUBLISH = "publish"
    SUBSCRIBE = "subscribe"
    ADMIN = "admin"


class ResourceScope(StrEnum):
    """Resource scopes that agents can access."""
    TRANSACTION = "transaction"
    INTELLIGENCE = "intelligence"
    REPORT = "report"
    FEEDBACK = "feedback"
    AGENT_COMM = "agent_comm"
    FEDERATED = "federated"
    CONFIG = "config"
    ALL = "*"


@dataclass
class Capability:
    """A single capability grant."""
    resource: ResourceScope
    actions: set[Action]
    # Optional: restrict to specific resource patterns
    resource_pattern: str = "*"  # e.g., "transaction.processed", "intelligence.*"
    # Optional: restrict to specific tenants
    tenant_id: str | None = None

    def allows(self, resource: str, action: Action) -> bool:
        """Check if this capability allows the given resource + action."""
        if action not in self.actions:
            return False
        if self.resource != ResourceScope.ALL:
            if not resource.startswith(self.resource.value):
                return False
        if self.resource_pattern != "*":
            if not fnmatch.fnmatch(resource, self.resource_pattern):
                return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource.value,
            "actions": [a.value for a in self.actions],
            "resource_pattern": self.resource_pattern,
            "tenant_id": self.tenant_id,
        }


@dataclass
class AgentCapabilityToken:
    """
    A capability token for an agent.

    Grants specific permissions for a limited time window.
    Signed by the governance agent's ML-DSA-65 key.
    """
    # Token identity
    token_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    agent_name: str = ""
    swarm: str = ""  # e.g., "intelligence", "revenue_ops", "governance"

    # Capabilities
    capabilities: list[Capability] = field(default_factory=list)

    # Allowed communication targets (empty = no restrictions)
    allowed_recipients: set[str] | None = None

    # Temporal constraints
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0  # Unix timestamp
    max_uses: int = 0  # 0 = unlimited

    # Issuer
    issued_by: str = "governance_agent"

    # Signature (filled by issuer)
    signature: bytes | None = None
    issuer_public_key: bytes | None = None

    # Usage tracking
    use_count: int = 0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def is_maxed_out(self) -> bool:
        return self.max_uses > 0 and self.use_count >= self.max_uses

    def allows(self, resource: str, action: Action) -> bool:
        """Check if this token allows the given resource + action."""
        if self.is_expired() or self.is_maxed_out():
            return False
        return any(cap.allows(resource, action) for cap in self.capabilities)

    def can_communicate_with(self, recipient: str) -> bool:
        """Check if this token allows communication with a recipient."""
        if self.allowed_recipients is None:
            return True  # No restriction
        return recipient in self.allowed_recipients

    def record_use(self) -> None:
        self.use_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "agent_name": self.agent_name,
            "swarm": self.swarm,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "allowed_recipients": list(self.allowed_recipients) if self.allowed_recipients else None,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "max_uses": self.max_uses,
            "issued_by": self.issued_by,
            "use_count": self.use_count,
        }


# ════════════════════════════════════════════════════════════════════
# Token Issuer
# ════════════════════════════════════════════════════════════════════


class CapabilityTokenIssuer:
    """
    Issues capability tokens to agents.

    Only the governance agent (or meta_agent) can issue tokens.
    Tokens are signed with the issuer's ML-DSA-65 key.
    """

    def __init__(self, issuer_name: str = "governance_agent"):
        self._provider = MlDsaProvider(MlDsaParameterSet.ML_DSA_65)
        self._key_pair = self._provider.generate_key_pair()
        self._issuer_name = issuer_name
        self._issued_tokens: dict[str, AgentCapabilityToken] = {}
        self._logger = logger.bind(component="capability_issuer")

    @property
    def public_key(self) -> bytes:
        return self._key_pair.public_key

    def issue_token(
        self,
        agent_name: str,
        swarm: str,
        capabilities: list[Capability],
        ttl_seconds: int = 3600,
        max_uses: int = 0,
        allowed_recipients: set[str] | None = None,
    ) -> AgentCapabilityToken:
        """
        Issue a capability token for an agent.

        Args:
            agent_name: Name of the agent receiving the token
            swarm: The swarm the agent belongs to
            capabilities: List of capability grants
            ttl_seconds: Token validity period (default: 1 hour)
            max_uses: Maximum number of uses (0 = unlimited)
            allowed_recipients: Restrict communication targets

        Returns:
            Signed AgentCapabilityToken
        """
        token = AgentCapabilityToken(
            agent_name=agent_name,
            swarm=swarm,
            capabilities=capabilities,
            expires_at=time.time() + ttl_seconds,
            max_uses=max_uses,
            allowed_recipients=allowed_recipients,
            issued_by=self._issuer_name,
        )

        # Sign the token
        token_bytes = json.dumps(token.to_dict(), sort_keys=True).encode()
        token.signature = self._provider.sign(token_bytes, self._key_pair.private_key)
        token.issuer_public_key = self._key_pair.public_key

        self._issued_tokens[token.token_id] = token
        self._logger.info(
            "capability_token_issued",
            agent=agent_name,
            swarm=swarm,
            token_id=token.token_id,
            ttl=ttl_seconds,
            capabilities=[c.resource.value for c in capabilities],
        )

        return token

    def verify_token(self, token: AgentCapabilityToken) -> bool:
        """
        Verify a capability token's signature and validity.

        Returns True if:
        - Signature is valid
        - Token is not expired
        - Token has not exceeded max uses
        """
        if token.is_expired():
            return False
        if token.is_maxed_out():
            return False
        if not token.signature or not token.issuer_public_key:
            return False

        # Reconstruct signed data
        verify_data = {
            k: v for k, v in token.to_dict().items()
            if k not in ("signature", "issuer_public_key")
        }
        token_bytes = json.dumps(verify_data, sort_keys=True).encode()

        return self._provider.verify(
            token_bytes,
            token.signature,
            token.issuer_public_key,
        )

    def revoke_token(self, token_id: str) -> bool:
        """Revoke a token (sets expiry to now)."""
        token = self._issued_tokens.get(token_id)
        if token:
            token.expires_at = time.time()
            self._logger.warning("capability_token_revoked", token_id=token_id)
            return True
        return False


# ════════════════════════════════════════════════════════════════════
# Predefined Capability Profiles
# ════════════════════════════════════════════════════════════════════

SWARM_CAPABILITIES = {
    "intelligence": [
        Capability(resource=ResourceScope.TRANSACTION, actions={Action.READ, Action.SUBSCRIBE}),
        Capability(resource=ResourceScope.INTELLIGENCE, actions={Action.READ, Action.WRITE, Action.PUBLISH}),
        Capability(resource=ResourceScope.REPORT, actions={Action.READ}),
    ],
    "revenue_ops": [
        Capability(resource=ResourceScope.INTELLIGENCE, actions={Action.READ}),
        Capability(resource=ResourceScope.REPORT, actions={Action.READ, Action.WRITE, Action.PUBLISH}),
        Capability(resource=ResourceScope.AGENT_COMM, actions={Action.READ, Action.WRITE}),
    ],
    "governance": [
        Capability(resource=ResourceScope.ALL, actions={Action.READ, Action.WRITE, Action.ADMIN, Action.DELEGATE}),
    ],
    "data_pipeline": [
        Capability(resource=ResourceScope.TRANSACTION, actions={Action.READ, Action.WRITE, Action.PUBLISH}),
        Capability(resource=ResourceScope.FEDERATED, actions={Action.READ, Action.WRITE}),
    ],
    "research": [
        Capability(resource=ResourceScope.INTELLIGENCE, actions={Action.READ}),
        Capability(resource=ResourceScope.TRANSACTION, actions={Action.READ}),
        Capability(resource=ResourceScope.REPORT, actions={Action.READ, Action.WRITE}),
    ],
    "communication": [
        Capability(resource=ResourceScope.AGENT_COMM, actions={Action.READ, Action.WRITE, Action.PUBLISH, Action.SUBSCRIBE}),
        Capability(resource=ResourceScope.REPORT, actions={Action.READ, Action.SUBSCRIBE}),
    ],
}


def create_default_token(
    issuer: CapabilityTokenIssuer,
    agent_name: str,
    swarm: str,
    ttl_seconds: int = 3600,
) -> AgentCapabilityToken:
    """Create a capability token with default swarm capabilities."""
    caps = SWARM_CAPABILITIES.get(swarm, [])
    return issuer.issue_token(
        agent_name=agent_name,
        swarm=swarm,
        capabilities=list(caps),
        ttl_seconds=ttl_seconds,
    )


# ════════════════════════════════════════════════════════════════════
# Singleton Issuer (for convenience)
# ════════════════════════════════════════════════════════════════════

_capability_issuer: CapabilityTokenIssuer | None = None


def get_capability_issuer() -> CapabilityTokenIssuer:
    """Get or create the singleton capability token issuer."""
    global _capability_issuer
    if _capability_issuer is None:
        _capability_issuer = CapabilityTokenIssuer()
    return _capability_issuer
