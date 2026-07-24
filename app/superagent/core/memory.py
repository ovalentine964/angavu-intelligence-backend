"""
Unified Memory System

Replaces the scattered memory implementations across agents.
Provides working memory, episodic memory, and semantic memory.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    """A single memory entry."""
    content: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    relevance: float = 1.0


class WorkingMemory:
    """Short-term context for current task execution."""

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.entries: list[MemoryEntry] = []
        self.token_count = 0

    def add(self, entry: dict) -> None:
        """Add an entry to working memory."""
        mem_entry = MemoryEntry(content=entry)
        self.entries.append(mem_entry)
        # Approximate token count (rough: 1 token per 4 chars)
        entry_str = str(entry)
        self.token_count += len(entry_str) // 4

        # Evict oldest entries if over limit
        while self.token_count > self.max_tokens and len(self.entries) > 1:
            removed = self.entries.pop(0)
            removed_str = str(removed.content)
            self.token_count -= len(removed_str) // 4

    def get_context(self) -> str:
        """Get current working memory as context string."""
        if not self.entries:
            return ""
        parts = []
        for entry in self.entries[-10:]:  # Last 10 entries
            content = entry.content
            entry_type = content.get("type", "unknown")
            if entry_type == "thought":
                parts.append(f"Thought: {content.get('reasoning', '')}")
            elif entry_type == "observation":
                insights = content.get("insights", [])
                parts.append(f"Observed: {', '.join(str(i) for i in insights)}")
            else:
                parts.append(f"{entry_type}: {str(content)[:200]}")
        return " | ".join(parts)

    def clear(self) -> None:
        """Clear working memory."""
        self.entries = []
        self.token_count = 0

    def get_recent(self, n: int = 5) -> list[dict]:
        """Get the N most recent entries."""
        return [e.content for e in self.entries[-n:]]


class EpisodicMemory:
    """Long-term storage of past interactions and outcomes."""

    def __init__(self, max_episodes: int = 5000):
        self.episodes: list[dict] = []
        self._max_episodes = max_episodes

    async def store(self, episode: dict) -> None:
        """Store an episode (interaction + outcome)."""
        episode.setdefault("stored_at", time.time())
        self.episodes.append(episode)

        # Trim old episodes
        if len(self.episodes) > self._max_episodes:
            self.episodes = self.episodes[-(self._max_episodes // 2):]

    async def recall(self, query: str, top_k: int = 5) -> list[dict]:
        """Recall relevant episodes by keyword matching."""
        if not self.episodes:
            return []

        query_lower = query.lower()
        scored: list[tuple[float, dict]] = []

        for ep in self.episodes:
            # Simple keyword relevance scoring
            ep_str = str(ep).lower()
            score = 0.0
            for word in query_lower.split():
                if word in ep_str:
                    score += 1.0
            if score > 0:
                scored.append((score, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:top_k]]

    def get_recent(self, n: int = 10) -> list[dict]:
        """Get the N most recent episodes."""
        return self.episodes[-n:]

    def get_stats(self) -> dict:
        """Get memory statistics."""
        return {
            "total_episodes": len(self.episodes),
            "max_episodes": self._max_episodes,
        }


class SemanticMemory:
    """Structured knowledge storage (facts, relationships, rules)."""

    def __init__(self):
        self.knowledge: dict[str, list[dict]] = defaultdict(list)

    async def add_fact(self, subject: str, predicate: str, obj: Any) -> None:
        """Add a knowledge triple."""
        self.knowledge[subject].append({
            "predicate": predicate,
            "object": obj,
            "timestamp": time.time(),
        })

    async def query(self, pattern: dict) -> list[dict]:
        """Query knowledge graph by pattern."""
        subject = pattern.get("subject")
        predicate = pattern.get("predicate")

        if subject:
            facts = self.knowledge.get(subject, [])
            if predicate:
                return [f for f in facts if f.get("predicate") == predicate]
            return facts

        # Search all subjects
        results = []
        for subj, facts in self.knowledge.items():
            for fact in facts:
                if predicate and fact.get("predicate") != predicate:
                    continue
                results.append({"subject": subj, **fact})
        return results

    def get_all_facts(self) -> dict[str, list[dict]]:
        """Get all stored facts."""
        return dict(self.knowledge)

    def get_stats(self) -> dict:
        """Get memory statistics."""
        total_facts = sum(len(facts) for facts in self.knowledge.values())
        return {
            "subjects": len(self.knowledge),
            "total_facts": total_facts,
        }
