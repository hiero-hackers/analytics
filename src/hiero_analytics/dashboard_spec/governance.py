"""Roles & coverage — authority, coverage, and risk.

The risk-focused family: who holds which role, where coverage is thin or
quiet, and how concentrated the work is. A sub-tab of the Governance umbrella,
next to the Maintainer-pipeline, Teams & TSC, and Organisation-diversity
families. Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec.glossary import GLOSSARY_NOTE, glossary_of

# Renders as a sub-tab under the Governance umbrella tab.
MACRO_PARENT = "Governance"

CHART_MACRO = {
    "name": "Roles & coverage",
    "charts": {
        "hiero-ledger": [
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
