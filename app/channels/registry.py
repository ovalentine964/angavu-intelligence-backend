"""
Channel Registry — Adapter management and worker-channel tracking.

Manages the lifecycle of channel adapters and provides lookup
for resolving worker identities across channels.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import structlog

from app.channels.adapters.base import BaseChannelAdapter, ChannelType

logger = structlog.get_logger(__name__)


class ChannelRegistry:
    """
    Registry of channel adapters. Manages registration, lookup,
    and worker identity resolution across channels.
    """

    def __init__(self):
        self._adapters: Dict[ChannelType, BaseChannelAdapter] = {}
        self._worker_channel_map: Dict[str, Dict[str, str]] = {}

    def register(self, adapter: BaseChannelAdapter) -> None:
        """Register a channel adapter."""
        channel = adapter.channel_type
        if channel in self._adapters:
            logger.warning(
                "adapter_overwritten",
                channel=channel.value,
            )
        self._adapters[channel] = adapter
        logger.info(
            "adapter_registered",
            channel=channel.value,
            adapter_type=type(adapter).__name__,
        )

    def unregister(self, channel: ChannelType) -> None:
        """Unregister a channel adapter."""
        if channel in self._adapters:
            del self._adapters[channel]
            logger.info("adapter_unregistered", channel=channel.value)

    def get_adapter(self, channel: ChannelType) -> Optional[BaseChannelAdapter]:
        """Get adapter for a specific channel type."""
        return self._adapters.get(channel)

    @property
    def registered_channels(self) -> List[str]:
        """List of registered channel names."""
        return [ch.value for ch in self._adapters.keys()]

    @property
    def all_adapters(self) -> Dict[ChannelType, BaseChannelAdapter]:
        """All registered adapters."""
        return dict(self._adapters)

    async def initialize_all(self) -> None:
        """Initialize all registered adapters."""
        for channel, adapter in self._adapters.items():
            try:
                await adapter.initialize()
                logger.info(
                    "adapter_initialized",
                    channel=channel.value,
                )
            except Exception as e:
                logger.error(
                    "adapter_init_failed",
                    channel=channel.value,
                    error=str(e),
                )

    async def shutdown_all(self) -> None:
        """Shutdown all registered adapters."""
        for channel, adapter in self._adapters.items():
            try:
                await adapter.shutdown()
                logger.info("adapter_shutdown", channel=channel.value)
            except Exception as e:
                logger.error(
                    "adapter_shutdown_failed",
                    channel=channel.value,
                    error=str(e),
                )

    async def resolve_worker_id(
        self,
        channel: ChannelType,
        channel_user_id: str,
    ) -> Optional[str]:
        """
        Resolve a channel-specific user ID to a canonical worker ID.

        For example, a WhatsApp phone number → worker UUID.
        """
        # Check cache first
        cache_key = f"{channel.value}:{channel_user_id}"
        if cache_key in self._worker_channel_map.get(channel.value, {}):
            return self._worker_channel_map[channel.value][cache_key]

        # Try adapter-specific resolution
        adapter = self.get_adapter(channel)
        if adapter and hasattr(adapter, "resolve_worker_id"):
            resolved = await adapter.resolve_worker_id(channel_user_id)
            if resolved:
                # Cache the mapping
                if channel.value not in self._worker_channel_map:
                    self._worker_channel_map[channel.value] = {}
                self._worker_channel_map[channel.value][cache_key] = resolved
                return resolved

        return None

    def link_worker_channel(
        self,
        worker_id: str,
        channel: ChannelType,
        channel_user_id: str,
    ) -> None:
        """
        Explicitly link a worker ID to a channel-specific user ID.
        Called during onboarding or verification.
        """
        if channel.value not in self._worker_channel_map:
            self._worker_channel_map[channel.value] = {}
        cache_key = f"{channel.value}:{channel_user_id}"
        self._worker_channel_map[channel.value][cache_key] = worker_id
        logger.info(
            "worker_channel_linked",
            worker_id=worker_id,
            channel=channel.value,
            channel_user_id=channel_user_id,
        )

    def get_stats(self) -> Dict[str, object]:
        """Get registry statistics."""
        return {
            "registered_channels": self.registered_channels,
            "adapter_count": len(self._adapters),
            "linked_workers": sum(
                len(m) for m in self._worker_channel_map.values()
            ),
        }
