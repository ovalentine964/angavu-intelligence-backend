"""
Channels Domain — /api/v1/channels/*

Aggregates:
    - WhatsApp Webhook          (app.api.whatsapp)
    - WhatsApp Connection Mgmt  (app.api.v1.whatsapp_connection)
    - Multi-Channel Triggers    (app.api.trigger_router)
    - Channel Health            (app.api.channel_health)
    - Multi-Channel Gateway     (app.api.v1.gateway)
"""

from fastapi import APIRouter

from app.api.channel_health import router as _ch_health
from app.api.trigger_router import router as _triggers
from app.api.v1.gateway import router as _gateway
from app.api.v1.whatsapp_connection import router as _wa_conn
from app.api.whatsapp import router as _wa_webhook

channels_router = APIRouter(tags=["Channels"])
channels_router.include_router(_wa_webhook)
channels_router.include_router(_wa_conn)
channels_router.include_router(_triggers)
channels_router.include_router(_ch_health)
channels_router.include_router(_gateway)
