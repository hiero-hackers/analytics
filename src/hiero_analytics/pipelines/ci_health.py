"""Pipeline for GitHub Actions workflow security checks."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.ci_health import check_workflows
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest.workflows import (
    fetch_repo_workflows_graphql,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.pipelines.scorecard import fetch_org_repos


def main(org: str = ORG) -> None:
    """Check organization repositories for unpinned GitHub Actions."""
    client, org_data_dir, _ = org_context(org)

    repos = fetch_org_repos(client, org)

    findings: list[dict[str, str]] = []

    for repo in repos:
        workflows = fetch_repo_workflows_graphql(
            client,
            repo.owner,
            repo.name,
        )

        for workflow_name, unpinned_actions in check_workflows(workflows).items():
            findings.extend(
                {
                    "repo": repo.full_name,
                    "workflow": workflow_name,
                    "action": action,
                }
                for action in unpinned_actions
            )

    df = pd.DataFrame(
        findings,
        columns=["repo", "workflow", "action"],
    )

    save_dataframe(
        df=df,
        path=org_data_dir / "ci_health.csv",
    )
