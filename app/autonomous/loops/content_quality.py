"""
Content Quality Loop — Self-Improving Content Generation.

Implements the Reflexion pattern for content creation:
    1. Generate content (blog post, social media, report)
    2. Evaluate quality (readability, SEO, engagement potential)
    3. Refine based on feedback
    4. Track improvement over time

This loop ensures that Angavu Intelligence's content output
continuously improves in quality, relevance, and engagement.

Quality Dimensions:
    - Readability    (Flesch-Kincaid, sentence length)
    - SEO            (keyword density, meta tags, structure)
    - Engagement     (hook quality, CTA presence, emotional resonance)
    - Accuracy       (data correctness, source citations)
    - Brand voice    (tone consistency, terminology)
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

from app.autonomous.learning import LearningSystem, MetricType
from app.autonomous.reflexion import (
    ReflexionResult,
    ReflexionStatus,
    create_reflexion_engine,
)

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════


class ContentType(str, Enum):
    """Types of content the loop can generate."""
    BLOG_POST = "blog_post"
    SOCIAL_MEDIA = "social_media"
    EMAIL_CAMPAIGN = "email_campaign"
    PRODUCT_DESCRIPTION = "product_description"
    MARKET_REPORT = "market_report"
    CUSTOMER_UPDATE = "customer_update"


class QualityDimension(str, Enum):
    """Dimensions of content quality evaluation."""
    READABILITY = "readability"
    SEO = "seo"
    ENGAGEMENT = "engagement"
    ACCURACY = "accuracy"
    BRAND_VOICE = "brand_voice"


@dataclass
class ContentRequest:
    """A request to generate content."""
    content_type: ContentType = ContentType.BLOG_POST
    topic: str = ""
    target_audience: str = "small_business_owners"
    language: str = "en"
    keywords: list[str] = field(default_factory=list)
    tone: str = "professional"
    max_words: int = 500
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type.value,
            "topic": self.topic,
            "target_audience": self.target_audience,
            "language": self.language,
            "keywords": self.keywords,
            "tone": self.tone,
            "max_words": self.max_words,
        }


@dataclass
class QualityScore:
    """Quality evaluation for a piece of content."""
    overall: float = 0.0
    readability: float = 0.0
    seo: float = 0.0
    engagement: float = 0.0
    accuracy: float = 0.0
    brand_voice: float = 0.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "readability": self.readability,
            "seo": self.seo,
            "engagement": self.engagement,
            "accuracy": self.accuracy,
            "brand_voice": self.brand_voice,
            "issues": self.issues,
            "suggestions": self.suggestions,
        }


@dataclass
class ContentOutput:
    """Generated content with metadata."""
    content_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content_type: str = ""
    title: str = ""
    body: str = ""
    meta_description: str = ""
    word_count: int = 0
    quality_score: QualityScore | None = None
    generated_at: float = field(default_factory=time.time)
    attempt_number: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type,
            "title": self.title,
            "body": self.body[:500] + "..." if len(self.body) > 500 else self.body,
            "word_count": self.word_count,
            "quality_score": self.quality_score.to_dict() if self.quality_score else None,
            "attempt_number": self.attempt_number,
        }


# ════════════════════════════════════════════════════════════════════
# Content Quality Critic
# ════════════════════════════════════════════════════════════════════


class ContentQualityCritic:
    """
    Evaluates content quality across multiple dimensions.

    Uses heuristic analysis for readability, SEO, engagement,
    accuracy, and brand voice consistency.
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self._weights = weights or {
            "readability": 0.25,
            "seo": 0.20,
            "engagement": 0.25,
            "accuracy": 0.15,
            "brand_voice": 0.15,
        }
        self._logger = logger.bind(component="content_quality_critic")

    async def critique(
        self,
        task: dict[str, Any],
        result: dict[str, Any],
        attempt_number: int,
    ) -> dict[str, Any]:
        """Evaluate content quality."""
        if not result.get("success", False):
            return {
                "score": 0.0,
                "issues": [f"Content generation failed: {result.get('error', 'unknown')}"],
                "suggestions": ["Check content generation pipeline", "Verify input data"],
            }

        content = result.get("data", {})
        body = content.get("body", "")
        title = content.get("title", "")
        keywords = task.get("keywords", [])

        # Evaluate each dimension
        readability = self._evaluate_readability(body)
        seo = self._evaluate_seo(body, title, keywords)
        engagement = self._evaluate_engagement(body, title)
        accuracy = self._evaluate_accuracy(content)
        brand_voice = self._evaluate_brand_voice(body, task.get("tone", "professional"))

        # Weighted overall score
        overall = (
            readability * self._weights["readability"]
            + seo * self._weights["seo"]
            + engagement * self._weights["engagement"]
            + accuracy * self._weights["accuracy"]
            + brand_voice * self._weights["brand_voice"]
        )

        # Collect issues and suggestions
        issues: list[str] = []
        suggestions: list[str] = []

        if readability < 0.6:
            issues.append(f"Low readability score: {readability:.2f}")
            suggestions.append("Shorter sentences, simpler vocabulary, use bullet points")
        if seo < 0.6:
            issues.append(f"Low SEO score: {seo:.2f}")
            suggestions.append(f"Include keywords: {', '.join(keywords[:3])}")
        if engagement < 0.6:
            issues.append(f"Low engagement score: {engagement:.2f}")
            suggestions.append("Add a hook in the first sentence, include a CTA")
        if brand_voice < 0.6:
            issues.append(f"Brand voice inconsistency: {brand_voice:.2f}")
            suggestions.append(f"Adjust tone to match '{task.get('tone', 'professional')}'")

        return {
            "score": round(overall, 3),
            "issues": issues,
            "suggestions": suggestions,
            "dimension_scores": {
                "readability": round(readability, 3),
                "seo": round(seo, 3),
                "engagement": round(engagement, 3),
                "accuracy": round(accuracy, 3),
                "brand_voice": round(brand_voice, 3),
            },
        }

    def _evaluate_readability(self, body: str) -> float:
        """Evaluate readability using sentence/word length heuristics."""
        if not body:
            return 0.0

        sentences = re.split(r'[.!?]+', body)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return 0.0

        words = body.split()
        if not words:
            return 0.0

        avg_sentence_len = len(words) / len(sentences)
        avg_word_len = sum(len(w) for w in words) / len(words)

        # Ideal: 15-20 words/sentence, 4-6 chars/word
        sentence_score = max(0, 1.0 - abs(avg_sentence_len - 17.5) / 17.5)
        word_score = max(0, 1.0 - abs(avg_word_len - 5) / 5)

        return (sentence_score + word_score) / 2

    def _evaluate_seo(self, body: str, title: str, keywords: list[str]) -> float:
        """Evaluate SEO quality."""
        if not body:
            return 0.0

        score = 0.5  # Base score

        # Keyword presence
        if keywords:
            body_lower = body.lower()
            title_lower = title.lower()
            found_in_body = sum(1 for kw in keywords if kw.lower() in body_lower)
            found_in_title = sum(1 for kw in keywords if kw.lower() in title_lower)
            keyword_score = (found_in_body / len(keywords)) * 0.3 + (found_in_title / len(keywords)) * 0.2
            score += keyword_score

        # Title length (50-60 chars ideal)
        if 40 <= len(title) <= 70:
            score += 0.1

        # Body length (300+ words for blog posts)
        word_count = len(body.split())
        if word_count >= 300:
            score += 0.1
        elif word_count >= 150:
            score += 0.05

        # Has headings (markdown # or HTML <h>)
        if re.search(r'^#{1,3}\s|<h[1-6]', body, re.MULTILINE):
            score += 0.1

        return min(1.0, score)

    def _evaluate_engagement(self, body: str, title: str) -> float:
        """Evaluate engagement potential."""
        if not body:
            return 0.0

        score = 0.4  # Base

        # Hook: first sentence question or bold statement
        first_sentence = re.split(r'[.!?]', body)[0] if body else ""
        if "?" in first_sentence or "!" in first_sentence:
            score += 0.15

        # Has CTA
        cta_patterns = [
            r'\b(sign up|subscribe|learn more|get started|try|contact|call|visit)\b',
            r'\b(click|download|join|register|book)\b',
        ]
        for pattern in cta_patterns:
            if re.search(pattern, body, re.IGNORECASE):
                score += 0.1
                break

        # Lists/bullet points
        if re.search(r'^\s*[-*•]\s|^\s*\d+[.)]\s', body, re.MULTILINE):
            score += 0.1

        # Emotional words
        emotional = [
            "amazing", "incredible", "essential", "critical", "powerful",
            "proven", "secret", "surprising", "urgent", "exclusive",
        ]
        found = sum(1 for w in emotional if w in body.lower())
        score += min(0.15, found * 0.03)

        # Questions (engagement hooks)
        question_count = body.count("?")
        score += min(0.1, question_count * 0.02)

        return min(1.0, score)

    def _evaluate_accuracy(self, content: dict[str, Any]) -> float:
        """Evaluate accuracy (heuristic — checks for data presence)."""
        score = 0.7  # Default assumption of reasonable accuracy

        # Has data/statistics
        body = content.get("body", "")
        if re.search(r'\d+%|\d+\.\d+|KES|USD|\d{4}', body):
            score += 0.15

        # Has citations/references
        if re.search(r'\[.*\]|according to|source:|research shows', body, re.IGNORECASE):
            score += 0.15

        return min(1.0, score)

    def _evaluate_brand_voice(self, body: str, expected_tone: str) -> float:
        """Evaluate brand voice consistency."""
        if not body:
            return 0.0

        score = 0.6  # Base

        tone_indicators = {
            "professional": ["therefore", "furthermore", "consequently", "analysis", "strategy"],
            "friendly": ["hey", "awesome", "let's", "you'll", "we're"],
            "authoritative": ["research shows", "data indicates", "proven", "established"],
            "casual": ["cool", "yeah", "btw", "huge", "super"],
        }

        indicators = tone_indicators.get(expected_tone, tone_indicators["professional"])
        found = sum(1 for w in indicators if w in body.lower())
        score += min(0.3, found * 0.06)

        # Penalize tone mismatch
        other_tones = {k: v for k, v in tone_indicators.items() if k != expected_tone}
        mismatch_count = 0
        for tone, words in other_tones.items():
            mismatch_count += sum(1 for w in words if w in body.lower())
        score -= min(0.2, mismatch_count * 0.04)

        return max(0.0, min(1.0, score))


