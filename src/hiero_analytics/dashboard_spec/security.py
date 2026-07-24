"""Security & scorecards — OpenSSF scores, CODEOWNERS and CI runners.

Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

CHART_MACRO = {
    "name": "Security & scorecards",
    "charts": {
        "hiero-ledger": [
            {
                "id": "scorecard",
                "title": "OpenSSF scorecard",
                "description": "Org-level OpenSSF scorecard and its per-check breakdown.",
                "files": [
                    ("Org scorecard", "org_scorecard.png"),
                    ("Score breakdown", "org_scorecard_breakdown.png"),
                ],
            },
            {
                "id": "ownership",
                "title": "Code owners & CI runners",
                "description": "CODEOWNERS coverage and the CI runners configured across repos.",
                "files": [
                    ("Code-owner coverage", "org_codeowner_summary.png"),
                    ("Code-owner coverage by repo", "org_codeowner_by_repo.png"),
                    ("Runners", "org_runner_chart.png"),
                ],
            },
        ],
    },
}

CHART_NOTES = {
    "org_scorecard.png": "Each repository's overall OpenSSF Scorecard score (0–10), a measure of security practices. "
    "Repositories without a published scorecard are omitted.",
    "org_scorecard_breakdown.png": "Each repository's OpenSSF score split into its individual checks (one colour per check, e.g. "
    "Code-Review, Branch-Protection), so you can see which practices contribute.",
    "org_codeowner_summary.png": "How many repositories have a CODEOWNERS file (Present) versus none (Missing).",
    "org_codeowner_by_repo.png": "CODEOWNERS file presence per repository. Teal indicates Present, while coral indicates Missing.",
    "org_runner_chart.png": "GitHub Actions runner usage per repository, stacked by type: self-hosted, standard "
    "(GitHub-hosted), or indeterminate (could not be classified).",
}

CHART_METHODOLOGY = {
    "org_codeowner_by_repo.png": [
        "Check each repository for the presence of a CODEOWNERS file in standard locations (root, .github/, or docs/).",
        "Represent presence/absence per repository as a stacked bar chart showing 100% compliance status (Present vs. Missing).",
    ],
}

WIDE_CHARTS: set[str] = set()
