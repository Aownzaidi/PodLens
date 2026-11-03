"""Data-access helpers for PodLens entities.

Thin wrappers around SQLAlchemy session operations, kept separate from
business logic (analysis_service) so persistence concerns don't leak into
the pipeline orchestration code.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.database_models import (
    AnalysisResult,
    AnalysisStatus,
    Comment,
    CommentAnalysis,
    SentimentLabel,
    Video,
)
from app.services.youtube_service import CollectedComment, VideoMetadata


def get_video_by_video_id(db: Session, video_id: str) -> Video | None:
    return db.execute(select(Video).where(Video.video_id == video_id)).scalar_one_or_none()


def get_latest_completed_analysis(db: Session, video_id: int) -> AnalysisResult | None:
    return (
        db.execute(
            select(AnalysisResult)
            .where(
                AnalysisResult.video_id == video_id,
                AnalysisResult.status.in_([AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL]),
            )
            .order_by(AnalysisResult.id.desc())
        )
        .scalars()
        .first()
    )


def get_comments_map_for_video(db: Session, video_id: int) -> dict[str, Comment]:
    comments = get_comments_for_video(db, video_id)
    return {c.youtube_comment_id: c for c in comments}


def get_or_create_video(db: Session, metadata: VideoMetadata, url: str) -> Video:
    existing = db.execute(
        select(Video).where(Video.video_id == metadata.video_id)
    ).scalar_one_or_none()

    if existing:
        existing.title = metadata.title
        existing.channel_title = metadata.channel_title
        existing.channel_id = metadata.channel_id
        existing.description = metadata.description
        existing.published_at = metadata.published_at
        existing.thumbnail_url = metadata.thumbnail_url
        existing.view_count = metadata.view_count
        existing.like_count = metadata.like_count
        existing.comment_count = metadata.comment_count
        existing.comments_disabled = metadata.comments_disabled
        db.flush()
        return existing

    video = Video(
        video_id=metadata.video_id,
        url=url,
        title=metadata.title,
        channel_title=metadata.channel_title,
        channel_id=metadata.channel_id,
        description=metadata.description,
        published_at=metadata.published_at,
        thumbnail_url=metadata.thumbnail_url,
        view_count=metadata.view_count,
        like_count=metadata.like_count,
        comment_count=metadata.comment_count,
        comments_disabled=metadata.comments_disabled,
    )
    db.add(video)
    db.flush()
    return video


def sync_comments(
    db: Session, video: Video, comments: list[tuple[CollectedComment, str]]
) -> tuple[list[Comment], list[Comment], list[Comment]]:
    """Synchronize incoming comments with stored comments for the video.

    Returns:
        (all_persisted, new_comments, edited_comments)
    Never deletes stored comments.
    """
    existing_rows = db.execute(
        select(Comment).where(Comment.video_id == video.id)
    ).scalars().all()
    existing_by_ytid = {c.youtube_comment_id: c for c in existing_rows}

    all_persisted: list[Comment] = []
    new_comments: list[Comment] = []
    edited_comments: list[Comment] = []

    for source, processed_text in comments:
        existing = existing_by_ytid.get(source.youtube_comment_id)
        if existing:
            text_changed = (
                existing.original_text != source.text
                or existing.processed_text != processed_text
            )
            if text_changed:
                existing.original_text = source.text
                existing.processed_text = processed_text
                existing.updated_at = source.updated_at or datetime.now(timezone.utc)
                existing.like_count = source.like_count
                edited_comments.append(existing)
            else:
                existing.like_count = source.like_count
                existing.author_display_name = source.author_display_name
                if source.updated_at:
                    existing.updated_at = source.updated_at

            all_persisted.append(existing)
            continue

        comment = Comment(
            video_id=video.id,
            youtube_comment_id=source.youtube_comment_id,
            parent_youtube_comment_id=source.parent_youtube_comment_id,
            is_reply=source.is_reply,
            author_display_name=source.author_display_name,
            author_channel_id=source.author_channel_id,
            original_text=source.text,
            processed_text=processed_text,
            like_count=source.like_count,
            reply_count=0,
            published_at=source.published_at,
            updated_at=source.updated_at,
        )
        db.add(comment)
        new_comments.append(comment)
        all_persisted.append(comment)

    db.flush()
    return all_persisted, new_comments, edited_comments


def upsert_comments(
    db: Session, video: Video, comments: list[tuple[CollectedComment, str]]
) -> list[Comment]:
    """Insert new comments, update existing ones (matched by youtube_comment_id),
    and return the full persisted list for this video's incoming batch."""
    all_persisted, _, _ = sync_comments(db, video, comments)
    return all_persisted


