"""End-to-end analysis pipeline orchestration.

Runs stages in order, persisting progress after each stage so status can be
polled, and ensures the pipeline never reports COMPLETED if a required
model inference step failed. Partial results (e.g. LLM unavailable) are
reported as PARTIAL with clear warnings rather than silently omitted.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.core.exceptions import (
    CommentsDisabledError,
    InvalidYouTubeUrlError,
    ModelInferenceError,
    ModelNotAvailableError,
    VideoNotFoundError,
    YouTubeApiError,
    YouTubeApiNotConfiguredError,
)
from app.database import repository
from app.models.database_models import AnalysisResult, AnalysisStatus, Comment, SentimentLabel
from app.services.audience_insight_service import (
    AnalyzedCommentForInsights,
    generate_audience_insights,
)
from app.services.importance_service import RankableComment, rank_comments
from app.services.llm_service import LLMService
from app.services.preprocessing_service import preprocess_comments
from app.services.sentiment_service import SentimentService
from app.services.spam_service import SpamService
from app.services.youtube_service import YouTubeService
from app.utils.youtube_url import extract_video_id

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(
        self,
        youtube_service: YouTubeService,
        spam_service: SpamService,
        sentiment_service: SentimentService,
        llm_service: LLMService,
    ):
        self._youtube = youtube_service
        self._spam = spam_service
        self._sentiment = sentiment_service
        self._llm = llm_service

    def run(self, db: Session, analysis_id: int, url: str) -> None:
        analysis = repository.get_analysis_result(db, analysis_id)
        if analysis is None:
            logger.error("Analysis %s not found when starting pipeline", analysis_id)
            return

        warnings: list[str] = []
        try:
            video_id = extract_video_id(url)

            repository.update_analysis_status(
                db, analysis, AnalysisStatus.COLLECTING, current_stage="collecting"
            )
            db.commit()

            # 1. Check whether the video already exists in SQLite
            existing_video = repository.get_video_by_video_id(db, video_id)
            previous_analysis = (
                repository.get_latest_completed_analysis(db, existing_video.id)
                if existing_video
                else None
            )

            # 2. Fetch video metadata and comments from YouTube
            collection = self._youtube.collect(video_id)
            if collection.truncated:
                limit_val = getattr(self._youtube, "_max_comments", 200)
                warnings.append(
                    f"Limited synchronization: checked the most recent {len(collection.comments)} "
                    f"comments up to the configured limit ({limit_val}). "
                    "Additional comments may exist on YouTube."
                )

            video = repository.get_or_create_video(db, collection.metadata, url)
            analysis.video_id = video.id
            db.commit()

            repository.update_analysis_status(
                db, analysis, AnalysisStatus.PREPROCESSING, current_stage="preprocessing"
            )
            db.commit()

            preprocessing = preprocess_comments(collection.comments)
            if preprocessing.invalid_removed or preprocessing.duplicates_removed:
                warnings.append(
                    f"Removed {preprocessing.invalid_removed} invalid/empty and "
                    f"{preprocessing.duplicates_removed} duplicate comments during preprocessing."
                )

            # 3. Categorize and synchronize comments
            all_persisted, new_comments, edited_comments = repository.sync_comments(
                db, video, [(pc.source, pc.processed_text) for pc in preprocessing.valid]
            )
            db.commit()

            # Identify which comments need ML inference:
            # - Brand new comments
            # - Edited comments
            # - Any existing comments lacking an analysis
            comments_needing_inference: list[Comment] = []
            for c in all_persisted:
                if c in new_comments or c in edited_comments:
                    comments_needing_inference.append(c)
                elif c.analysis is None or c.analysis.is_spam is None:
                    comments_needing_inference.append(c)

            all_video_comments = repository.get_comments_for_video(db, video.id)
            total_collected = len(all_video_comments)

            if not all_video_comments:
                repository.finalize_analysis_result(
                    db,
                    analysis,
                    status=AnalysisStatus.PARTIAL,
                    total_comments_collected=0,
                    total_comments_analyzed=0,
                    spam_count=0,
                    spam_percentage=0.0,
                    positive_count=0,
                    negative_count=0,
                    neutral_count=0,
                    important_comment_ids=[],
                    audience_summary=None,
                    discussion_themes=[],
                    future_topics=[],
                    insights_status="unavailable",
                    insights_error="No valid comments to analyze.",
                    warnings=warnings + ["No valid comments remained after preprocessing."],
                )
                db.commit()
                return

            # 4. Check if NO new or edited comments were detected:
            if len(comments_needing_inference) == 0 and previous_analysis is not None:
                logger.info(
                    "No new or edited comments detected for video %s. Reusing previous analysis %s.",
                    video_id,
                    previous_analysis.id,
                )
                prev_warnings = (
                    json.loads(previous_analysis.warnings) if previous_analysis.warnings else []
                )
                combined_warnings = list(
                    dict.fromkeys(
                        warnings
                        + prev_warnings
                        + ["No new or edited comments detected; reused saved analysis."]
                    )
                )
                prev_important_ids = (
                    json.loads(previous_analysis.important_comment_ids)
                    if previous_analysis.important_comment_ids
                    else []
                )
                prev_themes = (
                    json.loads(previous_analysis.discussion_themes)
                    if previous_analysis.discussion_themes
                    else []
                )
                prev_topics = (
                    json.loads(previous_analysis.future_topics)
                    if previous_analysis.future_topics
                    else []
                )

                repository.finalize_analysis_result(
                    db,
                    analysis,
                    status=previous_analysis.status,
                    total_comments_collected=total_collected,
                    total_comments_analyzed=previous_analysis.total_comments_analyzed,
                    spam_count=previous_analysis.spam_count,
                    spam_percentage=previous_analysis.spam_percentage,
                    positive_count=previous_analysis.positive_count,
                    negative_count=previous_analysis.negative_count,
                    neutral_count=previous_analysis.neutral_count,
                    important_comment_ids=prev_important_ids,
                    audience_summary=previous_analysis.audience_summary,
                    discussion_themes=prev_themes,
                    future_topics=prev_topics,
                    insights_status=previous_analysis.insights_status or "unavailable",
                    insights_error=previous_analysis.insights_error,
                    warnings=combined_warnings,
                )
                db.commit()
                return

            # 5. New or edited comments detected: Run incremental ML inference
            # --- Spam detection (ONLY on comments_needing_inference) ---
            repository.update_analysis_status(
                db, analysis, AnalysisStatus.SPAM_DETECTION, current_stage="spam_detection"
            )
            db.commit()

            spam_failed = False
            if comments_needing_inference:
                texts = [c.processed_text for c in comments_needing_inference]
                try:
                    spam_predictions = self._spam.classify_batch(texts)
                except (ModelNotAvailableError, ModelInferenceError) as exc:
                    logger.warning("Spam detection unavailable: %s", exc)
                    warnings.append(f"Spam detection unavailable: {exc}")
                    spam_predictions = [None] * len(comments_needing_inference)
                    spam_failed = True

                for comment, pred in zip(comments_needing_inference, spam_predictions):
                    is_spam = pred.is_spam if pred else None
                    spam_conf = pred.confidence if pred else None
                    repository.save_comment_analysis(
                        db,
                        comment,
                        is_spam=is_spam,
                        spam_confidence=spam_conf,
                        spam_model_version="bert-tiny" if pred else None,
                        sentiment_label=None,
                        sentiment_confidence=None,
                        sentiment_model_version=None,
                        importance_score=None,
                        is_important=False,
                    )
                db.commit()

            new_non_spam = [
                c for c in comments_needing_inference
                if c.analysis and (c.analysis.is_spam is False or c.analysis.is_spam is None)
            ]

            # --- Sentiment analysis (ONLY on new_non_spam) ---
            repository.update_analysis_status(
                db, analysis, AnalysisStatus.SENTIMENT_ANALYSIS, current_stage="sentiment_analysis"
            )
            db.commit()

            sentiment_results: dict[int, tuple[str, float | None]] = {}
            if new_non_spam:
                try:
                    sentiment_preds = self._sentiment.classify_batch(
                        [c.processed_text for c in new_non_spam]
                    )
                    for comment, pred in zip(new_non_spam, sentiment_preds):
                        sentiment_results[comment.id] = (pred.label, pred.confidence)
                except (ModelNotAvailableError, ModelInferenceError) as exc:
                    logger.warning("Sentiment analysis unavailable: %s", exc)
                    warnings.append(f"Sentiment analysis unavailable: {exc}")

                for comment in new_non_spam:
                    label, confidence = sentiment_results.get(comment.id, (None, None))
                    existing = comment.analysis
                    repository.save_comment_analysis(
                        db,
                        comment,
                        is_spam=existing.is_spam if existing else False,
                        spam_confidence=existing.spam_confidence if existing else None,
                        spam_model_version=existing.spam_model_version if existing else None,
                        sentiment_label=label,
                        sentiment_confidence=confidence,
                        sentiment_model_version="roberta" if label else None,
                        importance_score=None,
                        is_important=False,
                    )
                db.commit()

            # 6. Recalculate aggregate stats across ALL stored comments for this video
            all_video_comments = repository.get_comments_for_video(db, video.id)
            total_collected = len(all_video_comments)

            spam_count = sum(1 for c in all_video_comments if c.analysis and c.analysis.is_spam)
            spam_percentage = (
                round(100 * spam_count / total_collected, 1) if total_collected else 0.0
            )

            all_non_spam = [
                c for c in all_video_comments
                if c.analysis and c.analysis.is_spam is False
            ]

            positive_count = sum(
                1 for c in all_non_spam
                if c.analysis and c.analysis.sentiment_label == SentimentLabel.POSITIVE
            )
            negative_count = sum(
                1 for c in all_non_spam
                if c.analysis and c.analysis.sentiment_label == SentimentLabel.NEGATIVE
            )
            neutral_count = sum(
                1 for c in all_non_spam
                if c.analysis and c.analysis.sentiment_label == SentimentLabel.NEUTRAL
            )
            total_analyzed = positive_count + negative_count + neutral_count

            # 7. Re-rank important comments across all non-spam comments
            rankable = [
                RankableComment(
                    comment_id=c.id,
                    text=c.original_text,
                    like_count=c.like_count,
                    reply_count=c.reply_count,
                )
                for c in all_non_spam
            ]
            importance_scores = rank_comments(rankable)
            importance_by_id = {s.comment_id: s for s in importance_scores}

            for comment in all_non_spam:
                score_info = importance_by_id.get(comment.id)
                if comment.analysis:
                    comment.analysis.importance_score = score_info.score if score_info else None
                    comment.analysis.is_important = score_info.is_important if score_info else False
            db.commit()

            important_ids = [s.comment_id for s in importance_scores if s.is_important]

            # 8. Regenerate LLM audience insights for updated non-spam comment set
            repository.update_analysis_status(
                db, analysis, AnalysisStatus.GENERATING_INSIGHTS, current_stage="generating_insights"
            )
            db.commit()

            insight_input = []
            for comment in all_non_spam:
                sentiment_val = (
                    comment.analysis.sentiment_label.value
                    if comment.analysis and comment.analysis.sentiment_label
                    else None
                )
                insight_input.append(
                    AnalyzedCommentForInsights(
                        text=comment.original_text,
                        like_count=comment.like_count,
                        sentiment=sentiment_val,
                        is_spam=False,
                        is_important=comment.analysis.is_important if comment.analysis else False,
                    )
                )

            outcome = generate_audience_insights(
                self._llm,
                video.title,
                insight_input,
                {"positive": positive_count, "negative": negative_count, "neutral": neutral_count},
            )

            if outcome.status == "failed":
                warnings.append(f"Audience insight generation failed: {outcome.error}")
            elif outcome.status == "unavailable":
                warnings.append(f"Audience insights unavailable: {outcome.error}")

            if spam_failed or (not sentiment_results and new_non_spam):
                final_status = AnalysisStatus.PARTIAL
            elif outcome.status != "available":
                final_status = AnalysisStatus.PARTIAL
            else:
                final_status = AnalysisStatus.COMPLETED

            if new_comments or edited_comments:
                warnings.append(
                    f"Incremental update complete: processed {len(new_comments)} new and {len(edited_comments)} edited comments."
                )

            repository.finalize_analysis_result(
                db,
                analysis,
                status=final_status,
                total_comments_collected=total_collected,
                total_comments_analyzed=total_analyzed,
                spam_count=spam_count,
                spam_percentage=spam_percentage,
                positive_count=positive_count,
                negative_count=negative_count,
                neutral_count=neutral_count,
                important_comment_ids=important_ids,
                audience_summary=outcome.insights.audience_summary if outcome.insights else None,
                discussion_themes=outcome.insights.discussion_themes if outcome.insights else [],
                future_topics=outcome.insights.future_topics if outcome.insights else [],
                insights_status=outcome.status,
                insights_error=outcome.error,
                warnings=warnings,
            )
            db.commit()

        except (
            InvalidYouTubeUrlError,
            YouTubeApiNotConfiguredError,
            YouTubeApiError,
            VideoNotFoundError,
            CommentsDisabledError,
        ) as exc:
            logger.warning("Analysis %s failed at collection stage: %s", analysis_id, exc)
            repository.update_analysis_status(
                db, analysis, AnalysisStatus.FAILED, current_stage="collecting", error_message=str(exc)
            )
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive catch-all
            logger.exception("Analysis %s failed unexpectedly", analysis_id)
            repository.update_analysis_status(
                db, analysis, AnalysisStatus.FAILED, error_message=f"Unexpected error: {exc}"
            )
            db.commit()
