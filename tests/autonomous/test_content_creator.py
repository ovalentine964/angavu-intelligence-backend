"""
Tests for the Content Creation Agent.

Tests cover:
- Content generation for each type (blog, social, newsletter, case study)
- SEO metadata generation
- Topic rotation
- Channel defaults
"""

from unittest.mock import AsyncMock

import pytest

from app.agents.base import AgentEvent, EventType
from app.autonomous.agents.content_creator import ContentCreatorAgent
from app.autonomous.models.content import (
    ContentCalendar,
    ContentPiece,
    ContentStatus,
    ContentType,
    SEOMetadata,
)


@pytest.fixture
def agent():
    """Create a ContentCreatorAgent for testing."""
    a = ContentCreatorAgent()
    a._event_bus = AsyncMock()
    return a


# ── Content Model Tests ────────────────────────────────────────────


class TestContentModel:
    """Test Content data models."""

    def test_content_piece_creation(self):
        """Test creating a content piece."""
        piece = ContentPiece(
            content_type=ContentType.BLOG_POST,
            title="Test Blog",
            body="Test body content",
            status=ContentStatus.DRAFTED,
        )
        assert piece.title == "Test Blog"
        assert piece.status == ContentStatus.DRAFTED

    def test_content_piece_roundtrip(self):
        """Test ContentPiece serialization."""
        piece = ContentPiece(
            content_type=ContentType.SOCIAL_TWITTER,
            title="Test Tweet",
            body="Short tweet content",
            tags=["test", "social"],
        )
        data = piece.to_dict()
        restored = ContentPiece.from_dict(data)

        assert restored.title == "Test Tweet"
        assert restored.content_type == ContentType.SOCIAL_TWITTER
        assert "test" in restored.tags

    def test_seo_metadata(self):
        """Test SEO metadata."""
        seo = SEOMetadata(
            target_keyword="African market intelligence",
            meta_title="How AI Transforms African SMEs",
            meta_description="Learn how market intelligence helps",
            readability_score=80.0,
        )
        data = seo.to_dict()
        assert data["target_keyword"] == "African market intelligence"
        assert data["readability_score"] == 80.0

    def test_content_calendar(self):
        """Test content calendar."""
        calendar = ContentCalendar(
            themes=["AI in Africa", "SME Growth"],
            target_channels=["blog", "twitter"],
        )
        data = calendar.to_dict()
        assert len(data["themes"]) == 2
        assert data["planned_count"] == 0


# ── Content Creator Agent Tests ────────────────────────────────────


