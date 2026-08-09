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
                "title": "Most overdue relative to each repo's own pace",
                "description": (
                    "Repos currently furthest past their own typical release gap — a repo that "
                    "usually ships every 3 weeks and has gone quiet for 3 months ranks above one "
                    "that ships every 6 months and is 3 weeks 'late'. Repos with fewer than two "
                    "releases ever have no established cadence to compare against and are left "
                    "off this chart (see the staleness table below for those)."
                ),
                "files": [
                    ("Most overdue vs. own cadence", "release_staleness.png"),
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
        "many multiples of its usual pace it's currently overdue by. Repos with fewer than two "
        "releases ever (no established cadence) are excluded, not shown as zero."
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
        "Drop repos with fewer than two releases ever, or a zero-day median gap — no cadence to compare against.",
        "Sort descending and chart the most overdue repos.",
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
            "releases still gets a row, with its staleness fields blank rather than the row "
            "being silently absent. 'staleness_ratio' is null for repos with fewer than two "
            "releases (no cadence established yet) or a zero-day median gap."
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
                "well below 1 means it's release right on schedule. This is *relative to the "
                "repo's own history*, not a fixed threshold — a repo with a naturally long cadence "
                "isn't penalized for having one."
            ),
        },
        {
            "term": "What this tab cannot tell you.",
            "definition": (
                "Most zero-release repos are docs/governance/meta repos that were never going to "
                "ship a GitHub Release, not neglected code — the table doesn't distinguish the two, "
                'so read a blank row as "no release data," not automatically "unhealthy." '
                "Nothing here explains *why* a repo went quiet."
            ),
        },
    ],
}
