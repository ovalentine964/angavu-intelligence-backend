"""
Tests for the Onboarding Agent.

Tests cover:
- Onboarding flow generation for each product tier
- Step completion tracking
- Progress percentage calculation
- Stall detection
- Feedback processing
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.agents.base import EventType
from app.autonomous.agents.onboarding_agent import OnboardingAgent
from app.autonomous.models.onboarding import (
    OnboardingFlow,
    OnboardingStatus,
    OnboardingStep,
    StepStatus,
    create_default_onboarding_steps,
)


@pytest.fixture
def agent():
    """Create an OnboardingAgent for testing."""
    a = OnboardingAgent()
    a._event_bus = AsyncMock()
    return a


# ── Onboarding Model Tests ─────────────────────────────────────────


class TestOnboardingModel:
    """Test Onboarding data models."""

    def test_default_steps_standard(self):
        """Test default steps for standard tier."""
        steps = create_default_onboarding_steps("standard")
        assert len(steps) >= 5
        assert steps[0].name == "Welcome Email"
        assert steps[0].due_days == 0

    def test_default_steps_enterprise(self):
        """Test that enterprise gets more steps."""
        standard = create_default_onboarding_steps("standard")
        enterprise = create_default_onboarding_steps("enterprise")
        assert len(enterprise) > len(standard)

    def test_default_steps_professional(self):
        """Test that professional gets extra steps."""
        standard = create_default_onboarding_steps("standard")
        professional = create_default_onboarding_steps("professional")
        assert len(professional) > len(standard)

    def test_progress_percentage(self):
        """Test progress calculation."""
        flow = OnboardingFlow(
            steps=[
                OnboardingStep(name="Step 1", order=1, status=StepStatus.COMPLETED),
                OnboardingStep(name="Step 2", order=2, status=StepStatus.COMPLETED),
                OnboardingStep(name="Step 3", order=3, status=StepStatus.PENDING),
                OnboardingStep(name="Step 4", order=4, status=StepStatus.PENDING),
            ]
        )
        assert flow.progress_pct == 50.0

    def test_progress_all_done(self):
        """Test 100% progress."""
        flow = OnboardingFlow(
            steps=[
                OnboardingStep(name="Step 1", order=1, status=StepStatus.COMPLETED),
                OnboardingStep(name="Step 2", order=2, status=StepStatus.COMPLETED),
            ]
        )
        assert flow.progress_pct == 100.0

    def test_current_step(self):
        """Test getting the current incomplete step."""
        flow = OnboardingFlow(
            steps=[
                OnboardingStep(name="Step 1", order=1, status=StepStatus.COMPLETED),
                OnboardingStep(name="Step 2", order=2, status=StepStatus.PENDING),
                OnboardingStep(name="Step 3", order=3, status=StepStatus.PENDING),
            ]
        )
        current = flow.current_step
        assert current is not None
        assert current.name == "Step 2"

    def test_current_step_all_done(self):
        """Test current step when all steps are done."""
        flow = OnboardingFlow(
            steps=[
                OnboardingStep(name="Step 1", order=1, status=StepStatus.COMPLETED),
            ]
        )
        assert flow.current_step is None

    def test_stall_detection(self):
        """Test stalled onboarding detection."""
        flow = OnboardingFlow(
            status=OnboardingStatus.IN_PROGRESS,
            started_at=datetime.now(UTC) - timedelta(days=14),
            steps=[
                OnboardingStep(
                    name="Step 1",
                    order=1,
                    status=StepStatus.COMPLETED,
                    completed_at=datetime.now(UTC) - timedelta(days=10),
                ),
                OnboardingStep(name="Step 2", order=2, status=StepStatus.PENDING),
            ]
        )
        assert flow.is_stalled

    def test_not_stalled_when_active(self):
        """Test that recently active flows are not stalled."""
        flow = OnboardingFlow(
            status=OnboardingStatus.IN_PROGRESS,
            started_at=datetime.now(UTC) - timedelta(days=3),
            steps=[
                OnboardingStep(
                    name="Step 1",
                    order=1,
                    status=StepStatus.COMPLETED,
                    completed_at=datetime.now(UTC) - timedelta(days=1),
                ),
            ]
        )
        assert not flow.is_stalled

    def test_flow_roundtrip(self):
        """Test OnboardingFlow serialization."""
        flow = OnboardingFlow(
            client_id="c1",
            client_name="Test Corp",
            product_tier="enterprise",
            steps=create_default_onboarding_steps("enterprise"),
        )
        data = flow.to_dict()
        restored = OnboardingFlow.from_dict(data)

        assert restored.client_name == "Test Corp"
        assert restored.product_tier == "enterprise"
        assert len(restored.steps) == len(flow.steps)


# ── Onboarding Agent Tests ─────────────────────────────────────────


class TestOnboardingAgent:
    """Test the OnboardingAgent."""

    @pytest.mark.asyncio
    async def test_create_onboarding(self, agent):
        """Test creating an onboarding flow."""
        events = []
        result = await agent._create_onboarding(
            params={
                "client_id": "c1",
                "client_name": "Test Corp",
                "product_tier": "standard",
            },
            events=events,
        )

        assert "error" not in result
        assert result["client_name"] == "Test Corp"
        assert result["total_steps"] >= 5
        assert len(events) == 1
        assert events[0].event_type == EventType.ONBOARDING_STARTED

    @pytest.mark.asyncio
    async def test_create_enterprise_onboarding(self, agent):
        """Test that enterprise gets more steps."""
        events = []
        result = await agent._create_onboarding(
            params={
                "client_id": "c2",
                "client_name": "Big Corp",
                "product_tier": "enterprise",
            },
            events=events,
        )

        assert result["total_steps"] > 6  # More than standard

    @pytest.mark.asyncio
    async def test_welcome_email_auto_completed(self, agent):
        """Test that welcome email step is auto-completed."""
        events = []
        result = await agent._create_onboarding(
            params={"client_id": "c1", "client_name": "Corp", "product_tier": "standard"},
            events=events,
        )
        flow_id = result["flow_id"]
        flow = agent._flows[flow_id]

        # First step should be completed
        assert flow.steps[0].status == StepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_feedback_completes_flow(self, agent):
        """Test that positive feedback with all steps done completes the flow."""
        events = []
        result = await agent._create_onboarding(
            params={"client_id": "c1", "client_name": "Corp", "product_tier": "standard"},
            events=events,
        )
        flow_id = result["flow_id"]

        # Complete all steps
        flow = agent._flows[flow_id]
        for step in flow.steps:
            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.now(UTC)

        # Process feedback
        feedback_result = await agent._process_feedback(
            params={
                "flow_id": flow_id,
                "satisfaction_score": 4.5,
                "feedback": "Great onboarding experience!",
            },
            events=events,
        )

        assert feedback_result["status"] == OnboardingStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_complete_step(self, agent):
        """Test completing a specific step."""
        events = []
        result = await agent._create_onboarding(
            params={"client_id": "c1", "client_name": "Corp", "product_tier": "standard"},
            events=events,
        )
        flow_id = result["flow_id"]
        flow = agent._flows[flow_id]

        # Complete second step
        step_name = flow.steps[1].name
        complete_result = agent.complete_step(flow_id, step_name)

        assert complete_result is not None
        assert complete_result["step"] == step_name
        assert complete_result["progress_pct"] > 0

    @pytest.mark.asyncio
    async def test_check_progress(self, agent):
        """Test progress checking across all flows."""
        events = []
        await agent._create_onboarding(
            params={"client_id": "c1", "client_name": "Corp", "product_tier": "standard"},
            events=events,
        )

        check_result = await agent._check_progress(events)

        assert check_result["total_flows"] == 1
        assert check_result["active"] >= 0
