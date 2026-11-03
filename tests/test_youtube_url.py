import pytest

from app.core.exceptions import InvalidYouTubeUrlError
from app.utils.youtube_url import extract_video_id, is_valid_youtube_url


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=10s", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id_valid(url, expected_id):
    assert extract_video_id(url) == expected_id


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/",
        "https://vimeo.com/12345",
    ],
)
def test_extract_video_id_invalid(url):
    with pytest.raises(InvalidYouTubeUrlError):
        extract_video_id(url)


def test_is_valid_youtube_url():
    assert is_valid_youtube_url("https://youtu.be/dQw4w9WgXcQ") is True
    assert is_valid_youtube_url("not a url") is False
