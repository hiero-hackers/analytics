"""
Tests for contributor merged PR count functionality.
"""

from unittest.mock import Mock

import pytest

import hiero_analytics.data_sources.github_ingest as ingest
from hiero_analytics.data_sources.models import ContributorMergedPRCountRecord


# ---------------------------------------------------------
# fixtures
# ---------------------------------------------------------

@pytest.fixture
def mock_client():
    return Mock()


@pytest.fixture
def bypass_pagination(monkeypatch):
    """
    Replace paginate_cursor with a single-page execution.
    """
    monkeypatch.setattr(
        ingest,
        "paginate_cursor",
        lambda f: f(None)[0],
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


def test_contributor_merged_pr_count_record_zero():
    """Test a record with zero merged PRs."""
    record = ContributorMergedPRCountRecord(
        repo="hiero-ledger/hiero-sdk-python",
        login="inactive-user",
        merged_pr_count=0,
    )

    assert record.merged_pr_count == 0


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
# fetch_repo_contributor_merged_pr_count_graphql tests
# ---------------------------------------------------------

def test_fetch_repo_contributor_merged_pr_count_graphql(mock_client):
    """Test fetching merged PR count for a single repository."""
    mock_client.graphql.return_value = {
        "data": {
            "search": {
                "issueCount": 15,
            }
        }
    }

    record = ingest.fetch_repo_contributor_merged_pr_count_graphql(
        mock_client,
        owner="hiero-ledger",
        repo="hiero-sdk-python",
        login="sami",
    )

    assert isinstance(record, ContributorMergedPRCountRecord)
    assert record.repo == "hiero-ledger/hiero-sdk-python"
    assert record.login == "sami"
    assert record.merged_pr_count == 15

    # Verify the correct search query was used
    call_args = mock_client.graphql.call_args
    assert call_args is not None
    search_query = call_args[0][1]["searchQuery"]
    assert "is:pr" in search_query
    assert "is:merged" in search_query
    assert "author:sami" in search_query
    assert "repo:hiero-ledger/hiero-sdk-python" in search_query


def test_fetch_repo_contributor_merged_pr_count_graphql_zero(mock_client):
    """Test fetching when contributor has no merged PRs."""
    mock_client.graphql.return_value = {
        "data": {
            "search": {
                "issueCount": 0,
            }
        }
    }

    record = ingest.fetch_repo_contributor_merged_pr_count_graphql(
        mock_client,
        owner="hiero-ledger",
        repo="hiero-sdk-python",
        login="bob",
    )

    assert record.merged_pr_count == 0


# ---------------------------------------------------------
# fetch_org_contributor_merged_pr_count_graphql tests
# ---------------------------------------------------------

def test_fetch_org_contributor_merged_pr_count_graphql(mock_client, bypass_pagination):
    """Test fetching merged PR counts across all repositories in an org."""
    
    # Mock for fetching repos
    mock_client.graphql.side_effect = [
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {"name": "repo1"},
                            {"name": "repo2"},
                        ],
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": None,
                        },
                    }
                }
            }
        },
        # Merged count for repo1
        {
            "data": {
                "search": {
                    "issueCount": 10,
                }
            }
        },
        # Merged count for repo2
        {
            "data": {
                "search": {
                    "issueCount": 5,
                }
            }
        },
    ]

    records = ingest.fetch_org_contributor_merged_pr_count_graphql(
        mock_client,
        org="hiero-ledger",
        login="carol",
        max_workers=1,  # Single worker for predictable order
    )

    assert len(records) == 2

    # Find records by repo name to ensure order-independent testing
    repo1_record = next((r for r in records if "repo1" in r.repo), None)
    repo2_record = next((r for r in records if "repo2" in r.repo), None)

    assert repo1_record is not None
    assert repo1_record.login == "carol"
    assert repo1_record.merged_pr_count == 10
    
    assert repo2_record is not None
    assert repo2_record.login == "carol"
    assert repo2_record.merged_pr_count == 5

# ---------------------------------------------------------
# dataclass serialization
# ---------------------------------------------------------

def test_contributor_merged_pr_count_in_list():
    """Test that records work well in collections."""
    records = [
        ContributorMergedPRCountRecord("org/repo1", "alice", 5),
        ContributorMergedPRCountRecord("org/repo2", "mona", 3),
        ContributorMergedPRCountRecord("org/repo1", "sophie", 8),
    ]

    assert len(records) == 3
    alice_counts = [r.merged_pr_count for r in records if r.login == "alice"]
    assert sum(alice_counts) == 5


def test_contributor_merged_pr_count_comparison():
    """Test that records can be compared and sorted."""
    records = [
        ContributorMergedPRCountRecord("org/repo2", "mona", 3),
        ContributorMergedPRCountRecord("org/repo1", "mona", 5),
    ]

    # Sort by merged PR count descending
    sorted_records = sorted(records, key=lambda r: r.merged_pr_count, reverse=True)
    assert sorted_records[0].merged_pr_count == 5
    assert sorted_records[1].merged_pr_count == 3
