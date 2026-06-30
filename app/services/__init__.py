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
