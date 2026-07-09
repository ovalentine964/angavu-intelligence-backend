"""
LearningAgent — Tier 3 utility agent for feedback analysis and pattern learning.

Analyzes worker feedback, clusters similar feedback, extracts topics
and sentiment. Used by SelfEvolution and MetaAgent.

Tier: 3 (Utility) — stateless, on-demand invocation.
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List

import structlog

from app.agents.base import (
    AgentDecision, AgentEvent, AgentResult, BiasharaAgent,
)

logger = structlog.get_logger(__name__)


class LearningAgent(BiasharaAgent):
    """
    Analyzes feedback and extracts learning patterns.

    Capabilities:
    - Sentiment analysis (keyword-based)
    - Topic extraction (keyword clustering)
    - Feedback clustering by theme
    - Feature request detection
    - Trend detection across feedback batches

    Tier: 3 (Utility) — stateless
    """

    name = "LearningAgent"
    role = "Feedback analysis and pattern learning specialist"
    tier = 3
    capabilities = [
        "feedback_analysis",
        "sentiment_analysis",
        "topic_extraction",
        "feedback_clustering",
        "feature_request_detection",
        "trend_detection",
    ]

    # Sentiment keywords
    POSITIVE_WORDS = {
        "good", "great", "excellent", "helpful", "useful", "love", "amazing",
        "perfect", "thanks", "thank", "nzuri", "sawa", "poa", "vizuri",
        "awesome", "fantastic", "brilliant", "best", "improved", "better",
    }
    NEGATIVE_WORDS = {
        "bad", "poor", "terrible", "useless", "wrong", "error", "bug",
        "broken", "slow", "confusing", "hate", "worst", "mbaya", "bure",
        "awful", "horrible", "frustrating", "annoying", "disappointing",
    }
    FEATURE_INDICATORS = {
        "wish", "want", "need", "should", "could", "please add", "feature",
        "request", "would be nice", "it would help", "nataka", "ningependa",
    }

    def __init__(self):
        super().__init__(name=self.name, role=self.role, capabilities=self.capabilities)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        event = context.get("event", {})
        payload = event.get("payload", {})
        action = payload.get("action", "analyze_feedback")

        if action in ("analyze_feedback", "learn", "extract_patterns"):
            return AgentDecision(
                action="analyze_feedback",
                parameters={
                    "feedback_items": payload.get("feedback_items", []),
                    "language": payload.get("language", "en"),
                },
                confidence=0.85,
                reasoning="Analyzing feedback for patterns and sentiment",
            )
        return AgentDecision(action="noop", parameters={}, confidence=0.5, reasoning="No learning task requested")

    async def act(self, decision: AgentDecision) -> AgentResult:
        start = time.time()
        action = decision.action
        params = decision.parameters

        try:
            if action == "analyze_feedback":
                items = params.get("feedback_items", [])
                result = self._analyze(items)
                duration_ms = (time.time() - start) * 1000
                return AgentResult(success=True, data=result, duration_ms=duration_ms)
            elif action == "noop":
                return AgentResult(success=True, data=None, duration_ms=(time.time() - start) * 1000)
            else:
                return AgentResult(success=False, error=f"Unknown action: {action}", duration_ms=(time.time() - start) * 1000)
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), duration_ms=(time.time() - start) * 1000)

    def _analyze(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Full feedback analysis pipeline."""
        if not items:
            return {"item_count": 0, "sentiment": "neutral", "topics": [], "feature_requests": []}

        sentiments = []
        topics = []
        feature_requests = []

        for item in items:
            text = item.get("text", item.get("feedback", item.get("message", "")))
            if not text:
                continue

            text_lower = text.lower()

            # Sentiment
            pos = sum(1 for w in self.POSITIVE_WORDS if w in text_lower)
            neg = sum(1 for w in self.NEGATIVE_WORDS if w in text_lower)
            if pos > neg:
                sentiments.append("positive")
            elif neg > pos:
                sentiments.append("negative")
            else:
                sentiments.append("neutral")

            # Topics (extract significant words)
            words = re.findall(r'\b[a-zA-Z]{4,}\b', text_lower)
            topics.extend(words)

            # Feature requests
            if any(ind in text_lower for ind in self.FEATURE_INDICATORS):
                feature_requests.append({
                    "text": text[:200],
                    "source": item.get("worker_id", "unknown"),
                })

        # Aggregate
        sentiment_counts = Counter(sentiments)
        total = len(sentiments) or 1
        topic_counts = Counter(topics)
        top_topics = [t for t, _ in topic_counts.most_common(10) if len(t) > 3]

        # Cluster by theme (simple keyword-based)
        clusters = self._cluster_feedback(items)

        return {
            "item_count": len(items),
            "sentiment": {
                "overall": sentiment_counts.most_common(1)[0][0] if sentiment_counts else "neutral",
                "positive_pct": round(sentiment_counts.get("positive", 0) / total * 100, 1),
                "negative_pct": round(sentiment_counts.get("negative", 0) / total * 100, 1),
                "neutral_pct": round(sentiment_counts.get("neutral", 0) / total * 100, 1),
            },
            "top_topics": top_topics,
            "feature_requests": feature_requests[:10],
            "clusters": clusters,
        }

    def _cluster_feedback(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simple keyword-based feedback clustering."""
        theme_keywords = {
            "pricing": {"price", "cost", "expensive", "cheap", "bei", "gharama"},
            "accuracy": {"accurate", "correct", "wrong", "error", "sahihi", "kosa"},
            "usability": {"easy", "difficult", "confusing", "simple", "rahisi", "ngumu"},
            "speed": {"slow", "fast", "quick", "speed", "polepole", "haraka"},
            "features": {"add", "feature", "need", "want", "wish", "ongeza"},
            "delivery": {"deliver", "receive", "send", "message", "tuma", "pata"},
        }

        clusters = defaultdict(list)
        for item in items:
            text = (item.get("text", item.get("feedback", item.get("message", "")))).lower()
            matched = False
            for theme, keywords in theme_keywords.items():
                if any(kw in text for kw in keywords):
                    clusters[theme].append(text[:100])
                    matched = True
                    break
            if not matched:
                clusters["general"].append(text[:100])

        return [
            {"theme": theme, "count": len(feedbacks), "samples": feedbacks[:3]}
            for theme, feedbacks in sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
        ]
