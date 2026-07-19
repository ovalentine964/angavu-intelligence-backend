"""
Content models for the creation pipeline.

Content types:
    - Blog posts (long-form, SEO-optimized)
    - Social media posts (Twitter, LinkedIn, Instagram)
    - Email newsletters (weekly digest)
    - Case studies (client success stories)

Each piece flows through:
    Planned → Drafted → Reviewed → Published → Archived
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ContentType(str, Enum):
    """Types of content we produce."""
    BLOG_POST = "blog_post"
    SOCIAL_TWITTER = "social_twitter"
    SOCIAL_LINKEDIN = "social_linkedin"
    SOCIAL_INSTAGRAM = "social_instagram"
    EMAIL_NEWSLETTER = "email_newsletter"
    CASE_STUDY = "case_study"
    WHITEPAPER = "whitepaper"
    PRESS_RELEASE = "press_release"


class ContentStatus(str, Enum):
    """Content lifecycle states."""
    PLANNED = "planned"
    DRAFTED = "drafted"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"


@dataclass
class SEOMetadata:
    """SEO optimization metadata for a content piece."""
    target_keyword: str = ""
    secondary_keywords: list[str] = field(default_factory=list)
    meta_title: str = ""
    meta_description: str = ""
    suggested_headings: list[str] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    readability_score: float = 0.0  # 0-100

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_keyword": self.target_keyword,
            "secondary_keywords": self.secondary_keywords,
            "meta_title": self.meta_title,
            "meta_description": self.meta_description,
            "suggested_headings": self.suggested_headings,
            "readability_score": self.readability_score,
        }


@dataclass
class ContentPiece:
    """
    A single piece of content.

    Attributes:
        content_id: Unique identifier
        content_type: Type of content
        title: Content title
        body: Full content text
        summary: Short summary / excerpt
        author: Who wrote it (human or "ai_agent")
        status: Current lifecycle state
        seo: SEO metadata
        target_channels: Where to distribute
        scheduled_at: When to publish
        published_at: When it was actually published
        published_url: URL of published content
        engagement_metrics: Views, likes, shares, etc.
        tags: Content tags
        metadata: Arbitrary extra data
    """
    content_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content_type: ContentType = ContentType.BLOG_POST
    title: str = ""
    body: str = ""
    summary: str = ""
    author: str = "ai_agent"
    status: ContentStatus = ContentStatus.PLANNED
    seo: SEOMetadata = field(default_factory=SEOMetadata)
    target_channels: list[str] = field(default_factory=list)
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    published_url: str = ""
    engagement_metrics: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_id": self.content_id,
            "content_type": self.content_type.value,
            "title": self.title,
            "body": self.body[:500] + "..." if len(self.body) > 500 else self.body,
            "summary": self.summary,
            "author": self.author,
            "status": self.status.value,
            "seo": self.seo.to_dict(),
            "target_channels": self.target_channels,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContentPiece:
        seo_data = data.get("seo", {})
        seo = SEOMetadata(
            target_keyword=seo_data.get("target_keyword", ""),
            secondary_keywords=seo_data.get("secondary_keywords", []),
            meta_title=seo_data.get("meta_title", ""),
            meta_description=seo_data.get("meta_description", ""),
            readability_score=seo_data.get("readability_score", 0.0),
        )
        scheduled_at = None
        if data.get("scheduled_at"):
            scheduled_at = datetime.fromisoformat(data["scheduled_at"])
        return cls(
            content_id=data.get("content_id", uuid.uuid4().hex[:12]),
            content_type=ContentType(data.get("content_type", "blog_post")),
            title=data.get("title", ""),
            body=data.get("body", ""),
            summary=data.get("summary", ""),
            author=data.get("author", "ai_agent"),
            status=ContentStatus(data.get("status", "planned")),
            seo=seo,
            target_channels=data.get("target_channels", []),
            scheduled_at=scheduled_at,
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ContentCalendar:
    """
    Weekly content calendar.

    Plans content across channels for a given week.
    """
    week_start: datetime = field(default_factory=lambda: datetime.now(UTC))
    planned_pieces: list[ContentPiece] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    target_channels: list[str] = field(default_factory=lambda: ["blog", "twitter", "linkedin", "newsletter"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "week_start": self.week_start.isoformat(),
            "planned_count": len(self.planned_pieces),
            "themes": self.themes,
            "target_channels": self.target_channels,
            "pieces": [p.to_dict() for p in self.planned_pieces],
        }
