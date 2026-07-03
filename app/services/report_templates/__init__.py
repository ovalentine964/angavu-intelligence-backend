"""
Report generation templates for intelligence products.

Each template defines the structure and format for generating
PDF/HTML reports from intelligence product data.
"""

from app.services.report_templates.intelligence_report import IntelligenceReportGenerator
from app.services.report_templates.audience_reports import AudienceReportGenerator, AudienceType

__all__ = ["IntelligenceReportGenerator", "AudienceReportGenerator", "AudienceType"]
