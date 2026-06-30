"""Build the informational contributor-activity tables for an organization.

For each contributor this writes a high-level view of *how they show up* — their
work split across three neutral families (building & fixing, reviewing & guiding,
organizing & answering) — as CSV tables only, org-wide and per-repository. It is
deliberately descriptive: counts and shares, no score and no cross-contributor
ranking. Rows are ordered by ``last_active`` (recency).

This complements ``run_maintainer_pipeline_org`` (which maps activity onto named
governance roles); here we never name or rank roles.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from hiero_analytics.analysis.comembership import build_comembership_network
from hiero_analytics.analysis.contributor_activity_profile import (
    build_active_membership,
    build_contributor_profiles,
    build_contributor_profiles_by_repo,
)
from hiero_analytics.config.analysis import CONTRIBUTOR_NETWORK_REPOS_PER_LINK, ROLE_ACTIVE_DAYS
from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, ensure_org_dirs, ensure_repo_dirs
from hiero_analytics.data_sources.dataset_store import load_or_fetch
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_contributor_activity_graphql,
    fetch_org_issue_label_events_graphql,
)
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    IssueTimelineEventRecord,
)
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.network import render_comembership_network

logger = logging.getLogger(__name__)


def _build_contributor_network(records, label_events, by_repo, org_charts_dir) -> None:
    """Render the all-contributors co-membership network for the org.

    Governance-independent (no roles needed), so it runs for every org. Repos are
    sized by active contributors and linked when they share contributors; the link
    threshold scales with org size so a large org stays legible and a small one
    still shows its overlaps.
    """
    cutoff = datetime.now(UTC) - timedelta(days=ROLE_ACTIVE_DAYS)
    recent_records = [r for r in records if r.occurred_at and r.occurred_at >= cutoff]
    recent_labels = [e for e in label_events if e.occurred_at and e.occurred_at >= cutoff]
    recent_by_repo = build_contributor_profiles_by_repo(recent_records, recent_labels)

    membership = build_active_membership(by_repo, recent_by_repo)
    min_shared = max(1, round(len(by_repo) / CONTRIBUTOR_NETWORK_REPOS_PER_LINK))
    nodes, edges = build_comembership_network(membership, min_shared=min_shared)
    if render_comembership_network(
        nodes, edges, org_charts_dir / "all_network.png",
        title=f"{ORG} — contributors network (repos linked by shared contributors)",
        member_label="contributors",
    ):
        logger.info("Contributor network: %d repos, %d links (shared>=%d)", len(nodes), len(edges), min_shared)


def main() -> None:
    """Build the informational contributor-activity tables for the org."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)

    logger.info("Building contributor activity tables for org: %s", ORG)

    client = GitHubClient()
    # Reuse the datasets the maintainer/fetch pipelines persisted earlier in run_all
    # (avoiding extra org-wide fetches); falls back to fetching on a cold start.
    records = load_or_fetch(
        "contributor_activity",
        ORG,
        ContributorActivityRecord,
        lambda: fetch_org_contributor_activity_graphql(client, org=ORG, lookback_days=None),
    )
    label_events = load_or_fetch(
        "issue_label_events",
        ORG,
        IssueTimelineEventRecord,
        lambda: fetch_org_issue_label_events_graphql(client, org=ORG),
    )
    logger.info("Using %d activity records and %d label events (all-time)", len(records), len(label_events))

    # Org-wide: one row per contributor across all repos (cumulative, all-time).
    profiles = build_contributor_profiles(records, label_events)
    save_dataframe(profiles, org_data_dir / "contributor_activity_profiles.csv")
    logger.info("Built org-wide profiles for %d contributors", len(profiles))

    # Per-repository: the same table scoped to each repo, so a person's shape can
    # be seen to shift across repos. Written under each repo's data dir.
    by_repo = build_contributor_profiles_by_repo(records, label_events)
    for repo, repo_profiles in by_repo.items():
        repo_data_dir, _ = ensure_repo_dirs(repo)
        save_dataframe(repo_profiles, repo_data_dir / "contributor_activity_profiles.csv")
    logger.info("Wrote per-repo profiles for %d repositories", len(by_repo))

    # All-contributors network (no governance needed, so every org gets it).
    _build_contributor_network(records, label_events, by_repo, org_charts_dir)

    logger.info("Contributor activity tables complete")


if __name__ == "__main__":
    setup_logging()
    main()
