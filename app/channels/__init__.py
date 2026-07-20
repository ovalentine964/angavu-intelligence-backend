"""
Multi-Channel Gateway — OpenClaw Pattern for Angavu Intelligence.

One agent system, multiple channels, same session.
Workers can switch between Msaidizi app, WhatsApp, SMS, and voice
without losing context or conversation history.

Architecture:
    Channel Adapters → MultiChannelGateway → SessionSync → Intelligence Pipeline

Key insight from OpenClaw: sessions are keyed by WORKER, not by CHANNEL.
"""

from app.channels.failover import FailoverManager
from app.channels.gateway import MultiChannelGateway
from app.channels.health_monitor import ChannelHealthMonitor
from app.channels.registry import ChannelRegistry
from app.channels.session_sync import SessionSync

__all__ = [
    "ChannelRegistry",
    "FailoverManager",
    "ChannelHealthMonitor",
    "MultiChannelGateway",
    "SessionSync",
]
