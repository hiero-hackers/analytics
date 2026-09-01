"""Role-holder organisation-diversity analysis.

Reads the curated ``data/affiliations.yaml`` mapping (login -> organisation) and,
given the current holders of a governance role, classifies each holder and builds
the distribution + concentration metrics for the organisation-diversity charts.

The builders are role-agnostic: pass the role (or the value-column name derived
from it) and the same code serves maintainers, committers or triage. Maintainer
remains the default so the existing output surface is unchanged.

Independents (people with an identity but no corporate employer) count *toward*
diversity: in the concentration measure each is its own singleton entity, so a
large independent tail lowers the HHI rather than inflating one bucket.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

import pandas as pd
import yaml

from hiero_analytics.config.paths import SRC
from hiero_analytics.domain.repos import bare_repo

_HEATMAP_META = {"contributor name", "role", "activity score"}

logger = logging.getLogger(__name__)

AFFILIATIONS_PATH = SRC / "data" / "affiliations.yaml"
INDEPENDENT = "Independent"
UNKNOWN_LABEL = "Unknown"
OTHER_LABEL = "Other orgs"
_UNKNOWN_VALUES = {"", "?", "unknown", "none"}

DEFAULT_ROLE = "maintainer"


def role_column(role: str) -> str:
    """Column/keyname for a role's population count, e.g. ``maintainer`` -> ``maintainers``."""
    return f"{role}s"


def distribution_columns(value_col: str = "maintainers") -> list[str]:
    """Column order for an affiliation-distribution frame counting ``value_col``."""
    return ["organisation", value_col]


def repo_diversity_columns(count_col: str = "maintainers") -> list[str]:
    """Column order for a per-repo diversity frame whose population column is ``count_col``."""
    return [
        "repo",
        count_col,
        "distinct_orgs",
        "top_org",
        "top_org_pct",
        "independent",
        "unknown",
        "organisations",
    ]