def save_comment_analysis(
    db: Session,
    comment: Comment,
    is_spam: bool | None,
    spam_confidence: float | None,
    spam_model_version: str | None,
    sentiment_label: str | None,
    sentiment_confidence: float | None,
    sentiment_model_version: str | None,
    importance_score: float | None,
    is_important: bool,
) -> CommentAnalysis:
    analysis = comment.analysis
    if analysis is None:
        analysis = CommentAnalysis(comment_id=comment.id)
        db.add(analysis)

    analysis.is_spam = is_spam
    analysis.spam_confidence = spam_confidence
    analysis.spam_model_version = spam_model_version
    analysis.sentiment_label = SentimentLabel(sentiment_label) if sentiment_label else None
    analysis.sentiment_confidence = sentiment_confidence
    analysis.sentiment_model_version = sentiment_model_version
    analysis.importance_score = importance_score
    analysis.is_important = is_important
    analysis.analyzed_at = datetime.now(timezone.utc)
    db.flush()
    return analysis


def create_analysis_result(db: Session, video: Video) -> AnalysisResult:
    result = AnalysisResult(video_id=video.id, status=AnalysisStatus.PENDING)
    db.add(result)
    db.flush()
    return result


def get_analysis_result(db: Session, analysis_id: int) -> AnalysisResult | None:
    return db.get(AnalysisResult, analysis_id)


def update_analysis_status(
    db: Session,
    analysis: AnalysisResult,
    status: AnalysisStatus,
    current_stage: str | None = None,
    error_message: str | None = None,
    warnings: list[str] | None = None,
) -> None:
    analysis.status = status
    if current_stage is not None:
        analysis.current_stage = current_stage
    if error_message is not None:
        analysis.error_message = error_message
    if warnings is not None:
        analysis.warnings = json.dumps(warnings)
    if status in (AnalysisStatus.COMPLETED, AnalysisStatus.PARTIAL, AnalysisStatus.FAILED):
        analysis.completed_at = datetime.now(timezone.utc)
    db.flush()


def finalize_analysis_result(
    db: Session,
    analysis: AnalysisResult,
    status: AnalysisStatus,
    total_comments_collected: int,
    total_comments_analyzed: int,
    spam_count: int,
    spam_percentage: float,
    positive_count: int,
    negative_count: int,
    neutral_count: int,
    important_comment_ids: list[int],
    audience_summary: str | None,
    discussion_themes: list[str],
    future_topics: list[str],
    insights_status: str,
    insights_error: str | None,
    warnings: list[str],
    error_message: str | None = None,
) -> None:
    analysis.status = status
    analysis.total_comments_collected = total_comments_collected
    analysis.total_comments_analyzed = total_comments_analyzed
    analysis.spam_count = spam_count
    analysis.spam_percentage = spam_percentage
    analysis.positive_count = positive_count
    analysis.negative_count = negative_count
    analysis.neutral_count = neutral_count
    analysis.important_comment_ids = json.dumps(important_comment_ids)
    analysis.audience_summary = audience_summary
    analysis.discussion_themes = json.dumps(discussion_themes)
    analysis.future_topics = json.dumps(future_topics)
    analysis.insights_status = insights_status
    analysis.insights_error = insights_error
    analysis.warnings = json.dumps(warnings)
    analysis.error_message = error_message
    analysis.completed_at = datetime.now(timezone.utc)
    db.flush()


def get_comments_for_video(db: Session, video_id: int) -> list[Comment]:
    return (
        db.execute(select(Comment).where(Comment.video_id == video_id))
        .scalars()
        .all()
    )


def get_analysis_history(db: Session) -> list[dict]:
    """Retrieve all analyzed videos along with their latest analysis status and comment count."""
    videos = db.execute(select(Video).order_by(Video.id.desc())).scalars().all()
    history: list[dict] = []

    for v in videos:
        # Latest completed or partial analysis, falling back to most recent
        latest = get_latest_completed_analysis(db, v.id)
        if latest is None:
            latest = (
                db.execute(
                    select(AnalysisResult)
                    .where(AnalysisResult.video_id == v.id)
                    .order_by(AnalysisResult.id.desc())
                )
                .scalars()
                .first()
            )

        comment_count = db.scalar(
            select(func.count(Comment.id)).where(Comment.video_id == v.id)
        ) or 0

        analyzed_at = None
        if latest:
            analyzed_at = latest.completed_at or latest.created_at
        if analyzed_at is None:
            analyzed_at = v.collected_at

        history.append({
            "id": v.id,
            "video_id": v.video_id,
            "url": v.url,
            "title": v.title or f"Video ({v.video_id})",
            "channel_title": v.channel_title,
            "comment_count": comment_count,
            "analyzed_at": analyzed_at,
            "analysis_id": latest.id if latest else None,
            "status": latest.status.value if latest else "pending",
        })

    # Sort newest analyzed first
    history.sort(key=lambda item: item["analyzed_at"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return history


def delete_video_by_video_id(db: Session, video_id: str) -> bool:
    """Delete a video and all associated comments, analyses, and results from SQLite."""
    video = db.execute(select(Video).where(Video.video_id == video_id)).scalar_one_or_none()
    if not video:
        # Check if video_id is numeric database id
        if video_id.isdigit():
            video = db.get(Video, int(video_id))
    if not video:
        return False

    db.delete(video)
    db.commit()
    return True

