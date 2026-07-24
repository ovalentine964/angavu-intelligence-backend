"""
WhatsApp Business Reports — Bank-Ready Report Generation via WhatsApp.

Enables informal workers to generate professional business reports
they can present to banks (Equity, KCB, Co-op) and MFIs for loan
applications, all triggered from a simple WhatsApp message.

Usage from WhatsApp:
    "ripoti"       → Generate and send business report (Swahili)
    "report"       → Generate and send business report (English)
    "score"        → Send Alama Score summary
    "benki"        → Bank-ready formal report with QR verification
    "ripoti ya benki" → Same as "benki"

A mama mboga can text "nipatie ripoti ya benki" and walk into
Equity Bank with a professional PDF showing her business flow.
"""

from .report_generator import WhatsAppReportGenerator
from .templates import ReportTemplate, TemplateType
from .whatsapp_handler import WhatsAppReportHandler

__all__ = [
    "WhatsAppReportGenerator",
    "WhatsAppReportHandler",
    "ReportTemplate",
    "TemplateType",
]
