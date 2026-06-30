"""Build per-repository role-coverage tables: governance roles vs. real activity.

For each repo with governance-assigned roles, writes who holds triage / committer
/ maintainer permissions, their contribution counts in that repo (both all-time and
over the last ``ROLE_ACTIVE_DAYS`` days, as ``*_recent`` columns), and whether they
are currently active or **quiet in that repo** (no activity in that window) — plus a
combined ``role_coverage_all`` table (filter by repo) and the inverse
promotion-candidate list. Status and days-since-active reflect all-time recency.
Because roles are granted per repo, the only org-wide quiet list is
``role_coverage_globally_quiet``: holders with no activity in *any* repo for over
``GONE_DARK_DAYS`` days. Also emits team-activity and TSC tables.

This complements the role-agnostic contributor-activity tables; here we use the
role names deliberately, to show each permission-holder's recent activity in the
context of the role they hold.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pandas as pd

from hiero_analytics.analysis.comembership import build_comembership_network, role_membership
from hiero_analytics.analysis.contributor_activity_profile import (
    build_account_activity_by_repo,
    build_active_membership,
    build_contributor_profiles,
    build_contributor_profiles_by_repo,
    latest_activity_by_account,
    latest_activity_by_repo_account,
)
from hiero_analytics.analysis.repo_summaries import (
    build_repo_activity_overview,
    build_review_load_share,
    find_understaffed_repos,
)
from hiero_analytics.analysis.role_coverage import (
    annotate_repo_roles,
    build_repo_role_coverage,
    find_globally_quiet_role_holders,
    find_unbadged_role_work,
)
from hiero_analytics.analysis.team_activity import (
    build_team_activity_by_repo,
    build_team_activity_summary,
)
from hiero_analytics.config.analysis import (
    GONE_DARK_DAYS,
    LOAD_SHARE_MIN_ACTIONS,
    ROLE_ACTIVE_DAYS,
    ROLE_NETWORK_MIN_SHARED,
    UNDERSTAFFED_MAX_ACTIVE_MAINTAINERS,
)
from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, ensure_org_dirs, ensure_repo_dirs
from hiero_analytics.data_sources.dataset_store import load_or_fetch
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_org_contributor_activity_graphql,
    fetch_org_issue_label_events_graphql,
)
from hiero_analytics.data_sources.governance_config import (
    build_repo_role_lookup,
    build_team_membership,
    fetch_governance_config,
)
from hiero_analytics.data_sources.models import ContributorActivityRecord, IssueTimelineEventRecord
from hiero_analytics.domain.repos import bare_repo
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.plotting.network import render_comembership_network

logger = logging.getLogger(__name__)
# Thresholds live in config.analysis (ROLE_ACTIVE_DAYS, GONE_DARK_DAYS, the network
# link cutoffs, etc.) so they're discoverable and tunable in one place.


def _build_profile_sets(records, label_events, now):
    """All-time + windowed per-repo profiles and the all-time recency maps.

    Returns ``(all_time_by_repo, all_time_org_profiles, recent_by_repo,
    repo_last_seen, global_last_seen)``. Counts are all-time except ``recent_by_repo``
    (the last ``ROLE_ACTIVE_DAYS`` days, for role coverage's ``*_recent`` columns).
    """
    all_time_by_repo = build_contributor_profiles_by_repo(records, label_events)
    all_time_org_profiles = build_contributor_profiles(records, label_events)
    cutoff = now - timedelta(days=ROLE_ACTIVE_DAYS)
    w_records = [r for r in records if r.occurred_at and r.occurred_at >= cutoff]
    w_labels = [e for e in label_events if e.occurred_at and e.occurred_at >= cutoff]
    recent_by_repo = build_contributor_profiles_by_repo(w_records, w_labels)
    repo_last_seen = latest_activity_by_repo_account(records, label_events)
    global_last_seen = latest_activity_by_account(records, label_events)
    return all_time_by_repo, all_time_org_profiles, recent_by_repo, repo_last_seen, global_last_seen


def _write_role_coverage(roles_by_repo, all_time_by_repo, recent_by_repo, repo_last_seen, *, now):
    """Write each repo's role-coverage + promotion-candidate files; return the combined table.

    Counts are all-time with windowed ``*_recent`` columns; status/recency is all-time.
    Every repo with role-holders is covered, even quiet ones.
    """
    # Cover every governance repo that has role-holders — including quiet ones with
    # no recorded activity (often the highest-risk repos) — not just repos seen in
    # the activity data.
    role_repo_fulls = {f"{ORG}/{bare}" for bare in roles_by_repo}
    all_repo_names = {repo for repo, _ in repo_last_seen} | set(all_time_by_repo) | role_repo_fulls
    coverage_all = []
    for repo_full in sorted(all_repo_names):
        holders = roles_by_repo.get(bare_repo(repo_full))
        if not holders:
            continue
        profiles = all_time_by_repo.get(repo_full, pd.DataFrame())
        recent = recent_by_repo.get(repo_full, pd.DataFrame())
        seen = {acct: when for (rp, acct), when in repo_last_seen.items() if rp == repo_full}

        coverage = build_repo_role_coverage(
            holders, profiles, seen, now=now, active_within_days=ROLE_ACTIVE_DAYS, recent_profiles=recent
        )
        candidates = find_unbadged_role_work(profiles, holders, now=now, active_within_days=ROLE_ACTIVE_DAYS)

        repo_data_dir, _ = ensure_repo_dirs(repo_full)
        save_dataframe(coverage, repo_data_dir / "role_coverage.csv")
        save_dataframe(candidates, repo_data_dir / "role_promotion_candidates.csv")

        if not coverage.empty:
            labelled = coverage.copy()
            labelled.insert(0, "repo", repo_full)
            coverage_all.append(labelled)

    return pd.concat(coverage_all, ignore_index=True) if coverage_all else pd.DataFrame()


def _write_repo_summaries(combined, org_data_dir):
    """Per-repo activity overview, maintainer-coverage, and review-load-share tables."""
    overview = build_repo_activity_overview(combined)
    save_dataframe(overview, org_data_dir / "repo_activity_overview.csv")
    logger.info("Repo activity overview: %d repositories with role-holders", len(overview))

    understaffed = find_understaffed_repos(combined, max_active_maintainers=UNDERSTAFFED_MAX_ACTIVE_MAINTAINERS)
    save_dataframe(understaffed, org_data_dir / "maintainer_coverage_risk.csv")
    logger.info("Repos with <=1 active maintainer: %d", len(understaffed))

    load_share = build_review_load_share(combined, min_actions=LOAD_SHARE_MIN_ACTIONS)
    load_cols = ["repo", "mergers", "load_recent", "top_carrier", "top_role", "top_pct", "top2_pct"]
    if load_share.empty:
        load_table = pd.DataFrame(columns=load_cols)
    else:
        load_table = load_share.assign(
            top_pct=(load_share["top_share"] * 100).round().astype(int),
            top2_pct=(load_share["top2_share"] * 100).round().astype(int),
        )[load_cols]
    save_dataframe(load_table, org_data_dir / "review_load_share.csv")
    logger.info("Review load share: %d repos (>=%d review+merge in window)", len(load_share), LOAD_SHARE_MIN_ACTIONS)


def _write_role_networks(combined, all_time_by_repo, recent_by_repo, role_lookup, org_charts_dir):
    """Maintainer / committer / triage / general co-membership networks.

    "General" = contributors holding no governance role. The all-contributors network
    is governance-independent and produced by run_contributor_activity_org (every org).
    """
    role_holder_logins = frozenset(u.lower() for holders in role_lookup.values() for u in holders)
    general_membership = build_active_membership(all_time_by_repo, recent_by_repo, exclude=role_holder_logins)

    groups = [
        ("maintainer", "maintainers", role_membership(combined, "maintainer"),
         ROLE_NETWORK_MIN_SHARED["maintainer"]),
        ("committer", "committers", role_membership(combined, "committer"),
         ROLE_NETWORK_MIN_SHARED["committer"]),
        ("triage", "triage", role_membership(combined, "triage"), ROLE_NETWORK_MIN_SHARED["triage"]),
        ("general", "general contributors", general_membership, ROLE_NETWORK_MIN_SHARED["general"]),
    ]
    for key, label, membership, min_shared in groups:
        nodes, edges = build_comembership_network(membership, min_shared=min_shared)
        if render_comembership_network(
            nodes, edges, org_charts_dir / f"{key}_network.png",
            title=f"{ORG} — {label} network (repos linked by shared {label})",
            member_label=label,
        ):
            logger.info("%s network: %d repos, %d links (shared>=%d)", label, len(nodes), len(edges), min_shared)


def _write_team_tables(config, role_lookup, all_time_by_repo, all_time_org_profiles, global_last_seen, org_data_dir, *, now):
    """Gone-dark holders, team-activity tables, and spotlight (maintainer/TSC) by-repo tables."""
    globally_quiet = find_globally_quiet_role_holders(
        role_lookup, global_last_seen, now=now, threshold_days=GONE_DARK_DAYS
    )
    save_dataframe(globally_quiet, org_data_dir / "role_coverage_globally_quiet.csv")
    logger.info("%d role-holders with no activity in any repo (>%d days)", len(globally_quiet), GONE_DARK_DAYS)

    team_members = build_team_membership(config)
    team_summary = build_team_activity_summary(
        team_members, all_time_org_profiles, global_last_seen, now=now, dark_after_days=GONE_DARK_DAYS
    )
    team_by_repo = build_team_activity_by_repo(team_members, all_time_by_repo)
    save_dataframe(team_summary, org_data_dir / "team_activity_summary.csv")
    save_dataframe(team_by_repo, org_data_dir / "team_activity_by_repo.csv")
    quiet_teams = int((team_summary["status"] == "quiet").sum()) if not team_summary.empty else 0
    logger.info("Team activity: %d teams (%d quiet)", len(team_summary), quiet_teams)

    for label, members in (
        ("maintainer", {u for h in role_lookup.values() for u, r in h.items() if r == "maintainer"}),
        ("tsc", team_members.get("tsc", set())),
    ):
        table = annotate_repo_roles(build_account_activity_by_repo(members, all_time_by_repo), role_lookup)
        filename = "maintainer_activity_by_repo.csv" if label == "maintainer" else "tsc_activity_by_repo.csv"
        save_dataframe(table, org_data_dir / filename)
        count = table["account"].nunique() if not table.empty else 0
        logger.info("Wrote %s-by-repo activity for %d accounts", label, count)


def main() -> None:
    """Build per-repo role-coverage tables for the org's governance roles."""
    org_data_dir, org_charts_dir = ensure_org_dirs(ORG)
    now = datetime.now(UTC)

    config = fetch_governance_config()
    role_lookup = build_repo_role_lookup(config)
    # Governance keys are bare repo names; activity keys are "owner/repo".
    roles_by_repo = {bare_repo(repo): holders for repo, holders in role_lookup.items()}
    logger.info("Loaded governance roles for %d repos", len(roles_by_repo))

    client = GitHubClient()
    records = load_or_fetch(
        "contributor_activity", ORG, ContributorActivityRecord,
        lambda: fetch_org_contributor_activity_graphql(client, org=ORG, lookback_days=None),
    )
    label_events = load_or_fetch(
        "issue_label_events", ORG, IssueTimelineEventRecord,
        lambda: fetch_org_issue_label_events_graphql(client, org=ORG),
    )

    profiles = _build_profile_sets(records, label_events, now)
    all_time_by_repo, all_time_org_profiles, recent_by_repo, repo_last_seen, global_last_seen = profiles
    logger.info(
        "All-time profiles across %d repos; role coverage also reports last %d days",
        len(all_time_by_repo), ROLE_ACTIVE_DAYS,
    )

    combined = _write_role_coverage(roles_by_repo, all_time_by_repo, recent_by_repo, repo_last_seen, now=now)
    if not combined.empty:
        save_dataframe(combined, org_data_dir / "role_coverage_all.csv")
        _write_repo_summaries(combined, org_data_dir)
        _write_role_networks(combined, all_time_by_repo, recent_by_repo, role_lookup, org_charts_dir)

    _write_team_tables(
        config, role_lookup, all_time_by_repo, all_time_org_profiles, global_last_seen, org_data_dir, now=now
    )
    logger.info("Role coverage complete")


if __name__ == "__main__":
    setup_logging()
    main()
