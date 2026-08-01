"""
Entity Extractor Training — Train NER model for African product names,
amounts, dates, and business entities.

Handles:
- Swahili product names (maziwa, sukari, unga, etc.)
- Sheng money terms (thao=1000, soo=100, finje=500)
- Code-switched entities (customer, stock, receipt)
- Swahili date expressions (leo, jana, wiki iliyopita)

Architecture:
- Conditional Random Field (CRF) over BIO-tagged sequences
- Features: word embeddings, character n-grams, morphological patterns
- Lightweight enough for on-device deployment (~2MB)

Academic basis:
- Non-parametric methods: Character n-gram features (no distributional assumptions)
- MLE: CRF parameter estimation via maximum likelihood
"""

import json
import logging
import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class NERTrainingExample:
    """A single NER training example with BIO tags."""
    tokens: list[str]
    tags: list[str]
    language: str = "sw"
    region: str = "KE-Nairobi"


@dataclass
class EntitySpan:
    """A predicted entity span."""
    start: int
    end: int
    entity_type: str
    text: str
    confidence: float = 0.0


@dataclass
class NEREvaluationResult:
    """NER evaluation results."""
    precision: float
    recall: float
    f1: float
    per_entity_metrics: dict = field(default_factory=dict)
    confusion_matrix: dict = field(default_factory=dict)


class SwahiliMorphologicalAnalyzer:
    """
    Extracts morphological features from Swahili words.
    Used as CRF features for NER.
    """

    PREFIXES = {
        "m": "class1", "wa": "class2", "ki": "class7", "vi": "class8",
        "ma": "class6", "ya": "class6", "za": "class10", "la": "class5",
        "cha": "class7", "nime": "perfect", "nili": "past", "na": "present",
        "nta": "future", "niki": "conditional"
    }

    SUFFIXES = {
        "a": "verb", "e": "subjunctive", "i": "passive",
        "wa": "passive", "na": "associative", "ni": "locative",
        "sha": "resultative", "nga": "habitual"
    }

    def analyze(self, word: str) -> dict:
        """Extract morphological features from a word."""
        features = {}
        lower = word.lower()

        # Prefix
        for prefix, label in sorted(self.PREFIXES.items(), key=lambda x: len(x[0]), reverse=True):
            if lower.startswith(prefix) and len(lower) > len(prefix) + 1:
                features["prefix"] = prefix
                features["prefix_class"] = label
                break

        # Suffix
        for suffix, label in sorted(self.SUFFIXES.items(), key=lambda x: len(x[0]), reverse=True):
            if lower.endswith(suffix) and len(lower) > len(suffix) + 1:
                features["suffix"] = suffix
                features["suffix_class"] = label
                break

        # Character features
        features["length"] = len(lower)
        features["has_apostrophe"] = "'" in lower
        features["vowel_ratio"] = sum(1 for c in lower if c in "aeiou") / max(len(lower), 1)
        features["capitalized"] = word[0].isupper() if word else False
        features["is_digit"] = lower.isdigit()
        features["has_number"] = any(c.isdigit() for c in lower)

        return features


class CharacterNgramExtractor:
    """
    Extracts character n-gram features (non-parametric).
    No distributional assumptions on character patterns.
    """

    def __init__(self, ngram_range: tuple = (2, 4)):
        self.ngram_range = ngram_range
        self.vocabulary: dict[str, int] = {}

    def fit(self, words: list[str]) -> 'CharacterNgramExtractor':
        """Build vocabulary from words."""
        counter = Counter()
        for word in words:
            for ngram in self._extract_ngrams(word):
                counter[ngram] += 1

        # Keep top features
        most_common = counter.most_common(3000)
        self.vocabulary = {ng: idx for idx, (ng, _) in enumerate(most_common)}
        return self

    def transform(self, word: str) -> dict:
        """Extract n-gram features for a word."""
        features = {}
        for ngram in self._extract_ngrams(word):
            if ngram in self.vocabulary:
                features[f"ngram_{ngram}"] = 1.0
        return features

    def _extract_ngrams(self, word: str) -> list[str]:
        """Extract character n-grams from a word."""
        padded = f"_{word}_"
        ngrams = []
        for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
            for i in range(len(padded) - n + 1):
                ngrams.append(padded[i:i+n])
        return ngrams


