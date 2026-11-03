from app.services.importance_service import RankableComment, rank_comments


def test_rank_comments_empty():
    assert rank_comments([]) == []


def test_rank_comments_higher_engagement_scores_higher():
    comments = [
        RankableComment(comment_id=1, text="This podcast really changed how I think about my career choices.", like_count=500, reply_count=10),
        RankableComment(comment_id=2, text="nice", like_count=0, reply_count=0),
    ]

    scores = rank_comments(comments)
    score_by_id = {s.comment_id: s.score for s in scores}

    assert score_by_id[1] > score_by_id[2]


def test_rank_comments_flags_top_fraction_as_important():
    comments = [
        RankableComment(comment_id=i, text="A reasonably long and thoughtful comment about the show." * (1 if i < 3 else 0) or "ok", like_count=100 - i, reply_count=0)
        for i in range(30)
    ]

    scores = rank_comments(comments)
    important_count = sum(1 for s in scores if s.is_important)

    # top ~10%, bounded between 3 and 25
    assert 3 <= important_count <= 25
    # highest-like comment should be marked important
    top_comment_score = next(s for s in scores if s.comment_id == 0)
    assert top_comment_score.is_important is True


def test_rank_comments_all_zero_engagement_does_not_crash():
    comments = [RankableComment(comment_id=i, text="ok", like_count=0, reply_count=0) for i in range(5)]
    scores = rank_comments(comments)
    assert len(scores) == 5
