"""Sentiment analysis service — wraps the fine-tuned RoBERTa classifier.

Depends only on the SentimentClassifier interface so tests can inject a
mock classifier. Only called on comments that already passed spam filtering.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.exceptions import ModelInferenceError
from app.models.model_interfaces import SentimentClassifier

logger = logging.getLogger(__name__)

_EXPECTED_LABELS = {"positive", "negative", "neutral"}


@dataclass
class SentimentPrediction:
    label: str  # "positive" | "negative" | "neutral"
    confidence: float | None


class SentimentService:
    def __init__(self, classifier: SentimentClassifier):
        self._classifier = classifier

    def classify_batch(self, texts: list[str]) -> list[SentimentPrediction]:
        """Run sentiment classification on a batch of texts.

        Raises ModelNotAvailableError / ModelInferenceError if the model
        cannot produce real predictions - callers must not substitute a
        default sentiment on failure.
        """
        if not texts:
            return []

        predictions = self._classifier.predict_batch(texts)

        results: list[SentimentPrediction] = []
        for pred in predictions:
            normalized = pred.label.strip().lower()
            if normalized not in _EXPECTED_LABELS:
                raise ModelInferenceError(
                    f"Sentiment model returned unexpected label '{pred.label}'. "
                    f"Expected one of {_EXPECTED_LABELS}. Check "
                    "SENTIMENT_LABEL_MAP configuration."
                )
            results.append(SentimentPrediction(label=normalized, confidence=pred.confidence))
        return results
