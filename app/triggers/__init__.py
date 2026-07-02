"""
Triggers — Factor 11: Trigger from Anywhere.

Multiple entry points for agent activation:
- WhatsApp Business API
- USSD menus
- SMS gateway
- Voice calls

Each trigger normalizes input to a standard intent format
and routes to the appropriate agent.
"""

from app.triggers.base import BaseTrigger, TriggerIntent, TriggerResponse
from app.triggers.whatsapp_trigger import WhatsAppTrigger
from app.triggers.ussd_trigger import USSDTrigger
from app.triggers.sms_trigger import SMSTrigger
from app.triggers.voice_trigger import VoiceTrigger

__all__ = [
    "BaseTrigger",
    "TriggerIntent",
    "TriggerResponse",
    "WhatsAppTrigger",
    "USSDTrigger",
    "SMSTrigger",
    "VoiceTrigger",
]
