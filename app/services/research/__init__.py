"""
Research Methodology & Statistical Quality Framework for Biashara Intelligence.

Grounded in Valentine's Economics & Statistics degree:
- ECO 315: Research Methods → Research design, sampling, data collection
- STA 343: Experimental Design → Controlled experiments, factorial designs, RCTs
- STA 346: Statistical Quality Control → Process control charts, acceptance sampling
- STA 342: Test of Hypothesis → Significance testing, Type I/II errors, power analysis
- ECO 202/203: Economic Statistics → Data collection, cleaning, validation
- STA 245: Social & Economic Statistics for National Planning → Official statistics standards
"""

from app.services.research.data_quality import (
    DataQualityFramework,
    SPCChart,
    OutlierDetector,
    DataValidator,
)
from app.services.research.hypothesis_testing import (
    HypothesisTester,
    MultipleTestingCorrection,
    SignificanceReport,
)
from app.services.research.experimental_design import (
    ExperimentDesigner,
    ABTestFramework,
    PowerAnalyzer,
)
from app.services.research.confidence_intervals import (
    ConfidenceIntervalCalculator,
    BootstrapCI,
)
from app.services.research.sampling import (
    SamplingEngine,
    SampleSizeCalculator,
)

__all__ = [
    "DataQualityFramework",
    "SPCChart",
    "OutlierDetector",
    "DataValidator",
    "HypothesisTester",
    "MultipleTestingCorrection",
    "SignificanceReport",
    "ExperimentDesigner",
    "ABTestFramework",
    "PowerAnalyzer",
    "ConfidenceIntervalCalculator",
    "BootstrapCI",
    "SamplingEngine",
    "SampleSizeCalculator",
]