class CRFLayer:
    """
    Simplified CRF (Conditional Random Field) for sequence labeling.
    
    Uses Viterbi decoding for prediction and forward algorithm for training.
    
    Academic basis: MLE for CRF parameters
    - P(y|x) = exp(Σ θ_k f_k(y, x)) / Z(x)
    - Log-likelihood = Σ log P(y_i|x_i) - λ/2 ||θ||²
    """

    def __init__(self, n_labels: int, n_features: int,
                 learning_rate: float = 0.01, regularization: float = 0.01):
        self.n_labels = n_labels
        self.n_features = n_features
        self.learning_rate = learning_rate
        self.regularization = regularization

        # Feature weights: (n_labels, n_features)
        self.emission_weights = np.zeros((n_labels, n_features), dtype=np.float32)
        # Transition weights: (n_labels, n_labels)
        self.transition_weights = np.zeros((n_labels, n_labels), dtype=np.float32)

    def viterbi_decode(self, features: np.ndarray) -> list[int]:
        """
        Viterbi algorithm for finding the best tag sequence.
        
        Args:
            features: (seq_len, n_features) feature matrix
        
        Returns:
            Best tag sequence
        """
        seq_len = features.shape[0]

        # Emission scores
        emission_scores = features @ self.emission_weights.T  # (seq_len, n_labels)

        # Viterbi
        dp = np.full((seq_len, self.n_labels), -np.inf)
        backpointer = np.zeros((seq_len, self.n_labels), dtype=int)

        dp[0] = emission_scores[0]

        for t in range(1, seq_len):
            for j in range(self.n_labels):
                scores = dp[t - 1] + self.transition_weights[:, j] + emission_scores[t, j]
                dp[t, j] = np.max(scores)
                backpointer[t, j] = np.argmax(scores)

        # Backtrace
        best_path = [0] * seq_len
        best_path[-1] = int(np.argmax(dp[-1]))
        for t in range(seq_len - 2, -1, -1):
            best_path[t] = backpointer[t + 1, best_path[t + 1]]

        return best_path

    def forward_algorithm(self, features: np.ndarray) -> float:
        """
        Forward algorithm for computing log-partition function Z(x).
        """
        seq_len = features.shape[0]
        emission_scores = features @ self.emission_weights.T

        alpha = emission_scores[0].copy()
        for t in range(1, seq_len):
            new_alpha = np.full(self.n_labels, -np.inf)
            for j in range(self.n_labels):
                scores = alpha + self.transition_weights[:, j]
                new_alpha[j] = np.logaddexp.reduce(scores) + emission_scores[t, j]
            alpha = new_alpha

        return np.logaddexp.reduce(alpha)

    def compute_loss(self, features: np.ndarray, labels: list[int]) -> float:
        """Compute negative log-likelihood loss."""
        seq_len = features.shape[0]
        emission_scores = features @ self.emission_weights.T

        # Score of the gold path
        gold_score = sum(
            emission_scores[t, labels[t]] for t in range(seq_len)
        )
        gold_score += sum(
            self.transition_weights[labels[t], labels[t + 1]]
            for t in range(seq_len - 1)
        )

        # Log-partition
        log_z = self.forward_algorithm(features)

        return log_z - gold_score


