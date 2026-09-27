"""Shared declarations for interactive chart sources.

A chart spec's ``interactive_sources`` maps a PNG filename to the CSV that
feeds its interactive version and how to draw it; ``export/chart_data.py``
reads these. The presets here keep a series' label and colour identical on
every card that shows it, and keep each counting rule written once.
"""

from __future__ import annotations

from hiero_analytics.analysis.scorecard_analysis import CHECK_COLUMNS
from hiero_analytics.config.analysis import ACTIVITY_WEIGHTS, HEATMAP_MONTHS, HEATMAP_TOP_ROWS
from hiero_analytics.config.charts import DIFFICULTY_COLORS
from hiero_analytics.domain.labels import DIFFICULTY_ORDER

# The span tabs every windowed card shares, widest first: (PNG/CSV suffix, window).
SPAN_WINDOWS = [("", "all"), ("_365d", 365), ("_30d", 30), ("_7d", 7)]

ROLE_SERIES = [
    {"key": "general_user", "label": "General contributors", "color": "var(--chart-general)"},
    {"key": "triage", "label": "Triage", "color": "var(--chart-triage)"},
    {"key": "committer", "label": "Committers", "color": "var(--chart-committer)"},
    {"key": "maintainer", "label": "Maintainers", "color": "var(--chart-maintainer)"},
]

# Keyed by the display names the by-repo CSV uses as columns.
DIFFICULTY_SERIES = [{"key": name, "label": name, "color": DIFFICULTY_COLORS[name]} for name in DIFFICULTY_ORDER]

