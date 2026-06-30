"""
Intelligence product services for the 6 cloud intelligence products.

Services:
- SokoPulseService: FMCG demand forecasting
- BiasharaPulseService: Government MSME Activity Index
- AlamaScoreService: Bank credit scoring (300-850)
- JamiiInsightsService: NGO financial inclusion
- TaxBaseService: Government revenue estimation
- DistributionGapService: FMCG market coverage gaps
"""

from app.services.intelligence.soko_pulse import SokoPulseService
from app.services.intelligence.biashara_pulse import BiasharaPulseService
from app.services.intelligence.alama_score import AlamaScoreService
from app.services.intelligence.jamii_insights import JamiiInsightsService
from app.services.intelligence.tax_base import TaxBaseService
from app.services.intelligence.distribution_gap import DistributionGapService

__all__ = [
    "SokoPulseService",
    "BiasharaPulseService",
    "AlamaScoreService",
    "JamiiInsightsService",
    "TaxBaseService",
    "DistributionGapService",
]
