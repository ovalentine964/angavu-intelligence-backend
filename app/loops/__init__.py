"""
Angavu Loop Systems — Domain-Specific Goal-Driven Loops.

Each loop wraps a Angavu feature as a DeerFlow goal:
- TitheLoop          — Record → Analyze → Encourage
- GoalProgressLoop   — Track → Predict → Nudge
- LoanLoop           — Record → Verify → Alert
- IntelligenceLoop   — Collect → Analyze → Deliver

These loops USE DeerFlow's existing infrastructure:
- GoalState (goal.py)       — goal lifecycle management
- GoalEvaluation            — satisfied/blocker/reason
- ThreadState               — state management
- Journal (journal.py)      — decision tracking
- Reflection (resolvers.py) — self-improvement
- LoopDetection             — prevents infinite loops

They do NOT rewrite any DeerFlow primitives.
"""

from app.loops.config import BiasharaLoopConfig, get_loop_config, register_loop_config
from app.loops.goal_loop import GoalProgressLoop
from app.loops.intelligence_loop import IntelligenceLoop
from app.loops.loan_loop import LoanLoop
from app.loops.tithe_loop import TitheLoop

__all__ = [
    "BiasharaLoopConfig",
    "GoalProgressLoop",
    "IntelligenceLoop",
    "LoanLoop",
    "TitheLoop",
    "get_loop_config",
    "register_loop_config",
]
