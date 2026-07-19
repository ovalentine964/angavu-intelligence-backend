"""
Research Methodology & Statistical Quality Framework for Angavu Intelligence.

Grounded in Valentine's Economics & Statistics degree:
- ECO 315: Research Methods → Research design, sampling, data collection
- STA 343: Experimental Design → Controlled experiments, factorial designs, RCTs
- STA 346: Statistical Quality Control → Process control charts, acceptance sampling
- STA 342: Test of Hypothesis → Significance testing, Type I/II errors, power analysis
- ECO 202/203: Economic Statistics → Data collection, cleaning, validation
- STA 245: Social & Economic Statistics for National Planning → Official statistics standards
"""

from app.services.research.confidence_intervals import (
    BootstrapCI,
    ConfidenceIntervalCalculator,
)
from app.services.research.data_quality import (
    DataQualityFramework,
    DataValidator,
    OutlierDetector,
    SPCChart,
)
from app.services.research.experimental_design import (
    ABTestFramework,
    ExperimentDesigner,
    PowerAnalyzer,
)
from app.services.research.hypothesis_testing import (
    HypothesisTester,
    MultipleTestingCorrection,
    SignificanceReport,
)
from app.services.research.sampling import (
    SampleSizeCalculator,
    SamplingEngine,
)

__all__ = [
    "ABTestFramework",
    "BootstrapCI",
    "ConfidenceIntervalCalculator",
    "DataQualityFramework",
    "DataValidator",
    "ExperimentDesigner",
    "HypothesisTester",
    "MultipleTestingCorrection",
    "OutlierDetector",
    "PowerAnalyzer",
    "SPCChart",
    "SampleSizeCalculator",
    "SamplingEngine",
    "SignificanceReport",
]
