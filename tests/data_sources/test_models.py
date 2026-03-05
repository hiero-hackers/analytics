from datetime import datetime

from hiero_analytics.data_sources.models import IssueRecord, RepoRecord


def test_issue_record_creation():

    created = datetime(2024, 1, 1)

    issue = IssueRecord(
        repo="org/repo",
        number=123,
        title="Example issue",
        state="OPEN",
        created_at=created,
        labels=["bug", "good first issue"],
    )

    assert issue.repo == "org/repo"
    assert issue.number == 123
    assert issue.title == "Example issue"
    assert issue.state == "OPEN"
    assert issue.created_at == created
    assert issue.labels == ["bug", "good first issue"]


def test_repo_record_creation():

    repo = RepoRecord(full_name="org/repo")

    assert repo.full_name == "org/repo"


def test_issue_record_equality():

    created = datetime(2024, 1, 1)

    a = IssueRecord(
        repo="org/repo",
        number=1,
        title="Issue",
        state="OPEN",
        created_at=created,
        labels=["bug"],
    )

    b = IssueRecord(
        repo="org/repo",
        number=1,
        title="Issue",
        state="OPEN",
        created_at=created,
        labels=["bug"],
    )

    assert a == b