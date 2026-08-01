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
                    ("By repo (30d)", "difficulty_by_repo_30_days.png"),
                    ("Over time (weekly)", "difficulty_over_time_event_based_weekly.png"),
                    ("Over time, all issues (weekly)", "difficulty_over_time_all_event_based_weekly.png"),
                ],
            },
        ],
    },
}

CHART_NOTES = {
    "difficulty_by_repo_30_days.png": "Open issues per repository, stacked by difficulty level. Limited to issues labelled with a "
    "difficulty (or newly created) in the last 30 days; 'Unknown' = recent open issues not yet triaged.",
    "difficulty_over_time_event_based_weekly.png": "Open difficulty-labelled issues over the last year, reconstructed from when difficulty labels "
    "were actually applied (label events). Each band is a difficulty level; the height is how many "
    "open issues sat at that difficulty on that date.",
    "difficulty_over_time_all_event_based_weekly.png": "Same series with the 'Unknown' band added: open issues with no difficulty label (or whose "
    "label application date isn't recoverable from events), counted from their creation date. Shows "
    "how the untriaged backlog moves relative to the triaged one.",
}

CHART_METHODOLOGY = {}

WIDE_CHARTS: set[str] = set()
