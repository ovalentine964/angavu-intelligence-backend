"""
Three-Tier Memory Architecture for Angavu Intelligence Agents.

Implements the memory hierarchy from Swarm 3 research:
- Working Memory: Current context window (hot, fast, limited)
- Episodic Memory: Past interactions and outcomes (warm, searchable)
- Long-term Memory: Learned patterns and preferences (cold, persistent)

Reference:
- ARTEM (AAAI 2026): Spatial-temporal episodic memory
- DarwinMem (Mi et al., 2026): Evolutionary memory optimization
- Tsinghua "Awesome Memory for Agents" (2026)
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Memory Types
# ════════════════════════════════════════════════════════════════════


class MemoryTier(str, Enum):
    WORKING = "working"        # Current context window
    EPISODIC = "episodic"      # Past interactions
    LONGTERM = "longterm"      # Distilled patterns


class MemoryImportance(int, Enum):
    """Importance levels for memory items."""
    TRANSIENT = 0   # Ephemeral, discard freely
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4    # Never discard (errors, key decisions)


@dataclass
class MemoryItem:
    """A single memory item across all tiers."""
    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: Dict[str, Any] = field(default_factory=dict)
    tier: MemoryTier = MemoryTier.WORKING
    importance: MemoryImportance = MemoryImportance.NORMAL
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None  # For semantic search
    session_id: Optional[str] = None
    agent_name: Optional[str] = None

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def recency_score(self) -> float:
        """Exponential decay: 1.0 when fresh, approaches 0."""
        half_life = 300.0 if self.tier == MemoryTier.WORKING else 3600.0
        return 2.0 ** (-self.age_seconds / half_life)

    @property
    def importance_score(self) -> float:
        """Combined importance: priority + recency + frequency."""
        p = self.importance.value / MemoryImportance.CRITICAL.value
        r = self.recency_score
        f = min(1.0, self.access_count / 5.0)
        return (0.4 * p) + (0.4 * r) + (0.2 * f)

    def touch(self) -> None:
        """Record an access."""
        self.accessed_at = time.time()
        self.access_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "content": self.content,
            "tier": self.tier.value,
            "importance": self.importance.value,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
            "tags": self.tags,
            "age_seconds": round(self.age_seconds, 1),
        }


@dataclass
class EpisodicRecord:
    """
    An episodic memory record — a complete interaction snapshot.

    Captures the full context of an agent cycle:
    what happened, what was decided, what the outcome was.
    """
    episode_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    agent_name: str = ""
    session_id: str = ""
    trigger_event: Dict[str, Any] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    context_snapshot: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    success: bool = True
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    # Derived metrics
    lessons_learned: List[str] = field(default_factory=list)
    similar_episodes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "trigger_event": self.trigger_event,
            "decision": self.decision,
            "result_summary": {
                "success": self.success,
                "duration_ms": self.duration_ms,
                "error": self.result.get("error"),
            },
            "tags": self.tags,
            "lessons_learned": self.lessons_learned,
            "created_at": self.created_at,
        }


@dataclass
class LongTermPattern:
    """
    A distilled pattern in long-term memory.

    Represents a learned rule, preference, or behavioral pattern
    that the agent has extracted from episodic memory over time.
    """
    pattern_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    pattern_type: str = ""       # "preference", "rule", "trend", "correlation"
    description: str = ""
    confidence: float = 0.5      # 0.0 - 1.0, grows with evidence
    evidence_count: int = 0      # Number of episodes supporting this
    evidence_ids: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_reinforced: float = field(default_factory=time.time)
    agent_name: str = ""

    def reinforce(self, episode_id: str) -> None:
        """Reinforce this pattern with new evidence."""
        self.evidence_count += 1
        if episode_id not in self.evidence_ids:
            self.evidence_ids.append(episode_id)
            if len(self.evidence_ids) > 20:
                self.evidence_ids = self.evidence_ids[-20:]
        # Confidence grows logarithmically with evidence
        import math
        self.confidence = min(0.99, 0.5 + 0.15 * math.log(1 + self.evidence_count))
        self.last_reinforced = time.time()

    def decay(self, days_since_reinforcement: float) -> None:
        """Decay confidence if not reinforced."""
        if days_since_reinforcement > 30:
            self.confidence *= 0.95
        if days_since_reinforcement > 90:
            self.confidence *= 0.9

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "confidence": round(self.confidence, 3),
            "evidence_count": self.evidence_count,
            "parameters": self.parameters,
            "agent_name": self.agent_name,
            "last_reinforced": self.last_reinforced,
        }


# ════════════════════════════════════════════════════════════════════
# Working Memory — Current context window
# ════════════════════════════════════════════════════════════════════


class WorkingMemory:
    """
    Working memory — the agent's current context window.

    Hot, fast, limited. Manages the items that the agent is
    currently thinking about. Implements priority-weighted
    eviction with exponential decay.

    This replaces the simple list-based AgentMemory.short_term.
    """

    def __init__(self, max_tokens: int = 4000, max_items: int = 50):
        self._items: List[MemoryItem] = []
        self._max_tokens = max_tokens
        self._max_items = max_items
        self._total_tokens = 0

    def add(
        self,
        content: Dict[str, Any],
        importance: MemoryImportance = MemoryImportance.NORMAL,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> MemoryItem:
        """Add an item to working memory."""
        item = MemoryItem(
            content=content,
            tier=MemoryTier.WORKING,
            importance=importance,
            tags=tags or [],
            session_id=session_id,
            agent_name=agent_name,
        )
        # Estimate tokens (~4 chars per token)
        item.content["_token_est"] = max(1, len(str(content)) // 4)

        self._items.append(item)
        self._total_tokens += item.content.get("_token_est", 10)

        # Evict if over limits
        if len(self._items) > self._max_items or self._total_tokens > self._max_tokens:
            self._evict()

        return item

    def get_context(
        self,
        max_items: Optional[int] = None,
        filter_tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Get prioritized context items."""
        items = self._items
        if filter_tags:
            items = [i for i in items if any(t in i.tags for t in filter_tags)]

        # Sort by importance score
        items.sort(key=lambda i: i.importance_score, reverse=True)

        limit = max_items or len(items)
        result = []
        for item in items[:limit]:
            item.touch()
            result.append(item.content)

        return result

    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get N most recent items."""
        return [i.content for i in self._items[-n:]]

    def search(self, query: str) -> List[MemoryItem]:
        """Simple text search in working memory."""
        query_lower = query.lower()
        results = []
        for item in self._items:
            content_str = json.dumps(item.content, default=str).lower()
            if query_lower in content_str:
                item.touch()
                results.append(item)
        return results

    def clear(self) -> None:
        """Clear working memory."""
        self._items.clear()
        self._total_tokens = 0

    def _evict(self) -> None:
        """Evict lowest-importance items."""
        # Never evict CRITICAL items
        evictable = [i for i in self._items if i.importance < MemoryImportance.CRITICAL]
        evictable.sort(key=lambda i: i.importance_score)

        while (len(self._items) > self._max_items or self._total_tokens > self._max_tokens) and evictable:
            item = evictable.pop(0)
            self._items.remove(item)
            self._total_tokens -= item.content.get("_token_est", 10)

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def token_usage(self) -> Dict[str, Any]:
        return {
            "items": len(self._items),
            "total_tokens": self._total_tokens,
            "max_tokens": self._max_tokens,
            "utilization": round(self._total_tokens / self._max_tokens, 2) if self._max_tokens else 0,
        }


# ════════════════════════════════════════════════════════════════════
# Episodic Memory — Past interactions
# ════════════════════════════════════════════════════════════════════


class EpisodicMemory:
    """
    Episodic memory — records of past interactions and outcomes.

    Warm, searchable. Stores complete interaction snapshots
    so the agent can learn from past experience.

    Features:
    - Episode recording with full context
    - Similarity-based retrieval (find similar past situations)
    - Lesson extraction from episodes
    - Automatic consolidation to long-term patterns
    """

    def __init__(
        self,
        max_episodes: int = 500,
        consolidation_threshold: int = 5,
    ):
        self._episodes: List[EpisodicRecord] = []
        self._max_episodes = max_episodes
        self._consolidation_threshold = consolidation_threshold

        # Index for fast lookup
        self._by_agent: Dict[str, List[str]] = defaultdict(list)
        self._by_tag: Dict[str, List[str]] = defaultdict(list)
        self._by_success: Dict[bool, List[str]] = {True: [], False: []}

        self._logger = logger.bind(component="episodic_memory")

    def record(self, episode: EpisodicRecord) -> str:
        """
        Record a new episode.

        Returns the episode ID.
        """
        self._episodes.append(episode)

        # Update indexes
        self._by_agent[episode.agent_name].append(episode.episode_id)
        for tag in episode.tags:
            self._by_tag[tag].append(episode.episode_id)
        self._by_success[episode.success].append(episode.episode_id)

        # Trim old episodes
        if len(self._episodes) > self._max_episodes:
            self._episodes = self._episodes[-self._max_episodes:]

        self._logger.debug(
            "episode_recorded",
            episode_id=episode.episode_id,
            agent=episode.agent_name,
            success=episode.success,
        )

        return episode.episode_id

    def get_recent(
        self,
        agent_name: Optional[str] = None,
        n: int = 10,
        success_only: Optional[bool] = None,
    ) -> List[EpisodicRecord]:
        """Get recent episodes, optionally filtered."""
        episodes = self._episodes

        if agent_name:
            episode_ids = set(self._by_agent.get(agent_name, []))
            episodes = [e for e in episodes if e.episode_id in episode_ids]

        if success_only is not None:
            episodes = [e for e in episodes if e.success == success_only]

        return episodes[-n:]

    def get_similar(
        self,
        trigger_event: Dict[str, Any],
        agent_name: Optional[str] = None,
        limit: int = 5,
    ) -> List[EpisodicRecord]:
        """
        Find episodes with similar trigger events.

        Uses simple content similarity (could be enhanced with embeddings).
        """
        trigger_str = json.dumps(trigger_event, default=str).lower()
        trigger_words = set(trigger_str.split())

        scored = []
        for ep in self._episodes:
            if agent_name and ep.agent_name != agent_name:
                continue

            ep_str = json.dumps(ep.trigger_event, default=str).lower()
            ep_words = set(ep_str.split())

            # Jaccard similarity
            if trigger_words and ep_words:
                intersection = trigger_words & ep_words
                union = trigger_words | ep_words
                similarity = len(intersection) / len(union) if union else 0
            else:
                similarity = 0

            if similarity > 0.1:
                scored.append((similarity, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]

    def get_lessons(
        self,
        agent_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[str]:
        """Extract lessons from recent episodes."""
        episodes = self.get_recent(agent_name=agent_name, n=50)
        lessons = []
        for ep in episodes:
            lessons.extend(ep.lessons_learned)
        return lessons[-limit:]

    def get_failure_patterns(
        self,
        agent_name: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Analyze failure patterns from episodes."""
        failures = self.get_recent(agent_name=agent_name, n=100, success_only=False)

        # Group failures by error type
        error_types: Dict[str, int] = Counter()
        for ep in failures:
            error = ep.result.get("error", "unknown")
            error_types[error] += 1

        return [
            {"error": error, "count": count}
            for error, count in error_types.most_common(limit)
        ]

    def should_consolidate(self, agent_name: str) -> bool:
        """Check if enough episodes exist to consolidate into patterns."""
        recent = self.get_recent(agent_name=agent_name, n=20)
        return len(recent) >= self._consolidation_threshold

    @property
    def size(self) -> int:
        return len(self._episodes)


