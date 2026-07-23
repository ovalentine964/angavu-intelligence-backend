"""
Unified Intelligence Engine — direct service calls, no agent indirection.

Architecture: arch_backend.md §4.1
"""
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.intelligence.soko_pulse import SokoPulseService
from app.services.intelligence.alama_score import AlamaScoreService
from app.services.intelligence.angavu_pulse import AngavuPulseService
from app.services.intelligence.jamii_insights import JamiiInsightsService

logger = structlog.get_logger(__name__)


class IntelligenceEngine:
    """Central intelligence generation engine — replaces agent-based generation."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.soko_pulse = SokoPulseService(db)
        self.alama_score = AlamaScoreService(db)
        self.angavu_pulse = AngavuPulseService(db)
        self.jamii_insights = JamiiInsightsService(db)

    async def generate_soko_pulse(self, **kwargs):
        return await self.soko_pulse.generate_demand_forecast(**kwargs)

    async def generate_alama_score(self, **kwargs):
        return await self.alama_score.compute_score(**kwargs)

    async def generate_angavu_pulse(self, **kwargs):
        return await self.angavu_pulse.generate_pulse(**kwargs)

    async def generate_jamii_insights(self, **kwargs):
        return await self.jamii_insights.generate_insights(**kwargs)

    async def compare_regions(self, regions: list[str], **kwargs):
        return await self.angavu_pulse.compare_regions(regions, **kwargs)