class TestContentCreatorAgent:
    """Test the ContentCreatorAgent."""

    def test_generate_blog_post(self, agent):
        """Test blog post generation."""
        seo = SEOMetadata(target_keyword="African market intelligence")
        piece = agent._generate_content(
            ContentType.BLOG_POST,
            "How AI Transforms African SMEs",
            seo,
            ["blog", "linkedin"],
        )

        assert piece.content_type == ContentType.BLOG_POST
        assert len(piece.body) > 500  # Should be substantial
        assert "African" in piece.body
        assert piece.status == ContentStatus.DRAFTED

    def test_generate_twitter_post(self, agent):
        """Test Twitter post generation."""
        piece = agent._generate_content(
            ContentType.SOCIAL_TWITTER,
            "AI in Africa",
            SEOMetadata(),
            ["twitter"],
        )

        assert piece.content_type == ContentType.SOCIAL_TWITTER
        assert len(piece.body) <= 1000  # Twitter threads are longer but still bounded
        assert "🧵" in piece.body  # Thread emoji

    def test_generate_linkedin_post(self, agent):
        """Test LinkedIn post generation."""
        piece = agent._generate_content(
            ContentType.SOCIAL_LINKEDIN,
            "African Business Intelligence",
            SEOMetadata(),
            ["linkedin"],
        )

        assert piece.content_type == ContentType.SOCIAL_LINKEDIN
        assert "#" in piece.body  # Hashtags
        assert piece.status == ContentStatus.DRAFTED

    def test_generate_newsletter(self, agent):
        """Test newsletter generation."""
        seo = SEOMetadata(target_keyword="market intelligence")
        piece = agent._generate_content(
            ContentType.EMAIL_NEWSLETTER,
            "Weekly Digest",
            seo,
            ["email"],
        )

        assert piece.content_type == ContentType.EMAIL_NEWSLETTER
        assert "<h1>" in piece.body  # HTML format
        assert piece.status == ContentStatus.DRAFTED

    def test_generate_case_study(self, agent):
        """Test case study generation."""
        seo = SEOMetadata(target_keyword="market intelligence")
        piece = agent._generate_content(
            ContentType.CASE_STUDY,
            "Mama Mboga Success Story",
            seo,
            ["blog", "linkedin"],
        )

        assert piece.content_type == ContentType.CASE_STUDY
        assert "Results" in piece.body or "results" in piece.body
        assert "KES" in piece.body  # Should mention currency

    def test_topic_rotation(self, agent):
        """Test that topics rotate through the library."""
        topic1 = agent._select_topic(ContentType.BLOG_POST, {})
        topic2 = agent._select_topic(ContentType.BLOG_POST, {})
        topic3 = agent._select_topic(ContentType.BLOG_POST, {})

        # Should get different topics
        assert topic1 != topic2 or topic2 != topic3

    def test_explicit_topic_override(self, agent):
        """Test that explicit topic in payload overrides rotation."""
        topic = agent._select_topic(ContentType.BLOG_POST, {"topic": "Custom Topic"})
        assert topic == "Custom Topic"

    def test_default_channels(self, agent):
        """Test default channel assignment."""
        assert "twitter" in agent._default_channels(ContentType.SOCIAL_TWITTER)
        assert "linkedin" in agent._default_channels(ContentType.SOCIAL_LINKEDIN)
        assert "email" in agent._default_channels(ContentType.EMAIL_NEWSLETTER)
        assert "blog" in agent._default_channels(ContentType.BLOG_POST)

    def test_seo_planning(self, agent):
        """Test SEO strategy planning."""
        seo = agent._plan_seo("African Market Intelligence", ContentType.BLOG_POST)

        assert seo.target_keyword  # Should have a keyword
        assert seo.meta_title  # Should have meta title

    def test_seo_skipped_for_social(self, agent):
        """Test that deep SEO is skipped for social content."""
        seo = agent._plan_seo("Quick tweet", ContentType.SOCIAL_TWITTER)
        # Social content gets minimal SEO
        assert seo.target_keyword == "quick tweet"

    @pytest.mark.asyncio
    async def test_think_returns_generate_content(self, agent):
        """Test that think returns a generate_content decision."""
        event = AgentEvent(
            event_type=EventType.CONTENT_REQUESTED,
            source="test",
            payload={"content_type": "blog_post"},
        )

        await agent.observe(event)
        context = {
            "event": event.to_dict(),
            "memory": agent.memory.snapshot(),
            "tools": [],
            "past_reflections": [],
            "strategy_adjustment": None,
        }
        decision = await agent.think(context)

        assert decision.action == "generate_content"
        assert decision.parameters["content_type"] == "blog_post"

    @pytest.mark.asyncio
    async def test_act_generates_content(self, agent):
        """Test that act generates content and emits events."""
        from unittest.mock import MagicMock

        decision = MagicMock()
        decision.action = "generate_content"
        decision.parameters = {
            "content_type": "blog_post",
            "topic": "Test Topic",
            "target_channels": ["blog"],
            "seo": SEOMetadata(target_keyword="test").to_dict(),
            "requested_by": "test",
        }

        result = await agent.act(decision)

        assert result.success
        assert result.data["content_type"] == "blog_post"
        assert result.data["body_length"] > 0
        assert len(result.events_to_publish) >= 1
        assert result.events_to_publish[0].event_type == EventType.CONTENT_GENERATED

    @pytest.mark.asyncio
    async def test_social_auto_publishes(self, agent):
        """Test that social content auto-publishes."""
        from unittest.mock import MagicMock

        decision = MagicMock()
        decision.action = "generate_content"
        decision.parameters = {
            "content_type": "social_twitter",
            "topic": "Test Tweet",
            "target_channels": ["twitter"],
            "seo": SEOMetadata().to_dict(),
            "requested_by": "test",
        }

        result = await agent.act(decision)

        # Should have both generated and published events
        event_types = [e.event_type for e in result.events_to_publish]
        assert EventType.CONTENT_GENERATED in event_types
        assert EventType.CONTENT_PUBLISHED in event_types
