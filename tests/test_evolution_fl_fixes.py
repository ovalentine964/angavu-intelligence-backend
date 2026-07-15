"""
Tests for self-evolution quality judge and federated learning fixes.

Covers:
1. Self-evolution LLM judge — proper heuristic scoring with real metrics
2. FL gradient clipping — L2 norm bounded to max_norm
3. FL v2 adapter aggregation — weighted average instead of last-device-wins
"""

import base64
import importlib
import math
import os
import struct
import sys
from datetime import datetime, timedelta, timezone

import pytest

# Ensure app dir is on path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Bypass app/services/__init__.py (which pulls in the whole app)
# by importing modules directly via importlib
_spec_se = importlib.util.spec_from_file_location(
    "app.services.self_evolution",
    os.path.join(REPO_ROOT, "app", "services", "self_evolution.py"),
)
_mod_se = importlib.util.module_from_spec(_spec_se)
sys.modules["app.services.self_evolution"] = _mod_se
_spec_se.loader.exec_module(_mod_se)

_spec_flv2 = importlib.util.spec_from_file_location(
    "app.services.federated_learning_v2",
    os.path.join(REPO_ROOT, "app", "services", "federated_learning_v2.py"),
)
_mod_flv2 = importlib.util.module_from_spec(_spec_flv2)
sys.modules["app.services.federated_learning_v2"] = _mod_flv2
_spec_flv2.loader.exec_module(_mod_flv2)

# For FL v1, we need to set up its dependencies first
# The schemas module is standalone
_spec_schemas = importlib.util.spec_from_file_location(
    "app.schemas.federated_learning",
    os.path.join(REPO_ROOT, "app", "schemas", "federated_learning.py"),
)
_mod_schemas = importlib.util.module_from_spec(_spec_schemas)
sys.modules["app.schemas.federated_learning"] = _mod_schemas
_spec_schemas.loader.exec_module(_mod_schemas)

# fl_persistence needs a stub to avoid DB dependency
_spec_persist = importlib.util.spec_from_file_location(
    "app.services.fl_persistence",
    os.path.join(REPO_ROOT, "app", "services", "fl_persistence.py"),
)
_mod_persist = importlib.util.module_from_spec(_spec_persist)
sys.modules["app.services.fl_persistence"] = _mod_persist
try:
    _spec_persist.loader.exec_module(_mod_persist)
except Exception:
    # If fl_persistence fails (e.g. DB dependency), create a minimal stub
    class _StubFLPersistence:
        def save_update(self, *a, **kw): pass
        def save_device_info(self, *a, **kw): pass
        def get_latest_model(self, *a, **kw): return None
        def get_total_update_count(self): return 0
        def get_device_count(self): return 0
        def mark_processed(self, *a, **kw): pass
    _mod_persist.FLPersistence = _StubFLPersistence

_spec_fl = importlib.util.spec_from_file_location(
    "app.services.federated_learning",
    os.path.join(REPO_ROOT, "app", "services", "federated_learning.py"),
)
_mod_fl = importlib.util.module_from_spec(_spec_fl)
sys.modules["app.services.federated_learning"] = _mod_fl
_spec_fl.loader.exec_module(_mod_fl)

# Extract the names we need
SelfEvolutionService = _mod_se.SelfEvolutionService
FeedbackStatus = _mod_se.FeedbackStatus
FeedbackType = _mod_se.FeedbackType
WorkerFeedback = _mod_se.WorkerFeedback

AnonymizedUpdate = _mod_flv2.AnonymizedUpdate
DataCategory = _mod_flv2.DataCategory
_clip_gradient = _mod_flv2._clip_gradient
_clip_gradient_bytes = _mod_flv2._clip_gradient_bytes
_fedavg = _mod_flv2._fedavg
GRADIENT_MAX_NORM = _mod_flv2.GRADIENT_MAX_NORM

_weighted_lora_average = _mod_fl._weighted_lora_average


# ════════════════════════════════════════════════════════════════════
# Self-Evolution Quality Judge Tests
# ════════════════════════════════════════════════════════════════════


