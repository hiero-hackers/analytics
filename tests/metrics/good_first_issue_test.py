from hiero_analytics.metrics.good_first_issue import (
    count_good_first_issues,
)


def test_count_good_first_issues_case_insensitive():
    issues = [
        {"labels": [{"name": "Good First Issue"}]},
    ]

    assert count_good_first_issues(issues) == 1