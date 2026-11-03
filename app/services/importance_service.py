"""Important-comment identification using transparent, explainable rules.

Deliberately not a trained model. Importance is a normalized blend of
engagement (like count) and textual relevance signals (comment length,
within a sane range, as a proxy for substantive feedback vs. one-word
reactions). This is explicitly not a claim that likes alone determine true
importance - it's one explainable heuristic combining the metadata that is
actually available.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import log1p


@dataclass
class RankableComment:
    comment_id: int
    text: str
    like_count: int
    reply_count: int


@dataclass
class ImportanceScore:
    comment_id: int
    score: float
    is_important: bool


# Comments shorter than this are usually low-substance reactions ("lol", "nice")
_MIN_SUBSTANTIVE_LENGTH = 25
# Comments longer than this get diminishing returns (avoid rewarding rambling)
_LENGTH_SATURATION = 280

_TOP_FRACTION = 0.1  # top 10% of ranked comments are flagged "important"
_MIN_IMPORTANT = 3
_MAX_IMPORTANT = 25


def _length_signal(text_length: int) -> float:
    if text_length <= 0:
        return 0.0
    capped = min(text_length, _LENGTH_SATURATION)
    if capped < _MIN_SUBSTANTIVE_LENGTH:
        return capped / _MIN_SUBSTANTIVE_LENGTH * 0.3
    return 0.3 + 0.7 * (capped - _MIN_SUBSTANTIVE_LENGTH) / (
        _LENGTH_SATURATION - _MIN_SUBSTANTIVE_LENGTH
    )


def rank_comments(comments: list[RankableComment]) -> list[ImportanceScore]:
    """Score every comment and flag the top slice as "important".

    Score = log-scaled engagement (likes + replies) combined with a length
    signal, normalized to [0, 1]. Transparent and adjustable in one place.
    """
    if not comments:
        return []

    raw_scores: dict[int, float] = {}
    for c in comments:
        engagement = log1p(c.like_count) + 0.5 * log1p(c.reply_count)
        length_signal = _length_signal(len(c.text.strip()))
        raw_scores[c.comment_id] = engagement * (0.6 + 0.4 * length_signal)

    max_score = max(raw_scores.values()) or 1.0
    normalized = {cid: (s / max_score if max_score > 0 else 0.0) for cid, s in raw_scores.items()}

    sorted_ids = sorted(normalized.keys(), key=lambda cid: normalized[cid], reverse=True)
    important_count = min(
        _MAX_IMPORTANT, max(_MIN_IMPORTANT, round(len(sorted_ids) * _TOP_FRACTION))
    )
    important_count = min(important_count, len(sorted_ids))
    important_set = set(sorted_ids[:important_count])

    return [
        ImportanceScore(
            comment_id=cid, score=round(normalized[cid], 4), is_important=cid in important_set
        )
        for cid in normalized
    ]
