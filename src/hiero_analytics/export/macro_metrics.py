"""Headline metric tiles per dashboard macro, shared by both frontends.

The legacy generated dashboard and the JSON data API render the same tiles;
keeping the computations here means neither can drift from the other. Each
builder takes the macro's loaded section tables (keyed by section id) plus the
org's data directory, and returns ``(label, value)`` pairs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hiero_analytics.config.analysis import GONE_DARK_DAYS
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.domain.roles import ROLE_PRIORITY


def _load(path: Path) -> pd.DataFrame:
    """Read a CSV, or an empty frame if it doesn't exist."""
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _pct(count: int, total: int) -> str:
    """A whole-number percentage tile value ("37%")."""
    return f"{round(100 * count / total)}%"


# Counted at each person's highest role across all repos, so the buckets
# partition the permission-holders (no double-counting someone who is, say,
# maintainer in one repo and triage in another). Seniority comes from the shared
# ROLE_PRIORITY; general_user is not a granted role, so it is excluded.
_GRANTED_ROLES = tuple(role for role in ROLE_PRIORITY if role != "general_user")


def _holders_by_highest_role(coverage: pd.DataFrame) -> dict[str, int]:
    """Distinct permission-holders per highest role, from ``role_coverage_all``."""
    if coverage.empty or "granted_role" not in coverage or "user" not in coverage:
        return {}
    df = coverage.assign(
        _u=coverage["user"].str.lower(),
        _r=coverage["granted_role"].map(ROLE_PRIORITY).fillna(0),
    )
    highest = df.sort_values("_r").groupby("_u")["granted_role"].last()
    counts = highest.value_counts()
    return {role: int(counts.get(role, 0)) for role in _GRANTED_ROLES}


def contributors_metrics(loaded: dict[str, pd.DataFrame], org_data_dir: Path) -> list:
    """Headline tiles for the Contributors macro: who shows up, and how.

    All shares are over the full contributor list (the profiles table). "% commit"
    is measured as opening PRs — commits themselves aren't ingested.
    """
    profiles = loaded["profiles"]
    total = len(profiles)
    if total == 0:
        return []
    metrics = [
        ("contributors", total),
    ]
    # "Active last month": the 30d period variant lists exactly the contributors
    # with activity in that window, so the share is a row-count ratio.
    month = next((p for p in ACTIVITY_PERIODS if p.key == "30d"), None)
    if month is not None:
        active = _load(org_data_dir / month.filename("contributor_activity_profiles"))
        if not active.empty:
            metrics.append(("active last month %", _pct(len(active), total)))
    metrics += [
        ("multi-repo %", _pct(int((profiles["repos_touched"] >= 2).sum()), total)),
        ("file issues %", _pct(int((profiles["issues_opened"] > 0).sum()), total)),
        ("open PRs %", _pct(int((profiles["prs_opened"] > 0).sum()), total)),
        ("give reviews %", _pct(int((profiles["reviews_given"] > 0).sum()), total)),
    ]
    completers = _load(org_data_dir / "gfi_completers.csv")
    if "login" in completers:
        metrics.append(("completed a GFI %", _pct(int(completers["login"].nunique()), total)))
    return metrics


def governance_metrics(loaded: dict[str, pd.DataFrame], org_data_dir: Path) -> list:
    """Headline tiles for the Governance macro."""
    metrics: list = []
    role_counts = _holders_by_highest_role(loaded["repo"])
    for role, label in (("maintainer", "maintainers"), ("committer", "committers"), ("triage", "triage")):
        if role in role_counts:
            metrics.append((label, role_counts[role]))
    # The gonedark table follows the shared period tabs, but this tile keeps its
    # fixed 180-day access-hygiene threshold. Quiet-for-a-month is a superset of
    # quiet-for-180-days, so the 30d variant filters down to it exactly; a blank
    # days_since_active is a holder with no recorded activity at all.
    month = next((p for p in ACTIVITY_PERIODS if p.key == "30d"), None)
    quiet_month = _load(org_data_dir / month.filename("role_coverage_globally_quiet")) if month else pd.DataFrame()
    if "days_since_active" in quiet_month:
        days = quiet_month["days_since_active"]
        metrics.append(("quiet permission-holders (180d+)", int((days.isna() | (days >= GONE_DARK_DAYS)).sum())))
    if "status" in loaded["teams"]:
        metrics.append(("quiet teams", int((loaded["teams"]["status"] == "quiet").sum())))
    return metrics


METRICS_BY_MACRO = {"Contributors": contributors_metrics, "Governance": governance_metrics}


def macro_metrics(macro_name: str, family, org_data_dir: Path) -> list:
    """The macro's tiles computed from its section tables, or [] when none apply."""
    builder = METRICS_BY_MACRO.get(macro_name)
    if builder is None:
        return []
    loaded = {spec["id"]: _load(org_data_dir / spec["file"]) for spec in family.SECTION_SPECS}
    return builder(loaded, org_data_dir)
