"""
Channel Adapters — Normalize channel-specific data into UnifiedMessage.

Each adapter converts raw data from its channel (WhatsApp JIDs, SMS numbers,
voice DTMF, app payloads) into a common format the gateway can process.
"""

from app.channels.adapters.base import (
    BaseChannelAdapter,
    ChannelResponse,
    ChannelType,
    UnifiedMessage,
)
from app.channels.adapters.app_adapter import AppAdapter
from app.channels.adapters.whatsapp_adapter import WhatsAppAdapter
from app.channels.adapters.sms_adapter import SMSAdapter
from app.channels.adapters.voice_adapter import VoiceAdapter

__all__ = [
    "BaseChannelAdapter",
    "ChannelResponse",
    "ChannelType",
    "UnifiedMessage",
    "AppAdapter",
    "WhatsAppAdapter",
    "SMSAdapter",
    "VoiceAdapter",
]
