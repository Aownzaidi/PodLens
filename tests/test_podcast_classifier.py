"""Tests for the podcast content classifier."""
from __future__ import annotations

import pytest

from app.services.podcast_classifier import (
    ClassificationResult,
    PodcastClassifierLLM,
    _rule_based_classify,
    classify_podcast,
)
from app.services.youtube_service import VideoMetadata


def _meta(
    title: str = "",
    description: str = "",
    category_id: str = "22",
    duration_seconds: int | None = 3600,
) -> VideoMetadata:
    return VideoMetadata(
        video_id="abc12345678",
        title=title,
        channel_title="Test Channel",
        channel_id="UC_test",
        description=description,
        published_at=None,
        thumbnail_url=None,
        view_count=None,
        like_count=None,
        comment_count=None,
        comments_disabled=False,
        category_id=category_id,
        duration_seconds=duration_seconds,
    )


# ---------------------------------------------------------------------------
# Rule-based: PODCAST decisions (explicit podcast keyword in title)
# ---------------------------------------------------------------------------
def test_podcast_keyword_in_title():
    result = _rule_based_classify(_meta(title="The Tech Talk Podcast - Episode 45"))
    assert result.label == "PODCAST"


def test_joe_rogan_keyword_in_title():
    result = _rule_based_classify(_meta(title="Joe Rogan Experience #2100 - Full Episode"))
    assert result.label == "PODCAST"


def test_lex_fridman_keyword_in_title():
    result = _rule_based_classify(_meta(title="Lex Fridman #400 - Jeff Bezos"))
    assert result.label == "PODCAST"


# ---------------------------------------------------------------------------
# Rule-based: NOT_PODCAST decisions
# ---------------------------------------------------------------------------
def test_music_video_category():
    result = _rule_based_classify(_meta(title="Some Song", category_id="10"))
    assert result.label == "NOT_PODCAST"


def test_gaming_category():
    result = _rule_based_classify(_meta(title="Minecraft Let's Play", category_id="20"))
    assert result.label == "NOT_PODCAST"


def test_non_podcast_title_keyword_music():
    result = _rule_based_classify(_meta(title="Official Music Video - Bad Bunny ft. J Balvin"))
    assert result.label == "NOT_PODCAST"


def test_tutorial_title_keyword():
    result = _rule_based_classify(_meta(title="How to Build a React App in 2024 - Tutorial"))
    assert result.label == "NOT_PODCAST"


def test_vlog_title_keyword():
    result = _rule_based_classify(_meta(title="Day in My Life Vlog - NYC Edition"))
    assert result.label == "NOT_PODCAST"


def test_sitcom_drama_title_keyword():
    result = _rule_based_classify(_meta(title="Comedy Sitcom Episode 5 - Full Cast"))
    assert result.label == "NOT_PODCAST"


def test_drama_serial_title_keyword():
    result = _rule_based_classify(_meta(title="Popular Drama Serial Episode 25"))
    assert result.label == "NOT_PODCAST"


def test_short_video_not_podcast():
    # Video under 3 minutes (120 seconds) with no podcast signals
    result = _rule_based_classify(_meta(title="Quick Status Update", duration_seconds=120, category_id="22"))
    assert result.label == "NOT_PODCAST"


# ---------------------------------------------------------------------------
# Rule-based: UNCERTAIN decisions (deferred to LLM)
# ---------------------------------------------------------------------------
def test_uncertain_for_interview_without_podcast_in_title():
    # Long-form conversational interview without explicit "podcast" word
    result = _rule_based_classify(
        _meta(title="Elon Musk: A Deep Dive Interview", category_id="22", duration_seconds=5400)
    )
    assert result.label == "UNCERTAIN"


def test_uncertain_for_bulbulay_season_2():
    # Sitcom episode with title containing "Season 2" and "Comedy", no non-podcast trigger keyword
    result = _rule_based_classify(
        _meta(
            title="JACKPOT LAG GAYAAA!! | Bulbulay Season 2 | Momo | Khoobsurat | Nabeel | Mehmood Aslam | Comedy",
            category_id="23",
            duration_seconds=1304,
        )
    )
    assert result.label == "UNCERTAIN"


