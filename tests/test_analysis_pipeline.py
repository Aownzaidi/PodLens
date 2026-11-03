from datetime import datetime, timezone

from app.core.exceptions import ModelNotAvailableError
from app.database import repository
from app.models.database_models import AnalysisStatus
from app.models.model_interfaces import ClassificationPrediction
from app.services.analysis_service import AnalysisPipeline
from app.services.llm_service import LLMService
from app.services.sentiment_service import SentimentService
from app.services.spam_service import SpamService
from app.services.youtube_service import CollectedComment, CollectionResult, VideoMetadata


class FakeYouTubeService:
    def __init__(self, comments):
        self._comments = comments

    def collect(self, video_id):
        metadata = VideoMetadata(
            video_id=video_id,
            title="Test Episode",
            channel_title="Channel",
            channel_id="chan1",
            description=None,
            published_at=datetime.now(timezone.utc),
            thumbnail_url=None,
            view_count=100,
            like_count=10,
            comment_count=len(self._comments),
            comments_disabled=False,
        )
        return CollectionResult(metadata=metadata, comments=self._comments, truncated=False)


class FakeClassifier:
    def __init__(self, predictions):
        self._predictions = predictions

    def is_ready(self):
        return True

    def predict_batch(self, texts):
        return self._predictions[: len(texts)]


class AlwaysFailingClassifier:
    def is_ready(self):
        return False

    def predict_batch(self, texts):
        raise ModelNotAvailableError("model artifacts missing")


def _make_comment(ytid, text, likes=1):
    return CollectedComment(
        youtube_comment_id=ytid,
        text=text,
        author_display_name="Author",
        author_channel_id=ytid,
        like_count=likes,
        published_at=datetime.now(timezone.utc),
        updated_at=None,
    )


def test_pipeline_completes_successfully(db_session):
    comments = [
        _make_comment("1", "This episode was fantastic, loved the guest!", likes=50),
        _make_comment("2", "Buy cheap followers at spamsite.com", likes=0),
    ]
    youtube_service = FakeYouTubeService(comments)

    spam_classifier = FakeClassifier(
        [
            ClassificationPrediction(label="not_spam", confidence=0.9, raw_label_id=0),
            ClassificationPrediction(label="spam", confidence=0.95, raw_label_id=1),
        ]
    )
    sentiment_classifier = FakeClassifier(
        [ClassificationPrediction(label="positive", confidence=0.88, raw_label_id=2)]
    )

    pipeline = AnalysisPipeline(
        youtube_service=youtube_service,
        spam_service=SpamService(spam_classifier),
        sentiment_service=SentimentService(sentiment_classifier),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),  # not configured -> unavailable
    )

    from app.models.database_models import Video

    video = Video(video_id="abc12345678", url="https://youtu.be/abc12345678")
    db_session.add(video)
    db_session.flush()
    analysis = repository.create_analysis_result(db_session, video)
    db_session.commit()

    pipeline.run(db_session, analysis.id, "https://youtu.be/abc12345678")

    result = repository.get_analysis_result(db_session, analysis.id)
    # LLM unavailable (no key) -> PARTIAL, not FAILED; spam/sentiment stages succeeded.
    assert result.status == AnalysisStatus.PARTIAL
    assert result.spam_count == 1
    assert result.total_comments_analyzed == 1
    assert result.positive_count == 1
    assert result.insights_status == "unavailable"


def test_pipeline_reports_partial_when_spam_model_unavailable(db_session):
    comments = [_make_comment("1", "This episode was fantastic!", likes=10)]
    youtube_service = FakeYouTubeService(comments)

    pipeline = AnalysisPipeline(
        youtube_service=youtube_service,
        spam_service=SpamService(AlwaysFailingClassifier()),
        sentiment_service=SentimentService(FakeClassifier([])),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )

    from app.models.database_models import Video

    video = Video(video_id="abc12345678", url="https://youtu.be/abc12345678")
    db_session.add(video)
    db_session.flush()
    analysis = repository.create_analysis_result(db_session, video)
    db_session.commit()

    pipeline.run(db_session, analysis.id, "https://youtu.be/abc12345678")

    result = repository.get_analysis_result(db_session, analysis.id)
    assert result.status == AnalysisStatus.PARTIAL
    warnings = result.warnings or ""
    assert "Spam detection unavailable" in warnings


def test_pipeline_fails_cleanly_on_invalid_url(db_session):
    pipeline = AnalysisPipeline(
        youtube_service=FakeYouTubeService([]),
        spam_service=SpamService(FakeClassifier([])),
        sentiment_service=SentimentService(FakeClassifier([])),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )

    from app.models.database_models import Video

    video = Video(video_id="abc12345678", url="not-a-youtube-url")
    db_session.add(video)
    db_session.flush()
    analysis = repository.create_analysis_result(db_session, video)
    db_session.commit()

    pipeline.run(db_session, analysis.id, "not-a-youtube-url")

    result = repository.get_analysis_result(db_session, analysis.id)
    assert result.status == AnalysisStatus.FAILED
    assert result.error_message is not None
