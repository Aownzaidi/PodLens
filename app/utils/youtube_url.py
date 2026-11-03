"""YouTube URL validation and video ID extraction.

Supports the common public URL shapes:
    https://www.youtube.com/watch?v=VIDEO_ID
    https://youtube.com/watch?v=VIDEO_ID&t=10s
    https://youtu.be/VIDEO_ID
    https://www.youtube.com/embed/VIDEO_ID
    https://www.youtube.com/shorts/VIDEO_ID
    https://m.youtube.com/watch?v=VIDEO_ID
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from app.core.exceptions import InvalidYouTubeUrlError

_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")

_ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def _is_valid_video_id(candidate: str) -> bool:
    return bool(_VIDEO_ID_PATTERN.match(candidate))


def extract_video_id(url: str) -> str:
    """Extract and validate the 11-character YouTube video ID from a URL.

    Raises InvalidYouTubeUrlError if the URL is not a recognized/supported
    YouTube video URL or does not contain a well-formed video ID.
    """
    if not url or not url.strip():
        raise InvalidYouTubeUrlError("URL must not be empty.")

    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise InvalidYouTubeUrlError(f"Could not parse URL: {exc}") from exc

    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        pass  # kept as-is, already covered by _ALLOWED_HOSTS
    if host not in _ALLOWED_HOSTS:
        raise InvalidYouTubeUrlError(
            f"'{host or url}' is not a supported YouTube domain."
        )

    video_id: str | None = None

    if host == "youtu.be":
        # https://youtu.be/VIDEO_ID
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            video_id = path_parts[0]
    else:
        path = parsed.path or ""
        if path == "/watch":
            query = parse_qs(parsed.query or "")
            values = query.get("v")
            if values:
                video_id = values[0]
        elif path.startswith("/embed/"):
            video_id = path.split("/embed/", 1)[1].split("/")[0]
        elif path.startswith("/shorts/"):
            video_id = path.split("/shorts/", 1)[1].split("/")[0]
        elif path.startswith("/v/"):
            video_id = path.split("/v/", 1)[1].split("/")[0]

    if not video_id or not _is_valid_video_id(video_id):
        raise InvalidYouTubeUrlError(
            "Could not extract a valid video ID from this URL. Supported "
            "formats: youtube.com/watch?v=..., youtu.be/..., "
            "youtube.com/shorts/..."
        )

    return video_id


def is_valid_youtube_url(url: str) -> bool:
    try:
        extract_video_id(url)
        return True
    except InvalidYouTubeUrlError:
        return False
