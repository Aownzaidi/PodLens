import os
import tempfile
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import repository
from app.models.database_models import (
    AnalysisResult,
    AnalysisStatus,
    Base,
    Comment,
    CommentAnalysis,
    SentimentLabel,
    Video,
)
from app.models.model_interfaces import ClassificationPrediction
from app.services.analysis_service import AnalysisPipeline
from app.services.llm_service import LLMService
from app.services.sentiment_service import SentimentService
from app.services.spam_service import SpamService
from app.services.youtube_service import (
    CollectedComment,
    CollectionResult,
    VideoMetadata,
    YouTubeApiError,
)

VALID_VID = "abc12345678"  # exactly 11 chars
VALID_URL = f"https://www.youtube.com/watch?v={VALID_VID}"


class CountingSpamClassifier:
    def __init__(self):
        self.call_count = 0
        self.classified_texts = []

    def is_ready(self):
        return True

    def predict_batch(self, texts):
        self.call_count += 1
        self.classified_texts.extend(texts)
        results = []
        for text in texts:
            is_spam = "SPAM" in text.upper()
            results.append(
                ClassificationPrediction(
                    label="spam" if is_spam else "not_spam",
                    confidence=0.98 if is_spam else 0.95,
                    raw_label_id=1 if is_spam else 0,
                )
            )
        return results


class CountingSentimentClassifier:
    def __init__(self):
        self.call_count = 0
        self.classified_texts = []

    def is_ready(self):
        return True

    def predict_batch(self, texts):
        self.call_count += 1
        self.classified_texts.extend(texts)
        results = []
        for text in texts:
            if "great" in text.lower() or "love" in text.lower():
                label = "positive"
            elif "bad" in text.lower() or "terrible" in text.lower():
                label = "negative"
            else:
                label = "neutral"
            results.append(
                ClassificationPrediction(
                    label=label,
                    confidence=0.92,
                    raw_label_id=2 if label == "positive" else 0,
                )
            )
        return results


class FailingClassifier:
    def is_ready(self):
        return True

    def predict_batch(self, texts):
        from app.core.exceptions import ModelInferenceError
        raise ModelInferenceError("Simulated ML inference failure")


class MockYouTubeService:
    def __init__(self, comments, metadata=None, fail=False):
        self.comments = list(comments)
        self.metadata = metadata or VideoMetadata(
            video_id=VALID_VID,
            title="Podcast Ep 1",
            channel_title="Tech Talk",
            channel_id="chan_1",
            description="A discussion about tech",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="http://example.com/thumb.jpg",
            view_count=5000,
            like_count=300,
            comment_count=len(self.comments),
            comments_disabled=False,
        )
        self.fail = fail
        self._max_comments = 200

    def collect(self, video_id):
        if self.fail:
            raise YouTubeApiError("Simulated YouTube API network failure")
        return CollectionResult(metadata=self.metadata, comments=list(self.comments), truncated=False)


def _make_comment(cid, text, likes=5, updated_at=None):
    return CollectedComment(
        youtube_comment_id=cid,
        text=text,
        author_display_name=f"User_{cid}",
        author_channel_id=f"author_{cid}",
        like_count=likes,
        published_at=datetime.now(timezone.utc),
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# TEST 1 — New Podcast: Analyzed and saved into SQLite
# ---------------------------------------------------------------------------
def test_1_new_podcast_saved_to_sqlite(db_session):
    comments = [
        _make_comment("c1", "Great episode, really loved the discussion!"),
        _make_comment("c2", "Check this link for SPAM free tokens"),
        _make_comment("c3", "The sound quality was somewhat bad"),
    ]
    yt = MockYouTubeService(comments)
    spam_clf = CountingSpamClassifier()
    sentiment_clf = CountingSentimentClassifier()

    pipeline = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(spam_clf),
        sentiment_service=SentimentService(sentiment_clf),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )

    video = Video(video_id=VALID_VID, url=VALID_URL)
    db_session.add(video)
    db_session.flush()
    analysis = repository.create_analysis_result(db_session, video)
    db_session.commit()

    pipeline.run(db_session, analysis.id, video.url)

    # Verify video was saved
    saved_video = repository.get_video_by_video_id(db_session, VALID_VID)
    assert saved_video is not None
    assert saved_video.title == "Podcast Ep 1"

    # Verify all 3 comments are saved with predictions
    saved_comments = repository.get_comments_for_video(db_session, saved_video.id)
    assert len(saved_comments) == 3

    c1 = next(c for c in saved_comments if c.youtube_comment_id == "c1")
    assert c1.analysis.is_spam is False
    assert c1.analysis.sentiment_label == SentimentLabel.POSITIVE

    c2 = next(c for c in saved_comments if c.youtube_comment_id == "c2")
    assert c2.analysis.is_spam is True

    c3 = next(c for c in saved_comments if c.youtube_comment_id == "c3")
    assert c3.analysis.is_spam is False
    assert c3.analysis.sentiment_label == SentimentLabel.NEGATIVE

    # Verify analysis result
    res = repository.get_analysis_result(db_session, analysis.id)
    assert res.status in (AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL)
    assert res.total_comments_collected == 3
    assert res.spam_count == 1
    assert res.positive_count == 1
    assert res.negative_count == 1


