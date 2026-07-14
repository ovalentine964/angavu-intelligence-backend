"""
Msaidizi / Angavu Intelligence — Report Services
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
    MarkovChainAnalyzer,
    OptimizationEngine,
    HealthEconomicsEngine,
    AfricanDevelopmentEngine,
    BusinessCycleAnalyzer,
    ProbabilitySpace,
    ConditionalExpectation,
    ConvergenceTheorems,
    MartingaleAnalyzer,
)

__all__ += [
    "SokoPulseService",
    "BiasharaPulseService",
    "AlamaScoreService",
    "JamiiInsightsService",
    "TaxBaseService",
    "DistributionGapService",
    "MarkovChainAnalyzer",
    "OptimizationEngine",
    "HealthEconomicsEngine",
    "AfricanDevelopmentEngine",
    "BusinessCycleAnalyzer",
    "ProbabilitySpace",
    "ConditionalExpectation",
    "ConvergenceTheorems",
    "MartingaleAnalyzer",
]

# Quality control (STA 346)
from app.services.quality_control import SPCChart, DataQualityMonitor

__all__ += ["SPCChart", "DataQualityMonitor"]

# Mathematical foundations (MAT 101/121/124)
from app.services.math_foundation import AlgebraFoundations, DifferentialCalculus, IntegralCalculus

__all__ += ["AlgebraFoundations", "DifferentialCalculus", "IntegralCalculus"]

# Audience-aware reports (BCB 108)
from app.services.report_templates.audience_reports import AudienceReportGenerator, AudienceType

__all__ += ["AudienceReportGenerator", "AudienceType"]

# Training multi-agentic loop
from app.services.training import TrainingLoop
from app.services.nvidia_client import NVIDIAClient
from app.services.self_evolution import SelfEvolutionService

__all__ += [
    "TrainingLoop",
    "NVIDIAClient",
    "SelfEvolutionService",
]

# Hermes Agent Protocol
from app.services.hermes_service import HermesService, create_hermes_service

__all__ += [
    "HermesService",
    "create_hermes_service",
]

# ML Layer — XGBoost prediction services
try:
    from app.services.ml import FeatureEngineer, XGBoostService, ModelTrainer
    __all__ += ["FeatureEngineer", "XGBoostService", "ModelTrainer"]
except ImportError:
    pass  # ML dependencies not installed
