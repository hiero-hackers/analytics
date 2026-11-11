"""Tests for GitHub CI health data ingestion."""

import base64
from unittest.mock import Mock

import pytest
import requests

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

    load_cache = Mock(return_value=None)
    save_cache = Mock()

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        load_cache,
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

    expected_params = {
        "owner": "hiero-ledger",
        "repo": "hiero-sdk-java",
        "schema": 2,
    }
    load_cache.assert_called_once_with(
        "ci_health",
        "hiero-ledger/hiero-sdk-java",
        expected_params,
        CIHealthRecord,
        use_cache=None,
        ttl_seconds=None,
        refresh=False,
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
        dockerfiles=[],
        dockerfile_discovery_complete=False,
    )

    client.graphql.assert_called_once()
    assert client.graphql.call_args[0][1] == {"owner": "hiero-ledger", "repo": "hiero-sdk-java"}
    save_cache.assert_called_once_with(
        "ci_health",
        "hiero-ledger/hiero-sdk-java",
        expected_params,
        CIHealthRecord,
        [result],
        use_cache=None,
    )


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


def test_fetch_repo_ci_health_graphql_dockerfile_discovery(monkeypatch):
    """Discover Dockerfiles across the repo and fetch selected blobs."""
    tree_oid = "tree123"
    graphql_data = {
        "data": {
            "repository": {
                "hasWikiEnabled": False,
                "hasIssuesEnabled": False,
                "hasDiscussionsEnabled": False,
                "hasProjectsEnabled": False,
                "webCommitSignoffRequired": False,
                "headCommit": {"oid": "commit123", "tree": {"oid": tree_oid}},
                "object": {"entries": []},
            }
        }
    }

    tree_entries = [
        {"path": "Dockerfile", "type": "blob", "sha": "sha_root"},
        {"path": "docker/Dockerfile.prod", "type": "blob", "sha": "sha_prod"},
        {"path": "build/app.dockerfile", "type": "blob", "sha": "sha_app"},
        {"path": "README.md", "type": "blob", "sha": "sha_readme"},
        {"path": "docker", "type": "tree", "sha": "sha_dir"},
        {"path": "submodule", "type": "commit", "sha": "sha_sub"},
        {"path": "dockerfile_helper.py", "type": "blob", "sha": "sha_helper"},
    ]

    requested_urls: list[str] = []

    def mock_get(url: str):
        requested_urls.append(url)
        if url.endswith(f"/git/trees/{tree_oid}?recursive=1"):
            return {"tree": tree_entries, "truncated": False}
        if url.endswith("/git/blobs/sha_root"):
            return {"encoding": "base64", "content": base64.b64encode(b"FROM alpine:3.18\n").decode()}
        if url.endswith("/git/blobs/sha_prod"):
            return {"encoding": "base64", "content": base64.b64encode(b"FROM python:3.11\n").decode()}
        if url.endswith("/git/blobs/sha_app"):
            return {"encoding": "base64", "content": base64.b64encode(b"FROM node:20\n").decode()}
        raise AssertionError(f"Unexpected GET URL: {url}")

    client = Mock()
    client.graphql.return_value = graphql_data
    client.get.side_effect = mock_get

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    result = fetch_repo_ci_health_graphql(client, "hiero-ledger", "repo-docker")

    assert result is not None
    assert result.dockerfile_discovery_complete is True
    assert result.dockerfiles == [
        {"path": "Dockerfile", "text": "FROM alpine:3.18\n"},
        {"path": "docker/Dockerfile.prod", "text": "FROM python:3.11\n"},
        {"path": "build/app.dockerfile", "text": "FROM node:20\n"},
    ]

    expected_urls = [
        "https://api.github.com/repos/hiero-ledger/repo-docker/git/trees/tree123?recursive=1",
        "https://api.github.com/repos/hiero-ledger/repo-docker/git/blobs/sha_root",
        "https://api.github.com/repos/hiero-ledger/repo-docker/git/blobs/sha_prod",
        "https://api.github.com/repos/hiero-ledger/repo-docker/git/blobs/sha_app",
    ]
    assert requested_urls == expected_urls