# ---------------------------------------------------------------------------
# TEST 2 — Same Podcast, No New Comments: Existing results reused, ML NOT called
# ---------------------------------------------------------------------------
def test_2_same_podcast_no_new_comments_reuses_existing_without_ml(db_session):
    comments = [
        _make_comment("c1", "Great episode, really loved the discussion!"),
        _make_comment("c2", "Check this link for SPAM free tokens"),
    ]
    yt = MockYouTubeService(comments)
    spam_clf = CountingSpamClassifier()
    sentiment_clf = CountingSentimentClassifier()

    pipeline = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(spam_clf),
        sentiment_service=SentimentService(sentiment_clf),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )

    # First run
    video = Video(video_id=VALID_VID, url=VALID_URL)
    db_session.add(video)
    db_session.flush()
    analysis_1 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_1.id, video.url)

    assert spam_clf.call_count == 1
    assert sentiment_clf.call_count == 1

    # Second run for the SAME video with the SAME comments
    analysis_2 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_2.id, video.url)

    # Verify ML models were NOT called again!
    assert spam_clf.call_count == 1, "Spam classifier should NOT be called when no comments changed"
    assert sentiment_clf.call_count == 1, "Sentiment classifier should NOT be called when no comments changed"

    # Verify analysis_2 reused previous results
    res_2 = repository.get_analysis_result(db_session, analysis_2.id)
    assert res_2.total_comments_collected == 2
    assert res_2.spam_count == 1
    assert res_2.positive_count == 1
    warnings = res_2.warnings or ""
    assert "No new or edited comments detected" in warnings


# ---------------------------------------------------------------------------
# TEST 3 — Same Podcast, New Comments: Only new comments are classified
# ---------------------------------------------------------------------------
def test_3_same_podcast_incremental_new_comments_only(db_session):
    initial_comments = [
        _make_comment("c1", "Great episode, really loved the discussion!"),
    ]
    yt = MockYouTubeService(initial_comments)
    spam_clf = CountingSpamClassifier()
    sentiment_clf = CountingSentimentClassifier()

    pipeline = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(spam_clf),
        sentiment_service=SentimentService(sentiment_clf),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )

    # First run: 1 comment
    video = Video(video_id=VALID_VID, url=VALID_URL)
    db_session.add(video)
    db_session.flush()
    analysis_1 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_1.id, video.url)

    assert len(spam_clf.classified_texts) == 1

    # 2 new comments arrive (total 3 comments)
    yt.comments.append(_make_comment("c2", "Another SPAM comment here"))
    yt.comments.append(_make_comment("c3", "I love this host, great insights"))

    analysis_2 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_2.id, video.url)

    # Verify spam classifier was called on ONLY the 2 new comments in the second batch
    assert spam_clf.call_count == 2
    # Total classified across both runs should be 1 + 2 = 3 (NOT 1 + 3 = 4)
    assert len(spam_clf.classified_texts) == 3

    # Total comments in DB should now be 3
    all_comments = repository.get_comments_for_video(db_session, video.id)
    assert len(all_comments) == 3

    # Verify overall aggregated stats reflect all 3 comments
    res_2 = repository.get_analysis_result(db_session, analysis_2.id)
    assert res_2.total_comments_collected == 3
    assert res_2.spam_count == 1
    assert res_2.positive_count == 2


