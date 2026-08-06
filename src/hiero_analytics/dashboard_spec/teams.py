"""Teams & TSC — what the governance bodies are doing.

The team-shaped view of activity: each governance team's pulse, where each
team works, and the TSC members' own footprint. Split out of the Governance
tab so that tab can stay focused on roles and risk while this one answers
"what are our teams doing?". Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec.glossary import GLOSSARY_NOTE, glossary_of

# No chart galleries yet — the tab is table-led. The macro still names the tab.
CHART_MACRO = {
    "name": "Teams & TSC",
    "charts": {},
}

SECTION_SPECS = [
    {
        "id": "teams",
        "file": "team_activity_summary.csv",
        "periods": True,
        "title": "Team activity overview",
        "description": (
            "Each governance team's size, how many members have activity in the selected period, "
            "and its active or quiet status. Teams with no activity in that period are listed first."
        ),
        "columns": [
            ("team", "team"),
            ("members", "members"),
            ("active_members", "active"),
            ("status", "status"),
            ("days_since_active", "days since active"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
        ],
    },
    {
        "id": "teamrepo",
        "file": "team_activity_by_repo.csv",
        "periods": True,
        "title": "Team activity by repo",
        "description": (
            "Which repos each team is active in — type a team or repo to filter. This is a team-wide "
            "rollup (headcount + totals per repo); for a named maintainer's own by-repo activity, see "
            "the Governance tab's 'Roles and recent activity by repo' table, and for individual TSC "
            "members, see the TSC table below."
        ),
        "columns": [
            ("team", "team"),
            ("repo", "repo"),
            ("members_active", "members active"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "tscrepo",
        "file": "tsc_activity_by_repo.csv",
        "periods": True,
        "title": "TSC activity by repo",
        "description": "For TSC members with activity, which repos they work in and the role they hold there.",
        "columns": [
            ("account", "member"),
            ("repo", "repo"),
            ("repo_role", "role here"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("last_active", "last active"),
        ],
    },
]

# This tab's "how to read this": team and activity vocabulary only.
GLOSSARY = glossary_of(
    (
        "contributor / account / member / user",
        "PRs",
        "reviews",
        "merges",
        "issues",
        "labels",
        "members",
        "active / members active",
        "org-wide teams",
        "role / role here",
        "status",
        "days since active",
        "last active",
        "period tabs",
    ),
    note=GLOSSARY_NOTE,
)

SECTION_GROUPS = [
    # The teams as bodies first, then the TSC members individually.
    ("Teams", ["teams", "teamrepo"]),
    ("TSC", ["tscrepo"]),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

WIDE_CHARTS: set[str] = set()
CHART_NOTES: dict[str, str] = {}
CHART_METHODOLOGY: dict[str, list] = {}
