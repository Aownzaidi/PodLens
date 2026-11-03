"""Builds dashboard and report data from persisted analysis results.

Both the dashboard endpoint and the report endpoint call into this module so
they always reflect the same underlying stored results (per spec: report
and dashboard must stay consistent).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import AnalysisNotFoundError
from app.database import repository
from app.models.database_models import AnalysisResult, Comment, Video


@dataclass
class CommentView:
    id: int
    original_text: str
    author_display_name: str | None
    like_count: int
    published_at: object
    is_spam: bool | None
    spam_confidence: float | None
    sentiment_label: str | None
    sentiment_confidence: float | None
    is_important: bool
    importance_score: float | None


@dataclass
class AnalysisView:
    analysis: AnalysisResult
    video: Video
    comments: list[Comment]
    important_comments: list[CommentView]
    warnings: list[str]
    discussion_themes: list[str]
    future_topics: list[str]


def comment_to_view(comment: Comment) -> CommentView:
    analysis = comment.analysis
    return CommentView(
        id=comment.id,
        original_text=comment.original_text,
        author_display_name=comment.author_display_name,
        like_count=comment.like_count,
        published_at=comment.published_at,
        is_spam=analysis.is_spam if analysis else None,
        spam_confidence=analysis.spam_confidence if analysis else None,
        sentiment_label=(analysis.sentiment_label.value if analysis and analysis.sentiment_label else None),
        sentiment_confidence=analysis.sentiment_confidence if analysis else None,
        is_important=analysis.is_important if analysis else False,
        importance_score=analysis.importance_score if analysis else None,
    )


def load_analysis_view(db: Session, analysis_id: int) -> AnalysisView:
    analysis = repository.get_analysis_result(db, analysis_id)
    if analysis is None:
        raise AnalysisNotFoundError(f"Analysis '{analysis_id}' was not found.")

    video = analysis.video
    comments = repository.get_comments_for_video(db, video.id)

    important_ids = set(json.loads(analysis.important_comment_ids) if analysis.important_comment_ids else [])
    important_comments = [
        comment_to_view(c) for c in comments if c.id in important_ids
    ]
    # Keep the dashboard's important-comment ordering stable: highest importance first.
    important_comments.sort(key=lambda c: (c.importance_score or 0), reverse=True)

    warnings = json.loads(analysis.warnings) if analysis.warnings else []
    discussion_themes = json.loads(analysis.discussion_themes) if analysis.discussion_themes else []
    future_topics = json.loads(analysis.future_topics) if analysis.future_topics else []

    return AnalysisView(
        analysis=analysis,
        video=video,
        comments=comments,
        important_comments=important_comments,
        warnings=warnings,
        discussion_themes=discussion_themes,
        future_topics=future_topics,
    )


def filter_comments(
    comments: list[Comment],
    spam_filter: str | None = None,
    sentiment_filter: str | None = None,
    search: str | None = None,
) -> list[Comment]:
    """Apply dashboard/comments-table filters against real stored analysis data.

    spam_filter: "spam" | "not_spam" | None
    sentiment_filter: "positive" | "negative" | "neutral" | None
    Sentiment filtering only ever matches comments that were actually
    analyzed for sentiment (non-spam, successfully classified) - spam
    comments never get a sentiment label by construction.
    """
    result = comments

    if spam_filter == "spam":
        result = [c for c in result if c.analysis and c.analysis.is_spam is True]
    elif spam_filter == "not_spam":
        result = [c for c in result if c.analysis and c.analysis.is_spam is False]

    if sentiment_filter in {"positive", "negative", "neutral"}:
        result = [
            c
            for c in result
            if c.analysis
            and c.analysis.sentiment_label
            and c.analysis.sentiment_label.value == sentiment_filter
        ]

    if search:
        needle = search.strip().lower()
        if needle:
            result = [c for c in result if needle in c.original_text.lower()]

    return result
