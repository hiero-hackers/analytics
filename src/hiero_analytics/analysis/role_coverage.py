"""Role coverage: a repo's permission-holders alongside their recent activity.

Joins governance-assigned roles (triage / committer / maintainer) for a repo to
its per-repo contributor activity profile, so anyone can see which role-holders
have recent activity, which are currently ``quiet`` in that repo, and each
holder's all-time contribution counts there.

It deliberately uses the role names, unlike the role-agnostic
``contributor_activity_profile`` module. It reports facts — recency and
contribution counts — rather than any score, grade, or ranking.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from hiero_analytics.domain.bots import is_bot_login
from hiero_analytics.domain.repos import bare_repo

# Seniority order, used to pick a holder's highest role across repos.
ROLE_RANK: dict[str, int] = {"triage": 1, "committer": 2, "maintainer": 3}

_COVERAGE_COLUMNS = [
    "user",
    "granted_role",
    "status",
    "last_active",
    "days_since_active",
    "prs_opened",
    "reviews_given",
    "merges_done",
    "issues_opened",
    "labels_applied",
    "total_actions",
    "prs_recent",
    "reviews_recent",
    "merges_recent",
    "issues_recent",
    "labels_recent",
]

# The five raw contribution counts, in display order.
_COUNT_FIELDS = ("prs_opened", "reviews_given", "merges_done", "issues_opened", "labels_applied")

_UNBADGED_COLUMNS = [
    "user",
    "reviews_given",
    "merges_done",
    "building",
    "reviewing",
    "organizing",
    "days_since_active",
]


def looks_like_bot(login: str) -> bool:
    """Whether a login is an automation account (delegates to the shared detector)."""
    return is_bot_login(login)


def _counts(profile: object | None) -> list[int]:
    """The five raw contribution counts for a profile row (zeros if absent)."""
    if profile is None:
        return [0, 0, 0, 0, 0]
    return [int(getattr(profile, field)) for field in _COUNT_FIELDS]


def build_repo_role_coverage(
    role_holders: dict[str, str],
    repo_profiles: pd.DataFrame,
    repo_last_seen: dict[str, object],
    *,
    now: datetime,
    active_within_days: int = 90,
    recent_profiles: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """One row per permission-holder: role, recency, and their contribution counts.

    Parameters
    ----------
    role_holders
        ``{user: role}`` for one repo (role in triage/committer/maintainer).
    repo_profiles
        That repo's **all-time** contributor profile table; the ``*_opened`` /
        ``*_given`` count columns are cumulative.
    repo_last_seen
        ``{account_lower: last_active}`` over **all time** for this repo, used for
        recency — so a quiet holder still shows how long since they were active.
    now
        Reference time for recency (injected for testability).
    active_within_days
        A holder with no activity in the repo within this many days — or none ever
        — is marked ``quiet``.
    recent_profiles
        Optional profile table scoped to the last ``active_within_days`` days. When
        given, its counts populate the ``*_recent`` columns alongside the all-time
        ones; when omitted those columns are zero.

    Returns:
    -------
    pd.DataFrame
        Quiet holders first (most actionable), then active holders ordered by
        ascending ``total_actions`` (least-contributing surface first). Counts are
        all-time; ``*_recent`` are the last ``active_within_days`` days;
        ``last_active`` / ``days_since_active`` are all-time.
    """
    by_login = {str(row.contributor).lower(): row for row in repo_profiles.itertuples()}
    by_login_recent = (
        {str(row.contributor).lower(): row for row in recent_profiles.itertuples()}
        if recent_profiles is not None and not recent_profiles.empty
        else {}
    )

    rows = []
    for user, role in sorted(role_holders.items()):
        login = user.lower()
        last_active = repo_last_seen.get(login)
        days = None if last_active is None else (now - last_active).days
        status = "active" if (days is not None and days <= active_within_days) else "quiet"

        prs, reviews, merges, issues, labels = _counts(by_login.get(login))
        r_prs, r_reviews, r_merges, r_issues, r_labels = _counts(by_login_recent.get(login))

        rows.append(
            {
                "user": user,
                "granted_role": role,
                "status": status,
                "last_active": last_active,
                "days_since_active": days,
                "prs_opened": prs,
                "reviews_given": reviews,
                "merges_done": merges,
                "issues_opened": issues,
                "labels_applied": labels,
                "total_actions": prs + reviews + merges + issues + labels,
                "prs_recent": r_prs,
                "reviews_recent": r_reviews,
                "merges_recent": r_merges,
                "issues_recent": r_issues,
                "labels_recent": r_labels,
            }
        )

    coverage = pd.DataFrame(rows, columns=_COVERAGE_COLUMNS)
    if coverage.empty:
        return coverage

    coverage["_active"] = (coverage["status"] == "active").astype(int)
    return (
        coverage.sort_values(["_active", "total_actions", "user"])
        .drop(columns="_active")
        .reset_index(drop=True)
    )


def find_unbadged_role_work(
    repo_profiles: pd.DataFrame,
    role_holders: dict[str, str],
    *,
    now: datetime,
    active_within_days: int = 90,
    min_reviews: int = 20,
) -> pd.DataFrame:
    """Active humans doing substantial review work without holding a role.

    Promotion candidates: not in ``role_holders``, not a bot, active within
    ``active_within_days``, and reviewing at least ``min_reviews`` times in the
    repo. Sorted by review volume.
    """
    holders = {user.lower() for user in role_holders}
    if repo_profiles.empty:
        return pd.DataFrame(columns=_UNBADGED_COLUMNS)

    rows = []
    for profile in repo_profiles.itertuples():
        login = str(profile.contributor)
        if login.lower() in holders or looks_like_bot(login):
            continue
        days = (now - profile.last_active).days
        if int(profile.reviews_given) >= min_reviews and days <= active_within_days:
            rows.append(
                {
                    "user": login,
                    "reviews_given": int(profile.reviews_given),
                    "merges_done": int(profile.merges_done),
                    "building": int(profile.building_and_fixing),
                    "reviewing": int(profile.reviewing_and_guiding),
                    "organizing": int(profile.organizing_and_answering),
                    "days_since_active": days,
                }
            )

    return (
        pd.DataFrame(rows, columns=_UNBADGED_COLUMNS)
        .sort_values("reviews_given", ascending=False)
        .reset_index(drop=True)
    )


_GLOBAL_QUIET_COLUMNS = [
    "user",
    "highest_role",
    "roles",
    "repos_held",
    "last_active",
    "days_since_active",
]


def find_globally_quiet_role_holders(
    role_lookup: dict[str, dict[str, str]],
    last_seen: dict[str, tuple],
    *,
    now: datetime,
    threshold_days: int = 90,
) -> pd.DataFrame:
    """Permission-holders who are quiet across *every* repo, not just one.

    Roles are granted per-repo, so a flat per-repo quiet list conflates someone
    inactive in one repo with heavy activity in another. This instead flags
    holders whose *global* last activity (anywhere in the org) is older than
    ``threshold_days`` — or who have no recorded activity at all — i.e. genuinely
    gone dark. ``last_seen`` is the all-time recency map
    ``{account_lower: (last_active, display_login)}``. Sorted most-stale first
    (never-active holders at the top); ``days_since_active`` is blank for those.
    """
    roles_by_user: dict[str, set[str]] = {}
    repos_by_user: dict[str, set[str]] = {}
    for repo, holders in role_lookup.items():
        for user, role in holders.items():
            roles_by_user.setdefault(user.lower(), set()).add(role)
            repos_by_user.setdefault(user.lower(), set()).add(repo)

    rows = []
    for user in sorted(roles_by_user):
        entry = last_seen.get(user)
        seen = None if entry is None else entry[0]
        display = user if entry is None else entry[1]
        days = None if seen is None else (now - seen).days
        if days is not None and days <= threshold_days:
            continue  # active somewhere recently — not globally quiet
        roles = roles_by_user[user]
        rows.append(
            {
                "user": display,
                "highest_role": max(roles, key=lambda role: ROLE_RANK.get(role, 0)),
                "roles": ", ".join(sorted(roles)),
                "repos_held": len(repos_by_user[user]),
                "last_active": seen,
                "days_since_active": days,
            }
        )

    quiet = pd.DataFrame(rows, columns=_GLOBAL_QUIET_COLUMNS)
    if quiet.empty:
        return quiet
    quiet["_sort"] = quiet["days_since_active"].fillna(10**9)
    return quiet.sort_values("_sort", ascending=False).drop(columns="_sort").reset_index(drop=True)


def annotate_repo_roles(
    activity: pd.DataFrame,
    role_lookup: dict[str, dict[str, str]],
    *,
    default: str = "general",
) -> pd.DataFrame:
    """Add a ``repo_role`` column: each ``(account, repo)`` row's role in that repo.

    Roles come from ``role_lookup`` (``{repo: {user: role}}``); an account with no
    governance role in a given repo is labelled ``default`` (a general contributor
    there). Repo keys are matched on the bare repo name. The column is inserted
    right after ``account`` so activity can be read in the context of the role
    that account actually holds in that repo.
    """
    out = activity.copy()
    if out.empty:
        out["repo_role"] = pd.Series(dtype="object")
        return out

    roles_by_bare = {bare_repo(repo): holders for repo, holders in role_lookup.items()}

    def _role(row: pd.Series) -> str:
        holders = roles_by_bare.get(bare_repo(str(row["repo"])), {})
        return holders.get(str(row["account"]).lower(), default)

    out.insert(2, "repo_role", out.apply(_role, axis=1))
    return out
