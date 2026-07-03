"""
Customer Satisfaction Loop — Self-Improving Service Delivery.

Implements the Reflexion pattern for customer service:
    1. Collect customer feedback (WhatsApp, surveys, support tickets)
    2. Analyze sentiment and identify issues
    3. Generate improvement actions
    4. Auto-adjust service delivery
    5. Track satisfaction improvement over time

Architecture:
    ┌──────────────┐
    │   Feedback    │ (WhatsApp, surveys, tickets)
    └──────┬───────┘
           ▼
    ┌──────────────┐
    │  Sentiment   │ (positive/neutral/negative + score)
    │  Analysis    │
    └──────┬───────┘
           ▼
    ┌──────────────┐     ┌──────────────┐
    │  Categorize  │────▶│   Generate   │
    │  (issue type)│     │  Improvements│
    └──────────────┘     └──────┬───────┘
                                ▼
                         ┌──────────────┐
                         │   Apply &    │
                         │   Measure    │
                         └──────────────┘
"""

from __future__ import annotations

import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

from app.autonomous.reflexion import (
    AdaptiveReviser,
    ReflexionConfig,
    ReflexionEngine,
    ReflexionResult,
    ReflexionStatus,
    create_reflexion_engine,
)
from app.autonomous.learning import LearningSystem, MetricType

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Data Types
# ════════════════════════════════════════════════════════════════════


class Sentiment(str, Enum):
    """Customer sentiment classification."""
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"


class FeedbackChannel(str, Enum):
    """Channel where feedback was collected."""
    WHATSAPP = "whatsapp"
    SURVEY = "survey"
    SUPPORT_TICKET = "support_ticket"
    SOCIAL_MEDIA = "social_media"
    DIRECT = "direct"


class IssueCategory(str, Enum):
    """Categories of customer issues."""
    REPORT_QUALITY = "report_quality"
    DELIVERY_TIMING = "delivery_timing"
    DATA_ACCURACY = "data_accuracy"
    PRICING = "pricing"
    ONBOARDING = "onboarding"
    FEATURE_REQUEST = "feature_request"
    TECHNICAL_ISSUE = "technical_issue"
    GENERAL = "general"


@dataclass
class CustomerFeedback:
    """A piece of customer feedback."""
    feedback_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    customer_id: str = ""
    channel: FeedbackChannel = FeedbackChannel.WHATSAPP
    text: str = ""
    rating: Optional[int] = None  # 1-5 stars
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "customer_id": self.customer_id,
            "channel": self.channel.value,
            "text": self.text,
            "rating": self.rating,
            "timestamp": self.timestamp,
        }


@dataclass
class SentimentAnalysis:
    """Result of sentiment analysis on feedback."""
    sentiment: Sentiment = Sentiment.NEUTRAL
    score: float = 0.0  # -1.0 (very negative) to 1.0 (very positive)
    confidence: float = 0.0
    key_phrases: List[str] = field(default_factory=list)
    issue_category: IssueCategory = IssueCategory.GENERAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment": self.sentiment.value,
            "score": self.score,
            "confidence": self.confidence,
            "key_phrases": self.key_phrases,
            "issue_category": self.issue_category.value,
        }


@dataclass
class ImprovementAction:
    """An action to improve customer satisfaction."""
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    category: IssueCategory = IssueCategory.GENERAL
    description: str = ""
    priority: str = "medium"  # low, medium, high, critical
    estimated_impact: float = 0.0  # 0.0-1.0
    applied: bool = False
    applied_at: Optional[float] = None
    measured_impact: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "category": self.category.value,
            "description": self.description,
            "priority": self.priority,
            "estimated_impact": self.estimated_impact,
            "applied": self.applied,
            "measured_impact": self.measured_impact,
        }


@dataclass
class SatisfactionSnapshot:
    """Point-in-time customer satisfaction metrics."""
    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    avg_sentiment_score: float = 0.0
    nps_estimate: float = 0.0  # Net Promoter Score estimate (-100 to 100)
    total_feedback: int = 0
    positive_pct: float = 0.0
    negative_pct: float = 0.0
    top_issues: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "avg_sentiment_score": self.avg_sentiment_score,
            "nps_estimate": self.nps_estimate,
            "total_feedback": self.total_feedback,
            "positive_pct": self.positive_pct,
            "negative_pct": self.negative_pct,
            "top_issues": self.top_issues,
        }


