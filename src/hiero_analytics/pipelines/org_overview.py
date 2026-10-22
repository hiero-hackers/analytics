"""Org overview — the composition-level cards for an organization.

Orchestration only: it builds the org-wide cards (repositories ranked by
contributor count, language mix, recent pushes) for one org. The pipeline
registry declares it ``requires={"org_overview"}``, so the full run schedules
it for every org whose profile has that capability; registering another
composition org in ``config/orgs.py`` gains it these cards with no new code.

Tables are written to ``outputs/data/org/<org>/``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from hiero_analytics.analysis.org_overview_analysis import (
    build_contributor_counts,
    calculate_language_distribution,
    calculate_push_activity_summary,
    repos_to_dataframe,
)
from hiero_analytics.config.orgs import has_org_overview, rendered_orgs
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.github_ingest import fetch_org_repos_graphql
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import load_contributor_activity, org_context

logger = logging.getLogger(__name__)

# The contributor-count card covers roughly the last six months. It reads the
# persisted org-wide activity dataset (which the contributor_activity pipeline
# keeps current earlier in the same run) and keeps this window of it, rather
# than fetching a separate rolling window from GitHub every run.
CONTRIBUTOR_WINDOW_DAYS = 183


def _build_org_overview(org: str) -> None:
    """Build the org-wide composition cards for one org."""
    client, data_dir = org_context(org)

    repo_records = fetch_org_repos_graphql(client, org)
    cutoff = datetime.now(UTC) - timedelta(days=CONTRIBUTOR_WINDOW_DAYS)
    activity_records = [
        record
        for record in load_contributor_activity(client, org)
        if record.occurred_at is not None and record.occurred_at >= cutoff
    ]

    repos_df = repos_to_dataframe(repo_records)

    # Language distribution, only when the org has repos to describe.
    language_df = calculate_language_distribution(repos_df)
    if not language_df.empty:
        save_dataframe(language_df, data_dir / "language_distribution.csv")

    # Push activity, only when the values are non-zero
    activity_df = calculate_push_activity_summary(repos_df, days=30)
    if not activity_df.empty and activity_df["count"].sum() > 0:
        save_dataframe(activity_df, data_dir / "push_activity.csv")

    contributors_df = build_contributor_counts(activity_records)
    if not contributors_df.empty:
        contributors_df = contributors_df.sort_values("contributors", ascending=False)
        save_dataframe(contributors_df, data_dir / "contributor_counts.csv")

    logger.info("Org overview complete for %s. Tables written to %s", org, data_dir)


def main(org: str | None = None) -> None:
    """Build the org-overview cards for ``org``.

    The full run passes each org whose profile has the ``org_overview``
    capability (``run_all``). Run alone without ``--org``, it builds the
    rendered orgs that have the capability, as it always has.
    """
    targets = [org] if org else [name for name in rendered_orgs() if has_org_overview(name)] or [ORG]
    for target in targets:
        _build_org_overview(target)