DISTRIBUTION_COLUMNS = distribution_columns()
CLASSIFIED_COLUMNS = ["login", "organisation", "status"]
REPO_DIVERSITY_COLUMNS = repo_diversity_columns()
TEAM_DIVERSITY_COLUMNS = [
    "team",
    "members",
    "resolved",
    "distinct_orgs",
    "top_org",
    "top_org_pct",
    "hhi",
    "unknown",
    "single_employer",
    "organisations",
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


def classify_role_holders(logins: set[str], affiliations: dict[str, str]) -> pd.DataFrame:
    """One row per role-holder: login, organisation, status.

    status is ``affiliated`` (named employer), ``independent`` (solo / no
    employer), or ``unknown`` (no entry in the affiliations map). The caller
    decides which role the ``logins`` set represents.
    """
    rows: list[dict[str, object]] = []
    for login in sorted(logins):
        org = affiliations.get(login.lower())
        if not org:
            rows.append({"login": login, "organisation": None, "status": "unknown"})
        elif org == INDEPENDENT:
            rows.append({"login": login, "organisation": INDEPENDENT, "status": "independent"})
        else:
            rows.append({"login": login, "organisation": org, "status": "affiliated"})
    return pd.DataFrame(rows, columns=CLASSIFIED_COLUMNS)


def build_affiliation_distribution(
    classified: pd.DataFrame,
    *,
    value_col: str = "maintainers",
    include_unknown: bool = False,
) -> pd.DataFrame:
    """Chart frame (organisation, ``value_col``) over the role-holder population.

    Named employers each get a row counting their role-holders; all independents
    fold into a single ``Independent`` row (the chart shows the size of the
    diverse tail). With ``include_unknown`` the unmapped holders form their own
    ``Unknown`` band rather than vanishing, so the chart's total is the real
    population — the composition charts already work this way. Sorted by count,
    descending.
    """
    columns = distribution_columns(value_col)
    if classified.empty:
        return pd.DataFrame(columns=columns)

    population = classified.copy()
    if include_unknown:
        population.loc[population["status"] == "unknown", "organisation"] = UNKNOWN_LABEL
    else:
        population = population[population["status"] != "unknown"]
    if population.empty:
        return pd.DataFrame(columns=columns)

    counts = (
        population.groupby("organisation")["login"]
        .nunique()
        .reset_index(name=value_col)
        .sort_values(value_col, ascending=False, kind="stable")
        .reset_index(drop=True)
    )
    return counts[columns]


def known_share_pct(classified: pd.DataFrame) -> int:
    """Percentage of the population whose affiliation is curated (0 when empty).

    Quoted alongside any chart that shows an ``Unknown`` band, so a reader can
    weigh the shares against how much of the roster is actually resolved.
    """
    total = len(classified)
    if not total:
        return 0
    return round(100 * int((classified["status"] != "unknown").sum()) / total)


@dataclass(frozen=True)
class AffiliationSummary:
    """Coverage counts and concentration for one population of role-holders."""

    total: int
    affiliated: int
    independent: int
    unknown: int
    distinct_orgs: int
    hhi: int
    top_org: str | None
    top_share_pct: int


def summarize_affiliation(classified: pd.DataFrame) -> AffiliationSummary:
    """Coverage counts plus concentration (HHI) over the known set.

    HHI treats each independent as its own singleton entity, so independents
    push concentration down.
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
        for login, org, status in zip(known["login"], known["organisation"], known["status"], strict=True)
    ]
    known_total = len(entities)
    employer_counts = known[known["status"] == "affiliated"]["organisation"].value_counts()
    entity_counts = Counter(entities)
    hhi = round(10000 * sum((n / known_total) ** 2 for n in entity_counts.values())) if known_total else 0
    top_org = str(employer_counts.index[0]) if not employer_counts.empty else None
    top_share = round(100 * int(employer_counts.iloc[0]) / known_total) if known_total and top_org else 0

    return AffiliationSummary(
        total=total,
        affiliated=affiliated,
        independent=independent,
        unknown=unknown,
        distinct_orgs=int(employer_counts.size),
        hhi=hhi,
        top_org=top_org,
        top_share_pct=top_share,
    )


def top_n_with_other(
    distribution: pd.DataFrame,
    label_col: str,
    value_col: str,
    *,
    top_n: int = 6,
    always_keep: Collection[str] = (),
    always_pool: Collection[str] = (),
) -> pd.DataFrame:
    """Fold a distribution to its top-N rows plus a single ``Other (k)`` row.

    Keeps a donut readable: the largest ``top_n`` slices stay, the rest collapse
    into one. Labels in ``always_keep`` survive the fold however small they are,
    so a band the chart promises to show cannot silently disappear into
    ``Other``; they do not consume the ``top_n`` budget. Labels in
    ``always_pool`` are the mirror image: they always land in ``Other``, however
    large, and never compete for a slot — which is how a non-employer band like
    ``Independent`` is kept from displacing a real employer from the ranking.
    Returns the frame unchanged when it already has ``top_n`` rows or fewer, and
    when pooling would leave nothing ranked at all.
    """
    if distribution.empty:
        return distribution
    ordered = distribution.sort_values(value_col, ascending=False).reset_index(drop=True)
    pooled = ordered[ordered[label_col].isin(always_pool)]
    rankable = ordered[~ordered[label_col].isin(always_pool)]
    # Pooling every row would leave a pie whose only slice is 'Other' — no
    # information at all, so show the distribution as it stands instead.
    if rankable.empty:
        return ordered
    if pooled.empty and len(ordered) <= top_n:
        return ordered
    pinned = rankable[label_col].isin(always_keep)
    rest = rankable[~pinned]
    kept = pd.concat([rest.head(top_n), rankable[pinned]]).sort_values(value_col, ascending=False)
    tail = pd.concat([rest.iloc[top_n:], pooled])
    if tail.empty:
        return kept.reset_index(drop=True)
    other = pd.DataFrame([{label_col: f"Other ({len(tail)})", value_col: int(tail[value_col].sum())}])
    return pd.concat([kept, other], ignore_index=True)


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


def _repo_role_holders(role_lookup: dict[str, dict[str, str]], role: str) -> dict[str, set[str]]:
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
    role: str = DEFAULT_ROLE,
) -> pd.DataFrame:
    """Per-repo organisational diversity of a repo's ``role``-holders.

    One row per repo: how many hold the role, how many distinct employers they
    span, the largest employer and its share, and the independent / unknown
    counts. A repo where every holder shares one employer (``distinct_orgs`` 1)
    is an organisational bus-factor even when the org-wide picture looks diverse.
    Sorted single-employer-first (then most holders), so capture risk surfaces.
    The population column is named for the role (``maintainers``, ``committers``).
    """
    count_col = role_column(role)
    rows: list[dict[str, object]] = []
    for repo, logins in _repo_role_holders(role_lookup, role).items():
        classified = classify_role_holders(logins, affiliations)
        employer_counts = classified[classified["status"] == "affiliated"]["organisation"].value_counts()
        independent = int((classified["status"] == "independent").sum())
        unknown = int((classified["status"] == "unknown").sum())
        top_org = employer_counts.index[0] if not employer_counts.empty else None
        # Share of *resolved* holders (unknowns excluded) — the same statistic
        # as the team table's "largest org %", so the two tables read alike.
        resolved = len(logins) - unknown
        top_pct = round(100 * int(employer_counts.iloc[0]) / resolved) if not employer_counts.empty and resolved else 0
        rows.append(
            {
                "repo": repo,
                count_col: len(logins),
                "distinct_orgs": int(employer_counts.size),
                "top_org": top_org,
                "top_org_pct": top_pct,
                "independent": independent,
                "unknown": unknown,
                "organisations": ", ".join(employer_counts.index.tolist()),
            }
        )

    df = pd.DataFrame(rows, columns=repo_diversity_columns(count_col))
    if df.empty:
        return df
    return df.sort_values(["distinct_orgs", count_col], ascending=[True, False]).reset_index(drop=True)


def _build_org_composition(
    groups: list[tuple[str, set[str]]],
    affiliations: dict[str, str],
    *,
    label_col: str,
    top_n: int,
) -> tuple[pd.DataFrame, list[str]]:
    """Shared engine for the stacked employer-composition charts.

    ``groups`` is ``[(label, member_logins)]`` in the desired row order. The
    ``top_n`` employers (by total seats across all groups) keep their own
    segment; the rest pool into ``Other orgs``. Independents and unknowns get
    their own segments so each bar's length is the group's full member count.
    Returns ``(frame, segment_columns)`` with segments ordered for stacking.
    """
    if not groups:
        return pd.DataFrame(columns=[label_col]), []

    def segment(login: str) -> str:
        # INDEPENDENT passes through as its own segment; unmapped logins are Unknown.
        return affiliations.get(login.lower()) or UNKNOWN_LABEL

    seat_totals: Counter[str] = Counter()
    for _, members in groups:
        for login in members:
            seat_totals[segment(login)] += 1

    named = [org for org, _ in seat_totals.most_common() if org not in {INDEPENDENT, UNKNOWN_LABEL}]
    kept = named[:top_n]
    # Stacking order: big employers first, then Other, Independent, and Unknown last.
    segments = [*kept]
    if len(named) > top_n:
        segments.append(OTHER_LABEL)
    if seat_totals.get(INDEPENDENT):
        segments.append(INDEPENDENT)
    if seat_totals.get(UNKNOWN_LABEL):
        segments.append(UNKNOWN_LABEL)

    kept_set = set(kept)
    rows: list[dict[str, object]] = []
    for label, members in groups:
        counts = dict.fromkeys(segments, 0)
        for login in members:
            seg = segment(login)
            if seg not in kept_set and seg not in {INDEPENDENT, UNKNOWN_LABEL}:
                seg = OTHER_LABEL
            counts[seg] += 1
        rows.append({label_col: label, **counts})

    frame = pd.DataFrame(rows, columns=[label_col, *segments])
    return _sort_by_concentration(frame, segments, kept), segments


def build_repo_org_composition(
    role_lookup: dict[str, dict[str, str]],
    affiliations: dict[str, str],
    *,
    role: str = DEFAULT_ROLE,
    top_n: int = 6,
) -> tuple[pd.DataFrame, list[str]]:
    """Per-repo role-holder counts split by employer, for a stacked composition chart.

    The ``top_n`` employers (by total seats across repos) get their own column;
    the rest pool into ``Other orgs``. Independents and unknowns get their own
    columns so each bar's length is the repo's full holder count. Returns
    ``(frame, segment_columns)`` with segments ordered for stacking.
    """
    groups = list(_repo_role_holders(role_lookup, role).items())
    return _build_org_composition(groups, affiliations, label_col="repo", top_n=top_n)


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
        classified = classify_role_holders(set(members), affiliations)
        summary = summarize_affiliation(classified)
        resolved = summary.affiliated + summary.independent
        # Full org breakdown, e.g. "Hashgraph 5, LimeChain 2, Independent 1".
        employer_counts = classified[classified["status"] == "affiliated"]["organisation"].value_counts()
        mix = [f"{org} {int(n)}" for org, n in employer_counts.items()]
        if summary.independent:
            mix.append(f"Independent {summary.independent}")
        rows.append(
            {
                "team": team,
                "members": summary.total,
                "resolved": resolved,
                "distinct_orgs": summary.distinct_orgs,
                "top_org": summary.top_org,
                "top_org_pct": summary.top_share_pct,
                "hhi": summary.hhi,
                "unknown": summary.unknown,
                # One employer holds every resolved seat (no independents) -> capture
                # risk. Teams where unmapped members outnumber resolved ones are not
                # flagged: too little of the team is known to call it captured.
                "single_employer": (
                    summary.distinct_orgs == 1
                    and resolved >= 2
                    and summary.independent == 0
                    and resolved >= summary.unknown
                ),
                "organisations": ", ".join(mix),
            }
        )

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


def build_single_employer_repo_counts(repo_diversity: pd.DataFrame, *, count_col: str = "maintainers") -> pd.DataFrame:
    """Count single-employer repositories by the org that holds them (chart frame).

    A repo is single-employer when every *resolved* holder shares one employer
    (no independents) and there are at least two of them — the repo-level analogue
    of a captured team. Repos where unmapped holders outnumber resolved ones
    are not flagged: too little of the repo's roster is known to call it captured.
    """
    cols = ["organisation", "repos"]
    if repo_diversity.empty:
        return pd.DataFrame(columns=cols)
    resolved = repo_diversity[count_col] - repo_diversity["unknown"]
    single = (
        (repo_diversity["distinct_orgs"] == 1)
        & (repo_diversity["independent"] == 0)
        & (resolved >= 2)
        & (resolved >= repo_diversity["unknown"])
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
        (team, set(members)) for team, members in team_membership.items() if resolved_count(members) >= min_resolved
    ]
    groups.sort(key=lambda g: len(g[1]), reverse=True)
    return _build_org_composition(groups, affiliations, label_col="team", top_n=top_n)
