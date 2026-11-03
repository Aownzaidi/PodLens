from datetime import datetime, timezone

from app.database import repository
from app.models.database_models import AnalysisStatus
from app.services.youtube_service import CollectedComment, VideoMetadata


def _metadata(video_id="abc12345678"):
    return VideoMetadata(
        video_id=video_id,
        title="Test Podcast Episode",
        channel_title="Test Channel",
        channel_id="chan1",
        description="desc",
        published_at=datetime.now(timezone.utc),
        thumbnail_url="http://example.com/thumb.jpg",
        view_count=1000,
        like_count=100,
        comment_count=2,
        comments_disabled=False,
    )


def test_get_or_create_video_is_idempotent(db_session):
    video1 = repository.get_or_create_video(db_session, _metadata(), "https://youtu.be/abc12345678")
    db_session.commit()
    video2 = repository.get_or_create_video(db_session, _metadata(), "https://youtu.be/abc12345678")
    db_session.commit()

    assert video1.id == video2.id
    assert db_session.query(type(video1)).count() == 1


def test_upsert_comments_creates_and_updates(db_session):
    video = repository.get_or_create_video(db_session, _metadata(), "https://youtu.be/abc12345678")
    db_session.commit()

    comment = CollectedComment(
        youtube_comment_id="c1",
        text="Great episode!",
        author_display_name="Author",
        author_channel_id="a1",
        like_count=5,
        published_at=datetime.now(timezone.utc),
        updated_at=None,
    )

    persisted = repository.upsert_comments(db_session, video, [(comment, "Great episode!")])
    db_session.commit()
    assert len(persisted) == 1
    assert persisted[0].original_text == "Great episode!"

    # Re-upsert with updated like count should update, not duplicate.
    comment.like_count = 10
    persisted_again = repository.upsert_comments(db_session, video, [(comment, "Great episode!")])
    db_session.commit()

    assert len(persisted_again) == 1
    assert persisted_again[0].like_count == 10
    assert repository.get_comments_for_video(db_session, video.id).__len__() == 1


def test_save_comment_analysis_and_finalize_result(db_session):
    video = repository.get_or_create_video(db_session, _metadata(), "https://youtu.be/abc12345678")
    db_session.commit()

    comment = CollectedComment(
        youtube_comment_id="c1",
        text="Great episode!",
        author_display_name="Author",
        author_channel_id="a1",
        like_count=5,
        published_at=datetime.now(timezone.utc),
        updated_at=None,
    )
    persisted = repository.upsert_comments(db_session, video, [(comment, "Great episode!")])
    db_session.commit()

    repository.save_comment_analysis(
        db_session,
        persisted[0],
        is_spam=False,
        spam_confidence=0.9,
        spam_model_version="bert-tiny",
        sentiment_label="positive",
        sentiment_confidence=0.95,
        sentiment_model_version="roberta",
        importance_score=0.8,
        is_important=True,
    )
    db_session.commit()

    assert persisted[0].analysis.is_spam is False
    assert persisted[0].analysis.sentiment_label.value == "positive"

    analysis_result = repository.create_analysis_result(db_session, video)
    db_session.commit()

    repository.finalize_analysis_result(
        db_session,
        analysis_result,
        status=AnalysisStatus.COMPLETED,
        total_comments_collected=1,
        total_comments_analyzed=1,
        spam_count=0,
        spam_percentage=0.0,
        positive_count=1,
        negative_count=0,
        neutral_count=0,
        important_comment_ids=[persisted[0].id],
        audience_summary="Audience loved it.",
        discussion_themes=["career advice"],
        future_topics=["More guest interviews"],
        insights_status="available",
        insights_error=None,
        warnings=[],
    )
    db_session.commit()

    fetched = repository.get_analysis_result(db_session, analysis_result.id)
    assert fetched.status == AnalysisStatus.COMPLETED
    assert fetched.positive_count == 1
    assert fetched.video_id == video.id