class TestSentimentScoring:
    """Test the enhanced weighted sentiment scorer."""

    def _make_service(self):
        return SelfEvolutionService()

    def test_positive_feedback(self):
        svc = self._make_service()
        score = svc._score_sentiment("This is great and amazing, I love it!")
        assert score > 0.5, f"Expected positive score, got {score}"

    def test_negative_feedback(self):
        svc = self._make_service()
        score = svc._score_sentiment("This is terrible and frustrating, I hate it")
        assert score < -0.5, f"Expected negative score, got {score}"

    def test_neutral_feedback(self):
        svc = self._make_service()
        score = svc._score_sentiment("The feature was updated yesterday")
        assert score == 0.0, f"Expected neutral score, got {score}"

    def test_mixed_feedback(self):
        svc = self._make_service()
        score = svc._score_sentiment("It's good but also slow and broken")
        assert -1.0 <= score <= 1.0

    def test_intensifier_amplifies(self):
        svc = self._make_service()
        plain = svc._score_sentiment("good feature")
        intensified = svc._score_sentiment("very good feature")
        assert intensified >= plain

    def test_negator_flips(self):
        svc = self._make_service()
        positive = svc._score_sentiment("great feature")
        negated = svc._score_sentiment("not great feature")
        assert negated < positive

    def test_empty_text(self):
        svc = self._make_service()
        score = svc._score_sentiment("")
        assert score == 0.0

    def test_score_bounds(self):
        svc = self._make_service()
        score = svc._score_sentiment("amazing wonderful fantastic excellent")
        assert -1.0 <= score <= 1.0
        score = svc._score_sentiment("terrible horrible awful worst")
        assert -1.0 <= score <= 1.0


class TestQualityEvaluation:
    """Test the multi-signal quality evaluation judge."""

    def _make_service_with_feedback(self, feedback_specs):
        """Create a service with feedback items.

        feedback_specs: list of (text, type_override, age_days, status)
        """
        svc = SelfEvolutionService()
        now = datetime.now(timezone.utc)

        for i, spec in enumerate(feedback_specs):
            text = spec[0]
            fb_type = spec[1] if len(spec) > 1 else None
            age_days = spec[2] if len(spec) > 2 else 0
            status = spec[3] if len(spec) > 3 else FeedbackStatus.COLLECTED

            classified = svc._classify_feedback(text, fb_type)
            sentiment = svc._score_sentiment(text)
            urgency = svc._score_urgency(text, classified)

            fb = WorkerFeedback(
                worker_id=f"worker_{i}",
                feedback_type=classified,
                raw_text=text,
                sentiment_score=sentiment,
                urgency_score=urgency,
                status=status,
                collected_at=now - timedelta(days=age_days),
            )
            svc._feedback[fb.feedback_id] = fb

        return svc

    def test_no_feedback_returns_zero(self):
        svc = self._make_service_with_feedback([])
        result = svc.evaluate_quality()
        assert result["overall_score"] == 0.0
        assert result["diagnostics"] == "no_feedback_available"

    def test_positive_feedback_high_score(self):
        svc = self._make_service_with_feedback([
            ("This is great and amazing, love it!", None, 0),
            ("Very helpful and wonderful feature", None, 0),
            ("Excellent tool, perfect for my business", None, 1),
        ])
        result = svc.evaluate_quality()
        assert result["overall_score"] > 0.5, f"Expected > 0.5, got {result['overall_score']}"
        assert result["components"]["sentiment"] > 0.5

    def test_negative_feedback_low_error_score(self):
        svc = self._make_service_with_feedback([
            ("This is terrible and broken", None, 0),
            ("Hate this, it's frustrating and awful", None, 0),
            ("Worst feature ever, completely useless", None, 1),
        ])
        result = svc.evaluate_quality()
        assert result["components"]["error_rate"] < 0.7

    def test_mixed_feedback_moderate_score(self):
        svc = self._make_service_with_feedback([
            ("Great feature, love it!", None, 0),
            ("This is broken and doesn't work", None, 0),
            ("Useful but could be better", None, 1),
        ])
        result = svc.evaluate_quality()
        assert 0.2 < result["overall_score"] < 0.9

    def test_urgency_resolution_improves_score(self):
        svc_unresolved = self._make_service_with_feedback([
            ("This is broken and critical", "bug_report", 0, FeedbackStatus.COLLECTED),
        ])
        svc_resolved = self._make_service_with_feedback([
            ("This is broken and critical", "bug_report", 0, FeedbackStatus.DEPLOYED),
        ])

        result_unresolved = svc_unresolved.evaluate_quality()
        result_resolved = svc_resolved.evaluate_quality()

        assert result_resolved["components"]["urgency_resolution"] > \
               result_unresolved["components"]["urgency_resolution"]

    def test_components_sum_to_reasonable_range(self):
        svc = self._make_service_with_feedback([
            ("Good feature", None, 0),
            ("Needs improvement", None, 1),
            ("Bug in the system", "bug_report", 2),
            ("I love this tool", None, 0),
            ("Can you add more features?", "feature_request", 3),
        ])
        result = svc.evaluate_quality()
        assert 0.0 <= result["overall_score"] <= 1.0
        for comp_name, comp_score in result["components"].items():
            assert 0.0 <= comp_score <= 1.0, f"{comp_name} = {comp_score} out of range"

    def test_diagnostics_include_counts(self):
        svc = self._make_service_with_feedback([
            ("Good", None, 0),
            ("Bad", None, 0),
        ])
        result = svc.evaluate_quality()
        diag = result["diagnostics"]
        assert diag["total_feedback"] == 2
        assert "error_count" in diag
        assert "feedback_types" in diag


