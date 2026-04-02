from datetime import datetime

import pytest

from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    ContributorMergedPRCountRecord,
    IssueRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
    _parse_dt,
)

# ---------------------------------------------------------
# RepositoryRecord
# ---------------------------------------------------------

def test_repository_record_creation():

    repo = RepositoryRecord(
        full_name="org/repo",
        name="repo",
        owner="org",
    )

    assert repo.full_name == "org/repo"
    assert repo.name == "repo"
    assert repo.owner == "org"
    assert repo.created_at is None
    assert repo.stargazers is None
    assert repo.forks is None


def test_repository_record_optional_fields():

    dt = datetime(2024, 1, 1)

    repo = RepositoryRecord(
        full_name="org/repo",
        name="repo",
        owner="org",
        created_at=dt,
        stargazers=10,
        forks=5,
    )

    assert repo.created_at == dt
    assert repo.stargazers == 10
    assert repo.forks == 5


# ---------------------------------------------------------
# IssueRecord
# ---------------------------------------------------------

def test_issue_record_creation():

    created = datetime(2024, 1, 1)

    issue = IssueRecord(
        repo="org/repo",
        number=1,
        title="Bug",
        state="OPEN",
        created_at=created,
        closed_at=None,
        labels=["bug"],
    )

    assert issue.repo == "org/repo"
    assert issue.number == 1
    assert issue.title == "Bug"
    assert issue.state == "OPEN"
    assert issue.labels == ["bug"]


# ---------------------------------------------------------
# PullRequestDifficultyRecord
# ---------------------------------------------------------

def test_pr_difficulty_record_creation():

    created = datetime(2024, 1, 1)
    merged = datetime(2024, 1, 2)

    record = PullRequestDifficultyRecord(
        repo="org/repo",
        pr_number=10,
        pr_created_at=created,
        pr_merged_at=merged,
        pr_additions=5,
        pr_deletions=2,
        pr_changed_files=3,
        issue_number=1,
        issue_labels=["good first issue"],
    )

    assert record.pr_number == 10
    assert record.issue_number == 1
    assert record.issue_labels == ["good first issue"]


def test_contributor_activity_record_creation():

    occurred = datetime(2024, 1, 1)

    record = ContributorActivityRecord(
        repo="org/repo",
        activity_type="authored_pull_request",
        actor="alice",
        occurred_at=occurred,
        target_type="pull_request",
        target_number=10,
        target_author="alice",
        detail=None,
    )

    assert record.repo == "org/repo"
    assert record.activity_type == "authored_pull_request"
    assert record.actor == "alice"
    assert record.target_number == 10


# ---------------------------------------------------------
# dataclass equality
# ---------------------------------------------------------

def test_repository_record_equality():

    r1 = RepositoryRecord("org/repo", "repo", "org")
    r2 = RepositoryRecord("org/repo", "repo", "org")

    assert r1 == r2


# ---------------------------------------------------------
# immutability
# ---------------------------------------------------------

def test_repository_record_is_frozen():

    repo = RepositoryRecord("org/repo", "repo", "org")

    with pytest.raises(Exception):
        repo.name = "new-name"


def test_issue_record_is_frozen():

    issue = IssueRecord(
        repo="org/repo",
        number=1,
        title="Bug",
        state="OPEN",
        created_at=datetime(2024, 1, 1),
        closed_at=None,
        labels=["bug"],
    )

    with pytest.raises(Exception):
        issue.number = 2


# ---------------------------------------------------------
# ContributorMergedPRCountRecord
# ---------------------------------------------------------

def test_contributor_merged_pr_count_record_creation():
    """Test creating a ContributorMergedPRCountRecord."""
    record = ContributorMergedPRCountRecord(
        repo="hiero-ledger/hiero-sdk-python",
        login="john-doe",
        merged_pr_count=42,
    )

    assert record.repo == "hiero-ledger/hiero-sdk-python"
    assert record.login == "john-doe"
    assert record.merged_pr_count == 42


def test_contributor_merged_pr_count_record_zero():
    """Test a record with zero merged PRs."""
    record = ContributorMergedPRCountRecord(
        repo="hiero-ledger/hiero-sdk-python",
        login="inactive-user",
        merged_pr_count=0,
    )

    assert record.merged_pr_count == 0


def test_contributor_merged_pr_count_record_is_frozen():
    """Test that the record is immutable (frozen)."""
    record = ContributorMergedPRCountRecord(
        repo="hiero-ledger/hiero-sdk-python",
        login="john-doe",
        merged_pr_count=10,
    )

    with pytest.raises(Exception):
        record.merged_pr_count = 20


def test_contributor_merged_pr_count_record_equality():
    """Test record equality."""
    r1 = ContributorMergedPRCountRecord("org/repo", "alice", 5)
    r2 = ContributorMergedPRCountRecord("org/repo", "alice", 5)
    r3 = ContributorMergedPRCountRecord("org/repo", "alice", 6)

    assert r1 == r2
    assert r1 != r3

# ---------------------------------------------------------
# parse datetime
# ---------------------------------------------------------

def test_parse_dt():
    value = "2024-01-01T00:00:00Z"

    dt = _parse_dt(value)

    assert isinstance(dt, datetime)
    assert dt.year == 2024


def test_parse_dt_none():
    assert _parse_dt(None) is None

