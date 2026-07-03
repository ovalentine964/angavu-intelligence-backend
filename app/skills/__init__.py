"""
Angavu Intelligence — Skills Module

Each skill maps a university course unit (from Valentine Owuor's
BSc Economics & Statistics, Masinde Muliro University) into an
executable AI capability for Msaidizi and Angavu Intelligence.

The degree IS the product specification — 42 units, 545,000+ words
mapped to intelligence products.
"""

from app.skills.microfinance_analyzer import MicrofinanceAnalyzer
from app.skills.time_series_forecaster import TimeSeriesForecasterSkill
from app.skills.statistical_estimator import StatisticalEstimator
from app.skills.econometric_modeler import EconometricModeler
from app.skills.worker_segmenter import WorkerSegmenter
from app.skills.nonparametric_analyzer import NonparametricAnalyzer

__all__ = [
    "MicrofinanceAnalyzer",
    "TimeSeriesForecasterSkill",
    "StatisticalEstimator",
    "EconometricModeler",
    "WorkerSegmenter",
    "NonparametricAnalyzer",
]