# ════════════════════════════════════════════════════════════════════
# Sentiment Analyzer
# ════════════════════════════════════════════════════════════════════


class SentimentAnalyzer:
    """
    Analyzes customer feedback sentiment using keyword heuristics.

    In production, this would use an LLM or fine-tuned model.
    The heuristic version demonstrates the pattern.
    """

    # Sentiment lexicons
    POSITIVE_WORDS = {
        "good", "great", "excellent", "amazing", "helpful", "useful",
        "love", "best", "fantastic", "wonderful", "perfect", "happy",
        "satisfied", "impressed", "recommend", "thank", "thanks",
        "awesome", "brilliant", "outstanding", "superb", "reliable",
        "accurate", "fast", "easy", "clear", "insightful",
    }

    NEGATIVE_WORDS = {
        "bad", "poor", "terrible", "awful", "useless", "slow",
        "wrong", "error", "broken", "confusing", "disappointed",
        "frustrated", "annoying", "unreliable", "inaccurate", "late",
        "expensive", "waste", "worst", "horrible", "difficult",
        "unclear", "misleading", "overpriced", "bug", "crash",
    }

    ISSUE_KEYWORDS = {
        IssueCategory.REPORT_QUALITY: ["report", "quality", "format", "layout", "template"],
        IssueCategory.DELIVERY_TIMING: ["late", "delay", "slow", "timing", "schedule", "wait"],
        IssueCategory.DATA_ACCURACY: ["wrong", "inaccurate", "error", "mistake", "data", "correct"],
        IssueCategory.PRICING: ["price", "cost", "expensive", "cheap", "afford", "value", "fee"],
        IssueCategory.ONBOARDING: ["start", "begin", "setup", "confused", "how to", "tutorial"],
        IssueCategory.FEATURE_REQUEST: ["wish", "feature", "add", "would be nice", "suggest", "want"],
        IssueCategory.TECHNICAL_ISSUE: ["bug", "crash", "error", "broken", "not working", "fix"],
    }

    def analyze(self, text: str, rating: Optional[int] = None) -> SentimentAnalysis:
        """Analyze sentiment of a feedback text."""
        words = set(re.findall(r'\b\w+\b', text.lower()))

        positive_count = len(words & self.POSITIVE_WORDS)
        negative_count = len(words & self.NEGATIVE_WORDS)

        # Calculate base score from word counts
        total_sentiment_words = positive_count + negative_count
        if total_sentiment_words > 0:
            word_score = (positive_count - negative_count) / total_sentiment_words
        else:
            word_score = 0.0

        # Adjust with rating if available
        if rating is not None:
            rating_score = (rating - 3) / 2  # Maps 1-5 to -1.0 to 1.0
            score = word_score * 0.6 + rating_score * 0.4
        else:
            score = word_score

        # Classify sentiment
        if score >= 0.5:
            sentiment = Sentiment.VERY_POSITIVE
        elif score >= 0.2:
            sentiment = Sentiment.POSITIVE
        elif score >= -0.2:
            sentiment = Sentiment.NEUTRAL
        elif score >= -0.5:
            sentiment = Sentiment.NEGATIVE
        else:
            sentiment = Sentiment.VERY_NEGATIVE

        # Detect issue category
        issue_category = IssueCategory.GENERAL
        best_match = 0
        for category, keywords in self.ISSUE_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in text.lower())
            if matches > best_match:
                best_match = matches
                issue_category = category

        # Extract key phrases (simple n-gram approach)
        key_phrases = []
        for word in words:
            if word in self.POSITIVE_WORDS or word in self.NEGATIVE_WORDS:
                key_phrases.append(word)

        confidence = min(1.0, 0.5 + total_sentiment_words * 0.1)

        return SentimentAnalysis(
            sentiment=sentiment,
            score=round(score, 3),
            confidence=round(confidence, 3),
            key_phrases=key_phrases[:10],
            issue_category=issue_category,
        )


# ════════════════════════════════════════════════════════════════════
# Customer Satisfaction Executor
# ════════════════════════════════════════════════════════════════════


