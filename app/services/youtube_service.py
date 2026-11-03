"""YouTube Data API v3 integration: video metadata + comment collection."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.exceptions import (
    CommentsDisabledError,
    VideoNotFoundError,
    YouTubeApiError,
    YouTubeApiNotConfiguredError,
)

logger = logging.getLogger(__name__)

_API_SERVICE_NAME = "youtube"
_API_VERSION = "v3"


@dataclass
class VideoMetadata:
    video_id: str
    title: str | None
    channel_title: str | None
    channel_id: str | None
    description: str | None
    published_at: datetime | None
    thumbnail_url: str | None
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    comments_disabled: bool = False


@dataclass
class CollectedComment:
    youtube_comment_id: str
    text: str
    author_display_name: str | None
    author_channel_id: str | None
    like_count: int
    published_at: datetime | None
    updated_at: datetime | None
    is_reply: bool = False
    parent_youtube_comment_id: str | None = None


@dataclass
class CollectionResult:
    metadata: VideoMetadata
    comments: list[CollectedComment] = field(default_factory=list)
    truncated: bool = False  # True if more comments existed than the configured limit


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class YouTubeService:
    def __init__(self, api_key: str | None, max_comments: int = 200):
        self._api_key = api_key
        self._max_comments = max_comments
        self._client = None

    def _get_client(self):
        if not self._api_key:
            raise YouTubeApiNotConfiguredError(
                "YOUTUBE_API_KEY is not configured. Set it in your .env file to "
                "enable video/comment collection."
            )
        if self._client is None:
            self._client = build(
                _API_SERVICE_NAME, _API_VERSION, developerKey=self._api_key, cache_discovery=False
            )
        return self._client

    def fetch_video_metadata(self, video_id: str) -> VideoMetadata:
        client = self._get_client()
        try:
            response = (
                client.videos()
                .list(part="snippet,statistics,status", id=video_id)
                .execute()
            )
        except HttpError as exc:
            raise YouTubeApiError(self._describe_http_error(exc)) from exc

        items = response.get("items", [])
        if not items:
            raise VideoNotFoundError(
                f"Video '{video_id}' was not found, is private, or has been removed."
            )

        item = items[0]
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        thumbnails = snippet.get("thumbnails", {})
        best_thumb = thumbnails.get("high") or thumbnails.get("default") or {}

        comments_disabled = "commentCount" not in statistics

        return VideoMetadata(
            video_id=video_id,
            title=snippet.get("title"),
            channel_title=snippet.get("channelTitle"),
            channel_id=snippet.get("channelId"),
            description=snippet.get("description"),
            published_at=_parse_dt(snippet.get("publishedAt")),
            thumbnail_url=best_thumb.get("url"),
            view_count=_safe_int(statistics.get("viewCount")),
            like_count=_safe_int(statistics.get("likeCount")),
            comment_count=_safe_int(statistics.get("commentCount")),
            comments_disabled=comments_disabled,
        )

    def fetch_comments(
        self, video_id: str, order: str = "time"
    ) -> tuple[list[CollectedComment], bool]:
        """Fetch top-level comments and their replies, up to the configured limit.

        Returns (comments, truncated) where truncated indicates more comments
        were available than the configured max_comments_per_video limit.
        """
        client = self._get_client()
        collected: list[CollectedComment] = []
        truncated = False
        page_token: str | None = None

        try:
            while True:
                remaining = self._max_comments - len(collected)
                if remaining <= 0:
                    truncated = True
                    break

                response = (
                    client.commentThreads()
                    .list(
                        part="snippet,replies",
                        videoId=video_id,
                        maxResults=min(100, max(1, remaining)),
                        pageToken=page_token,
                        textFormat="plainText",
                        order=order,
                    )
                    .execute()
                )

                for thread in response.get("items", []):
                    top_snippet = thread["snippet"]["topLevelComment"]["snippet"]
                    top_id = thread["snippet"]["topLevelComment"]["id"]
                    collected.append(_comment_from_snippet(top_id, top_snippet))

                    if len(collected) >= self._max_comments:
                        truncated = True
                        break

                    reply_items = thread.get("replies", {}).get("comments", [])
                    for reply in reply_items:
                        if len(collected) >= self._max_comments:
                            truncated = True
                            break
                        reply_snippet = reply["snippet"]
                        collected.append(
                            _comment_from_snippet(
                                reply["id"],
                                reply_snippet,
                                is_reply=True,
                                parent_id=top_id,
                            )
                        )

                if truncated:
                    break

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        except HttpError as exc:
            if exc.resp.status == 403 and "commentsDisabled" in str(exc):
                raise CommentsDisabledError(
                    f"Comments are disabled for video '{video_id}'."
                ) from exc
            raise YouTubeApiError(self._describe_http_error(exc)) from exc

        return collected, truncated

    def collect(self, video_id: str, order: str = "time") -> CollectionResult:
        metadata = self.fetch_video_metadata(video_id)
        if metadata.comments_disabled:
            raise CommentsDisabledError(
                f"Comments are disabled for video '{video_id}'."
            )

        comments, truncated = self.fetch_comments(video_id, order=order)
        return CollectionResult(metadata=metadata, comments=comments, truncated=truncated)

    @staticmethod
    def _describe_http_error(exc: HttpError) -> str:
        status = getattr(exc.resp, "status", "unknown")
        reason = ""
        try:
            reason = exc.error_details[0].get("reason", "") if exc.error_details else ""
        except Exception:
            pass

        if status == 403 and ("quotaExceeded" in str(exc) or reason == "quotaExceeded"):
            return "YouTube API quota exceeded. Try again later or use a different API key."
        if status == 404:
            return "The requested YouTube resource was not found."
        return f"YouTube API error (status {status}): {exc}"


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _comment_from_snippet(
    comment_id: str, snippet: dict, is_reply: bool = False, parent_id: str | None = None
) -> CollectedComment:
    return CollectedComment(
        youtube_comment_id=comment_id,
        text=snippet.get("textOriginal") or snippet.get("textDisplay") or "",
        author_display_name=snippet.get("authorDisplayName"),
        author_channel_id=(snippet.get("authorChannelId") or {}).get("value"),
        like_count=_safe_int(snippet.get("likeCount")) or 0,
        published_at=_parse_dt(snippet.get("publishedAt")),
        updated_at=_parse_dt(snippet.get("updatedAt")),
        is_reply=is_reply,
        parent_youtube_comment_id=parent_id,
    )
