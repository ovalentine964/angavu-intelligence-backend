"""
Hermes Agent Protocol — Full Implementation for Angavu Intelligence Backend.

Implements Nous Research's self-evolving AI agent pattern:
    Worker-keyed sessions → Skill discovery → Closed learning loop
    → Memory consolidation (short-term → long-term)

Key design principles:
    1. Sessions keyed by WORKER (not channel) — cross-channel continuity
    2. Skills are Markdown documents capturing reusable procedures
    3. Closed learning loop: task → trace → feedback → skill improvement
    4. Memory consolidation: ephemeral context → persistent knowledge

Architecture:
    ┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
    │  SessionSync │────▶│  HermesService   │────▶│  SkillGenerator │
    │  (worker-key)│     │  (orchestrator)  │     │  (closed loop)  │
    └─────────────┘     └──────────────────┘     └─────────────────┘
            │                    │                        │
            │                    ▼                        │
            │            ┌──────────────┐                 │
            └───────────▶│  MemoryLayer │◀────────────────┘
                         │  (L1/L2/L3)  │
                         └──────────────┘

Integration points:
    - Wired into AgentFactory.create_all() via _attach_hermes()
    - Publishes/subscribes via EventBus for inter-agent coordination
    - Exposes REST API endpoints for session management
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

from app.channels.session_sync import SessionSync, Session, Interaction
from app.agents.skill_generator import (
    SkillGenerator,
    GeneratedSkill,
    InteractionTrace,
    SkillCategory,
)
from app.agents.event_bus import EventBus

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Constants & Configuration
# ════════════════════════════════════════════════════════════════════

# Memory consolidation thresholds
SHORT_TERM_MAX_INTERACTIONS = 50       # Before consolidation kicks in
LONG_TERM_SUMMARY_MIN_LENGTH = 100     # Min chars for a meaningful summary
MEMORY_CONSOLIDATION_INTERVAL_S = 3600 # Every hour

# Skill discovery confidence threshold
SKILL_DISCOVERY_MIN_CONFIDENCE = 0.6

# Worker activity tracking
WORKER_ACTIVITY_WINDOW_S = 86400  # 24 hours


class HermesEventType(str, Enum):
    """Hermes-specific event types for the event bus."""
    SESSION_CREATED = "hermes.session.created"
    SESSION_RESUMED = "hermes.session.resumed"
    SKILL_DISCOVERED = "hermes.skill.discovered"
    SKILL_APPLIED = "hermes.skill.applied"
    SKILL_IMPROVED = "hermes.skill.improved"
    MEMORY_CONSOLIDATED = "hermes.memory.consolidated"
    LEARNING_LOOP_COMPLETED = "hermes.learning.loop.completed"
    FEEDBACK_RECEIVED = "hermes.feedback.received"


# ════════════════════════════════════════════════════════════════════
# Data Classes
# ════════════════════════════════════════════════════════════════════


@dataclass
class WorkerProfile:
    """
    Aggregated profile for a worker, built across sessions.

    Captures behavioral patterns, preferences, and skill affinities
    that persist beyond individual sessions.
    """

    worker_id: str
    first_seen: str = ""
    last_active: str = ""
    total_interactions: int = 0
    preferred_language: str = "sw"
    preferred_channel: str = ""
    business_domain: str = ""  # retail, agriculture, transport, etc.
    skill_affinities: Dict[str, float] = field(default_factory=dict)
    # category → affinity score (0.0-1.0)
    frequent_topics: List[str] = field(default_factory=list)
    correction_patterns: Dict[str, int] = field(default_factory=dict)
    # correction_type → count
    satisfaction_trend: List[float] = field(default_factory=list)
    # Rolling window of satisfaction scores


@dataclass
class MemoryConsolidation:
    """Result of a memory consolidation pass."""

    worker_id: str
    interactions_consolidated: int
    patterns_extracted: int
    summary: str
    topics: List[str]
    timestamp: str


@dataclass
class HermesSessionState:
    """Extended session state for Hermes protocol."""

    session: Session
    trace_id: Optional[str] = None
    active_skills: List[str] = field(default_factory=list)
    # skill_ids being used in this session
    pending_feedback: List[Dict[str, Any]] = field(default_factory=list)
    # feedback waiting to be processed
    context_window: List[Dict[str, Any]] = field(default_factory=list)
    # Recent interactions for context
    last_skill_search: Optional[str] = None
    last_skill_search_result: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# Hermes Service
# ════════════════════════════════════════════════════════════════════


class HermesService:
    """
    Full Hermes Agent Protocol implementation.

    Orchestrates the closed learning loop:
        1. Worker sends message → session lookup (worker-keyed)
        2. Skill discovery: search existing skills for the query
        3. Execute with skill context (if found)
        4. Trace the interaction
        5. On completion: check if complex+successful → generate skill
        6. On feedback: update skill confidence → improve
        7. Periodically: consolidate short-term → long-term memory

    Thread-safe: all mutable state is protected by asyncio locks.
    """

    def __init__(
        self,
        session_sync: SessionSync,
        skill_generator: SkillGenerator,
        event_bus: Optional[EventBus] = None,
    ):
        self._session_sync = session_sync
        self._skill_generator = skill_generator
        self._event_bus = event_bus

        # Worker profiles (in-memory, persisted via session context)
        self._profiles: Dict[str, WorkerProfile] = {}

        # Active Hermes sessions (worker_id → state)
        self._hermes_sessions: Dict[str, HermesSessionState] = {}

        # Memory consolidation state
        self._last_consolidation: Dict[str, float] = {}  # worker_id → timestamp
        self._consolidation_summaries: Dict[str, List[str]] = {}

        # Skill application callbacks (skill_category → handler)
        self._skill_handlers: Dict[str, Callable[..., Coroutine]] = {}

        # Background task references
        self._background_tasks: List[asyncio.Task] = []

        self._logger = logger.bind(component="hermes_service")

    # ── Lifecycle ──────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the Hermes service. Call after SessionSync.initialize()."""
        self._logger.info("hermes_service_initializing")
        # Register default skill handlers
        self._register_default_skill_handlers()
        self._logger.info("hermes_service_initialized")

    async def shutdown(self) -> None:
        """Gracefully shut down the Hermes service."""
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        self._background_tasks.clear()
        self._logger.info("hermes_service_shutdown")

    # ── Session Management (Worker-Keyed) ──────────────────────────

    async def get_or_create_hermes_session(
        self,
        worker_id: str,
        channel: str = "app_text",
    ) -> HermesSessionState:
        """
        Get or create a Hermes session for a worker.

        Sessions are keyed by WORKER, not channel. A worker who switches
        from app to WhatsApp keeps their full Hermes context.

        Args:
            worker_id: The worker's unique identifier
            channel: The current channel (app_text, whatsapp, ussd, etc.)

        Returns:
            HermesSessionState with full context
        """
        from app.channels.adapters.base import ChannelType

        # Map channel string to ChannelType
        channel_type = self._resolve_channel_type(channel)

        # Get or create base session via SessionSync
        session = await self._session_sync.get_or_create_session(
            worker_id=worker_id,
            channel=channel_type,
        )

        # Get or create Hermes state
        if worker_id not in self._hermes_sessions:
            hermes_state = HermesSessionState(session=session)
            self._hermes_sessions[worker_id] = hermes_state

            # Load worker profile
            await self._load_worker_profile(worker_id)

            # Publish session created event
            await self._publish_event(
                HermesEventType.SESSION_CREATED,
                {
                    "worker_id": worker_id,
                    "session_id": session.session_id,
                    "channel": channel,
                    "is_new": session.interaction_count == 0,
                },
            )

            self._logger.info(
                "hermes_session_created",
                worker_id=worker_id,
                session_id=session.session_id,
            )
        else:
            hermes_state = self._hermes_sessions[worker_id]
            hermes_state.session = session  # Update base session reference

            # Publish session resumed event
            await self._publish_event(
                HermesEventType.SESSION_RESUMED,
                {
                    "worker_id": worker_id,
                    "session_id": session.session_id,
                    "channel": channel,
                    "interaction_count": session.interaction_count,
                },
            )

        return hermes_state

    async def get_worker_profile(self, worker_id: str) -> WorkerProfile:
        """Get or create a worker profile."""
        if worker_id not in self._profiles:
            await self._load_worker_profile(worker_id)
        return self._profiles[worker_id]

    # ── Skill Discovery ───────────────────────────────────────────

    async def discover_skills(
        self,
        worker_id: str,
        query: str,
        limit: int = 3,
    ) -> List[GeneratedSkill]:
        """
        Discover relevant skills for a worker's query.

        Searches the skill generator for matching skills, filtered
        by the worker's domain and skill affinities.

        Args:
            worker_id: The worker's identifier
            query: The worker's current query/intent
            limit: Maximum skills to return

        Returns:
            List of relevant GeneratedSkill objects, sorted by relevance
        """
        # Search skills
        skills = self._skill_generator.search_skills(query, limit=limit * 2)

        # Score by worker affinity
        profile = await self.get_worker_profile(worker_id)
        scored_skills = []
        for skill in skills:
            affinity = profile.skill_affinities.get(skill.category.value, 0.5)
            # Combined score: keyword match * affinity * confidence
            combined_score = affinity * skill.confidence
            scored_skills.append((combined_score, skill))

        # Sort by combined score
        scored_skills.sort(key=lambda x: x[0], reverse=True)

        # Filter by minimum confidence
        result = [
            skill
            for score, skill in scored_skills[:limit]
            if score >= SKILL_DISCOVERY_MIN_CONFIDENCE
        ]

        # Update session state
        if worker_id in self._hermes_sessions:
            state = self._hermes_sessions[worker_id]
            state.last_skill_search = query
            state.last_skill_search_result = [s.skill_id for s in result]
            state.active_skills = [s.skill_id for s in result]

        if result:
            await self._publish_event(
                HermesEventType.SKILL_DISCOVERED,
                {
                    "worker_id": worker_id,
                    "query": query,
                    "skill_count": len(result),
                    "skill_ids": [s.skill_id for s in result],
                    "skill_titles": [s.title for s in result],
                },
            )

        self._logger.info(
            "skills_discovered",
            worker_id=worker_id,
            query_len=len(query),
            found=len(result),
        )

        return result

    # ── Closed Learning Loop ──────────────────────────────────────

    async def start_interaction_trace(
        self,
        worker_id: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start tracing a worker interaction for the closed learning loop.

        Returns the trace_id for later steps.

        Flow:
            1. Start trace in SkillGenerator
            2. Record interaction start in session
            3. Return trace_id for step recording
        """
        trace_id = self._skill_generator.start_trace(
            worker_id=worker_id,
            query=query,
            context=context,
        )

        # Update session state
        if worker_id in self._hermes_sessions:
            self._hermes_sessions[worker_id].trace_id = trace_id

        self._logger.debug(
            "interaction_trace_started",
            worker_id=worker_id,
            trace_id=trace_id,
        )

        return trace_id

    async def record_trace_step(
        self,
        trace_id: str,
        action: str,
        tool_used: Optional[str] = None,
        input_data: Optional[str] = None,
        output_data: Optional[str] = None,
        duration_ms: int = 0,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Record a step in an active interaction trace."""
        self._skill_generator.record_step(
            trace_id=trace_id,
            action=action,
            tool_used=tool_used,
            input_data=input_data,
            output_data=output_data,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )

    async def complete_interaction(
        self,
        worker_id: str,
        trace_id: str,
        response: str,
        channel: str = "app_text",
        outcome: str = "success",
        lessons: Optional[List[str]] = None,
    ) -> Optional[GeneratedSkill]:
        """
        Complete an interaction and potentially generate a skill.

        This is the core of the closed learning loop:
            1. End the trace (may generate a skill)
            2. Record the interaction in SessionSync
            3. Update worker profile
            4. Check if memory consolidation is needed

        Returns:
            GeneratedSkill if a new skill was created, None otherwise
        """
        # End trace — may generate skill
        skill = self._skill_generator.end_trace(
            trace_id=trace_id,
            response=response,
            outcome=outcome,
            lessons=lessons,
        )

        # Record interaction in SessionSync
        from app.channels.adapters.base import ChannelType
        channel_type = self._resolve_channel_type(channel)

        state = self._hermes_sessions.get(worker_id)
        if state:
            await self._session_sync.record_interaction(
                worker_id=worker_id,
                session_id=state.session.session_id,
                channel=channel_type,
                user_message=state.context_window[-1].get("user_message", "") if state.context_window else "",
                agent_response=response,
                metadata={
                    "trace_id": trace_id,
                    "outcome": outcome,
                    "skill_generated": skill is not None,
                },
            )

        # Update context window
        if state:
            state.context_window.append({
                "user_message": state.context_window[-1].get("user_message", "") if state.context_window else "",
                "agent_response": response,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "outcome": outcome,
            })
            # Keep context window bounded
            if len(state.context_window) > 20:
                state.context_window = state.context_window[-20:]

        # Update worker profile
        await self._update_worker_profile(worker_id, outcome, skill)

        # If skill generated, publish event and update affinity
        if skill:
            await self._publish_event(
                HermesEventType.SKILL_DISCOVERED,
                {
                    "worker_id": worker_id,
                    "skill_id": skill.skill_id,
                    "skill_title": skill.title,
                    "category": skill.category.value,
                    "confidence": skill.confidence,
                    "complexity": skill.complexity,
                },
            )

            # Update skill affinity for this worker
            profile = await self.get_worker_profile(worker_id)
            current = profile.skill_affinities.get(skill.category.value, 0.5)
            profile.skill_affinities[skill.category.value] = min(1.0, current + 0.1)

        # Check memory consolidation
        await self._maybe_consolidate_memory(worker_id)

        # Clear trace
        if state:
            state.trace_id = None

        self._logger.info(
            "interaction_completed",
            worker_id=worker_id,
            outcome=outcome,
            skill_generated=skill is not None,
        )

        return skill

    async def record_feedback(
        self,
        worker_id: str,
        skill_id: str,
        success: bool,
        feedback_text: Optional[str] = None,
    ) -> None:
        """
        Record feedback on a skill application.

        This closes the feedback loop:
            Skill applied → user feedback → confidence update → improvement
        """
        self._skill_generator.record_skill_usage(
            skill_id=skill_id,
            success=success,
        )

        skill = self._skill_generator.get_skill(skill_id)
        if skill:
            await self._publish_event(
                HermesEventType.SKILL_IMPROVED if success else HermesEventType.FEEDBACK_RECEIVED,
                {
                    "worker_id": worker_id,
                    "skill_id": skill_id,
                    "success": success,
                    "new_confidence": skill.confidence,
                    "success_rate": skill.success_rate,
                    "usage_count": skill.usage_count,
                    "feedback_text": feedback_text,
                },
            )

            # Update worker profile
            profile = await self.get_worker_profile(worker_id)
            if success:
                current = profile.skill_affinities.get(skill.category.value, 0.5)
                profile.skill_affinities[skill.category.value] = min(1.0, current + 0.05)

        self._logger.info(
            "feedback_recorded",
            worker_id=worker_id,
            skill_id=skill_id,
            success=success,
        )

    # ── Memory Consolidation ──────────────────────────────────────

    async def consolidate_memory(
        self,
        worker_id: str,
    ) -> Optional[MemoryConsolidation]:
        """
        Consolidate short-term memory into long-term.

        Takes recent interactions, extracts patterns, and stores
        them in the worker profile and session context.

        This is the "sleep" cycle of the Hermes pattern —
        like how human memory consolidates during rest.
        """
        # Get recent history
        history = await self._session_sync.get_recent_history(
            worker_id=worker_id,
            limit=SHORT_TERM_MAX_INTERACTIONS,
        )

        if len(history) < 3:
            return None

        # Extract patterns from history
        patterns = self._extract_patterns(history)
        topics = self._extract_topics(history)
        summary = self._generate_summary(history)

        # Update session context with consolidated knowledge
        await self._session_sync.update_session_context(
            worker_id=worker_id,
            context_update={
                "consolidated_patterns": patterns,
                "consolidated_topics": topics,
                "consolidated_summary": summary,
                "last_consolidation": datetime.now(timezone.utc).isoformat(),
            },
        )

        # Update worker profile
        profile = await self.get_worker_profile(worker_id)
        profile.frequent_topics = topics
        self._last_consolidation[worker_id] = time.time()

        # Store summary
        if worker_id not in self._consolidation_summaries:
            self._consolidation_summaries[worker_id] = []
        self._consolidation_summaries[worker_id].append(summary)
        # Keep last 10 summaries
        self._consolidation_summaries[worker_id] = \
            self._consolidation_summaries[worker_id][-10:]

        consolidation = MemoryConsolidation(
            worker_id=worker_id,
            interactions_consolidated=len(history),
            patterns_extracted=len(patterns),
            summary=summary,
            topics=topics,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await self._publish_event(
            HermesEventType.MEMORY_CONSOLIDATED,
            {
                "worker_id": worker_id,
                "interactions": len(history),
                "patterns": len(patterns),
                "topics": topics,
            },
        )

        self._logger.info(
            "memory_consolidated",
            worker_id=worker_id,
            interactions=len(history),
            patterns=len(patterns),
        )

        return consolidation

    # ── Skill Registration ────────────────────────────────────────

    def register_skill_handler(
        self,
        category: str,
        handler: Callable[..., Coroutine],
    ) -> None:
        """
        Register a handler for a skill category.

        When a skill of this category is discovered, the handler
        is called with the skill context to execute it.
        """
        self._skill_handlers[category] = handler
        self._logger.info("skill_handler_registered", category=category)

    # ── Statistics & Diagnostics ──────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get Hermes service statistics."""
        return {
            "active_sessions": len(self._hermes_sessions),
            "worker_profiles": len(self._profiles),
            "skill_stats": self._skill_generator.get_stats(),
            "consolidation_pending": sum(
                1 for wid, ts in self._last_consolidation.items()
                if time.time() - ts > MEMORY_CONSOLIDATION_INTERVAL_S
            ),
            "registered_handlers": list(self._skill_handlers.keys()),
        }

    def get_session_state(self, worker_id: str) -> Optional[HermesSessionState]:
        """Get the Hermes session state for a worker."""
        return self._hermes_sessions.get(worker_id)

    # ── Internal Methods ──────────────────────────────────────────

    async def _load_worker_profile(self, worker_id: str) -> None:
        """Load or create a worker profile from session context."""
        context = await self._session_sync.get_session_context(worker_id)

        profile = WorkerProfile(
            worker_id=worker_id,
            first_seen=context.get("first_seen", datetime.now(timezone.utc).isoformat()),
            last_active=datetime.now(timezone.utc).isoformat(),
            preferred_language=context.get("preferred_language", "sw"),
            business_domain=context.get("business_domain", ""),
            skill_affinities=context.get("skill_affinities", {}),
            frequent_topics=context.get("consolidated_topics", []),
        )

        self._profiles[worker_id] = profile

    async def _update_worker_profile(
        self,
        worker_id: str,
        outcome: str,
        skill: Optional[GeneratedSkill],
    ) -> None:
        """Update worker profile after an interaction."""
        profile = await self.get_worker_profile(worker_id)
        profile.total_interactions += 1
        profile.last_active = datetime.now(timezone.utc).isoformat()

        # Track satisfaction trend
        satisfaction = 1.0 if outcome == "success" else 0.5 if outcome == "partial" else 0.0
        profile.satisfaction_trend.append(satisfaction)
        if len(profile.satisfaction_trend) > 50:
            profile.satisfaction_trend = profile.satisfaction_trend[-50:]

        # Persist profile to session context
        await self._session_sync.update_session_context(
            worker_id=worker_id,
            context_update={
                "first_seen": profile.first_seen,
                "preferred_language": profile.preferred_language,
                "business_domain": profile.business_domain,
                "skill_affinities": profile.skill_affinities,
                "total_interactions": profile.total_interactions,
            },
        )

    async def _maybe_consolidate_memory(self, worker_id: str) -> None:
        """Check if memory consolidation is needed and trigger it."""
        last = self._last_consolidation.get(worker_id, 0)
        state = self._hermes_sessions.get(worker_id)

        if state and len(state.context_window) >= SHORT_TERM_MAX_INTERACTIONS:
            if time.time() - last > MEMORY_CONSOLIDATION_INTERVAL_S:
                # Run consolidation in background
                task = asyncio.create_task(self.consolidate_memory(worker_id))
                self._background_tasks.append(task)

    def _extract_patterns(self, history: List[Dict[str, Any]]) -> List[str]:
        """Extract behavioral patterns from interaction history."""
        patterns = []

        # Count intents
        intent_counts: Dict[str, int] = {}
        for interaction in history:
            msg = interaction.get("user_message", "").lower()
            if any(w in msg for w in ["nimeuza", "sold", "sale"]):
                intent_counts["sale"] = intent_counts.get("sale", 0) + 1
            elif any(w in msg for w in ["nimenunua", "bought", "purchase"]):
                intent_counts["purchase"] = intent_counts.get("purchase", 0) + 1
            elif any(w in msg for w in ["matumizi", "expense", "spent"]):
                intent_counts["expense"] = intent_counts.get("expense", 0) + 1
            elif any(w in msg for w in ["bei", "price", "cost"]):
                intent_counts["pricing"] = intent_counts.get("pricing", 0) + 1

        for intent, count in sorted(intent_counts.items(), key=lambda x: x[1], reverse=True):
            patterns.append(f"Frequent {intent} interactions ({count}x)")

        # Time patterns
        channels = set()
        for interaction in history:
            ch = interaction.get("channel", "")
            if ch:
                channels.add(ch)
        if len(channels) > 1:
            patterns.append(f"Multi-channel user: {', '.join(channels)}")

        return patterns[:10]

    def _extract_topics(self, history: List[Dict[str, Any]]) -> List[str]:
        """Extract frequent topics from history."""
        topic_words: Dict[str, int] = {}
        for interaction in history:
            msg = interaction.get("user_message", "").lower()
            for word in msg.split():
                word = word.strip(".,!?;:")
                if len(word) > 3:
                    topic_words[word] = topic_words.get(word, 0) + 1

        # Sort by frequency, return top 10
        sorted_topics = sorted(topic_words.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_topics[:10]]

    def _generate_summary(self, history: List[Dict[str, Any]]) -> str:
        """Generate a summary of recent interactions."""
        if not history:
            return ""

        interaction_count = len(history)
        topics = self._extract_topics(history)
        patterns = self._extract_patterns(history)

        summary = f"Session with {interaction_count} interactions."
        if topics:
            summary += f" Topics: {', '.join(topics[:5])}."
        if patterns:
            summary += f" Patterns: {patterns[0]}."

        return summary

    def _register_default_skill_handlers(self) -> None:
        """Register default skill category handlers."""
        # These are passthrough handlers — the actual execution
        # happens in the domain agents. These handlers provide
        # the skill context to the execution pipeline.
        for category in SkillCategory:
            self._skill_handlers[category.value] = self._default_skill_handler

    async def _default_skill_handler(
        self,
        skill: GeneratedSkill,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Default handler: returns skill procedure as guidance."""
        return {
            "skill_id": skill.skill_id,
            "procedure": skill.procedure,
            "pitfalls": skill.pitfalls,
            "verification": skill.verification,
            "confidence": skill.confidence,
        }

    @staticmethod
    def _resolve_channel_type(channel: str):
        """Resolve channel string to ChannelType enum."""
        from app.channels.adapters.base import ChannelType

        channel_map = {
            "app_text": ChannelType.APP_TEXT,
            "app_voice": ChannelType.APP_VOICE,
            "whatsapp": ChannelType.WHATSAPP,
            "ussd": ChannelType.USSD,
            "sms": ChannelType.SMS,
        }
        return channel_map.get(channel, ChannelType.APP_TEXT)

    async def _publish_event(
        self,
        event_type: HermesEventType,
        payload: Dict[str, Any],
    ) -> None:
        """Publish a Hermes event to the event bus."""
        if not self._event_bus:
            return

        try:
            from app.agents.base import AgentEvent

            event = AgentEvent(
                event_id=str(uuid.uuid4()),
                event_type=event_type.value,
                source="HermesService",
                payload=payload,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            await self._event_bus.publish(event)
        except Exception as e:
            self._logger.warning("hermes_event_publish_failed", error=str(e))


# ════════════════════════════════════════════════════════════════════
# Factory Function
# ════════════════════════════════════════════════════════════════════


def create_hermes_service(
    session_sync: Optional[SessionSync] = None,
    skill_generator: Optional[SkillGenerator] = None,
    event_bus: Optional[EventBus] = None,
    db_path: str = "angavu_sessions.db",
) -> HermesService:
    """
    Factory function to create a fully configured HermesService.

    Creates default SessionSync and SkillGenerator if not provided.

    Args:
        session_sync: Existing SessionSync instance (or creates new)
        skill_generator: Existing SkillGenerator instance (or creates new)
        event_bus: EventBus for inter-agent communication
        db_path: Database path for SessionSync

    Returns:
        Configured HermesService ready for initialize()
    """
    if session_sync is None:
        session_sync = SessionSync(db_path=db_path)
        session_sync.initialize()

    if skill_generator is None:
        skill_generator = SkillGenerator()

    return HermesService(
        session_sync=session_sync,
        skill_generator=skill_generator,
        event_bus=event_bus,
    )
