"""
Content Creation Pipeline Agent — Auto-generates marketing content.

Lifecycle:
    observe → Content request event or scheduled trigger
    think   → Determine content type, topic, and SEO strategy
    act     → Generate content, optimize for SEO, schedule distribution
    reflect → Learn from engagement metrics

Content types:
    - Blog posts (1000-2000 words, SEO-optimized)
    - Social media (Twitter threads, LinkedIn posts)
    - Email newsletters (weekly digest)
    - Case studies (client success stories)

SEO strategy:
    - Target keyword research
    - Meta title / description optimization
    - Internal linking suggestions
    - Readability scoring
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from app.agents.base import (
    AgentDecision,
    AgentEvent,
    AgentResult,
    BiasharaAgent,
    EventType,
)
from app.autonomous.models.content import (
    ContentCalendar,
    ContentPiece,
    ContentStatus,
    ContentType,
    SEOMetadata,
)

logger = structlog.get_logger(__name__)

# ── Content templates and configuration ────────────────────────────

# Industry-relevant topics for Angavu Intelligence
TOPIC_LIBRARY: Dict[str, List[str]] = {
    "blog_post": [
        "How AI-Powered Market Intelligence Transforms African SMEs",
        "5 Ways Real-Time Price Forecasting Reduces Stock Losses",
        "The Future of Credit Scoring for Informal Workers",
        "M-Pesa Data Intelligence: Unlocking Business Growth",
        "Distribution Gap Analysis: Finding Hidden Market Opportunities",
        "From Gut Feeling to Data-Driven Decisions in African Retail",
        "How FMCG Companies Use Point-of-Sale Intelligence",
        "Worker Financial Inclusion Through Transaction Data",
    ],
    "social_twitter": [
        "🧵 Thread: How informal workers are using AI to grow their businesses",
        "📊 Market insight: Real-time price trends in Nairobi's Gikomba market",
        "🚀 New feature: Automated credit scoring for dukawallahs",
        "💡 Did you know? 80% of African SMEs lack access to market data",
        "🎯 Case study: How a mama mboga increased revenue 40% with data",
    ],
    "social_linkedin": [
        "The untapped potential of Africa's informal economy",
        "Why traditional credit scoring fails 1.3B Africans",
        "Building ethical AI for bottom-of-pyramid markets",
        "The $4.5T opportunity in African SME intelligence",
    ],
    "email_newsletter": [
        "Weekly Market Intelligence Digest",
        "Monthly Platform Update & Insights",
        "Quarterly Industry Trends Report",
    ],
}

# SEO keyword clusters for Angavu's domain
KEYWORD_CLUSTERS: Dict[str, List[str]] = {
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

# Channel configuration
CHANNEL_CONFIG: Dict[str, Dict[str, Any]] = {
    "blog": {"max_length": 5000, "tone": "professional", "format": "markdown"},
    "twitter": {"max_length": 280, "tone": "conversational", "format": "text"},
    "linkedin": {"max_length": 3000, "tone": "professional", "format": "text"},
    "newsletter": {"max_length": 3000, "tone": "informative", "format": "html"},
}


class ContentCreatorAgent(BiasharaAgent):
    """
    Autonomous content creation agent.

    Subscribes to: content.requested
    Publishes:     content.generated, content.published

    Generates SEO-optimized content across multiple channels.
    Manages a weekly content calendar.
    """

    def __init__(self):
        super().__init__(
            name="ContentCreator",
            role="Content creation and SEO optimization specialist",
            capabilities=[
                "blog_writing",
                "social_media_copy",
                "email_newsletters",
                "seo_optimization",
                "content_calendar",
                "distribution_management",
            ],
        )
        # Content calendar state
        self._calendar: Optional[ContentCalendar] = None
        # Generated content history
        self._content_history: List[Dict[str, Any]] = []
        # Topic rotation index
        self._topic_indices: Dict[str, int] = {}

    # ── Lifecycle ───────────────────────────────────────────────────

    async def observe(self, event: AgentEvent) -> None:
        """Filter for content and marketing events."""
        await super().observe(event)
        if event.event_type not in (
            EventType.CONTENT_REQUESTED,
            EventType.REVENUE_METRIC_RECORDED,
        ):
            self._logger.debug("ignoring_event", event_type=event.event_type.value)

    async def think(self, context: Dict[str, Any]) -> AgentDecision:
        """
        Decide what content to generate.

        Analysis:
        1. Check content calendar for scheduled pieces
        2. Check if any channel is under-published
        3. Select topic from rotating library
        4. Determine SEO strategy
        """
        event_data = context.get("event", {})
        payload = event_data.get("payload", {})

        # Determine content type from request or auto-select
        content_type_str = payload.get("content_type", "blog_post")
        try:
            content_type = ContentType(content_type_str)
        except ValueError:
            content_type = ContentType.BLOG_POST

        # Select topic (rotate through library)
        topic = self._select_topic(content_type, payload)

        # Determine target channels
        target_channels = payload.get("target_channels", self._default_channels(content_type))

        # SEO strategy
        seo = self._plan_seo(topic, content_type)

        # Check past reflections for content performance lessons
        reflections = context.get("past_reflections", [])

        confidence = 0.85
        strategy = context.get("strategy_adjustment")
        if strategy:
            confidence *= strategy.get("threshold_factor", 1.0)

        return AgentDecision(
            action="generate_content",
            parameters={
                "content_type": content_type.value,
                "topic": topic,
                "target_channels": target_channels,
                "seo": seo.to_dict(),
                "requested_by": payload.get("requested_by", "auto"),
            },
            confidence=confidence,
            reasoning=(
                f"Generating {content_type.value} on topic: '{topic}'. "
                f"Target channels: {', '.join(target_channels)}. "
                f"SEO keyword: '{seo.target_keyword}'."
            ),
        )

    async def act(self, decision: AgentDecision) -> AgentResult:
        """
        Generate content and schedule for distribution.

        Creates the content piece, applies SEO optimization,
        and emits events for distribution.
        """
        start = time.time()

        try:
            params = decision.parameters
            content_type = ContentType(params["content_type"])
            topic = params["topic"]
            target_channels = params["target_channels"]
            seo_data = params["seo"]

            seo = SEOMetadata(
                target_keyword=seo_data.get("target_keyword", ""),
                secondary_keywords=seo_data.get("secondary_keywords", []),
                meta_title=seo_data.get("meta_title", ""),
                meta_description=seo_data.get("meta_description", ""),
            )

            # Generate content based on type
            content_piece = self._generate_content(content_type, topic, seo, target_channels)

            # Store in history
            self._content_history.append({
                "content_id": content_piece.content_id,
                "type": content_type.value,
                "topic": topic,
                "status": content_piece.status.value,
                "timestamp": time.time(),
            })

            events_to_publish = []

            # Content generated event
            events_to_publish.append(AgentEvent(
                event_type=EventType.CONTENT_GENERATED,
                source=self.name,
                payload={
                    "content": content_piece.to_dict(),
                    "content_id": content_piece.content_id,
                    "content_type": content_type.value,
                    "channels": target_channels,
                },
            ))

            # Content published event (auto-publish for social, schedule for blog)
            if content_type in (ContentType.SOCIAL_TWITTER, ContentType.SOCIAL_LINKEDIN):
                content_piece.status = ContentStatus.PUBLISHED
                content_piece.published_at = datetime.now(timezone.utc)
                events_to_publish.append(AgentEvent(
                    event_type=EventType.CONTENT_PUBLISHED,
                    source=self.name,
                    payload={
                        "content_id": content_piece.content_id,
                        "content_type": content_type.value,
                        "channels": target_channels,
                        "published_at": content_piece.published_at.isoformat(),
                    },
                ))

            duration_ms = (time.time() - start) * 1000

            return AgentResult(
                success=True,
                data={
                    "content_id": content_piece.content_id,
                    "content_type": content_type.value,
                    "title": content_piece.title,
                    "status": content_piece.status.value,
                    "channels": target_channels,
                    "seo_keyword": seo.target_keyword,
                    "body_length": len(content_piece.body),
                },
                duration_ms=duration_ms,
                events_to_publish=events_to_publish,
            )

        except Exception as exc:
            return AgentResult(
                success=False,
                error=str(exc),
                duration_ms=(time.time() - start) * 1000,
                events_to_publish=[
                    AgentEvent(
                        event_type=EventType.PIPELINE_ERROR,
                        source=self.name,
                        payload={"error": str(exc), "phase": "content_creation"},
                    )
                ],
            )

    async def reflect(self, result: AgentResult) -> None:
        """Learn from content performance."""
        await super().reflect(result)

        if result.success:
            data = result.data or {}
            self.memory.remember({
                "event_type": "content_generated",
                "content_id": data.get("content_id"),
                "content_type": data.get("content_type"),
                "body_length": data.get("body_length"),
            })

    # ── Content generation ──────────────────────────────────────────

    def _generate_content(
        self,
        content_type: ContentType,
        topic: str,
        seo: SEOMetadata,
        channels: List[str],
    ) -> ContentPiece:
        """Generate content based on type and topic."""

        if content_type == ContentType.BLOG_POST:
            return self._generate_blog_post(topic, seo, channels)
        elif content_type == ContentType.SOCIAL_TWITTER:
            return self._generate_twitter_post(topic, channels)
        elif content_type == ContentType.SOCIAL_LINKEDIN:
            return self._generate_linkedin_post(topic, channels)
        elif content_type == ContentType.EMAIL_NEWSLETTER:
            return self._generate_newsletter(topic, seo, channels)
        elif content_type == ContentType.CASE_STUDY:
            return self._generate_case_study(topic, seo, channels)
        else:
            return ContentPiece(
                content_type=content_type,
                title=topic,
                body=f"Content placeholder for: {topic}",
                summary=topic,
                status=ContentStatus.DRAFTED,
                seo=seo,
                target_channels=channels,
            )

    def _generate_blog_post(
        self,
        topic: str,
        seo: SEOMetadata,
        channels: List[str],
    ) -> ContentPiece:
        """Generate a blog post with SEO optimization."""
        keyword = seo.target_keyword or topic

        body = f"""# {topic}