def test_fetch_repo_ci_health_graphql_dockerfile_truncated(monkeypatch):
    """When recursive tree is truncated, discovery completeness is marked False."""
    graphql_data = {
        "data": {
            "repository": {
                "headCommit": {"oid": "commit123", "tree": {"oid": "tree_trunc"}},
                "object": {"entries": []},
            }
        }
    }

    client = Mock()
    client.graphql.return_value = graphql_data
    client.get.return_value = {
        "tree": [{"path": "Dockerfile", "type": "blob", "sha": "sha1"}],
        "truncated": True,
    }

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    result = fetch_repo_ci_health_graphql(client, "hiero-ledger", "repo-trunc")

    assert result is not None
    assert result.dockerfile_discovery_complete is False


def test_fetch_repo_ci_health_graphql_null_head_no_rest_call(monkeypatch):
    """Null HEAD commit makes no REST call and marks discovery incomplete."""
    graphql_data = {
        "data": {
            "repository": {
                "headCommit": None,
                "object": {"entries": []},
            }
        }
    }

    client = Mock()
    client.graphql.return_value = graphql_data

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    result = fetch_repo_ci_health_graphql(client, "hiero-ledger", "empty-repo")

    assert result is not None
    assert result.dockerfile_discovery_complete is False
    assert result.dockerfiles == []
    client.get.assert_not_called()


def test_fetch_repo_ci_health_graphql_blob_decoding_failures(monkeypatch):
    """Decoding errors (bad base64, bad utf-8, non-base64 encoding, missing) result in text=None."""
    graphql_data = {
        "data": {
            "repository": {
                "headCommit": {"oid": "c1", "tree": {"oid": "t1"}},
                "object": {"entries": []},
            }
        }
    }

    tree_entries = [
        {"path": "Dockerfile.invalid_b64", "type": "blob", "sha": "sha_b64"},
        {"path": "Dockerfile.invalid_utf8", "type": "blob", "sha": "sha_utf8"},
        {"path": "Dockerfile.not_base64", "type": "blob", "sha": "sha_enc"},
        {"path": "Dockerfile.no_content", "type": "blob", "sha": "sha_empty"},
    ]

    def mock_get(url: str):
        if "git/trees" in url:
            return {"tree": tree_entries, "truncated": False}
        if "sha_b64" in url:
            return {"encoding": "base64", "content": "not-valid-base64!!!"}
        if "sha_utf8" in url:
            return {"encoding": "base64", "content": base64.b64encode(b"\xff\xfe\xfd").decode()}
        if "sha_enc" in url:
            return {"encoding": "utf-8", "content": "FROM alpine"}
        if "sha_empty" in url:
            return {"encoding": "base64", "content": None}
        raise AssertionError(f"Unexpected URL {url}")

    client = Mock()
    client.graphql.return_value = graphql_data
    client.get.side_effect = mock_get

    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        Mock(),
    )

    result = fetch_repo_ci_health_graphql(client, "hiero-ledger", "repo-decode")

    assert result is not None
    assert result.dockerfile_discovery_complete is True
    assert len(result.dockerfiles) == 4
    for df in result.dockerfiles:
        assert df["text"] is None


def test_fetch_repo_ci_health_graphql_tree_http_error_propagates(monkeypatch):
    """HTTP 500 on the tree request propagates and no record is saved."""
    graphql_data = {
        "data": {
            "repository": {
                "headCommit": {"oid": "c1", "tree": {"oid": "t1"}},
                "object": {"entries": []},
            }
        }
    }

    client = Mock()
    client.graphql.return_value = graphql_data
    response = Mock()
    response.status_code = 500
    client.get.side_effect = requests.HTTPError(response=response)

    save_cache = Mock()
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.load_records_cache",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        "hiero_analytics.data_sources.github_ingest.ci_health.save_records_cache",
        save_cache,
    )

    with pytest.raises(requests.HTTPError):
        fetch_repo_ci_health_graphql(client, "hiero-ledger", "repo-err")

    save_cache.assert_not_called()
