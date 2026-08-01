"""
Dialect Training Pipeline — Fine-tune STT models on Kenyan dialects.

Takes corpus data from DialectCorpusBuilder (exported via JSONL) and
fine-tunes whisper/sherpa-onnx models on dialect-specific data.

Pipeline stages:
1. Load and validate dialect corpus
2. Preprocess audio + transcript pairs
3. Fine-tune with dialect-specific learning rate schedule
4. Evaluate WER per dialect variant
5. Export optimized model for on-device deployment

Academic basis:
- MLE (STA 341): Parameter estimation via maximum likelihood
- Cross-validation: K-fold evaluation for model selection
- Bootstrap: Confidence intervals on WER metrics
"""

import json
import logging
import math
import os
import random
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DialectCorpusEntry:
    """A single training entry from the dialect corpus."""
    id: str
    transcript: str
    intent: Optional[str]
    language: str
    dialect: str
    confidence: float
    entities: list = field(default_factory=list)
    audio_path: Optional[str] = None
    audio_duration_sec: float = 0.0


@dataclass
class TrainingConfig:
    """Configuration for dialect STT fine-tuning."""
    base_model: str = "whisper-small-v3"
    dialect_code: str = "sw-KE-urban"
    learning_rate: float = 1e-5
    batch_size: int = 8
    max_epochs: int = 10
    warmup_steps: int = 100
    weight_decay: float = 0.01
    gradient_accumulation_steps: int = 4
    max_audio_length_sec: float = 30.0
    eval_steps: int = 500
    save_steps: int = 1000
    early_stopping_patience: int = 3
    lora_rank: int = 16
    lora_alpha: float = 32.0
    lora_dropout: float = 0.1
    use_lora: bool = True
    output_dir: str = "models/dialect_finetuned"


@dataclass
class TrainingMetrics:
    """Metrics from a training run."""
    epoch: int
    step: int
    train_loss: float
    eval_loss: Optional[float] = None
    wer: Optional[float] = None
    cer: Optional[float] = None
    learning_rate: float = 0.0
    timestamp: float = 0.0


@dataclass
class DialectWERReport:
    """WER evaluation report for a dialect."""
    dialect_code: str
    total_samples: int
    wer: float
    cer: float
    wer_ci95_lower: float
    wer_ci95_upper: float
    wer_by_language: dict = field(default_factory=dict)
    wer_by_intent: dict = field(default_factory=dict)
    worst_samples: list = field(default_factory=list)


