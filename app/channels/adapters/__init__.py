"""
Channel Adapters — Normalize channel-specific data into UnifiedMessage.

Each adapter converts raw data from its channel (WhatsApp JIDs, SMS numbers,
voice DTMF, app payloads) into a common format the gateway can process.
"""

from app.channels.adapters.app_adapter import AppAdapter
from app.channels.adapters.base import (
    BaseChannelAdapter,
    ChannelResponse,
    ChannelType,
    UnifiedMessage,
)
from app.channels.adapters.http_api_adapter import HttpApiAdapter
from app.channels.adapters.sms_adapter import SMSAdapter
from app.channels.adapters.telegram_adapter import TelegramAdapter
from app.channels.adapters.voice_adapter import VoiceAdapter
from app.channels.adapters.whatsapp_adapter import WhatsAppAdapter

__all__ = [
    "AppAdapter",
    "BaseChannelAdapter",
    "ChannelResponse",
    "ChannelType",
    "HttpApiAdapter",
    "SMSAdapter",
    "TelegramAdapter",
    "UnifiedMessage",
    "VoiceAdapter",
    "WhatsAppAdapter",
]
