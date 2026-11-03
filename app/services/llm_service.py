"""LLM integration for audience summaries and future topic suggestions.

Provider is configurable via environment variables (LLM_PROVIDER, LLM_API_KEY,
LLM_MODEL, LLM_API_BASE). Default/concrete implementation targets OpenAI's
chat completions API. If no API key is configured, callers get a clear
"unavailable" result rather than a fabricated summary.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.core.exceptions import LLMNotConfiguredError, LLMRequestError

logger = logging.getLogger(__name__)

_MAX_COMMENTS_IN_PROMPT = 60
_MAX_COMMENT_CHARS = 300

_SYSTEM_PROMPT = (
    "You are an analyst summarizing audience feedback on a podcast episode "
    "based ONLY on the comments provided. Do not invent opinions, requests, "
    "or facts that are not supported by the given comments. If the comments "
    "do not support a conclusion, omit it rather than guessing. Respond with "
    "strict JSON matching the requested schema."
)

_RESPONSE_SCHEMA_HINT = """
Respond with a single JSON object with exactly these keys:
{
  "audience_summary": "2-4 sentence summary of how the audience reacted overall",
  "discussion_themes": ["short theme phrase", "..."],
  "future_topics": ["suggested future topic grounded in the comments", "..."]
}
Provide at most 6 discussion_themes and at most 6 future_topics. If the
comments do not support any future topic suggestions, return an empty list
for future_topics rather than inventing one.
"""


@dataclass
class AudienceInsights:
    audience_summary: str
    discussion_themes: list[str]
    future_topics: list[str]


@dataclass
class LLMInputComment:
    text: str
    like_count: int
    sentiment: str | None


def build_prompt(
    video_title: str | None,
    sentiment_counts: dict[str, int],
    important_comments: list[LLMInputComment],
    sample_comments: list[LLMInputComment],
) -> str:
    """Build the user-facing prompt from real analysis results only."""
    total = sum(sentiment_counts.values())
    sentiment_summary = (
        f"Out of {total} analyzed (non-spam) comments: "
        f"{sentiment_counts.get('positive', 0)} positive, "
        f"{sentiment_counts.get('negative', 0)} negative, "
        f"{sentiment_counts.get('neutral', 0)} neutral."
    )

    def _format(comments: list[LLMInputComment]) -> str:
        lines = []
        for c in comments[:_MAX_COMMENTS_IN_PROMPT]:
            text = c.text[:_MAX_COMMENT_CHARS]
            sentiment_tag = f"[{c.sentiment}]" if c.sentiment else ""
            lines.append(f"- {sentiment_tag} ({c.like_count} likes) {text}")
        return "\n".join(lines) if lines else "(none)"

    return (
        f"Podcast video title: {video_title or 'Unknown'}\n\n"
        f"Sentiment distribution: {sentiment_summary}\n\n"
        f"Most important/engaged comments:\n{_format(important_comments)}\n\n"
        f"Additional sample of analyzed comments:\n{_format(sample_comments)}\n\n"
        f"{_RESPONSE_SCHEMA_HINT}"
    )


class LLMService:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        provider: str = "openai",
        api_base: str | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._provider = provider
        self._api_base = api_base
        self._client = None

    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _get_client(self):
        if not self.is_configured():
            raise LLMNotConfiguredError(
                "No LLM API key is configured. Set LLM_API_KEY in your .env "
                "file to enable audience insight generation."
            )
        if self._client is None:
            from openai import OpenAI

            kwargs = {"api_key": self._api_key}
            if self._api_base:
                kwargs["base_url"] = self._api_base
            self._client = OpenAI(**kwargs)
        return self._client

    def generate_insights(self, prompt: str) -> AudienceInsights:
        if self._provider != "openai":
            raise LLMNotConfiguredError(
                f"LLM_PROVIDER '{self._provider}' is not supported. Supported: 'openai'."
            )

        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                timeout=30,
            )
        except Exception as exc:
            raise LLMRequestError(f"LLM request failed: {exc}") from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LLMRequestError("LLM returned an empty response.")

        return self._parse_response(content)

    @staticmethod
    def _parse_response(content: str) -> AudienceInsights:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMRequestError(f"LLM response was not valid JSON: {exc}") from exc

        summary = data.get("audience_summary")
        themes = data.get("discussion_themes", [])
        topics = data.get("future_topics", [])

        if not isinstance(summary, str) or not summary.strip():
            raise LLMRequestError("LLM response missing a valid 'audience_summary'.")
        if not isinstance(themes, list):
            raise LLMRequestError("LLM response 'discussion_themes' must be a list.")
        if not isinstance(topics, list):
            raise LLMRequestError("LLM response 'future_topics' must be a list.")

        return AudienceInsights(
            audience_summary=summary.strip(),
            discussion_themes=[str(t).strip() for t in themes if str(t).strip()][:6],
            future_topics=[str(t).strip() for t in topics if str(t).strip()][:6],
        )
