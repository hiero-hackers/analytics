"""Build per-contributor activity profiles for the informational dashboard.

Groups each contributor's GitHub activity into three neutral *families* of work
(named for the activity, not for any role or rank):

- ``building_and_fixing``   — authoring pull requests
- ``reviewing_and_guiding`` — reviewing and merging others' pull requests
- ``organizing_and_answering`` — engaging with the issue backlog

This is deliberately descriptive, not evaluative: the output is per-contributor
counts and shares, never a single score and never a cross-contributor ranking.

Data completeness note: ``organizing_and_answering`` reflects issues a
contributor opened plus labels they applied (when label events with an ``actor``
are supplied). Answering/triage *conversation* — comments, reproductions,
closing duplicates — is not captured yet; that needs issue-comment ingestion
before this family is fully representative.
"""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe
from hiero_analytics.data_sources.models import (
    ContributorActivityRecord,
    IssueTimelineEventRecord,
)
from hiero_analytics.domain.bots import is_bot_login
from hiero_analytics.domain.repos import bare_repo

# Which activity_type belongs to which family. Activity types absent here are
# ignored by the family rollups (but still counted in the raw event frame).
# ``labeled_issue`` is synthesized from label events (see build_contributor_profiles).
ACTIVITY_FAMILY: dict[str, str] = {
    "authored_pull_request": "building_and_fixing",
    "reviewed_pull_request": "reviewing_and_guiding",
    "merged_pull_request": "reviewing_and_guiding",
    "authored_issue": "organizing_and_answering",
    "labeled_issue": "organizing_and_answering",
}

_EVENT_COLUMNS = [
    "contributor",
    "activity_type",
    "family",
    "repo",
    "target_author",
    "review_state",
    "occurred_at",
    "target_number",
    "month",
]

_PROFILE_COLUMNS = [
    "contributor",
    "prs_opened",
    "issues_opened",
    "labels_applied",
    "reviews_given",
    "merges_done",
    "reviews_of_others",
    "reviews_for_newcomers",
    "changes_requested",
    "repos_touched",
    "months_active",
    "first_active",
    "last_active",
    "building_and_fixing",
    "reviewing_and_guiding",
    "organizing_and_answering",
    "building_share",
    "reviewing_share",
    "organizing_share",
]


def contributor_activity_to_dataframe(
    records: list[ContributorActivityRecord],
) -> pd.DataFrame:
    """Flatten activity records into one row per event, tagged with its family.

    Automation accounts (bots) are dropped — they aren't contributors.
    """
    return records_to_dataframe(
        records,
        lambda r: None
        if not r.actor or is_bot_login(r.actor)
        else {
            "contributor": r.actor,
            "activity_type": r.activity_type,
            "family": ACTIVITY_FAMILY.get(r.activity_type, "other"),
            "repo": r.repo,
            "target_author": r.target_author,
            "review_state": r.detail,
            "occurred_at": r.occurred_at,
            "target_number": r.target_number,
            "month": r.occurred_at.strftime("%Y-%m") if r.occurred_at else None,
        },
        _EVENT_COLUMNS,
    )


def label_events_to_dataframe(
    label_events: list[IssueTimelineEventRecord],
) -> pd.DataFrame:
    """Flatten label *applications* into the same per-event schema.

    Each ``labeled`` event is attributed to the contributor who applied it
    (``actor``) as a synthetic ``labeled_issue`` activity in the organizing family.
    ``unlabeled`` (removal) events are ignored, so removals don't inflate the
    organizing counts. Events without an actor (e.g. older datasets fetched before
    ``actor`` was captured) are dropped, so this is additive and safe on partial data.
    """
    return records_to_dataframe(
        label_events,
        lambda e: None
        if not e.actor or e.event_type != "labeled" or is_bot_login(e.actor)
        else {
            "contributor": e.actor,
            "activity_type": "labeled_issue",
            "family": "organizing_and_answering",
            "repo": e.repo,
            "target_author": None,
            "review_state": None,
            "occurred_at": e.occurred_at,
            "target_number": e.issue_number,
            "month": e.occurred_at.strftime("%Y-%m") if e.occurred_at else None,
        },
        _EVENT_COLUMNS,
    )


