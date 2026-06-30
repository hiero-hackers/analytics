"""Maintainer organisation-diversity analysis.

Reads the curated ``data/affiliations.yaml`` mapping (login -> organisation) and,
given the current maintainer set, classifies each maintainer and builds the
distribution + concentration metrics for the organisation-diversity chart.

Independents (people with an identity but no corporate employer) count *toward*
diversity: in the concentration measure each is its own singleton entity, so a
large independent tail lowers the HHI rather than inflating one bucket.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

import pandas as pd
import yaml

from hiero_analytics.config.analysis import HEATMAP_TOP_ROWS
from hiero_analytics.config.paths import SRC
from hiero_analytics.domain.repos import bare_repo

_HEATMAP_META = {"contributor name", "role", "activity score"}

logger = logging.getLogger(__name__)

AFFILIATIONS_PATH = SRC / "data" / "affiliations.yaml"
INDEPENDENT = "Independent"
UNKNOWN_LABEL = "Unknown"
OTHER_LABEL = "Other orgs"
_UNKNOWN_VALUES = {"", "?", "unknown", "none"}

DISTRIBUTION_COLUMNS = ["organisation", "maintainers"]
CLASSIFIED_COLUMNS = ["login", "organisation", "status"]
REPO_DIVERSITY_COLUMNS = [
    "repo", "maintainers", "distinct_orgs", "top_org", "top_org_pct",
    "independent", "unknown", "organisations",
]
TEAM_DIVERSITY_COLUMNS = [
    "team", "members", "resolved", "distinct_orgs", "top_org", "top_org_pct",
    "hhi", "unknown", "single_employer", "organisations",
]


def load_affiliations(path=AFFILIATIONS_PATH) -> dict[str, str]:
    """Load the curated login -> organisation map, keyed by lowercased login.

    Unknown markers ('?', blank) are dropped, so a missing key and an explicit
    '?' are treated identically downstream.
    """
    if not path.exists():
        logger.warning("Affiliations file not found: %s", path)
        return {}

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    mapping: dict[str, str] = {}
    for login, org in raw.items():
        value = str(org).strip()
        if value.lower() in _UNKNOWN_VALUES:
            continue
        mapping[str(login).strip().lower()] = value
    return mapping


def load_manual_logins(path=AFFILIATIONS_PATH) -> set[str]:
    """Lowercased logins whose value was hand-set (YAML comment marked manual/MANUAL)."""
    if not path.exists():
        return set()
    manual: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#") or ":" not in raw:
            continue
        body, sep, comment = raw.partition("#")
        if not sep:
            continue
        # 'manual' anywhere in the comment — at the start, appended after the role
        # tag ('# maintainer # manual'), or the generator's '… · MANUAL — …'.
        if re.search(r"\bmanual\b", comment, re.IGNORECASE):
            manual.add(body.split(":", 1)[0].strip().lower())
    return manual


def classify_maintainers(maintainers: set[str], affiliations: dict[str, str]) -> pd.DataFrame:
    """One row per maintainer: login, organisation, status.

    status is ``affiliated`` (named employer), ``independent`` (solo / no
    employer), or ``unknown`` (no entry in the affiliations map).
    """
    rows: list[dict[str, object]] = []
    for login in sorted(maintainers):
        org = affiliations.get(login.lower())
        if not org:
            rows.append({"login": login, "organisation": None, "status": "unknown"})
        elif org == INDEPENDENT:
            rows.append({"login": login, "organisation": INDEPENDENT, "status": "independent"})
        else:
            rows.append({"login": login, "organisation": org, "status": "affiliated"})
    return pd.DataFrame(rows, columns=CLASSIFIED_COLUMNS)


def build_affiliation_distribution(classified: pd.DataFrame) -> pd.DataFrame:
    """Chart frame (organisation, maintainers) over the *known* set.

    Named employers each get a row counting their maintainers; all independents
    fold into a single ``Independent`` row (the chart shows the size of the
    diverse tail). Unknowns are excluded. Sorted by count, descending.
    """
    if classified.empty:
        return pd.DataFrame(columns=DISTRIBUTION_COLUMNS)

    known = classified[classified["status"] != "unknown"]
    if known.empty:
        return pd.DataFrame(columns=DISTRIBUTION_COLUMNS)

    counts = (
        known.groupby("organisation")["login"]
        .nunique()
        .reset_index(name="maintainers")
        .sort_values("maintainers", ascending=False, kind="stable")
        .reset_index(drop=True)
    )
    return counts[DISTRIBUTION_COLUMNS]


def summarize_affiliation(classified: pd.DataFrame) -> dict[str, object]:
    """Coverage counts plus concentration (HHI) over the known set.

    HHI treats each independent as its own singleton entity, so independents
    push concentration down. Returns a dict of plain numbers for logging /
    headline metrics.
    """
    total = len(classified)
    by_status = classified["status"].value_counts().to_dict() if total else {}
    affiliated = int(by_status.get("affiliated", 0))
    independent = int(by_status.get("independent", 0))
    unknown = int(by_status.get("unknown", 0))

    # Concentration entities: employer name for the affiliated, a unique key per
    # independent so the diverse tail lowers the HHI instead of clustering.
    known = classified[classified["status"] != "unknown"]
    entities = [
        org if status == "affiliated" else f"independent:{login}"
        for login, org, status in zip(
            known["login"], known["organisation"], known["status"], strict=True
        )
    ]
    known_total = len(entities)
    employer_counts = (
        known[known["status"] == "affiliated"]["organisation"].value_counts()
    )
    entity_counts = Counter(entities)
    hhi = (
        round(10000 * sum((n / known_total) ** 2 for n in entity_counts.values()))
        if known_total
        else 0
    )
    top_org = employer_counts.index[0] if not employer_counts.empty else None
    top_share = (
        round(100 * int(employer_counts.iloc[0]) / known_total) if known_total and top_org else 0
    )

    return {
        "maintainers": total,
        "affiliated": affiliated,
        "independent": independent,
        "unknown": unknown,
        "distinct_orgs": int(employer_counts.size),
        "hhi": hhi,
        "top_org": top_org,
        "top_share_pct": top_share,
    }


def top_n_with_other(distribution: pd.DataFrame, label_col: str, value_col: str, *, top_n: int = 6) -> pd.DataFrame:
    """Fold a distribution to its top-N rows plus a single ``Other (k)`` row.

    Keeps a donut readable: the largest ``top_n`` slices stay, the rest collapse
    into one. Returns the frame unchanged when it already has ``top_n`` rows or fewer.
    """
    if distribution.empty:
        return distribution
    ordered = distribution.sort_values(value_col, ascending=False).reset_index(drop=True)
    if len(ordered) <= top_n:
        return ordered
    head = ordered.head(top_n)
    tail = ordered.iloc[top_n:]
    other = pd.DataFrame([{label_col: f"Other ({len(tail)})", value_col: int(tail[value_col].sum())}])
    return pd.concat([head, other], ignore_index=True)


def build_org_activity_heatmap(contributor_heatmap, affiliations, *, include_unknown=False):
    """Aggregate a per-contributor activity heatmap into a per-organisation one.

    Takes the contributor-by-month matrix from
    ``contributor_heatmap.build_activity_heatmap_dataframe`` (which already weights,
    windows and excludes bots), maps each contributor by login to their employer,
    and sums the weighted monthly scores. Independent is kept as its own row;
    unmapped contributors are dropped unless ``include_unknown``. Busiest orgs first.
    """
    month_cols = [c for c in contributor_heatmap.columns if c not in _HEATMAP_META]
    empty = pd.DataFrame(columns=["organisation", "activity score", *month_cols])
    if contributor_heatmap.empty:
        return empty

    df = contributor_heatmap.copy()
    df["organisation"] = df["contributor name"].str.lower().map(affiliations)
    if include_unknown:
        df["organisation"] = df["organisation"].fillna(UNKNOWN_LABEL)
    else:
        df = df[df["organisation"].notna()]
    if df.empty:
        return empty

    return (
        df.groupby("organisation")[["activity score", *month_cols]]
        .sum()
        .reset_index()
        .sort_values("activity score", ascending=False)
        .reset_index(drop=True)
    )


def org_heatmap_chart_data(org_heatmap, *, top_rows: int = HEATMAP_TOP_ROWS):
    """Top-N orgs as ``(values, row_labels, col_labels)`` for ``plot_heatmap``, or None."""
    if org_heatmap.empty:
        return None
    month_cols = [c for c in org_heatmap.columns if c not in {"organisation", "activity score"}]
    chart = org_heatmap.head(top_rows)
    if chart.empty:
        return None
    return chart[month_cols].to_numpy(dtype=float), chart["organisation"].tolist(), month_cols


def filter_active_logins(logins, last_active, cutoff):
    """Subset of ``logins`` whose most recent activity is at or after ``cutoff``.

    ``last_active`` is ``{login_lower: (datetime, display_login)}`` as produced by
    ``latest_activity_by_account``. A login with no recorded activity is treated
    as inactive. Used to measure diversity over the maintainers who actually hold
    the keys day-to-day, not just the nominal roster.
    """
    active = set()
    for login in logins:
        entry = last_active.get(login.lower())
        if entry and entry[0] >= cutoff:
            active.add(login)
    return active


def _repo_maintainers(role_lookup: dict[str, dict[str, str]], role: str) -> dict[str, set[str]]:
    """Map bare repo name -> set of logins holding ``role`` there (non-empty repos only)."""
    repos: dict[str, set[str]] = {}
    for repo, holders in role_lookup.items():
        logins = {login for login, held in holders.items() if held == role}
        if logins:
            repos[bare_repo(repo)] = logins
    return repos


def build_repo_affiliation_diversity(
    role_lookup: dict[str, dict[str, str]],
    affiliations: dict[str, str],
    *,
    role: str = "maintainer",
) -> pd.DataFrame:
    """Per-repo organisational diversity of a repo's ``role``-holders.

    One row per repo: how many hold the role, how many distinct employers they
    span, the largest employer and its share, and the independent / unknown
    counts. A repo where every holder shares one employer (``distinct_orgs`` 1)
    is an organisational bus-factor even when the org-wide picture looks diverse.
    Sorted single-employer-first (then most holders), so capture risk surfaces.
    """
    rows: list[dict[str, object]] = []
    for repo, logins in _repo_maintainers(role_lookup, role).items():
        classified = classify_maintainers(logins, affiliations)
        employer_counts = classified[classified["status"] == "affiliated"]["organisation"].value_counts()
        independent = int((classified["status"] == "independent").sum())
        unknown = int((classified["status"] == "unknown").sum())
        top_org = employer_counts.index[0] if not employer_counts.empty else None
        top_pct = round(100 * int(employer_counts.iloc[0]) / len(logins)) if not employer_counts.empty else 0
        rows.append({
            "repo": repo,
            "maintainers": len(logins),
            "distinct_orgs": int(employer_counts.size),
            "top_org": top_org,
            "top_org_pct": top_pct,
            "independent": independent,
            "unknown": unknown,
            "organisations": ", ".join(employer_counts.index.tolist()),
        })

    df = pd.DataFrame(rows, columns=REPO_DIVERSITY_COLUMNS)
    if df.empty:
        return df
    return df.sort_values(["distinct_orgs", "maintainers"], ascending=[True, False]).reset_index(drop=True)


def build_repo_org_composition(
    role_lookup: dict[str, dict[str, str]],
    affiliations: dict[str, str],
    *,
    role: str = "maintainer",
    top_n: int = 6,
) -> tuple[pd.DataFrame, list[str]]:
    """Per-repo maintainer counts split by employer, for a stacked composition chart.

    The ``top_n`` employers (by total seats across repos) get their own column;
    the rest pool into ``Other orgs``. Independents and unknowns get their own
    columns so each bar's length is the repo's full maintainer count. Returns
    ``(frame, segment_columns)`` with segments ordered for stacking.
    """
    repos = _repo_maintainers(role_lookup, role)
    if not repos:
        return pd.DataFrame(columns=["repo"]), []

    def segment(login: str) -> str:
        org = affiliations.get(login.lower())
        if not org:
            return UNKNOWN_LABEL
        return org  # INDEPENDENT passes through as its own segment

    seat_totals: Counter[str] = Counter()
    for logins in repos.values():
        for login in logins:
            seat_totals[segment(login)] += 1

    named = [
        org for org, _ in seat_totals.most_common()
        if org not in {INDEPENDENT, UNKNOWN_LABEL}
    ]
    kept = named[:top_n]
    has_other = len(named) > top_n
    # Stacking order: big employers first, then Other, Independent, and Unknown last.
    segments = [*kept]
    if has_other:
        segments.append(OTHER_LABEL)
    if seat_totals.get(INDEPENDENT):
        segments.append(INDEPENDENT)
    if seat_totals.get(UNKNOWN_LABEL):
        segments.append(UNKNOWN_LABEL)

    kept_set = set(kept)
    rows: list[dict[str, object]] = []
    for repo, logins in repos.items():
        counts = dict.fromkeys(segments, 0)
        for login in logins:
            seg = segment(login)
            if seg not in kept_set and seg not in {INDEPENDENT, UNKNOWN_LABEL}:
                seg = OTHER_LABEL
            counts[seg] += 1
        rows.append({"repo": repo, **counts})

    frame = pd.DataFrame(rows, columns=["repo", *segments])
    return _sort_by_concentration(frame, segments, kept), segments


def _sort_by_concentration(frame: pd.DataFrame, segments: list[str], employer_cols: list[str]) -> pd.DataFrame:
    """Order a composition frame most-concentrated first (largest single employer's share).

    Ties on concentration are broken by the *dominant* employer's position in the
    segment (legend / colour) order, so bars with equal concentration are grouped by
    colour — all the Hashgraph-led bars together, then LimeChain, and so on — which
    makes the wall of bars far easier to scan. Total seats is the final tiebreak.
    """
    if frame.empty or not employer_cols:
        return frame
    totals = frame[segments].sum(axis=1)
    employers = frame[employer_cols]
    top_share = employers.max(axis=1) / totals.where(totals != 0, 1)
    # Rank each bar by which employer leads it, using the segment order (= colour /
    # legend order). idxmax keeps the first column on ties, so an all-zero-employer
    # bar (e.g. fully independent/unknown) consistently ranks under the first colour.
    colour_rank = {col: i for i, col in enumerate(employer_cols)}
    top_colour = employers.idxmax(axis=1).map(colour_rank)
    return (
        frame.assign(_conc=top_share, _colour=top_colour, _total=totals)
        .sort_values(["_conc", "_colour", "_total"], ascending=[False, True, False])
        .drop(columns=["_conc", "_colour", "_total"])
        .reset_index(drop=True)
    )


def build_team_affiliation_diversity(
    team_membership: dict[str, set[str]],
    affiliations: dict[str, str],
    *,
    min_members: int = 2,
) -> pd.DataFrame:
    """Per-team organisational concentration, for the governance-capture view.

    For each governance team, how many members resolve to an employer, how many
    distinct employers, the largest and its share, and the concentration (HHI).
    ``single_employer`` flags a team where every *resolved* member shares one
    employer (capture / bus-factor risk) — a security concern for admin, release,
    and maintainer teams. ``unknown`` shows how much of the team is unmapped, so
    a flag on a mostly-unknown team can be read with appropriate caution. Teams
    smaller than ``min_members`` are skipped. Most concentrated first.
    """
    rows: list[dict[str, object]] = []
    for team, members in team_membership.items():
        if len(members) < min_members:
            continue
        classified = classify_maintainers(set(members), affiliations)
        summary = summarize_affiliation(classified)
        resolved = int(summary["affiliated"]) + int(summary["independent"])
        # Full org breakdown, e.g. "Hashgraph 5, LimeChain 2, Independent 1".
        employer_counts = classified[classified["status"] == "affiliated"]["organisation"].value_counts()
        mix = [f"{org} {int(n)}" for org, n in employer_counts.items()]
        if summary["independent"]:
            mix.append(f"Independent {int(summary['independent'])}")
        rows.append({
            "team": team,
            "members": int(summary["maintainers"]),
            "resolved": resolved,
            "distinct_orgs": int(summary["distinct_orgs"]),
            "top_org": summary["top_org"],
            "top_org_pct": int(summary["top_share_pct"]),
            "hhi": int(summary["hhi"]),
            "unknown": int(summary["unknown"]),
            # One employer holds every resolved seat (no independents) -> capture risk.
            "single_employer": summary["distinct_orgs"] == 1 and resolved >= 2 and summary["independent"] == 0,
            "organisations": ", ".join(mix),
        })

    df = pd.DataFrame(rows, columns=TEAM_DIVERSITY_COLUMNS)
    if df.empty:
        return df
    return df.sort_values(["hhi", "members"], ascending=[False, False]).reset_index(drop=True)


def build_single_employer_team_counts(team_diversity: pd.DataFrame) -> pd.DataFrame:
    """Count single-employer teams by the org that controls them (chart frame)."""
    if team_diversity.empty:
        return pd.DataFrame(columns=["organisation", "teams"])
    captured = team_diversity[team_diversity["single_employer"]]
    if captured.empty:
        return pd.DataFrame(columns=["organisation", "teams"])
    return (
        captured.groupby("top_org")["team"]
        .nunique()
        .reset_index(name="teams")
        .rename(columns={"top_org": "organisation"})
        .sort_values("teams", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def build_single_employer_repo_counts(repo_diversity: pd.DataFrame) -> pd.DataFrame:
    """Count single-employer repositories by the org that holds them (chart frame).

    A repo is single-employer when every *resolved* maintainer shares one employer
    (no independents) and there are at least two of them — the repo-level analogue
    of a captured team.
    """
    cols = ["organisation", "repos"]
    if repo_diversity.empty:
        return pd.DataFrame(columns=cols)
    resolved = repo_diversity["maintainers"] - repo_diversity["unknown"]
    single = (
        (repo_diversity["distinct_orgs"] == 1)
        & (repo_diversity["independent"] == 0)
        & (resolved >= 2)
    )
    captured = repo_diversity[single]
    if captured.empty:
        return pd.DataFrame(columns=cols)
    return (
        captured.groupby("top_org")["repo"]
        .nunique()
        .reset_index(name="repos")
        .rename(columns={"top_org": "organisation"})
        .sort_values("repos", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def build_team_org_composition(
    team_membership: dict[str, set[str]],
    affiliations: dict[str, str],
    *,
    top_n: int = 6,
    min_resolved: int = 4,
) -> tuple[pd.DataFrame, list[str]]:
    """Per-team member counts split by employer, for a stacked composition chart.

    Mirrors :func:`build_repo_org_composition` but over governance teams, and only
    for teams with at least ``min_resolved`` resolved members (so the chart stays
    readable — the full set of teams lives in the diversity table). Returns
    ``(frame, segment_columns)``, teams ordered largest first.
    """
    def resolved_count(members: set[str]) -> int:
        return sum(1 for m in members if affiliations.get(m.lower()))

    groups = [
        (team, set(members))
        for team, members in team_membership.items()
        if resolved_count(members) >= min_resolved
    ]
    if not groups:
        return pd.DataFrame(columns=["team"]), []
    groups.sort(key=lambda g: len(g[1]), reverse=True)

    def segment(login: str) -> str:
        return affiliations.get(login.lower()) or UNKNOWN_LABEL

    seat_totals: Counter[str] = Counter()
    for _, members in groups:
        for login in members:
            seat_totals[segment(login)] += 1

    named = [org for org, _ in seat_totals.most_common() if org not in {INDEPENDENT, UNKNOWN_LABEL}]
    kept = named[:top_n]
    segments = [*kept]
    if len(named) > top_n:
        segments.append(OTHER_LABEL)
    if seat_totals.get(INDEPENDENT):
        segments.append(INDEPENDENT)
    if seat_totals.get(UNKNOWN_LABEL):
        segments.append(UNKNOWN_LABEL)

    kept_set = set(kept)
    rows: list[dict[str, object]] = []
    for team, members in groups:
        counts = dict.fromkeys(segments, 0)
        for login in members:
            seg = segment(login)
            if seg not in kept_set and seg not in {INDEPENDENT, UNKNOWN_LABEL}:
                seg = OTHER_LABEL
            counts[seg] += 1
        rows.append({"team": team, **counts})

    return _sort_by_concentration(pd.DataFrame(rows, columns=["team", *segments]), segments, kept), segments
