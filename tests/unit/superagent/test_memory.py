"""
Tests for the 3-tier Unified Memory System.

Tests WorkingMemory, EpisodicMemory, and SemanticMemory
with their actual implementations.
"""

import pytest
import time

from app.superagent.core.memory import (
    WorkingMemory,
    EpisodicMemory,
    SemanticMemory,
    MemoryEntry,
)


class TestWorkingMemory:
    """Test short-term working memory."""

    def test_init_defaults(self):
        wm = WorkingMemory()
        assert wm.max_tokens == 8000
        assert wm.entries == []
        assert wm.token_count == 0

    def test_init_custom_max_tokens(self):
        wm = WorkingMemory(max_tokens=4000)
        assert wm.max_tokens == 4000

    def test_add_entry(self):
        wm = WorkingMemory()
        wm.add({"type": "thought", "reasoning": "test"})
        assert len(wm.entries) == 1
        assert wm.token_count > 0

    def test_add_multiple_entries(self):
        wm = WorkingMemory()
        wm.add({"type": "thought", "data": "a"})
        wm.add({"type": "observation", "data": "b"})
        assert len(wm.entries) == 2

    def test_get_context_empty(self):
        wm = WorkingMemory()
        assert wm.get_context() == ""

    def test_get_context_with_entries(self):
        wm = WorkingMemory()
        wm.add({"type": "thought", "reasoning": "analyzing sales"})
        wm.add({"type": "observation", "insights": ["high volume"]})

        context = wm.get_context()
        assert "analyzing sales" in context
        assert "high volume" in context

    def test_clear_resets_state(self):
        wm = WorkingMemory()
        wm.add({"key": "value"})
        wm.clear()
        assert wm.entries == []
        assert wm.token_count == 0

    def test_eviction_when_over_limit(self):
        wm = WorkingMemory(max_tokens=50)
        # Add entries that exceed the limit
        for i in range(20):
            wm.add({"type": "test", "data": "x" * 100})

        # Should have evicted some entries
        assert wm.token_count <= wm.max_tokens + 50  # some tolerance

    def test_get_recent(self):
        wm = WorkingMemory()
        for i in range(10):
            wm.add({"index": i})

        recent = wm.get_recent(3)
        assert len(recent) == 3
        assert recent[0]["index"] == 7
        assert recent[2]["index"] == 9


class TestMemoryEntry:
    """Test the MemoryEntry dataclass."""

    def test_entry_creation(self):
        entry = MemoryEntry(content={"key": "value"})
        assert entry.content == {"key": "value"}
        assert entry.relevance == 1.0
        assert entry.timestamp > 0

    def test_entry_custom_relevance(self):
        entry = MemoryEntry(content={}, relevance=0.5)
        assert entry.relevance == 0.5


