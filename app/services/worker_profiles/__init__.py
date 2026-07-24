"""
Worker Profiles — Msaidizi / Angavu Intelligence

Defines 25 worker types in Kenya's informal economy with their
specific needs, financial products, and operational realities.

Modules:
- profiles: Worker type definitions and registry
- recommendations: Type-specific recommendations engine
- sector_intelligence: Sector-level insights and benchmarks
"""

from .profiles import (
    FinancialProduct,
    IncomeRange,
    KeyMetric,
    OperatingCosts,
    RiskLevel,
    SeasonalityPattern,
    WorkerProfile,
    WorkerSector,
    get_all_profiles,
    get_profile,
    get_profiles_by_sector,
    get_type_ids,
    search_profiles,
)

from .recommendations import (
    FinancialFit,
    InsightRule,
    Recommendation,
    RecommendationCategory,
    RecommendationEngine,
    RecommendationPriority,
    TrackingRecommendation,
    get_recommendation_engine,
)

from .sector_intelligence import (
    BestPractice,
    MarketTrend,
    PriceBenchmark,
    SectorChallenge,
    SectorIntelligence,
    SeasonalPattern as SectorSeasonalPattern,
    get_all_sector_intelligence,
    get_best_practices_for_type,
    get_price_benchmarks_for_type,
    get_seasonal_forecast,
    get_sector_for_type,
    get_sector_intelligence,
)

__all__ = [
    # Profiles
    "WorkerProfile", "WorkerSector", "IncomeRange", "OperatingCosts",
    "KeyMetric", "FinancialProduct", "RiskLevel", "SeasonalityPattern",
    "get_all_profiles", "get_profile", "get_profiles_by_sector",
    "get_type_ids", "search_profiles",
    # Recommendations
    "RecommendationEngine", "Recommendation", "RecommendationCategory",
    "RecommendationPriority", "TrackingRecommendation", "InsightRule",
    "FinancialFit", "get_recommendation_engine",
    # Sector Intelligence
    "SectorIntelligence", "PriceBenchmark", "SectorChallenge",
    "BestPractice", "MarketTrend", "SectorSeasonalPattern",
    "get_all_sector_intelligence", "get_sector_intelligence",
    "get_sector_for_type", "get_price_benchmarks_for_type",
    "get_seasonal_forecast", "get_best_practices_for_type",
]
