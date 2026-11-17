"""GitHub CI health data ingestion."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

from hiero_analytics.data_sources.cache import (
    load_records_cache,
    save_records_cache,
)
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.queries import load_query

CI_HEALTH_CACHE_KEY = "ci_health"


@dataclass(frozen=True)
class CIHealthRecord:
    """Raw data required by CI health checks."""

    workflows: list[dict[str, str]]
    has_wiki_enabled: bool
    has_issues_enabled: bool
    has_discussions_enabled: bool
    has_projects_enabled: bool
    web_commit_signoff_required: bool
    dockerfiles: list[dict[str, str | None]] = field(default_factory=list)
    dockerfile_discovery_complete: bool = False


def _is_dockerfile_path(path: str) -> bool:
    """Return whether a path matches Dockerfile naming conventions."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name == "dockerfile" or name.startswith("dockerfile.") or name.endswith(".dockerfile")


def _decode_blob_content(blob_resp: dict[str, Any]) -> str | None:
    """Safely decode base64 blob content to UTF-8 text."""
    if blob_resp.get("encoding") != "base64":
        return None
    raw_content = blob_resp.get("content")
    if not isinstance(raw_content, str):
        return None
    try:
        clean_content = "".join(raw_content.split())
        decoded = base64.b64decode(clean_content, validate=True)
        return decoded.decode("utf-8")
    except Exception:
        return None


def _fetch_dockerfiles(
    client: GitHubClient,
    owner: str,
    repo: str,
    tree_oid: str | None,
) -> tuple[list[dict[str, str | None]], bool]:
    """Discover Dockerfiles via Git Trees API and fetch their blob contents."""
    if not tree_oid:
        return [], False

    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{tree_oid}?recursive=1"
    tree_resp = client.get(tree_url)
    if not isinstance(tree_resp, dict):
        return [], False

    discovery_complete = not bool(tree_resp.get("truncated", False))
    dockerfiles: list[dict[str, str | None]] = []

    for entry in tree_resp.get("tree") or []:
        if entry.get("type") == "blob" and _is_dockerfile_path(entry.get("path", "")):
            sha = entry.get("sha")
            blob_url = f"https://api.github.com/repos/{owner}/{repo}/git/blobs/{sha}"
            blob_resp = client.get(blob_url)
            text = _decode_blob_content(blob_resp) if isinstance(blob_resp, dict) else None
            dockerfiles.append(
                {
                    "path": entry.get("path", ""),
                    "text": text,
                }
            )

    return dockerfiles, discovery_complete


def fetch_repo_ci_health_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
    *,
    use_cache: bool | None = None,
    cache_ttl_seconds: int | None = None,
    refresh: bool = False,
) -> CIHealthRecord | None:
    """Fetch and cache CI health data for one repository."""
    parameters: dict[str, object] = {
        "owner": owner,
        "repo": repo,
        "schema": 2,
    }
    scope = f"{owner}/{repo}"

    cached = load_records_cache(
        CI_HEALTH_CACHE_KEY,
        scope,
        parameters,
        CIHealthRecord,
        use_cache=use_cache,
        ttl_seconds=cache_ttl_seconds,
        refresh=refresh,
    )

    if cached is not None:
        return cached[0] if cached else None

    data = client.graphql(
        load_query("ci_health"),
        {"owner": owner, "repo": repo},
    )

    repository = (data.get("data") or {}).get("repository")
    if not repository:
        return None

    head_commit = repository.get("headCommit") or {}
    tree_oid: str | None = None
    if isinstance(head_commit, dict):
        head_tree = head_commit.get("tree")
        if isinstance(head_tree, dict):
            tree_oid = head_tree.get("oid")

    dockerfiles, dockerfile_discovery_complete = _fetch_dockerfiles(
        client,
        owner,
        repo,
        tree_oid,
    )

    tree = repository.get("object") or {}
    workflows: list[dict[str, str]] = []

    for entry in tree.get("entries") or []:
        if entry.get("name") != "workflows":
            continue

        workflows_tree = entry.get("object") or {}

        for workflow_entry in workflows_tree.get("entries") or []:
            name = workflow_entry.get("name", "")
            obj = workflow_entry.get("object") or {}

            if not name.endswith((".yml", ".yaml")):
                continue

            text = obj.get("text")
            if text is None:
                continue

            workflows.append(
                {
                    "name": name,
                    "text": text,
                }
            )
        name = entry.get("name", "")
        obj = entry.get("object") or {}

        if not name.endswith((".yml", ".yaml")):
            continue

        text = obj.get("text")
        if text is None:
            continue

        workflows.append(
            {
                "name": name,
                "text": text,
            }
        )

    record = CIHealthRecord(
        workflows=workflows,
        has_wiki_enabled=bool(repository.get("hasWikiEnabled")),
        has_issues_enabled=bool(repository.get("hasIssuesEnabled")),
        has_discussions_enabled=bool(repository.get("hasDiscussionsEnabled")),
        has_projects_enabled=bool(repository.get("hasProjectsEnabled")),
        web_commit_signoff_required=bool(repository.get("webCommitSignoffRequired")),
        dockerfiles=dockerfiles,
        dockerfile_discovery_complete=dockerfile_discovery_complete,
    )

    save_records_cache(
        CI_HEALTH_CACHE_KEY,
        scope,
        parameters,
        CIHealthRecord,
        [record],
        use_cache=use_cache,
    )

    return record
