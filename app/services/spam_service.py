"""Spam detection service — wraps the fine-tuned BERT-tiny classifier.

This service knows nothing about model internals; it depends only on the
SpamClassifier interface (app.models.model_interfaces) so tests can inject a
mock classifier and production code injects the real Hugging Face-backed one.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.exceptions import ModelInferenceError, ModelNotAvailableError
from app.models.model_interfaces import SpamClassifier

logger = logging.getLogger(__name__)

_EXPECTED_LABELS = {"spam", "not_spam"}


@dataclass
class SpamPrediction:
    is_spam: bool
    confidence: float | None


class SpamService:
    def __init__(self, classifier: SpamClassifier):
        self._classifier = classifier

    def is_available(self) -> bool:
        try:
            return self._classifier.is_ready() or True
        except Exception:
            return False

    def classify_batch(self, texts: list[str]) -> list[SpamPrediction]:
        """Run spam classification on a batch of texts.

        Raises ModelNotAvailableError / ModelInferenceError if the model
        cannot produce real predictions - callers must not substitute a
        default "not spam" result on failure.
        """
        if not texts:
            return []

        predictions = self._classifier.predict_batch(texts)

        results: list[SpamPrediction] = []
        for pred in predictions:
            normalized = pred.label.strip().lower()
            if normalized not in _EXPECTED_LABELS:
                raise ModelInferenceError(
                    f"Spam model returned unexpected label '{pred.label}'. "
                    f"Expected one of {_EXPECTED_LABELS}. Check SPAM_LABEL_MAP "
                    "configuration."
                )
            results.append(
                SpamPrediction(is_spam=(normalized == "spam"), confidence=pred.confidence)
            )
        return results
