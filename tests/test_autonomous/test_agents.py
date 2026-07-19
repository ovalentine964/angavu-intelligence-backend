"""Tests for autonomous agents (Sales, Content, Operations)."""


import pytest

from app.agents.base import AgentDecision, EventType
from app.autonomous.agents.content_agent import ContentAgent
from app.autonomous.agents.operations_agent import OperationsAgent
from app.autonomous.agents.sales_agent import SalesAgent
from app.autonomous.escalation import EscalationManager
from app.autonomous.monitoring import AgentMonitor


class TestSalesAgent:
    @pytest.fixture
    def agent(self):
        a = SalesAgent()
        a.set_monitor(AgentMonitor())
        a.set_escalation(EscalationManager())
        return a

    def test_agent_identity(self, agent):
        assert agent.name == "SalesAgent"
        assert "lead_discovery" in agent.capabilities
        assert "outreach_execution" in agent.capabilities

    @pytest.mark.asyncio
    async def test_think_idle_on_no_event(self, agent):
        context = {"event": {"event_type": "", "payload": {}}}
        decision = await agent.think(context)
        assert decision.action == "idle"

    @pytest.mark.asyncio
    async def test_think_qualify_on_mfi_transaction(self, agent):
        context = {
            "event": {
                "event_type": EventType.TRANSACTION_PROCESSED.value,
                "payload": {"business_type": "mfi", "id": "lead_1"},
            }
        }
        decision = await agent.think(context)
        assert decision.action == "qualify_lead"
        assert decision.confidence > 0.5

    @pytest.mark.asyncio
    async def test_act_qualify_lead(self, agent):
        decision = AgentDecision(
            action="qualify_lead",
            parameters={
                "lead_data": {
                    "id": "lead_test",
                    "sector": "mfi",
                    "user_count": 5000,
                    "has_api": True,
                    "country": "KE",
                    "annual_revenue": 200000,
                    "active_pain_point": True,
                }
            },
        )
        result = await agent.act(decision)
        assert result.success
        assert result.data["qualified"] is True
        assert result.data["score"] >= 0.6

    @pytest.mark.asyncio
    async def test_act_qualify_low_score_lead(self, agent):
        decision = AgentDecision(
            action="qualify_lead",
            parameters={
                "lead_data": {
                    "id": "lead_low",
                    "sector": "retail",
                    "user_count": 10,
                    "has_api": False,
                    "country": "US",
                    "annual_revenue": 5000,
                    "active_pain_point": False,
                }
            },
        )
        result = await agent.act(decision)
        assert result.success
        assert result.data["qualified"] is False

    @pytest.mark.asyncio
    async def test_act_unknown_action(self, agent):
        decision = AgentDecision(action="nonexistent_action", parameters={})
        result = await agent.act(decision)
        assert result.success is False
        assert "Unknown action" in result.error

    @pytest.mark.asyncio
    async def test_follow_up_scheduling(self, agent):
        # Qualify a lead first
        decision = AgentDecision(
            action="qualify_lead",
            parameters={
                "lead_data": {
                    "id": "lead_followup",
                    "sector": "sacco",
                    "user_count": 10000,
                    "has_api": True,
                    "country": "KE",
                    "annual_revenue": 500000,
                    "active_pain_point": True,
                }
            },
        )
        await agent.act(decision)

        # Manually schedule a follow-up
        agent._follow_up_schedule["lead_followup"] = 0  # Due now
        due = agent._get_due_follow_ups()
        assert len(due) >= 1


