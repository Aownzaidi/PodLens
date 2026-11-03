"""Prepares LLM input from real analysis results and orchestrates insight generation.

Keeps the "what goes into the prompt" decision separate from the LLM
transport (llm_service.py) so the selection logic (prioritize non-spam,
important comments first) is independently testable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.exceptions import LLMNotConfiguredError, LLMRequestError
from app.services.llm_service import AudienceInsights, LLMInputComment, LLMService, build_prompt

logger = logging.getLogger(__name__)

_MAX_SAMPLE_COMMENTS = 40


@dataclass
class AnalyzedCommentForInsights:
    text: str
    like_count: int
    sentiment: str | None
    is_spam: bool
    is_important: bool


@dataclass
class InsightsOutcome:
    status: str  # "available" | "unavailable" | "failed"
    insights: AudienceInsights | None
    error: str | None = None


def generate_audience_insights(
    llm_service: LLMService,
    video_title: str | None,
    comments: list[AnalyzedCommentForInsights],
    sentiment_counts: dict[str, int],
) -> InsightsOutcome:
    if not llm_service.is_configured():
        return InsightsOutcome(
            status="unavailable",
            insights=None,
            error="No LLM API key configured; insight generation is unavailable.",
        )

    non_spam = [c for c in comments if not c.is_spam]
    important = [c for c in non_spam if c.is_important]
    sample = [c for c in non_spam if not c.is_important][:_MAX_SAMPLE_COMMENTS]

    important_input = [
        LLMInputComment(text=c.text, like_count=c.like_count, sentiment=c.sentiment)
        for c in important
    ]
    sample_input = [
        LLMInputComment(text=c.text, like_count=c.like_count, sentiment=c.sentiment)
        for c in sample
    ]

    if not important_input and not sample_input:
        return InsightsOutcome(
            status="unavailable",
            insights=None,
            error="No non-spam comments available to summarize.",
        )

    prompt = build_prompt(video_title, sentiment_counts, important_input, sample_input)

    try:
        insights = llm_service.generate_insights(prompt)
        return InsightsOutcome(status="available", insights=insights)
    except (LLMNotConfiguredError, LLMRequestError) as exc:
        logger.warning("LLM insight generation failed: %s", exc)
        return InsightsOutcome(status="failed", insights=None, error=str(exc))
