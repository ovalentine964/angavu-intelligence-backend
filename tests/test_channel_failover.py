"""
Tests for Channel Failover — Multi-channel delivery with automatic fallback.

Tests cover:
- FailoverManager creation and configuration
- Channel priority ordering
- Send with primary channel success
- Failover when primary fails
- Failover through all channels
- Telegram ID mapping
- Image sending
- Statistics tracking
- Health monitor integration
- Error handling

Run: pytest tests/test_channel_failover.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.adapters.base import BaseChannelAdapter, ChannelType
from app.channels.failover import (
    CHANNEL_HTTP_API,
    CHANNEL_SMS,
    CHANNEL_TELEGRAM,
    CHANNEL_WHATSAPP,
    DEFAULT_PRIORITY,
    FailoverManager,
)
from app.channels.health_monitor import ChannelHealthMonitor


# ════════════════════════════════════════════════════════════════════
# Mock Adapters
# ════════════════════════════════════════════════════════════════════


class MockAdapter(BaseChannelAdapter):
    """Mock channel adapter for testing."""

    def __init__(self, channel_type: ChannelType, send_success: bool = True):
        self._channel_type = channel_type
        self._send_success = send_success
        self._send_message_calls = []
        self._send_image_calls = []

    @property
    def channel_type(self) -> ChannelType:
        return self._channel_type

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def parse_raw_message(self, raw_data):
        return MagicMock()

    async def send_message(
        self,
        recipient_id: str,
        content: str,
        content_type: str = "text",
        **kwargs,
    ) -> bool:
        self._send_message_calls.append((recipient_id, content, content_type))
        return self._send_success

    async def send_image(
        self,
        recipient_id: str,
        image_data: bytes,
        caption: str = "",
    ) -> bool:
        self._send_image_calls.append((recipient_id, image_data, caption))
        return self._send_success


class MockRegistry:
    """Mock adapter registry."""

    def __init__(self, adapters: dict[ChannelType, BaseChannelAdapter] | None = None):
        self._adapters = adapters or {}

    def get_adapter(self, channel_type: ChannelType) -> BaseChannelAdapter | None:
        return self._adapters.get(channel_type)


class MockHealthMonitor:
    """Mock health monitor that reports all channels as healthy."""

    def __init__(self, healthy: bool = True):
        self._healthy = healthy

    def is_channel_healthy(self, channel_name: str) -> bool:
        return self._healthy


class SelectiveHealthMonitor:
    """Mock health monitor that reports specific channels as unhealthy."""

    def __init__(self, unhealthy_channels: set[str]):
        self._unhealthy = unhealthy_channels

    def is_channel_healthy(self, channel_name: str) -> bool:
        return channel_name not in self._unhealthy


# ════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════


@pytest.fixture
def all_success_adapters():
    """Adapters where all channels succeed."""
    return {
        ChannelType.WHATSAPP: MockAdapter(ChannelType.WHATSAPP, True),
        ChannelType.TELEGRAM: MockAdapter(ChannelType.TELEGRAM, True),
        ChannelType.SMS: MockAdapter(ChannelType.SMS, True),
        ChannelType.HTTP_API: MockAdapter(ChannelType.HTTP_API, True),
    }


@pytest.fixture
def whatsapp_fails_adapters():
    """Adapters where WhatsApp fails but others succeed."""
    return {
        ChannelType.WHATSAPP: MockAdapter(ChannelType.WHATSAPP, False),
        ChannelType.TELEGRAM: MockAdapter(ChannelType.TELEGRAM, True),
        ChannelType.SMS: MockAdapter(ChannelType.SMS, True),
        ChannelType.HTTP_API: MockAdapter(ChannelType.HTTP_API, True),
    }


@pytest.fixture
def all_fail_adapters():
    """Adapters where all channels fail."""
    return {
        ChannelType.WHATSAPP: MockAdapter(ChannelType.WHATSAPP, False),
        ChannelType.TELEGRAM: MockAdapter(ChannelType.TELEGRAM, False),
        ChannelType.SMS: MockAdapter(ChannelType.SMS, False),
        ChannelType.HTTP_API: MockAdapter(ChannelType.HTTP_API, False),
    }


# ════════════════════════════════════════════════════════════════════
# FailoverManager Configuration Tests
# ════════════════════════════════════════════════════════════════════


class TestFailoverManagerConfig:
    """Test FailoverManager creation and configuration."""

    def test_default_channel_priority(self):
        """Default priority should be WhatsApp → Telegram → SMS → HTTP."""
        assert DEFAULT_PRIORITY == [
            CHANNEL_WHATSAPP, CHANNEL_TELEGRAM, CHANNEL_SMS, CHANNEL_HTTP_API,
        ]

    def test_manager_creation(self):
        """FailoverManager should be created with defaults."""
        fm = FailoverManager()
        assert fm._failover_count == 0
        assert fm._total_sent == 0
        assert fm._total_failed == 0

    def test_channel_order_default(self):
        """_get_channel_order should return default priority."""
        fm = FailoverManager()
        order = fm._get_channel_order()
        assert order == DEFAULT_PRIORITY

    def test_channel_order_preferred(self):
        """Preferred channel should be first."""
        fm = FailoverManager()
        order = fm._get_channel_order(preferred_channel=CHANNEL_TELEGRAM)
        assert order[0] == CHANNEL_TELEGRAM
        assert len(order) == len(DEFAULT_PRIORITY)

    def test_channel_order_invalid_preferred(self):
        """Invalid preferred channel should fall back to default."""
        fm = FailoverManager()
        order = fm._get_channel_order(preferred_channel="invalid")
        assert order == DEFAULT_PRIORITY


# ════════════════════════════════════════════════════════════════════
# Telegram ID Mapping Tests
# ════════════════════════════════════════════════════════════════════


class TestTelegramIDMapping:
    """Test Telegram chat_id mapping."""

    def test_set_and_get_telegram_id(self):
        fm = FailoverManager()
        fm.set_telegram_id("worker_001", "tg_chat_123")
        assert fm.get_telegram_id("worker_001") == "tg_chat_123"

    def test_get_unknown_telegram_id(self):
        fm = FailoverManager()
        assert fm.get_telegram_id("unknown_worker") is None

    def test_resolve_recipient_telegram_with_mapping(self):
        fm = FailoverManager()
        fm.set_telegram_id("worker_001", "tg_chat_123")
        resolved = fm._resolve_recipient("worker_001", CHANNEL_TELEGRAM)
        assert resolved == "tg_chat_123"

    def test_resolve_recipient_telegram_without_mapping(self):
        fm = FailoverManager()
        resolved = fm._resolve_recipient("worker_001", CHANNEL_TELEGRAM)
        assert resolved == "worker_001"  # Falls back to as-is

    def test_resolve_recipient_whatsapp(self):
        fm = FailoverManager()
        resolved = fm._resolve_recipient("+254712345678", CHANNEL_WHATSAPP)
        assert resolved == "+254712345678"

    def test_resolve_recipient_sms(self):
        fm = FailoverManager()
        resolved = fm._resolve_recipient("+254712345678", CHANNEL_SMS)
        assert resolved == "+254712345678"

    def test_resolve_recipient_http_api(self):
        fm = FailoverManager()
        resolved = fm._resolve_recipient("worker_001", CHANNEL_HTTP_API)
        assert resolved == "worker_001"


# ════════════════════════════════════════════════════════════════════
# Send Tests — Happy Path
# ════════════════════════════════════════════════════════════════════


class TestSendHappyPath:
    """Test successful message delivery."""

    @pytest.mark.asyncio
    async def test_send_primary_channel_success(self, all_success_adapters):
        """Should succeed on first try with WhatsApp."""
        registry = MockRegistry(all_success_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send(recipient_id="+254712345678", content="Hello!")

        assert result["success"] is True
        assert result["channel_used"] == CHANNEL_WHATSAPP
        assert result["failover_triggered"] is False
        assert len(result["attempted"]) == 1
        assert fm._total_sent == 1

    @pytest.mark.asyncio
    async def test_send_with_preferred_channel(self, all_success_adapters):
        """Preferred channel should be tried first."""
        registry = MockRegistry(all_success_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send(
            recipient_id="+254712345678",
            content="Hello!",
            preferred_channel=CHANNEL_SMS,
        )

        assert result["success"] is True
        assert result["channel_used"] == CHANNEL_SMS


# ════════════════════════════════════════════════════════════════════
# Send Tests — Failover
# ════════════════════════════════════════════════════════════════════


class TestSendFailover:
    """Test failover behavior when channels fail."""

    @pytest.mark.asyncio
    async def test_failover_to_telegram(self, whatsapp_fails_adapters):
        """Should fall back to Telegram when WhatsApp fails."""
        registry = MockRegistry(whatsapp_fails_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send(recipient_id="+254712345678", content="Hello!")

        assert result["success"] is True
        assert result["channel_used"] == CHANNEL_TELEGRAM
        assert result["failover_triggered"] is True
        assert fm._failover_count == 1

    @pytest.mark.asyncio
    async def test_failover_records_attempted_channels(self, whatsapp_fails_adapters):
        """Should record all attempted channels."""
        registry = MockRegistry(whatsapp_fails_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send(recipient_id="+254712345678", content="Hello!")

        assert len(result["attempted"]) == 2
        assert any("whatsapp" in a for a in result["attempted"])
        assert any("telegram" in a for a in result["attempted"])

    @pytest.mark.asyncio
    async def test_all_channels_fail(self, all_fail_adapters):
        """Should report failure when all channels fail."""
        registry = MockRegistry(all_fail_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send(recipient_id="+254712345678", content="Hello!")

        assert result["success"] is False
        assert result["error"] == "All channels failed"
        assert result["channel_used"] is None
        assert fm._total_failed == 1

    @pytest.mark.asyncio
    async def test_failover_skips_unhealthy_channel(self):
        """Should skip unhealthy channels (except HTTP API)."""
        adapters = {
            ChannelType.WHATSAPP: MockAdapter(ChannelType.WHATSAPP, True),
            ChannelType.TELEGRAM: MockAdapter(ChannelType.TELEGRAM, True),
            ChannelType.SMS: MockAdapter(ChannelType.SMS, True),
            ChannelType.HTTP_API: MockAdapter(ChannelType.HTTP_API, True),
        }
        registry = MockRegistry(adapters)
        # WhatsApp is unhealthy
        health = SelectiveHealthMonitor(unhealthy_channels={CHANNEL_WHATSAPP})
        fm = FailoverManager(registry=registry, health_monitor=health)

        result = await fm.send(recipient_id="+254712345678", content="Hello!")

        assert result["success"] is True
        # Should have skipped WhatsApp and used Telegram
        assert result["channel_used"] == CHANNEL_TELEGRAM
        assert result["failover_triggered"] is True
        # WhatsApp should not have been called
        assert len(adapters[ChannelType.WHATSAPP]._send_message_calls) == 0

    @pytest.mark.asyncio
    async def test_http_api_never_skipped(self):
        """HTTP API should never be skipped even if unhealthy."""
        adapters = {
            ChannelType.WHATSAPP: MockAdapter(ChannelType.WHATSAPP, False),
            ChannelType.TELEGRAM: MockAdapter(ChannelType.TELEGRAM, False),
            ChannelType.SMS: MockAdapter(ChannelType.SMS, False),
            ChannelType.HTTP_API: MockAdapter(ChannelType.HTTP_API, True),
        }
        registry = MockRegistry(adapters)
        # All channels unhealthy
        health = SelectiveHealthMonitor(unhealthy_channels={
            CHANNEL_WHATSAPP, CHANNEL_TELEGRAM, CHANNEL_SMS, CHANNEL_HTTP_API,
        })
        fm = FailoverManager(registry=registry, health_monitor=health)

        result = await fm.send(recipient_id="worker_001", content="Hello!")

        # HTTP API should still be tried
        assert result["success"] is True
        assert result["channel_used"] == CHANNEL_HTTP_API


# ════════════════════════════════════════════════════════════════════
# Image Sending Tests
# ════════════════════════════════════════════════════════════════════


class TestImageSending:
    """Test image sending with failover."""

    @pytest.mark.asyncio
    async def test_send_image_success(self, all_success_adapters):
        """Should send image via primary channel."""
        registry = MockRegistry(all_success_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send_image(
            recipient_id="+254712345678",
            image_data=b"fake_image_bytes",
            caption="Your report",
        )

        assert result["success"] is True
        # Verify image was sent via WhatsApp
        wa_adapter = all_success_adapters[ChannelType.WHATSAPP]
        assert len(wa_adapter._send_image_calls) == 1

    @pytest.mark.asyncio
    async def test_send_image_failover(self, whatsapp_fails_adapters):
        """Should failover to next channel for images."""
        registry = MockRegistry(whatsapp_fails_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send_image(
            recipient_id="+254712345678",
            image_data=b"fake_image_bytes",
        )

        assert result["success"] is True
        assert result["channel_used"] == CHANNEL_TELEGRAM


# ════════════════════════════════════════════════════════════════════
# No Registry Tests
# ════════════════════════════════════════════════════════════════════


class TestNoRegistry:
    """Test behavior when no adapter registry is provided."""

    @pytest.mark.asyncio
    async def test_send_without_registry(self):
        """Should fail gracefully when no registry."""
        fm = FailoverManager(registry=None, health_monitor=MockHealthMonitor())

        result = await fm.send(recipient_id="+254712345678", content="Hello!")

        assert result["success"] is False
        assert "no_adapter" in str(result["attempted"])


# ════════════════════════════════════════════════════════════════════
# Statistics Tests
# ════════════════════════════════════════════════════════════════════


class TestStatistics:
    """Test failover statistics tracking."""

    @pytest.mark.asyncio
    async def test_stats_after_success(self, all_success_adapters):
        """Stats should track successful sends."""
        registry = MockRegistry(all_success_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        await fm.send(recipient_id="+254712345678", content="Hello!")

        stats = fm.get_stats()
        assert stats["total_sent"] == 1
        assert stats["total_failed"] == 0
        assert stats["failover_count"] == 0
        assert stats["channel_send_counts"][CHANNEL_WHATSAPP] == 1

    @pytest.mark.asyncio
    async def test_stats_after_failover(self, whatsapp_fails_adapters):
        """Stats should track failover events."""
        registry = MockRegistry(whatsapp_fails_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        await fm.send(recipient_id="+254712345678", content="Hello!")

        stats = fm.get_stats()
        assert stats["total_sent"] == 1
        assert stats["failover_count"] == 1
        assert stats["channel_fail_counts"][CHANNEL_WHATSAPP] == 1
        assert stats["channel_send_counts"][CHANNEL_TELEGRAM] == 1

    @pytest.mark.asyncio
    async def test_stats_after_all_fail(self, all_fail_adapters):
        """Stats should track total failures."""
        registry = MockRegistry(all_fail_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        await fm.send(recipient_id="+254712345678", content="Hello!")

        stats = fm.get_stats()
        assert stats["total_sent"] == 0
        assert stats["total_failed"] == 1

    @pytest.mark.asyncio
    async def test_stats_telegram_mappings(self):
        """Stats should track Telegram ID mappings."""
        fm = FailoverManager()
        fm.set_telegram_id("w1", "tg1")
        fm.set_telegram_id("w2", "tg2")

        stats = fm.get_stats()
        assert stats["telegram_id_mappings"] == 2


# ════════════════════════════════════════════════════════════════════
# Edge Cases
# ════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_adapter_exception_during_send(self):
        """Should handle adapter exceptions gracefully."""
        whatsapp = MockAdapter(ChannelType.WHATSAPP, True)
        whatsapp.send_message = AsyncMock(side_effect=Exception("Connection timeout"))
        telegram = MockAdapter(ChannelType.TELEGRAM, True)

        registry = MockRegistry({
            ChannelType.WHATSAPP: whatsapp,
            ChannelType.TELEGRAM: telegram,
            ChannelType.SMS: MockAdapter(ChannelType.SMS, True),
            ChannelType.HTTP_API: MockAdapter(ChannelType.HTTP_API, True),
        })
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        result = await fm.send(recipient_id="+254712345678", content="Hello!")

        # Should failover to Telegram
        assert result["success"] is True
        assert result["channel_used"] == CHANNEL_TELEGRAM
        assert any("error" in a for a in result["attempted"])

    @pytest.mark.asyncio
    async def test_send_multiple_messages(self, all_success_adapters):
        """Should track statistics across multiple sends."""
        registry = MockRegistry(all_success_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        for i in range(5):
            await fm.send(recipient_id=f"+25471234567{i}", content=f"Message {i}")

        stats = fm.get_stats()
        assert stats["total_sent"] == 5
        assert stats["channel_send_counts"][CHANNEL_WHATSAPP] == 5

    @pytest.mark.asyncio
    async def test_content_type_passed_to_adapter(self, all_success_adapters):
        """Content type should be passed to the adapter."""
        registry = MockRegistry(all_success_adapters)
        fm = FailoverManager(registry=registry, health_monitor=MockHealthMonitor())

        await fm.send(
            recipient_id="+254712345678",
            content="Hello!",
            content_type="text",
        )

        wa = all_success_adapters[ChannelType.WHATSAPP]
        assert len(wa._send_message_calls) == 1
        assert wa._send_message_calls[0] == ("+254712345678", "Hello!", "text")
