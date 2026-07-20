"""Tests for contributor merged PR count functionality."""

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_ingest as ingest
from hiero_analytics.data_sources.models import ContributorMergedPRCountRecord, PullRequestDifficultyRecord

# ---------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------


@pytest.fixture
def mock_client():
    """Return a Mock object standing in for GitHubClient."""
    return Mock()


def _pr(repo: str, number: int, author: str | None, issue: int | None = None) -> PullRequestDifficultyRecord:
    """Create a merged-PR difficulty record for count derivation tests."""
    return PullRequestDifficultyRecord(
        repo=repo,
        pr_number=number,
        pr_created_at=datetime(2024, 1, 1, tzinfo=UTC),
        pr_merged_at=datetime(2024, 1, 2, tzinfo=UTC),
        pr_additions=1,
        pr_deletions=1,
        pr_changed_files=1,
        issue_number=issue,
        issue_labels=[],
        author=author,
    )


# ---------------------------------------------------------
# ContributorMergedPRCountRecord model tests
# ---------------------------------------------------------


def test_contributor_merged_pr_count_record_creation():
    """Test creating a ContributorMergedPRCountRecord."""
    record = ContributorMergedPRCountRecord(
        repo="hiero-ledger/hiero-sdk-python",
        login="sami",
        merged_pr_count=42,
    )

    assert record.repo == "hiero-ledger/hiero-sdk-python"
    assert record.login == "sami"
    assert record.merged_pr_count == 42


def test_contributor_merged_pr_count_record_frozen():
    """Test that the record is immutable (frozen)."""
    record = ContributorMergedPRCountRecord(
        repo="hiero-ledger/hiero-sdk-python",
        login="sami",
        merged_pr_count=10,
    )

    with pytest.raises(AttributeError):
        record.merged_pr_count = 20


# ---------------------------------------------------------
# fetch_repo_contributor_merged_pr_count_graphql
# ---------------------------------------------------------


def test_repo_count_derives_from_pr_records_and_dedups(monkeypatch, mock_client):
    """The count is distinct PR numbers for the login, deduped across linked issues."""
    records = [
        _pr("org/repo", 1, "Sami", issue=10),
        _pr("org/repo", 1, "Sami", issue=11),  # same PR, second linked issue
        _pr("org/repo", 2, "sami"),  # unlinked PR still counts
        _pr("org/repo", 3, "bob"),
        _pr("org/repo", 4, None),  # authorless PRs never count
    ]
    monkeypatch.setattr(ingest.contributors, "fetch_repo_merged_pr_difficulty_graphql", Mock(return_value=records))

    record = ingest.fetch_repo_contributor_merged_pr_count_graphql(mock_client, "org", "repo", login="sami")

    assert record.repo == "org/repo"
    assert record.login == "sami"
    assert record.merged_pr_count == 2  # PRs 1 and 2 (case-insensitive author match)


def test_repo_count_zero_when_login_absent(monkeypatch, mock_client):
    """A contributor with no merged PRs gets a zero-count record."""
    monkeypatch.setattr(
        ingest.contributors, "fetch_repo_merged_pr_difficulty_graphql", Mock(return_value=[_pr("org/repo", 1, "bob")])
    )

    record = ingest.fetch_repo_contributor_merged_pr_count_graphql(mock_client, "org", "repo", login="ghost")

    assert record.merged_pr_count == 0


# ---------------------------------------------------------
# fetch_org_contributor_merged_pr_count_graphql
# ---------------------------------------------------------


def test_org_counts_derive_from_incremental_dataset(monkeypatch, mock_client):
    """Org counts come from the merged-PR dataset: one record per repo with activity."""
    records = [
        _pr("org/repo1", 1, "carol"),
        _pr("org/repo1", 2, "carol"),
        _pr("org/repo2", 7, "Carol", issue=3),
        _pr("org/repo3", 9, "bob"),
    ]
    monkeypatch.setattr(ingest.contributors, "fetch_org_merged_pr_difficulty_graphql", Mock(return_value=records))

    results = ingest.fetch_org_contributor_merged_pr_count_graphql(mock_client, org="org", login="carol")

    assert [(r.repo, r.merged_pr_count) for r in results] == [("org/repo1", 2), ("org/repo2", 1)]
    assert all(r.login == "carol" for r in results)


def test_org_counts_respect_repo_filter(monkeypatch, mock_client):
    """The optional repos filter matches both full names and short names."""
    records = [_pr("org/repo1", 1, "carol"), _pr("org/repo2", 2, "carol")]
    monkeypatch.setattr(ingest.contributors, "fetch_org_merged_pr_difficulty_graphql", Mock(return_value=records))

    results = ingest.fetch_org_contributor_merged_pr_count_graphql(
        mock_client, org="org", login="carol", repos=["repo2"]
    )

    assert [r.repo for r in results] == ["org/repo2"]
