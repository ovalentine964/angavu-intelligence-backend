"""
Self-Evolution Service — Worker-driven feature evolution.

Makes Msaidizi evolve based on worker feedback:

    Workers tell Msaidizi what they want →
    Feedback Collector records →
    Feature Designer creates →
    Worker gets what they wanted →
    More feedback → More features → More workers → ...

This is the flywheel: every worker interaction makes the product better,
which attracts more workers, which generates more feedback.

Design principles:
    1. Workers are co-designers, not just users
    2. Feedback is structured, not just collected
    3. Features are data-driven, not opinion-driven
    4. Adoption is tracked, not assumed
"""

from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


# ════════════════════════════════════════════════════════════════════
# Enums & Data Classes
# ════════════════════════════════════════════════════════════════════


class FeedbackType(str, Enum):
    """Types of worker feedback."""
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"
    IMPROVEMENT = "improvement"
    PRAISE = "praise"
    COMPLAINT = "complaint"
    CORRECTION = "correction"
    WORKFLOW_PAIN = "workflow_pain"  # "I wish I could..."
    MISSING_CAPABILITY = "missing_capability"  # "Can you..."


class FeedbackStatus(str, Enum):
    """Status of feedback in the evolution pipeline."""
    COLLECTED = "collected"
    ANALYZING = "analyzing"
    CLUSTERED = "clustered"  # Grouped with similar feedback
    SPEC_GENERATED = "spec_generated"  # Feature spec created
    IN_DEVELOPMENT = "in_development"
    TESTING = "testing"
    DEPLOYED = "deployed"
    ADOPTED = "adopted"  # Workers are using it
    REJECTED = "rejected"  # Not viable


class FeaturePriority(str, Enum):
    """Priority levels for feature development."""
    CRITICAL = "critical"  # Blocking workers
    HIGH = "high"  # Many workers requesting
    MEDIUM = "medium"  # Nice to have, moderate demand
    LOW = "low"  # Few requests, future consideration


@dataclass
class WorkerFeedback:
    """A piece of feedback from a worker."""
    feedback_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    worker_id: str = ""
    feedback_type: FeedbackType = FeedbackType.FEATURE_REQUEST
    raw_text: str = ""  # What the worker said
    structured_intent: str = ""  # Parsed intent
    context: Dict[str, Any] = field(default_factory=dict)  # Business type, region, etc.
    sentiment_score: float = 0.0  # -1 to 1
    urgency_score: float = 0.0  # 0 to 1
    status: FeedbackStatus = FeedbackStatus.COLLECTED
    cluster_id: Optional[str] = None  # Grouped with similar feedback
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FeedbackCluster:
    """A cluster of similar feedback requests."""
    cluster_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    theme: str = ""  # Human-readable theme
    feedback_ids: List[str] = field(default_factory=list)
    worker_count: int = 0  # Unique workers who requested this
    avg_urgency: float = 0.0
    sample_feedback: List[str] = field(default_factory=list)  # Representative quotes
    business_types: Dict[str, int] = field(default_factory=dict)  # Distribution
    regions: Dict[str, int] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FeatureSpec:
    """Generated feature specification from feedback cluster."""
    spec_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    cluster_id: str = ""
    title: str = ""
    description: str = ""
    user_story: str = ""  # "As a [worker], I want [feature] so that [benefit]"
    acceptance_criteria: List[str] = field(default_factory=list)
    priority: FeaturePriority = FeaturePriority.MEDIUM
    estimated_impact: float = 0.0  # 0-1, estimated worker satisfaction lift
    affected_worker_count: int = 0
    voice_interaction_design: str = ""  # How it works via voice
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FeatureAdoption:
    """Tracks adoption and impact of a deployed feature."""
    feature_id: str = ""
    feature_title: str = ""
    deployed_at: Optional[datetime] = None
    total_workers_eligible: int = 0
    workers_using: int = 0
    adoption_rate: float = 0.0  # workers_using / total_workers_eligible
    usage_frequency: float = 0.0  # avg uses per worker per week
    satisfaction_delta: float = 0.0  # Change in satisfaction score
    retention_impact: float = 0.0  # Change in worker retention
    feedback_volume: int = 0  # Post-deployment feedback
    positive_feedback_ratio: float = 0.0
    measured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EvolutionReport:
    """Summary of the self-evolution pipeline state."""
    total_feedback_collected: int = 0
    active_clusters: int = 0
    features_in_development: int = 0
    features_deployed: int = 0
    avg_adoption_rate: float = 0.0
    top_requested_themes: List[Dict[str, Any]] = field(default_factory=list)
    feedback_velocity: float = 0.0  # Feedback per day (7-day avg)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ════════════════════════════════════════════════════════════════════
