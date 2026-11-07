"""Podcast content classification service.

Classification pipeline:
  1. Rule-based fast path:
     - Hard-rejects non-podcast YouTube categories (Music=10, Gaming=20, etc.) unless title has podcast keywords.
     - Hard-rejects unambiguous non-podcast formats in title (official music videos, let's play walkthroughs,
       drama serials, soap operas, full movies, daily vlogs, trailers).
     - Hard-rejects extremely short videos (< 3 minutes) unless title has explicit podcast keywords.
     - Fast-accepts videos with explicit podcast branding in title (podcast, vodcast, joe rogan experience, etc.).
  2. If the rule-based step returns UNCERTAIN, the dedicated classifier LLM (Groq) is called
     to evaluate the full metadata (title, channel, duration, category, description)
     and make the final determination: PODCAST, NOT_PODCAST, or UNCERTAIN.

Result labels: "PODCAST" | "NOT_PODCAST" | "UNCERTAIN"
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.services.youtube_service import VideoMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# YouTube category IDs that are fundamentally not podcast content
# See https://developers.google.com/youtube/v3/docs/videoCategories/list
# ---------------------------------------------------------------------------
_NON_PODCAST_CATEGORY_IDS = {
    "1",   # Film & Animation
    "2",   # Autos & Vehicles
    "10",  # Music
    "15",  # Pets & Animals
    "17",  # Sports
    "18",  # Short Movies
    "19",  # Travel & Events
    "20",  # Gaming
    "30",  # Movies
    "31",  # Anime/Animation
    "32",  # Action/Adventure
    "33",  # Classics
    "34",  # Comedy (standalone film)
    "35",  # Documentary (standalone film)
    "36",  # Drama
    "37",  # Family
    "38",  # Foreign
    "39",  # Horror
    "40",  # Sci-Fi/Fantasy
    "41",  # Thriller
    "42",  # Shorts
    "43",  # Shows (TV episodes)
    "44",  # Trailers
}

# ---------------------------------------------------------------------------
# Keyword signals
# ---------------------------------------------------------------------------
# Explicit podcast keywords in title that unambiguously indicate podcast content
_EXPLICIT_PODCAST_KEYWORDS = re.compile(
    r"\b(podcast|podcasts|podcasting|vodcast|videocast|"
    r"joe\s*rogan\s*experience|lex\s*fridman|huberman\s*lab)\b",
    re.IGNORECASE,
)

# Unambiguous non-podcast signals in title.
# NOTE: Do NOT include generic words like "how to", "movie", "film", "drama",
# because podcasts frequently discuss movies/drama or use "How to..." in episode titles.
_NON_PODCAST_TITLE_KEYWORDS = re.compile(
    r"\b("
    # Music & Audio
    r"official\s*music\s*video|official\s*video|official\s*audio|lyrics?\s*video|audio\s*track|full\s*song|remix|live\s*performance|"
    r"mv\b|"
    # Gaming Playthroughs
    r"gameplay\s*walkthrough|let[''s]+\s*play|speedrun\s*world\s*record|"
    # Tutorials & DIY (DO NOT include "how to", but "tutorial" is safe)
    r"tutorial\b|"
    # Vlogs & Personal life
    r"daily\s*vlog|day\s*in\s*my\s*life|travel\s*vlog|"
    # Unboxings
    r"unboxing\s*video|haul\s*video|"
    # Short-form
    r"shorts\b|#shorts|"
    # Trailers & Previews
    r"official\s*trailer|teaser\s*trailer|movie\s*trailer|"
    # Fictional Dramas, Sitcoms, Movies
    r"sitcom\b|drama\s*serial|soap\s*opera|telefilm|telenovela|full\s*movie|short\s*film|"
    # Anime & Cartoons
    r"anime\s*episode|cartoon\s*episode|"
    # Soundtracks
    r"title\s*track|ost\b"
    r")\b",
    re.IGNORECASE,
)

# Minimum duration (in seconds) for a podcast (3 minutes)
_MIN_PODCAST_DURATION_SECONDS = 3 * 60


# ---------------------------------------------------------------------------
# Classification dataclass
# ---------------------------------------------------------------------------
@dataclass
class ClassificationResult:
    label: str        # "PODCAST" | "NOT_PODCAST" | "UNCERTAIN"
    reason: str       # human-readable explanation
    confidence: str = "high"  # "high" | "medium" | "low"

    def __repr__(self) -> str:
        return f"ClassificationResult(label={self.label!r}, reason={self.reason!r})"


# ---------------------------------------------------------------------------
# Rule-based classifier (fast, no network)
# ---------------------------------------------------------------------------
def _rule_based_classify(metadata: VideoMetadata) -> ClassificationResult:
    title = (metadata.title or "").strip()
    category_id = metadata.category_id or ""
    duration = metadata.duration_seconds

    has_podcast_keyword = bool(_EXPLICIT_PODCAST_KEYWORDS.search(title))

    # --- Hard reject: Non-podcast categories (Music, Gaming, Shorts, etc.) ---
    if category_id in _NON_PODCAST_CATEGORY_IDS and not has_podcast_keyword:
        return ClassificationResult(
            "NOT_PODCAST",
            f"YouTube category ID {category_id} is not associated with podcast content.",
        )

    # --- Hard reject: Clear non-podcast signals in TITLE ---
    if _NON_PODCAST_TITLE_KEYWORDS.search(title) and not has_podcast_keyword:
        return ClassificationResult(
            "NOT_PODCAST",
            "Title contains keywords strongly associated with non-podcast content.",
        )

    # --- Hard reject: Under 3 minutes ---
    if duration is not None and duration < _MIN_PODCAST_DURATION_SECONDS and not has_podcast_keyword:
        return ClassificationResult(
            "NOT_PODCAST",
            f"Video duration ({duration}s) is below the minimum length for a podcast.",
        )

    # --- Fast accept: Explicit podcast keyword in title ---
    if has_podcast_keyword and not _NON_PODCAST_TITLE_KEYWORDS.search(title):
        return ClassificationResult(
            "PODCAST",
            "Title explicitly identifies video as podcast content.",
        )

    # Everything else (interviews, talks, ambiguous titles, comedy shows, dramas, etc.)
    # is deferred to the LLM for accurate context-aware classification.
    return ClassificationResult(
        "UNCERTAIN",
        "Insufficient explicit title signals; deferred to LLM for classification.",
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Dedicated LLM Classifier (Groq)
# ---------------------------------------------------------------------------
_LLM_SYSTEM_PROMPT = (
    "You are a strict YouTube content classifier. Your ONLY task is to decide whether "
    "a YouTube video is podcast-style content or not.\n\n"
    "ACCEPT as PODCAST:\n"
    "- Dedicated podcast episodes and video podcasts\n"
    "- Conversational long-form interviews and discussions (e.g. Raj Shamani, Joe Rogan, Lex Fridman, Ranveer Allahbadia, Modern Wisdom, etc.)\n"
    "- Panel discussions, roundtables, and talk shows\n"
    "- In-depth conversational commentary/analysis shows\n\n"
    "REJECT as NOT_PODCAST:\n"
    "- TV drama serials, sitcoms, soap operas, and fictional web series (e.g. Bulbulay, Pakistani/Indian drama serials, comedy sitcoms)\n"
    "- Music videos, songs, and audio tracks\n"
    "- Gaming videos, walkthroughs, and streams\n"
    "- Step-by-step coding/software tutorials, DIY guides, and classroom lectures\n"
    "- Personal daily vlogs and travel vlogs\n"
    "- Unboxings and product reviews\n"
    "- Stand-up comedy specials, comedy sketches, pranks, and parodies\n"
    "- News broadcasts and news bulletins\n"
    "- Movie trailers, teasers, and clips\n"
    "- Short-form content (Shorts, Reels, TikToks)\n\n"
    "Respond ONLY with a single JSON object with these exact keys:\n"
    "{\"label\": \"PODCAST\" | \"NOT_PODCAST\" | \"UNCERTAIN\", \"reason\": \"one concise sentence explaining why\"}"
)


class PodcastClassifierLLM:
    """Lightweight standalone LLM client used ONLY for podcast classification.

    Configured by CLASSIFIER_API_KEY, CLASSIFIER_MODEL, CLASSIFIER_API_BASE
    in .env — completely independent of the audience-insight LLM key.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str,
        api_base: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._api_base = api_base
        self._client = None

    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def _get_client(self):
        if not self.is_configured():
            return None
        if self._client is None:
            from openai import OpenAI
            kwargs: dict = {"api_key": self._api_key}
            if self._api_base:
                kwargs["base_url"] = self._api_base
            self._client = OpenAI(**kwargs)
        return self._client

    def classify(self, metadata: VideoMetadata) -> ClassificationResult:
        client = self._get_client()
        if client is None:
            return ClassificationResult(
                "UNCERTAIN",
                "Classifier API key not configured; cannot confirm classification.",
                confidence="low",
            )

        title = (metadata.title or "(no title)")[:300]
        description = (metadata.description or "(no description)")[:600]
        channel = metadata.channel_title or "unknown channel"
        duration_str = (
            f"{metadata.duration_seconds // 60} minutes"
            if metadata.duration_seconds is not None
            else "unknown"
        )

        user_prompt = (
            f"Title: {title}\n"
            f"Channel: {channel}\n"
            f"Category ID: {metadata.category_id or 'unknown'}\n"
            f"Duration: {duration_str}\n"
            f"Description excerpt: {description}\n\n"
            "Is this a podcast? Reply with JSON only."
        )

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                timeout=15,
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                raise ValueError("Empty response from classifier LLM")
            data = json.loads(content)
            raw_label = str(data.get("label", "UNCERTAIN")).upper().strip()
            label = raw_label if raw_label in ("PODCAST", "NOT_PODCAST", "UNCERTAIN") else "UNCERTAIN"
            reason = str(data.get("reason", "LLM classification.")).strip()
            return ClassificationResult(label, reason, confidence="medium")
        except Exception as exc:
            logger.warning("Podcast classifier LLM call failed: %s", exc)
            return ClassificationResult(
                "UNCERTAIN",
                f"Classifier LLM call failed: {exc}",
                confidence="low",
            )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def classify_podcast(
    metadata: VideoMetadata,
    classifier_llm: PodcastClassifierLLM,
) -> ClassificationResult:
    """Classify a YouTube video as PODCAST, NOT_PODCAST, or UNCERTAIN.

    Uses a fast rule-based pass first. Only calls the dedicated classifier LLM
    (CLASSIFIER_API_KEY) if the rules return UNCERTAIN, minimising API usage.
    """
    result = _rule_based_classify(metadata)
    logger.info(
        "Rule-based classification for '%s': %s — %s",
        metadata.title,
        result.label,
        result.reason,
    )

    if result.label == "UNCERTAIN":
        logger.info(
            "Falling back to classifier LLM for '%s'", metadata.title
        )
        result = classifier_llm.classify(metadata)
        logger.info(
            "Classifier LLM result for '%s': %s — %s",
            metadata.title,
            result.label,
            result.reason,
        )

    return result
