from datetime import datetime, timezone

from app.database import repository
from app.models.database_models import AnalysisStatus
from app.services import report_service
from app.services.youtube_service import CollectedComment, VideoMetadata


def _setup_video_with_comments(db_session):
    metadata = VideoMetadata(
        video_id="abc12345678",
        title="Test Episode",
        channel_title="Channel",
        channel_id="chan1",
        description=None,
        published_at=datetime.now(timezone.utc),
        thumbnail_url=None,
        view_count=100,
        like_count=10,
        comment_count=2,
        comments_disabled=False,
    )
    video = repository.get_or_create_video(db_session, metadata, "https://youtu.be/abc12345678")
    db_session.commit()

    comments_data = [
        CollectedComment("c1", "Loved this episode!", "A", "a1", 20, datetime.now(timezone.utc), None),
        CollectedComment("c2", "Buy followers now", "B", "b1", 0, datetime.now(timezone.utc), None),
    ]
    persisted = repository.upsert_comments(
        db_session, video, [(c, c.text) for c in comments_data]
    )
    db_session.commit()

    repository.save_comment_analysis(
        db_session, persisted[0], is_spam=False, spam_confidence=0.9, spam_model_version="v1",
        sentiment_label="positive", sentiment_confidence=0.9, sentiment_model_version="v1",
        importance_score=0.9, is_important=True,
    )
    repository.save_comment_analysis(
        db_session, persisted[1], is_spam=True, spam_confidence=0.95, spam_model_version="v1",
        sentiment_label=None, sentiment_confidence=None, sentiment_model_version=None,
        importance_score=None, is_important=False,
    )
    db_session.commit()

    analysis = repository.create_analysis_result(db_session, video)
    repository.finalize_analysis_result(
        db_session, analysis, status=AnalysisStatus.COMPLETED,
        total_comments_collected=2, total_comments_analyzed=1,
        spam_count=1, spam_percentage=50.0,
        positive_count=1, negative_count=0, neutral_count=0,
        important_comment_ids=[persisted[0].id],
        audience_summary="Audience loved it.", discussion_themes=["guest"],
        future_topics=["More guests"], insights_status="available", insights_error=None,
        warnings=[],
    )
    db_session.commit()
    return analysis, persisted


def test_load_analysis_view_returns_important_comments_only(db_session):
    analysis, persisted = _setup_video_with_comments(db_session)

    view = report_service.load_analysis_view(db_session, analysis.id)

    assert len(view.important_comments) == 1
    assert view.important_comments[0].id == persisted[0].id
    assert view.discussion_themes == ["guest"]
    assert view.future_topics == ["More guests"]


def test_filter_comments_spam_only(db_session):
    _, persisted = _setup_video_with_comments(db_session)
    comments = repository.get_comments_for_video(db_session, persisted[0].video_id)

    spam_only = report_service.filter_comments(comments, spam_filter="spam")
    not_spam_only = report_service.filter_comments(comments, spam_filter="not_spam")

    assert len(spam_only) == 1
    assert spam_only[0].analysis.is_spam is True
    assert len(not_spam_only) == 1
    assert not_spam_only[0].analysis.is_spam is False


def test_filter_comments_sentiment_never_matches_spam(db_session):
    _, persisted = _setup_video_with_comments(db_session)
    comments = repository.get_comments_for_video(db_session, persisted[0].video_id)

    positive_only = report_service.filter_comments(comments, sentiment_filter="positive")

    assert len(positive_only) == 1
    assert positive_only[0].analysis.is_spam is False


def test_filter_comments_search(db_session):
    _, persisted = _setup_video_with_comments(db_session)
    comments = repository.get_comments_for_video(db_session, persisted[0].video_id)

    results = report_service.filter_comments(comments, search="loved")
    assert len(results) == 1
    assert "Loved" in results[0].original_text