# ════════════════════════════════════════════════════════════════════
# FL Gradient Clipping Tests
# ════════════════════════════════════════════════════════════════════


class TestGradientClipping:
    """Test that gradient clipping bounds L2 norm to max_norm."""

    def _make_gradient_bytes(self, values):
        return struct.pack(f"<{len(values)}f", *values)

    def _decode_gradient_bytes(self, raw_bytes):
        n = len(raw_bytes) // 4
        return list(struct.unpack(f"<{n}f", raw_bytes[:n * 4]))

    def test_clip_gradient_small_not_clipped(self):
        grad = [0.1, 0.2, 0.3]
        clipped = _clip_gradient(grad, max_norm=1.0)
        assert clipped == grad

    def test_clip_gradient_large_is_clipped(self):
        grad = [3.0, 4.0]  # L2 norm = 5.0
        clipped = _clip_gradient(grad, max_norm=1.0)
        l2 = math.sqrt(sum(v * v for v in clipped))
        assert abs(l2 - 1.0) < 1e-6, f"Expected L2=1.0, got {l2}"
        assert abs(clipped[0] / clipped[1] - 3.0 / 4.0) < 1e-6

    def test_clip_gradient_exact_norm(self):
        grad = [0.6, 0.8]  # L2 norm = 1.0
        clipped = _clip_gradient(grad, max_norm=1.0)
        assert clipped == grad

    def test_clip_gradient_preserves_direction(self):
        grad = [10.0, 20.0, 30.0]
        clipped = _clip_gradient(grad, max_norm=1.0)
        for i in range(1, len(grad)):
            ratio_orig = grad[i] / grad[0]
            ratio_clip = clipped[i] / clipped[0]
            assert abs(ratio_orig - ratio_clip) < 1e-6

    def test_clip_gradient_bytes(self):
        values = [3.0, 4.0, 0.0]  # L2 norm = 5.0
        raw = self._make_gradient_bytes(values)
        clipped_raw = _clip_gradient_bytes(raw, max_norm=1.0)
        clipped = self._decode_gradient_bytes(clipped_raw)
        l2 = math.sqrt(sum(v * v for v in clipped))
        assert abs(l2 - 1.0) < 1e-6

    def test_clip_gradient_empty(self):
        assert _clip_gradient([], max_norm=1.0) == []

    def test_clip_gradient_zeros(self):
        grad = [0.0, 0.0, 0.0]
        clipped = _clip_gradient(grad, max_norm=1.0)
        assert clipped == [0.0, 0.0, 0.0]

    def test_clip_gradient_very_large(self):
        grad = [1000.0, 2000.0, 3000.0]
        clipped = _clip_gradient(grad, max_norm=1.0)
        l2 = math.sqrt(sum(v * v for v in clipped))
        assert abs(l2 - 1.0) < 1e-6


# ════════════════════════════════════════════════════════════════════
# FL v2 Adapter Aggregation Tests
# ════════════════════════════════════════════════════════════════════


