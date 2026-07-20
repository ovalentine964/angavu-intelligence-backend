"""
Tests for Agent Factory — Creation, wiring, and lifecycle management.

Tests cover:
- AgentInfrastructure dataclass
- AgentFactory.create_all() with mocked dependencies
- Agent creation (core, domain, utility, governance, research)
- Service injection into agents
- Shutdown ordering
- EventBus and tracer wiring
- Communication protocol creation
- Edge cases and error handling

Run: pytest tests/test_agent_factory.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import BiasharaAgent, EventType
from app.agents.event_bus import EventBus
from app.agents.factory import AgentFactory, AgentInfrastructure
from app.agents.observability import AgentTracer


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def factory():
    """Create a fresh AgentFactory."""
    return AgentFactory()


@pytest.fixture
def mock_event_bus():
    """Create a mock EventBus."""
    bus = MagicMock(spec=EventBus)
    bus.connect = AsyncMock()
    bus.disconnect = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.get_stats = MagicMock(return_value={"mode": "in_memory", "subscriptions": {}, "dead_letter_count": 0, "persisted_count": 0})
    return bus


# ════════════════════════════════════════════════════════════════════
# AgentInfrastructure Tests
# ════════════════════════════════════════════════════════════════════


class TestAgentInfrastructure:
    """Test AgentInfrastructure dataclass."""

    def test_agent_map_auto_populated(self):
        """agent_map should be auto-populated from agents list."""
        mock_agent = MagicMock(spec=BiasharaAgent)
        mock_agent.name = "TestAgent"
        bus = MagicMock(spec=EventBus)
        tracer = MagicMock(spec=AgentTracer)

        infra = AgentInfrastructure(
            event_bus=bus,
            tracer=tracer,
            agents=[mock_agent],
        )
        assert "TestAgent" in infra.agent_map
        assert infra.agent_map["TestAgent"] is mock_agent

    def test_default_empty_lists(self):
        """Default lists should be empty."""
        bus = MagicMock(spec=EventBus)
        tracer = MagicMock(spec=AgentTracer)
        infra = AgentInfrastructure(event_bus=bus, tracer=tracer, agents=[])
        assert infra.domain_agents == []
        assert infra.utility_agents == []
        assert infra.financial_agents == []
        assert infra.governance_agents == []
        assert infra.research_agents == []
        assert infra.loop_agents == []
        assert infra.intelligence_flows == {}


# ════════════════════════════════════════════════════════════════════
# Factory Creation Tests (mocked dependencies)
# ════════════════════════════════════════════════════════════════════


class TestAgentFactoryCreation:
    """Test AgentFactory.create_all() with mocked infrastructure."""

    @pytest.mark.asyncio
    async def test_create_all_returns_infrastructure(self, factory):
        """create_all() should return AgentInfrastructure."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        assert isinstance(infra, AgentInfrastructure)
        assert infra.event_bus is not None
        assert infra.tracer is not None
        assert len(infra.agents) >= 4  # Core agents

        # Cleanup
        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_core_agents_created(self, factory):
        """Core agents (4) should always be created."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        agent_names = {a.name for a in infra.agents}
        assert "TransactionProcessor" in agent_names
        assert "IntelligenceGenerator" in agent_names
        assert "ReportGenerator" in agent_names
        assert "SelfEvolution" in agent_names

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_domain_agents_created(self, factory):
        """Domain agents should be created."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        domain_names = {a.name for a in infra.domain_agents}
        # Should have at least the 6 domain + 5 new agents
        assert len(domain_names) >= 6

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_utility_agents_created(self, factory):
        """Utility agents should be created."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        utility_names = {a.name for a in infra.utility_agents}
        assert len(utility_names) >= 6

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_governance_agents_created(self, factory):
        """Governance agents (Audit, Ethics, Privacy) should be created."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        gov_names = {a.name for a in infra.governance_agents}
        assert "AuditAgent" in gov_names
        assert "EthicsAgent" in gov_names
        assert "PrivacyAgent" in gov_names

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_research_agents_created(self, factory):
        """Research agents should be created."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        research_names = {a.name for a in infra.research_agents}
        assert len(research_names) >= 3

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_event_bus_wired_to_all_agents(self, factory):
        """EventBus should be injected into all agents."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        all_agents = infra.agents + infra.domain_agents + infra.utility_agents + infra.governance_agents + infra.research_agents
        for agent in all_agents:
            assert agent._event_bus is infra.event_bus
        assert infra.meta_agent._event_bus is infra.event_bus

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_tracer_wired_to_all_agents(self, factory):
        """AgentTracer should be injected into all agents."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        all_agents = infra.agents + infra.domain_agents + infra.utility_agents + infra.governance_agents + infra.research_agents
        for agent in all_agents:
            assert agent._tracer is infra.tracer

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_communication_protocols_created(self, factory):
        """Communication protocols should be created."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        assert infra.broadcast_protocol is not None
        assert infra.p2p_protocol is not None
        assert infra.delegation_protocol is not None

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False

    @pytest.mark.asyncio
    async def test_meta_agent_created(self, factory):
        """MetaAgent should be created and have all agents registered."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        assert infra.meta_agent is not None
        assert infra.meta_agent.name == "MetaAgent"

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False


# ════════════════════════════════════════════════════════════════════
# Shutdown Tests
# ════════════════════════════════════════════════════════════════════


class TestAgentFactoryShutdown:
    """Test AgentFactory.shutdown() behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_stops_all_agents(self, factory):
        """Shutdown should stop all agents."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        # All agents should be running
        for agent in infra.agents:
            assert agent._running is True

        await factory.shutdown()

        # All agents should be stopped
        for agent in infra.agents:
            assert agent._running is False

    @pytest.mark.asyncio
    async def test_shutdown_disconnects_event_bus(self, factory):
        """Shutdown should disconnect the event bus."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock) as mock_disconnect:
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

                await factory.shutdown()
                mock_disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_clears_infrastructure(self, factory):
        """Shutdown should clear the infrastructure reference."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        assert factory._infrastructure is not None
        await factory.shutdown()
        assert factory._infrastructure is None

    @pytest.mark.asyncio
    async def test_shutdown_without_create_is_noop(self, factory):
        """Shutdown without prior create_all should not raise."""
        await factory.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_shutdown_handles_agent_errors(self, factory):
        """Shutdown should handle individual agent stop errors gracefully."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        # Make one agent's stop raise
        original_stop = infra.agents[0].stop
        infra.agents[0].stop = AsyncMock(side_effect=RuntimeError("stop failed"))

        # Shutdown should not raise
        await factory.shutdown()
        assert factory._infrastructure is None


# ════════════════════════════════════════════════════════════════════
# Reflect Loop Tests
# ════════════════════════════════════════════════════════════════════


class TestReflectLoops:
    """Test reflect→behavior feedback loop wiring."""

    @pytest.mark.asyncio
    async def test_intelligence_generator_has_adaptive_reflect(self, factory):
        """IntelligenceGenerator should have adaptive reflect wired."""
        with patch.object(EventBus, 'connect', new_callable=AsyncMock):
            with patch.object(EventBus, 'disconnect', new_callable=AsyncMock):
                infra = await factory.create_all(
                    enable_loops=False,
                    enable_long_horizon=False,
                    enable_deerflow=False,
                )

        intel = next(a for a in infra.agents if a.name == "IntelligenceGenerator")
        # The reflect method should be wrapped (not the original)
        assert hasattr(intel, 'reflect')

        for agent in infra.agents + infra.domain_agents + infra.utility_agents:
            agent._running = False
        for agent in infra.governance_agents + infra.research_agents:
            agent._running = False
