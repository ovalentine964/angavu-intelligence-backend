"""
Governance Swarm (Swarm 5) — Agent oversight, compliance, and audit.

Agents:
    AuditAgent      — Decision audit trail, explainability
    EthicsAgent     — Ethical boundary enforcement, bias detection
    PrivacyAgent    — Data privacy compliance (GDPR, Kenya DPA)

The ComplianceAgent (already in implementations_extra) is also part
of this swarm at the factory level but lives in its original module.
"""

from app.agents.governance.audit import AuditAgent
from app.agents.governance.ethics import EthicsAgent
from app.agents.governance.privacy import PrivacyAgent

__all__ = [
    "AuditAgent",
    "EthicsAgent",
    "PrivacyAgent",
]
