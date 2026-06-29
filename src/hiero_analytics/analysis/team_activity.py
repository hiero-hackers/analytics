"""Team-level activity rollups from governance team membership + activity profiles.

A team is marked **quiet** when none of its members have recent activity anywhere
within the window; ``build_team_activity_by_repo`` shows which repos each team is
active in. Descriptive — it aggregates member activity and never ranks teams.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

# Raw contribution columns carried from the contributor profiles.
_CONTRIB_COLS = ("prs_opened", "reviews_given", "merges_done", "issues_opened", "labels_applied")

_SUMMARY_COLUMNS = [
    "team",
    "members",
    "active_members",
    "status",
    "last_active",
    "days_since_active",
    *_CONTRIB_COLS,
]

_BY_REPO_COLUMNS = [
    "team",
    "repo",
    "members_active",
    "last_active",
    *_CONTRIB_COLS,
]


def _aggregate(members, by_login, last_seen, *, now, active_within_days):
    """Window counts from ``by_login`` + all-time recency from ``last_seen`` per member."""
    totals = dict.fromkeys(_CONTRIB_COLS, 0)
    last_active = None
    active_members = 0
    for member in members:
        profile = by_login.get(member)
        if profile is not None:
            for column in _CONTRIB_COLS:
                totals[column] += int(getattr(profile, column))
        entry = last_seen.get(member)
        if entry is None:
            continue
        when = entry[0]
        if last_active is None or when > last_active:
            last_active = when
        if (now - when).days <= active_within_days:
            active_members += 1
    return totals, last_active, active_members


def build_team_activity_summary(
    team_members: dict[str, set[str]],
    org_profiles: pd.DataFrame,
    last_seen: dict[str, tuple],
    *,
    now: datetime,
    dark_after_days: int = 90,
) -> pd.DataFrame:
    """One row per team: size, recent activity, and active/quiet status.

    A team is ``quiet`` when none of its members has recent activity anywhere within
    ``dark_after_days``. Contribution counts come from ``org_profiles`` (all-time);
    recency comes from ``last_seen`` (``{account_lower: (last_active, login)}``,
    all-time). Teams with no recent activity sort first.
    """
    by_login = (
        {str(row.contributor).lower(): row for row in org_profiles.itertuples()}
        if not org_profiles.empty
        else {}
    )

    rows = []
    for team, members in sorted(team_members.items()):
        totals, last_active, active_members = _aggregate(
            members, by_login, last_seen, now=now, active_within_days=dark_after_days
        )
        rows.append(
            {
                "team": team,
                "members": len(members),
                "active_members": active_members,
                "status": "active" if active_members > 0 else "quiet",
                "last_active": last_active,
                "days_since_active": None if last_active is None else (now - last_active).days,
                **totals,
            }
        )

    summary = pd.DataFrame(rows, columns=_SUMMARY_COLUMNS)
    if summary.empty:
        return summary

    summary["_active"] = (summary["status"] == "active").astype(int)
    summary["_sort"] = summary["days_since_active"].fillna(10**9)
    return (
        summary.sort_values(["_active", "_sort"], ascending=[True, False])
        .drop(columns=["_active", "_sort"])
        .reset_index(drop=True)
    )


def build_team_activity_by_repo(
    team_members: dict[str, set[str]],
    by_repo: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """One row per ``(team, repo)`` the team is active in, with aggregated counts.

    Shows which repos each team actually works in (members with activity there),
    grouped by team, most active repo first. Requires ``now`` only implicitly via
    ``last_active`` (the latest member activity in that repo).
    """
    repo_maps = {
        repo: ({str(row.contributor).lower(): row for row in profiles.itertuples()} if not profiles.empty else {})
        for repo, profiles in by_repo.items()
    }

    rows = []
    for team, members in sorted(team_members.items()):
        for repo, login_map in repo_maps.items():
            totals = dict.fromkeys(_CONTRIB_COLS, 0)
            last_active = None
            members_active = 0
            for member in members:
                profile = login_map.get(member)
                if profile is None:
                    continue
                members_active += 1
                for column in _CONTRIB_COLS:
                    totals[column] += int(getattr(profile, column))
                when = profile.last_active
                if last_active is None or when > last_active:
                    last_active = when
            if members_active == 0:
                continue
            rows.append(
                {"team": team, "repo": repo, "members_active": members_active, "last_active": last_active, **totals}
            )

    table = pd.DataFrame(rows, columns=_BY_REPO_COLUMNS)
    if table.empty:
        return table

    table["_total"] = table[list(_CONTRIB_COLS)].sum(axis=1)
    return (
        table.sort_values(["team", "_total"], ascending=[True, False])
        .drop(columns="_total")
        .reset_index(drop=True)
    )
