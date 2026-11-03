import pytest

from app.core.exceptions import LLMNotConfiguredError, LLMRequestError
from app.services.audience_insight_service import AnalyzedCommentForInsights, generate_audience_insights
from app.services.llm_service import LLMService


class StubLLMService(LLMService):
    def __init__(self, configured=True, raise_error=None, result=None):
        super().__init__(api_key="fake" if configured else None, model="gpt-4o-mini")
        self._raise_error = raise_error
        self._result = result

    def generate_insights(self, prompt):
        if self._raise_error:
            raise self._raise_error
        return self._result


def test_generate_audience_insights_unavailable_when_not_configured():
    service = StubLLMService(configured=False)
    outcome = generate_audience_insights(service, "Title", [], {})

    assert outcome.status == "unavailable"
    assert outcome.insights is None


def test_generate_audience_insights_unavailable_when_no_comments():
    service = StubLLMService(configured=True)
    outcome = generate_audience_insights(service, "Title", [], {})

    assert outcome.status == "unavailable"
    assert "No non-spam comments" in outcome.error


def test_generate_audience_insights_failed_on_llm_error():
    service = StubLLMService(configured=True, raise_error=LLMRequestError("timeout"))
    comments = [AnalyzedCommentForInsights(text="Great show", like_count=5, sentiment="positive", is_spam=False, is_important=True)]

    outcome = generate_audience_insights(service, "Title", comments, {"positive": 1})

    assert outcome.status == "failed"
    assert "timeout" in outcome.error


def test_generate_audience_insights_success():
    from app.services.llm_service import AudienceInsights

    result = AudienceInsights(
        audience_summary="Listeners enjoyed it.",
        discussion_themes=["career"],
        future_topics=["More interviews"],
    )
    service = StubLLMService(configured=True, result=result)
    comments = [AnalyzedCommentForInsights(text="Great show", like_count=5, sentiment="positive", is_spam=False, is_important=True)]

    outcome = generate_audience_insights(service, "Title", comments, {"positive": 1})

    assert outcome.status == "available"
    assert outcome.insights.audience_summary == "Listeners enjoyed it."


def test_llm_service_raises_when_not_configured():
    service = LLMService(api_key=None, model="gpt-4o-mini")
    with pytest.raises(LLMNotConfiguredError):
        service.generate_insights("some prompt")


def test_llm_service_parse_response_rejects_missing_summary():
    with pytest.raises(LLMRequestError):
        LLMService._parse_response('{"discussion_themes": [], "future_topics": []}')


def test_llm_service_parse_response_valid():
    insights = LLMService._parse_response(
        '{"audience_summary": "Great reception.", "discussion_themes": ["a"], "future_topics": ["b"]}'
    )
    assert insights.audience_summary == "Great reception."
    assert insights.discussion_themes == ["a"]
    assert insights.future_topics == ["b"]
