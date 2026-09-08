"""Pipeline for GitHub Actions workflow security checks."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.ci_health import check_actions_sha_pinned
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest.workflows import (
    fetch_repo_workflows_graphql,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.pipelines.scorecard import fetch_org_repos


def main(org: str = ORG) -> None:
    """Check organization repositories for CI health issues."""
    client, org_data_dir, _ = org_context(org)

    repos = fetch_org_repos(client, org)

    findings: list[dict[str, str]] = []

    for repo in repos:
        workflows = fetch_repo_workflows_graphql(
            client,
            repo.owner,
            repo.name,
        )

        result = check_actions_sha_pinned(workflows)

        findings.append(
            {
                "repo": repo.full_name,
                "check": result.check,
                "band": result.band,
                "status": result.status,
                "evidence": result.evidence,
                "location": result.location,
            }
        )

    df = pd.DataFrame(
        findings,
        columns=[
            "repo",
            "check",
            "band",
            "status",
            "evidence",
            "location",
        ],
    )

    save_dataframe(
        df=df,
        path=org_data_dir / "ci_health_checks.csv",
    )
