"""
Intent Classifier Training — Train intent router on Swahili commands.

Uses the training data from IntentTrainingData.kt (exported as JSON)
to train a lightweight intent classification model suitable for
on-device deployment.

Model architecture:
- TF-IDF + Logistic Regression (fast, small, interpretable)
- Optional: DistilBERT multilingual fine-tune (higher accuracy, larger)

Academic basis:
- MLE (STA 341): Multinomial logistic regression via maximum likelihood
- Cross-validation: Model selection and hyperparameter tuning
- Non-parametric: TF-IDF as non-parametric feature extraction
"""

import json
import logging
import math
import os
import pickle
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class IntentExample:
    """A single intent training example."""
    utterance: str
    intent: str
    language: str
    region: str
    confidence: float = 1.0
    entities: dict = field(default_factory=dict)


@dataclass
class IntentClassificationResult:
    """Result of intent classification."""
    intent: str
    confidence: float
    all_scores: dict = field(default_factory=dict)
    language_detected: str = ""


class SwahiliTokenizer:
    """
    Tokenizer for Swahili and Sheng text.
    Handles:
    - Swahili morphology (prefix/suffix splitting)
    - Sheng vocabulary
    - Code-switching boundaries
    """

    # Swahili prefixes to split
    PREFIXES = [
        "nime", "nili", "nta", "niki", "na", "si", "hu",
        "tu", "wa", "m", "ki", "vi", "ma", "ya", "za", "la", "cha",
        "ku", "pa", "mu"
    ]

    # Common stop words to remove
    STOP_WORDS = {
        "na", "ya", "za", "wa", "la", "cha", "kwa", "katika",
        "ni", "si", "hu", "lakini", "au", "ama", "pia", "tena",
        "sasa", "bado", "tayari", "sana", "hii", "huyo", "yule",
        "the", "is", "a", "an", "and", "or", "but", "in", "on", "at"
    }

    def tokenize(self, text: str) -> list[str]:
        """Tokenize text into words, handling Swahili morphology."""
        text = text.lower().strip()
        # Split on whitespace and punctuation
        tokens = re.findall(r"[a-z']+", text)
        # Remove very short tokens
        tokens = [t for t in tokens if len(t) >= 2]
        return tokens

    def tokenize_with_stems(self, text: str) -> list[str]:
        """Tokenize and extract stems (prefix-stripped roots)."""
        tokens = self.tokenize(text)
        stems = []
        for token in tokens:
            stem = self._extract_stem(token)
            stems.append(stem)
        return stems

    def _extract_stem(self, word: str) -> str:
        """Extract stem by removing common prefixes."""
        for prefix in sorted(self.PREFIXES, key=len, reverse=True):
            if word.startswith(prefix) and len(word) > len(prefix) + 2:
                return word[len(prefix):]
        return word


class TFIDFVectorizer:
    """
    TF-IDF vectorizer optimized for Swahili/Sheng text.
    
    Uses subword features to handle Sheng vocabulary evolution.
    """

    def __init__(self, max_features: int = 5000, use_subwords: bool = True):
        self.max_features = max_features
        self.use_subwords = use_subwords
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}
        self._fitted = False

    def fit(self, documents: list[list[str]]) -> 'TFIDFVectorizer':
        """Fit the vectorizer on tokenized documents."""
        # Count document frequencies
        df = Counter()
        for doc in documents:
            unique_tokens = set(doc)
            for token in unique_tokens:
                df[token] += 1
                if self.use_subwords and len(token) > 4:
                    # Add character n-gram features
                    for n in [3, 4]:
                        for i in range(len(token) - n + 1):
                            ngram = f"_{token[i:i+n]}_"
                            df[ngram] += 1

        # Select top features by document frequency
        most_common = df.most_common(self.max_features)
        self.vocabulary = {token: idx for idx, (token, _) in enumerate(most_common)}

        # Compute IDF
        n_docs = len(documents)
        self.idf = {
            token: math.log((n_docs + 1) / (count + 1)) + 1
            for token, count in most_common
        }

        self._fitted = True
        return self

    def transform(self, documents: list[list[str]]) -> np.ndarray:
        """Transform tokenized documents to TF-IDF vectors."""
        if not self._fitted:
            raise RuntimeError("Vectorizer not fitted")

        n_docs = len(documents)
        n_features = len(self.vocabulary)
        matrix = np.zeros((n_docs, n_features), dtype=np.float32)

        for i, doc in enumerate(documents):
            tf = Counter(doc)
            if self.use_subwords:
                for token in doc:
                    if len(token) > 4:
                        for n in [3, 4]:
                            for j in range(len(token) - n + 1):
                                ngram = f"_{token[j:j+n]}_"
                                tf[ngram] += 1

            for token, count in tf.items():
                if token in self.vocabulary:
                    idx = self.vocabulary[token]
                    tfidf = (1 + math.log(count)) * self.idf.get(token, 1.0)
                    matrix[i, idx] = tfidf

            # L2 normalize
            norm = np.linalg.norm(matrix[i])
            if norm > 0:
                matrix[i] /= norm

        return matrix

    def fit_transform(self, documents: list[list[str]]) -> np.ndarray:
        """Fit and transform in one step."""
        return self.fit(documents).transform(documents)


