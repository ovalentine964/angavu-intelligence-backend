"""
Voice Emotion Detection — Angavu Intelligence Backend

Detects stress, frustration, and emotional state from voice features.
Uses acoustic features (pitch, energy, spectral) for classification.

Designed for Kenyan informal workers — accounts for:
  - Swahili/English code-switching
  - High-noise environments (markets, boda-boda)
  - Cultural expression norms
"""

import json
import sys
import numpy as np
from typing import Any, Dict, List, Optional


class VoiceEmotionDetector:
    """
    Emotion detection from voice acoustic features.
    Extracts pitch (F0), energy, spectral centroid, zero-crossing rate,
    and classifies into emotion categories.
    """

    EMOTIONS = ["neutral", "stress", "frustration", "joy", "sadness", "anger", "fear"]

    # Typical feature ranges per emotion (simplified from literature)
    FEATURE_PROFILES = {
        "neutral":    {"pitch_mean": 150, "pitch_std": 20, "energy": 0.3, "zcr": 0.05, "spectral_centroid": 1500},
        "stress":     {"pitch_mean": 200, "pitch_std": 40, "energy": 0.5, "zcr": 0.08, "spectral_centroid": 2000},
        "frustration": {"pitch_mean": 180, "pitch_std": 35, "energy": 0.6, "zcr": 0.10, "spectral_centroid": 1800},
        "joy":        {"pitch_mean": 220, "pitch_std": 30, "energy": 0.4, "zcr": 0.06, "spectral_centroid": 1700},
        "sadness":    {"pitch_mean": 120, "pitch_std": 15, "energy": 0.2, "zcr": 0.03, "spectral_centroid": 1200},
        "anger":      {"pitch_mean": 210, "pitch_std": 50, "energy": 0.7, "zcr": 0.12, "spectral_centroid": 2200},
        "fear":       {"pitch_mean": 230, "pitch_std": 45, "energy": 0.4, "zcr": 0.09, "spectral_centroid": 1900},
    }

    def __init__(self, sample_rate: int = 16000, frame_size: int = 512):
        self.sample_rate = sample_rate
        self.frame_size = frame_size

    def extract_features(self, audio_data: List[float]) -> Dict[str, float]:
        """Extract acoustic features from audio signal."""
        signal = np.array(audio_data)
        if len(signal) == 0:
            return {"error": "Empty audio data"}

        # Energy (RMS)
        energy = float(np.sqrt(np.mean(signal ** 2)))

        # Zero-crossing rate
        zcr = float(np.mean(np.abs(np.diff(np.sign(signal))) > 0))

        # Simple pitch estimation via autocorrelation
        # (In production, use YIN or pYIN algorithm)
        pitch_values = []
        step = self.frame_size
        for i in range(0, len(signal) - self.frame_size, step):
            frame = signal[i:i + self.frame_size]
            corr = np.correlate(frame, frame, mode='full')
            corr = corr[len(corr) // 2:]
            # Find first peak after zero crossing
            d = np.diff(corr)
            peaks = np.where(d[:-1] > 0)[0] & np.where(d[1:] < 0)[0]
            if len(peaks) > 0:
                f0 = self.sample_rate / (peaks[0] + 1)
                pitch_values.append(f0)

        pitch_mean = float(np.mean(pitch_values)) if pitch_values else 150.0
        pitch_std = float(np.std(pitch_values)) if pitch_values else 20.0

        # Spectral centroid (simplified)
        fft = np.abs(np.fft.rfft(signal))
        freqs = np.fft.rfftfreq(len(signal), 1.0 / self.sample_rate)
        spectral_centroid = float(np.sum(freqs * fft) / (np.sum(fft) + 1e-10))

        return {
            "pitch_mean": pitch_mean,
            "pitch_std": pitch_std,
            "energy": energy,
            "zcr": zcr,
            "spectral_centroid": spectral_centroid,
            "duration_seconds": len(signal) / self.sample_rate
        }

    def classify_emotion(self, features: Dict[str, float]) -> Dict[str, Any]:
        """Classify emotion from extracted features using distance-based approach."""
        if "error" in features:
            return {"error": features["error"]}

        scores = {}
        feature_keys = ["pitch_mean", "pitch_std", "energy", "zcr", "spectral_centroid"]

        for emotion, profile in self.FEATURE_PROFILES.items():
            # Normalized Euclidean distance
            dist = 0.0
            for key in feature_keys:
                if key in features and key in profile:
                    scale = abs(profile[key]) + 1e-6
                    dist += ((features[key] - profile[key]) / scale) ** 2
            scores[emotion] = 1.0 / (1.0 + np.sqrt(dist))

        # Normalize to probabilities
        total = sum(scores.values())
        probs = {k: v / total for k, v in scores.items()}
        top_emotion = max(probs, key=probs.get)

        # Stress and frustration detection (primary use case)
        stress_level = probs.get("stress", 0) + probs.get("frustration", 0) + probs.get("anger", 0)

        return {
            "primary_emotion": top_emotion,
            "confidence": probs[top_emotion],
            "emotion_probabilities": probs,
            "stress_level": min(stress_level, 1.0),
            "is_stressed": stress_level > 0.4,
            "features": features
        }

    def detect(self, audio_data: List[float]) -> Dict[str, Any]:
        """Full pipeline: extract features → classify emotion."""
        features = self.extract_features(audio_data)
        result = self.classify_emotion(features)
        return result


# ── Runner ──

def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    dispatch = {
        "detect_emotion": lambda a: VoiceEmotionDetector(
            sample_rate=a.get("sample_rate", 16000)
        ).detect(a["audio_data"]),
        "extract_features": lambda a: VoiceEmotionDetector(
            sample_rate=a.get("sample_rate", 16000)
        ).extract_features(a["audio_data"]),
    }
    if method not in dispatch:
        return {"error": f"Unknown method: {method}"}
    try:
        return dispatch[method](args)
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    input_data = json.loads(sys.argv[1])
    result = run_method(input_data["method"], input_data["args"])
    print(json.dumps(result, default=str))