def combined_activity_events(
    records: list[ContributorActivityRecord],
    label_events: list[IssueTimelineEventRecord] | None = None,
) -> pd.DataFrame:
    """Concatenate contributor activity and actor-tagged label events into one frame."""
    frames = [
        frame
        for frame in (
            contributor_activity_to_dataframe(records),
            label_events_to_dataframe(label_events or []),
        )
        if not frame.empty
    ]
    if not frames:
        return pd.DataFrame(columns=_EVENT_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def _share(part: int, whole: int) -> int:
    """Integer percentage of ``part`` out of ``whole`` (0 when ``whole`` is 0)."""
    return round(part / whole * 100) if whole else 0


def build_contributor_profiles(
    records: list[ContributorActivityRecord],
    label_events: list[IssueTimelineEventRecord] | None = None,
    *,
    newcomer_max_prs: int = 2,
) -> pd.DataFrame:
    """Summarize each contributor's activity into the three work families.

    Parameters
    ----------
    records
        Contributor activity events (issue/PR authoring, reviews, merges).
    label_events
        Optional issue label add/remove events. Those carrying an ``actor`` are
        folded into the organizing family as ``labels_applied`` — the triage
        signal. Omit them (or pass events without actors) and organizing simply
        reflects issues opened, as before.
    newcomer_max_prs
        A reviewed PR counts as "for a newcomer" when its author has authored at
        most this many PRs across the whole window. A coarse, intentionally
        forgiving heuristic for a high-level mentorship signal — not a precise
        first-contribution detector.

    Returns:
    -------
    pd.DataFrame
        One row per contributor with high-level counts and family shares, ordered
        by ``last_active`` (most recently active first). This is a recency sort —
        useful for spotting who is currently engaged or has gone quiet — not a
        volume or performance ranking.
    """
    events = combined_activity_events(records, label_events)
    return _profiles_from_events(events, newcomer_max_prs=newcomer_max_prs)


def _profiles_from_events(events: pd.DataFrame, *, newcomer_max_prs: int) -> pd.DataFrame:
    """Per-contributor rollup over an already-built event frame.

    The shared engine behind both the org-wide and per-repo profile tables. When
    given a single repo's events, newcomer detection is naturally repo-scoped
    (authors with few PRs *in that repo*).
    """
    if events.empty:
        return pd.DataFrame(columns=_PROFILE_COLUMNS)

    pr_authors = events[events["activity_type"] == "authored_pull_request"]
    prs_per_author = pr_authors.groupby("contributor").size()
    newcomers = set(prs_per_author[prs_per_author <= newcomer_max_prs].index)

    rows = []
    for contributor, group in events.groupby("contributor"):
        types = group["activity_type"]
        reviews = group[types == "reviewed_pull_request"]

        prs_opened = int((types == "authored_pull_request").sum())
        issues_opened = int((types == "authored_issue").sum())
        labels_applied = int((types == "labeled_issue").sum())
        reviews_given = int(len(reviews))
        merges_done = int((types == "merged_pull_request").sum())

        building = prs_opened
        reviewing = reviews_given + merges_done
        organizing = issues_opened + labels_applied
        total = building + reviewing + organizing

        rows.append(
            {
                "contributor": contributor,
                "prs_opened": prs_opened,
                "issues_opened": issues_opened,
                "labels_applied": labels_applied,
                "reviews_given": reviews_given,
                "merges_done": merges_done,
                "reviews_of_others": int((reviews["target_author"] != contributor).sum()),
                "reviews_for_newcomers": int(reviews["target_author"].isin(newcomers).sum()),
                "changes_requested": int((reviews["review_state"] == "CHANGES_REQUESTED").sum()),
                "repos_touched": int(group["repo"].nunique()),
                "months_active": int(group["month"].nunique()),
                "first_active": group["occurred_at"].min(),
                "last_active": group["occurred_at"].max(),
                "building_and_fixing": building,
                "reviewing_and_guiding": reviewing,
                "organizing_and_answering": organizing,
                "building_share": _share(building, total),
                "reviewing_share": _share(reviewing, total),
                "organizing_share": _share(organizing, total),
            }
        )

    return (
        pd.DataFrame(rows, columns=_PROFILE_COLUMNS)
        .sort_values("last_active", ascending=False)
        .reset_index(drop=True)
    )


def build_contributor_profiles_by_repo(
    records: list[ContributorActivityRecord],
    label_events: list[IssueTimelineEventRecord] | None = None,
    *,
    newcomer_max_prs: int = 2,
) -> dict[str, pd.DataFrame]:
    """Build a contributor-profile table per repository.

    Returns ``{repo: profiles_df}`` (same schema as :func:`build_contributor_profiles`,
    scoped to each repo), so you can see how a person shows up in one repo versus
    another — someone may build in one and review in another. Repos are keyed in
    sorted order.
    """
    events = combined_activity_events(records, label_events)
    return {
        repo: _profiles_from_events(group, newcomer_max_prs=newcomer_max_prs)
        for repo, group in events.groupby("repo")
    }


def build_active_membership(
    by_repo: dict[str, pd.DataFrame],
    recent_by_repo: dict[str, pd.DataFrame],
    *,
    exclude: frozenset[str] = frozenset(),
) -> pd.DataFrame:
    """Long ``[repo, user, active]`` table of every contributor in each repo.

    ``by_repo`` is the all-time per-repo profiles; ``recent_by_repo`` the same scoped
    to a recent window — a contributor is ``active`` when they appear in the recent
    set for that repo. Repo names are the bare name; logins are lowercased.
    ``exclude`` drops logins (e.g. role-holders, for a "general contributors" view).
    Feeds the co-membership network builder.
    """
    rows = []
    for repo_full, profiles in by_repo.items():
        if profiles.empty:
            continue
        recent = recent_by_repo.get(repo_full)
        recent_users = (
            set(recent["contributor"].astype(str).str.lower())
            if recent is not None and not recent.empty else set()
        )
        for contributor in profiles["contributor"]:
            login = str(contributor).lower()
            if login in exclude:
                continue
            rows.append({"repo": bare_repo(repo_full), "user": login, "active": login in recent_users})
    return pd.DataFrame(rows, columns=["repo", "user", "active"])


def build_account_activity_by_repo(
    accounts: set[str],
    by_repo: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Long table of ``(repo, account, ...)`` rows for the given accounts.

    For each account, one row per repo it is active in (its per-repo profile), so
    you can see *which* repos an account works in and *what* it does in each.
    Accounts are matched case-insensitively. Grouped by account, most-active repo
    first. ``by_repo`` is the output of :func:`build_contributor_profiles_by_repo`.
    """
    columns = ["repo", "account", *_PROFILE_COLUMNS[1:]]
    wanted = {account.lower() for account in accounts}

    frames = []
    for repo, profiles in by_repo.items():
        if profiles.empty:
            continue
        subset = profiles[profiles["contributor"].str.lower().isin(wanted)]
        if subset.empty:
            continue
        labelled = subset.copy()
        labelled.insert(0, "repo", repo)
        frames.append(labelled)

    if not frames:
        return pd.DataFrame(columns=columns)

    out = pd.concat(frames, ignore_index=True).rename(columns={"contributor": "account"})
    out["_total"] = (
        out["building_and_fixing"] + out["reviewing_and_guiding"] + out["organizing_and_answering"]
    )
    return (
        out.sort_values(["account", "_total"], ascending=[True, False])
        .drop(columns="_total")
        .reset_index(drop=True)
    )


def latest_activity_by_account(
    records: list[ContributorActivityRecord],
    label_events: list[IssueTimelineEventRecord] | None = None,
) -> dict[str, tuple]:
    """All-time recency per account: ``{account_lower: (last_active, display_login)}``.

    Used to report how long a quiet/dark holder has been gone, independent of any
    activity window applied to the contribution counts.
    """
    out: dict[str, tuple] = {}
    pairs = [(r.actor, r.occurred_at) for r in records]
    pairs += [(e.actor, e.occurred_at) for e in (label_events or [])]
    for actor, when in pairs:
        if not actor or when is None:
            continue
        key = actor.lower()
        current = out.get(key)
        if current is None or when > current[0]:
            out[key] = (when, actor)
    return out


def latest_activity_by_repo_account(
    records: list[ContributorActivityRecord],
    label_events: list[IssueTimelineEventRecord] | None = None,
) -> dict[tuple[str, str], object]:
    """All-time recency per repo+account: ``{(repo, account_lower): last_active}``."""
    out: dict[tuple[str, str], object] = {}
    triples = [(r.repo, r.actor, r.occurred_at) for r in records]
    triples += [(e.repo, e.actor, e.occurred_at) for e in (label_events or [])]
    for repo, actor, when in triples:
        if not actor or when is None:
            continue
        key = (repo, actor.lower())
        current = out.get(key)
        if current is None or when > current:
            out[key] = when
    return out