class TestContentAgent:
    @pytest.fixture
    def agent(self):
        a = ContentAgent()
        a.set_monitor(AgentMonitor())
        a.set_escalation(EscalationManager())
        return a

    def test_agent_identity(self, agent):
        assert agent.name == "ContentAgent"
        assert "content_creation" in agent.capabilities
        assert "seo_optimization" in agent.capabilities

    @pytest.mark.asyncio
    async def test_think_idle(self, agent):
        context = {"event": {"event_type": "", "payload": {}}}
        decision = await agent.think(context)
        assert decision.action in ("idle", "research_topics")

    @pytest.mark.asyncio
    async def test_think_create_on_intelligence(self, agent):
        context = {
            "event": {
                "event_type": EventType.INTELLIGENCE_GENERATED.value,
                "payload": {"market_insight": "Mobile money growth in Kenya"},
            }
        }
        decision = await agent.think(context)
        assert decision.action == "create_content"
        assert decision.confidence > 0.5

    @pytest.mark.asyncio
    async def test_act_create_content(self, agent):
        decision = AgentDecision(
            action="create_content",
            parameters={
                "topic": "Financial Inclusion in East Africa",
                "pillar": "thought_leadership",
                "format": "blog_post",
                "channels": ["blog", "linkedin"],
            },
        )
        result = await agent.act(decision)
        assert result.success
        assert result.data["status"] == "drafted"
        assert len(result.data["seo_keywords"]) > 0

    @pytest.mark.asyncio
    async def test_act_research_topics(self, agent):
        decision = AgentDecision(action="research_topics", parameters={})
        result = await agent.act(decision)
        assert result.success
        assert result.data["topics_found"] > 0

    def test_keyword_selection(self, agent):
        keywords = agent._select_keywords("Mobile money growth in Africa")
        assert len(keywords) >= 2
        assert any("mobile money" in kw for kw in keywords)


class TestOperationsAgent:
    @pytest.fixture
    def agent(self):
        a = OperationsAgent()
        a.set_monitor(AgentMonitor())
        a.set_escalation(EscalationManager())
        return a

    def test_agent_identity(self, agent):
        assert agent.name == "OperationsAgent"
        assert "invoice_generation" in agent.capabilities
        assert "expense_tracking" in agent.capabilities

    @pytest.mark.asyncio
    async def test_think_idle(self, agent):
        context = {"event": {"event_type": "", "payload": {}}}
        decision = await agent.think(context)
        assert decision.action == "idle"

    @pytest.mark.asyncio
    async def test_think_invoice_on_transaction(self, agent):
        context = {
            "event": {
                "event_type": EventType.TRANSACTION_PROCESSED.value,
                "payload": {
                    "requires_invoice": True,
                    "amount_usd": 200,
                    "client": "Test MFI",
                },
            }
        }
        decision = await agent.think(context)
        assert decision.action == "generate_invoice"

    @pytest.mark.asyncio
    async def test_think_approval_on_high_value(self, agent):
        context = {
            "event": {
                "event_type": EventType.TRANSACTION_PROCESSED.value,
                "payload": {
                    "requires_invoice": True,
                    "amount_usd": 1000,
                    "client": "Big MFI",
                },
            }
        }
        decision = await agent.think(context)
        assert decision.action == "request_approval"

    @pytest.mark.asyncio
    async def test_act_generate_invoice(self, agent):
        decision = AgentDecision(
            action="generate_invoice",
            parameters={
                "transaction": {
                    "amount_usd": 300,
                    "client": "Test SACCO",
                    "description": "Msaidizi subscription",
                }
            },
        )
        result = await agent.act(decision)
        assert result.success
        assert result.data["invoice_id"].startswith("INV-")
        assert result.data["amount_usd"] == 300
        assert result.data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_act_record_revenue(self, agent):
        decision = AgentDecision(
            action="record_revenue",
            parameters={
                "payment": {
                    "amount_usd": 150,
                    "source": "subscription",
                    "client": "Test Client",
                }
            },
        )
        result = await agent.act(decision)
        assert result.success
        assert result.data["amount_usd"] == 150
        assert len(agent._revenue_records) == 1

    @pytest.mark.asyncio
    async def test_generate_summary(self, agent):
        # Add some data
        agent._revenue_records.append({"amount_usd": 500})
        agent._expenses.append({"amount_usd": 200})
        agent._invoices["INV-1"] = {"amount_usd": 300, "status": "sent"}

        decision = AgentDecision(action="generate_summary", parameters={"batch": {}})
        result = await agent.act(decision)
        assert result.success
        assert result.data["total_revenue_usd"] == 500
        assert result.data["total_expenses_usd"] == 200
        assert result.data["net_income_usd"] == 300


class TestAutonomousAgentBase:
    """Test the base autonomous agent integration."""

    @pytest.mark.asyncio
    async def test_health_check_includes_autonomous_fields(self):
        agent = SalesAgent()
        agent.set_monitor(AgentMonitor())
        agent.set_escalation(EscalationManager())
        health = agent.health_check()
        assert "consecutive_errors" in health
        assert "tasks_today" in health
        assert "cost_today_usd" in health
        assert "monitor_connected" in health
        assert "escalation_connected" in health
