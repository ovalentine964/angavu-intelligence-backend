"""
Context Manager — Factor 3: Own Your Context Window.

Proactively manages agent context to stay within token limits.
Tracks usage, summarizes old context, prioritizes recent/important items,
and compresses repeated patterns.

Mathematical foundation:
- Sliding window with priority-weighted eviction
- Exponential decay for recency scoring
- Frequency-based importance for pattern compression
"""

from __future__ import annotations

import hashlib
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class ContextPriority(int, Enum):
    """Priority levels for context items. Higher = more important."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4  # Errors, strategy adjustments, active task state


@dataclass
class ContextItem:
    """A single item in the agent's context window."""
    content: Dict[str, Any]
    priority: ContextPriority = ContextPriority.NORMAL
    token_estimate: int = 0  # Approximate token count
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    item_id: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.item_id:
            # Deterministic ID from content hash
            raw = str(sorted(self.content.items()))
            self.item_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.token_estimate:
            # Rough estimate: ~4 chars per token
            self.token_estimate = max(1, len(str(self.content)) // 4)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def recency_score(self) -> float:
        """Exponential decay score based on age. Fresh = 1.0, old → 0."""
        half_life = 300.0  # 5 minutes
        age = self.age_seconds
        return 2.0 ** (-age / half_life)

    @property
    def importance_score(self) -> float:
        """Combined priority + recency + access frequency score."""
        priority_weight = self.priority.value / ContextPriority.CRITICAL.value
        recency_weight = self.recency_score
        frequency_weight = min(1.0, self.access_count / 5.0)
        return (0.4 * priority_weight) + (0.4 * recency_weight) + (0.2 * frequency_weight)


@dataclass
class ContextSummary:
    """A compressed summary of evicted context items."""
    original_ids: List[str]
    summary_text: str
    token_estimate: int
    item_count: int
    time_range: Tuple[float, float]
    created_at: float = field(default_factory=time.time)


class ContextManager:
    """
    Proactive context window manager for Angavu agents.

    Manages a token-budgeted context window with:
    - Priority-based retention (errors > recent > old)
    - Automatic summarization when approaching limits
    - Pattern compression for repeated observations
    - Token usage tracking per agent

    Usage:
        ctx = ContextManager(agent_name="soko_pulse", max_tokens=4000)
        ctx.add({"event": "price_update", "item": "nyanya", "price": 50})
        context = ctx.get_context()  # Returns what fits in budget
    """

    def __init__(
        self,
        agent_name: str,
        max_tokens: int = 4000,
        summarizer: Optional[Callable[[List[ContextItem]], str]] = None,
        compression_threshold: float = 0.8,  # Trigger compression at 80% full
    ):
        self.agent_name = agent_name
        self.max_tokens = max_tokens
        self.compression_threshold = compression_threshold
        self._summarizer = summarizer or self._default_summarizer

        self._items: List[ContextItem] = []
        self._summaries: List[ContextSummary] = []
        self._total_tokens: int = 0
        self._eviction_count: int = 0
        self._compression_count: int = 0

        # Pattern tracking for compression
        self._pattern_counter: Counter = Counter()
        self._pattern_items: Dict[str, List[ContextItem]] = defaultdict(list)

        self._logger = logger.bind(agent=agent_name, component="context_manager")

    # ── Public API ──────────────────────────────────────────────────

    def add(
        self,
        content: Dict[str, Any],
        priority: ContextPriority = ContextPriority.NORMAL,
        tags: Optional[List[str]] = None,
    ) -> ContextItem:
        """Add an item to the context window. Triggers compression if needed."""
        item = ContextItem(
            content=content,
            priority=priority,
            tags=tags or [],
        )

        # Track patterns before adding
        pattern_key = self._extract_pattern_key(content)
        if pattern_key:
            self._pattern_counter[pattern_key] += 1
            self._pattern_items[pattern_key].append(item)

        self._items.append(item)
        self._total_tokens += item.token_estimate

        # Proactive compression if approaching limit
        if self._total_tokens > self.max_tokens * self.compression_threshold:
            self._compress()

        self._logger.debug(
            "context_item_added",
            item_id=item.item_id,
            tokens=item.token_estimate,
            total_tokens=self._total_tokens,
            max_tokens=self.max_tokens,
        )

        return item

    def get_context(
        self,
        max_items: Optional[int] = None,
        include_summaries: bool = True,
        filter_tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get the current context window, fitting within token budget.

        Returns a dict with:
        - items: prioritized list of context items
        - summaries: compressed summaries of old context
        - token_usage: current vs max tokens
        - patterns: detected repeated patterns
        """
        # Filter items
        items = self._items
        if filter_tags:
            items = [i for i in items if any(t in i.tags for t in filter_tags)]

        # Sort by importance (highest first)
        items.sort(key=lambda i: i.importance_score, reverse=True)

        # Fit within budget
        budget = self.max_tokens
        fitted_items = []
        used_tokens = 0

        # Summaries take priority (they're compressed)
        summaries_to_include = []
        if include_summaries:
            for s in self._summaries[-3:]:  # Last 3 summaries
                if used_tokens + s.token_estimate <= budget:
                    summaries_to_include.append(s)
                    used_tokens += s.token_estimate

        # Then add items by importance
        for item in items:
            if max_items and len(fitted_items) >= max_items:
                break
            if used_tokens + item.token_estimate > budget:
                break
            item.access_count += 1
            item.last_accessed = time.time()
            fitted_items.append(item)
            used_tokens += item.token_estimate

        # Detect patterns
        patterns = self._detect_patterns()

        return {
            "items": [i.content for i in fitted_items],
            "summaries": [
                {"text": s.summary_text, "item_count": s.item_count}
                for s in summaries_to_include
            ],
            "token_usage": {
                "current": self._total_tokens,
                "max": self.max_tokens,
                "utilization": round(self._total_tokens / self.max_tokens, 2),
                "fitted_tokens": used_tokens,
            },
            "patterns": patterns,
            "item_count": len(self._items),
            "summary_count": len(self._summaries),
        }

    def get_token_usage(self) -> Dict[str, Any]:
        """Get current token usage statistics."""
        return {
            "agent": self.agent_name,
            "current_tokens": self._total_tokens,
            "max_tokens": self.max_tokens,
            "utilization": round(self._total_tokens / self.max_tokens, 2),
            "item_count": len(self._items),
            "summary_count": len(self._summaries),
            "eviction_count": self._eviction_count,
            "compression_count": self._compression_count,
            "top_patterns": self._pattern_counter.most_common(5),
        }

    def clear(self) -> None:
        """Clear all context items and summaries."""
        self._items.clear()
        self._summaries.clear()
        self._total_tokens = 0
        self._pattern_counter.clear()
        self._pattern_items.clear()
        self._logger.info("context_cleared")

    # ── Compression Engine ──────────────────────────────────────────

    def _compress(self) -> None:
        """
        Compress context when approaching token limit.

        Strategy:
        1. Compress repeated patterns into single summary items
        2. Summarize oldest low-priority items
        3. Evict lowest-importance items if still over budget
        """
        self._logger.info(
            "context_compression_triggered",
            total_tokens=self._total_tokens,
            max_tokens=self.max_tokens,
        )

        # Step 1: Compress repeated patterns
        self._compress_patterns()

        # Step 2: Summarize old items if still over budget
        if self._total_tokens > self.max_tokens * self.compression_threshold:
            self._summarize_old_items()

        # Step 3: Hard eviction if still over
        if self._total_tokens > self.max_tokens:
            self._evict_lowest_importance()

        self._compression_count += 1

    def _compress_patterns(self) -> None:
        """Compress repeated event patterns into single summary items."""
        for pattern_key, count in self._pattern_counter.items():
            if count < 3:
                continue  # Need at least 3 repetitions

            items = self._pattern_items.get(pattern_key, [])
            if len(items) < 3:
                continue

            # Create a summary of the pattern
            summary = ContextSummary(
                original_ids=[i.item_id for i in items],
                summary_text=f"Pattern '{pattern_key}' repeated {count} times. "
                             f"Latest: {items[-1].content}",
                token_estimate=max(10, len(pattern_key) + 20),  # Much smaller
                item_count=len(items),
                time_range=(items[0].created_at, items[-1].created_at),
            )

            # Remove the original items
            ids_to_remove = {i.item_id for i in items}
            removed_tokens = sum(
                i.token_estimate for i in self._items
                if i.item_id in ids_to_remove
            )

            self._items = [i for i in self._items if i.item_id not in ids_to_remove]
            self._total_tokens -= removed_tokens
            self._summaries.append(summary)
            self._total_tokens += summary.token_estimate
            self._eviction_count += len(items)

            # Clear pattern tracking
            self._pattern_items[pattern_key] = []
            self._pattern_counter[pattern_key] = 0

            self._logger.info(
                "pattern_compressed",
                pattern=pattern_key,
                items_removed=len(items),
                tokens_saved=removed_tokens - summary.token_estimate,
            )

    def _summarize_old_items(self) -> None:
        """Summarize the oldest, lowest-priority items."""
        # Sort by age (oldest first), then by priority (lowest first)
        sorted_items = sorted(
            self._items,
            key=lambda i: (i.created_at, i.priority.value),
        )

        # Take bottom 20% for summarization
        count = max(1, len(sorted_items) // 5)
        to_summarize = sorted_items[:count]

        if not to_summarize:
            return

        summary_text = self._summarizer(to_summarize)
        summary = ContextSummary(
            original_ids=[i.item_id for i in to_summarize],
            summary_text=summary_text,
            token_estimate=max(15, len(summary_text) // 4),
            item_count=len(to_summarize),
            time_range=(to_summarize[0].created_at, to_summarize[-1].created_at),
        )

        ids_to_remove = {i.item_id for i in to_summarize}
        removed_tokens = sum(
            i.token_estimate for i in self._items if i.item_id in ids_to_remove
        )

        self._items = [i for i in self._items if i.item_id not in ids_to_remove]
        self._total_tokens -= removed_tokens
        self._summaries.append(summary)
        self._total_tokens += summary.token_estimate
        self._eviction_count += len(to_summarize)

        self._logger.info(
            "items_summarized",
            count=len(to_summarize),
            tokens_saved=removed_tokens - summary.token_estimate,
        )

    def _evict_lowest_importance(self) -> None:
        """Hard-evict lowest-importance items until under budget."""
        # Sort by importance (lowest first)
        self._items.sort(key=lambda i: i.importance_score)

        while self._total_tokens > self.max_tokens and self._items:
            item = self._items.pop(0)
            self._total_tokens -= item.token_estimate
            self._eviction_count += 1

            self._logger.debug(
                "item_evicted",
                item_id=item.item_id,
                importance=item.importance_score,
                tokens=item.token_estimate,
            )

    # ── Pattern Detection ───────────────────────────────────────────

    def _extract_pattern_key(self, content: Dict[str, Any]) -> Optional[str]:
        """Extract a pattern key from content for compression tracking."""
        # Use event type + primary entity as pattern key
        event_type = content.get("event_type", content.get("type", ""))
        source = content.get("source", "")
        if event_type:
            return f"{event_type}:{source}"
        return None

    def _detect_patterns(self) -> List[Dict[str, Any]]:
        """Detect repeated patterns in current context."""
        patterns = []
        for key, count in self._pattern_counter.most_common(5):
            if count >= 2:
                patterns.append({
                    "pattern": key,
                    "count": count,
                    "compressed": count < 3,  # Not yet compressed
                })
        return patterns

    # ── Default Summarizer ──────────────────────────────────────────

    @staticmethod
    def _default_summarizer(items: List[ContextItem]) -> str:
        """Default summarizer: extract key fields from items."""
        if not items:
            return ""

        # Group by event type
        by_type: Dict[str, int] = Counter()
        for item in items:
            etype = item.content.get("event_type", item.content.get("type", "unknown"))
            by_type[etype] += 1

        parts = [f"{count}x {etype}" for etype, count in by_type.items()]
        time_span = items[-1].created_at - items[0].created_at
        return f"Summary of {len(items)} items over {time_span:.0f}s: {', '.join(parts)}"


class AgentContextManager:
    """
    Per-agent context manager that integrates with AngavuAgent.

    Wraps ContextManager with agent-specific hooks for automatic
    context management during observe/think/act/reflect cycles.
    """

    def __init__(
        self,
        agent_name: str,
        max_tokens: int = 4000,
        auto_add_events: bool = True,
    ):
        self.context_manager = ContextManager(
            agent_name=agent_name,
            max_tokens=max_tokens,
        )
        self.auto_add_events = auto_add_events
        self._logger = logger.bind(agent=agent_name, component="agent_context")

    def on_observe(self, event_data: Dict[str, Any]) -> None:
        """Called when agent observes an event. Adds to context."""
        if not self.auto_add_events:
            return

        # Determine priority based on event type
        event_type = event_data.get("event_type", "")
        if "error" in event_type.lower():
            priority = ContextPriority.HIGH
        elif "feedback" in event_type.lower():
            priority = ContextPriority.HIGH
        elif "health" in event_type.lower():
            priority = ContextPriority.LOW
        else:
            priority = ContextPriority.NORMAL

        self.context_manager.add(
            content=event_data,
            priority=priority,
            tags=[event_type],
        )

    def on_act_result(self, result_data: Dict[str, Any]) -> None:
        """Called after act phase. Adds result to context."""
        success = result_data.get("success", True)
        priority = ContextPriority.NORMAL if success else ContextPriority.HIGH

        self.context_manager.add(
            content={"type": "act_result", **result_data},
            priority=priority,
            tags=["result", "success" if success else "failure"],
        )

    def on_error(self, error_data: Dict[str, Any]) -> None:
        """Called on error. Adds with high priority."""
        self.context_manager.add(
            content={"type": "error", **error_data},
            priority=ContextPriority.CRITICAL,
            tags=["error"],
        )

    def get_context_for_think(self) -> Dict[str, Any]:
        """Get optimized context for the think phase."""
        return self.context_manager.get_context()

    def get_usage(self) -> Dict[str, Any]:
        """Get token usage stats."""
        return self.context_manager.get_token_usage()