# ---------------------------------------------------------------------------
# TEST 4 — Duplicate Prevention: Multiple runs do not insert duplicates
# ---------------------------------------------------------------------------
def test_4_duplicate_prevention_across_multiple_runs(db_session):
    comments = [
        _make_comment("c1", "First comment"),
        _make_comment("c2", "Second comment"),
    ]
    yt = MockYouTubeService(comments)
    pipeline = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(CountingSpamClassifier()),
        sentiment_service=SentimentService(CountingSentimentClassifier()),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )

    video = Video(video_id=VALID_VID, url=VALID_URL)
    db_session.add(video)
    db_session.flush()

    for i in range(3):
        analysis = repository.create_analysis_result(db_session, video)
        db_session.commit()
        pipeline.run(db_session, analysis.id, video.url)

    # Verify exactly 2 comments exist for this video in DB
    all_comments = repository.get_comments_for_video(db_session, video.id)
    assert len(all_comments) == 2

    # Verify video table only has 1 record
    video_count = db_session.query(Video).filter(Video.video_id == VALID_VID).count()
    assert video_count == 1


# ---------------------------------------------------------------------------
# TEST 5 — Database Persistence: Data persists after closing & reopening SQLite
# ---------------------------------------------------------------------------
def test_5_database_persistence_across_restart(tmp_path):
    db_file = tmp_path / "test_persist.db"
    db_url = f"sqlite:///{db_file}"

    # First session: insert and analyze
    engine_1 = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine_1)
    Session_1 = sessionmaker(bind=engine_1)

    with Session_1() as db:
        yt = MockYouTubeService([_make_comment("c1", "Great podcast episode!")])
        pipeline = AnalysisPipeline(
            youtube_service=yt,
            spam_service=SpamService(CountingSpamClassifier()),
            sentiment_service=SentimentService(CountingSentimentClassifier()),
            llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
        )
        video = Video(video_id=VALID_VID, url=VALID_URL)
        db.add(video)
        db.flush()
        analysis = repository.create_analysis_result(db, video)
        db.commit()
        pipeline.run(db, analysis.id, video.url)

    engine_1.dispose()

    # Second session: simulating restart of FastAPI and running init_db()
    engine_2 = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine_2)  # init_db creates missing, keeps existing
    Session_2 = sessionmaker(bind=engine_2)

    with Session_2() as db:
        video_reloaded = repository.get_video_by_video_id(db, VALID_VID)
        assert video_reloaded is not None
        assert video_reloaded.title == "Podcast Ep 1"

        comments_reloaded = repository.get_comments_for_video(db, video_reloaded.id)
        assert len(comments_reloaded) == 1
        assert comments_reloaded[0].original_text == "Great podcast episode!"
        assert comments_reloaded[0].analysis.sentiment_label == SentimentLabel.POSITIVE

        analyses = db.query(AnalysisResult).filter(AnalysisResult.video_id == video_reloaded.id).all()
        assert len(analyses) == 1
        assert analyses[0].status in (AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL)

    engine_2.dispose()


# ---------------------------------------------------------------------------
# TEST 6 — Edited Comment: Text and predictions updated without creating duplicates
# ---------------------------------------------------------------------------
def test_6_edited_comment_updates_text_and_reruns_prediction(db_session):
    comments = [
        _make_comment("c1", "This was a great episode!"),
    ]
    yt = MockYouTubeService(comments)
    spam_clf = CountingSpamClassifier()
    sentiment_clf = CountingSentimentClassifier()

    pipeline = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(spam_clf),
        sentiment_service=SentimentService(sentiment_clf),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )

    video = Video(video_id=VALID_VID, url=VALID_URL)
    db_session.add(video)
    db_session.flush()
    analysis_1 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_1.id, video.url)

    c1 = repository.get_comments_for_video(db_session, video.id)[0]
    assert c1.analysis.sentiment_label == SentimentLabel.POSITIVE

    # Author edits their comment on YouTube to express negative sentiment
    edited_time = datetime.now(timezone.utc)
    yt.comments = [
        _make_comment("c1", "Actually this was terrible and bad quality", updated_at=edited_time),
    ]

    analysis_2 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_2.id, video.url)

    # Verify no duplicate was inserted
    all_comments = repository.get_comments_for_video(db_session, video.id)
    assert len(all_comments) == 1

    # Verify text was updated
    updated_c1 = all_comments[0]
    assert "terrible and bad" in updated_c1.original_text

    # Verify sentiment prediction was updated to NEGATIVE
    assert updated_c1.analysis.sentiment_label == SentimentLabel.NEGATIVE

    # Verify overall analysis reflects the update
    res_2 = repository.get_analysis_result(db_session, analysis_2.id)
    assert res_2.positive_count == 0
    assert res_2.negative_count == 1