def test_uncertain_when_general_talk_title():
    result = _rule_based_classify(
        _meta(title="The Future Mark Zuckerberg Is Trying To Build", category_id="22", duration_seconds=2800)
    )
    assert result.label == "UNCERTAIN"


# ---------------------------------------------------------------------------
# PodcastClassifierLLM.is_configured
# ---------------------------------------------------------------------------
def test_classifier_llm_not_configured_when_no_key():
    llm = PodcastClassifierLLM(api_key=None, model="openai/gpt-oss-120b")
    assert not llm.is_configured()


def test_classifier_llm_not_configured_when_blank_key():
    llm = PodcastClassifierLLM(api_key="   ", model="openai/gpt-oss-120b")
    assert not llm.is_configured()


def test_classifier_llm_configured_when_key_set():
    llm = PodcastClassifierLLM(api_key="gsk_test123", model="openai/gpt-oss-120b")
    assert llm.is_configured()


def test_classifier_llm_returns_uncertain_when_unconfigured():
    llm = PodcastClassifierLLM(api_key=None, model="openai/gpt-oss-120b")
    result = llm.classify(_meta(title="Some Talk Show"))
    assert result.label == "UNCERTAIN"


# ---------------------------------------------------------------------------
# classify_podcast: LLM not called when rule is confident
# ---------------------------------------------------------------------------
class _AlwaysFailLLM(PodcastClassifierLLM):
    """Classifier LLM stub that must NOT be called when rules are confident."""
    def __init__(self):
        super().__init__(api_key="fake_key", model="openai/gpt-oss-120b")

    def classify(self, metadata):
        raise AssertionError("Classifier LLM should NOT be called when rules are confident.")


def test_classify_podcast_does_not_call_llm_when_confident_podcast():
    meta = _meta(title="Joe Rogan Experience #2100 - Morgan Freeman", category_id="22")
    result = classify_podcast(meta, _AlwaysFailLLM())
    assert result.label == "PODCAST"


def test_classify_not_podcast_does_not_call_llm_when_confident():
    meta = _meta(title="Official Music Video - Pop Star", category_id="10")
    result = classify_podcast(meta, _AlwaysFailLLM())
    assert result.label == "NOT_PODCAST"


# ---------------------------------------------------------------------------
# classify_podcast: LLM fallback when UNCERTAIN — using stub classify()
# ---------------------------------------------------------------------------
class _StubPodcastLLM(PodcastClassifierLLM):
    def __init__(self, label: str):
        super().__init__(api_key="fake_key", model="openai/gpt-oss-120b")
        self._label = label

    def classify(self, metadata):
        return ClassificationResult(self._label, "Stub classification.")


def test_classify_falls_back_to_llm_podcast():
    meta = _meta(title="The Future Mark Zuckerberg Is Trying To Build", category_id="22", duration_seconds=2800)
    result = classify_podcast(meta, _StubPodcastLLM("PODCAST"))
    assert result.label == "PODCAST"


def test_classify_falls_back_to_llm_rejects_bulbulay():
    meta = _meta(
        title="JACKPOT LAG GAYAAA!! | Bulbulay Season 2 | Momo | Khoobsurat | Nabeel | Mehmood Aslam | Comedy",
        category_id="23",
        duration_seconds=1304,
    )
    result = classify_podcast(meta, _StubPodcastLLM("NOT_PODCAST"))
    assert result.label == "NOT_PODCAST"


def test_classify_falls_back_to_llm_uncertain():
    meta = _meta(title="Ambiguous Title", category_id="22", duration_seconds=None)
    result = classify_podcast(meta, _StubPodcastLLM("UNCERTAIN"))
    assert result.label == "UNCERTAIN"


# ---------------------------------------------------------------------------
# ClassificationResult dataclass
# ---------------------------------------------------------------------------
def test_classification_result_repr():
    r = ClassificationResult("PODCAST", "Has podcast keyword.")
    assert "PODCAST" in repr(r)
    assert r.confidence == "high"
