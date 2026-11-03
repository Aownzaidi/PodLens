import pytest

from app.core.exceptions import ModelInferenceError, ModelNotAvailableError
from app.models.model_interfaces import ClassificationPrediction, SentimentClassifier
from app.services.sentiment_service import SentimentService


class MockSentimentClassifier(SentimentClassifier):
    def __init__(self, predictions=None, raise_error=None):
        self._predictions = predictions or []
        self._raise_error = raise_error

    def is_ready(self) -> bool:
        return True

    def predict_batch(self, texts):
        if self._raise_error:
            raise self._raise_error
        return self._predictions


def test_classify_batch_maps_labels_correctly():
    classifier = MockSentimentClassifier(
        predictions=[
            ClassificationPrediction(label="positive", confidence=0.9, raw_label_id=2),
            ClassificationPrediction(label="NEGATIVE", confidence=0.8, raw_label_id=0),
            ClassificationPrediction(label="neutral", confidence=0.6, raw_label_id=1),
        ]
    )
    service = SentimentService(classifier)

    results = service.classify_batch(["Loved it!", "Terrible episode", "It was okay"])

    assert [r.label for r in results] == ["positive", "negative", "neutral"]
    assert results[0].confidence == 0.9


def test_classify_batch_empty_input_returns_empty():
    service = SentimentService(MockSentimentClassifier(predictions=[]))
    assert service.classify_batch([]) == []


def test_classify_batch_raises_on_unexpected_label():
    classifier = MockSentimentClassifier(
        predictions=[ClassificationPrediction(label="LABEL_1", confidence=0.5, raw_label_id=1)]
    )
    service = SentimentService(classifier)

    with pytest.raises(ModelInferenceError):
        service.classify_batch(["some text"])


def test_classify_batch_propagates_model_not_available():
    classifier = MockSentimentClassifier(raise_error=ModelNotAvailableError("missing artifacts"))
    service = SentimentService(classifier)

    with pytest.raises(ModelNotAvailableError):
        service.classify_batch(["some text"])
