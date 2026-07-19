"""Tests for the escalation system."""


import pytest

from app.autonomous.escalation import (
    DEFAULT_SLAS,
    ESCALATION_TRIGGERS,
    EscalationManager,
    EscalationTicket,
    Priority,
)


class TestPriority:
    def test_priority_ordering(self):
        assert Priority.P1_CRITICAL < Priority.P2_HIGH < Priority.P3_MEDIUM < Priority.P4_LOW

    def test_priority_names(self):
        assert Priority.P1_CRITICAL.name == "P1_CRITICAL"
        assert Priority.P4_LOW.name == "P4_LOW"


class TestSLA:
    def test_default_slas_defined(self):
        assert len(DEFAULT_SLAS) == 4
        for p in Priority:
            assert p in DEFAULT_SLAS

    def test_p1_sla_is_fastest(self):
        p1 = DEFAULT_SLAS[Priority.P1_CRITICAL]
        p4 = DEFAULT_SLAS[Priority.P4_LOW]
        assert p1.response_time_seconds < p4.response_time_seconds
        assert p1.resolution_time_seconds < p4.resolution_time_seconds

    def test_sla_has_channels(self):
        for sla in DEFAULT_SLAS.values():
            assert len(sla.channels) > 0

    def test_response_time_label(self):
        assert DEFAULT_SLAS[Priority.P1_CRITICAL].response_time_label == "5m"
        assert DEFAULT_SLAS[Priority.P2_HIGH].response_time_label == "1h"


class TestEscalationTriggers:
    def test_all_triggers_have_fields(self):
        for name, trigger in ESCALATION_TRIGGERS.items():
            assert trigger.name == name
            assert trigger.description
            assert trigger.priority in Priority
            assert trigger.condition

    def test_financial_action_is_p1(self):
        assert ESCALATION_TRIGGERS["financial_action"].priority == Priority.P1_CRITICAL

    def test_compliance_risk_is_p1(self):
        assert ESCALATION_TRIGGERS["compliance_risk"].priority == Priority.P1_CRITICAL

    def test_trigger_to_dict(self):
        trigger = ESCALATION_TRIGGERS["consecutive_errors"]
        d = trigger.to_dict()
        assert d["name"] == "consecutive_errors"
        assert "priority" in d


class TestEscalationTicket:
    def test_ticket_creation(self):
        ticket = EscalationTicket(
            ticket_id="test123",
            trigger_name="consecutive_errors",
            priority=Priority.P2_HIGH,
            agent_name="TestAgent",
            summary="Test escalation",
        )
        assert ticket.status == "open"
        assert ticket.age_seconds >= 0
        assert not ticket.is_breached

    def test_ticket_acknowledge(self):
        ticket = EscalationTicket(
            ticket_id="test123",
            trigger_name="test",
            priority=Priority.P3_MEDIUM,
            agent_name="TestAgent",
            summary="Test",
        )
        ticket.acknowledge()
        assert ticket.status == "acknowledged"
        assert ticket.acknowledged_at is not None

    def test_ticket_resolve(self):
        ticket = EscalationTicket(
            ticket_id="test123",
            trigger_name="test",
            priority=Priority.P3_MEDIUM,
            agent_name="TestAgent",
            summary="Test",
        )
        ticket.resolve("Fixed by doing X")
        assert ticket.status == "resolved"
        assert ticket.resolved_at is not None
        assert ticket.resolution == "Fixed by doing X"

    def test_ticket_to_dict(self):
        ticket = EscalationTicket(
            ticket_id="test123",
            trigger_name="test",
            priority=Priority.P3_MEDIUM,
            agent_name="TestAgent",
            summary="Test",
        )
        d = ticket.to_dict()
        assert d["ticket_id"] == "test123"
        assert d["priority"] == "P3_MEDIUM"
        assert d["status"] == "open"


class TestEscalationManager:
    @pytest.fixture
    def manager(self):
        return EscalationManager()

    @pytest.mark.asyncio
    async def test_escalate_creates_ticket(self, manager):
        ticket = await manager.escalate(
            trigger_name="consecutive_errors",
            agent_name="TestAgent",
            summary="Test error",
        )
        assert ticket.status == "open"
        assert ticket.agent_name == "TestAgent"

    @pytest.mark.asyncio
    async def test_escalate_with_unknown_trigger(self, manager):
        ticket = await manager.escalate(
            trigger_name="nonexistent_trigger",
            agent_name="TestAgent",
            summary="Unknown trigger test",
        )
        assert ticket.status == "open"

    @pytest.mark.asyncio
    async def test_record_task_updates_total(self, manager):
        manager.record_task()
        manager.record_task()
        metrics = manager.get_metrics()
        assert metrics["total_tasks"] == 2

    @pytest.mark.asyncio
    async def test_escalation_rate_calculation(self, manager):
        # Record 10 tasks with 1 escalation
        for _ in range(10):
            manager.record_task()
        await manager.escalate(
            trigger_name="consecutive_errors",
            agent_name="TestAgent",
            summary="One escalation",
        )
        metrics = manager.get_metrics()
        assert metrics["escalation_rate"] == pytest.approx(9.09, abs=0.1)  # 1/11 * 100

    @pytest.mark.asyncio
    async def test_acknowledge_ticket(self, manager):
        ticket = await manager.escalate(
            trigger_name="consecutive_errors",
            agent_name="TestAgent",
            summary="Test",
        )
        assert manager.acknowledge_ticket(ticket.ticket_id)
        assert manager.acknowledge_ticket(ticket.ticket_id) is False  # Already acknowledged

    @pytest.mark.asyncio
    async def test_resolve_ticket(self, manager):
        ticket = await manager.escalate(
            trigger_name="consecutive_errors",
            agent_name="TestAgent",
            summary="Test",
        )
        assert manager.resolve_ticket(ticket.ticket_id, "Fixed")
        assert ticket.ticket_id not in manager._tickets

    @pytest.mark.asyncio
    async def test_get_open_tickets(self, manager):
        await manager.escalate(
            trigger_name="consecutive_errors",
            agent_name="Agent1",
            summary="First",
        )
        await manager.escalate(
            trigger_name="low_confidence",
            agent_name="Agent2",
            summary="Second",
        )
        open_tickets = manager.get_open_tickets()
        assert len(open_tickets) == 2

    @pytest.mark.asyncio
    async def test_notification_handler(self, manager):
        notified = []

        async def mock_handler(ticket):
            notified.append(ticket.ticket_id)

        manager.register_notification_handler("telegram", mock_handler)
        ticket = await manager.escalate(
            trigger_name="consecutive_errors",
            agent_name="TestAgent",
            summary="Notify test",
        )
        assert ticket.ticket_id in notified

    @pytest.mark.asyncio
    async def test_metrics_structure(self, manager):
        metrics = manager.get_metrics()
        assert "total_tasks" in metrics
        assert "escalation_rate" in metrics
        assert "on_target" in metrics
        assert "open_tickets" in metrics