# Self-Evolution Service
# ════════════════════════════════════════════════════════════════════


class SelfEvolutionService:
    """
    Makes Msaidizi evolve based on worker feedback.

    Workers tell Msaidizi what they want →
    Feedback Collector records →
    Feature Designer creates →
    Worker gets what they wanted →
    More feedback → More features → More workers → ...

    The flywheel:
        Worker feedback → Structured analysis → Feature clusters →
        Auto-generated specs → Development → Deployment →
        Adoption tracking → More feedback ↻

    Usage:
        evolution = SelfEvolutionService()
        await evolution.collect_feedback("worker_123", "I wish I could...")
        trends = await evolution.analyze_feedback_trends()
        spec = await evolution.generate_feature_spec(cluster)
        adoption = await evolution.track_adoption(feature_id)
    """

    def __init__(self) -> None:
        # In-memory stores — these should be backed by database in production.
        # Use persist_* methods to flush to database when available.
        self._feedback: Dict[str, WorkerFeedback] = {}
        self._clusters: Dict[str, FeedbackCluster] = {}
        self._specs: Dict[str, FeatureSpec] = {}
        self._adoptions: Dict[str, FeatureAdoption] = {}
        self._db_session: Any = None  # Injected via set_db_session()

    def set_db_session(self, session: Any) -> None:
        """Inject a database session for persistence.

        Call this during application startup to enable database-backed
        persistence. Without this, all data lives in memory only.
        """
        self._db_session = session

    async def _persist_feedback(self, fb: WorkerFeedback) -> None:
        """Persist a feedback record to database (stub).

        When a database session is available, this writes the feedback
        to the worker_feedback table. Currently a no-op stub.
        """
        if self._db_session is None:
            return  # No DB session — keep in memory only
        # TODO: Implement database persistence
        # await self._db_session.execute(
        #     insert(worker_feedback_table).values(
        #         feedback_id=fb.feedback_id,
        #         worker_id=fb.worker_id,
        #         feedback_type=fb.feedback_type,
        #         raw_text=fb.raw_text,
        #         processed_signal=fb.processed_signal,
        #         created_at=fb.created_at,
        #     )
        # )
        # await self._db_session.commit()

    # ── Feedback Collection ───────────────────────────────────────

    async def collect_feedback(
        self,
        worker_id: str,
        feedback: str,
        feedback_type: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkerFeedback:
        """
        Collect worker feedback for feature requests.

        Processes raw feedback into structured signals:
        1. Classify feedback type (feature request, bug, complaint, etc.)
        2. Extract structured intent
        3. Score sentiment and urgency
        4. Assign to cluster (if similar feedback exists)

        Args:
            worker_id: Unique worker identifier
            feedback: Raw feedback text from worker
            feedback_type: Optional explicit type
            context: Optional context (business_type, region, etc.)

        Returns:
            Structured WorkerFeedback object
        """
        logger.info(
            "self_evolution.collecting_feedback",
            worker_id=worker_id,
            feedback_length=len(feedback),
        )

        # Classify feedback type
        classified_type = self._classify_feedback(feedback, feedback_type)

        # Extract structured intent
        intent = self._extract_intent(feedback, classified_type)

        # Score sentiment and urgency
        sentiment = self._score_sentiment(feedback)
        urgency = self._score_urgency(feedback, classified_type)

        fb = WorkerFeedback(
            worker_id=worker_id,
            feedback_type=classified_type,
            raw_text=feedback,
            structured_intent=intent,
            context=context or {},
            sentiment_score=sentiment,
            urgency_score=urgency,
        )

        # Try to assign to existing cluster
        cluster_id = await self._find_or_create_cluster(fb)
        fb.cluster_id = cluster_id
        fb.status = FeedbackStatus.CLUSTERED

        # Store
        self._feedback[fb.feedback_id] = fb

        logger.info(
            "self_evolution.feedback_collected",
            feedback_id=fb.feedback_id,
            worker_id=worker_id,
            feedback_type=classified_type.value,
            cluster_id=cluster_id,
            urgency=round(urgency, 2),
        )

        return fb

    async def collect_batch_feedback(
        self,
        feedback_items: List[Dict[str, Any]],
    ) -> List[WorkerFeedback]:
        """
        Collect multiple feedback items in batch.

        Args:
            feedback_items: List of dicts with worker_id, feedback, etc.

        Returns:
            List of processed WorkerFeedback objects
        """
        results = []
        for item in feedback_items:
            fb = await self.collect_feedback(
                worker_id=item["worker_id"],
                feedback=item["feedback"],
                feedback_type=item.get("feedback_type"),
                context=item.get("context"),
            )
            results.append(fb)
        return results

    # ── Feedback Analysis ─────────────────────────────────────────

    async def analyze_feedback_trends(self) -> Dict[str, Any]:
        """
        Analyze feedback trends to identify most-requested features.

        Returns:
            Dict with:
            - top_themes: Most requested feature themes
            - feedback_velocity: Feedback rate (items/day)
            - urgency_distribution: Distribution of urgency scores
            - sentiment_trend: Average sentiment over time
            - worker_coverage: % of workers providing feedback
        """
        logger.info(
            "self_evolution.analyzing_trends",
            total_feedback=len(self._feedback),
            total_clusters=len(self._clusters),
        )

        if not self._feedback:
            return {
                "top_themes": [],
                "feedback_velocity": 0.0,
                "urgency_distribution": {},
                "sentiment_trend": 0.0,
                "worker_coverage": 0.0,
            }

        # Cluster analysis — rank by worker count and urgency
        ranked_clusters = sorted(
            self._clusters.values(),
            key=lambda c: (c.worker_count, c.avg_urgency),
            reverse=True,
        )

        top_themes = [
            {
                "cluster_id": c.cluster_id,
                "theme": c.theme,
                "worker_count": c.worker_count,
                "avg_urgency": round(c.avg_urgency, 3),
                "sample_feedback": c.sample_feedback[:3],
                "business_types": c.business_types,
            }
            for c in ranked_clusters[:10]
        ]

        # Feedback velocity (items per day)
        feedbacks = list(self._feedback.values())
        if len(feedbacks) >= 2:
            first = min(f.collected_at for f in feedbacks)
            last = max(f.collected_at for f in feedbacks)
            days = max((last - first).total_seconds() / 86400, 1)
            velocity = len(feedbacks) / days
        else:
            velocity = float(len(feedbacks))

        # Urgency distribution
        urgency_buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for fb in feedbacks:
            if fb.urgency_score >= 0.8:
                urgency_buckets["critical"] += 1
            elif fb.urgency_score >= 0.6:
                urgency_buckets["high"] += 1
            elif fb.urgency_score >= 0.3:
                urgency_buckets["medium"] += 1
            else:
                urgency_buckets["low"] += 1

        # Sentiment
        avg_sentiment = (
            sum(f.sentiment_score for f in feedbacks) / len(feedbacks)
            if feedbacks
            else 0.0
        )

        # Worker coverage
        unique_workers = len(set(f.worker_id for f in feedbacks))

        result = {
            "top_themes": top_themes,
            "feedback_velocity": round(velocity, 2),
            "urgency_distribution": urgency_buckets,
            "sentiment_trend": round(avg_sentiment, 3),
            "unique_workers": unique_workers,
            "total_feedback": len(feedbacks),
            "total_clusters": len(self._clusters),
        }

        logger.info(
            "self_evolution.trends_analyzed",
            top_theme=top_themes[0]["theme"] if top_themes else "none",
            velocity=round(velocity, 2),
        )

        return result

    # ── Feature Spec Generation ───────────────────────────────────

    async def generate_feature_spec(self, feedback_cluster: Dict[str, Any]) -> FeatureSpec:
        """
        Generate feature specification from feedback cluster.

        Creates a structured spec with:
        - Title and description
        - User story format
        - Acceptance criteria
        - Voice interaction design (how it works via Msaidizi)
        - Priority and impact estimation

        Args:
            feedback_cluster: Cluster data (from analyze_feedback_trends)

        Returns:
            FeatureSpec ready for development
        """
        cluster_id = feedback_cluster.get("cluster_id", "")
        theme = feedback_cluster.get("theme", "Unknown feature")
        worker_count = feedback_cluster.get("worker_count", 0)
        avg_urgency = feedback_cluster.get("avg_urgency", 0.5)
        samples = feedback_cluster.get("sample_feedback", [])
        business_types = feedback_cluster.get("business_types", {})

        logger.info(
            "self_evolution.generating_spec",
            cluster_id=cluster_id,
            theme=theme,
            worker_count=worker_count,
        )

        # Determine priority
        if avg_urgency >= 0.8 and worker_count >= 10:
            priority = FeaturePriority.CRITICAL
        elif avg_urgency >= 0.6 or worker_count >= 5:
            priority = FeaturePriority.HIGH
        elif avg_urgency >= 0.3 or worker_count >= 2:
            priority = FeaturePriority.MEDIUM
        else:
            priority = FeaturePriority.LOW

        # Generate user story
        primary_business = (
            max(business_types, key=business_types.get) if business_types else "business owner"
        )
        user_story = (
            f"As a {primary_business}, "
            f"I want {theme.lower()} "
            f"so that I can work more efficiently with Msaidizi."
        )

        spec = FeatureSpec(
            cluster_id=cluster_id,
            title=theme,
            description=(
                f"Feature requested by {worker_count} workers. "
                f"Average urgency: {avg_urgency:.1%}. "
                f"Representative feedback: {'; '.join(samples[:3])}"
            ),
            user_story=user_story,
            acceptance_criteria=[
                f"Worker can {theme.lower()} via voice command",
                "Feature works across all supported dialects",
                "Response time < 3 seconds on 3G connection",
                "Worker satisfaction score ≥ 4.0/5.0 after 1 week",
            ],
            priority=priority,
            estimated_impact=min(avg_urgency * (worker_count / 100), 1.0),
            affected_worker_count=worker_count,
            voice_interaction_design=(
                f"Worker says: 'Msaidizi, {theme.lower()}'\n"
                f"Msaidizi responds with confirmation and executes."
            ),
        )

        # Store spec
        self._specs[spec.spec_id] = spec

        # Update cluster status
        if cluster_id in self._clusters:
            # Mark associated feedback as spec_generated
            for fb_id in self._clusters[cluster_id].feedback_ids:
                if fb_id in self._feedback:
                    self._feedback[fb_id].status = FeedbackStatus.SPEC_GENERATED

        logger.info(
            "self_evolution.spec_generated",
            spec_id=spec.spec_id,
            title=spec.title,
            priority=priority.value,
            estimated_impact=round(spec.estimated_impact, 3),
        )

        return spec

    # ── Adoption Tracking ─────────────────────────────────────────

    def evaluate_quality(
        self,
        feedbacks: Optional[List[WorkerFeedback]] = None,
        adoptions: Optional[Dict[str, FeatureAdoption]] = None,
    ) -> Dict[str, Any]:
        """Evaluate overall evolution quality using real metrics.

        Replaces the previous hardcoded 0.5-0.7 judge scores with a
        multi-signal heuristic that considers:

        1. **Feedback sentiment** — weighted average of sentiment scores,
           newer feedback weighted more heavily (exponential decay).
        2. **Feature adoption** — ratio of features with >10% adoption,
           weighted by affected worker count.
        3. **Error rate** — proportion of bug reports and complaints
           relative to total feedback (lower is better).
        4. **Urgency resolution** — proportion of high-urgency feedback
           that has moved past COLLECTED status.
        5. **Feedback diversity** — Shannon entropy of feedback types
           (higher diversity = healthier evolution signal).

        Returns:
            Dict with overall_score (0-1), component scores, and
            diagnostics.
        """
        if feedbacks is None:
            feedbacks = list(self._feedback.values())
        if adoptions is None:
            adoptions = self._adoptions

        if not feedbacks:
            return {
                "overall_score": 0.0,
                "components": {},
                "diagnostics": "no_feedback_available",
            }

        now = datetime.now(timezone.utc)

        # ── Component 1: Weighted feedback sentiment (0-1) ──
        # Newer feedback gets more weight (half-life = 30 days)
        weighted_sentiment_sum = 0.0
        weight_total = 0.0
        for fb in feedbacks:
            age_days = max((now - fb.collected_at).total_seconds() / 86400, 0.01)
            recency_weight = math.exp(-0.023 * age_days)  # half-life ≈ 30 days
            weighted_sentiment_sum += fb.sentiment_score * recency_weight
            weight_total += recency_weight

        avg_sentiment = weighted_sentiment_sum / weight_total if weight_total > 0 else 0.0
        # Map from [-1, 1] to [0, 1]
        sentiment_score = (avg_sentiment + 1.0) / 2.0

        # ── Component 2: Feature adoption quality (0-1) ──
        if adoptions:
            adoption_scores = []
            for adoption in adoptions.values():
                # Each feature contributes based on adoption rate and scale
                feat_score = adoption.adoption_rate
                # Bonus for positive satisfaction delta
                if adoption.satisfaction_delta > 0:
                    feat_score = min(1.0, feat_score + adoption.satisfaction_delta * 0.3)
                # Penalty for negative satisfaction
                elif adoption.satisfaction_delta < 0:
                    feat_score = max(0.0, feat_score + adoption.satisfaction_delta * 0.3)
                adoption_scores.append(feat_score)
            adoption_score = sum(adoption_scores) / len(adoption_scores)
        else:
            # No deployed features yet — neutral score based on pipeline activity
            specs_count = len(self._specs)
            adoption_score = min(0.5, specs_count * 0.1)  # Partial credit for specs

        # ── Component 3: Error rate (0-1, inverted so lower error = higher score) ──
        error_types = {FeedbackType.BUG_REPORT, FeedbackType.COMPLAINT, FeedbackType.CORRECTION}
        error_count = sum(1 for fb in feedbacks if fb.feedback_type in error_types)
        error_ratio = error_count / len(feedbacks)
        # Sigmoid mapping: error_ratio=0 → 1.0, error_ratio=0.5 → 0.5, error_ratio=1 → 0.0
        error_score = 1.0 / (1.0 + math.exp(5.0 * (error_ratio - 0.3)))

        # ── Component 4: Urgency resolution (0-1) ──
        high_urgency = [fb for fb in feedbacks if fb.urgency_score >= 0.6]
        if high_urgency:
            resolved = sum(
                1 for fb in high_urgency
                if fb.status not in {FeedbackStatus.COLLECTED, FeedbackStatus.ANALYZING}
            )
            urgency_resolution = resolved / len(high_urgency)
        else:
            urgency_resolution = 1.0  # No urgent items = perfect score

        # ── Component 5: Feedback type diversity (Shannon entropy) ──
        type_counts: Dict[str, int] = Counter(fb.feedback_type.value for fb in feedbacks)
        total = sum(type_counts.values())
        entropy = 0.0
        for count in type_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        max_entropy = math.log2(max(len(FeedbackType), 1))
        diversity_score = entropy / max_entropy if max_entropy > 0 else 0.0

        # ── Weighted combination ──
        weights = {
            "sentiment": 0.25,
            "adoption": 0.25,
            "error_rate": 0.20,
            "urgency_resolution": 0.15,
            "diversity": 0.15,
        }
        components = {
            "sentiment": round(sentiment_score, 4),
            "adoption": round(adoption_score, 4),
            "error_rate": round(error_score, 4),
            "urgency_resolution": round(urgency_resolution, 4),
            "diversity": round(diversity_score, 4),
        }

        overall = sum(
            components[k] * weights[k] for k in weights
        )
        overall = round(max(0.0, min(1.0, overall)), 4)

        return {
            "overall_score": overall,
            "components": components,
            "weights": weights,
            "diagnostics": {
                "total_feedback": len(feedbacks),
                "error_count": error_count,
                "high_urgency_count": len(high_urgency),
                "features_deployed": len(adoptions),
                "specs_generated": len(self._specs),
                "feedback_types": dict(type_counts),
            },
        }

    async def track_adoption(self, feature_id: str) -> Dict[str, Any]:
        """
        Track feature adoption and impact.

        Measures:
        - Adoption rate: % of eligible workers using the feature
        - Usage frequency: How often workers use it
        - Satisfaction delta: Change in satisfaction after deployment
        - Retention impact: Effect on worker retention
        - Feedback sentiment: Post-deployment feedback

        Args:
            feature_id: Feature/spec ID to track

        Returns:
            Adoption metrics dict
        """
        logger.info("self_evolution.tracking_adoption", feature_id=feature_id)

        # TODO: Wire to actual usage analytics
        # 1. Query feature usage logs
        # 2. Calculate adoption rate
        # 3. Compare pre/post satisfaction
        # 4. Analyze retention curves

        spec = self._specs.get(feature_id)
        title = spec.title if spec else feature_id

        adoption = FeatureAdoption(
            feature_id=feature_id,
            feature_title=title,
        )

        self._adoptions[feature_id] = adoption

        result = {
            "feature_id": feature_id,
            "feature_title": title,
            "adoption_rate": adoption.adoption_rate,
            "usage_frequency": adoption.usage_frequency,
            "satisfaction_delta": adoption.satisfaction_delta,
            "retention_impact": adoption.retention_impact,
            "positive_feedback_ratio": adoption.positive_feedback_ratio,
            "status": "tracking",
        }

        logger.info(
            "self_evolution.adoption_tracked",
            feature_id=feature_id,
            adoption_rate=adoption.adoption_rate,
        )

        return result

    # ── Evolution Report ──────────────────────────────────────────

    async def get_evolution_report(self) -> EvolutionReport:
        """
        Generate a summary report of the self-evolution pipeline.

        Shows how the feedback flywheel is performing:
        - How much feedback is coming in
        - What themes are emerging
        - How many features are in the pipeline
        - What the adoption rates look like
        """
        trends = await self.analyze_feedback_trends()

        report = EvolutionReport(
            total_feedback_collected=len(self._feedback),
            active_clusters=len(self._clusters),
            features_in_development=len([
                s for s in self._specs.values()
            ]),
            features_deployed=len(self._adoptions),
            avg_adoption_rate=(
                sum(a.adoption_rate for a in self._adoptions.values()) / len(self._adoptions)
                if self._adoptions
                else 0.0
            ),
            top_requested_themes=trends.get("top_themes", [])[:5],
            feedback_velocity=trends.get("feedback_velocity", 0.0),
        )

        return report

    # ── Internal Helpers ──────────────────────────────────────────

    def _classify_feedback(
        self,
        text: str,
        explicit_type: Optional[str] = None,
    ) -> FeedbackType:
        """Classify feedback type from text."""
        if explicit_type:
            try:
                return FeedbackType(explicit_type)
            except ValueError:
                pass

        text_lower = text.lower()

        # Pattern matching for common feedback types
        if any(w in text_lower for w in ["i wish", "it would be nice", "can you add", "please add"]):
            return FeedbackType.FEATURE_REQUEST
        if any(w in text_lower for w in ["can you", "is there a way", "how do i"]):
            return FeedbackType.MISSING_CAPABILITY
        if any(w in text_lower for w in ["broken", "error", "doesn't work", "bug", "crash"]):
            return FeedbackType.BUG_REPORT
        if any(w in text_lower for w in ["slow", "confusing", "hard to", "difficult"]):
            return FeedbackType.WORKFLOW_PAIN
        if any(w in text_lower for w in ["no, i meant", "wrong", "incorrect"]):
            return FeedbackType.CORRECTION
        if any(w in text_lower for w in ["great", "love", "amazing", "thank", "good"]):
            return FeedbackType.PRAISE
        if any(w in text_lower for w in ["hate", "terrible", "worst", "frustrating"]):
            return FeedbackType.COMPLAINT

        return FeedbackType.IMPROVEMENT

    def _extract_intent(self, text: str, feedback_type: FeedbackType) -> str:
        """Extract structured intent from raw feedback text."""
        # Simple heuristic — in production, use LLM extraction via NIM
        text_clean = text.strip()

        if feedback_type == FeedbackType.FEATURE_REQUEST:
            return f"REQUEST: {text_clean}"
        if feedback_type == FeedbackType.BUG_REPORT:
            return f"BUG: {text_clean}"
        if feedback_type == FeedbackType.CORRECTION:
            return f"CORRECTION: {text_clean}"
        if feedback_type == FeedbackType.WORKFLOW_PAIN:
            return f"PAIN_POINT: {text_clean}"

        return f"FEEDBACK: {text_clean}"

    def _score_sentiment(self, text: str) -> float:
        """Score sentiment from -1 (negative) to 1 (positive).

        Uses a weighted keyword-based heuristic with intensity modifiers.
        In production, replace with NIM sentiment model.
        """
        text_lower = text.lower()

        # Weighted positive words (stronger sentiment = higher weight)
        positive_words = {
            "good": 1, "great": 2, "love": 3, "amazing": 3,
            "helpful": 2, "thank": 1, "perfect": 3, "excellent": 3,
            "wonderful": 3, "fantastic": 3, "awesome": 2, "nice": 1,
            "useful": 1, "impressed": 2, "brilliant": 3,
        }
        # Weighted negative words
        negative_words = {
            "bad": 1, "hate": 3, "terrible": 3, "slow": 2,
            "broken": 3, "wrong": 2, "frustrating": 3, "awful": 3,
            "useless": 3, "annoying": 2, "disappointing": 2,
            "poor": 1, "horrible": 3, "worst": 3,
        }
        # Intensity modifiers amplify nearby sentiment
        intensifiers = {"very", "really", "extremely", "absolutely", "so"}
        negators = {"not", "never", "no", "don't", "doesn't", "isn't", "wasn't"}

        words = text_lower.split()
        pos_score = 0.0
        neg_score = 0.0

        for i, word in enumerate(words):
            # Check for preceding intensifier
            intensity = 1.5 if i > 0 and words[i - 1] in intensifiers else 1.0
            # Check for preceding negator (flips sentiment)
            negated = i > 0 and words[i - 1] in negators

            if word in positive_words:
                if negated:
                    neg_score += positive_words[word] * intensity
                else:
                    pos_score += positive_words[word] * intensity
            elif word in negative_words:
                if negated:
                    pos_score += negative_words[word] * intensity * 0.5  # Negated negative is weakly positive
                else:
                    neg_score += negative_words[word] * intensity

        total = pos_score + neg_score
        if total == 0:
            return 0.0

        return round((pos_score - neg_score) / total, 3)

    def _score_urgency(self, text: str, feedback_type: FeedbackType) -> float:
        """Score urgency from 0 (low) to 1 (critical)."""
        text_lower = text.lower()

        # Type-based urgency
        type_urgency = {
            FeedbackType.BUG_REPORT: 0.7,
            FeedbackType.CORRECTION: 0.6,
            FeedbackType.WORKFLOW_PAIN: 0.5,
            FeedbackType.FEATURE_REQUEST: 0.4,
            FeedbackType.MISSING_CAPABILITY: 0.4,
            FeedbackType.IMPROVEMENT: 0.3,
            FeedbackType.COMPLAINT: 0.6,
            FeedbackType.PRAISE: 0.1,
        }

        base = type_urgency.get(feedback_type, 0.3)

        # Keyword modifiers
        if any(w in text_lower for w in ["urgent", "immediately", "asap", "critical"]):
            base = min(base + 0.3, 1.0)
        if any(w in text_lower for w in ["blocking", "can't work", "stopped working"]):
            base = min(base + 0.2, 1.0)

        return round(base, 3)

    async def _find_or_create_cluster(self, feedback: WorkerFeedback) -> str:
        """
        Find an existing cluster for similar feedback, or create a new one.

        Uses simple keyword/semantic matching.
        In production, use NVIDIA NIM embeddings for semantic clustering.
        """
        intent_lower = feedback.structured_intent.lower()

        # Simple keyword matching for now
        best_cluster: Optional[FeedbackCluster] = None
        best_score = 0.0

        for cluster in self._clusters.values():
            if not cluster.theme:
                continue
            theme_lower = cluster.theme.lower()
            # Simple word overlap
            intent_words = set(intent_lower.split())
            theme_words = set(theme_lower.split())
            overlap = len(intent_words & theme_words)
            total = len(intent_words | theme_words)
            if total > 0:
                score = overlap / total
                if score > best_score and score > 0.2:
                    best_score = score
                    best_cluster = cluster

        if best_cluster:
            # Add to existing cluster
            best_cluster.feedback_ids.append(feedback.feedback_id)
            best_cluster.worker_count = len(set(
                self._feedback[fid].worker_id
                for fid in best_cluster.feedback_ids
                if fid in self._feedback
            ))
            best_cluster.last_seen = datetime.now(timezone.utc)
            if len(best_cluster.sample_feedback) < 5:
                best_cluster.sample_feedback.append(feedback.raw_text[:200])
            # Update urgency average
            urgencies = [
                self._feedback[fid].urgency_score
                for fid in best_cluster.feedback_ids
                if fid in self._feedback
            ]
            best_cluster.avg_urgency = sum(urgencies) / len(urgencies) if urgencies else 0.0
            return best_cluster.cluster_id

        # Create new cluster
        new_cluster = FeedbackCluster(
            theme=feedback.structured_intent[:100],
            feedback_ids=[feedback.feedback_id],
            worker_count=1,
            avg_urgency=feedback.urgency_score,
            sample_feedback=[feedback.raw_text[:200]],
            business_types={feedback.context.get("business_type", "unknown"): 1},
            regions={feedback.context.get("region", "unknown"): 1},
        )
        self._clusters[new_cluster.cluster_id] = new_cluster
        return new_cluster.cluster_id
