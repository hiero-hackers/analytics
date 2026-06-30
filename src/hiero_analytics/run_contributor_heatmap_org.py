"""Render the contributor-activity heatmap for an organization.

Orchestration only: it reuses the persisted org-wide contributor-activity dataset
(populated earlier in ``run_all``, so no extra GitHub fetch when present), builds
the weighted monthly matrix (:mod:`analysis.contributor_heatmap`) and renders it
(:func:`plotting.heatmap.plot_heatmap`). The ranked, score-based companion to the
descriptive profiles/networks in ``run_contributor_activity_org``.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from hiero_analytics.analysis.contributor_heatmap import (
    build_activity_heatmap_dataframe,
    heatmap_chart_data,
)
from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, ensure_org_dirs
from hiero_analytics.data_sources.dataset_store import load_or_fetch
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_org_contributor_activity_graphql
from hiero_analytics.data_sources.governance_config import build_repo_role_lookup, fetch_governance_config
from hiero_analytics.data_sources.models import ContributorActivityRecord
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.heatmap import plot_heatmap

logger = logging.getLogger(__name__)

# Secondary composition org rendered alongside the primary org. It has no
# governance config, so its contributors carry no role label — the heatmap colours
# by activity rather than role, so the chart itself is unaffected.
HACKERS_ORG = "hiero-hackers"


def _load_or_fetch_records(client: GitHubClient, org: str) -> list[ContributorActivityRecord]:
    """Reuse the persisted org-wide contributor-activity dataset for ``org``, or fetch it.

    The same ``all`` dataset is populated by the maintainer/profile pipelines earlier
    in ``run_all``, so this reads it from disk instead of issuing another org-wide fetch.
    """
    return load_or_fetch(
        "contributor_activity",
        org,
        ContributorActivityRecord,
        lambda: fetch_org_contributor_activity_graphql(client, org=org, lookback_days=None),
    )


def _save_heatmap_chart(heatmap_df: pd.DataFrame, output_path: Path) -> None:
    """Render the heatmap PNG for the top contributors, if there's data to show."""
    chart = heatmap_chart_data(heatmap_df)
    if chart is None:
        return
    values, row_labels, col_labels = chart
    plot_heatmap(
        values,
        row_labels=row_labels,
        col_labels=col_labels,
        output_path=output_path,
        title=f"Top {len(row_labels)} Contributor Activity Heatmap",
        xlabel="Month",
        ylabel="Contributor",
        value_label="Weighted monthly activity score",
    )


def _build_heatmap_for_org(
    org: str,
    repo_role_lookup: dict[str, dict[str, str]],
    client: GitHubClient,
) -> None:
    """Build the heatmap (data table + chart) for one org from its activity dataset."""
    org_data_dir, org_charts_dir = ensure_org_dirs(org)
    records = _load_or_fetch_records(client, org)
    logger.info("Using %d activity records for the %s heatmap", len(records), org)

    heatmap_df = build_activity_heatmap_dataframe(records, repo_role_lookup)
    save_dataframe(heatmap_df, org_data_dir / "contributor_activity_heatmap.csv")
    _save_heatmap_chart(heatmap_df, org_charts_dir / "contributor_activity_heatmap.png")
    logger.info("Contributor activity heatmap complete for %s (%d contributors)", org, len(heatmap_df))


def main() -> None:
    """Build the contributor-activity heatmap for the primary org and hiero-hackers."""
    client = GitHubClient()

    # Primary org: contributors are labelled by their governance role.
    _build_heatmap_for_org(ORG, build_repo_role_lookup(fetch_governance_config()), client)

    # Secondary composition org: no governance config, so no role labels. Isolated
    # so a problem here can't drop the primary org's heatmap.
    if HACKERS_ORG != ORG:
        try:
            _build_heatmap_for_org(HACKERS_ORG, {}, client)
        except Exception:
            logger.exception("Heatmap for %s failed; the primary org heatmap is unaffected", HACKERS_ORG)


if __name__ == "__main__":
    setup_logging()
    main()
