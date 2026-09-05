"""GitHub Actions workflow ingestion via GraphQL."""

from __future__ import annotations

from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.queries import load_query


def fetch_repo_workflows_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> list[dict[str, str]]:
    """Fetch workflow YAML files from .github/workflows via GraphQL."""
    data = client.graphql(
        load_query("workflows"),
        {
            "owner": owner,
            "repo": repo,
        },
    )

    repository = (data.get("data") or {}).get("repository") or {}
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

    return workflows
