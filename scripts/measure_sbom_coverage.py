"""Measure real SBOM coverage for an org — the gating question on #338.

Not a registered pipeline; this is throwaway measurement code to answer
"how many repos have a readable dependency-graph SBOM" before investing in
the resolution heuristic or the chart. Run directly:

    uv run python measure_sbom_coverage.py

Requires GITHUB_TOKEN in the environment (same as any other pipeline run).
Prints a coverage breakdown and writes the raw per-repo results to
sbom_coverage_raw.csv for closer inspection.
"""

from __future__ import annotations

import csv

from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_repos_graphql
from hiero_analytics.data_sources.github_rest import fetch_org_sbom_data


def main(org: str = ORG) -> None:
    """Fetch SBOM coverage for every repo in ``org`` and print a summary."""
    client = GitHubClient()

    repos = fetch_org_repos_graphql(client, org)
    if not repos:
        print(f"No repositories found for org: {org}")
        return

    repo_names = [r.name for r in repos]
    print(f"Fetching SBOM data for {len(repo_names)} repos in {org}...")

    coverage, packages = fetch_org_sbom_data(client, org, repo_names)

    by_status: dict[str, list] = {}
    for c in coverage:
        by_status.setdefault(c.status, []).append(c)

    print()
    print("=== Coverage summary ===")
    for status in ("ok", "disabled", "error"):
        rows = by_status.get(status, [])
        print(f"{status:>10}: {len(rows)} repos")

    ok_rows = by_status.get("ok", [])
    nonzero = [c for c in ok_rows if c.package_count > 0]
    zero = [c for c in ok_rows if c.package_count == 0]
    print()
    print(f"Of the {len(ok_rows)} repos with a readable SBOM:")
    print(f"  {len(nonzero)} have at least one dependency ({sum(c.package_count for c in nonzero)} packages total)")
    print(f"  {len(zero)} have a readable but empty manifest")

    print()
    print(f"Total dependency edges (all ecosystems, unresolved to org repos yet): {len(packages)}")
    ecosystems: dict[str, int] = {}
    for p in packages:
        ecosystems[p.ecosystem] = ecosystems.get(p.ecosystem, 0) + 1
    for eco, n in sorted(ecosystems.items(), key=lambda kv: -kv[1]):
        print(f"  {eco}: {n}")

    with open("sbom_coverage_raw.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["repo", "status", "package_count"])
        for c in sorted(coverage, key=lambda c: c.repo):
            writer.writerow([c.repo, c.status, c.package_count])

    print()
    print("Wrote per-repo detail to sbom_coverage_raw.csv")


if __name__ == "__main__":
    main()
