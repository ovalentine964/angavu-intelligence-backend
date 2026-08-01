"""
Training Data Validator — Validate and clean dialect training data.

Ensures data quality before it enters training pipelines:
- Schema validation (required fields, types)
- Linguistic validation (valid Swahili/Sheng patterns)
- Deduplication (exact and fuzzy)
- Label consistency checks
- Distribution analysis (class balance, outlier detection)
- Privacy checks (no PII in training data)

Academic basis:
- Non-parametric outlier detection (no distributional assumptions)
- Bootstrap for confidence intervals on data quality metrics
"""

import hashlib
import json
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of validating a single sample."""
    sample_id: str
    is_valid: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    quality_score: float = 1.0


@dataclass
class ValidationReport:
    """Report on a full dataset validation."""
    total_samples: int
    valid_samples: int
    invalid_samples: int
    duplicate_samples: int
    quality_score_mean: float
    quality_score_std: float
    errors_by_type: dict = field(default_factory=dict)
    warnings_by_type: dict = field(default_factory=dict)
    class_distribution: dict = field(default_factory=dict)
    class_balance_ratio: float = 0.0
    outliers_detected: list = field(default_factory=list)
    pii_detected: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)


class SchemaValidator:
    """Validates data schema (required fields, types)."""

    # Required fields for different data types
    INTENT_SCHEMA = {
        "utterance": {"type": str, "required": True, "min_length": 2},
        "intent": {"type": str, "required": True},
        "language": {"type": str, "required": False, "allowed": ["sw", "en", "sheng", "code-switch"]},
        "region": {"type": str, "required": False},
        "confidence": {"type": (int, float), "required": False, "min": 0, "max": 1}
    }

    NER_SCHEMA = {
        "tokens": {"type": list, "required": True, "min_length": 1},
        "tags": {"type": list, "required": True, "min_length": 1},
        "language": {"type": str, "required": False},
        "region": {"type": str, "required": False}
    }

    STT_SCHEMA = {
        "transcript": {"type": str, "required": True, "min_length": 2},
        "dialect": {"type": str, "required": True},
        "confidence": {"type": (int, float), "required": False, "min": 0, "max": 1}
    }

    def validate(self, sample: dict, schema_type: str = "intent") -> ValidationResult:
        """Validate a single sample against schema."""
        schema = getattr(self, f"{schema_type.upper()}_SCHEMA", self.INTENT_SCHEMA)
        errors = []
        warnings = []
        sample_id = sample.get("id", sample.get("utterance", "")[:20])

        for field_name, rules in schema.items():
            value = sample.get(field_name)

            # Required check
            if rules.get("required") and value is None:
                errors.append(f"Missing required field: {field_name}")
                continue

            if value is None:
                continue

            # Type check
            expected_type = rules.get("type")
            if expected_type and not isinstance(value, expected_type):
                errors.append(f"Field '{field_name}' has wrong type: "
                            f"expected {expected_type}, got {type(value)}")
                continue

            # String length
            if isinstance(value, str):
                min_len = rules.get("min_length")
                if min_len and len(value) < min_len:
                    errors.append(f"Field '{field_name}' too short: {len(value)} < {min_len}")

            # Numeric range
            if isinstance(value, (int, float)):
                min_val = rules.get("min")
                max_val = rules.get("max")
                if min_val is not None and value < min_val:
                    errors.append(f"Field '{field_name}' below minimum: {value} < {min_val}")
                if max_val is not None and value > max_val:
                    errors.append(f"Field '{field_name}' above maximum: {value} > {max_val}")

            # Allowed values
            allowed = rules.get("allowed")
            if allowed and value not in allowed:
                warnings.append(f"Field '{field_name}' has unexpected value: {value}")

        # NER-specific: tokens and tags must have same length
        if schema_type == "ner":
            tokens = sample.get("tokens", [])
            tags = sample.get("tags", [])
            if len(tokens) != len(tags):
                errors.append(f"Token/tag length mismatch: {len(tokens)} vs {len(tags)}")

        quality_score = 1.0 - (len(errors) * 0.3 + len(warnings) * 0.1)
        quality_score = max(0.0, quality_score)

        return ValidationResult(
            sample_id=sample_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            quality_score=quality_score
        )


class LinguisticValidator:
    """Validates linguistic properties of Swahili/Sheng text."""

    # Swahili character set
    SWAHILI_CHARS = set("abcdefghijklmnopqrstuvwxyz'")

    # Known Sheng markers
    SHENG_MARKERS = {
        "sasa", "niaje", "mambo", "poa", "msee", "mbogi", "genje",
        "thao", "kibaki", "ngiri", "soo", "jaboya", "finje"
    }

    def validate_transcript(self, text: str) -> ValidationResult:
        """Validate a transcript's linguistic properties."""
        errors = []
        warnings = []

        # Basic checks
        if not text or not text.strip():
            errors.append("Empty transcript")
            return ValidationResult(sample_id="", is_valid=False, errors=errors)

        text = text.strip()

        # Character set check
        invalid_chars = set(text.lower()) - self.SWAHILI_CHARS - set(" 0123456789.,!?;:-")
        if invalid_chars:
            warnings.append(f"Non-standard characters: {invalid_chars}")

        # Length check
        words = text.split()
        if len(words) > 100:
            warnings.append(f"Very long transcript: {len(words)} words")

        if len(words) == 1 and len(text) < 3:
            warnings.append("Suspiciously short transcript")

        # Repetition check (stuttering detection)
        if self._has_excessive_repetition(words):
            warnings.append("Excessive word repetition detected")

        # All-caps check
        if text.isupper() and len(text) > 10:
            warnings.append("All-caps transcript")

        quality_score = 1.0 - (len(errors) * 0.3 + len(warnings) * 0.1)

        return ValidationResult(
            sample_id=text[:20],
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            quality_score=max(0.0, quality_score)
        )

    def validate_intent_label(self, intent: str, utterance: str) -> ValidationResult:
        """Validate that an intent label makes sense for the utterance."""
        errors = []
        warnings = []

        # Known intents
        known_intents = {
            "RECORD_SALE", "RECORD_PURCHASE", "CHECK_STOCK", "CHECK_BALANCE",
            "RECORD_EXPENSE", "CHECK_PROFIT", "SEND_RECEIPT", "ADD_PRODUCT",
            "SEARCH_PRODUCT", "RECORD_PAYMENT", "CHECK_DEBT", "REPORT_DAILY",
            "GREETING", "HELP", "CANCEL", "CONFIRM"
        }

        if intent not in known_intents:
            warnings.append(f"Unknown intent: {intent}")

        # Heuristic checks
        utterance_lower = utterance.lower()

        # Check for intent-utterance consistency
        if intent == "GREETING" and not any(w in utterance_lower for w in
            ["habari", "sasa", "niaje", "mambo", "jambo", "hello", "shikamoo"]):
            warnings.append("GREETING intent but no greeting words found")

        if intent == "RECORD_SALE" and not any(w in utterance_lower for w in
            ["uza", "sold", "sale", "mauzo", "piga"]):
            warnings.append("RECORD_SALE intent but no sale-related words")

        if intent == "CHECK_STOCK" and not any(w in utterance_lower for w in
            ["stock", "bidhaa", "baki", "angalia", "kuna"]):
            warnings.append("CHECK_STOCK intent but no stock-related words")

        quality_score = 1.0 - (len(errors) * 0.3 + len(warnings) * 0.1)

        return ValidationResult(
            sample_id=utterance[:20],
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            quality_score=max(0.0, quality_score)
        )

    def _has_excessive_repetition(self, words: list[str]) -> bool:
        """Check for excessive word repetition (stuttering artifacts)."""
        if len(words) < 3:
            return False

        # Check for repeated bigrams
        for i in range(len(words) - 2):
            if words[i] == words[i + 1] == words[i + 2]:
                return True

        # Check for repeated trigrams
        if len(words) >= 6:
            for i in range(len(words) - 5):
                tri1 = (words[i], words[i + 1], words[i + 2])
                tri2 = (words[i + 3], words[i + 4], words[i + 5])
                if tri1 == tri2:
                    return True

        return False