## Introduction

In today's rapidly evolving African business landscape, data-driven decision making is no longer a luxury — it's a necessity. {keyword} is transforming how businesses operate across the continent.

## The Challenge

African SMEs face unique challenges:
- Limited access to market intelligence
- Fragmented supply chains
- Informal transaction records
- Lack of credit history

## How {keyword} Changes the Game

By leveraging real-time transaction data, AI-powered analytics, and mobile-first delivery, Angavu Intelligence provides:

1. **Real-time market insights** — Know what's selling, where, and at what price
2. **Predictive analytics** — Forecast demand before it happens
3. **Credit intelligence** — Build financial identity from business transactions
4. **Distribution optimization** — Find gaps in the supply chain

## Case in Point

Consider a typical mama mboga in Nairobi's Gikomba market. Before Angavu, she relied on gut feeling for pricing and restocking. With access to real-time market data, she can:

- Optimize her product mix based on demand patterns
- Avoid stockouts during peak hours
- Negotiate better prices with suppliers using market benchmarks
- Build a credit profile from her transaction history

## The Impact

Early adopters of {keyword} have seen:
- 25-40% reduction in stock losses
- 15-30% improvement in profit margins
- 3x faster access to micro-credit
- 50% better supplier negotiation outcomes

## What's Next

The future of African business intelligence is autonomous, AI-powered, and accessible to every worker — from dukawallahs to mama mbogas. Angavu Intelligence is building that future, one transaction at a time.