# ════════════════════════════════════════════════════════════════════
# Content Executor
# ════════════════════════════════════════════════════════════════════


class ContentExecutor:
    """
    Generates content based on a request.

    In production, this would call an LLM. For now, it produces
    structured placeholder content that demonstrates the loop pattern.
    """

    def __init__(self):
        self._logger = logger.bind(component="content_executor")

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate content based on the task specification."""
        start = time.time()

        try:
            content_type = task.get("content_type", "blog_post")
            topic = task.get("topic", "Business Intelligence")
            audience = task.get("target_audience", "small_business_owners")
            keywords = task.get("keywords", [])
            tone = task.get("tone", "professional")
            max_words = task.get("max_words", 500)

            # Check for Reflexion feedback
            feedback = task.get("_reflexion_feedback", {})
            suggestions = feedback.get("suggestions", [])

            # Generate content structure
            title = f"{topic}: Key Insights for {audience.replace('_', ' ').title()}"

            body_parts = []
            body_parts.append(
                f"# {title}\n\n"
                f"Understanding {topic.lower()} is essential for {audience.replace('_', ' ')}. "
                f"This analysis provides actionable insights based on current market data.\n"
            )

            if keywords:
                body_parts.append(
                    f"## Why {topic} Matters\n\n"
                    f"Key factors: {', '.join(keywords)}. "
                    f"These elements drive business success in today's market.\n"
                )

            body_parts.append(
                "## Key Findings\n\n"
                "- Market trends show 15% growth in the sector\n"
                "- Customer engagement metrics improved by 23%\n"
                "- Revenue optimization opportunities identified in 3 areas\n"
            )

            body_parts.append(
                "## Recommendations\n\n"
                "1. Implement data-driven decision making\n"
                "2. Focus on customer retention strategies\n"
                "3. Optimize pricing based on market analysis\n"
            )

            body_parts.append(
                f"## Next Steps\n\n"
                f"Contact Angavu Intelligence for a personalized {topic.lower()} assessment. "
                f"Sign up for our weekly market intelligence reports.\n"
            )

            # Apply Reflexion suggestions
            if suggestions:
                body_parts.append(f"\n<!-- Refinements applied: {'; '.join(suggestions[:3])} -->")

            body = "\n".join(body_parts)
            word_count = len(body.split())

            return {
                "success": True,
                "data": {
                    "content_type": content_type,
                    "title": title,
                    "body": body,
                    "word_count": word_count,
                    "keywords_used": keywords,
                    "tone": tone,
                },
                "duration_ms": (time.time() - start) * 1000,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": (time.time() - start) * 1000,
            }


# ════════════════════════════════════════════════════════════════════
# Content Reviser
# ════════════════════════════════════════════════════════════════════


class ContentReviser:
    """
    Revises content generation strategy based on quality critique.

    Adjusts the content request parameters to address identified issues.
    """

    async def revise(
        self,
        task: dict[str, Any],
        critique: dict[str, Any],
        previous_attempts: list,
    ) -> dict[str, Any]:
        """Create a revised content task based on critique."""
        revised_task = dict(task)
        suggestions = critique.get("suggestions", [])
        dimensions = critique.get("dimension_scores", {})

        plan_parts = []

        # Address specific dimension weaknesses
        if dimensions.get("readability", 1.0) < 0.6:
            revised_task["max_words"] = min(task.get("max_words", 500), 300)
            plan_parts.append("Reduce content length for readability")

        if dimensions.get("seo", 1.0) < 0.6:
            # Boost keyword focus
            revised_task["_seo_boost"] = True
            plan_parts.append("Increase keyword density and add headings")

        if dimensions.get("engagement", 1.0) < 0.6:
            revised_task["_add_hook"] = True
            revised_task["_add_cta"] = True
            plan_parts.append("Add engagement hook and call-to-action")

        if dimensions.get("brand_voice", 1.0) < 0.6:
            plan_parts.append(f"Adjust tone to match '{task.get('tone', 'professional')}'")

        # General suggestions
        for suggestion in suggestions[:3]:
            plan_parts.append(f"Apply: {suggestion}")

        return {
            "revised_task": revised_task,
            "plan": "; ".join(plan_parts) if plan_parts else "General refinement",
        }


# ════════════════════════════════════════════════════════════════════
# Content Quality Loop
# ════════════════════════════════════════════════════════════════════


class ContentQualityLoop:
    """
    Self-improving content generation loop.

    Wraps content generation with the Reflexion pattern:
    1. Generate content
    2. Evaluate quality (readability, SEO, engagement, accuracy, brand voice)
    3. Refine based on quality feedback
    4. Repeat until quality threshold met

    Usage:
        loop = ContentQualityLoop(quality_threshold=0.75)
        result = await loop.generate(ContentRequest(
            content_type=ContentType.BLOG_POST,
            topic="Market Intelligence",
            keywords=["market analysis", "business intelligence"],
        ))
    """

    def __init__(
        self,
        quality_threshold: float = 0.7,
        max_attempts: int = 3,
        learning_system: LearningSystem | None = None,
        event_bus: Any = None,
    ):
        self._learning = learning_system or LearningSystem()
        self._engine = create_reflexion_engine(
            executor=ContentExecutor(),
            critic=ContentQualityCritic(),
            reviser=ContentReviser(),
            quality_threshold=quality_threshold,
            max_attempts=max_attempts,
            event_bus=event_bus,
        )
        self._logger = logger.bind(component="content_quality_loop")

    async def generate(self, request: ContentRequest) -> ReflexionResult:
        """
        Generate content with self-improvement loop.

        Returns a ReflexionResult with the final content and quality metrics.
        """
        task = request.to_dict()

        self._logger.info(
            "content_generation_started",
            content_type=request.content_type.value,
            topic=request.topic,
        )

        result = await self._engine.run(
            task=task,
            task_name=f"content:{request.content_type.value}:{request.topic[:30]}",
        )

        # Record in learning system
        if result.status == ReflexionStatus.ACCEPTED:
            self._learning.record_success(
                agent_name="ContentQualityLoop",
                task_name=f"generate_{request.content_type.value}",
                quality_score=result.final_score,
                duration_ms=result.total_duration_ms,
            )
        else:
            self._learning.record_failure(
                agent_name="ContentQualityLoop",
                task_name=f"generate_{request.content_type.value}",
                error=f"Quality below threshold: {result.final_score:.2f}",
            )

        # Record quality metrics
        self._learning.record_metric(
            agent_name="ContentQualityLoop",
            task_name=f"generate_{request.content_type.value}",
            metric_type=MetricType.CONTENT_QUALITY,
            value=result.final_score,
        )

        return result

    def get_stats(self) -> dict[str, Any]:
        """Get content quality loop statistics."""
        return {
            "engine_stats": self._engine.get_stats(),
            "learning_stats": self._learning.get_profile("ContentQualityLoop").to_dict(),
        }
