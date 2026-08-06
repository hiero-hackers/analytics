"""Governance — authority, coverage, and risk.

The risk-focused family: who holds which role, where coverage is thin or
quiet, and how the maintainer pipeline is developing. The team-shaped view
lives in the Teams & TSC family, and employer concentration in the
Organisation-diversity family. Pure data; see the package __init__ for
assembly.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec.glossary import GLOSSARY_NOTE, glossary_of

CHART_MACRO = {
    "name": "Governance",
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
            {
                "id": "role-networks",
                "title": "Role networks",
                "slideshow": True,
                "description": (
                    "Repositories linked by the people who hold each governance role — one slide per "
                    "tier, narrowing from maintainers (the most governance-relevant view) through "
                    "committers to triage. Each bubble is a repo sized by that role's active holders; "
                    "links mean shared holders (thicker = more). Colour = repository type. The "
                    "all-contributors view lives in the Contributors tab. Use Prev/Next; click to "
                    "enlarge."
                ),
                "files": [
                    ("Maintainers", "maintainer_network.png"),
                    ("Committers", "committer_network.png"),
                    ("Triage", "triage_network.png"),
                ],
            },
        ],
    },
}

# Each section: which CSV it reads and how to render it. Sections appear only when
# their CSV exists and is non-empty, so governance-only tables are simply absent
# for orgs without a governance config.
SECTION_SPECS = [
    {
        "id": "repoactivity",
        "file": "repo_activity_overview.csv",
        "periods": True,
        "title": "Repository activity — permission-holders by role",
        "description": (
            "One row per repo: how many maintainers, committers and triage hold it, how many "
            "are active in the selected period, and activity split by role. Sorted by activity "
            "within that period. 'actions' = PRs + reviews + merges + issues + labels, summed."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers", "number"),
            ("committers", "committers", "number"),
            ("triage", "triage", "number"),
            ("active_recent", "active", "number"),
            ("maintainer_actions_recent", "maint. actions", "number"),
            ("committer_actions_recent", "comm. actions", "number"),
            ("triage_actions_recent", "triage actions", "number"),
            ("actions_recent", "actions", "number"),
            ("last_active", "last active", "date"),
        ],
    },
    {
        "id": "understaffed",
        "file": "maintainer_coverage_risk.csv",
        "periods": True,
        "title": "Repos with one or fewer active maintainers",
        "description": (
            "Repos where at most one maintainer has been active in the selected period. 'maintainers' is "
            "the total on paper; 'committers' and 'triage' show others with access to the repo. Fewest "
            "active maintainers first."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers", "number"),
            ("active_maintainers", "active maintainers", "number"),
            ("committers", "committers", "number"),
            ("triage", "triage", "number"),
        ],
    },
    {
        "id": "loadshare",
        "file": "review_load_share.csv",
        "periods": True,
        "title": "Who carries the review load",
        "description": (
            "For each repo, the share of review+merge work in the selected period done by the single busiest "
            "person who can merge — committer or maintainer. 'top role' is whether the busiest is a "
            "committer or maintainer; 'top %' is their share, 'top-2 %' the top two combined. Highest "
            "concentration first; repos with under 20 recent review+merge actions are omitted."
        ),
        "columns": [
            ("repo", "repo"),
            ("top_carrier", "top carrier"),
            ("top_role", "top role"),
            ("top_pct", "top %", "number"),
            ("top2_pct", "top-2 %", "number"),
        ],
    },
    {
        "id": "repo",
        "file": "role_coverage_all.csv",
        "periods": True,
        "title": "Roles and recent activity by repo",
        "description": (
            "Type a repo to see its permission-holders and their contributions in this repo "
            "during the selected period, plus whether each has activity here in that period. "
            "Days since active always refers to the latest recorded activity."
        ),
        "columns": [
            ("repo", "repo"),
            ("user", "user"),
            ("granted_role", "role"),
            ("status", "status"),
            ("days_since_active", "days since active", "number"),
            ("prs_recent", "PRs", "number"),
            ("reviews_recent", "reviews", "number"),
            ("merges_recent", "merges", "number"),
            ("issues_recent", "issues", "number"),
            ("labels_recent", "labels", "number"),
        ],
    },
    {
        "id": "gonedark",
        "file": "role_coverage_globally_quiet.csv",
        "periods": True,
        "title": "Permission-holders with no recent activity",
        "description": (
            "Permission-holders with no recorded activity in any repo within the selected "
            "period; 'All time' lists those with no recorded activity at all. Useful for "
            "keeping access lists current. A blank 'days since active' means no recorded "
            "activity yet. The 'quiet permission-holders' KPI tile above stays at a fixed "
            "180-day threshold regardless of the tab."
        ),
        "columns": [
            ("user", "user"),
            ("highest_role", "highest role"),
            ("roles", "roles held"),
            ("repos_held", "repos", "number"),
            ("days_since_active", "days since active", "number"),
            ("last_active", "last active", "date"),
        ],
    },
]


# Tables grouped by purpose so viewers get a short, scannable menu instead of one
# long stack. Each group renders under its own heading (with a jump-bar link), and
# within a group the order goes high-level aggregate → most granular. Groups render
# after the charts. Order here is the on-screen order.
# This tab's "how to read this": role and activity columns only — the team and
# organisation-diversity vocabulary lives with those tabs.
GLOSSARY = glossary_of(
    (
        "contributor / account / member / user",
        "PRs",
        "reviews",
        "merges",
        "issues",
        "labels",
        "actions",
        "top carrier / top % / top role",
        "role / role here",
        "highest role",
        "roles held",
        "how roles are set",
        "maintainers / committers / triage",
        "active / members active",
        "status",
        "days since active",
        "last active",
        "repos",
        "period tabs",
    ),
    note=GLOSSARY_NOTE,
)

SECTION_GROUPS = [
    # The actionable headlines — where coverage is thin or work is concentrated.
    ("Coverage & risk", ["repoactivity", "understaffed", "loadshare", "gonedark"]),
    # Reference: who holds which role, per repo.
    ("Roles by repo", ["repo"]),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

# No governance chart currently needs the horizontal-scroll treatment.
WIDE_CHARTS: set[str] = set()

# "How to read this" notes, keyed by chart filename. These describe how to read the
# chart (its encoding and window) — never the current data values — so they stay
# accurate across every refresh. A chart with no entry here simply shows no note.
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
    "maintainer_network.png": "Each bubble is a repository, sized by how many maintainers are active in it; two repos are "
    "linked when they share a maintainer (thicker line = more shared). Bubble colour is the repo's "
    "category.",
    "committer_network.png": "Each bubble is a repository, sized by how many committers are active in it; two repos are "
    "linked when they share a committer (thicker line = more shared). Bubble colour is the repo's "
    "category.",
    "triage_network.png": "Each bubble is a repository, sized by how many triage-role holders are active in it; two repos "
    "are linked when they share a triage holder (thicker line = more shared). Bubble colour is the "
    "repo's category.",
}

# Step-by-step "how this was built" methodology, keyed by chart filename. Shown as
# an expandable list in the zoom (lightbox) view, under the short note. Like the
# notes these describe the method, never the current values, so they stay accurate.
# A chart with no entry simply shows no methodology block.
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
    "maintainer_network.png": [
        (
            "Resolve who holds the role in each repository from the governance config's team→permission "
            "grants (maintain/admin → maintainer, write → committer, triage → triage)."
        ),
        "Make each repository a node, sized by how many holders of that role it has.",
        (
            "Link two repositories when they share role-holders; thickness is how many they share. Edges "
            "use all holders, active or not, so shared ownership shows even where the group is quiet."
        ),
        ("Colour nodes by repository type, and thin links with a minimum-shared threshold so the graph stays legible."),
    ],
}

# The committer and triage networks are the same construction over a different
# role, so they share the maintainer network's steps rather than restating them.
CHART_METHODOLOGY["committer_network.png"] = CHART_METHODOLOGY["maintainer_network.png"]
CHART_METHODOLOGY["triage_network.png"] = CHART_METHODOLOGY["maintainer_network.png"]
