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
from .dialect_training_pipeline import DialectTrainingPipeline, TrainingConfig, create_pipeline
from .intent_classifier_training import IntentClassifierTrainer, train_intent_classifier
from .entity_extractor_training import EntityExtractorTrainer, train_entity_extractor
from .federated_dialect_learning import FederatedDialectLearning, create_federated_learner
from .dialect_evaluation import DialectEvaluator, evaluate_dialect
from .training_data_validator import TrainingDataValidator, validate_training_data

__all__ = [
    "DialectIngestService",
    "DialectClusterEngine",
    "VocabularyAggregator",
    "DialectAdapterRegistry",
    "DialectTrainingPipeline",
    "TrainingConfig",
    "create_pipeline",
    "IntentClassifierTrainer",
    "train_intent_classifier",
    "EntityExtractorTrainer",
    "train_entity_extractor",
    "FederatedDialectLearning",
    "create_federated_learner",
    "DialectEvaluator",
    "evaluate_dialect",
    "TrainingDataValidator",
    "validate_training_data",
]
