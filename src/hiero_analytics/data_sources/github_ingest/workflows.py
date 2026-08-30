"""GitHub Actions workflow ingestion via the GraphQL API."""

from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.queries import load_query


def fetch_repo_workflows_graphql(
    client: GitHubClient,
    owner: str,
    repo: str,
) -> list[dict[str, str]]:
    """Fetch workflow YAML files from a repository via GitHub GraphQL."""
    data = client.graphql(
        load_query("workflows"),
        {
            "owner": owner,
            "repo": repo,
        },
    )

    repository = (data.get("data") or {}).get("repository") or {}
    tree = repository.get("object") or {}

    workflows = []

    for entry in tree.get("entries") or []:
        obj = entry.get("object") or {}

        if not entry["name"].endswith((".yml", ".yaml")):
            continue

        if "text" not in obj:
            continue

        workflows.append(
            {
                "name": entry["name"],
                "text": obj["text"],
            }
        )

    return workflows
