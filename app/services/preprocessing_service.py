"""Comment preprocessing: cleaning, deduplication, and validity checks.

Original comment text is never discarded or overwritten - every result keeps
both `original_text` and `processed_text` so the frontend always shows what
the commenter actually wrote, while the processed_text is what's fed to the
models.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.youtube_service import CollectedComment
from app.utils.text_processing import clean_comment_text, is_empty_or_invalid


@dataclass
class PreprocessedComment:
    source: CollectedComment
    processed_text: str


@dataclass
class PreprocessingResult:
    valid: list[PreprocessedComment]
    duplicates_removed: int
    invalid_removed: int


def preprocess_comments(comments: list[CollectedComment]) -> PreprocessingResult:
    seen_keys: set[tuple[str | None, str]] = set()
    valid: list[PreprocessedComment] = []
    duplicates_removed = 0
    invalid_removed = 0

    for comment in comments:
        processed = clean_comment_text(comment.text)

        if is_empty_or_invalid(processed):
            invalid_removed += 1
            continue

        # Dedupe on (author, cleaned text) - same author posting identical
        # text twice (e.g. API returning overlapping pages) is a duplicate;
        # different authors with the same text are kept (common short
        # reactions like "lol" or "this").
        dedupe_key = (comment.author_channel_id, processed.lower())
        if dedupe_key in seen_keys:
            duplicates_removed += 1
            continue
        seen_keys.add(dedupe_key)

        valid.append(PreprocessedComment(source=comment, processed_text=processed))

    return PreprocessingResult(
        valid=valid, duplicates_removed=duplicates_removed, invalid_removed=invalid_removed
    )
