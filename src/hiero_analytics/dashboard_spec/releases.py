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
        # "*": org-independent — this pipeline is extra_orgs=True (releases
        # have no governance dependency), so the chart must render for any
        # org whose pipeline produced the files, not just hiero-ledger.
        "*": [
            {
                "id": "release-timeline",
                "group": _GROUP,
                "title": "Release timeline",
                "description": (
                    "Every release per repo, windowed by the tabs below (Week / 1 month / "
                    "1 year / Last 18 months) — busiest repos at top. Click the chart for the "
                    "full methodology."
                ),
                "files": [
                    (
                        "Release timeline",
                        [
                            ("Last 18 months", "release_timeline.png"),
                            ("1 year", "release_timeline_365d.png"),
                            ("1 month", "release_timeline_30d.png"),
                            ("Week", "release_timeline_7d.png"),
                        ],
                    ),
                ],
            },
        ],
    },
}

WIDE_CHARTS: set[str] = set()

CHART_NOTES = {
    "release_timeline.png": (
        "One dot per release, diamonds for prereleases. Repos with zero releases in the "
        "selected span aren't shown on the chart (see the table for those)."
    ),
}

CHART_METHODOLOGY = {
    "release_timeline.png": [
        "Fetch every published, non-draft release for each repo in the org (GitHub Releases only, no git-tag fallback).",
        "Filter to the selected span (Week / 1 month / 1 year / Last 18 months).",
        "Plot one point per release, sorted top-to-bottom by release count within that span.",
        "Label each row with its exact count instead of relying on dot density, which would distort under high cadence.",
    ],
}

SECTION_SPECS = [
    {
        "id": "release-staleness",
        "file": "release_repo_summary.csv",
        "title": "Release staleness by repo",
        "description": (
            "Every repo in the org, whether or not it has ever released — a repo with no "
            "releases still gets a row, ranked maximally stale, rather than being silently "
            "absent. See the glossary below for what 'staleness_ratio' and 'pace' mean."
        ),
        "columns": [
            ("repo", "repo"),
            ("latest_release", "latest release", "date"),
            ("days_since_last_release", "days since", "number"),
            ("median_gap_days", "typical gap (days)", "number"),
            ("staleness_ratio", "× overdue vs. own pace", "number"),
            ("staleness_bucket", "pace", "staleness"),
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
            "term": "Prereleases.",
            "definition": (
                "Shown in the timeline chart (diamond markers) — that's about release rhythm, "
                "and a release candidate is part of that rhythm. Excluded from 'latest release', "
                "'typical gap', and 'pace' in the table below: a repo cutting frequent RC tags "
                "without shipping a real release would otherwise read as on pace off that noise, "
                "not actual shipping health. A repo with only prereleases and no full release "
                "ever shows as never released."
            ),
        },
        {
            "term": "Staleness ratio and pace.",
            "definition": (
                "days since the last release, divided by that repo's own *median* gap between "
                "releases. A ratio above 1 means the repo is currently past its own typical pace; "
                "well below 1 means it's on schedule. This is *relative to the repo's own "
                "history*, not a fixed threshold — a repo with a naturally long cadence isn't "
                "penalized for having one. The 'pace' column is the same signal as a colored "
                "chip: on pace, watch (1-3x its typical gap), overdue (3x+), never released, or "
                "not enough history yet to judge."
            ),
        },
        {
            "term": "What this tab cannot tell you.",
            "definition": (
                "Most zero-release repos are docs/governance/meta repos that were never going to "
                "ship a GitHub Release, not neglected code — but the ranking treats every "
                "never-released repo as equally maximally stale, so the top of that ranking will "
                "usually be dominated by non-shipping repos rather than genuinely neglected "
                'ones. Read "never released" as exactly that, not automatically "urgent." '
                "Nothing here explains *why* a repo went quiet, either."
            ),
        },
    ],
}
