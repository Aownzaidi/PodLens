from datetime import datetime, timezone

from app.services.preprocessing_service import preprocess_comments
from app.services.youtube_service import CollectedComment
from app.utils.text_processing import clean_comment_text, collapse_repeated_characters, is_empty_or_invalid


def _comment(text, ytid="c1", author_channel_id="a1"):
    return CollectedComment(
        youtube_comment_id=ytid,
        text=text,
        author_display_name="Author",
        author_channel_id=author_channel_id,
        like_count=0,
        published_at=datetime.now(timezone.utc),
        updated_at=None,
    )


def test_clean_comment_text_strips_urls_and_normalizes_whitespace():
    cleaned = clean_comment_text("Check   this out!! https://example.com/foo  ")
    assert "http" not in cleaned
    assert cleaned == "Check this out!!"


def test_clean_comment_text_preserves_emoji():
    cleaned = clean_comment_text("Great episode 🔥🔥")
    assert "🔥" in cleaned


def test_collapse_repeated_characters():
    assert collapse_repeated_characters("soooooo good") == "sooo good"


def test_is_empty_or_invalid():
    assert is_empty_or_invalid("") is True
    assert is_empty_or_invalid("   ") is True
    assert is_empty_or_invalid("...") is True
    assert is_empty_or_invalid("hello") is False
    assert is_empty_or_invalid("🔥") is False


def test_preprocess_removes_duplicates_and_invalid():
    comments = [
        _comment("Great episode!", ytid="1", author_channel_id="a"),
        _comment("Great episode!", ytid="2", author_channel_id="a"),  # duplicate (same author+text)
        _comment("   ", ytid="3", author_channel_id="b"),  # invalid/empty
        _comment("Great episode!", ytid="4", author_channel_id="c"),  # same text, different author: kept
    ]

    result = preprocess_comments(comments)

    assert result.duplicates_removed == 1
    assert result.invalid_removed == 1
    assert len(result.valid) == 2
    assert result.valid[0].source.youtube_comment_id == "1"
    assert result.valid[1].source.youtube_comment_id == "4"


def test_preprocess_keeps_original_text_untouched():
    comments = [_comment("Check this https://x.com   now!!")]
    result = preprocess_comments(comments)

    assert result.valid[0].source.text == "Check this https://x.com   now!!"
    assert "http" not in result.valid[0].processed_text