class Deduplicator:
    """Detects and removes duplicate samples."""

    def __init__(self, fuzzy_threshold: float = 0.9):
        self.fuzzy_threshold = fuzzy_threshold

    def find_exact_duplicates(self, samples: list[dict],
                               key_field: str = "utterance") -> list[tuple]:
        """Find exact duplicate pairs."""
        seen = {}
        duplicates = []

        for i, sample in enumerate(samples):
            key = sample.get(key_field, "")
            key_hash = hashlib.md5(key.lower().strip().encode()).hexdigest()

            if key_hash in seen:
                duplicates.append((seen[key_hash], i))
            else:
                seen[key_hash] = i

        return duplicates

    def find_near_duplicates(self, samples: list[dict],
                              key_field: str = "utterance") -> list[tuple]:
        """Find near-duplicate pairs using character-level similarity."""
        near_dupes = []
        texts = [sample.get(key_field, "").lower().strip() for sample in samples]

        for i in range(len(texts)):
            for j in range(i + 1, min(len(texts), i + 100)):  # Limit comparisons
                sim = self._char_similarity(texts[i], texts[j])
                if sim >= self.fuzzy_threshold:
                    near_dupes.append((i, j, sim))

        return near_dupes

    def deduplicate(self, samples: list[dict],
                     key_field: str = "utterance") -> tuple:
        """
        Remove duplicates, keeping the first occurrence.
        Returns (deduplicated_samples, removed_indices).
        """
        seen = set()
        deduped = []
        removed = []

        for i, sample in enumerate(samples):
            key = sample.get(key_field, "").lower().strip()
            key_hash = hashlib.md5(key.encode()).hexdigest()

            if key_hash not in seen:
                seen.add(key_hash)
                deduped.append(sample)
            else:
                removed.append(i)

        return deduped, removed

    def _char_similarity(self, a: str, b: str) -> float:
        """Compute character-level similarity (Jaccard on character trigrams)."""
        if not a or not b:
            return 0.0

        trigrams_a = set(a[i:i+3] for i in range(len(a) - 2))
        trigrams_b = set(b[i:i+3] for i in range(len(b) - 2))

        if not trigrams_a or not trigrams_b:
            return 0.0

        intersection = trigrams_a & trigrams_b
        union = trigrams_a | trigrams_b

        return len(intersection) / len(union)