class MultinomialLogisticRegression:
    """
    Multinomial Logistic Regression for intent classification.
    
    Uses gradient descent with L2 regularization.
    
    Academic basis: MLE (STA 341)
    - P(y=k|x) = exp(w_k^T x) / Σ_j exp(w_j^T x)
    - Loss = -Σ log P(y_i|x_i) + λ||W||²
    - Gradient descent optimization
    """

    def __init__(self, n_classes: int, n_features: int,
                 learning_rate: float = 0.01, regularization: float = 0.01,
                 max_iter: int = 1000):
        self.n_classes = n_classes
        self.n_features = n_features
        self.learning_rate = learning_rate
        self.regularization = regularization
        self.max_iter = max_iter
        # Weight matrix: (n_classes, n_features)
        self.weights = np.zeros((n_classes, n_features), dtype=np.float32)
        self.bias = np.zeros(n_classes, dtype=np.float32)
        self.classes: list[str] = []

    def fit(self, X: np.ndarray, y: np.ndarray, classes: list[str]):
        """
        Fit the model using gradient descent.
        
        Args:
            X: Feature matrix (n_samples, n_features)
            y: Class indices (n_samples,)
            classes: List of class labels
        """
        self.classes = classes
        n_samples = X.shape[0]

        for iteration in range(self.max_iter):
            # Forward pass: softmax
            logits = X @ self.weights.T + self.bias
            probs = self._softmax(logits)

            # One-hot encode targets
            y_onehot = np.zeros_like(probs)
            for i in range(n_samples):
                y_onehot[i, y[i]] = 1.0

            # Gradient
            grad_w = (probs - y_onehot).T @ X / n_samples
            grad_b = np.mean(probs - y_onehot, axis=0)

            # L2 regularization
            grad_w += self.regularization * self.weights

            # Update
            self.weights -= self.learning_rate * grad_w
            self.bias -= self.learning_rate * grad_b

            # Log loss
            if iteration % 100 == 0:
                loss = self._compute_loss(probs, y)
                logger.debug(f"Iteration {iteration}: loss={loss:.4f}")

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class indices."""
        logits = X @ self.weights.T + self.bias
        return np.argmax(logits, axis=1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        logits = X @ self.weights.T + self.bias
        return self._softmax(logits)

    def _softmax(self, logits: np.ndarray) -> np.ndarray:
        """Numerically stable softmax."""
        shifted = logits - np.max(logits, axis=1, keepdims=True)
        exp = np.exp(shifted)
        return exp / np.sum(exp, axis=1, keepdims=True)

    def _compute_loss(self, probs: np.ndarray, y: np.ndarray) -> float:
        """Cross-entropy loss."""
        n = len(y)
        log_probs = np.log(probs[np.arange(n), y] + 1e-10)
        return -np.mean(log_probs)


class IntentClassifierTrainer:
    """
    Trains an intent classifier for Swahili/Sheng voice commands.
    
    Pipeline:
    1. Load training data (from IntentTrainingData.kt export)
    2. Tokenize with Swahili-aware tokenizer
    3. Vectorize with TF-IDF (subword features for Sheng)
    4. Train multinomial logistic regression
    5. Evaluate with cross-validation
    6. Export for on-device deployment
    """

    def __init__(self, max_features: int = 5000):
        self.tokenizer = SwahiliTokenizer()
        self.vectorizer = TFIDFVectorizer(max_features=max_features, use_subwords=True)
        self.model: Optional[MultinomialLogisticRegression] = None
        self.intent_labels: list[str] = []
        self.training_data: list[IntentExample] = []

    def load_training_data(self, data_path: str = None,
                           data_list: list[dict] = None) -> int:
        """Load training data from JSON file or list of dicts."""
        if data_path:
            with open(data_path, 'r', encoding='utf-8') as f:
                data_list = json.load(f)

        if data_list is None:
            raise ValueError("Provide data_path or data_list")

        self.training_data = []
        for item in data_list:
            example = IntentExample(
                utterance=item["utterance"],
                intent=item["intent"],
                language=item.get("language", "sw"),
                region=item.get("region", "KE-Nairobi"),
                confidence=item.get("confidence", 1.0),
                entities=item.get("entities", {})
            )
            self.training_data.append(example)

        # Extract intent labels
        self.intent_labels = sorted(set(e.intent for e in self.training_data))
        logger.info(f"Loaded {len(self.training_data)} examples, "
                    f"{len(self.intent_labels)} intents")
        return len(self.training_data)

    def train(self, learning_rate: float = 0.01,
              regularization: float = 0.01,
              max_iter: int = 1000) -> dict:
        """
        Train the intent classifier.
        Returns training metrics.
        """
        if not self.training_data:
            raise ValueError("No training data loaded")

        # Tokenize
        tokenized = [
            self.tokenizer.tokenize(e.utterance) for e in self.training_data
        ]

        # Vectorize
        X = self.vectorizer.fit_transform(tokenized)

        # Encode labels
        label_to_idx = {label: idx for idx, label in enumerate(self.intent_labels)}
        y = np.array([label_to_idx[e.intent] for e in self.training_data])

        # Train
        self.model = MultinomialLogisticRegression(
            n_classes=len(self.intent_labels),
            n_features=X.shape[1],
            learning_rate=learning_rate,
            regularization=regularization,
            max_iter=max_iter
        )
        self.model.fit(X, y, self.intent_labels)

        # Compute training accuracy
        predictions = self.model.predict(X)
        accuracy = np.mean(predictions == y)

        metrics = {
            "accuracy": float(accuracy),
            "n_samples": len(self.training_data),
            "n_classes": len(self.intent_labels),
            "n_features": X.shape[1]
        }

        logger.info(f"Training complete: accuracy={accuracy:.4f}")
        return metrics

    def predict(self, utterance: str) -> IntentClassificationResult:
        """Predict intent for a single utterance."""
        if self.model is None:
            raise RuntimeError("Model not trained")

        tokens = self.tokenizer.tokenize(utterance)
        X = self.vectorizer.transform([tokens])
        probs = self.model.predict_proba(X)[0]

        best_idx = np.argmax(probs)
        return IntentClassificationResult(
            intent=self.intent_labels[best_idx],
            confidence=float(probs[best_idx]),
            all_scores={
                label: float(prob)
                for label, prob in zip(self.intent_labels, probs)
            },
            language_detected=self._detect_language(tokens)
        )

    def cross_validate(self, k: int = 5) -> dict:
        """
        K-fold cross-validation.
        
        Returns mean accuracy and per-fold results.
        """
        from sklearn.model_selection import KFold

        tokenized = [
            self.tokenizer.tokenize(e.utterance) for e in self.training_data
        ]
        X = self.vectorizer.fit_transform(tokenized)
        label_to_idx = {label: idx for idx, label in enumerate(self.intent_labels)}
        y = np.array([label_to_idx[e.intent] for e in self.training_data])

        kf = KFold(n_splits=k, shuffle=True, random_state=42)
        fold_accuracies = []

        for fold, (train_idx, test_idx) in enumerate(kf.split(X)):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            model = MultinomialLogisticRegression(
                n_classes=len(self.intent_labels),
                n_features=X.shape[1],
                max_iter=500
            )
            model.fit(X_train, y_train, self.intent_labels)

            predictions = model.predict(X_test)
            accuracy = np.mean(predictions == y_test)
            fold_accuracies.append(float(accuracy))

            logger.info(f"Fold {fold + 1}: accuracy={accuracy:.4f}")

        return {
            "mean_accuracy": float(np.mean(fold_accuracies)),
            "std_accuracy": float(np.std(fold_accuracies)),
            "fold_accuracies": fold_accuracies
        }

    def export_model(self, output_path: str):
        """Export model for on-device deployment."""
        os.makedirs(output_path, exist_ok=True)

        # Save vectorizer vocabulary
        with open(os.path.join(output_path, "vocabulary.json"), 'w') as f:
            json.dump(self.vectorizer.vocabulary, f)

        # Save model weights
        np.savez(
            os.path.join(output_path, "model_weights.npz"),
            weights=self.model.weights,
            bias=self.model.bias
        )

        # Save intent labels
        with open(os.path.join(output_path, "intent_labels.json"), 'w') as f:
            json.dump(self.intent_labels, f)

        # Save config
        with open(os.path.join(output_path, "config.json"), 'w') as f:
            json.dump({
                "n_classes": len(self.intent_labels),
                "n_features": self.vectorizer.max_features,
                "use_subwords": self.vectorizer.use_subwords
            }, f, indent=2)

        logger.info(f"Model exported to {output_path}")

    def _detect_language(self, tokens: list[str]) -> str:
        """Detect primary language from tokens."""
        sheng_markers = {
            "sasa", "niaje", "mambo", "poa", "msee", "mbogi",
            "thao", "kibaki", "ngiri", "soo"
        }
        sheng_count = sum(1 for t in tokens if t in sheng_markers)
        if sheng_count > len(tokens) * 0.2:
            return "sheng"
        return "sw"


def train_intent_classifier(training_data_path: str = None,
                            training_data: list[dict] = None,
                            output_path: str = "models/intent_classifier") -> dict:
    """Factory function to train and export an intent classifier."""
    trainer = IntentClassifierTrainer()
    trainer.load_training_data(
        data_path=training_data_path,
        data_list=training_data
    )
    metrics = trainer.train()
    cv_results = trainer.cross_validate(k=5)
    trainer.export_model(output_path)

    return {**metrics, "cross_validation": cv_results}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) > 1:
        data_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else "models/intent_classifier"
        results = train_intent_classifier(data_path, output_path=output_path)
        print(json.dumps(results, indent=2))
    else:
        print("Usage: python intent_classifier_training.py <data.json> [output_dir]")
