"""
Training Multi-Agentic Loop — Self-improving model pipeline.

8 agents orchestrate a continuous training cycle:
    Data Collector → Data Curator → Model Trainer →
    Model Evaluator → Experiment Runner → Model Deployer →
    Quality Monitor → Feedback Processor

7 phases:
    Signal Capture → Data Pipeline → Training →
    Evaluation → Experiment → Deployment → Monitoring

Every worker interaction is a training signal. The loop never stops.
"""

from .loop import TrainingLoop

__all__ = ["TrainingLoop"]
