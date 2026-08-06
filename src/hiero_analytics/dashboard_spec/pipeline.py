"""Maintainer pipeline — the bench of future maintainers, over time and by repo.

The pipeline-shaped view of governance: one counting rule (distinct people per
role) rendered at four time resolutions and across repositories. A sub-tab of
the Governance umbrella. Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

# Renders as a sub-tab under the Governance umbrella tab.
MACRO_PARENT = "Governance"

CHART_MACRO = {
    "name": "Maintainer pipeline",
    "charts": {
        "hiero-ledger": [
            {
                "id": "maintainer-pipeline",
                "title": "Maintainer pipeline over time",
                "description": (
                    "How the maintainer/committer pipeline has moved over time — is the bench of "
                    "future maintainers developing? The same spans, per repository, are the next card."
                ),
                "files": [
                    (
                        "Unique active contributors by role",
                        [
                            # One rule at four resolutions, widest first.
                            # See analysis/maintainer_pipeline.py.
                            ("All time", "maintainer_pipeline_yearly.png"),
                            ("1 year", "maintainer_pipeline_monthly.png"),
                            ("1 month", "maintainer_pipeline_weekly.png"),
                            ("Week", "maintainer_pipeline_daily.png"),
                        ],
                    ),
                ],
            },
            {
                "id": "maintainer-pipeline-by-repo",
                "title": "Maintainer pipeline by repository",
                "description": (
                    "The same role split, cut by repository instead of time: who is active in each "
                    "repo over the selected span. Spans match the over-time card, so the two cards "
                    "answer 'when' and 'where' with one vocabulary."
                ),
                "files": [
                    (
                        "Active contributors by role and repository",
                        [
                            ("All time", "maintainer_pipeline_by_repo.png"),
                            ("1 year", "maintainer_pipeline_by_repo_365d.png"),
                            ("1 month", "maintainer_pipeline_by_repo_30d.png"),
                            ("Week", "maintainer_pipeline_by_repo_7d.png"),
                        ],
                    ),
                ],
            },
        ],
    },
}

WIDE_CHARTS: set[str] = set()

# This tab's "how to read this". Prose only; *asterisks* mark emphasis.
GLOSSARY = {
    "title": "How to read this tab — what the numbers mean",
    "layout": "notes",
    "terms": [
        {
            "term": "What is counted.",
            "definition": (
                "Distinct people with tracked activity (PRs, reviews, merges, issues, labels), each "
                "counted once per bucket under the *highest* governance role they hold in any repo — "
                "general → triage → committer → maintainer — so a busy person never inflates a tier."
            ),
        },
        {
            "term": "The spans.",
            "definition": (
                "The tabs zoom one rule through four resolutions: *All time* (per year), *1 year* "
                "(per month), *1 month* (per week), *Week* (per day). The by-repository card applies "
                "the same spans across repos instead of time; a person active in several repos counts "
                "in each there."
            ),
        },
        {
            "term": "Partial buckets.",
            "definition": (
                "The newest bucket is always in progress — the current year, month, week, or day is "
                "counted up to now, so its bar is expected to be lower."
            ),
        },
    ],
}

CHART_NOTES = {
    "maintainer_pipeline_yearly.png": "The widest view: one bar per calendar year, all the way back, counting everyone active at "
    "any point in that year. Each person is counted once, under the highest governance role they hold "
    "in any repo (general → triage → committer → maintainer), so a bar's total is the distinct people "
    "active. The narrower tabs beside it apply the same rule to shorter spans — this one is the whole "
    "history. Past bars never move; the current year is partial by definition.",
    "maintainer_pipeline_daily.png": "The narrowest view: the last seven days, one bar per day, same counting rule as the wider "
    "tabs. Useful for spotting whether a quiet week is quiet everywhere or just in one role; too "
    "short to read a trend from, which is what the 1 month and 1 year views are for. Today's bar "
    "covers activity so far today.",
    "maintainer_pipeline_monthly.png": "Each bar is a calendar month, counting the distinct people active that month — once each, under "
    "the highest governance role they hold in any repo (general → triage → committer → maintainer). "
    "Counts are strictly per-month (not a trailing window), so the current month is month-to-date. "
    "Only the most recent 12 months are charted — the '1 year' span; full history stays in the CSV.",
    "maintainer_pipeline_weekly.png": "Each bar is an ISO week (Mon–Sun), counting the distinct people active that week — once each, "
    "under the highest governance role they hold in any repo (general → triage → committer → "
    "maintainer). Counts are strictly per-week (not a trailing window), so the current week is "
    "week-to-date. Only the most recent 5 weeks are charted — the '1 month' span; full history stays in the CSV.",
    "maintainer_pipeline_by_repo.png": "Each bar is a repository, counting people active there over the selected span (the tabs match "
    "the over-time card: all time, 1 year, 1 month, week), grouped by the governance role they hold "
    "in that repo (general → triage → committer → maintainer). A person active in several repos is "
    "counted in each; smaller repos are pooled into 'Other Repos'.",
}

CHART_METHODOLOGY = {
    "maintainer_pipeline_yearly.png": [
        (
            "Take every tracked activity event (PRs opened, reviews, merges, issues, labels) and attach "
            "the governance role its actor held: maintainer, committer, triage, or general user."
        ),
        (
            "Bucket events by period (year, month, or week — the variant tabs) and count *distinct* "
            "people active in each role per bucket, so one very busy person does not inflate a tier."
        ),
        (
            "Stack the tiers to show whether the bench below maintainers is developing; the by-repo "
            "variant does the same across repositories instead of time."
        ),
        (
            "Membership in a bucket is whole-bucket: one tracked event anywhere in the year (or month, "
            "or week) counts. No recency window is applied here — that is what separates this view "
            "from the 'active at year end' variant, and from the per-repo activity tables, which use "
            "their own recent-activity window."
        ),
    ],
    "maintainer_pipeline_by_repo.png": [
        (
            "Take the same role-attached activity events as the over-time card, filtered to the "
            "selected span: everything, the last year, the last month, or the last week."
        ),
        (
            "Count distinct people per repository at the highest role they hold in that repo — a "
            "person active in several repos counts in each, so bars overlap deliberately."
        ),
        "Pool repositories below the display threshold into 'Other Repos' so the chart stays readable.",
    ],
}
