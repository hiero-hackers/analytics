"""Issues & onboarding — difficulty mix and triage signals.

Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

# Shown when the selected org has no content for this tab.
ABSENT_NOTE = (
    "Nothing generated for this org yet: the issue-difficulty and onboarding "
    "pipelines are org-independent, so this fills in on the next full run."
)

CHART_MACRO = {
    "name": "Issues & onboarding",
    "charts": {
        # "*": org-independent — these cards render for any org whose pipelines
        # produced the files (missing variants drop out per org).
        "*": [
            {
                "id": "issue-difficulty",
                "group": "Issue difficulty",
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
                            # The shared span vocabulary, widest first, matching
                            # the chart tabs and tables everywhere else.
                            ("All time", "difficulty_by_repo.png"),
                            ("1 year", "difficulty_by_repo_365d.png"),
                            ("1 month", "difficulty_by_repo_30d.png"),
                            ("Week", "difficulty_by_repo_7d.png"),
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
    # Shared by all "By repo" span tabs (variants without their own note
    # inherit the first one).
    "difficulty_by_repo.png": "Open issues per repository, stacked by difficulty level. Each tab limits to issues labelled "
    "with a difficulty (or newly created) within its span; 'All time' is the whole open backlog and "
    "'Unknown' = open issues not yet triaged. Wider spans are the closest view of a repo's "
    "accumulated triage debt.",
    "difficulty_over_time_event_based_weekly.png": "Open difficulty-labelled issues over the last year, reconstructed from when difficulty labels "
    "were actually applied (label events). Each band is a difficulty level; the height is how many "
    "open issues sat at that difficulty on that date.",
    "difficulty_over_time_all_event_based_weekly.png": "Same series with the 'Unknown' band added: open issues with no difficulty label (or whose "
    "label application date isn't recoverable from events), counted from their creation date. Shows "
    "how the untriaged backlog moves relative to the triaged one.",
}

CHART_METHODOLOGY = {
    "difficulty_by_repo.png": [
        "Fetch every open issue across the organisation's repositories, with its labels.",
        (
            "Map each issue's labels to a difficulty level using the shared label vocabulary "
            "(domain/labels.py); an issue carrying no difficulty label becomes 'Unknown'."
        ),
        (
            "Keep only issues labelled with a difficulty — or newly created — within the selected span, "
            "so the narrower tabs reflect what triage has touched recently; 'All time' keeps the whole "
            "open backlog."
        ),
        "Count the remaining open issues per repository, stacked by difficulty level.",
    ],
    "difficulty_over_time_event_based_weekly.png": [
        (
            "Fetch the label timeline for every issue — each 'labeled' and 'unlabeled' event with its "
            "timestamp — rather than reading only the labels issues carry today."
        ),
        (
            "Replay those events week by week to reconstruct which difficulty each open issue held at each "
            "point in the past year."
        ),
        (
            "Count open issues at each difficulty for every week; a relabelled issue therefore changes "
            "history, because the chart reflects what was known then, not now."
        ),
    ],
}

WIDE_CHARTS: set[str] = set()

# This tab's "how to read this". Prose only; *asterisks* mark emphasis.
GLOSSARY = {
    "title": "How to read this tab — what the numbers mean",
    "layout": "notes",
    "terms": [
        {
            "term": "What is measured.",
            "definition": (
                "Open issues across the organisation's repositories, grouped by the difficulty label "
                "they carry. Issues are counted, never people — this tab says what work is waiting, not "
                "who is doing it."
            ),
        },
        {
            "term": "Difficulty levels.",
            "definition": (
                "Read from each issue's labels. *Unknown* is the important one: a recently opened or "
                "unlabelled issue nobody has triaged a difficulty onto yet. It is the onboarding signal "
                "on this tab, because repositories no longer rely on a good-first-issue-candidate label "
                "to surface approachable work."
            ),
        },
        {
            "term": "By repo (30 days).",
            "definition": (
                "Open issues per repository, stacked by difficulty, limited to issues labelled with a "
                "difficulty (or newly created) in the last 30 days — a snapshot of what triage has "
                "touched recently, not the whole backlog."
            ),
        },
        {
            "term": "Over time (weekly).",
            "definition": (
                "The last year reconstructed from *when difficulty labels were actually applied*, not "
                "from the labels issues carry today. Each band's height is how many open issues sat at "
                "that difficulty on that date, so relabelling an old issue moves history."
            ),
        },
        {
            "term": "What this tab cannot tell you.",
            "definition": (
                "An issue with no difficulty label is invisible to the difficulty split beyond counting "
                "as Unknown, and closed issues are out of scope entirely — this is a picture of the open "
                "queue, not of throughput."
            ),
        },
    ],
}