# ════════════════════════════════════════════════════════════════════
# Long-term Memory — Distilled patterns
# ════════════════════════════════════════════════════════════════════


class LongTermMemory:
    """
    Long-term memory — distilled patterns and preferences.

    Cold, persistent. Stores patterns extracted from episodic memory
    through consolidation. These patterns influence future agent decisions.

    Pattern types:
    - preference: User/business preferences learned over time
    - rule: Behavioral rules derived from experience
    - trend: Market or behavioral trends
    - correlation: Observed correlations between events
    """

    def __init__(self, max_patterns: int = 200):
        self._patterns: Dict[str, LongTermPattern] = {}
        self._max_patterns = max_patterns

        # Indexes
        self._by_type: Dict[str, List[str]] = defaultdict(list)
        self._by_agent: Dict[str, List[str]] = defaultdict(list)

        self._logger = logger.bind(component="longterm_memory")

    def store(self, pattern: LongTermPattern) -> str:
        """Store or update a pattern."""
        # Check for existing similar pattern
        existing = self._find_similar(pattern)
        if existing:
            existing.reinforce(pattern.evidence_ids[0] if pattern.evidence_ids else "")
            self._logger.debug("pattern_reinforced", pattern_id=existing.pattern_id)
            return existing.pattern_id

        self._patterns[pattern.pattern_id] = pattern
        self._by_type[pattern.pattern_type].append(pattern.pattern_id)
        self._by_agent[pattern.agent_name].append(pattern.pattern_id)

        # Trim if over limit
        if len(self._patterns) > self._max_patterns:
            self._evict_weakest()

        self._logger.info(
            "pattern_stored",
            pattern_id=pattern.pattern_id,
            type=pattern.pattern_type,
            confidence=round(pattern.confidence, 3),
        )
        return pattern.pattern_id

    def retrieve(
        self,
        pattern_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[LongTermPattern]:
        """Retrieve patterns matching criteria."""
        patterns = list(self._patterns.values())

        if pattern_type:
            pattern_ids = set(self._by_type.get(pattern_type, []))
            patterns = [p for p in patterns if p.pattern_id in pattern_ids]

        if agent_name:
            pattern_ids = set(self._by_agent.get(agent_name, []))
            patterns = [p for p in patterns if p.pattern_id in pattern_ids]

        if min_confidence > 0:
            patterns = [p for p in patterns if p.confidence >= min_confidence]

        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns

    def get_strongest(
        self,
        agent_name: Optional[str] = None,
        limit: int = 10,
    ) -> List[LongTermPattern]:
        """Get the strongest (highest confidence) patterns."""
        return self.retrieve(agent_name=agent_name, min_confidence=0.3)[:limit]

    def consolidate_episode(self, episode: EpisodicRecord) -> Optional[LongTermPattern]:
        """
        Attempt to consolidate an episode into a long-term pattern.

        Called after recording episodes. If the episode reveals a
        learnable pattern, creates or reinforces a LongTermPattern.
        """
        # Extract potential patterns from the episode
        if not episode.success and episode.result.get("error"):
            # Failure → create an error-avoidance rule
            pattern = LongTermPattern(
                pattern_type="rule",
                description=f"Avoid action that caused: {episode.result.get('error', 'unknown')[:100]}",
                confidence=0.5,
                evidence_count=1,
                evidence_ids=[episode.episode_id],
                parameters={"error_type": episode.result.get("error", "")},
                agent_name=episode.agent_name,
            )
            return self.store(pattern)

        if episode.success and episode.duration_ms > 0:
            # Success → track performance pattern
            pattern = LongTermPattern(
                pattern_type="trend",
                description=f"Successful {episode.agent_name} action took {episode.duration_ms:.0f}ms",
                confidence=0.5,
                evidence_count=1,
                evidence_ids=[episode.episode_id],
                parameters={"avg_duration_ms": episode.duration_ms},
                agent_name=episode.agent_name,
            )
            return self.store(pattern)

        return None

    def decay_all(self, days: float = 30.0) -> int:
        """Decay all patterns. Returns count of patterns removed."""
        removed = 0
        to_remove = []
        for pid, pattern in self._patterns.items():
            days_since = (time.time() - pattern.last_reinforced) / 86400
            pattern.decay(days_since)
            if pattern.confidence < 0.1:
                to_remove.append(pid)

        for pid in to_remove:
            del self._patterns[pid]
            removed += 1

        return removed

    def _find_similar(self, pattern: LongTermPattern) -> Optional[LongTermPattern]:
        """Find an existing pattern similar to the given one."""
        for existing in self._patterns.values():
            if (existing.pattern_type == pattern.pattern_type
                    and existing.agent_name == pattern.agent_name
                    and existing.description[:50] == pattern.description[:50]):
                return existing
        return None

    def _evict_weakest(self) -> None:
        """Remove the weakest pattern to make room."""
        if not self._patterns:
            return
        weakest_id = min(self._patterns, key=lambda pid: self._patterns[pid].confidence)
        del self._patterns[weakest_id]

    @property
    def size(self) -> int:
        return len(self._patterns)


# ════════════════════════════════════════════════════════════════════
# TieredMemoryManager — Unified interface
# ════════════════════════════════════════════════════════════════════


class TieredMemoryManager:
    """
    Unified three-tier memory manager for Angavu agents.

    Integrates working, episodic, and long-term memory into a
    single interface that agents use during observe→think→act→reflect.

    Flow:
        1. observe() → items enter Working Memory
        2. think()   → Working Memory + Long-term patterns inform decisions
        3. act()     → results recorded as Episodic Memory
        4. reflect() → episodes consolidated into Long-term patterns

    Usage:
        memory = TieredMemoryManager(agent_name="soko_pulse")
        memory.working.add({"event": "price_update", "item": "nyanya"})
        context = memory.get_context_for_decision()
        memory.record_episode(trigger, decision, result)
    """

    def __init__(
        self,
        agent_name: str,
        working_max_tokens: int = 4000,
        episodic_max: int = 500,
        longterm_max: int = 200,
    ):
        self.agent_name = agent_name
        self.working = WorkingMemory(max_tokens=working_max_tokens)
        self.episodic = EpisodicMemory(max_episodes=episodic_max)
        self.longterm = LongTermMemory(max_patterns=longterm_max)

        self._session_id = uuid.uuid4().hex[:12]
        self._logger = logger.bind(agent=agent_name, component="tiered_memory")

    # ── Observe Phase ───────────────────────────────────────────────

    def on_observe(
        self,
        event_data: Dict[str, Any],
        importance: MemoryImportance = MemoryImportance.NORMAL,
        tags: Optional[List[str]] = None,
    ) -> MemoryItem:
        """Record an observed event in working memory."""
        return self.working.add(
            content=event_data,
            importance=importance,
            tags=tags or [],
            session_id=self._session_id,
            agent_name=self.agent_name,
        )

    # ── Think Phase ─────────────────────────────────────────────────

    def get_context_for_decision(self) -> Dict[str, Any]:
        """
        Get the full context for a decision.

        Combines:
        - Working memory (current context)
        - Relevant long-term patterns
        - Similar past episodes
        - Recent lessons
        """
        # Working memory context
        working_context = self.working.get_context(max_items=20)

        # Long-term patterns for this agent
        patterns = self.longterm.get_strongest(agent_name=self.agent_name, limit=5)
        pattern_dicts = [p.to_dict() for p in patterns]

        # Recent episodes
        recent_episodes = self.episodic.get_recent(agent_name=self.agent_name, n=5)
        episode_dicts = [e.to_dict() for e in recent_episodes]

        # Lessons
        lessons = self.episodic.get_lessons(agent_name=self.agent_name, limit=5)

        # Failure patterns to avoid
        failure_patterns = self.episodic.get_failure_patterns(agent_name=self.agent_name, limit=3)

        return {
            "working_memory": working_context,
            "longterm_patterns": pattern_dicts,
            "recent_episodes": episode_dicts,
            "lessons": lessons,
            "failure_patterns": failure_patterns,
            "memory_stats": self.get_stats(),
        }

    def get_relevant_patterns(
        self,
        context: Dict[str, Any],
        min_confidence: float = 0.5,
    ) -> List[LongTermPattern]:
        """Get patterns relevant to the current context."""
        # For now, return strongest patterns for this agent
        # Could be enhanced with semantic matching against context
        return self.longterm.get_strongest(
            agent_name=self.agent_name,
            limit=5,
        )

    # ── Act Phase ───────────────────────────────────────────────────

    def on_act_result(
        self,
        result_data: Dict[str, Any],
        importance: MemoryImportance = MemoryImportance.NORMAL,
    ) -> None:
        """Record act result in working memory."""
        self.working.add(
            content={"type": "act_result", **result_data},
            importance=importance,
            tags=["result"],
            session_id=self._session_id,
            agent_name=self.agent_name,
        )

    # ── Reflect Phase ───────────────────────────────────────────────

    def record_episode(
        self,
        trigger_event: Dict[str, Any],
        decision: Dict[str, Any],
        result: Dict[str, Any],
        duration_ms: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Record a complete episode and attempt consolidation.

        This is the key integration point between episodic and long-term memory.
        """
        episode = EpisodicRecord(
            agent_name=self.agent_name,
            session_id=self._session_id,
            trigger_event=trigger_event,
            decision=decision,
            result=result,
            duration_ms=duration_ms,
            success=result.get("success", True),
            tags=tags or [],
        )

        # Extract lessons from failures
        if not episode.success:
            error = result.get("error", "unknown")
            episode.lessons_learned.append(
                f"Failed: {error}. Avoid similar conditions."
            )

        # Record in episodic memory
        episode_id = self.episodic.record(episode)

        # Attempt consolidation to long-term memory
        if self.episodic.should_consolidate(self.agent_name):
            self._consolidate()

        self._logger.info(
            "episode_recorded",
            episode_id=episode_id,
            success=episode.success,
            duration_ms=round(duration_ms, 2),
        )

        return episode_id

    def _consolidate(self) -> None:
        """
        Consolidate recent episodes into long-term patterns.

        Called when enough episodes have accumulated.
        This is the memory consolidation step inspired by
        DarwinMem's evolutionary memory optimization.
        """
        recent = self.episodic.get_recent(agent_name=self.agent_name, n=20)

        consolidated = 0
        for episode in recent:
            pattern = self.longterm.consolidate_episode(episode)
            if pattern:
                consolidated += 1

        if consolidated > 0:
            self._logger.info(
                "memory_consolidated",
                episodes_processed=len(recent),
                patterns_created=consolidated,
            )

    # ── Error Recording ─────────────────────────────────────────────

    def on_error(
        self,
        error_data: Dict[str, Any],
    ) -> None:
        """Record an error with critical importance."""
        self.working.add(
            content={"type": "error", **error_data},
            importance=MemoryImportance.CRITICAL,
            tags=["error"],
            session_id=self._session_id,
            agent_name=self.agent_name,
        )

    # ── Maintenance ─────────────────────────────────────────────────

    def maintenance(self) -> Dict[str, Any]:
        """
        Periodic memory maintenance.

        - Decay long-term patterns
        - Consolidate recent episodes
        - Report memory health
        """
        decayed = self.longterm.decay_all(days=30)
        consolidated = 0
        if self.episodic.should_consolidate(self.agent_name):
            self._consolidate()
            consolidated = 1

        stats = self.get_stats()
        stats["maintenance"] = {
            "patterns_decayed": decayed,
            "consolidation_triggered": consolidated > 0,
        }

        self._logger.info("memory_maintenance", **stats["maintenance"])
        return stats

    # ── Stats ───────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            "agent": self.agent_name,
            "session_id": self._session_id,
            "working_memory": self.working.token_usage,
            "episodic_memory": {"episodes": self.episodic.size},
            "longterm_memory": {"patterns": self.longterm.size},
        }
