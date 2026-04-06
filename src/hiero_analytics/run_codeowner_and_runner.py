import logging

from hiero_analytics.analysis.codeowner_workflow_analysis import (
    fetch_repo_workflows,
    has_codeowners_file,
    prepare_org_codeowners_summary,
    prepare_repo_level_codeowner_summary,
    runner_records_to_dataframe,
    prepare_stacked_runner_summary
)
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.cache import load_records_cache, save_records_cache
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.models import CodeOwnersRecord, RepositoryRecord, RunnerRecord
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar
from hiero_analytics.run_scorecard_for_org import fetch_org_repos


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_codeowners_for_repos(client: GitHubClient, org: str, repos: list[RepositoryRecord]) -> list[CodeOwnersRecord]:
    """Fetches CODEOWNERS status for each repository."""
    ttl_seconds = 60 *60 * 12
    kind = "codeowner"
    parameters = {"repo_count": len(repos), "check": "codeowners"}

    cached_records = load_records_cache(
        kind=kind,
        scope=ORG,
        parameters=parameters,
        record_type=CodeOwnersRecord,
        ttl_seconds=ttl_seconds,
        refresh=False
    )

    if cached_records:
        return cached_records

    logger.info("Compliance cache stale or missing. Performing fresh GitHub scan...")
    
    records = [
        CodeOwnersRecord(repo=r.name, status=has_codeowners_file(client, org, r.name))
        for r in repos
    ]

    save_records_cache(
        kind=kind,
        scope=ORG,
        parameters=parameters,
        record_type=CodeOwnersRecord,
        records=records
    )

    return records


def get_workflow_for_repos(client: GitHubClient, org: str, repos: list[RepositoryRecord]) -> list[RunnerRecord]:
    """Fetches or runner data with job-level granularity."""
    ttl_seconds = 60 *60 * 12
    kind = "workflows"
    params = {"n": len(repos)}
    
    cached = load_records_cache(kind, org, params, RunnerRecord, ttl_seconds=ttl_seconds, refresh=False)
    if cached:
        return cached

    records = []
    for r in repos:
        logger.info(f"Processing runners for: {r.name}")
        job_stats = fetch_repo_workflows(client, org, r.name)
        for stat in job_stats:
            records.append(RunnerRecord(
                repo=r.name, 
                workflow_file=stat["file"],
                job_name=stat["job"],
                runner=stat["runner"],
                is_self_hosted=stat["is_self_hosted"]
            ))
    
    save_records_cache(kind, org, params, RunnerRecord, records)
    return records


def main() -> None:
    client = GitHubClient()
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)

    repos = fetch_org_repos(client, ORG)

    if not repos:
        logger.warning("No repositories found for org: %s", ORG)
        return
    
    codeowners = get_codeowners_for_repos(client, ORG, repos)

    codeowners_summary_df = prepare_org_codeowners_summary(codeowners)    
    if not codeowners_summary_df.empty:
        plot_bar(
            df=codeowners_summary_df,
            x_col="status",
            y_col="count",
            title="Organization Wide Codeowners File Summary",
            output_path=org_charts_dir / "org_codeowner_summary.png",
            colors={"Present": "#2A9D8F","Missing": "#E76F51"},
        )

    codeowners_repo_df = prepare_repo_level_codeowner_summary(codeowners)
    if not codeowners_repo_df.empty:
        save_dataframe(df=codeowners_repo_df, path=org_data_dir / "repo_wise_codeowner_status.csv")

    runners = get_workflow_for_repos(client, ORG, repos)

    runners_df = runner_records_to_dataframe(runners)
    if not runners_df.empty:
        save_dataframe(df=runners_df, path=org_data_dir / "org_runner_status.csv")

    runner_stacked_df = prepare_stacked_runner_summary(runners)
    if not runner_stacked_df.empty:
        plot_stacked_bar(
            df=runner_stacked_df,
            x_col="repo",
            stack_cols=["Self-Hosted", "Standard"],
            labels=["Self-Hosted", "Standard"],
            title="Repository Wide Runner Types Breakdown",
            output_path=org_charts_dir / "org_runner_chart.png",
            colors={"Self-Hosted": "#2A9D8F","Standard": "#E76F51"},
            annotate_totals=False
        )


if __name__ == "__main__":
    main()