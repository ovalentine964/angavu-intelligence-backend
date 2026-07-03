"""
Tests for the Lead Qualification Agent.

Tests cover:
- Scoring accuracy across all 5 dimensions
- Qualification thresholds (escalate, qualify, reject)
- Edge cases (missing data, zero budget, unknown industry)
- Reflect→behavior feedback loop
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.agents.base import AgentEvent, EventType
from app.autonomous.models.lead import Lead, LeadScore, LeadStatus, LeadSource
from app.autonomous.agents.lead_qualifier import (
    LeadQualifierAgent,
    ESCALATE_THRESHOLD,
    QUALIFY_THRESHOLD,
    INDUSTRY_FIT_SCORES,
    COMPANY_SIZE_SCORES,
)


@pytest.fixture
def agent():
    """Create a LeadQualifierAgent for testing."""
    a = LeadQualifierAgent()
    a._event_bus = AsyncMock()
    return a


@pytest.fixture
def high_value_lead():
    """Create a high-value lead that should be escalated."""
    return Lead(
        lead_id="test-lead-001",
        company_name="Acme FMCG Ltd",
        contact_name="John Doe",
        contact_email="john@acme.com",
        industry="fmcg",
        company_size="201-1000",
        estimated_budget=600_000,
        source=LeadSource.REFERRAL,
    )


@pytest.fixture
def mid_value_lead():
    """Create a mid-value lead that should be qualified."""
    return Lead(
        lead_id="test-lead-002",
        company_name="Small Retail Shop",
        contact_name="Jane Smith",
        contact_email="jane@shop.com",
        industry="retail",
        company_size="11-50",
        estimated_budget=30_000,
        source=LeadSource.WEBSITE,
    )


@pytest.fixture
def low_value_lead():
    """Create a low-value lead that should be rejected."""
    return Lead(
        lead_id="test-lead-003",
        company_name="Unknown Startup",
        contact_name="Bob",
        industry="other",
        company_size="1-10",
        estimated_budget=500,
        source=LeadSource.OTHER,
    )


# ── Scoring Tests ──────────────────────────────────────────────────


class TestLeadScoring:
    """Test the scoring algorithm."""

    def test_company_size_scoring(self):
        """Test company size band scoring."""
        assert LeadQualifierAgent._score_company_size("1-10") == 20.0
        assert LeadQualifierAgent._score_company_size("11-50") == 45.0
        assert LeadQualifierAgent._score_company_size("51-200") == 70.0
        assert LeadQualifierAgent._score_company_size("201-1000") == 85.0
        assert LeadQualifierAgent._score_company_size("1000+") == 95.0
        assert LeadQualifierAgent._score_company_size("unknown") == 20.0  # default

    def test_industry_fit_scoring(self):
        """Test industry fit scoring."""
        assert LeadQualifierAgent._score_industry_fit("fmcg") == 95.0
        assert LeadQualifierAgent._score_industry_fit("retail") == 90.0
        assert LeadQualifierAgent._score_industry_fit("FMCG") == 95.0  # case insensitive
        assert LeadQualifierAgent._score_industry_fit("unknown_industry") == 20.0

    def test_budget_scoring(self):
        """Test budget band scoring."""
        assert LeadQualifierAgent._score_budget(600_000) == 95.0
        assert LeadQualifierAgent._score_budget(150_000) == 80.0
        assert LeadQualifierAgent._score_budget(50_000) == 60.0
        assert LeadQualifierAgent._score_budget(10_000) == 40.0
        assert LeadQualifierAgent._score_budget(500) == 5.0
        assert LeadQualifierAgent._score_budget(0) == 5.0

    def test_timing_scoring(self):
        """Test timing/urgency scoring."""
        # Immediate urgency
        assert LeadQualifierAgent._score_timing({"urgency": "immediate"}) == 90.0
        # This quarter
        assert LeadQualifierAgent._score_timing({"urgency": "this_quarter"}) == 70.0
        # Exploring
        assert LeadQualifierAgent._score_timing({"urgency": "exploring"}) == 15.0
        # Decision timeline
        assert LeadQualifierAgent._score_timing({"decision_timeline_days": 7}) >= 85.0
        assert LeadQualifierAgent._score_timing({"decision_timeline_days": 120}) >= 20.0
        # No signals → baseline
        assert LeadQualifierAgent._score_timing({}) == 50.0

    def test_engagement_scoring(self):
        """Test engagement signal scoring."""
        # Baseline for inbound
        assert LeadQualifierAgent._score_engagement({}) == 30.0
        # With meetings
        score = LeadQualifierAgent._score_engagement({"meetings_requested": 2})
        assert score >= 60.0
        # With referral bonus
        score = LeadQualifierAgent._score_engagement({"source": "referral"})
        assert score >= 45.0

    def test_composite_score_calculation(self):
        """Test weighted composite score calculation."""
        score = LeadScore(
            company_size=80.0,
            industry_fit=90.0,
            budget_signal=70.0,
            timing=60.0,
            engagement=50.0,
        )
        composite = score.calculate_composite()
        expected = 80*0.25 + 90*0.25 + 70*0.20 + 60*0.15 + 50*0.15
        assert abs(composite - expected) < 0.01


# ── Qualification Decision Tests ───────────────────────────────────


class TestQualificationDecisions:
    """Test qualification decisions."""

    @pytest.mark.asyncio
    async def test_high_value_lead_escalated(self, agent, high_value_lead):
        """High-value leads should be escalated to Valentine."""
        event = AgentEvent(
            event_type=EventType.LEAD_CREATED,
            source="test",
            payload={"lead": high_value_lead.to_dict()},
        )

        # Run through lifecycle
        await agent.observe(event)
        context = {
            "event": event.to_dict(),
            "memory": agent.memory.snapshot(),
            "tools": [],
            "past_reflections": [],
            "strategy_adjustment": None,
        }
        decision = await agent.think(context)

        assert decision.action == "escalate"
        assert decision.confidence >= ESCALATE_THRESHOLD / 100
        assert "ESCALATE" in decision.reasoning

    @pytest.mark.asyncio
    async def test_mid_value_lead_qualified(self, agent, mid_value_lead):
        """Mid-value leads should be qualified for nurturing."""
        event = AgentEvent(
            event_type=EventType.LEAD_CREATED,
            source="test",
            payload={"lead": mid_value_lead.to_dict()},
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

        assert decision.action == "qualify"
        assert QUALIFY_THRESHOLD / 100 <= decision.confidence < ESCALATE_THRESHOLD / 100

    @pytest.mark.asyncio
    async def test_low_value_lead_rejected(self, agent, low_value_lead):
        """Low-value leads should be rejected."""
        event = AgentEvent(
            event_type=EventType.LEAD_CREATED,
            source="test",
            payload={"lead": low_value_lead.to_dict()},
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

        assert decision.action == "reject"
        assert decision.confidence < QUALIFY_THRESHOLD / 100

    @pytest.mark.asyncio
    async def test_act_escalate_assigns_valentine(self, agent, high_value_lead):
        """Escalated leads should be assigned to Valentine."""
        decision = MagicMock()
        decision.action = "escalate"
        decision.parameters = {
            "lead": high_value_lead.to_dict(),
            "scores": LeadScore(company_size=85, industry_fit=95, budget_signal=95, timing=70, engagement=30).to_dict(),
            "weights": agent._weights,
        }

        result = await agent.act(decision)

        assert result.success
        assert result.data["action"] == "escalate"
        assert result.data["assigned_to"] == "valentine"
        assert len(result.events_to_publish) > 0
        assert result.events_to_publish[0].event_type == EventType.LEAD_ESCALATED

    @pytest.mark.asyncio
    async def test_act_qualify_emits_event(self, agent, mid_value_lead):
        """Qualified leads should emit lead.qualified event."""
        decision = MagicMock()
        decision.action = "qualify"
        decision.parameters = {
            "lead": mid_value_lead.to_dict(),
            "scores": LeadScore(company_size=45, industry_fit=90, budget_signal=60, timing=50, engagement=30).to_dict(),
            "weights": agent._weights,
        }

        result = await agent.act(decision)

        assert result.success
        assert result.events_to_publish[0].event_type == EventType.LEAD_QUALIFIED


# ── Edge Case Tests ────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_lead_model_roundtrip(self):
        """Test Lead serialization and deserialization."""
        lead = Lead(
            company_name="Test Corp",
            industry="fmcg",
            company_size="51-200",
            estimated_budget=100_000,
        )
        lead.score = LeadScore(company_size=70, industry_fit=95, budget_signal=80)
        lead.score.calculate_composite()

        data = lead.to_dict()
        restored = Lead.from_dict(data)

        assert restored.company_name == "Test Corp"
        assert restored.industry == "fmcg"
        assert restored.score.company_size == 70

    def test_empty_lead_scoring(self):
        """Test scoring a lead with all defaults."""
        lead = Lead()
        scores = LeadScore()
        # Should not crash
        scores.company_size = LeadQualifierAgent._score_company_size(lead.company_size)
        scores.industry_fit = LeadQualifierAgent._score_industry_fit(lead.industry)
        scores.budget_signal = LeadQualifierAgent._score_budget(lead.estimated_budget)
        composite = scores.calculate_composite()
        assert composite >= 0

    def test_lead_score_serialization(self):
        """Test LeadScore to_dict."""
        score = LeadScore(company_size=80, industry_fit=90, budget_signal=70, timing=60, engagement=50, composite=75)
        data = score.to_dict()
        assert data["company_size"] == 80.0
        assert data["composite"] == 75.0

    @pytest.mark.asyncio
    async def test_reflect_stores_outcomes(self, agent):
        """Test that reflect stores conversion outcomes."""
        from app.agents.base import AgentResult

        result = AgentResult(
            success=True,
            data={"lead_id": "test", "action": "escalate", "composite_score": 80},
        )
        await agent.reflect(result)

        assert len(agent._conversion_outcomes) == 1
        assert agent._conversion_outcomes[0]["lead_id"] == "test"