class TestEpisodicMemory:
    """Test long-term episodic memory."""

    def test_init(self):
        em = EpisodicMemory()
        assert em.episodes == []

    def test_init_custom_max(self):
        em = EpisodicMemory(max_episodes=100)
        assert em._max_episodes == 100

    @pytest.mark.asyncio
    async def test_store_episode(self):
        em = EpisodicMemory()
        await em.store({"interaction": "test", "outcome": "success"})
        assert len(em.episodes) == 1
        assert "stored_at" in em.episodes[0]

    @pytest.mark.asyncio
    async def test_store_adds_timestamp(self):
        em = EpisodicMemory()
        await em.store({"data": "test"})
        assert em.episodes[0]["stored_at"] > 0

    @pytest.mark.asyncio
    async def test_recall_by_keyword(self):
        em = EpisodicMemory()
        await em.store({"interaction": "sold mandazi", "amount": 500})
        await em.store({"interaction": "bought unga", "amount": 200})
        await em.store({"interaction": "sold chai", "amount": 100})

        results = await em.recall("mandazi")
        assert len(results) == 1
        assert "mandazi" in str(results[0])

    @pytest.mark.asyncio
    async def test_recall_top_k(self):
        em = EpisodicMemory()
        for i in range(10):
            await em.store({"data": f"sale {i}", "type": "sale"})

        results = await em.recall("sale", top_k=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_recall_empty(self):
        em = EpisodicMemory()
        results = await em.recall("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_recall_no_match(self):
        em = EpisodicMemory()
        await em.store({"data": "mandazi sale"})
        results = await em.recall("xyz_nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_eviction_at_max(self):
        em = EpisodicMemory(max_episodes=10)
        for i in range(15):
            await em.store({"index": i})
        # Should have evicted down to half
        assert len(em.episodes) <= 10

    def test_get_recent(self):
        em = EpisodicMemory()
        em.episodes = [{"i": i} for i in range(20)]
        recent = em.get_recent(5)
        assert len(recent) == 5
        assert recent[0]["i"] == 15

    def test_get_stats(self):
        em = EpisodicMemory()
        em.episodes = [{"i": 1}, {"i": 2}]
        stats = em.get_stats()
        assert stats["total_episodes"] == 2


class TestSemanticMemory:
    """Test structured semantic/knowledge memory."""

    def test_init(self):
        sm = SemanticMemory()
        assert sm.knowledge is not None

    @pytest.mark.asyncio
    async def test_add_fact(self):
        sm = SemanticMemory()
        await sm.add_fact("mandazi", "price", 20)
        assert "mandazi" in sm.knowledge
        assert len(sm.knowledge["mandazi"]) == 1
        assert sm.knowledge["mandazi"][0]["predicate"] == "price"
        assert sm.knowledge["mandazi"][0]["object"] == 20

    @pytest.mark.asyncio
    async def test_add_multiple_facts(self):
        sm = SemanticMemory()
        await sm.add_fact("mandazi", "price", 20)
        await sm.add_fact("mandazi", "category", "food")
        await sm.add_fact("chai", "price", 10)

        assert len(sm.knowledge["mandazi"]) == 2
        assert len(sm.knowledge["chai"]) == 1

    @pytest.mark.asyncio
    async def test_query_by_subject(self):
        sm = SemanticMemory()
        await sm.add_fact("mandazi", "price", 20)
        await sm.add_fact("chai", "price", 10)

        results = await sm.query({"subject": "mandazi"})
        assert len(results) == 1
        assert results[0]["object"] == 20

    @pytest.mark.asyncio
    async def test_query_by_predicate(self):
        sm = SemanticMemory()
        await sm.add_fact("mandazi", "price", 20)
        await sm.add_fact("chai", "price", 10)
        await sm.add_fact("mandazi", "category", "food")

        results = await sm.query({"predicate": "price"})
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_by_subject_and_predicate(self):
        sm = SemanticMemory()
        await sm.add_fact("mandazi", "price", 20)
        await sm.add_fact("mandazi", "category", "food")

        results = await sm.query({"subject": "mandazi", "predicate": "price"})
        assert len(results) == 1
        assert results[0]["object"] == 20

    @pytest.mark.asyncio
    async def test_query_all(self):
        sm = SemanticMemory()
        await sm.add_fact("mandazi", "price", 20)
        await sm.add_fact("chai", "price", 10)

        results = await sm.query({})
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_empty(self):
        sm = SemanticMemory()
        results = await sm.query({"subject": "nonexistent"})
        assert results == []

    def test_get_all_facts(self):
        sm = SemanticMemory()
        sm.knowledge["mandazi"].append({"predicate": "price", "object": 20, "timestamp": time.time()})
        facts = sm.get_all_facts()
        assert "mandazi" in facts

    def test_get_stats(self):
        sm = SemanticMemory()
        sm.knowledge["a"].append({"predicate": "p", "object": 1, "timestamp": 0})
        sm.knowledge["b"].append({"predicate": "q", "object": 2, "timestamp": 0})
        stats = sm.get_stats()
        assert stats["subjects"] == 2
        assert stats["total_facts"] == 2