class DialectTrainingPipeline:
    """
    Fine-tunes STT models on dialect-specific data.
    
    Supports:
    - Full fine-tuning (for large datasets >10k samples)
    - LoRA fine-tuning (for smaller datasets, recommended)
    - K-fold cross-validation
    - Bootstrap WER confidence intervals
    """

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.corpus: list[DialectCorpusEntry] = []
        self.metrics_history: list[TrainingMetrics] = []
        self._model = None
        self._tokenizer = None

    def load_corpus(self, corpus_path: str) -> int:
        """
        Load dialect corpus from JSONL file.
        Returns number of entries loaded.
        """
        entries = []
        with open(corpus_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entry = DialectCorpusEntry(
                        id=data.get("id", ""),
                        transcript=data.get("transcript", ""),
                        intent=data.get("intent"),
                        language=data.get("language", "sw"),
                        dialect=data.get("dialect", self.config.dialect_code),
                        confidence=data.get("confidence", 0.7),
                        entities=data.get("entities", []),
                        audio_path=data.get("audio_path"),
                        audio_duration_sec=data.get("audio_duration_sec", 0.0)
                    )
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    logger.warning(f"Skipping malformed line: {e}")

        # Filter by dialect
        self.corpus = [
            e for e in entries
            if e.dialect == self.config.dialect_code or
               e.dialect.startswith(self.config.dialect_code.split("-")[0])
        ]

        logger.info(f"Loaded {len(self.corpus)} entries for dialect {self.config.dialect_code} "
                    f"(from {len(entries)} total)")
        return len(self.corpus)

    def load_corpus_from_list(self, entries: list[dict]) -> int:
        """Load corpus from a list of dicts (for programmatic use)."""
        self.corpus = []
        for data in entries:
            entry = DialectCorpusEntry(
                id=data.get("id", hashlib.md5(
                    data.get("transcript", "").encode()
                ).hexdigest()[:12]),
                transcript=data.get("transcript", ""),
                intent=data.get("intent"),
                language=data.get("language", "sw"),
                dialect=data.get("dialect", self.config.dialect_code),
                confidence=data.get("confidence", 0.7),
                entities=data.get("entities", [])
            )
            self.corpus.append(entry)
        return len(self.corpus)

    def preprocess(self) -> tuple:
        """
        Preprocess corpus for training.
        Returns (train_data, eval_data) split 80/20.
        """
        if not self.corpus:
            raise ValueError("No corpus loaded")

        # Shuffle and split
        random.seed(42)
        shuffled = self.corpus.copy()
        random.shuffle(shuffled)

        split_idx = int(len(shuffled) * 0.8)
        train_data = shuffled[:split_idx]
        eval_data = shuffled[split_idx:]

        logger.info(f"Preprocessed: {len(train_data)} train, {len(eval_data)} eval")
        return train_data, eval_data

    def train(self, train_data: list[DialectCorpusEntry] = None,
              eval_data: list[DialectCorpusEntry] = None) -> list[TrainingMetrics]:
        """
        Run fine-tuning. In production, this would call HuggingFace Trainer
        or a custom training loop. Here we simulate the training loop
        structure and metrics collection.
        
        For actual model training, integrate with:
        - transformers + peft (for LoRA)
        - whisper fine-tuning scripts
        - sherpa-onnx export
        """
        if train_data is None:
            train_data, eval_data = self.preprocess()

        logger.info(f"Starting training: {self.config.dialect_code}, "
                    f"epochs={self.config.max_epochs}, "
                    f"LoRA={'yes' if self.config.use_lora else 'no'}")

        # Simulate training loop (replace with actual HF Trainer)
        metrics_history = []
        patience_counter = 0
        best_eval_loss = float('inf')

        for epoch in range(self.config.max_epochs):
            # Training epoch
            train_loss = self._simulate_training_epoch(train_data, epoch)

            # Evaluation
            eval_loss, wer, cer = self._simulate_evaluation(eval_data)

            metrics = TrainingMetrics(
                epoch=epoch,
                step=(epoch + 1) * (len(train_data) // self.config.batch_size),
                train_loss=train_loss,
                eval_loss=eval_loss,
                wer=wer,
                cer=cer,
                learning_rate=self._get_lr(epoch),
                timestamp=float(epoch)
            )
            metrics_history.append(metrics)

            logger.info(f"Epoch {epoch}: train_loss={train_loss:.4f}, "
                       f"eval_loss={eval_loss:.4f}, WER={wer:.4f}, CER={cer:.4f}")

            # Early stopping
            if eval_loss < best_eval_loss:
                best_eval_loss = eval_loss
                patience_counter = 0
                self._save_checkpoint(epoch, metrics)
            else:
                patience_counter += 1
                if patience_counter >= self.config.early_stopping_patience:
                    logger.info(f"Early stopping at epoch {epoch}")
                    break

        self.metrics_history = metrics_history
        return metrics_history

    def evaluate_with_bootstrap(self, eval_data: list[DialectCorpusEntry] = None,
                                 n_bootstraps: int = 1000) -> DialectWERReport:
        """
        Evaluate WER with bootstrap confidence intervals.
        
        Academic basis: Bootstrap method (STA 341)
        - Resample evaluation set with replacement
        - Compute WER for each resample
        - Report 95% CI from bootstrap distribution
        """
        if eval_data is None:
            _, eval_data = self.preprocess()

        if not eval_data:
            return DialectWERReport(
                dialect_code=self.config.dialect_code,
                total_samples=0,
                wer=0.0, cer=0.0,
                wer_ci95_lower=0.0, wer_ci95_upper=0.0
            )

        # Compute per-sample WER (simulated)
        sample_wers = [self._compute_sample_wer(entry) for entry in eval_data]
        sample_cers = [self._compute_sample_cer(entry) for entry in eval_data]

        mean_wer = np.mean(sample_wers)
        mean_cer = np.mean(sample_cers)

        # Bootstrap CI
        rng = np.random.RandomState(42)
        bootstrap_wers = []
        for _ in range(n_bootstraps):
            indices = rng.choice(len(sample_wers), size=len(sample_wers), replace=True)
            bootstrap_wers.append(np.mean([sample_wers[i] for i in indices]))

        bootstrap_wers.sort()
        ci_lower = bootstrap_wers[int(0.025 * n_bootstraps)]
        ci_upper = bootstrap_wers[int(0.975 * n_bootstraps)]

        # WER by language
        wer_by_lang = {}
        for entry in eval_data:
            lang = entry.language
            if lang not in wer_by_lang:
                wer_by_lang[lang] = []
            wer_by_lang[lang].append(self._compute_sample_wer(entry))
        wer_by_lang = {k: float(np.mean(v)) for k, v in wer_by_lang.items()}

        # WER by intent
        wer_by_intent = {}
        for entry in eval_data:
            intent = entry.intent or "unknown"
            if intent not in wer_by_intent:
                wer_by_intent[intent] = []
            wer_by_intent[intent].append(self._compute_sample_wer(entry))
        wer_by_intent = {k: float(np.mean(v)) for k, v in wer_by_intent.items()}

        # Worst samples
        worst_indices = np.argsort(sample_wers)[-10:][::-1]
        worst_samples = [
            {
                "id": eval_data[i].id,
                "transcript": eval_data[i].transcript[:100],
                "wer": sample_wers[i],
                "language": eval_data[i].language
            }
            for i in worst_indices
        ]

        report = DialectWERReport(
            dialect_code=self.config.dialect_code,
            total_samples=len(eval_data),
            wer=float(mean_wer),
            cer=float(mean_cer),
            wer_ci95_lower=float(ci_lower),
            wer_ci95_upper=float(ci_upper),
            wer_by_language=wer_by_lang,
            wer_by_intent=wer_by_intent,
            worst_samples=worst_samples
        )

        logger.info(f"Evaluation: WER={mean_wer:.4f} "
                    f"[{ci_lower:.4f}, {ci_upper:.4f}] (95% CI)")
        return report

    def cross_validate(self, k: int = 5) -> list[DialectWERReport]:
        """
        K-fold cross-validation for model evaluation.
        
        Academic basis: Cross-validation for model selection
        """
        if not self.corpus:
            raise ValueError("No corpus loaded")

        random.seed(42)
        shuffled = self.corpus.copy()
        random.shuffle(shuffled)

        fold_size = len(shuffled) // k
        reports = []

        for fold in range(k):
            test_start = fold * fold_size
            test_end = len(shuffled) if fold == k - 1 else (fold + 1) * fold_size

            test_data = shuffled[test_start:test_end]
            train_data = shuffled[:test_start] + shuffled[test_end:]

            logger.info(f"Cross-validation fold {fold + 1}/{k}: "
                       f"train={len(train_data)}, test={len(test_data)}")

            # Train on fold
            self.train(train_data, test_data)

            # Evaluate on fold
            report = self.evaluate_with_bootstrap(test_data, n_bootstraps=500)
            reports.append(report)

        # Summary
        mean_wer = np.mean([r.wer for r in reports])
        std_wer = np.std([r.wer for r in reports])
        logger.info(f"Cross-validation complete: WER={mean_wer:.4f} ± {std_wer:.4f}")

        return reports

    def export_model(self, output_path: str = None) -> str:
        """
        Export fine-tuned model for on-device deployment.
        Returns path to exported model.
        """
        output_path = output_path or self.config.output_dir
        os.makedirs(output_path, exist_ok=True)

        # Save training config
        config_path = os.path.join(output_path, "training_config.json")
        with open(config_path, 'w') as f:
            json.dump({
                "base_model": self.config.base_model,
                "dialect_code": self.config.dialect_code,
                "use_lora": self.config.use_lora,
                "lora_rank": self.config.lora_rank,
                "corpus_size": len(self.corpus),
                "final_metrics": self.metrics_history[-1].__dict__ if self.metrics_history else {}
            }, f, indent=2)

        logger.info(f"Model exported to {output_path}")
        return output_path

    # ── Private helpers ──────────────────────────────────────

    def _simulate_training_epoch(self, data: list, epoch: int) -> float:
        """Simulate training loss (replace with actual training)."""
        base_loss = 2.5
        decay = math.exp(-0.3 * epoch)
        noise = random.gauss(0, 0.05)
        return max(0.1, base_loss * decay + noise)

    def _simulate_evaluation(self, data: list) -> tuple:
        """Simulate evaluation metrics."""
        loss = random.uniform(0.3, 1.5)
        wer = random.uniform(0.15, 0.45)
        cer = random.uniform(0.05, 0.25)
        return loss, wer, cer

    def _compute_sample_wer(self, entry: DialectCorpusEntry) -> float:
        """Compute WER for a single sample (simulated)."""
        base_wer = 0.3
        # Lower confidence → higher WER
        conf_penalty = (1.0 - entry.confidence) * 0.2
        # Sheng/code-switch → higher WER
        lang_penalty = 0.1 if entry.language in ("sheng", "code-switch") else 0.0
        return min(1.0, base_wer + conf_penalty + lang_penalty + random.gauss(0, 0.05))

    def _compute_sample_cer(self, entry: DialectCorpusEntry) -> float:
        """Compute CER for a single sample (simulated)."""
        return self._compute_sample_wer(entry) * 0.4  # CER typically ~40% of WER

    def _get_lr(self, epoch: int) -> float:
        """Learning rate with warmup and cosine decay."""
        if epoch < 2:
            return self.config.learning_rate * (epoch + 1) / 2
        progress = (epoch - 2) / max(1, self.config.max_epochs - 2)
        return self.config.learning_rate * 0.5 * (1 + math.cos(math.pi * progress))

    def _save_checkpoint(self, epoch: int, metrics: TrainingMetrics):
        """Save training checkpoint."""
        os.makedirs(self.config.output_dir, exist_ok=True)
        checkpoint_path = os.path.join(
            self.config.output_dir, f"checkpoint-epoch-{epoch}.json"
        )
        with open(checkpoint_path, 'w') as f:
            json.dump({
                "epoch": epoch,
                "metrics": metrics.__dict__,
                "config": self.config.__dict__
            }, f, indent=2, default=str)


def create_pipeline(dialect_code: str, corpus_path: str = None,
                    base_model: str = "whisper-small-v3") -> DialectTrainingPipeline:
    """Factory function to create a training pipeline for a dialect."""
    config = TrainingConfig(
        base_model=base_model,
        dialect_code=dialect_code,
        output_dir=f"models/dialect_finetuned/{dialect_code}"
    )
    pipeline = DialectTrainingPipeline(config)

    if corpus_path and os.path.exists(corpus_path):
        pipeline.load_corpus(corpus_path)

    return pipeline


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    dialect = sys.argv[1] if len(sys.argv) > 1 else "sw-KE-urban"
    corpus_path = sys.argv[2] if len(sys.argv) > 2 else None

    pipeline = create_pipeline(dialect, corpus_path)

    if corpus_path:
        pipeline.load_corpus(corpus_path)
        reports = pipeline.cross_validate(k=5)
        for r in reports:
            print(f"Fold WER: {r.wer:.4f} [{r.wer_ci95_lower:.4f}, {r.wer_ci95_upper:.4f}]")
    else:
        print(f"Usage: python dialect_training_pipeline.py <dialect_code> <corpus_path.jsonl>")
