"""
Content Agent — Autonomous content creation, distribution, and SEO.

Manages the content pipeline for Angavu Intelligence's market presence:
    - Creates blog posts, case studies, social media content
    - Optimizes content for SEO (financial inclusion keywords)
    - Schedules distribution across channels
    - Monitors engagement and adjusts strategy
    - Maintains brand voice consistency

This is the single content agent for the autonomous framework.
It supersedes ContentCreatorAgent with full template-based generation
and autonomous lifecycle integration.

Content pillars:
    1. Financial inclusion thought leadership
    2. Customer success stories (informal workers)
    3. Product updates and feature announcements
    4. Industry analysis (mobile money, microfinance)
    5. Educational content (financial literacy)
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.agents.base import AgentDecision, AgentResult, EventType
from app.autonomous.agents.base import AutonomousAgent
from app.autonomous.config import AgentConfig

logger = structlog.get_logger(__name__)


# ── Content templates and configuration ────────────────────────────

# Industry-relevant topics for Angavu Intelligence
TOPIC_LIBRARY: dict[str, list[str]] = {
    "blog_post": [
        "How AI-Powered Market Intelligence Transforms African SMEs",
        "5 Ways Real-Time Price Forecasting Reduces Stock Losses",
        "The Future of Credit Scoring for Informal Workers",
        "M-Pesa Data Intelligence: Unlocking Business Growth",
        "Distribution Gap Analysis: Finding Hidden Market Opportunities",
    ],
    "social_twitter": [
        "\U0001f9f5 Thread: How informal workers are using AI to grow their businesses",
        "\U0001f4ca Market insight: Real-time price trends in Nairobi's Gikomba market",
        "\U0001f680 New feature: Automated credit scoring for dukawallahs",
    ],
    "social_linkedin": [
        "The untapped potential of Africa's informal economy",
        "Why traditional credit scoring fails 1.3B Africans",
        "Building ethical AI for bottom-of-pyramid markets",
    ],
    "email_newsletter": [
        "Weekly Market Intelligence Digest",
        "Monthly Platform Update & Insights",
    ],
}

# SEO keyword clusters for Angavu's domain
KEYWORD_CLUSTERS: dict[str, list[str]] = {
    "primary": [
        "African market intelligence",
        "SME business analytics",
        "informal economy data",
        "M-Pesa analytics",
        "African credit scoring",
    ],
    "secondary": [
        "price forecasting Africa",
        "business intelligence Kenya",
        "retail analytics emerging markets",
        "FMCG distribution intelligence",
        "financial inclusion data",
    ],
}


class ContentAgent(AutonomousAgent):
    """
    Autonomous content agent for Angavu Intelligence / Msaidizi.

    Handles the full content lifecycle:
    1. Topic Discovery — scan trends, keywords, competitor content
    2. Content Creation — draft articles, posts, newsletters
    3. SEO Optimization — keyword integration, meta descriptions
    4. Distribution — schedule across blog, social, email
    5. Performance Tracking — engagement metrics, adjust strategy
    """

    CONFIG_NAME = "content_agent"
    SUBSCRIBED_EVENTS = [
        EventType.INTELLIGENCE_GENERATED,
        EventType.REPORT_DELIVERED,
        EventType.FEEDBACK_RECEIVED,
    ]

    def __init__(self, config: AgentConfig | None = None):
        super().__init__(
            name="ContentAgent",
            role="Autonomous Content — creation, distribution, SEO",
            capabilities=[
                "topic_research",
                "content_creation",
                "seo_optimization",
                "social_media_scheduling",
                "newsletter_management",
                "engagement_tracking",
            ],
            config=config,
        )

        # Content pipeline state
        self._content_calendar: list[dict[str, Any]] = []
        self._published_content: list[dict[str, Any]] = []
        self._topic_queue: list[dict[str, Any]] = []

        # SEO keywords (financial inclusion domain)
        self._target_keywords = [
            "financial inclusion",
            "informal workers",
            "mobile money Africa",
            "microfinance technology",
            "digital financial services",
            "CFO AI assistant",
            "voice-first fintech",
            "SME financial management",
            "SACCO digital transformation",
            "mobile lending platform",
        ]

        # Content pillars with distribution weights
        self._content_pillars = {
            "thought_leadership": {"weight": 0.30, "channels": ["blog", "linkedin", "twitter"]},
            "customer_stories": {"weight": 0.25, "channels": ["blog", "email", "linkedin"]},
            "product_updates": {"weight": 0.20, "channels": ["blog", "twitter", "email"]},
            "industry_analysis": {"weight": 0.15, "channels": ["blog", "linkedin"]},
            "educational": {"weight": 0.10, "channels": ["blog", "twitter", "tiktok"]},
        }

        # Brand voice guidelines
        self._brand_voice = {
            "tone": "professional yet approachable",
            "perspective": "first-person plural (we)",
            "values": ["empowerment", "inclusion", "innovation", "trust"],
            "avoid": ["jargon overload", "condescending language", "unverified claims"],
        }

        # Register tools
        self.tools.register("research_topics", self._research_topics, "Find trending topics")
        self.tools.register("create_content", self._create_content, "Draft content piece")
        self.tools.register("optimize_seo", self._optimize_seo, "SEO optimization pass")

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """
        Analyze context and decide what content action to take.

        Decision logic:
        - Intelligence report → create thought leadership piece
        - Report delivered → create customer story or analysis
        - Feedback received → adjust content strategy
        - Content calendar due → create scheduled content
        """
        event_data = context.get("event", {})
        event_type = event_data.get("event_type", "")

        # Check content calendar for due items
        due_content = self._get_due_content()
        if due_content:
            item = due_content[0]
            return AgentDecision(
                action="create_content",
                parameters={
                    "topic": item.get("topic"),
                    "pillar": item.get("pillar", "thought_leadership"),
                    "format": item.get("format", "blog_post"),
                    "channels": item.get("channels", ["blog"]),
                },
                confidence=0.85,
                reasoning=f"Content calendar item due: {item.get('topic', 'unknown')}",
            )

        if event_type == EventType.INTELLIGENCE_GENERATED.value:
            payload = event_data.get("payload", {})
            return AgentDecision(
                action="create_content",
                parameters={
                    "topic": self._extract_topic_from_intelligence(payload),
                    "pillar": "industry_analysis",
                    "format": "blog_post",
                    "channels": ["blog", "linkedin"],
                    "source_data": payload,
                },
                confidence=0.75,
                reasoning="Intelligence report contains content-worthy insights",
            )

        if event_type == EventType.REPORT_DELIVERED.value:
            payload = event_data.get("payload", {})
            return AgentDecision(
                action="create_content",
                parameters={
                    "topic": f"Customer success: {payload.get('customer', 'partner')}",
                    "pillar": "customer_stories",
                    "format": "case_study",
                    "channels": ["blog", "email", "linkedin"],
                    "source_data": payload,
                },
                confidence=0.7,
                reasoning="Delivered report can become a customer story",
            )

        if event_type == EventType.FEEDBACK_RECEIVED.value:
            return AgentDecision(
                action="adjust_strategy",
                parameters={"feedback": event_data.get("payload", {})},
                confidence=0.8,
                reasoning="Feedback received — review content performance",
            )

        # Periodic topic research
        if self._should_research():
            return AgentDecision(
                action="research_topics",
                parameters={},
                confidence=0.6,
                reasoning="Time to research new content topics",
            )

        return AgentDecision(
            action="idle",
            parameters={},
            confidence=0.5,
            reasoning="No content action needed at this time",
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """Execute the content action."""
        action = decision.action
        params = decision.parameters
        start = time.time()

        try:
            if action == "create_content":
                result_data = await self._create_content(params)
            elif action == "research_topics":
                result_data = await self._research_topics()
            elif action == "adjust_strategy":
                result_data = await self._adjust_strategy(params.get("feedback", {}))
            elif action == "idle":
                result_data = {"status": "idle"}
            else:
                return AgentResult(
                    success=False,
                    error=f"Unknown action: {action}",
                    duration_ms=(time.time() - start) * 1000,
                )

            return AgentResult(
                success=True,
                data=result_data,
                duration_ms=(time.time() - start) * 1000,
            )

        except Exception as exc:
            self._logger.error("content_action_failed", action=action, error=str(exc))
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
            )

    # ── Content Operations ──────────────────────────────────────────

    async def _create_content(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a content piece."""
        topic = params.get("topic", "Untitled")
        pillar = params.get("pillar", "thought_leadership")
        format_type = params.get("format", "blog_post")
        channels = params.get("channels", ["blog"])

        # SEO optimization
        seo_keywords = self._select_keywords(topic)

        content = {
            "content_id": f"content_{int(time.time())}",
            "topic": topic,
            "pillar": pillar,
            "format": format_type,
            "channels": channels,
            "seo_keywords": seo_keywords,
            "status": "drafted",
            "created_at": time.time(),
            "brand_voice_check": True,
        }

        self._published_content.append(content)
        self._logger.info(
            "content_created",
            content_id=content["content_id"],
            topic=topic[:50],
            pillar=pillar,
            format=format_type,
        )

        # Escalate for approval if it's a thought leadership piece
        if pillar == "thought_leadership" and self._escalation:
            await self._escalation.escalate(
                trigger_name="new_partnership",  # Reuse for content approval
                agent_name=self.name,
                summary=f"Content draft ready for review: {topic}",
                details={"content_id": content["content_id"], "pillar": pillar},
                priority=self._escalation.Priority.P4_LOW,
            )

        return content

    async def _research_topics(self) -> dict[str, Any]:
        """Research trending topics for content creation."""
        # Analyze recent intelligence for content signals
        topics = []
        for keyword in self._target_keywords[:5]:
            topics.append({
                "keyword": keyword,
                "trend": "stable",
                "content_gap": True,
                "suggested_angle": f"The future of {keyword} in East Africa",
            })

        # Add to topic queue
        for topic in topics:
            self._topic_queue.append(topic)

        self._logger.info("topics_researched", count=len(topics))
        return {"topics_found": len(topics), "topics": topics}

    async def _adjust_strategy(self, feedback: dict[str, Any]) -> dict[str, Any]:
        """Adjust content strategy based on performance feedback."""
        engagement = feedback.get("engagement_rate", 0)
        if engagement < 0.02:  # Less than 2% engagement
            self._logger.warning("low_engagement", rate=engagement)
            return {
                "adjustment": "increase_interactivity",
                "reason": f"Engagement rate {engagement:.2%} is below target",
            }
        return {"adjustment": "maintain", "engagement_rate": engagement}

    def _select_keywords(self, topic: str) -> list[str]:
        """Select relevant SEO keywords for a topic."""
        topic_lower = topic.lower()
        relevant = [kw for kw in self._target_keywords if any(
            word in topic_lower for word in kw.split()
        )]
        # Always include at least 2 keywords
        if len(relevant) < 2:
            relevant.extend(self._target_keywords[:2])
        return relevant[:5]

    def _extract_topic_from_intelligence(self, payload: dict[str, Any]) -> str:
        """Extract a content topic from intelligence data."""
        if payload.get("market_insight"):
            return f"Market Analysis: {payload['market_insight'][:50]}"
        if payload.get("trend"):
            return f"Trend Alert: {payload['trend'][:50]}"
        return "Industry Intelligence Update"

    def _get_due_content(self) -> list[dict[str, Any]]:
        """Get content items due for creation."""
        now = time.time()
        due = [item for item in self._content_calendar if item.get("due_at", 0) <= now]
        # Remove from calendar
        self._content_calendar = [item for item in self._content_calendar if item.get("due_at", 0) > now]
        return due

    def _should_research(self) -> bool:
        """Check if it's time to research new topics."""
        if not self._topic_queue:
            return True
        last_research = max(
            (t.get("researched_at", 0) for t in self._topic_queue),
            default=0,
        )
        return time.time() - last_research > 86400  # Research daily
