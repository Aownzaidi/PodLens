"""Pydantic request/response schemas for the PodLens API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.utils.youtube_url import is_valid_youtube_url


class AnalyzeRequest(BaseModel):
    url: str = Field(..., min_length=1, description="YouTube podcast video URL")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not is_valid_youtube_url(v):
            raise ValueError(
                "Not a supported YouTube video URL. Expected formats: "
                "youtube.com/watch?v=..., youtu.be/..., youtube.com/shorts/..."
            )
        return v


class AnalyzeResponse(BaseModel):
    analysis_id: int
    video_id: str
    status: str
    message: str


class HistoryItem(BaseModel):
    id: int
    video_id: str
    url: str
    title: Optional[str] = None
    channel_title: Optional[str] = None
    comment_count: int = 0
    analyzed_at: Optional[datetime] = None
    analysis_id: Optional[int] = None
    status: Optional[str] = None


class DeleteResponse(BaseModel):
    success: bool
    message: str


class StatusResponse(BaseModel):
    analysis_id: int
    video_id: str
    status: str
    current_stage: Optional[str] = None
    error_message: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class VideoInfo(BaseModel):
    video_id: str
    url: str
    title: Optional[str] = None
    channel_title: Optional[str] = None
    published_at: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None


class SentimentStats(BaseModel):
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    total_analyzed: int = 0

    @property
    def positive_pct(self) -> float:
        return round(100 * self.positive / self.total_analyzed, 1) if self.total_analyzed else 0.0

    @property
    def negative_pct(self) -> float:
        return round(100 * self.negative / self.total_analyzed, 1) if self.total_analyzed else 0.0

    @property
    def neutral_pct(self) -> float:
        return round(100 * self.neutral / self.total_analyzed, 1) if self.total_analyzed else 0.0


class CommentOut(BaseModel):
    id: int
    original_text: str
    author_display_name: Optional[str] = None
    like_count: int
    published_at: Optional[datetime] = None
    is_spam: Optional[bool] = None
    spam_confidence: Optional[float] = None
    sentiment_label: Optional[str] = None
    sentiment_confidence: Optional[float] = None
    is_important: bool = False
    importance_score: Optional[float] = None


class CommentsPage(BaseModel):
    items: list[CommentOut]
    total: int
    page: int
    page_size: int


class InsightsOut(BaseModel):
    status: str  # "available" | "unavailable" | "failed"
    audience_summary: Optional[str] = None
    discussion_themes: list[str] = Field(default_factory=list)
    future_topics: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class DashboardResponse(BaseModel):
    analysis_id: int
    status: str
    video: VideoInfo
    total_comments_collected: int
    total_comments_analyzed: int
    spam_count: int
    spam_percentage: float
    sentiment: SentimentStats
    important_comments: list[CommentOut]
    insights: InsightsOut
    warnings: list[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    analysis_id: int
    status: str
    generated_at: datetime
    video: VideoInfo
    total_comments_collected: int
    total_comments_analyzed: int
    spam_count: int
    spam_percentage: float
    sentiment: SentimentStats
    important_comments: list[CommentOut]
    insights: InsightsOut
    warnings: list[str] = Field(default_factory=list)
    is_partial: bool = False


class ErrorResponse(BaseModel):
    detail: str
