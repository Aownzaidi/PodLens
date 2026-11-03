import pytest

from app.core.exceptions import ModelInferenceError, ModelNotAvailableError
from app.models.model_interfaces import ClassificationPrediction, SpamClassifier
from app.services.spam_service import SpamService


class MockSpamClassifier(SpamClassifier):
    def __init__(self, predictions=None, raise_error=None):
        self._predictions = predictions or []
        self._raise_error = raise_error

    def is_ready(self) -> bool:
        return True

    def predict_batch(self, texts):
        if self._raise_error:
            raise self._raise_error
        return self._predictions


def test_classify_batch_maps_spam_label_correctly():
    classifier = MockSpamClassifier(
        predictions=[
            ClassificationPrediction(label="spam", confidence=0.95, raw_label_id=1),
            ClassificationPrediction(label="not_spam", confidence=0.88, raw_label_id=0),
        ]
    )
    service = SpamService(classifier)

    results = service.classify_batch(["Buy followers now!", "Great episode, thanks!"])

    assert results[0].is_spam is True
    assert results[0].confidence == 0.95
    assert results[1].is_spam is False
    assert results[1].confidence == 0.88


def test_classify_batch_empty_input_returns_empty():
    service = SpamService(MockSpamClassifier(predictions=[]))
    assert service.classify_batch([]) == []


def test_classify_batch_raises_on_unexpected_label():
    classifier = MockSpamClassifier(
        predictions=[ClassificationPrediction(label="LABEL_0", confidence=0.5, raw_label_id=0)]
    )
    service = SpamService(classifier)

    with pytest.raises(ModelInferenceError):
        service.classify_batch(["some text"])


def test_classify_batch_propagates_model_not_available():
    classifier = MockSpamClassifier(raise_error=ModelNotAvailableError("missing artifacts"))
    service = SpamService(classifier)

    with pytest.raises(ModelNotAvailableError):
        service.classify_batch(["some text"])
