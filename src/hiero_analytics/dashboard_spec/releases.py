"""Releases — GitHub Releases cadence and staleness.

Its own tab rather than a Governance sub-section: release staleness isn't
governance-dependent or period-scoped (see analysis/releases.py and the
design discussion on hiero-hackers/analytics#331), so it doesn't fit
Governance's period-tabbed, governance-config-gated shape. Pure data; see
the package __init__ for assembly.
"""

from __future__ import annotations

# Shown when the selected org has no content for this tab.
ABSENT_NOTE = "No releases pipeline data for this org yet."

_GROUP = "Release cadence & staleness"

CHART_MACRO = {
    "name": "Releases",
    "charts": {
        "hiero-ledger": [
            {
                "id": "release-timeline",
                "group": _GROUP,
                "title": "Release timeline",
                "description": (
                    "Every release per repo over roughly the last 18 months. Y-axis sorted by "
                    "release count (busiest at top); the number beside each row is that repo's "
                    "total release count in the window, so a high-cadence repo's row stays "
                    "readable instead of turning into a solid smear of overlapping dots."
                ),
                "files": [
                    ("Release timeline", "release_timeline.png"),
                ],
            },
            {
                "id": "release-staleness-chart",
                "group": _GROUP,
                "title": "Shipping repos most overdue relative to their own pace",
                "description": (
                    "Repos currently furthest past their own typical release gap — a repo that "
                    "usually ships every 3 weeks and has gone quiet for 3 months ranks above one "
                    "that ships every 6 months and is 3 weeks 'late'. Repos that have never "
                    "released rank as maximally stale in the underlying data and the table below, "
                    "but aren't plotted here — a linear scale can't represent that fairly next to "
                    "a finite ratio. Repos with only one release ever, or a same-day repeat "
                    "release, have no established cadence to compare against either, so those are "
                    "left off too (see the staleness table below for all three cases)."
                ),
                "files": [
                    ("Most overdue shipping repos vs. own cadence", "release_staleness.png"),
                ],
            },
        ],
    },
}

CHART_NOTES = {
    "release_timeline.png": (
        "One dot per release, diamonds for prereleases, over roughly the last 18 months. "
        "Repos with zero releases in that window aren't shown on the chart (see the table for those)."
    ),
    "release_staleness.png": (
        "days_since_last_release divided by the repo's own median gap between releases — how "
        "many multiples of its usual pace it's currently overdue by. Never-released repos rank as "
        "maximally stale in the table (staleness_ratio is infinite), but aren't plotted here since "
        "a bar chart can't represent that on a linear scale. Repos with only one release ever, or "
        "a zero-day median gap, have no established cadence and are excluded from both."
    ),
}

CHART_METHODOLOGY = {
    "release_timeline.png": [
        "Fetch every published, non-draft release for each repo in the org (GitHub Releases only, no git-tag fallback).",
        "Window to roughly the last 18 months at chart time (the underlying CSV keeps full history).",
        "Plot one point per release, sorted top-to-bottom by total release count in the window.",
        "Label each row with its exact count instead of relying on dot density, which would distort under high cadence.",
    ],
    "release_staleness.png": [
        "For each repo, compute the median gap between consecutive releases (its typical cadence).",
        "Divide days since the most recent release by that median gap.",
        "Exclude repos with no plottable ratio: never-released repos (infinite in the "
        "underlying table, not on a linear chart) and repos with fewer than two releases "
        "ever or a zero-day median gap (no cadence to compare against at all).",
        "Sort descending and chart the most overdue shipping repos.",
    ],
}

WIDE_CHARTS: set[str] = {"release_timeline.png"}

SECTION_SPECS = [
    {
        "id": "release-staleness",
        "file": "release_repo_summary.csv",
        "title": "Release staleness by repo",
        "description": (
            "Every repo in the org, whether or not it has ever released — a repo with no "
            "releases still gets a row rather than being silently absent, and ranks as "
            "maximally stale ('staleness_ratio' is infinite; 'median_gap_days' stays blank "
            "since there's no cadence to report). 'staleness_ratio' is blank instead for the "
            "narrower case of a repo with only one release ever, or a same-day repeat release "
            "— it has shipped, there just isn't enough history yet to say what's normal for it."
        ),
        "columns": [
            ("repo", "repo"),
            ("latest_release", "latest release", "date"),
            ("days_since_last_release", "days since", "number"),
            ("median_gap_days", "typical gap (days)", "number"),
            ("staleness_ratio", "× overdue vs. own pace", "number"),
        ],
    },
]

SECTION_GROUPS = [
    (_GROUP, ["release-staleness"]),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

# This tab's "how to read this". Prose only; *asterisks* mark emphasis.
GLOSSARY = {
    "title": "How to read this tab — what the numbers mean",
    "layout": "notes",
    "terms": [
        {
            "term": "What is measured.",
            "definition": (
                "Published, non-draft GitHub Releases per repo — tags, timestamps, and whether "
                "each was marked a prerelease. No git-tag fallback: a repo that ships via tags "
                "without using GitHub Releases will show no data here."
            ),
        },
        {
            "term": "Why not release count.",
            "definition": (
                "Release count mostly reflects a repo's age and tagging style (a repo that tags a "
                "release on every merge racks up hundreds; one that ships quarterly won't), not "
                "how healthy its release cadence is — so it's shown as context, not as the "
                "headline signal."
            ),
        },
        {
            "term": "Staleness ratio.",
            "definition": (
                "days since the last release, divided by that repo's own *median* gap between "
                "releases. A ratio above 1 means the repo is currently past its own typical pace; "
                "well below 1 means it's on schedule. This is *relative to the repo's own "
                "history*, not a fixed threshold — a repo with a naturally long cadence isn't "
                "penalized for having one. A repo that has *never* released shows an infinite "
                "ratio — ranked as maximally stale rather than hidden, but not plotted on the "
                "chart, since a linear scale can't represent infinity next to a finite number."
            ),
        },
        {
            "term": "What this tab cannot tell you.",
            "definition": (
                "Most zero-release repos are docs/governance/meta repos that were never going to "
                "ship a GitHub Release, not neglected code — but the ranking treats every "
                "never-released repo as equally maximally stale, so the top of that ranking will "
                "usually be dominated by non-shipping repos rather than genuinely neglected "
                'ones. Read a repo at the top of the list as "has never released," not '
                'automatically "urgent." Nothing here explains *why* a repo went quiet, either.'
            ),
        },
    ],
}
