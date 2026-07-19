"""
Agent-to-Agent Knowledge Sharing — Cross-Worker Learning.

Enables agents to share learned knowledge, patterns, and strategies
with each other. This accelerates learning: if one agent discovers
a useful pattern, all similar agents benefit immediately.

Knowledge Types:
  - Patterns:  Discovered regularities (e.g., "demand peaks on Fridays")
  - Strategies: Tested action strategies (e.g., "markup 15% for perishables")
  - Warnings:   Known failure modes (e.g., "never trust supplier X on Mondays")
  - Insights:   Domain knowledge (e.g., "Mombasa prices lag Nairobi by 2 days")

Sharing Mechanisms:
  1. Broadcast: Agent publishes a discovery, all subscribed agents receive it
  2. Request:   Agent asks for help, peers contribute relevant knowledge
  3. Gossip:    Periodic random knowledge exchange between agent pairs
  4. Mentor:    High-trust agents teach lower-trust agents

References:
  - Multi-Agent Reinforcement Learning (MARL) — knowledge transfer
  - Federated Learning — privacy-preserving knowledge aggregation
  - Swarm Intelligence — stigmergic communication patterns
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class KnowledgeType(str, Enum):
    """Types of shareable knowledge."""
    PATTERN = "pattern"         # Discovered regularity
    STRATEGY = "strategy"       # Tested action approach
    WARNING = "warning"         # Known failure mode
    INSIGHT = "insight"         # Domain knowledge
    FEEDBACK = "feedback"       # Outcome-based learning


class KnowledgeConfidence(str, Enum):
    """Confidence level for shared knowledge."""
    EXPERIMENTAL = "experimental"   # Untested, just discovered
    TESTED = "tested"              # Verified by 1-3 agents
    PROVEN = "proven"              # Verified by 4+ agents
    DEPRECATED = "deprecated"      # Superseded by newer knowledge


@dataclass
class KnowledgeItem:
    """A piece of shareable knowledge."""
    knowledge_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    knowledge_type: KnowledgeType = KnowledgeType.PATTERN
    source_agent: str = ""
    title: str = ""
    description: str = ""
    domain: str = ""               # "agriculture", "retail", "transport", etc.
    tags: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    confidence: KnowledgeConfidence = KnowledgeConfidence.EXPERIMENTAL
    verification_count: int = 0    # How many agents verified this
    verified_by: list[str] = field(default_factory=list)
    success_count: int = 0         # Times this knowledge led to success
    failure_count: int = 0         # Times this knowledge led to failure
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    expires_at: float | None = None

    @property
    def effectiveness(self) -> float:
        """Success rate when this knowledge was applied."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5  # Unknown
        return self.success_count / total

    @property
    def is_expired(self) -> bool:
        """Check if this knowledge item has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def record_usage(self, success: bool) -> None:
        """Record an outcome when this knowledge was applied."""
        self.last_used = time.time()
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

    def verify(self, agent_name: str) -> None:
        """Mark this knowledge as verified by an agent."""
        if agent_name not in self.verified_by:
            self.verified_by.append(agent_name)
            self.verification_count = len(self.verified_by)

            # Auto-promote confidence
            if self.verification_count >= 4:
                self.confidence = KnowledgeConfidence.PROVEN
            elif self.verification_count >= 1:
                self.confidence = KnowledgeConfidence.TESTED

    def to_dict(self) -> dict[str, Any]:
        """Serialize knowledge item to dictionary."""
        return {
            "knowledge_id": self.knowledge_id,
            "type": self.knowledge_type.value,
            "source_agent": self.source_agent,
            "title": self.title,
            "description": self.description,
            "domain": self.domain,
            "tags": self.tags,
            "confidence": self.confidence.value,
            "verification_count": self.verification_count,
            "effectiveness": round(self.effectiveness, 3),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "created_at": self.created_at,
            "last_used": self.last_used,
        }


@dataclass
class KnowledgeRequest:
    """A request for knowledge from a peer agent."""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    requesting_agent: str = ""
    domain: str = ""
    query: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    responses: list[KnowledgeItem] = field(default_factory=list)


class KnowledgeSharingHub:
    """
    Central hub for agent-to-agent knowledge sharing.

    Agents publish discoveries and request knowledge from peers.
    The hub manages knowledge lifecycle: storage, verification,
    expiration, and retrieval.

    Usage:
        hub = KnowledgeSharingHub()

        # Agent discovers a pattern
        hub.publish(KnowledgeItem(
            source_agent="SokoPulse",
            knowledge_type=KnowledgeType.PATTERN,
            title="Nyanya price peaks on Fridays",
            domain="agriculture",
            data={"peak_day": "friday", "avg_increase_pct": 15},
        ))

        # Another agent requests knowledge
        results = hub.query(
            requesting_agent="RetailAgent",
            domain="agriculture",
            tags=["price", "pattern"],
        )
    """

    def __init__(
        self,
        max_knowledge_items: int = 5000,
        default_ttl_days: float = 90.0,
    ):
        self._knowledge: dict[str, KnowledgeItem] = {}
        self._max_items = max_knowledge_items
        self._default_ttl = default_ttl_days * 86400  # Convert to seconds

        # Indexes for fast retrieval
        self._by_domain: dict[str, set[str]] = defaultdict(set)
        self._by_tag: dict[str, set[str]] = defaultdict(set)
        self._by_type: dict[str, set[str]] = defaultdict(set)
        self._by_agent: dict[str, set[str]] = defaultdict(set)

        # Subscription: agents register interest in domains/tags
        self._subscriptions: dict[str, dict[str, set[str]]] = defaultdict(
            lambda: {"domains": set(), "tags": set()}
        )

        # Request tracking
        self._requests: list[KnowledgeRequest] = []

        self._logger = logger.bind(component="knowledge_sharing_hub")

    # ── Publishing ─────────────────────────────────────────────────

    def publish(self, knowledge: KnowledgeItem) -> str:
        """
        Publish a knowledge item to the hub.

        Indexes it for retrieval and notifies subscribed agents.
        """
        # Set expiry if not set
        if knowledge.expires_at is None:
            knowledge.expires_at = time.time() + self._default_ttl

        self._knowledge[knowledge.knowledge_id] = knowledge

        # Update indexes
        if knowledge.domain:
            self._by_domain[knowledge.domain].add(knowledge.knowledge_id)
        for tag in knowledge.tags:
            self._by_tag[tag].add(knowledge.knowledge_id)
        self._by_type[knowledge.knowledge_type.value].add(knowledge.knowledge_id)
        self._by_agent[knowledge.source_agent].add(knowledge.knowledge_id)

        # Evict if over limit
        if len(self._knowledge) > self._max_items:
            self._evict_stale()

        self._logger.info(
            "knowledge_published",
            knowledge_id=knowledge.knowledge_id,
            source=knowledge.source_agent,
            type=knowledge.knowledge_type.value,
            domain=knowledge.domain,
            title=knowledge.title[:50],
        )

        # Notify subscribed agents (returns list for caller to dispatch)
        subscribers = self._get_subscribers(knowledge.domain, knowledge.tags)
        if subscribers:
            self._logger.debug(
                "knowledge_notify_subscribers",
                knowledge_id=knowledge.knowledge_id,
                subscribers=subscribers,
            )

        return knowledge.knowledge_id

    # ── Querying ───────────────────────────────────────────────────

    def query(
        self,
        requesting_agent: str,
        domain: str | None = None,
        knowledge_type: KnowledgeType | None = None,
        tags: list[str] | None = None,
        min_confidence: KnowledgeConfidence | None = None,
        min_effectiveness: float = 0.0,
        limit: int = 10,
    ) -> list[KnowledgeItem]:
        """
        Query the knowledge base for relevant items.

        Returns items sorted by relevance (effectiveness × confidence × recency).
        """
        # Start with all knowledge
        candidate_ids: set[str] | None = None

        # Filter by domain
        if domain:
            domain_ids = self._by_domain.get(domain, set())
            candidate_ids = domain_ids.copy() if candidate_ids is None else candidate_ids & domain_ids

        # Filter by type
        if knowledge_type:
            type_ids = self._by_type.get(knowledge_type.value, set())
            candidate_ids = type_ids.copy() if candidate_ids is None else candidate_ids & type_ids

        # Filter by tags (union — any matching tag)
        if tags:
            tag_ids: set[str] = set()
            for tag in tags:
                tag_ids |= self._by_tag.get(tag, set())
            candidate_ids = tag_ids.copy() if candidate_ids is None else candidate_ids & tag_ids

        # If no filters, use all
        if candidate_ids is None:
            candidate_ids = set(self._knowledge.keys())

        # Apply filters
        results = []
        confidence_order = {
            KnowledgeConfidence.EXPERIMENTAL: 0,
            KnowledgeConfidence.TESTED: 1,
            KnowledgeConfidence.PROVEN: 2,
            KnowledgeConfidence.DEPRECATED: -1,
        }
        min_conf_val = confidence_order.get(min_confidence, 0) if min_confidence else 0

        for kid in candidate_ids:
            item = self._knowledge.get(kid)
            if item is None or item.is_expired:
                continue
            if item.source_agent == requesting_agent:
                continue  # Don't return own knowledge
            if confidence_order.get(item.confidence, 0) < min_conf_val:
                continue
            if item.effectiveness < min_effectiveness:
                continue
            results.append(item)

        # Sort by relevance: effectiveness × confidence × recency
        now = time.time()
        results.sort(
            key=lambda x: (
                x.effectiveness
                * (1 + confidence_order.get(x.confidence, 0))
                * max(0.1, 1.0 - (now - x.last_used) / (30 * 86400))
            ),
            reverse=True,
        )

        return results[:limit]

    def request_knowledge(
        self,
        requesting_agent: str,
        domain: str,
        query: str,
        tags: list[str] | None = None,
    ) -> KnowledgeRequest:
        """
        Explicitly request knowledge from peers.

        Stores the request for tracking and returns matching knowledge.
        """
        request = KnowledgeRequest(
            requesting_agent=requesting_agent,
            domain=domain,
            query=query,
            tags=tags or [],
        )

        # Find matching knowledge
        matches = self.query(
            requesting_agent=requesting_agent,
            domain=domain,
            tags=tags,
            min_confidence=KnowledgeConfidence.TESTED,
            limit=5,
        )
        request.responses = matches

        self._requests.append(request)
        if len(self._requests) > 1000:
            self._requests = self._requests[-1000:]

        self._logger.info(
            "knowledge_requested",
            agent=requesting_agent,
            domain=domain,
            query=query[:50],
            matches=len(matches),
        )

        return request

    # ── Verification & Feedback ────────────────────────────────────

    def verify_knowledge(self, knowledge_id: str, agent_name: str) -> bool:
        """Mark a knowledge item as verified by an agent."""
        item = self._knowledge.get(knowledge_id)
        if item is None:
            return False
        item.verify(agent_name)
        self._logger.info(
            "knowledge_verified",
            knowledge_id=knowledge_id,
            verifier=agent_name,
            total_verifications=item.verification_count,
            new_confidence=item.confidence.value,
        )
        return True

    def record_outcome(self, knowledge_id: str, success: bool) -> bool:
        """Record the outcome of applying a knowledge item."""
        item = self._knowledge.get(knowledge_id)
        if item is None:
            return False
        item.record_usage(success)

        # Deprecate if consistently failing
        if item.failure_count >= 5 and item.effectiveness < 0.3:
            item.confidence = KnowledgeConfidence.DEPRECATED
            self._logger.warning(
                "knowledge_deprecated",
                knowledge_id=knowledge_id,
                effectiveness=round(item.effectiveness, 3),
            )

        return True

    # ── Subscriptions ──────────────────────────────────────────────

    def subscribe(
        self,
        agent_name: str,
        domains: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """Subscribe an agent to knowledge updates in specific domains/tags."""
        if domains:
            self._subscriptions[agent_name]["domains"].update(domains)
        if tags:
            self._subscriptions[agent_name]["tags"].update(tags)

        self._logger.debug(
            "agent_subscribed",
            agent=agent_name,
            domains=list(self._subscriptions[agent_name]["domains"]),
            tags=list(self._subscriptions[agent_name]["tags"]),
        )

    def _get_subscribers(self, domain: str, tags: list[str]) -> list[str]:
        """Get agents subscribed to a domain or set of tags."""
        subscribers: set[str] = set()
        for agent_name, subs in self._subscriptions.items():
            if domain in subs["domains"]:
                subscribers.add(agent_name)
            for tag in tags:
                if tag in subs["tags"]:
                    subscribers.add(agent_name)
        return list(subscribers)

    # ── Maintenance ────────────────────────────────────────────────

    def _evict_stale(self) -> None:
        """Evict expired and deprecated knowledge."""
        to_remove = []
        for kid, item in self._knowledge.items():
            if item.is_expired or item.confidence == KnowledgeConfidence.DEPRECATED:
                to_remove.append(kid)

        for kid in to_remove:
            self._remove_item(kid)

        # If still over limit, remove least effective
        if len(self._knowledge) > self._max_items:
            sorted_items = sorted(
                self._knowledge.values(),
                key=lambda x: x.effectiveness * (1 if x.confidence == KnowledgeConfidence.PROVEN else 0.5),
            )
            for item in sorted_items[:len(self._knowledge) - self._max_items]:
                self._remove_item(item.knowledge_id)

    def _remove_item(self, knowledge_id: str) -> None:
        """Remove a knowledge item and clean up indexes."""
        item = self._knowledge.pop(knowledge_id, None)
        if item is None:
            return
        if item.domain:
            self._by_domain[item.domain].discard(knowledge_id)
        for tag in item.tags:
            self._by_tag[tag].discard(knowledge_id)
        self._by_type[item.knowledge_type.value].discard(knowledge_id)
        self._by_agent[item.source_agent].discard(knowledge_id)

    # ── Queries ────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get hub statistics."""
        return {
            "total_knowledge": len(self._knowledge),
            "by_type": {t.value: len(self._by_type.get(t.value, set())) for t in KnowledgeType},
            "by_confidence": {
                conf.value: sum(
                    1 for k in self._knowledge.values() if k.confidence == conf
                )
                for conf in KnowledgeConfidence
            },
            "total_requests": len(self._requests),
            "subscribed_agents": len(self._subscriptions),
            "domains": list(self._by_domain.keys()),
        }

    def get_agent_contributions(self, agent_name: str) -> dict[str, Any]:
        """Get knowledge contribution stats for an agent."""
        items = [
            self._knowledge[kid]
            for kid in self._by_agent.get(agent_name, set())
            if kid in self._knowledge
        ]
        return {
            "agent_name": agent_name,
            "total_contributions": len(items),
            "by_type": {
                t.value: sum(1 for k in items if k.knowledge_type == t)
                for t in KnowledgeType
            },
            "avg_effectiveness": (
                round(sum(k.effectiveness for k in items) / len(items), 3)
                if items else 0.0
            ),
            "proven_count": sum(
                1 for k in items if k.confidence == KnowledgeConfidence.PROVEN
            ),
        }

    def get_top_knowledge(
        self,
        domain: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get the most effective knowledge items."""
        items = list(self._knowledge.values())
        if domain:
            items = [k for k in items if k.domain == domain]

        items = [k for k in items if not k.is_expired]
        items.sort(key=lambda x: x.effectiveness * x.verification_count, reverse=True)

        return [k.to_dict() for k in items[:limit]]