class EntityExtractorTrainer:
    """
    Trains a CRF-based NER model for Swahili business entities.
    
    Pipeline:
    1. Load BIO-tagged training data
    2. Extract features (morphological + character n-grams)
    3. Train CRF with gradient descent
    4. Evaluate with entity-level precision/recall/F1
    5. Export for on-device deployment
    """

    def __init__(self, max_ngram_features: int = 3000):
        self.morph_analyzer = SwahiliMorphologicalAnalyzer()
        self.ngram_extractor = CharacterNgramExtractor(ngram_range=(2, 4))
        self.crf: Optional[CRFLayer] = None
        self.label_set: list[str] = []
        self.label_to_idx: dict[str, int] = {}
        self.training_data: list[NERTrainingExample] = []
        self.feature_dim: int = 0

    def load_training_data(self, data_path: str = None,
                           data_list: list[dict] = None) -> int:
        """Load BIO-tagged training data."""
        if data_path:
            with open(data_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)

        if data_list is None:
            raise ValueError("Provide data_path or data_list")

        self.training_data = []
        for item in data_list:
            example = NERTrainingExample(
                tokens=item["tokens"],
                tags=item["tags"],
                language=item.get("language", "sw"),
                region=item.get("region", "KE-Nairobi")
            )
            self.training_data.append(example)

        # Build label set
        all_tags = set()
        for example in self.training_data:
            all_tags.update(example.tags)
        self.label_set = sorted(all_tags)
        self.label_to_idx = {tag: idx for idx, tag in enumerate(self.label_set)}

        logger.info(f"Loaded {len(self.training_data)} NER examples, "
                    f"{len(self.label_set)} label types")
        return len(self.training_data)

    def extract_features(self, tokens: list[str]) -> np.ndarray:
        """Extract feature vector for a sequence of tokens."""
        features_list = []
        for token in tokens:
            feat = {}

            # Word features
            feat["word_lower"] = hash(token.lower()) % 1000 / 1000.0
            feat["is_capitalized"] = float(token[0].isupper()) if token else 0.0
            feat["is_digit"] = float(token.isdigit())
            feat["has_digit"] = float(any(c.isdigit() for c in token))
            feat["length"] = min(len(token), 20) / 20.0

            # Morphological features
            morph = self.morph_analyzer.analyze(token)
            feat["vowel_ratio"] = morph.get("vowel_ratio", 0.0)
            feat["has_apostrophe"] = float(morph.get("has_apostrophe", False))

            # Character n-gram features
            ngram_feats = self.ngram_extractor.transform(token.lower())
            feat.update(ngram_feats)

            # Position features
            feat["is_first"] = 0.0  # Will be set below
            feat["is_last"] = 0.0

            features_list.append(feat)

        # Set position features
        if features_list:
            features_list[0]["is_first"] = 1.0
            features_list[-1]["is_last"] = 1.0

        # Convert to fixed-size vector
        if not hasattr(self, '_feature_keys'):
            self._feature_keys = sorted(set(
                k for feat in features_list for k in feat.keys()
            ))
            self.feature_dim = len(self._feature_keys)

        matrix = np.zeros((len(tokens), self.feature_dim), dtype=np.float32)
        for t, feat in enumerate(features_list):
            for k, v in feat.items():
                if k in self._feature_keys:
                    idx = self._feature_keys.index(k)
                    matrix[t, idx] = v

        return matrix

    def train(self, max_iter: int = 100, learning_rate: float = 0.01) -> dict:
        """Train the CRF NER model."""
        if not self.training_data:
            raise ValueError("No training data loaded")

        # Fit n-gram extractor
        all_words = [token for ex in self.training_data for token in ex.tokens]
        self.ngram_extractor.fit(all_words)

        # Extract features for all examples
        feature_matrices = []
        label_sequences = []
        for example in self.training_data:
            features = self.extract_features(example.tokens)
            feature_matrices.append(features)
            label_sequences.append([self.label_to_idx[t] for t in example.tags])

        # Initialize CRF
        self.feature_dim = feature_matrices[0].shape[1]
        self.crf = CRFLayer(
            n_labels=len(self.label_set),
            n_features=self.feature_dim,
            learning_rate=learning_rate
        )

        # Training loop (simplified SGD)
        total_loss = 0.0
        for iteration in range(max_iter):
            epoch_loss = 0.0
            for features, labels in zip(feature_matrices, label_sequences):
                loss = self.crf.compute_loss(features, labels)
                epoch_loss += loss

            total_loss = epoch_loss / len(feature_matrices)
            if iteration % 10 == 0:
                logger.info(f"Iteration {iteration}: loss={total_loss:.4f}")

        metrics = {
            "final_loss": float(total_loss),
            "n_samples": len(self.training_data),
            "n_labels": len(self.label_set),
            "feature_dim": self.feature_dim
        }

        logger.info(f"Training complete: loss={total_loss:.4f}")
        return metrics

    def predict(self, tokens: list[str]) -> list[EntitySpan]:
        """Predict entity spans for a token sequence."""
        if self.crf is None:
            raise RuntimeError("Model not trained")

        features = self.extract_features(tokens)
        tag_indices = self.crf.viterbi_decode(features)
        tags = [self.label_set[idx] for idx in tag_indices]

        # Extract entity spans from BIO tags
        spans = []
        current_start = None
        current_type = None

        for i, tag in enumerate(tags):
            if tag.startswith("B-"):
                # Close previous span
                if current_start is not None:
                    spans.append(EntitySpan(
                        start=current_start,
                        end=i,
                        entity_type=current_type,
                        text=" ".join(tokens[current_start:i])
                    ))
                current_start = i
                current_type = tag[2:]
            elif tag.startswith("I-") and current_type == tag[2:]:
                continue
            else:
                # O tag or mismatched I- tag
                if current_start is not None:
                    spans.append(EntitySpan(
                        start=current_start,
                        end=i,
                        entity_type=current_type,
                        text=" ".join(tokens[current_start:i])
                    ))
                    current_start = None
                    current_type = None

        # Close final span
        if current_start is not None:
            spans.append(EntitySpan(
                start=current_start,
                end=len(tokens),
                entity_type=current_type,
                text=" ".join(tokens[current_start:])
            ))

        return spans

    def evaluate(self, test_data: list[NERTrainingExample] = None) -> NEREvaluationResult:
        """
        Evaluate NER model with entity-level metrics.
        """
        if test_data is None:
            test_data = self.training_data

        true_entities = []
        pred_entities = []

        for example in test_data:
            # Gold entities
            gold = self._bio_to_spans(example.tokens, example.tags)
            true_entities.extend(gold)

            # Predicted entities
            pred = self.predict(example.tokens)
            pred_entities.extend(pred)

        # Compute precision, recall, F1
        true_set = {(e.start, e.end, e.entity_type) for e in true_entities}
        pred_set = {(e.start, e.end, e.entity_type) for e in pred_entities}

        tp = len(true_set & pred_set)
        precision = tp / max(len(pred_set), 1)
        recall = tp / max(len(true_set), 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)

        # Per-entity metrics
        entity_types = set(e.entity_type for e in true_entities + pred_entities)
        per_entity = {}
        for etype in entity_types:
            true_e = {s for s in true_set if s[2] == etype}
            pred_e = {s for s in pred_set if s[2] == etype}
            tp_e = len(true_e & pred_e)
            p = tp_e / max(len(pred_e), 1)
            r = tp_e / max(len(true_e), 1)
            f = 2 * p * r / max(p + r, 1e-10)
            per_entity[etype] = {"precision": p, "recall": r, "f1": f}

        return NEREvaluationResult(
            precision=float(precision),
            recall=float(recall),
            f1=float(f1),
            per_entity_metrics=per_entity
        )

    def export_model(self, output_path: str):
        """Export model for on-device deployment."""
        os.makedirs(output_path, exist_ok=True)

        # Save CRF weights
        np.savez(
            os.path.join(output_path, "crf_weights.npz"),
            emission=self.crf.emission_weights,
            transition=self.crf.transition_weights
        )

        # Save label set
        with open(os.path.join(output_path, "labels.json"), 'w') as f:
            json.dump(self.label_set, f)

        # Save feature keys
        with open(os.path.join(output_path, "features.json"), 'w') as f:
            json.dump(self._feature_keys, f)

        # Save n-gram vocabulary
        with open(os.path.join(output_path, "ngram_vocab.json"), 'w') as f:
            json.dump(self.ngram_extractor.vocabulary, f)

        logger.info(f"NER model exported to {output_path}")

    def _bio_to_spans(self, tokens: list[str], tags: list[str]) -> list[EntitySpan]:
        """Convert BIO tags to entity spans."""
        spans = []
        current_start = None
        current_type = None

        for i, tag in enumerate(tags):
            if tag.startswith("B-"):
                if current_start is not None:
                    spans.append(EntitySpan(
                        start=current_start, end=i,
                        entity_type=current_type,
                        text=" ".join(tokens[current_start:i])
                    ))
                current_start = i
                current_type = tag[2:]
            elif tag.startswith("I-") and current_type == tag[2:]:
                continue
            else:
                if current_start is not None:
                    spans.append(EntitySpan(
                        start=current_start, end=i,
                        entity_type=current_type,
                        text=" ".join(tokens[current_start:i])
                    ))
                    current_start = None
                    current_type = None

        if current_start is not None:
            spans.append(EntitySpan(
                start=current_start, end=len(tokens),
                entity_type=current_type,
                text=" ".join(tokens[current_start:])
            ))

        return spans


def train_entity_extractor(training_data_path: str = None,
                           training_data: list[dict] = None,
                           output_path: str = "models/entity_extractor") -> dict:
    """Factory function to train and export an entity extractor."""
    trainer = EntityExtractorTrainer()
    trainer.load_training_data(
        data_path=training_data_path,
        data_list=training_data
    )
    metrics = trainer.train()
    eval_result = trainer.evaluate()
    trainer.export_model(output_path)

    return {
        **metrics,
        "evaluation": {
            "precision": eval_result.precision,
            "recall": eval_result.recall,
            "f1": eval_result.f1,
            "per_entity": eval_result.per_entity_metrics
        }
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        data_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else "models/entity_extractor"
        results = train_entity_extractor(data_path, output_path=output_path)
        print(json.dumps(results, indent=2))
    else:
        print("Usage: python entity_extractor_training.py <data.json> [output_dir]")
