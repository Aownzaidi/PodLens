"""Deterministic text-cleaning helpers used by the preprocessing service.

These are pure functions (no model calls, no I/O) so they are easy to unit
test and reason about.
"""
from __future__ import annotations

import html
import re
import unicodedata

_URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_WHITESPACE_PATTERN = re.compile(r"\s+")
_REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{3,}")  # 4+ repeated chars, e.g. "soooooo"


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def decode_html_entities(text: str) -> str:
    return html.unescape(text)


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def replace_urls(text: str, placeholder: str = "") -> str:
    """Replace URLs with a placeholder (default: remove) since raw links add
    no useful signal for spam/sentiment models but can dominate tokenization."""
    return _URL_PATTERN.sub(placeholder, text)


def collapse_repeated_characters(text: str, max_repeat: int = 3) -> str:
    """Collapse runs of 4+ identical characters down to `max_repeat`.

    Preserves emphasis (e.g. "soooo good" -> "sooo good") without destroying
    it entirely, which keeps signal useful for sentiment while reducing
    tokenizer noise.
    """

    def _collapse(match: re.Match) -> str:
        return match.group(1) * max_repeat

    return _REPEATED_CHAR_PATTERN.sub(_collapse, text)


def clean_comment_text(raw_text: str) -> str:
    """Produce model-ready text from a raw YouTube comment.

    Preserves emojis, punctuation, and casing (these carry sentiment/spam
    signal) while normalizing whitespace/encoding artifacts and stripping
    raw URLs. The original text is never mutated - this returns a new string
    for storage alongside (not instead of) the original.
    """
    if raw_text is None:
        return ""

    text = decode_html_entities(raw_text)
    text = normalize_unicode(text)
    text = replace_urls(text)
    text = collapse_repeated_characters(text)
    text = normalize_whitespace(text)
    return text


def is_empty_or_invalid(text: str) -> bool:
    """A comment is considered invalid for analysis if, after cleaning,
    it has no meaningful content (empty, or only punctuation/whitespace)."""
    if text is None:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    # Must contain at least one alphanumeric character or emoji-range symbol.
    has_content = any(ch.isalnum() for ch in stripped) or any(
        unicodedata.category(ch) == "So" for ch in stripped
    )
    return not has_content
