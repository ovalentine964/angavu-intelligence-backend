"""
Intelligence product services for the cloud intelligence platform.

Services (Original 6):
- SokoPulseService: FMCG demand forecasting
- BiasharaPulseService: Government MSME Activity Index
- AlamaScoreService: Bank credit scoring (300-850)
- JamiiInsightsService: NGO financial inclusion
- TaxBaseService: Government revenue estimation
- DistributionGapService: FMCG market coverage gaps

Services (Phase 1 — New):
- GDPEstimatorService: Real-time informal GDP estimation
- InflationTrackerService: Daily price indices across 47 counties

Services (Phase 2 — New):
- GivingInsightsService: Financial giving and tithing patterns
- LoanIntelligenceService: Loan purpose verification and repayment tracking
"""

from app.services.intelligence.soko_pulse import SokoPulseService
from app.services.intelligence.biashara_pulse import BiasharaPulseService
from app.services.intelligence.alama_score import AlamaScoreService
from app.services.intelligence.jamii_insights import JamiiInsightsService
from app.services.intelligence.tax_base import TaxBaseService
from app.services.intelligence.distribution_gap import DistributionGapService
from app.services.intelligence.gdp_estimator import GDPEstimatorService
from app.services.intelligence.inflation_tracker import InflationTrackerService
from app.services.intelligence.giving_insights import GivingInsightsService
from app.services.intelligence.loan_intelligence import LoanIntelligenceService
from app.services.intelligence.markov_chains import MarkovChainAnalyzer, OptimizationEngine, markov_analyzer, optimization_engine
from app.services.intelligence.health_economics import HealthEconomicsEngine
from app.services.intelligence.african_development import AfricanDevelopmentEngine
from app.services.intelligence.business_cycles import BusinessCycleAnalyzer
from app.services.intelligence.measure_theory import (
    ProbabilitySpace,
    ConditionalExpectation,
    ConvergenceTheorems,
    MartingaleAnalyzer,
)

__all__ = [
    "SokoPulseService",
    "BiasharaPulseService",
    "AlamaScoreService",
    "JamiiInsightsService",
    "TaxBaseService",
    "DistributionGapService",
    "GDPEstimatorService",
    "InflationTrackerService",
    "GivingInsightsService",
    "LoanIntelligenceService",
    "MarkovChainAnalyzer",
    "OptimizationEngine",
    "markov_analyzer",
    "optimization_engine",
    "HealthEconomicsEngine",
    "AfricanDevelopmentEngine",
    "BusinessCycleAnalyzer",
    "ProbabilitySpace",
    "ConditionalExpectation",
    "ConvergenceTheorems",
    "MartingaleAnalyzer",
]
