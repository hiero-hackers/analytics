"""GitHub CI health data ingestion."""

from __future__ import annotations

from dataclasses import dataclass

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
        parameters,
    )

    repository = (data.get("data") or {}).get("repository")
    if not repository:
        return None

    tree = repository.get("object") or {}
    workflows: list[dict[str, str]] = []

    for entry in tree.get("entries") or []:
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
