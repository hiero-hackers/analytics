"""Per-repository rollups derived from the combined ``role_coverage_all`` table.

These summarize a repo's permission-holders into one row per repo — an activity
overview, the maintainer-coverage view, and the review-load concentration — as
opposed to ``role_coverage``, which works per ``(repo, holder)``.
"""

from __future__ import annotations

import pandas as pd

# Last-window contribution-count columns, as emitted by build_repo_role_coverage.
_RECENT_FIELDS = ("prs_recent", "reviews_recent", "merges_recent", "issues_recent", "labels_recent")
# Roles that can merge pull requests (write access). Triage cannot merge.
_CAN_MERGE = ("maintainer", "committer")

_OVERVIEW_COLUMNS = [
    "repo",
    "maintainers",
    "committers",
    "triage",
    "active_recent",
    "maintainer_actions_recent",
    "committer_actions_recent",
    "triage_actions_recent",
    "actions_recent",
    "actions_all_time",
    "last_active",
]

_UNDERSTAFFED_COLUMNS = ["repo", "maintainers", "active_maintainers", "committers", "triage"]

_LOAD_SHARE_COLUMNS = [
    "repo",
    "mergers",
    "load_recent",
    "top_carrier",
    "top_role",
    "top_share",
    "second_share",
    "rest_share",
    "top2_share",
]


def build_repo_activity_overview(coverage_all: pd.DataFrame) -> pd.DataFrame:
    """Per-repo rollup of permission-holder activity, broken down by role.

    Takes the combined ``role_coverage_all`` table (one row per ``(repo, holder)``,
    with a ``repo`` column, ``granted_role``, ``status``, the all-time
    ``total_actions`` and the ``*_recent`` counts). Returns one row per repo: holder
    counts by role, how many are active in the recent window, recent action totals
    overall and per role group, the all-time action total, and the latest activity.
    "Actions" is the five contribution counts summed. Sorted by recent actions
    (most active repo first).
    """
    if coverage_all.empty:
        return pd.DataFrame(columns=_OVERVIEW_COLUMNS)

    df = coverage_all.copy()
    df["_recent"] = df[list(_RECENT_FIELDS)].sum(axis=1)

    rows = []
    for repo, group in df.groupby("repo"):
        role = group["granted_role"]
        rows.append(
            {
                "repo": repo,
                "maintainers": int((role == "maintainer").sum()),
                "committers": int((role == "committer").sum()),
                "triage": int((role == "triage").sum()),
                "active_recent": int((group["status"] == "active").sum()),
                "maintainer_actions_recent": int(group.loc[role == "maintainer", "_recent"].sum()),
                "committer_actions_recent": int(group.loc[role == "committer", "_recent"].sum()),
                "triage_actions_recent": int(group.loc[role == "triage", "_recent"].sum()),
                "actions_recent": int(group["_recent"].sum()),
                "actions_all_time": int(group["total_actions"].sum()),
                # Holders with no activity carry NaN/NaT; coerce so max ignores them.
                "last_active": pd.to_datetime(group["last_active"], errors="coerce", utc=True).max(),
            }
        )

    overview = pd.DataFrame(rows, columns=_OVERVIEW_COLUMNS)
    return overview.sort_values("actions_recent", ascending=False).reset_index(drop=True)


def find_understaffed_repos(coverage_all: pd.DataFrame, *, max_active_maintainers: int = 1) -> pd.DataFrame:
    """Repos with at most ``max_active_maintainers`` maintainers active in the window.

    From the combined ``role_coverage_all`` table, counts maintainers per repo and how
    many are active in the recent window, plus the committer/triage pools with access.
    Filters by *active* maintainers, so it surfaces both zero-maintainer repos and repos
    whose maintainers have all gone quiet. Fewest active (then fewest total) first.
    """
    if coverage_all.empty or "granted_role" not in coverage_all:
        return pd.DataFrame(columns=_UNDERSTAFFED_COLUMNS)

    df = coverage_all.copy()
    df["repo"] = df["repo"].astype(str).str.split("/").str[-1]
    df["user"] = df["user"].astype(str).str.lower()

    rows = []
    for repo, group in df.groupby("repo"):
        role = group["granted_role"]
        maint = group[role == "maintainer"]
        rows.append(
            {
                "repo": repo,
                "maintainers": int(maint["user"].nunique()),
                "active_maintainers": int(maint[maint["status"] == "active"]["user"].nunique()),
                "committers": int(group[role == "committer"]["user"].nunique()),
                "triage": int(group[role == "triage"]["user"].nunique()),
            }
        )

    out = pd.DataFrame(rows, columns=_UNDERSTAFFED_COLUMNS)
    out = out[out["active_maintainers"] <= max_active_maintainers]
    return out.sort_values(
        ["active_maintainers", "maintainers", "committers"], ascending=[True, True, False]
    ).reset_index(drop=True)


def build_review_load_share(coverage_all: pd.DataFrame, *, min_actions: int = 20) -> pd.DataFrame:
    """Per-repo concentration of review+merge load (recent window).

    The load-carriers are everyone who can merge — committers *and* maintainers (a
    committer has write access, so they review and merge too); triage is excluded
    (it cannot merge). For each repo, sums each person's recent reviews + merges and
    reports what share the busiest one does — i.e. how concentrated the work is, and
    whether that person is a committer or maintainer. Splits the load into busiest /
    second / everyone-else shares for a stacked-bar view. Only repos with at least
    ``min_actions`` total recent load are kept. Highest busiest-person share first.
    """
    if coverage_all.empty or "granted_role" not in coverage_all:
        return pd.DataFrame(columns=_LOAD_SHARE_COLUMNS)

    df = coverage_all.copy()
    df["repo"] = df["repo"].astype(str).str.split("/").str[-1]
    pool = df[df["granted_role"].isin(_CAN_MERGE)].copy()
    pool["load"] = pool["reviews_recent"] + pool["merges_recent"]

    rows = []
    for repo, group in pool.groupby("repo"):
        total = int(group["load"].sum())
        if total < min_actions:
            continue
        ordered = group[group["load"] > 0].sort_values("load", ascending=False)
        if ordered.empty:
            continue
        loads = ordered["load"].tolist()
        top = int(loads[0])
        second = int(loads[1]) if len(loads) > 1 else 0
        rest = max(total - top - second, 0)
        rows.append(
            {
                "repo": repo,
                "mergers": int(len(ordered)),  # people who actually reviewed/merged
                "load_recent": total,
                "top_carrier": ordered["user"].iloc[0],
                "top_role": ordered["granted_role"].iloc[0],
                "top_share": round(top / total, 4),
                "second_share": round(second / total, 4),
                "rest_share": round(rest / total, 4),
                "top2_share": round((top + second) / total, 4),
            }
        )

    out = pd.DataFrame(rows, columns=_LOAD_SHARE_COLUMNS)
    if out.empty:
        return out
    return out.sort_values("top_share", ascending=False).reset_index(drop=True)
