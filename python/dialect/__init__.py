"""
Dialect Aggregation Service — Backend service for aggregating dialect signals
from Msaidizi devices and building shared dialect models.

Part of the Angavu Intelligence Backend.

Receives anonymized dialect signals from devices, clusters workers by dialect
similarity, aggregates vocabulary and phonetic patterns, and manages
dialect-specific LoRA adapter distribution.

Privacy guarantees:
- Never receives raw audio or full transcripts
- Differential privacy on all aggregated outputs
- Minimum cohort size of 100 workers per cluster
- Worker identity is pseudonymous and rotated weekly
"""

from .ingest import DialectIngestService
from .clustering import DialectClusterEngine
from .vocabulary import VocabularyAggregator
from .registry import DialectAdapterRegistry

__all__ = [
    "DialectIngestService",
    "DialectClusterEngine",
    "VocabularyAggregator",
    "DialectAdapterRegistry",
]
