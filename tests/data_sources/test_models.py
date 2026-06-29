"""Tests for normalized GitHub data record models."""

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    ContributorMergedPRCountRecord,
    IssueRecord,
    IssueTimelineEventRecord,
    PullRequestDifficultyRecord,
    RepositoryRecord,
    _extract_label_name,
    _extract_labels,
    _extract_login,
    _parse_dt,
)

# ---------------------------------------------------------
# RepositoryRecord
# ---------------------------------------------------------

def test_repository_record_creation():
    """Repository records should initialize required fields."""
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
    """Repository records should keep optional metadata when provided."""
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
    """Issue records should store the normalized issue payload."""
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
    """PR difficulty records should link pull requests to issue labels."""
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
    """Contributor activity records should store normalized PR events."""
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


def test_contributor_activity_record_from_issue_node():
    """Contributor activity records should hydrate issue creation events."""
    records = ContributorActivityRecord.from_github_node(
        {
            "number": 12,
            "createdAt": "2024-01-02T00:00:00Z",
            "author": {"login": "dana"},
        },
        {
            "owner": "org",
            "repo": "repo",
            "target_type": "issue",
            "cutoff": datetime.fromisoformat("2024-01-01T00:00:00+00:00"),
        },
    )

    assert records == [
        ContributorActivityRecord(
            repo="org/repo",
            activity_type="authored_pull_request",
            actor="dana",
            occurred_at=datetime.fromisoformat("2024-01-02T00:00:00+00:00"),
            target_type="pull_request",
            target_number=12,
            target_author="dana",
        )
    ]


def test_issue_timeline_event_record_creation():
    """Issue timeline records should preserve normalized event metadata."""
    occurred = datetime(2024, 1, 1)

    record = IssueTimelineEventRecord(
        repo="org/repo",
        issue_number=10,
        event_type="labeled",
        occurred_at=occurred,
        label="good first issue",
    )

    assert record.repo == "org/repo"
    assert record.issue_number == 10
    assert record.event_type == "labeled"
    assert record.label == "good first issue"


def test_issue_timeline_event_from_issue_node_expands_timeline_items():
    """A GraphQL issue node expands its timelineItems into normalized events."""
    node = {
        "number": 42,
        "timelineItems": {
            "nodes": [
                {
                    "__typename": "LabeledEvent",
                    "createdAt": "2024-03-01T12:00:00Z",
                    "label": {"name": "Beginner"},
                },
                {
                    "__typename": "UnlabeledEvent",
                    "createdAt": "2024-03-05T09:30:00Z",
                    "label": {"name": "Beginner"},
                },
            ]
        },
    }

    records = IssueTimelineEventRecord.from_github_node(node, {"owner": "org", "repo": "repo"})

    assert [(r.event_type, r.label) for r in records] == [
        ("labeled", "beginner"),  # event type and label name lower-cased
        ("unlabeled", "beginner"),
    ]
    assert all(r.repo == "org/repo" and r.issue_number == 42 for r in records)
    assert records[0].occurred_at == _parse_dt("2024-03-01T12:00:00Z")


def test_issue_timeline_event_from_github_node_handles_empty():
    """An issue with no label events yields no records."""
    node = {"number": 7, "timelineItems": {"nodes": []}}

    records = IssueTimelineEventRecord.from_github_node(node, {"owner": "org", "repo": "repo"})

    assert records == []


# ---------------------------------------------------------
# dataclass equality
# ---------------------------------------------------------

def test_repository_record_equality():
    """Repository records should compare by value."""
    r1 = RepositoryRecord("org/repo", "repo", "org")
    r2 = RepositoryRecord("org/repo", "repo", "org")

    assert r1 == r2


# ---------------------------------------------------------
# immutability
# ---------------------------------------------------------

def test_repository_record_is_frozen():
    """Repository records should be immutable."""
    repo = RepositoryRecord("org/repo", "repo", "org")

    with pytest.raises(FrozenInstanceError):
        repo.name = "new-name"


def test_issue_record_is_frozen():
    """Issue records should be immutable."""
    issue = IssueRecord(
        repo="org/repo",
        number=1,
        title="Bug",
        state="OPEN",
        created_at=datetime(2024, 1, 1),
        closed_at=None,
        labels=["bug"],
    )

    with pytest.raises(FrozenInstanceError):
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

    with pytest.raises(FrozenInstanceError):
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
    """ISO timestamps should parse into datetime objects."""
    value = "2024-01-01T00:00:00Z"

    dt = _parse_dt(value)

    assert isinstance(dt, datetime)
    assert dt.year == 2024


def test_parse_dt_none():
    """A missing timestamp should remain missing."""
    assert _parse_dt(None) is None


# ---------------------------------------------------------
# hydration helpers (defensive extraction)
# ---------------------------------------------------------

def test_extract_login_reads_nested_login():
    """A well-formed actor node yields its login."""
    assert _extract_login({"author": {"login": "alice"}}) == "alice"


def test_extract_login_honors_custom_key():
    """A non-default key (e.g. mergedBy) is read."""
    assert _extract_login({"mergedBy": {"login": "bob"}}, "mergedBy") == "bob"


def test_extract_login_degrades_on_missing_or_malformed():
    """Null, empty, or non-mapping actors return None instead of raising."""
    assert _extract_login({}) is None
    assert _extract_login({"author": None}) is None
    assert _extract_login({"author": {}}) is None
    assert _extract_login({"author": "alice"}) is None  # actor is not a mapping
    assert _extract_login(None) is None


def test_extract_labels_returns_names():
    """Label nodes are flattened to a list of names, case preserved by default."""
    container = {"labels": {"nodes": [{"name": "Bug"}, {"name": "GFI"}]}}
    assert _extract_labels(container) == ["Bug", "GFI"]


def test_extract_labels_lowercases_when_requested():
    """The lower flag normalizes label case."""
    container = {"labels": {"nodes": [{"name": "Bug"}]}}
    assert _extract_labels(container, lower=True) == ["bug"]


def test_extract_labels_degrades_on_missing_or_malformed():
    """Missing labels, non-mapping entries, and non-str names are skipped."""
    assert _extract_labels({}) == []
    assert _extract_labels(None) == []
    assert _extract_labels({"labels": {"nodes": ["x", {"name": 5}, {"name": "ok"}]}}) == ["ok"]


def test_extract_label_name_lowercases():
    """A single label node yields its lower-cased name."""
    assert _extract_label_name({"label": {"name": "Beginner"}}) == "beginner"


def test_extract_label_name_degrades_on_missing_or_malformed():
    """Null or malformed single labels return None."""
    assert _extract_label_name({}) is None
    assert _extract_label_name({"label": None}) is None
    assert _extract_label_name({"label": {}}) is None
    assert _extract_label_name(None) is None
