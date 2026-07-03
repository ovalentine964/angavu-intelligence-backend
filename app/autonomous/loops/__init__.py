"""
Autonomous Self-Improvement Loops for Angavu Intelligence.

Domain-specific Reflexion loops that continuously improve:

1. ContentQualityLoop     — Generate → Evaluate → Refine content
2. CustomerSatisfactionLoop — Feedback → Sentiment → Adjust service
3. RevenueOptimizationLoop  — Metrics → Test pricing → Auto-adjust

Each loop wraps the ReflexionEngine with domain-specific
executor, critic, and reviser implementations.
"""

from app.autonomous.loops.content_quality import ContentQualityLoop
from app.autonomous.loops.customer_satisfaction import CustomerSatisfactionLoop
from app.autonomous.loops.revenue_optimization import RevenueOptimizationLoop

__all__ = [
    "ContentQualityLoop",
    "CustomerSatisfactionLoop",
    "RevenueOptimizationLoop",
]
