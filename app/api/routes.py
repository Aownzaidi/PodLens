"""FastAPI routes for the PodLens workflow."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    CommentOut,
    CommentsPage,
    DashboardResponse,
    DeleteResponse,
    HistoryItem,
    InsightsOut,
    ReportResponse,
    SentimentStats,
    StatusResponse,
    VideoInfo,
)
from app.config import get_settings
from app.core.exceptions import AnalysisNotFoundError, InvalidYouTubeUrlError, PodLensError
from app.database.connection import get_db, session_scope
from app.database import repository
from app.services import report_service
from app.services.analysis_service import AnalysisPipeline
from app.services.llm_service import LLMService
from app.services.sentiment_service import SentimentService
from app.services.spam_service import SpamService
from app.services.youtube_service import YouTubeService
from app.utils.youtube_url import extract_video_id

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_pipeline() -> AnalysisPipeline:
    """Construct the pipeline with real service implementations.

    Model classifiers are constructed lazily (HuggingFaceTextClassifier loads
    on first predict_batch call), so the app can start even before model
    artifacts are supplied - failures surface per-analysis, not at startup.
    """
    from app.models.model_loader import HuggingFaceTextClassifier

    settings = get_settings()

    youtube_service = YouTubeService(
        api_key=settings.youtube_api_key, max_comments=settings.max_comments_per_video
    )
    spam_classifier = HuggingFaceTextClassifier(
        model_dir=settings.spam_model_dir,
        batch_size=settings.model_inference_batch_size,
        force_cpu=settings.force_cpu,
        explicit_label_map=settings.parsed_spam_label_map(),
        model_name="spam_bert_tiny",
    )
    sentiment_classifier = HuggingFaceTextClassifier(
        model_dir=settings.sentiment_model_dir,
        batch_size=settings.model_inference_batch_size,
        force_cpu=settings.force_cpu,
        explicit_label_map=settings.parsed_sentiment_label_map(),
        model_name="sentiment_roberta",
    )
    llm_service = LLMService(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        provider=settings.llm_provider,
        api_base=settings.llm_api_base,
    )

    return AnalysisPipeline(
        youtube_service=youtube_service,
        spam_service=SpamService(spam_classifier),
        sentiment_service=SentimentService(sentiment_classifier),
        llm_service=llm_service,
    )


def _run_pipeline_background(analysis_id: int, url: str) -> None:
    pipeline = _build_pipeline()
    with session_scope() as db:
        pipeline.run(db, analysis_id, url)


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
def start_analysis(
    payload: AnalyzeRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    try:
        video_id = extract_video_id(payload.url)
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_settings()
    if not settings.youtube_configured:
        raise HTTPException(
            status_code=503,
            detail="YouTube API is not configured on the server (missing YOUTUBE_API_KEY).",
        )

    # Create a placeholder video row if needed so we have something to attach
    # the analysis to immediately; youtube_service.collect() will refresh it.
    from app.models.database_models import AnalysisResult, AnalysisStatus, Video

    existing_video = db.query(Video).filter(Video.video_id == video_id).one_or_none()
    if existing_video is None:
        existing_video = Video(video_id=video_id, url=payload.url)
        db.add(existing_video)
        db.flush()
    else:
        # Prevent duplicate concurrent analysis for the same video if one is active
        active_analysis = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.video_id == existing_video.id,
                AnalysisResult.status.in_([
                    AnalysisStatus.PENDING,
                    AnalysisStatus.COLLECTING,
                    AnalysisStatus.PREPROCESSING,
                    AnalysisStatus.SPAM_DETECTION,
                    AnalysisStatus.SENTIMENT_ANALYSIS,
                    AnalysisStatus.GENERATING_INSIGHTS,
                ]),
            )
            .first()
        )
        if active_analysis:
            return AnalyzeResponse(
                analysis_id=active_analysis.id,
                video_id=video_id,
                status=active_analysis.status.value,
                message="Analysis already in progress. Poll /api/analysis/{id}/status for progress.",
            )

    analysis = repository.create_analysis_result(db, existing_video)
    db.commit()

    background_tasks.add_task(_run_pipeline_background, analysis.id, payload.url)

    return AnalyzeResponse(
        analysis_id=analysis.id,
        video_id=video_id,
        status=analysis.status.value,
        message="Analysis started. Poll /api/analysis/{id}/status for progress.",
    )


@router.get("/analysis/{analysis_id}/status", response_model=StatusResponse)
def get_status(analysis_id: int, db: Session = Depends(get_db)):
    analysis = repository.get_analysis_result(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")

    warnings = json.loads(analysis.warnings) if analysis.warnings else []
    return StatusResponse(
        analysis_id=analysis.id,
        video_id=analysis.video.video_id,
        status=analysis.status.value,
        current_stage=analysis.current_stage,
        error_message=analysis.error_message,
        warnings=warnings,
        created_at=analysis.created_at,
        updated_at=analysis.updated_at,
        completed_at=analysis.completed_at,
    )


def _video_info(video) -> VideoInfo:
    return VideoInfo(
        video_id=video.video_id,
        url=video.url,
        title=video.title,
        channel_title=video.channel_title,
        published_at=video.published_at,
        thumbnail_url=video.thumbnail_url,
        view_count=video.view_count,
        like_count=video.like_count,
        comment_count=video.comment_count,
    )


def _comment_out(view: report_service.CommentView) -> CommentOut:
    return CommentOut(
        id=view.id,
        original_text=view.original_text,
        author_display_name=view.author_display_name,
        like_count=view.like_count,
        published_at=view.published_at,
        is_spam=view.is_spam,
        spam_confidence=view.spam_confidence,
        sentiment_label=view.sentiment_label,
        sentiment_confidence=view.sentiment_confidence,
        is_important=view.is_important,
        importance_score=view.importance_score,
    )


def _insights_out(view: report_service.AnalysisView) -> InsightsOut:
    analysis = view.analysis
    return InsightsOut(
        status=analysis.insights_status or "unavailable",
        audience_summary=analysis.audience_summary,
        discussion_themes=view.discussion_themes,
        future_topics=view.future_topics,
        error=analysis.insights_error,
    )


@router.get("/analysis/{analysis_id}/dashboard", response_model=DashboardResponse)
def get_dashboard(analysis_id: int, db: Session = Depends(get_db)):
    try:
        view = report_service.load_analysis_view(db, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    analysis = view.analysis
    sentiment = SentimentStats(
        positive=analysis.positive_count,
        negative=analysis.negative_count,
        neutral=analysis.neutral_count,
        total_analyzed=analysis.total_comments_analyzed,
    )

    return DashboardResponse(
        analysis_id=analysis.id,
        status=analysis.status.value,
        video=_video_info(view.video),
        total_comments_collected=analysis.total_comments_collected,
        total_comments_analyzed=analysis.total_comments_analyzed,
        spam_count=analysis.spam_count,
        spam_percentage=analysis.spam_percentage,
        sentiment=sentiment,
        important_comments=[_comment_out(c) for c in view.important_comments],
        insights=_insights_out(view),
        warnings=view.warnings,
    )


@router.get("/analysis/{analysis_id}/comments", response_model=CommentsPage)
def get_comments(
    analysis_id: int,
    db: Session = Depends(get_db),
    spam: str | None = Query(default=None, pattern="^(spam|not_spam)$"),
    sentiment: str | None = Query(default=None, pattern="^(positive|negative|neutral)$"),
    search: str | None = Query(default=None, max_length=256),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    try:
        view = report_service.load_analysis_view(db, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    filtered = report_service.filter_comments(
        view.comments, spam_filter=spam, sentiment_filter=sentiment, search=search
    )
    total = len(filtered)
    start = (page - 1) * page_size
    page_items = filtered[start : start + page_size]

    items = [_comment_out(report_service.comment_to_view(c)) for c in page_items]
    return CommentsPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/analysis/{analysis_id}/report", response_model=ReportResponse)
def get_report(analysis_id: int, db: Session = Depends(get_db)):
    try:
        view = report_service.load_analysis_view(db, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    analysis = view.analysis
    sentiment = SentimentStats(
        positive=analysis.positive_count,
        negative=analysis.negative_count,
        neutral=analysis.neutral_count,
        total_analyzed=analysis.total_comments_analyzed,
    )
    is_partial = analysis.status.value in ("partial", "failed")

    return ReportResponse(
        analysis_id=analysis.id,
        status=analysis.status.value,
        generated_at=datetime.now(timezone.utc),
        video=_video_info(view.video),
        total_comments_collected=analysis.total_comments_collected,
        total_comments_analyzed=analysis.total_comments_analyzed,
        spam_count=analysis.spam_count,
        spam_percentage=analysis.spam_percentage,
        sentiment=sentiment,
        important_comments=[_comment_out(c) for c in view.important_comments],
        insights=_insights_out(view),
        warnings=view.warnings,
        is_partial=is_partial,
    )


@router.get("/history", response_model=list[HistoryItem])
def get_history(db: Session = Depends(get_db)):
    """Return all analyzed videos with their latest analysis status and comment count."""
    return repository.get_analysis_history(db)


@router.delete("/history/{video_id}", response_model=DeleteResponse)
def delete_video_history(video_id: str, db: Session = Depends(get_db)):
    """Delete a video and all associated comments, analyses, and results from SQLite."""
    deleted = repository.delete_video_by_video_id(db, video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Video '{video_id}' not found.")
    return DeleteResponse(success=True, message=f"Video '{video_id}' and all its data deleted successfully.")

