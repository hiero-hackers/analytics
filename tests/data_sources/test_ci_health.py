"""Tests for GitHub CI health data ingestion."""

from unittest.mock import Mock

from hiero_analytics.data_sources.github_ingest.ci_health import (
    CIHealthRecord,
    fetch_repo_ci_health_graphql,
)


def test_fetch_repo_ci_health_graphql_cache_hit(monkeypatch):
    """Return cached CI health data without making a GraphQL request."""
    cached_record = CIHealthRecord(
        workflows=[
            {
                "name": "ci.yml",
                "text": "uses: actions/checkout@v4",
            }
        ],
        has_wiki_enabled=False,
        has_issues_enabled=True,
        has_discussions_enabled=False,
        has_projects_enabled=False,
        web_commit_signoff_required=True,
    )

    graphql = Mock()

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=[cached_record]),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    client = Mock()
    client.graphql = graphql

    result = fetch_repo_ci_health_graphql(
        client,
        "hiero-ledger",
        "hiero-sdk-java",
    )

    assert result == cached_record
    graphql.assert_not_called()


def test_fetch_repo_ci_health_graphql_cache_miss(monkeypatch):
    """Fetch and cache CI health data when no cached record exists."""
    graphql_data = {
        "data": {
            "repository": {
                "hasWikiEnabled": True,
                "hasIssuesEnabled": True,
                "hasDiscussionsEnabled": False,
                "hasProjectsEnabled": True,
                "webCommitSignoffRequired": True,
                "root": {
                    "entries": [
                        {"name": "package.json"},
                        {"name": "Dockerfile"},
                        {"name": ".github"},
                    ]
                },
                "object": {
                    "entries": [
                        {
                            "name": "workflows",
                            "object": {
                                "entries": [
                                    {
                                        "name": "ci.yml",
                                        "object": {"text": ("name: CI\nuses: actions/checkout@v4\n")},
                                    },
                                    {
                                        "name": "release.yaml",
                                        "object": {"text": "name: Release\n"},
                                    },
                                    {
                                        "name": "broken.yml",
                                        "object": {},
                                    },
                                ]
                            },
                        },
                        {
                            "name": "dependabot.yml",
                            "object": {"text": "version: 2\n"},
                        },
                        {
                            "name": "README.md",
                            "object": {"text": "# CI documentation"},
                        },
                    ]
                },
            }
        }
    }

    client = Mock()
    client.graphql.return_value = graphql_data

    save_cache = Mock()

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        save_cache,
    )

    result = fetch_repo_ci_health_graphql(
        client,
        "hiero-ledger",
        "hiero-sdk-java",
    )

    assert result == CIHealthRecord(
        workflows=[
            {
                "name": "ci.yml",
                "text": "name: CI\nuses: actions/checkout@v4\n",
            },
            {
                "name": "release.yaml",
                "text": "name: Release\n",
            },
        ],
        has_wiki_enabled=True,
        has_issues_enabled=True,
        has_discussions_enabled=False,
        has_projects_enabled=True,
        web_commit_signoff_required=True,
        root_entries=["package.json", "Dockerfile", ".github"],
        dependabot_config="version: 2\n",
    )

    client.graphql.assert_called_once()
    save_cache.assert_called_once()


def test_fetch_repo_ci_health_graphql_missing_repository(monkeypatch):
    """Return None when GitHub does not return repository data."""
    client = Mock()
    client.graphql.return_value = {
        "data": {
            "repository": None,
        }
    }

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    save_cache = Mock()
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        save_cache,
    )

    result = fetch_repo_ci_health_graphql(
        client,
        "hiero-ledger",
        "does-not-exist",
    )

    assert result is None
    save_cache.assert_not_called()


def test_fetch_repo_ci_health_graphql_empty_workflows(monkeypatch):
    """Return a record with no workflows when the workflow tree is empty."""
    client = Mock()
    client.graphql.return_value = {
        "data": {
            "repository": {
                "hasWikiEnabled": False,
                "hasIssuesEnabled": False,
                "hasDiscussionsEnabled": False,
                "hasProjectsEnabled": False,
                "webCommitSignoffRequired": False,
                "object": {"entries": []},
            }
        }
    }

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    result = fetch_repo_ci_health_graphql(
        client,
        "hiero-ledger",
        "empty-repo",
    )

    assert result == CIHealthRecord(
        workflows=[],
        has_wiki_enabled=False,
        has_issues_enabled=False,
        has_discussions_enabled=False,
        has_projects_enabled=False,
        web_commit_signoff_required=False,
    )


def test_fetch_repo_ci_health_graphql_reads_dependabot_yaml_variant(monkeypatch):
    """Pick up the `.yaml` spelling of the Dependabot config."""
    client = Mock()
    client.graphql.return_value = {
        "data": {
            "repository": {
                "root": {"entries": [{"name": "go.mod"}]},
                "object": {
                    "entries": [
                        {
                            "name": "dependabot.yaml",
                            "object": {"text": "version: 2\nupdates: []\n"},
                        }
                    ]
                },
            }
        }
    }

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    result = fetch_repo_ci_health_graphql(client, "hiero-ledger", "some-repo")

    assert result is not None
    assert result.dependabot_config == "version: 2\nupdates: []\n"
    assert result.root_entries == ["go.mod"]
    assert result.workflows == []


def test_fetch_repo_ci_health_graphql_without_dependabot_or_root(monkeypatch):
    """Missing root tree and config leave the new fields empty rather than failing."""
    client = Mock()
    client.graphql.return_value = {"data": {"repository": {"object": None, "root": None}}}

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    result = fetch_repo_ci_health_graphql(client, "hiero-ledger", "bare-repo")

    assert result is not None
    assert result.root_entries == []
    assert result.dependabot_config is None
