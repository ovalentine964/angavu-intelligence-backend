"""
Msaidizi / Angavu Intelligence — Report Services
Voice-based AI CFO for Africa's informal economy.
"""

from .comparison_engine import ComparisonEngine
from .drift_detector import CUSUMDriftDetector, ModelDriftMonitor
from .fallback_handler import FallbackHandler, get_fallback_handler
from .health_score import BusinessHealthScorer
from .heckman_correction import HeckmanCorrector
from .model_router import ModelRouter, get_model_router
from .provider_registry import ProviderRegistry, get_provider_registry
from .report_generator import ReportGenerator
from .report_scheduler import ReportScheduler
from .seasonal_analyzer import SeasonalAnalyzer
from .token_compressor import TokenCompressor, get_token_compressor
from .whatsapp_charts import BarChart, CashFlowDiagram, Heatmap, ProgressBar, Sparkline, TrendLine

__all__ = [
    "BarChart",
    "BusinessHealthScorer",
    "CUSUMDriftDetector",
    "CashFlowDiagram",
    "ComparisonEngine",
    "FallbackHandler",
    "Heatmap",
    "HeckmanCorrector",
    "ModelDriftMonitor",
    "ModelRouter",
    "ProgressBar",
    "ProviderRegistry",
    "ReportGenerator",
    "ReportScheduler",
    "SeasonalAnalyzer",
    "Sparkline",
    "TokenCompressor",
    "TrendLine",
    "get_fallback_handler",
    "get_model_router",
    "get_provider_registry",
    "get_token_compressor",
]

# Intelligence product services
from app.services.intelligence import (
    AfricanDevelopmentEngine,
    AlamaScoreService,
    BiasharaPulseService,
    BusinessCycleAnalyzer,
    ConditionalExpectation,
    ConvergenceTheorems,
    DistributionGapService,
    HealthEconomicsEngine,
    JamiiInsightsService,
    MarkovChainAnalyzer,
    MartingaleAnalyzer,
    OptimizationEngine,
    ProbabilitySpace,
    SokoPulseService,
    TaxBaseService,
)

__all__ += [
    "AfricanDevelopmentEngine",
    "AlamaScoreService",
    "BiasharaPulseService",
    "BusinessCycleAnalyzer",
    "ConditionalExpectation",
    "ConvergenceTheorems",
    "DistributionGapService",
    "HealthEconomicsEngine",
    "JamiiInsightsService",
    "MarkovChainAnalyzer",
    "MartingaleAnalyzer",
    "OptimizationEngine",
    "ProbabilitySpace",
    "SokoPulseService",
    "TaxBaseService",
]

# Quality control (STA 346)
from app.services.quality_control import DataQualityMonitor, SPCChart

__all__ += ["DataQualityMonitor", "SPCChart"]

# Mathematical foundations (MAT 101/121/124)
from app.services.math_foundation import AlgebraFoundations, DifferentialCalculus, IntegralCalculus

__all__ += ["AlgebraFoundations", "DifferentialCalculus", "IntegralCalculus"]

# Audience-aware reports (BCB 108)
from app.services.report_templates.audience_reports import AudienceReportGenerator, AudienceType

__all__ += ["AudienceReportGenerator", "AudienceType"]

# Training multi-agentic loop
from app.services.nvidia_client import NVIDIAClient
from app.services.self_evolution import SelfEvolutionService
from app.services.training import TrainingLoop

__all__ += [
    "NVIDIAClient",
    "SelfEvolutionService",
    "TrainingLoop",
]

# Hermes Agent Protocol
from app.services.hermes_service import HermesService, create_hermes_service

__all__ += [
    "HermesService",
    "create_hermes_service",
]

# ML Layer — XGBoost prediction services
try:
    from app.services.ml import FeatureEngineer, ModelTrainer, XGBoostService
    __all__ += ["FeatureEngineer", "ModelTrainer", "XGBoostService"]
except ImportError:
    pass  # ML dependencies not installed
