"""Issues & onboarding — difficulty mix and triage signals.

Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

CHART_MACRO = {
    "name": "Issues & onboarding",
    "charts": {
        "hiero-ledger": [
            {
                "id": "issue-difficulty",
                "title": "Issue difficulty",
                "description": (
                    "Difficulty mix of open issues and how it has shifted over time. 'Unknown' is the "
                    "primary onboarding/triage signal here — recently opened or unlabelled issues that "
                    "haven't been triaged with a difficulty yet, since repos no longer rely on a "
                    "good-first-issue-candidate label to surface onboarding-friendly work."
                ),
                "files": [
                    (
                        "By repo",
                        [
                            ("30 days", "difficulty_by_repo_30_days.png"),
                            ("90 days", "difficulty_by_repo_90_days.png"),
                            ("1 year", "difficulty_by_repo_365_days.png"),
                        ],
                    ),
                    (
                        "Over time (weekly)",
                        [
                            ("All issues", "difficulty_over_time_all_event_based_weekly.png"),
                            ("Labelled", "difficulty_over_time_event_based_weekly.png"),
                        ],
                    ),
                ],
            },
        ],
    },
}

CHART_NOTES = {
    # Shared by all "By repo" window tabs (variants without their own note
    # inherit the first one).
    "difficulty_by_repo_30_days.png": "Open issues per repository, stacked by difficulty level. Each tab limits to issues labelled "
    "with a difficulty (or newly created) within its window; 'Unknown' = open issues not yet "
    "triaged. Wider windows are the closest view of a repo's accumulated triage debt.",
    "difficulty_over_time_event_based_weekly.png": "Open difficulty-labelled issues over the last year, reconstructed from when difficulty labels "
    "were actually applied (label events). Each band is a difficulty level; the height is how many "
    "open issues sat at that difficulty on that date.",
    "difficulty_over_time_all_event_based_weekly.png": "Same series with the 'Unknown' band added: open issues with no difficulty label (or whose "
    "label application date isn't recoverable from events), counted from their creation date. Shows "
    "how the untriaged backlog moves relative to the triaged one.",
}

CHART_METHODOLOGY = {}

WIDE_CHARTS: set[str] = set()