class TestFLv2AdapterAggregation:
    """Test that FL v2 uses weighted average for adapter deltas."""

    def _encode_floats(self, values):
        packed = struct.pack(f"<{len(values)}f", *values)
        return base64.b64encode(packed).decode("ascii")

    def _decode_b64(self, b64_str):
        raw = base64.b64decode(b64_str)
        n = len(raw) // 4
        return list(struct.unpack(f"<{n}f", raw[:n * 4]))

    def test_fedavg_weighted_adapter_aggregation(self):
        """Adapter deltas should be averaged by weight, not last-device-wins."""
        # Device 1: weight=1, deltas=[0.1, 0.2]
        update1 = AnonymizedUpdate(
            device_id_hash="a" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=1,
            gradient_deltas=self._encode_floats([0.1, 0.2]),
        )
        # Device 2: weight=3, deltas=[0.3, 0.6]
        update2 = AnonymizedUpdate(
            device_id_hash="b" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=3,
            gradient_deltas=self._encode_floats([0.3, 0.6]),
        )

        result = _fedavg([update1, update2], DataCategory.VOCABULARY)

        adapter_b64 = result.get("adapter_deltas")
        assert adapter_b64 is not None, "adapter_deltas should not be None"
        agg = self._decode_b64(adapter_b64)

        # Weighted avg: (0.1*1 + 0.3*3)/(1+3) = 1.0/4 = 0.25
        #               (0.2*1 + 0.6*3)/(1+3) = 2.0/4 = 0.5
        assert abs(agg[0] - 0.25) < 0.01, f"Expected 0.25, got {agg[0]}"
        assert abs(agg[1] - 0.5) < 0.01, f"Expected 0.5, got {agg[1]}"

    def test_fedavg_not_last_device_wins(self):
        """Verify it's not just using the last device's deltas."""
        # Device 1: weight=100, deltas=[0.1, 0.2] (small, under clip threshold)
        update1 = AnonymizedUpdate(
            device_id_hash="a" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=100,
            gradient_deltas=self._encode_floats([0.1, 0.2]),
        )
        # Device 2: weight=1, deltas=[0.9, 0.1] (last device)
        update2 = AnonymizedUpdate(
            device_id_hash="b" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=1,
            gradient_deltas=self._encode_floats([0.9, 0.1]),
        )

        result = _fedavg([update1, update2], DataCategory.VOCABULARY)
        agg = self._decode_b64(result["adapter_deltas"])

        # Weighted avg: (0.1*100 + 0.9*1)/(101) = 10.9/101 ≈ 0.108
        # NOT 0.9 (which last-device-wins would give)
        assert agg[0] < 0.5, f"Should be ~0.108, got {agg[0]}"
        assert abs(agg[0] - (0.1 * 100 + 0.9 * 1) / 101) < 0.01

    def test_fedavg_clips_gradients_before_aggregation(self):
        """Gradients should be clipped to max_norm=1.0 before averaging."""
        update1 = AnonymizedUpdate(
            device_id_hash="a" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=1,
            gradient_deltas=self._encode_floats([100.0, 200.0]),
        )

        result = _fedavg([update1], DataCategory.VOCABULARY)
        agg = self._decode_b64(result["adapter_deltas"])

        l2 = math.sqrt(sum(v * v for v in agg))
        assert l2 <= GRADIENT_MAX_NORM + 1e-4, \
            f"L2 norm {l2} should be <= {GRADIENT_MAX_NORM}"

    def test_fedavg_empty_updates(self):
        result = _fedavg([], DataCategory.VOCABULARY)
        assert result == {}

    def test_fedavg_no_adapter_deltas(self):
        update = AnonymizedUpdate(
            device_id_hash="a" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=1,
            gradient_deltas=None,
        )
        result = _fedavg([update], DataCategory.VOCABULARY)
        assert result.get("adapter_deltas") is None

    def test_fedavg_single_device(self):
        """Single device's deltas should pass through (after clipping)."""
        update = AnonymizedUpdate(
            device_id_hash="a" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=1,
            gradient_deltas=self._encode_floats([0.5, 0.3]),
        )
        result = _fedavg([update], DataCategory.VOCABULARY)
        agg = self._decode_b64(result["adapter_deltas"])

        assert abs(agg[0] - 0.5) < 1e-4
        assert abs(agg[1] - 0.3) < 1e-4

    def test_fedavg_mismatched_lengths(self):
        """Devices with different gradient lengths should be handled."""
        update1 = AnonymizedUpdate(
            device_id_hash="a" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=1,
            gradient_deltas=self._encode_floats([0.1, 0.2, 0.3]),
        )
        update2 = AnonymizedUpdate(
            device_id_hash="b" * 16,
            category=DataCategory.VOCABULARY,
            dialect="sw",
            pattern_count=1,
            gradient_deltas=self._encode_floats([0.4, 0.5]),
        )

        result = _fedavg([update1, update2], DataCategory.VOCABULARY)
        agg = self._decode_b64(result["adapter_deltas"])

        assert len(agg) == 3
        assert abs(agg[0] - 0.25) < 0.01
        assert abs(agg[1] - 0.35) < 0.01
        assert abs(agg[2] - 0.3) < 0.01


# ════════════════════════════════════════════════════════════════════
# FL v1 Weighted LoRA Average Tests
# ════════════════════════════════════════════════════════════════════


class TestFLv1GradientClipping:
    """Test that FL v1 clips gradients to L2 norm 1.0."""

    def test_v1_clip_norm_is_1(self):
        """Verify v1 uses clip norm of 1.0 (was 5.0)."""
        import inspect
        source = inspect.getsource(_mod_fl._secure_aggregate_gradients)
        assert "L2_CLIP_NORM = 1.0" in source, \
            "v1 L2_CLIP_NORM should be 1.0 for tight DP guarantees"

    def test_v1_weighted_lora_average(self):
        """Test v1's weighted LoRA average produces correct weighted mean."""
        raw1 = struct.pack("<2f", 2.0, 4.0)
        raw2 = struct.pack("<2f", 6.0, 12.0)

        result_b64 = _weighted_lora_average([(raw1, 1.0), (raw2, 3.0)])
        raw = base64.b64decode(result_b64)
        values = list(struct.unpack("<2f", raw))

        # Weighted avg: (2*1 + 6*3)/(1+3) = 5.0, (4*1 + 12*3)/(1+3) = 10.0
        assert abs(values[0] - 5.0) < 1e-4
        assert abs(values[1] - 10.0) < 1e-4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