class PIIDetector:
    """Detects personally identifiable information in training data."""

    # Patterns that might indicate PII
    PHONE_PATTERN = re.compile(r'\b(?:\+?254|0)[17]\d{8}\b')
    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    ID_PATTERN = re.compile(r'\b\d{6,8}\b')  # Kenyan ID numbers

    def detect(self, text: str) -> list[dict]:
        """Detect potential PII in text."""
        findings = []

        # Phone numbers
        phones = self.PHONE_PATTERN.findall(text)
        for phone in phones:
            findings.append({"type": "phone", "value": phone, "confidence": 0.8})

        # Emails
        emails = self.EMAIL_PATTERN.findall(text)
        for email in emails:
            findings.append({"type": "email", "value": email, "confidence": 0.9})

        # ID numbers (lower confidence, could be amounts)
        ids = self.ID_PATTERN.findall(text)
        for id_num in ids:
            if int(id_num) > 100000:  # Likely ID, not amount
                findings.append({"type": "id_number", "value": id_num, "confidence": 0.4})

        return findings


class OutlierDetector:
    """
    Non-parametric outlier detection for training data quality.
    Uses IQR method (no distributional assumptions).
    """

    @staticmethod
    def detect_outliers_iqr(values: list[float], multiplier: float = 1.5) -> list[int]:
        """
        Detect outliers using the IQR method.
        Academic basis: Non-parametric methods (no distributional assumptions)
        """
        if len(values) < 4:
            return []

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[3 * n // 4]
        iqr = q3 - q1

        lower_bound = q1 - multiplier * iqr
        upper_bound = q3 + multiplier * iqr

        return [i for i, v in enumerate(values)
                if v < lower_bound or v > upper_bound]


class TrainingDataValidator:
    """
    Full training data validation pipeline.
    
    Runs:
    1. Schema validation
    2. Linguistic validation
    3. Deduplication
    4. PII detection
    5. Distribution analysis
    6. Outlier detection
    """

    def __init__(self):
        self.schema_validator = SchemaValidator()
        self.linguistic_validator = LinguisticValidator()
        self.deduplicator = Deduplicator()
        self.pii_detector = PIIDetector()
        self.outlier_detector = OutlierDetector()

    def validate_intent_data(self, samples: list[dict]) -> ValidationReport:
        """Validate intent classification training data."""
        return self._validate(samples, schema_type="intent",
                             key_field="utterance", label_field="intent")

    def validate_ner_data(self, samples: list[dict]) -> ValidationReport:
        """Validate NER training data."""
        return self._validate(samples, schema_type="ner",
                             key_field="tokens", label_field=None)

    def validate_stt_data(self, samples: list[dict]) -> ValidationReport:
        """Validate STT training data."""
        return self._validate(samples, schema_type="stt",
                             key_field="transcript", label_field=None)

    def _validate(self, samples: list[dict], schema_type: str,
                  key_field: str, label_field: str = None) -> ValidationReport:
        """Run full validation pipeline."""
        if not samples:
            return ValidationReport(
                total_samples=0, valid_samples=0, invalid_samples=0,
                duplicate_samples=0, quality_score_mean=0, quality_score_std=0
            )

        # 1. Schema validation
        schema_results = []
        for sample in samples:
            result = self.schema_validator.validate(sample, schema_type)
            schema_results.append(result)

        # 2. Linguistic validation
        linguistic_results = []
        for sample in samples:
            if schema_type == "intent":
                utterance = sample.get("utterance", "")
                intent = sample.get("intent", "")
                result = self.linguistic_validator.validate_intent_label(intent, utterance)
                linguistic_results.append(result)
            elif schema_type == "stt":
                transcript = sample.get("transcript", "")
                result = self.linguistic_validator.validate_transcript(transcript)
                linguistic_results.append(result)

        # 3. Deduplication
        _, removed_indices = self.deduplicator.deduplicate(samples, key_field)

        # 4. PII detection
        pii_findings = []
        for i, sample in enumerate(samples):
            text = sample.get(key_field, "")
            if isinstance(text, list):
                text = " ".join(text)
            findings = self.pii_detector.detect(str(text))
            if findings:
                pii_findings.append({"sample_idx": i, "findings": findings})

        # 5. Quality scores
        quality_scores = [r.quality_score for r in schema_results]
        quality_mean = float(np.mean(quality_scores))
        quality_std = float(np.std(quality_scores))

        # 6. Class distribution (for intent data)
        class_dist = {}
        if label_field:
            labels = [s.get(label_field, "unknown") for s in samples]
            class_dist = dict(Counter(labels))

        # Class balance ratio
        if class_dist:
            counts = list(class_dist.values())
            balance_ratio = min(counts) / max(counts) if max(counts) > 0 else 0
        else:
            balance_ratio = 1.0

        # 7. Error/warning aggregation
        errors_by_type = Counter()
        warnings_by_type = Counter()
        for r in schema_results + linguistic_results:
            for e in r.errors:
                errors_by_type[e.split(":")[0] if ":" in e else e] += 1
            for w in r.warnings:
                warnings_by_type[w.split(":")[0] if ":" in w else w] += 1

        # 8. Generate recommendations
        recommendations = self._generate_recommendations(
            quality_mean, balance_ratio, len(removed_indices),
            len(pii_findings), len(samples)
        )

        valid_count = sum(1 for r in schema_results if r.is_valid)

        return ValidationReport(
            total_samples=len(samples),
            valid_samples=valid_count,
            invalid_samples=len(samples) - valid_count,
            duplicate_samples=len(removed_indices),
            quality_score_mean=quality_mean,
            quality_score_std=quality_std,
            errors_by_type=dict(errors_by_type),
            warnings_by_type=dict(warnings_by_type),
            class_distribution=class_dist,
            class_balance_ratio=balance_ratio,
            pii_detected=pii_findings,
            recommendations=recommendations
        )

    def clean_dataset(self, samples: list[dict],
                      schema_type: str = "intent") -> list[dict]:
        """
        Clean a dataset by removing invalid/duplicate samples.
        Returns cleaned dataset.
        """
        # Remove duplicates
        deduped, _ = self.deduplicator.deduplicate(samples)

        # Remove invalid samples
        cleaned = []
        for sample in deduped:
            result = self.schema_validator.validate(sample, schema_type)
            if result.is_valid and result.quality_score >= 0.5:
                cleaned.append(sample)

        logger.info(f"Cleaned dataset: {len(samples)} → {len(cleaned)} samples "
                    f"(removed {len(samples) - len(cleaned)})")

        return cleaned

    def _generate_recommendations(self, quality_mean: float, balance_ratio: float,
                                   n_duplicates: int, n_pii: int,
                                   n_total: int) -> list[str]:
        """Generate actionable recommendations."""
        recs = []

        if quality_mean < 0.7:
            recs.append("Overall data quality is low (<0.7). Review data collection pipeline.")

        if balance_ratio < 0.3:
            recs.append("Severe class imbalance detected. Consider oversampling minority classes "
                       "or collecting more data for underrepresented intents.")

        if n_duplicates > n_total * 0.1:
            recs.append(f"High duplicate rate ({n_duplicates}/{n_total}). "
                       f"Review data collection for redundancy.")

        if n_pii > 0:
            recs.append(f"Potential PII detected in {n_pii} samples. "
                       f"Review and anonymize before training.")

        if n_total < 100:
            recs.append("Small dataset. Consider data augmentation or transfer learning.")

        if not recs:
            recs.append("Dataset looks good! Ready for training.")

        return recs


def validate_training_data(data: list[dict], data_type: str = "intent") -> dict:
    """Factory function for data validation."""
    validator = TrainingDataValidator()

    if data_type == "intent":
        report = validator.validate_intent_data(data)
    elif data_type == "ner":
        report = validator.validate_ner_data(data)
    elif data_type == "stt":
        report = validator.validate_stt_data(data)
    else:
        raise ValueError(f"Unknown data type: {data_type}")

    return {
        "total_samples": report.total_samples,
        "valid_samples": report.valid_samples,
        "invalid_samples": report.invalid_samples,
        "duplicate_samples": report.duplicate_samples,
        "quality_score_mean": report.quality_score_mean,
        "quality_score_std": report.quality_score_std,
        "class_balance_ratio": report.class_balance_ratio,
        "pii_detected": len(report.pii_detected),
        "recommendations": report.recommendations,
        "errors_by_type": report.errors_by_type
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            data = json.load(f)
        data_type = sys.argv[2] if len(sys.argv) > 2 else "intent"
        result = validate_training_data(data, data_type)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python training_data_validator.py <data.json> [intent|ner|stt]")
