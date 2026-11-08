"""Domain-specific exceptions used across PodLens services.

Each exception maps to a specific, user-facing error condition so the API
layer can translate it into an appropriate HTTP status code and message
without leaking internal details.
"""
from __future__ import annotations


class PodLensError(Exception):
    """Base class for all PodLens domain errors."""


class InvalidYouTubeUrlError(PodLensError):
    """Raised when a submitted URL is not a valid/supported YouTube video URL."""


class YouTubeApiNotConfiguredError(PodLensError):
    """Raised when the YouTube Data API key is missing."""


class YouTubeApiError(PodLensError):
    """Raised when the YouTube Data API returns an error (quota, network, etc.)."""


class VideoNotFoundError(PodLensError):
    """Raised when the requested video does not exist or is unavailable."""


class CommentsDisabledError(PodLensError):
    """Raised when the video has comments disabled."""


class ModelNotAvailableError(PodLensError):
    """Raised when a required ML model's artifacts are missing or invalid."""


class ModelInferenceError(PodLensError):
    """Raised when inference fails on an otherwise loaded model."""


class LLMNotConfiguredError(PodLensError):
    """Raised when no LLM API key/provider is configured."""


class LLMRequestError(PodLensError):
    """Raised when the LLM API call fails (timeout, rate limit, bad response)."""


class AnalysisNotFoundError(PodLensError):
    """Raised when a requested analysis id does not exist."""


class NotAPodcastError(PodLensError):
    """Raised when the submitted video is classified as non-podcast content."""