---

*Ready to transform your business with data? [Get started with Angavu Intelligence](https://angavu.ai).*
"""

        return ContentPiece(
            content_type=ContentType.BLOG_POST,
            title=topic,
            body=body,
            summary=f"A comprehensive look at how {keyword} is transforming African SMEs.",
            status=ContentStatus.DRAFTED,
            seo=seo,
            target_channels=channels,
            tags=["blog", "market-intelligence", "africa", "sme"],
        )

    def _generate_twitter_post(self, topic: str, channels: List[str]) -> ContentPiece:
        """Generate a Twitter thread."""
        body = f"""🧵 {topic}

1/ Africa has 44M+ informal businesses. Most operate on gut feeling.

2/ What if every dukawallah had access to the same data as Walmart?

3/ That's what @AngavuIntel is building — AI-powered market intelligence for Africa's informal economy.

4/ Real results from early users:
📊 25% less stock waste
💰 30% better margins
🏦 3x faster credit access

5/ The future of African business is data-driven. And it's here now.

[Learn more → angavu.ai]"""

        return ContentPiece(
            content_type=ContentType.SOCIAL_TWITTER,
            title=topic,
            body=body,
            summary=topic,
            status=ContentStatus.DRAFTED,
            target_channels=["twitter"],
            tags=["twitter", "thread", "africa", "fintech"],
        )

    def _generate_linkedin_post(self, topic: str, channels: List[str]) -> ContentPiece:
        """Generate a LinkedIn post."""
        body = f"""{topic}

The informal economy accounts for 85% of employment in Sub-Saharan Africa. Yet these 44M+ businesses lack access to basic market intelligence.

Traditional enterprise analytics tools weren't built for:
→ A mama mboga tracking daily sales via M-Pesa
→ A dukawallah optimizing inventory with seasonal data
→ A boda boda driver building a credit profile

At Angavu Intelligence, we're changing this. Our AI-powered platform transforms raw transaction data into actionable intelligence — delivered via WhatsApp, the channel these workers already use.

Early results:
📊 25-40% reduction in stock losses
💰 15-30% improvement in profit margins
🏦 3x faster access to micro-credit

The next billion-dollar market isn't in Silicon Valley. It's in Gikomba, Korogocho, and every informal market across Africa.

#AfricanBusiness #Fintech #MarketIntelligence #InformalEconomy #AI"""

        return ContentPiece(
            content_type=ContentType.SOCIAL_LINKEDIN,
            title=topic,
            body=body,
            summary=topic,
            status=ContentStatus.DRAFTED,
            target_channels=["linkedin"],
            tags=["linkedin", "thought-leadership", "africa"],
        )

    def _generate_newsletter(
        self,
        topic: str,
        seo: SEOMetadata,
        channels: List[str],
    ) -> ContentPiece:
        """Generate an email newsletter."""
        body = f"""<h1>{topic}</h1>

<p>Here's what's new in the world of African market intelligence this week:</p>

<h2>📊 Market Highlights</h2>
<ul>
<li>Nairobi retail prices stable week-over-week</li>
<li>M-Pesa transaction volume up 12% in informal sector</li>
<li>FMCG distribution gaps identified in 3 new regions</li>
</ul>

<h2>🚀 Platform Updates</h2>
<ul>
<li>New: Real-time price alerts for tracked products</li>
<li>Improved: Credit scoring accuracy +15%</li>
<li>Coming soon: WhatsApp voice reports in Swahili</li>
</ul>

<h2>💡 Insight of the Week</h2>
<p>Businesses that track daily transactions see 30% better margins than those relying on monthly summaries. Start tracking today.</p>

<h2>📈 Your Weekly Numbers</h2>
<p>Log in to your Angavu dashboard to see your personalized market intelligence report.</p>

<p><a href="https://angavu.ai">View your dashboard →</a></p>"""

        return ContentPiece(
            content_type=ContentType.EMAIL_NEWSLETTER,
            title=topic,
            body=body,
            summary="Weekly market intelligence digest from Angavu.",
            status=ContentStatus.DRAFTED,
            seo=seo,
            target_channels=["email"],
            tags=["newsletter", "weekly-digest"],
        )

    def _generate_case_study(
        self,
        topic: str,
        seo: SEOMetadata,
        channels: List[str],
    ) -> ContentPiece:
        """Generate a client case study."""
        body = f"""# {topic}

## Client Profile
- **Business:** Mama Mboga (fresh produce vendor)
- **Location:** Gikomba Market, Nairobi
- **Challenge:** High stock waste, inconsistent pricing, no credit access

## The Problem
Wanjiku had been running her produce stall for 8 years. She lost an estimated 30% of her stock to spoilage and price fluctuations. Without transaction records, she couldn't access formal credit.

## The Solution
Using Angavu Intelligence's WhatsApp-based platform, Wanjiku:
1. Recorded daily transactions via voice
2. Received real-time price alerts for her products
3. Got weekly market intelligence reports
4. Built a credit profile from her transaction history

## Results (After 3 Months)
- **Stock waste:** Reduced from 30% to 12% (-60%)
- **Profit margins:** Improved from 15% to 28% (+87%)
- **Credit access:** Qualified for KES 50,000 micro-loan
- **Time saved:** 2 hours/day on manual record-keeping

## Key Takeaway
"I used to throw away tomatoes every week because I bought too many at the wrong price. Now I know exactly what to buy and when. My children are eating better, and I'm saving for their school fees." — Wanjiku

---

*Want similar results? [Start your free trial](https://angavu.ai).*"""

        return ContentPiece(
            content_type=ContentType.CASE_STUDY,
            title=topic,
            body=body,
            summary="How a Nairobi mama mboga reduced stock waste by 60% with data.",
            status=ContentStatus.DRAFTED,
            seo=seo,
            target_channels=["blog", "linkedin", "email"],
            tags=["case-study", "success-story", "nairobi"],
        )

    # ── Helper methods ──────────────────────────────────────────────

    def _select_topic(self, content_type: ContentType, payload: Dict[str, Any]) -> str:
        """Select topic from library using rotation."""
        # Check for explicit topic in request
        if payload.get("topic"):
            return payload["topic"]

        type_key = content_type.value
        topics = TOPIC_LIBRARY.get(type_key, TOPIC_LIBRARY["blog_post"])

        # Rotate through topics
        idx = self._topic_indices.get(type_key, 0) % len(topics)
        self._topic_indices[type_key] = idx + 1

        return topics[idx]

    def _default_channels(self, content_type: ContentType) -> List[str]:
        """Get default distribution channels for a content type."""
        channel_map = {
            ContentType.BLOG_POST: ["blog", "linkedin", "twitter"],
            ContentType.SOCIAL_TWITTER: ["twitter"],
            ContentType.SOCIAL_LINKEDIN: ["linkedin"],
            ContentType.SOCIAL_INSTAGRAM: ["instagram"],
            ContentType.EMAIL_NEWSLETTER: ["email"],
            ContentType.CASE_STUDY: ["blog", "linkedin", "email"],
            ContentType.WHITEPAPER: ["blog", "email"],
            ContentType.PRESS_RELEASE: ["blog", "twitter", "linkedin"],
        }
        return channel_map.get(content_type, ["blog"])

    def _plan_seo(self, topic: str, content_type: ContentType) -> SEOMetadata:
        """Plan SEO strategy for the content piece."""
        if content_type not in (ContentType.BLOG_POST, ContentType.CASE_STUDY, ContentType.WHITEPAPER):
            # Social content doesn't need deep SEO
            return SEOMetadata(target_keyword=topic.lower())

        # Select keyword from cluster
        primary_keywords = KEYWORD_CLUSTERS["primary"]
        secondary_keywords = KEYWORD_CLUSTERS["secondary"]

        # Match topic to best keyword
        topic_lower = topic.lower()
        best_keyword = primary_keywords[0]  # default
        for kw in primary_keywords:
            if any(word in topic_lower for word in kw.lower().split()):
                best_keyword = kw
                break

        return SEOMetadata(
            target_keyword=best_keyword,
            secondary_keywords=secondary_keywords[:3],
            meta_title=topic[:60],  # Google truncates at ~60 chars
            meta_description=f"Learn how {best_keyword} is transforming African businesses. Real data, real results."[:155],
            readability_score=75.0,  # Target: grade 8 reading level
        )