class SatisfactionExecutor:
    """
    Processes customer feedback and generates improvement actions.

    This executor:
    1. Analyzes sentiment of the feedback
    2. Categorizes the issue
    3. Generates improvement actions
    4. Returns processed results
    """

    def __init__(self):
        self._analyzer = SentimentAnalyzer()
        self._logger = logger.bind(component="satisfaction_executor")

    async def execute(
        self,
        task: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process customer feedback."""
        start = time.time()

        try:
            feedback_text = task.get("text", "")
            customer_id = task.get("customer_id", "unknown")
            channel = task.get("channel", "whatsapp")
            rating = task.get("rating")

            # Check for Reflexion feedback
            reflexion = task.get("_reflexion_feedback", {})

            # Analyze sentiment
            analysis = self._analyzer.analyze(feedback_text, rating)

            # Generate improvement actions
            actions = self._generate_actions(analysis, reflexion)

            return {
                "success": True,
                "data": {
                    "customer_id": customer_id,
                    "channel": channel,
                    "sentiment": analysis.to_dict(),
                    "improvement_actions": [a.to_dict() for a in actions],
                    "actions_count": len(actions),
                    "high_priority_actions": sum(1 for a in actions if a.priority in ("high", "critical")),
                },
                "duration_ms": (time.time() - start) * 1000,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "duration_ms": (time.time() - start) * 1000,
            }

    def _generate_actions(
        self,
        analysis: SentimentAnalysis,
        reflexion: Dict[str, Any],
    ) -> List[ImprovementAction]:
        """Generate improvement actions based on sentiment analysis."""
        actions = []

        # Actions based on issue category
        category_actions = {
            IssueCategory.REPORT_QUALITY: ImprovementAction(
                category=IssueCategory.REPORT_QUALITY,
                description="Review and improve report templates based on feedback",
                priority="high",
                estimated_impact=0.7,
            ),
            IssueCategory.DELIVERY_TIMING: ImprovementAction(
                category=IssueCategory.DELIVERY_TIMING,
                description="Optimize delivery schedule and add status notifications",
                priority="high",
                estimated_impact=0.8,
            ),
            IssueCategory.DATA_ACCURACY: ImprovementAction(
                category=IssueCategory.DATA_ACCURACY,
                description="Implement additional data validation checks",
                priority="critical",
                estimated_impact=0.9,
            ),
            IssueCategory.PRICING: ImprovementAction(
                category=IssueCategory.PRICING,
                description="Review pricing model and communicate value proposition",
                priority="medium",
                estimated_impact=0.5,
            ),
            IssueCategory.ONBOARDING: ImprovementAction(
                category=IssueCategory.ONBOARDING,
                description="Improve onboarding flow with guided tutorials",
                priority="medium",
                estimated_impact=0.6,
            ),
            IssueCategory.FEATURE_REQUEST: ImprovementAction(
                category=IssueCategory.FEATURE_REQUEST,
                description="Log feature request for product roadmap review",
                priority="low",
                estimated_impact=0.4,
            ),
            IssueCategory.TECHNICAL_ISSUE: ImprovementAction(
                category=IssueCategory.TECHNICAL_ISSUE,
                description="Escalate technical issue for immediate investigation",
                priority="critical",
                estimated_impact=0.85,
            ),
        }

        action = category_actions.get(analysis.issue_category)
        if action:
            actions.append(action)

        # Actions based on sentiment severity
        if analysis.sentiment in (Sentiment.VERY_NEGATIVE, Sentiment.NEGATIVE):
            actions.append(ImprovementAction(
                category=analysis.issue_category,
                description="Trigger proactive customer outreach for recovery",
                priority="high",
                estimated_impact=0.6,
            ))

        # Apply Reflexion suggestions
        if reflexion.get("suggestions"):
            for suggestion in reflexion["suggestions"][:2]:
                actions.append(ImprovementAction(
                    category=analysis.issue_category,
                    description=f"Reflexion-driven: {suggestion}",
                    priority="medium",
                    estimated_impact=0.5,
                ))

        return actions


# ════════════════════════════════════════════════════════════════════
# Satisfaction Critic
# ════════════════════════════════════════════════════════════════════


class SatisfactionCritic:
    """
    Evaluates the quality of feedback processing results.

    Checks:
    - Sentiment analysis confidence
    - Issue categorization accuracy
    - Action relevance and completeness
    """

    async def critique(
        self,
        task: Dict[str, Any],
        result: Dict[str, Any],
        attempt_number: int,
    ) -> Dict[str, Any]:
        """Evaluate feedback processing quality."""
        if not result.get("success", False):
            return {
                "score": 0.0,
                "issues": [f"Processing failed: {result.get('error', 'unknown')}"],
                "suggestions": ["Check feedback text quality", "Verify analysis pipeline"],
            }

        data = result.get("data", {})
        sentiment = data.get("sentiment", {})
        actions = data.get("improvement_actions", [])

        issues = []
        suggestions = []
        score = 1.0

        # Check sentiment confidence
        confidence = sentiment.get("confidence", 0)
        if confidence < 0.5:
            score -= 0.2
            issues.append(f"Low sentiment confidence: {confidence:.2f}")
            suggestions.append("Gather more context or use LLM-based analysis")

        # Check if actions were generated
        if not actions:
            score -= 0.3
            issues.append("No improvement actions generated")
            suggestions.append("Ensure issue categorization produces actionable outputs")

        # Check for high-priority actions
        high_priority = data.get("high_priority_actions", 0)
        if high_priority == 0 and sentiment.get("score", 0) < -0.3:
            score -= 0.15
            issues.append("Negative feedback without high-priority actions")
            suggestions.append("Escalate negative sentiment feedback")

        # Penalize repeated attempts
        if attempt_number > 1:
            score -= 0.05 * (attempt_number - 1)

        return {
            "score": max(0.0, min(1.0, score)),
            "issues": issues,
            "suggestions": suggestions,
        }


# ════════════════════════════════════════════════════════════════════
# Customer Satisfaction Loop
# ════════════════════════════════════════════════════════════════════


class CustomerSatisfactionLoop:
    """
    Self-improving customer satisfaction loop.

    Collects feedback, analyzes sentiment, generates improvements,
    and tracks satisfaction over time using the Reflexion pattern.

    Usage:
        loop = CustomerSatisfactionLoop()

        # Process feedback
        result = await loop.process_feedback(CustomerFeedback(
            customer_id="c123",
            text="The reports are great but sometimes arrive late",
            rating=3,
        ))

        # Get satisfaction metrics
        snapshot = loop.get_satisfaction_snapshot()
    """

    def __init__(
        self,
        quality_threshold: float = 0.65,
        max_attempts: int = 2,
        learning_system: Optional[LearningSystem] = None,
        event_bus: Any = None,
    ):
        self._learning = learning_system or LearningSystem()
        self._feedback_history: List[CustomerFeedback] = []
        self._sentiment_history: List[SentimentAnalysis] = []
        self._actions: List[ImprovementAction] = []
        self._snapshots: List[SatisfactionSnapshot] = []

        self._engine = create_reflexion_engine(
            executor=SatisfactionExecutor(),
            critic=SatisfactionCritic(),
            reviser=AdaptiveReviser(),
            quality_threshold=quality_threshold,
            max_attempts=max_attempts,
            event_bus=event_bus,
        )
        self._event_bus = event_bus
        self._logger = logger.bind(component="customer_satisfaction_loop")

    async def process_feedback(self, feedback: CustomerFeedback) -> ReflexionResult:
        """
        Process a piece of customer feedback with self-improvement.

        Returns a ReflexionResult with sentiment analysis and improvement actions.
        """
        self._feedback_history.append(feedback)

        task = {
            "text": feedback.text,
            "customer_id": feedback.customer_id,
            "channel": feedback.channel.value,
            "rating": feedback.rating,
        }

        self._logger.info(
            "feedback_processing_started",
            customer_id=feedback.customer_id,
            channel=feedback.channel.value,
            has_rating=feedback.rating is not None,
        )

        result = await self._engine.run(
            task=task,
            task_name=f"feedback:{feedback.customer_id}",
        )

        # Extract and store sentiment
        if result.final_result and result.final_result.get("success"):
            sentiment_data = result.final_result.get("data", {}).get("sentiment", {})
            analysis = SentimentAnalysis(
                sentiment=Sentiment(sentiment_data.get("sentiment", "neutral")),
                score=sentiment_data.get("score", 0.0),
                confidence=sentiment_data.get("confidence", 0.0),
                key_phrases=sentiment_data.get("key_phrases", []),
                issue_category=IssueCategory(sentiment_data.get("issue_category", "general")),
            )
            self._sentiment_history.append(analysis)

            # Store improvement actions
            for action_data in result.final_result.get("data", {}).get("improvement_actions", []):
                self._actions.append(ImprovementAction(
                    category=IssueCategory(action_data.get("category", "general")),
                    description=action_data.get("description", ""),
                    priority=action_data.get("priority", "medium"),
                    estimated_impact=action_data.get("estimated_impact", 0.0),
                ))

        # Record in learning system
        if result.status == ReflexionStatus.ACCEPTED:
            self._learning.record_success(
                agent_name="CustomerSatisfactionLoop",
                task_name="process_feedback",
                quality_score=result.final_score,
                duration_ms=result.total_duration_ms,
            )
        else:
            self._learning.record_failure(
                agent_name="CustomerSatisfactionLoop",
                task_name="process_feedback",
                error=f"Quality below threshold: {result.final_score:.2f}",
            )

        # Record satisfaction metric
        if self._sentiment_history:
            latest = self._sentiment_history[-1]
            self._learning.record_metric(
                agent_name="CustomerSatisfactionLoop",
                task_name="process_feedback",
                metric_type=MetricType.CUSTOMER_SATISFACTION,
                value=(latest.score + 1) / 2,  # Normalize -1..1 to 0..1
            )

        return result

    def get_satisfaction_snapshot(self) -> SatisfactionSnapshot:
        """Get current satisfaction metrics snapshot."""
        if not self._sentiment_history:
            return SatisfactionSnapshot()

        scores = [s.score for s in self._sentiment_history]
        sentiments = [s.sentiment for s in self._sentiment_history]

        positive_count = sum(
            1 for s in sentiments
            if s in (Sentiment.POSITIVE, Sentiment.VERY_POSITIVE)
        )
        negative_count = sum(
            1 for s in sentiments
            if s in (Sentiment.NEGATIVE, Sentiment.VERY_NEGATIVE)
        )
        total = len(sentiments)

        # Issue frequency
        issue_counts: Dict[str, int] = defaultdict(int)
        for s in self._sentiment_history:
            issue_counts[s.issue_category.value] += 1

        top_issues = sorted(
            [{"category": k, "count": v} for k, v in issue_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:5]

        # NPS estimate: % promoters (score > 0.5) - % detractors (score < -0.5)
        promoters = sum(1 for s in scores if s > 0.5)
        detractors = sum(1 for s in scores if s < -0.5)
        nps = ((promoters - detractors) / total * 100) if total > 0 else 0

        snapshot = SatisfactionSnapshot(
            avg_sentiment_score=sum(scores) / total,
            nps_estimate=round(nps, 1),
            total_feedback=total,
            positive_pct=round(positive_count / total * 100, 1),
            negative_pct=round(negative_count / total * 100, 1),
            top_issues=top_issues,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def get_improvement_actions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent improvement actions."""
        sorted_actions = sorted(
            self._actions,
            key=lambda a: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(a.priority, 4),
        )
        return [a.to_dict() for a in sorted_actions[:limit]]

    def get_stats(self) -> Dict[str, Any]:
        """Get customer satisfaction loop statistics."""
        return {
            "engine_stats": self._engine.get_stats(),
            "total_feedback_processed": len(self._feedback_history),
            "sentiment_distribution": self._get_sentiment_distribution(),
            "top_issues": self._get_issue_distribution(),
            "total_actions_generated": len(self._actions),
            "learning_profile": self._learning.get_profile("CustomerSatisfactionLoop").to_dict(),
        }

    def _get_sentiment_distribution(self) -> Dict[str, int]:
        """Get distribution of sentiment classifications."""
        dist: Dict[str, int] = defaultdict(int)
        for s in self._sentiment_history:
            dist[s.sentiment.value] += 1
        return dict(dist)

    def _get_issue_distribution(self) -> Dict[str, int]:
        """Get distribution of issue categories."""
        dist: Dict[str, int] = defaultdict(int)
        for s in self._sentiment_history:
            dist[s.issue_category.value] += 1
        return dict(dist)
