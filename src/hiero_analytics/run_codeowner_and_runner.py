import logging

from hiero_analytics.analysis.codeowner_workflow_analysis import (
    prepare_org_codeowners_summary,
    prepare_repo_level_codeowner_summary,
    runner_records_to_dataframe,
    prepare_stacked_runner_summary
)
from hiero_analytics.data_sources.github_search import (
    fetch_repo_workflows,
    has_codeowners_file,
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


def generate_codeowners_markdown_report(records: list[CodeOwnersRecord], output_path: str) -> None:
    """Generates a Markdown table showing CODEOWNERS status with ticks and crosses."""
    lines = [
        "# CODEOWNERS Compliance Report",
        "",
        "| Repository | Status |",
        "| :--- | :---: |"
    ]
    
    for record in records:
        status_icon = "✅" if record.status else "❌"
        lines.append(f"| {record.repo} | {status_icon} |")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    logger.info(f"Markdown report saved to: {output_path}")

def generate_runner_markdown_report(records: list[RunnerRecord], output_file: str) -> None:
    """Generates a Markdown report from RunnerRecord dataclass objects."""
    repos: dict[str, list[RunnerRecord]] = {}
    for r in records:
        repo_name = r.repo
        if repo_name not in repos:
            repos[repo_name] = []
        repos[repo_name].append(r)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# GitHub Actions Runner Compliance Report\n\n")
        f.write("This report categorizes runners into **Self-Hosted**, **Standard (GitHub-hosted)**, and **Indeterminate (Dynamic)**.\n\n")

        f.write("| Repository | Self-Hosted (✅) | Standard (❌) | Indeterminate (⚠️) |\n")
        f.write("| :--- | :---: | :---: | :---: |\n")

        for repo_name in sorted(repos.keys()):
            data = repos[repo_name]
            self_count = sum(1 for x in data if x.is_self_hosted is True)
            std_count = sum(1 for x in data if x.is_self_hosted is False)
            ind_count = sum(1 for x in data if x.is_self_hosted is None)
            f.write(f"| **{repo_name}** | {self_count} | {std_count} | {ind_count} |\n")

        f.write("\n---\n\n")

    print(f"Runner report successfully generated: {output_file}")


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

    generate_codeowners_markdown_report(
        records=codeowners, 
        output_path=org_data_dir / "codeowners_report.md"
    )

    runners = get_workflow_for_repos(client, ORG, repos)

    runners_df = runner_records_to_dataframe(runners)
    if not runners_df.empty:
        save_dataframe(df=runners_df, path=org_data_dir / "org_runner_status.csv")
    
    generate_runner_markdown_report(
        records=runners,
        output_file=str(org_data_dir / "runner_report.md")
    )

    runner_stacked_df = prepare_stacked_runner_summary(runners)
    if not runner_stacked_df.empty:
        plot_stacked_bar(
            df=runner_stacked_df,
            x_col="repo",
            stack_cols=["Self-Hosted", "Standard", "Indeterminate"],
            labels=["Self-Hosted", "Standard", "Indeterminate"],
            title="Repository Wide Runner Types Breakdown",
            output_path=org_charts_dir / "org_runner_chart.png",
            colors={"Self-Hosted": "#2A9D8F","Standard": "#E76F51", "Indeterminate": "#94A3B8"},
            annotate_totals=False
        )


if __name__ == "__main__":
    main()