"""
Skill Generator — Closed Learning Loop (Hermes Pattern).

Implements the pattern that makes Msaidizi smarter over time:
    Worker query → Trace → Was complex + successful? → Generate skill
    Future similar query → FTS5 search → Load skill → Execute faster

Skills are Markdown documents that capture reusable procedures,
learned from successful complex interactions. They are stored
in the L2 episodic memory for future retrieval.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Minimum steps to consider an interaction "complex enough" to learn from
MIN_COMPLEXITY_FOR_SKILL = 3


class SkillCategory(str, Enum):
    """Categories for generated skills."""

    PRICING = "pricing"
    INVENTORY = "inventory"
    SAVINGS = "savings"
    MARKET = "market"
    TRANSPORT = "transport"
    RECORDS = "records"
    GENERAL = "general"


@dataclass
class TraceStep:
    """A single step in an interaction trace."""

    step_id: str
    action: str
    tool_used: str | None = None
    input_data: str | None = None
    output_data: str | None = None
    duration_ms: int = 0
    success: bool = True
    error: str | None = None


@dataclass
class InteractionTrace:
    """
    Full execution trace of a worker interaction.

    Captures every step the agent took to fulfill a request,
    enabling pattern recognition and skill extraction.
    """

    trace_id: str
    worker_id: str
    query: str
    response: str
    steps: list[TraceStep] = field(default_factory=list)
    outcome: str = "success"  # success, partial, failure
    lessons: list[str] = field(default_factory=list)
    dialect: str = "sw"
    language: str = "sw"
    context: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    ended_at: str = ""
    total_duration_ms: int = 0

    @property
    def complexity(self) -> int:
        """Number of steps in the trace."""
        return len(self.steps)

    @property
    def is_complex(self) -> bool:
        """Whether this trace is complex enough to generate a skill."""
        return self.complexity >= MIN_COMPLEXITY_FOR_SKILL

    @property
    def is_successful(self) -> bool:
        """Whether the interaction was successful."""
        return self.outcome == "success"


@dataclass
class GeneratedSkill:
    """
    A skill document generated from a successful complex interaction.

    Skills are Markdown documents with:
    - Procedure (step-by-step)
    - Pitfalls to avoid
    - Verification steps
    - Academic basis (ECO/STA alignment)
    """

    skill_id: str
    title: str
    category: SkillCategory
    procedure: list[str]
    pitfalls: list[str]
    verification: list[str]
    academic_basis: str
    complexity: int
    confidence: float
    usage_count: int = 0
    success_count: int = 0
    source_trace_id: str = ""
    created_at: str = ""
    last_used_at: str = ""
    keywords: list[str] = field(default_factory=list)
    dialect: str = "sw"

    @property
    def success_rate(self) -> float:
        """Success rate when this skill is applied."""
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    def to_markdown(self) -> str:
        """Render skill as a Markdown document."""
        lines = [
            f"# {self.title}",
            "",
            f"**Category:** {self.category.value.title()}",
            f"**Academic Basis:** {self.academic_basis}",
            f"**Complexity:** {self.complexity} steps",
            f"**Confidence:** {self.confidence:.0%}",
            f"**Usage:** {self.usage_count} times "
            f"({self.success_rate:.0%} success)",
            "",
            "## Procedure",
        ]
        for i, step in enumerate(self.procedure, 1):
            lines.append(f"{i}. {step}")

        if self.pitfalls:
            lines.extend(["", "## Pitfalls to Avoid"])
            for pitfall in self.pitfalls:
                lines.append(f"- {pitfall}")

        if self.verification:
            lines.extend(["", "## Verification"])
            for check in self.verification:
                lines.append(f"- [ ] {check}")

        if self.keywords:
            lines.extend(["", f"**Keywords:** {', '.join(self.keywords)}"])

        return "\n".join(lines)


class SkillGenerator:
    """
    Closed learning loop — generates reusable skills from
    successful complex interactions.

    Flow:
        Trace → Complexity check → Outcome check → Extract pattern
        → Generate skill document → Store in L2 FTS5

    Skills improve over time: usage tracking updates confidence,
    and successful reuse boosts the skill's relevance score.
    """

    def __init__(self, episodic_memory: Any = None):
        self._episodic_memory = episodic_memory
        self._active_traces: dict[str, InteractionTrace] = {}
        self._generated_skills: dict[str, GeneratedSkill] = {}

    def start_trace(
        self,
        worker_id: str,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Start tracing an interaction."""
        trace_id = str(uuid.uuid4())
        trace = InteractionTrace(
            trace_id=trace_id,
            worker_id=worker_id,
            query=query,
            response="",
            context=context or {},
            started_at=datetime.now(UTC).isoformat(),
        )
        self._active_traces[trace_id] = trace
        logger.debug("trace_started", trace_id=trace_id, worker_id=worker_id)
        return trace_id

    def record_step(
        self,
        trace_id: str,
        action: str,
        tool_used: str | None = None,
        input_data: str | None = None,
        output_data: str | None = None,
        duration_ms: int = 0,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Record a step in the active trace."""
        trace = self._active_traces.get(trace_id)
        if not trace:
            return

        step = TraceStep(
            step_id=str(uuid.uuid4()),
            action=action,
            tool_used=tool_used,
            input_data=input_data,
            output_data=output_data,
            duration_ms=duration_ms,
            success=success,
            error=error,
        )
        trace.steps.append(step)

    def end_trace(
        self,
        trace_id: str,
        response: str,
        outcome: str = "success",
        lessons: list[str] | None = None,
    ) -> GeneratedSkill | None:
        """
        End the trace and potentially generate a skill.

        Returns a GeneratedSkill if the interaction was complex
        and successful enough to learn from.
        """
        trace = self._active_traces.pop(trace_id, None)
        if not trace:
            return None

        trace.response = response
        trace.outcome = outcome
        trace.lessons = lessons or []
        trace.ended_at = datetime.now(UTC).isoformat()

        # Calculate total duration
        total_ms = sum(s.duration_ms for s in trace.steps)
        trace.total_duration_ms = total_ms

        logger.info(
            "trace_ended",
            trace_id=trace_id,
            complexity=trace.complexity,
            outcome=outcome,
            is_complex=trace.is_complex,
        )

        # Check if we should generate a skill
        if not trace.is_complex:
            logger.debug(
                "trace_too_simple",
                trace_id=trace_id,
                steps=trace.complexity,
                threshold=MIN_COMPLEXITY_FOR_SKILL,
            )
            return None

        if not trace.is_successful:
            logger.debug(
                "trace_not_successful",
                trace_id=trace_id,
                outcome=outcome,
            )
            return None

        # Generate skill
        skill = self._generate_skill(trace)
        self._generated_skills[skill.skill_id] = skill

        # Store in episodic memory if available
        if self._episodic_memory:
            self._store_skill(skill)

        logger.info(
            "skill_generated",
            skill_id=skill.skill_id,
            title=skill.title,
            category=skill.category.value,
            complexity=skill.complexity,
        )

        return skill

    def _generate_skill(self, trace: InteractionTrace) -> GeneratedSkill:
        """Extract a reusable skill from a successful complex trace."""
        # Classify category
        category = self._classify_category(trace)

        # Extract procedure from steps
        procedure = self._extract_procedure(trace)

        # Extract pitfalls from errors and lessons
        pitfalls = self._extract_pitfalls(trace)

        # Generate verification checks
        verification = self._generate_verification(trace, category)

        # Determine academic basis
        academic_basis = self._determine_academic_basis(category)

        # Generate title
        title = self._generate_title(trace, category)

        # Extract keywords
        keywords = self._extract_keywords(trace)

        # Calculate initial confidence
        confidence = self._calculate_confidence(trace)

        return GeneratedSkill(
            skill_id=str(uuid.uuid4()),
            title=title,
            category=category,
            procedure=procedure,
            pitfalls=pitfalls,
            verification=verification,
            academic_basis=academic_basis,
            complexity=trace.complexity,
            confidence=confidence,
            source_trace_id=trace.trace_id,
            created_at=datetime.now(UTC).isoformat(),
            keywords=keywords,
            dialect=trace.dialect,
        )

    def _classify_category(self, trace: InteractionTrace) -> SkillCategory:
        """Classify the skill category based on trace content."""
        query_lower = trace.query.lower()
        content = f"{query_lower} {' '.join(trace.lessons)}".lower()

        category_keywords = {
            SkillCategory.PRICING: [
                "bei", "price", "gharama", "cost", "markup", "profit",
                "faida", "bidhaa",
            ],
            SkillCategory.INVENTORY: [
                "stock", "hifadhi", "inventory", "restock", "agizo",
                "order", "supply", "bidhaa",
            ],
            SkillCategory.SAVINGS: [
                "akiba", "savings", "weka", "banco", "m-pesa",
                "deposit", "interest",
            ],
            SkillCategory.MARKET: [
                "soko", "market", "supplier", "mteja", "customer",
                "competition", "brand",
            ],
            SkillCategory.TRANSPORT: [
                "usafiri", "transport", "delivery", "gari", "pikipiki",
                "cost ya usafiri",
            ],
            SkillCategory.RECORDS: [
                "rekodi", "records", "sales", "mauzo", "report",
                "ripoti", "data",
            ],
        }

        best_category = SkillCategory.GENERAL
        best_score = 0

        for cat, keywords in category_keywords.items():
            score = sum(1 for kw in keywords if kw in content)
            if score > best_score:
                best_score = score
                best_category = cat

        return best_category

    def _extract_procedure(self, trace: InteractionTrace) -> list[str]:
        """Extract step-by-step procedure from trace steps."""
        procedure = []
        for step in trace.steps:
            if step.success:
                desc = step.action
                if step.tool_used:
                    desc += f" (using {step.tool_used})"
                procedure.append(desc)
        return procedure

    def _extract_pitfalls(self, trace: InteractionTrace) -> list[str]:
        """Extract pitfalls from errors and lessons."""
        pitfalls = []

        # From failed steps
        for step in trace.steps:
            if not step.success and step.error:
                pitfalls.append(f"Watch out: {step.error}")

        # From lessons
        pitfalls.extend(trace.lessons)

        return pitfalls[:5]  # Limit to 5 pitfalls

    def _generate_verification(
        self, trace: InteractionTrace, category: SkillCategory
    ) -> list[str]:
        """Generate verification checklist for the skill."""
        verification = []

        if category == SkillCategory.PRICING:
            verification = [
                "Verify current wholesale price",
                "Confirm transport cost calculation",
                "Check markup is within 30-40% range",
            ]
        elif category == SkillCategory.INVENTORY:
            verification = [
                "Confirm current stock level",
                "Verify supplier availability",
                "Check delivery timeline",
            ]
        elif category == SkillCategory.SAVINGS:
            verification = [
                "Confirm deposit amount",
                "Verify M-Pesa transaction",
                "Update savings record",
            ]
        else:
            verification = [
                "Confirm all steps completed",
                "Verify outcome matches expectation",
            ]

        return verification

    def _determine_academic_basis(self, category: SkillCategory) -> str:
        """Map category to ECO/STA academic unit."""
        mapping = {
            SkillCategory.PRICING: "ECO 201 — Producer theory: pricing decisions",
            SkillCategory.INVENTORY: "ECO 201 — Inventory management and supply cycles",
            SkillCategory.SAVINGS: "ECO 206 — Microfinance and savings behavior",
            SkillCategory.MARKET: "ECO 101 — Market structure and competition",
            SkillCategory.TRANSPORT: "ECO 201 — Transaction costs and logistics",
            SkillCategory.RECORDS: "STA 142 — Data collection and analysis",
            SkillCategory.GENERAL: "ECO 101 — Rational decision-making",
        }
        return mapping.get(category, "ECO 101 — General economics")

    def _generate_title(
        self, trace: InteractionTrace, category: SkillCategory
    ) -> str:
        """Generate a descriptive title for the skill."""
        # Use first 50 chars of query + category
        query_summary = trace.query[:50].strip()
        if len(trace.query) > 50:
            query_summary += "..."
        return f"{category.value.title()} Protocol: {query_summary}"

    def _extract_keywords(self, trace: InteractionTrace) -> list[str]:
        """Extract searchable keywords from the trace."""
        words = set()
        text = f"{trace.query} {trace.response} {' '.join(trace.lessons)}"
        # Simple keyword extraction — split and filter short/common words
        for word in text.lower().split():
            word = word.strip(".,!?;:")
            if len(word) > 3:
                words.add(word)
        return sorted(list(words))[:10]

    def _calculate_confidence(self, trace: InteractionTrace) -> float:
        """Calculate initial confidence score for the skill."""
        base = 0.5

        # Bonus for more steps (more complex = more to learn)
        step_bonus = min(trace.complexity * 0.05, 0.2)

        # Bonus for all steps successful
        all_success = all(s.success for s in trace.steps)
        success_bonus = 0.15 if all_success else 0.0

        # Bonus for lessons learned
        lesson_bonus = min(len(trace.lessons) * 0.05, 0.1)

        return min(base + step_bonus + success_bonus + lesson_bonus, 1.0)

    def _store_skill(self, skill: GeneratedSkill) -> None:
        """Store generated skill in episodic memory."""
        try:
            if hasattr(self._episodic_memory, "store_skill"):
                self._episodic_memory.store_skill(
                    skill_id=skill.skill_id,
                    title=skill.title,
                    category=skill.category.value,
                    content=skill.to_markdown(),
                    keywords=skill.keywords,
                    confidence=skill.confidence,
                    worker_id="",  # Skills are worker-agnostic
                )
        except Exception as e:
            logger.error("skill_store_failed", error=str(e))

    def record_skill_usage(
        self,
        skill_id: str,
        success: bool,
    ) -> None:
        """Record that a skill was used and whether it succeeded."""
        skill = self._generated_skills.get(skill_id)
        if not skill:
            return

        skill.usage_count += 1
        if success:
            skill.success_count += 1
        skill.last_used_at = datetime.now(UTC).isoformat()

        # Update confidence based on success rate
        if skill.usage_count >= 3:
            skill.confidence = 0.5 + (skill.success_rate * 0.5)

        logger.info(
            "skill_usage_recorded",
            skill_id=skill_id,
            success=success,
            usage_count=skill.usage_count,
            success_rate=skill.success_rate,
        )

    def search_skills(
        self,
        query: str,
        category: SkillCategory | None = None,
        limit: int = 5,
    ) -> list[GeneratedSkill]:
        """Search for relevant skills by query and optional category."""
        results = []
        query_lower = query.lower()

        for skill in self._generated_skills.values():
            # Category filter
            if category and skill.category != category:
                continue

            # Keyword match
            score = 0
            for keyword in skill.keywords:
                if keyword in query_lower:
                    score += 1

            if score > 0:
                results.append((score, skill))

        # Sort by score, then confidence
        results.sort(key=lambda x: (x[0], x[1].confidence), reverse=True)
        return [skill for _, skill in results[:limit]]

    def get_skill(self, skill_id: str) -> GeneratedSkill | None:
        """Get a specific skill by ID."""
        return self._generated_skills.get(skill_id)

    def get_all_skills(self) -> list[GeneratedSkill]:
        """Get all generated skills."""
        return list(self._generated_skills.values())

    def get_stats(self) -> dict[str, Any]:
        """Get skill generator statistics."""
        skills = list(self._generated_skills.values())
        return {
            "total_skills": len(skills),
            "categories": {
                cat.value: sum(1 for s in skills if s.category == cat)
                for cat in SkillCategory
            },
            "avg_confidence": (
                sum(s.confidence for s in skills) / len(skills)
                if skills
                else 0.0
            ),
            "total_usage": sum(s.usage_count for s in skills),
            "active_traces": len(self._active_traces),
        }
