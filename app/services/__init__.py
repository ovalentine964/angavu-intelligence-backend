"""
Msaidizi / Biashara AI — Report Services
Voice-based AI CFO for Africa's informal economy.
"""

from .report_generator import ReportGenerator
from .report_scheduler import ReportScheduler
from .health_score import BusinessHealthScorer
from .seasonal_analyzer import SeasonalAnalyzer
from .comparison_engine import ComparisonEngine
from .heckman_correction import HeckmanCorrector
from .drift_detector import CUSUMDriftDetector, ModelDriftMonitor
from .whatsapp_charts import BarChart, Sparkline, Heatmap, CashFlowDiagram, ProgressBar, TrendLine
from .provider_registry import ProviderRegistry, get_provider_registry
from .token_compressor import TokenCompressor, get_token_compressor
from .fallback_handler import FallbackHandler, get_fallback_handler
from .model_router import ModelRouter, get_model_router

__all__ = [
    "ReportGenerator",
    "ReportScheduler",
    "BusinessHealthScorer",
    "SeasonalAnalyzer",
    "ComparisonEngine",
    "HeckmanCorrector",
    "CUSUMDriftDetector",
    "ModelDriftMonitor",
    "BarChart",
    "Sparkline",
    "Heatmap",
    "CashFlowDiagram",
    "ProgressBar",
    "TrendLine",
    "ProviderRegistry",
    "get_provider_registry",
    "TokenCompressor",
    "get_token_compressor",
    "FallbackHandler",
    "get_fallback_handler",
    "ModelRouter",
    "get_model_router",
]

# Intelligence product services
from app.services.intelligence import (
    SokoPulseService,
    BiasharaPulseService,
    AlamaScoreService,
    JamiiInsightsService,
    TaxBaseService,
    DistributionGapService,
)

__all__ += [
    "SokoPulseService",
    "BiasharaPulseService",
    "AlamaScoreService",
    "JamiiInsightsService",
    "TaxBaseService",
    "DistributionGapService",
]

# Training multi-agentic loop
from app.services.training import TrainingLoop
from app.services.nvidia_client import NVIDIAClient
from app.services.self_evolution import SelfEvolutionService

__all__ += [
    "TrainingLoop",
    "NVIDIAClient",
    "SelfEvolutionService",
]
