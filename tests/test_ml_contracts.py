from ml.features import priority_score


def test_priority_score_is_bounded_and_weighted():
    assert priority_score(1, 1, 0, 1, 1) == 100
    assert priority_score(-1, -1, 1, -1, -1) == 0