# ---------------------------------------------------------------------------
# TEST 7 — API or Inference Failure: Previously stored records remain safe
# ---------------------------------------------------------------------------
def test_7_failure_safety_preserves_stored_records(db_session):
    # Step A: Initial successful run
    comments = [_make_comment("c1", "Great initial comment")]
    yt = MockYouTubeService(comments)
    pipeline = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(CountingSpamClassifier()),
        sentiment_service=SentimentService(CountingSentimentClassifier()),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )
    video = Video(video_id=VALID_VID, url=VALID_URL)
    db_session.add(video)
    db_session.flush()
    analysis_1 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_1.id, video.url)

    assert len(repository.get_comments_for_video(db_session, video.id)) == 1

    # Step B: YouTube API fails during second run
    yt.fail = True
    analysis_2 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis_2.id, video.url)

    # Second analysis marked FAILED
    res_2 = repository.get_analysis_result(db_session, analysis_2.id)
    assert res_2.status == AnalysisStatus.FAILED

    # But previously saved comments remain completely safe and untouched!
    saved_comments = repository.get_comments_for_video(db_session, video.id)
    assert len(saved_comments) == 1
    assert saved_comments[0].original_text == "Great initial comment"
    assert saved_comments[0].analysis.sentiment_label == SentimentLabel.POSITIVE

    # Step C: ML inference fails on new comment
    yt.fail = False
    yt.comments.append(_make_comment("c2", "Brand new comment that triggers ML failure"))
    pipeline_failing_ml = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(FailingClassifier()),
        sentiment_service=SentimentService(CountingSentimentClassifier()),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )
    analysis_3 = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline_failing_ml.run(db_session, analysis_3.id, video.url)

    # Third analysis marked PARTIAL due to ML failure
    res_3 = repository.get_analysis_result(db_session, analysis_3.id)
    assert res_3.status == AnalysisStatus.PARTIAL
    assert "Spam detection unavailable" in (res_3.warnings or "")

    # c1 still has its original valid positive label intact!
    c1_check = next(c for c in repository.get_comments_for_video(db_session, video.id) if c.youtube_comment_id == "c1")
    assert c1_check.analysis.sentiment_label == SentimentLabel.POSITIVE


# ---------------------------------------------------------------------------
# TEST 8 — History & Deletion: Fetch history and delete video from database
# ---------------------------------------------------------------------------
def test_8_history_and_deletion(db_session):
    # Setup video 1 with comments
    comments = [_make_comment("c1", "Love this podcast!"), _make_comment("c2", "Nice host")]
    yt = MockYouTubeService(comments)
    pipeline = AnalysisPipeline(
        youtube_service=yt,
        spam_service=SpamService(CountingSpamClassifier()),
        sentiment_service=SentimentService(CountingSentimentClassifier()),
        llm_service=LLMService(api_key=None, model="gpt-4o-mini"),
    )
    video = Video(video_id=VALID_VID, url=VALID_URL)
    db_session.add(video)
    db_session.flush()
    analysis = repository.create_analysis_result(db_session, video)
    db_session.commit()
    pipeline.run(db_session, analysis.id, video.url)

    # Verify history lists the video
    history = repository.get_analysis_history(db_session)
    assert len(history) == 1
    assert history[0]["video_id"] == VALID_VID
    assert history[0]["comment_count"] == 2
    assert history[0]["title"] == "Podcast Ep 1"

    # Delete the video
    success = repository.delete_video_by_video_id(db_session, VALID_VID)
    assert success is True

    # Verify video, comments, analyses, results are all deleted from SQLite
    assert repository.get_video_by_video_id(db_session, VALID_VID) is None
    assert len(repository.get_comments_for_video(db_session, video.id)) == 0
    assert db_session.query(AnalysisResult).filter(AnalysisResult.video_id == video.id).count() == 0
    assert len(repository.get_analysis_history(db_session)) == 0

