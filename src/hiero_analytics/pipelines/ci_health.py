"""Pipeline for GitHub Actions workflow security checks."""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.ci_health import (
    check_actions_sha_pinned,
    check_explicit_permissions,
    check_repository_security_configuration,
)
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest.ci_health import (
    fetch_repo_ci_health_graphql,
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
        record = fetch_repo_ci_health_graphql(
            client,
            repo.owner,
            repo.name,
        )

        if record is None:
            continue

        results = [
            check_actions_sha_pinned(record.workflows),
            check_explicit_permissions(record.workflows),
            check_repository_security_configuration(
                record.workflows,
                has_wiki_enabled=record.has_wiki_enabled,
                has_issues_enabled=record.has_issues_enabled,
                has_discussions_enabled=record.has_discussions_enabled,
                has_projects_enabled=record.has_projects_enabled,
                web_commit_signoff_required=record.web_commit_signoff_required,
            ),
        ]

        findings.extend(
            {
                "repo": repo.full_name,
                "check": result.check,
                "band": result.band,
                "status": result.status,
                "evidence": result.evidence,
                "location": result.location,
            }
            for result in results
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