# The over-time CSVs use short column keys for the same levels.
DIFFICULTY_OVER_TIME_SERIES = [
    {"key": key, "label": name, "color": DIFFICULTY_COLORS[name]}
    for key, name in [
        ("unknown", "Unknown"),
        ("gfi", "Good First Issue"),
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
]

ROLE_ACTIVITY = {
    "kind": "timeseries",
    "series": ROLE_SERIES,
    "mark": "bar",
    "stacked": True,
    "metric": "active_contributors_by_role",
    "unit": "Unique active contributors",
    "population": (
        "Each person is counted once per bucket under the highest governance role they hold in any "
        "repository. Bots are excluded. Counts across periods must not be added to obtain unique people."
    ),
}

ROLE_BY_REPO = {
    "kind": "categories",
    "category": "repo",
    "category_label": "Repository",
    "series": ROLE_SERIES,
    "stacked": True,
    "orientation": "horizontal",
    "rank": True,
    "top_n": 10,
    "metric": "active_contributors_by_role",
    "unit": "Unique active contributors",
    "population": (
        "Each person is counted once per repository under the role they hold there. Someone active in "
        "several repositories is counted in each, so repository counts must not be added to obtain "
        "unique people. Bots are excluded."
    ),
    # The PNG pools small repositories into "Other Repos"; this view lists every one.
    "note": (
        "Each bar is a repository, counting people active there over the selected span, grouped by the "
        "governance role they hold in that repo (general → triage → committer → maintainer). The chart "
        "shows the busiest repositories first; the data view lists every repository."
    ),
}


def affiliation_share(role: str, plural: str, suffix: str) -> dict:
    """Ranked employer bars for one role, replacing the top-2 pie."""
    return {
        "kind": "categories",
        "file": f"affiliation_distribution{suffix}.csv",
        "category": "organisation",
        "category_label": "Organisation",
        "series": [{"key": plural, "label": plural.capitalize(), "color": "var(--chart-maintainer)"}],
        "orientation": "horizontal",
        "rank": True,
        "top_n": 10,
        "window": "snapshot",
        "metric": f"{role}_affiliations",
        "unit": plural.capitalize(),
        "population": (
            f"People whose highest role anywhere is {role}, by curated employer. Solo contributors appear "
            "as 'Independent'; people with no curated affiliation are excluded, so shares are of resolved "
            "people only."
        ),
        # The PNG pools all but the two largest employers; this view ranks every one.
        "note": (
            "Every employer with at least one resolved role-holder, largest first. Check the "
            "affiliations-known tile before reading the bars as the whole population."
        ),
    }


def composition(category: str, label: str, file: str, unit: str, population: str) -> dict:
    """Each row's employer mix, drawn as 100% bars in the analysis's concentration order."""
    return {
        "kind": "categories",
        "file": file,
        "category": category,
        "category_label": label,
        "series": "columns",
        "palette": "organisation",
        "stacked": True,
        "normalize": True,
        "orientation": "horizontal",
        "top_n": 15,
        "reference": {"value": 50, "label": "Majority"},
        "window": "snapshot",
        "metric": "employer_composition",
        "unit": unit,
        "population": population,
        "note": (
            "Each bar is normalised to 100%, so segments are each employer's share of that row's "
            "role-holders; the dashed line marks 50%. Rows are ordered most-concentrated first. The six "
            "largest employers get their own colour; smaller ones pool into 'Other orgs'. The data view "
            "shows the underlying counts."
        ),
    }


REPO_GROWTH = {
    "kind": "timeseries",
    "file": "repo_growth_timeline.csv",
    "category": "month",
    "category_label": "Month (UTC)",
    "frequency": "month",
    # The CSV stores each month as its first day ("2024-01-01").
    "normalize_dates": True,
    "metric": "repositories_created",
    "population": (
        "Repositories currently in the organisation, by the month GitHub records them as created. "
        "Deleted or transferred-out repositories are not counted."
    ),
}

# New repositories are a flow (bars, empty months are zero); the running total is
# a stock (a line that holds its level through empty months).
REPO_GROWTH_SOURCES = {
    "repos_created_per_month.png": {
        **REPO_GROWTH,
        "series": [{"key": "repos_created", "label": "New repositories", "color": "var(--chart-committer)"}],
        "unit": "Repositories created",
    },
    "cumulative_repo_count.png": {
        **REPO_GROWTH,
        "series": [
            {"key": "cumulative_repos", "label": "Repositories", "color": "var(--chart-committer)", "fill": "carry"}
        ],
        "mark": "line",
        "unit": "Total repositories",
    },
}


_WEIGHTS = ", ".join(f"{name} ×{weight}" for name, weight in ACTIVITY_WEIGHTS.items())


def activity_heatmap(
    file: str, row: str, label: str, *, rule: str, avatars: bool = False, sublabel: dict | None = None
) -> dict:
    """A weighted-activity heatmap (one of contributors, teams, organisations, repositories)."""
    return {
        "kind": "matrix",
        "file": file,
        "row": row,
        "row_label": label,
        **({"sublabel": sublabel} if sublabel else {}),
        "total": {"key": "activity score", "label": "Six-month score"},
        "columns": "months",
        "value_label": "Weighted activity score",
        "avatars": avatars,
        "top_n": HEATMAP_TOP_ROWS,
        "window": "snapshot",
        "metric": "weighted_activity",
        "unit": "Weighted monthly activity score",
        # Weighted, never raw counts: say so wherever the number appears.
        "population": (
            f"A weighted score, not a count: {_WEIGHTS}. Other activity (comments, labels) is not scored. "
            f"Columns are the last {HEATMAP_MONTHS} complete calendar months (UTC); the current month is "
            f"excluded. Bots are excluded. {rule}"
        ),
        "note": (
            f"The {HEATMAP_TOP_ROWS} highest six-month scores are shown first; search or show all to see every "
            "row. Stronger colour means a higher score; the scale lists each shade's range, and every cell "
            "states its exact value."
        ),
    }


def role_network(key: str, label: str) -> dict:
    """Repositories linked by people who hold one governance role."""
    return {
        "kind": "network",
        "file": f"{key}_network_nodes.csv",
        "edges_file": f"{key}_network_edges.csv",
        "member_label": label,
        "window": "snapshot",
        "metric": f"{key}_comembership",
        "unit": f"Repositories linked by shared {label}",
        "population": (
            f"A node is a repository where someone holds the {key} role (their highest role in that "
            f"repository); its size is how many of those {label} were active there in the last 90 days. "
            f"A link joins two repositories that share at least one {key}, counted whether active or not."
        ),
    }


CONTRIBUTOR_HEATMAP = activity_heatmap(
    "contributor_activity_heatmap.csv",
    "contributor name",
    "Contributor",
    avatars=True,
    sublabel={"key": "role", "label": "Highest role"},
    rule="Each row is one person.",
)

ACTIVITY_HEATMAP_SOURCES = {
    "contributor_activity_heatmap.png": CONTRIBUTOR_HEATMAP,
    "team_activity_heatmap.png": activity_heatmap(
        "team_activity_heatmap.csv",
        "team",
        "Team",
        rule="A person on several teams counts toward each, so team rows overlap and must not be added.",
    ),
    "org_activity_heatmap.png": activity_heatmap(
        "org_activity_heatmap.csv",
        "organisation",
        "Organisation",
        rule="Each person counts toward their curated employer; people with no curated affiliation are excluded.",
    ),
    "repo_activity_heatmap.png": activity_heatmap(
        "repo_activity_heatmap.csv",
        "repo",
        "Repository",
        rule="Each event counts once, in the repository where it happened.",
    ),
}

CONTRIBUTOR_NETWORK = {
    "kind": "network",
    "file": "all_network_nodes.csv",
    "edges_file": "all_network_edges.csv",
    "member_label": "contributors",
    "window": "snapshot",
    "metric": "contributor_comembership",
    "unit": "Repositories linked by shared contributors",
    "population": (
        "A node is a repository with recorded contributors (bots excluded); its size is how many were active "
        "there in the last 90 days. A link joins two repositories that share enough contributors: the "
        "threshold is one shared contributor per six repositories in the organisation, at least one."
    ),
}

# Released-in-window events; the PNG spans 548 days for its "Last 18 months" tab.
RELEASE_TIMELINE_SOURCES = {
    f"release_timeline{suffix}.png": {
        "kind": "events",
        "file": "release_timeline.csv",
        "category": "repo",
        "category_label": "Repository",
        "strip_org_prefix": True,
        "time": "published_at",
        "label": "tag_name",
        "label_label": "Tag",
        "flag": {
            "key": "is_prerelease",
            "false": {"key": "release", "label": "Release", "color": "var(--chart-2)"},
            "true": {"key": "prerelease", "label": "Prerelease", "color": "var(--chart-1)"},
        },
        "window": days,
        "metric": "releases",
        "unit": "Published releases",
        "population": (
            "Each published GitHub release, by repository and publication time (UTC). Drafts are excluded; "
            "prereleases are marked. Repositories with no release in the window are not shown."
        ),
    }
    for suffix, days in [("", 548), ("_365d", 365), ("_30d", 30), ("_7d", 7)]
}

SCORECARD_CHECKS = {
    "kind": "matrix",
    "file": "org_scorecard_checks.csv",
    "row": "repo",
    "row_label": "Repository",
    "strip_org_prefix": True,
    "total": {"key": "score", "label": "Aggregate score"},
    "columns": [{"key": check, "label": check} for check in CHECK_COLUMNS],
    "values": "number",
    "scale_max": 10,
    "missing": {"value": -1, "label": "Not scored"},
    "value_label": "Check score (0–10)",
    "window": "snapshot",
    "metric": "openssf_scorecard_checks",
    "unit": "OpenSSF Scorecard check scores",
    "population": (
        "Each repository's per-check OpenSSF Scorecard results (0–10), as published by the Scorecard API. "
        "'Not scored' means Scorecard reported the check as inconclusive or did not report it. The "
        "aggregate is Scorecard's own "
        "weighted score, not the sum or mean of the checks."
    ),
    "note": (
        "One row per repository, one column per check; stronger colour means a higher check score on a fixed "
        "0–10 scale. Replaces the stacked breakdown, whose bar lengths implied the checks add up to the score."
    ),
}


def status_meter(file: str, label: str, unit: str, population: str) -> dict:
    """A snapshot split into a few statuses, headline status first, as one part-to-whole meter."""
    return {
        "kind": "categories",
        "file": file,
        "category": "status",
        "category_label": label,
        "series": [{"key": "count", "label": unit}],
        "mark": "meter",
        "window": "snapshot",
        "metric": file.removesuffix(".csv"),
        "unit": unit,
        "population": population,
    }


def ranked_counts(file: str, category: str, label: str, key: str, unit: str, population: str) -> dict:
    """An explorable ranking backed by the complete analysis table."""
    return {
        "kind": "categories",
        "file": file,
        "category": category,
        "category_label": label,
        "series": [{"key": key, "label": unit}],
        "orientation": "horizontal",
        "rank": True,
        "top_n": 15,
        "window": "snapshot",
        "metric": file.removesuffix(".csv"),
        "unit": unit,
        "population": population,
    }


OVERVIEW_SOURCES = {
    "contributor_counts.png": {
        **ranked_counts(
            "contributor_counts.csv",
            "repo",
            "Repository",
            "contributors",
            "Contributors",
            "Distinct contributors recorded in each repository. People active in several repositories count in each.",
        ),
        "strip_org_prefix": True,
    },
    "language_distribution.png": ranked_counts(
        "language_distribution.csv",
        "language",
        "Language",
        "count",
        "Repositories",
        "Repositories grouped by their primary language reported by GitHub; not lines of code.",
    ),
    "push_activity.png": status_meter(
        "push_activity.csv",
        "Push activity",
        "Repositories",
        "Repositories with a push in the 30 days before collection versus other repositories.",
    ),
}

SINGLE_EMPLOYER_SOURCES = {
    f"{stem}.png": ranked_counts(
        f"{stem}.csv",
        "organisation",
        "Organisation",
        key,
        unit,
        f"{population} Independent and unresolved affiliations follow the diversity table's counting rules.",
    )
    for stem, key, unit, population in [
        (
            "single_employer_teams_by_org",
            "teams",
            "Teams",
            "Governance teams whose resolved members share one employer.",
        ),
        (
            "single_employer_repos_by_org",
            "repos",
            "Repositories",
            "Repositories whose resolved maintainers share one employer.",
        ),
        (
            "single_employer_repos_by_org_committers",
            "repos",
            "Repositories",
            "Repositories whose resolved committers share one employer.",
        ),
    ]
}

OWNERSHIP_SOURCES = {
    "org_codeowner_summary.png": status_meter(
        "org_codeowner_summary.csv",
        "CODEOWNERS file",
        "Repositories",
        "Repositories with or without a CODEOWNERS file in the standard GitHub locations.",
    ),
    "org_runner_chart.png": {
        **ranked_counts(
            "org_runner_summary.csv",
            "repo",
            "Repository",
            "Standard",
            "Workflow jobs",
            "Workflow job runner declarations, grouped by repository. Indeterminate declarations cannot be classified.",
        ),
        "series": [{"key": key, "label": key} for key in ["Self-Hosted", "Standard", "Indeterminate"]],
        "stacked": True,
        "strip_org_prefix": True,
    },
}

HIP_STATUS_SOURCE = {
    **ranked_counts(
        "hip_activity_by_status.csv",
        "bucket",
        "HIP status",
        "merged",
        "HIPs",
        "Each HIP counts once under its strongest PR evidence. No citing PR for a Final/Active HIP is a citation gap, not proof it is unimplemented.",
    ),
    "rank": False,
    "stacked": True,
    "series": [
        {"key": "merged", "label": "With merged implementation PRs"},
        {"key": "open_only", "label": "With open PRs only"},
        {"key": "none_awaiting", "label": "Awaiting implementation evidence"},
        {"key": "citation_gap", "label": "Citation gap (Final/Active)"},
    ],
}

DISCORD_SOURCES = {
    "hiero_discord_channel_categories.png": {
        **ranked_counts(
            "hiero_discord_channel_categories.csv",
            "category",
            "Topic",
            "earlier",
            "Messages",
            "Messages from a manual Discord snapshot, split into its last 90 days and earlier history.",
        ),
        "series": [{"key": "last_90d", "label": "Last 90 days"}, {"key": "earlier", "label": "Earlier history"}],
        "stacked": True,
    },
    "hiero_discord_recent_activity_30d.png": {
        **ranked_counts(
            "hiero_discord_recent_activity_30d.csv",
            "channel_label",
            "Channel",
            "d30",
            "Messages",
            "Messages in the 30 days before the manual Discord snapshot. Show all to inspect every channel.",
        ),
        "top_n": 5,
    },
    "hiero_discord_monthly_traffic.png": {
        "kind": "timeseries",
        "file": "hiero_discord_monthly_traffic.csv",
        "category": "month",
        "category_label": "Month (UTC)",
        "frequency": "month",
        "normalize_dates": True,
        "series": [{"key": "messages", "label": "Messages"}],
        "mark": "area",
        "metric": "discord_messages",
        "unit": "Messages",
        "population": "Monthly messages from a manual Discord snapshot.",
    },
}
