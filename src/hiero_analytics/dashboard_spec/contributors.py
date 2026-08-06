"""Contributors — the people and their activity.

The community-focused family: who contributes, how activity moves month to
month, and how repositories connect through shared people. Authority, coverage
risk, and employer concentration live in the governance family. Pure data; see
the package __init__ for assembly.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec.glossary import glossary_of

CHART_MACRO = {
    "name": "Contributors",
    "charts": {
        "hiero-ledger": [
            {
                "id": "contributor-network",
                "title": "Contributor network",
                "description": (
                    "The widest view of how work connects the ecosystem: each bubble is a repository "
                    "sized by its active contributors, and two repos are linked when they share "
                    "contributors (thicker = more). Colour = repository type. Per-role versions "
                    "(maintainers, committers, triage) live in the Governance tab. Click to enlarge."
                ),
                "files": [("Repositories linked by shared contributors", "all_network.png")],
            },
            {
                "id": "activity-heatmap",
                "title": "Activity heatmaps",
                "slideshow": True,
                "description": (
                    "Weighted monthly activity over the last six months (greener = more active). Slide "
                    "through the same activity zooming steadily out — from each individual contributor, "
                    "to their governance team, to their employer, and finally to the repositories the "
                    "work lands in. For employer concentration and authority risk, see the Governance tab."
                ),
                "files": [
                    ("By contributor", "contributor_activity_heatmap.png"),
                    ("By team", "team_activity_heatmap.png"),
                    ("By organisation", "org_activity_heatmap.png"),
                    ("By repository", "repo_activity_heatmap.png"),
                ],
            },
        ],
        "hiero-hackers": [
            {
                "id": "org-overview",
                "title": "Organization overview (org-wide)",
                "description": (
                    "Org-wide view of hiero-hackers: repositories ranked by contributor count, "
                    "the language mix across repos, and how many repos pushed in the last 30 days."
                ),
                "files": [
                    ("Top repositories by contributors", "contributor_counts.png"),
                    ("Programming languages", "language_distribution.png"),
                    ("Repository push activity (30d)", "push_activity.png"),
                ],
            },
            {
                "id": "contributor-network",
                "title": "Contributor network",
                "description": (
                    "Each bubble is a repository, sized by its active contributors; two repos are "
                    "linked when they share contributors. Colour = repository type. Click to enlarge."
                ),
                "files": [("Repositories linked by shared contributors", "all_network.png")],
            },
            {
                "id": "activity-heatmap",
                "title": "Contributor activity heatmap",
                "description": (
                    "Weighted monthly activity for the most active contributors over the last six "
                    "months (greener = more active that month)."
                ),
                "files": [("Activity heatmap", "contributor_activity_heatmap.png")],
            },
        ],
    },
}

# Each section: which CSV it reads and how to render it. Sections appear only when
# their CSV exists and is non-empty.
SECTION_SPECS = [
    {
        "id": "profiles",
        "file": "contributor_activity_profiles.csv",
        "periods": True,
        "title": "All contributors",
        "description": "Every contributor's org-wide activity in the selected period, most recently active first.",
        "columns": [
            ("contributor", "contributor"),
            ("prs_opened", "PRs", "number"),
            ("reviews_given", "reviews", "number"),
            ("merges_done", "merges", "number"),
            ("issues_opened", "issues", "number"),
            ("labels_applied", "labels", "number"),
            ("repos_touched", "repos", "number"),
            ("last_active", "last active"),
        ],
    },
]

# This tab's "how to read this": only the columns the contributor tables show.
GLOSSARY = glossary_of(
    (
        "contributor / account / member / user",
        "PRs",
        "reviews",
        "merges",
        "issues",
        "labels",
        "actions",
        "repos",
        "last active",
        "period tabs",
    ),
    note=(
        "Tabbed activity tables use the selected period; the all-time columns are cumulative. Tracked "
        "activities are opening PRs/issues, reviewing, merging, and labeling — comments and reactions "
        "are not counted."
    ),
)

SECTION_GROUPS = [
    # The full per-person list.
    ("All contributors", ["profiles"]),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

WIDE_CHARTS: set[str] = set()

# "How to read this" notes, keyed by chart filename. These describe how to read the
# chart (its encoding and window) — never the current data values — so they stay
# accurate across every refresh. A chart with no entry here simply shows no note.
CHART_NOTES = {
    "all_network.png": "Each bubble is a repository, sized by its active contributors; two repos are linked when they "
    "share contributors. Bubble colour is the repo's category; the link threshold scales with org size.",
    "contributor_activity_heatmap.png": "Rows are the 25 busiest contributors over the last six months; columns are those months. The "
    "colour and number in each cell are a weighted activity score (issues ×2, reviews ×3, PRs opened "
    "×3, merges ×2) for that month — greener = more active, redder = less. Bots are excluded.",
    "org_activity_heatmap.png": "Rows are organisations, columns are the last six months; each cell is that org's people's "
    "weighted activity that month (issues ×2, reviews ×3, PRs opened ×3, merges ×2) — greener = more "
    "active. It shows which employers carry the work over time, the activity counterpart to the "
    "head-count chart. Bots and contributors not mapped to an organisation are excluded.",
    "team_activity_heatmap.png": "Rows are governance teams, columns are the last six months; each cell is the weighted activity of "
    "the team's members that month (same weights as the other heatmaps). A contributor on several teams "
    "counts toward each, so team totals overlap — this measures each team's activity, not a partition. "
    "The 25 busiest teams are shown; bots are excluded.",
    "repo_activity_heatmap.png": "Rows are repositories, columns are the last six months; each cell is the repo's weighted activity "
    "that month (issues ×2, reviews ×3, PRs opened ×3, merges ×2) — greener = more active. Aggregated "
    "straight from the events, so each counts once. The 25 busiest repositories are shown; bots are "
    "excluded.",
    "contributor_counts.png": "The 20 repositories with the most distinct contributors over the last six months; bar height is "
    "the number of unique contributors.",
    "language_distribution.png": "How many repositories use each primary language (current snapshot). Repositories with no "
    "detected language are grouped as 'Unknown'.",
    "push_activity.png": "The share of repositories that received a push in the last 30 days (active) versus those that "
    "did not (inactive).",
}

# Step-by-step "how this was built" methodology, keyed by chart filename. Shown as
# an expandable list in the zoom (lightbox) view, under the short note. Like the
# notes these describe the method, never the current values, so they stay accurate.
# A chart with no entry simply shows no methodology block.
CHART_METHODOLOGY = {
    "all_network.png": [
        (
            "Take every tracked contributor activity (PRs opened, reviews, merges, issues, labels) and "
            "reduce it to which people were active in which repositories."
        ),
        "Make each repository a node, sized by how many contributors it has.",
        (
            "Link two repositories when they share contributors; the link's thickness is how many they "
            "share. Links use all contributors, active or not, so latent structure shows even in a quiet "
            "period."
        ),
        (
            "Thin the links with a minimum-shared threshold that scales with the number of repositories, "
            "so a dense organisation stays readable rather than becoming a hairball."
        ),
    ],
    "contributor_counts.png": [
        "Take the org-wide contributor activity records for the Hiero Hackers organisation.",
        "Count the distinct contributors active in each repository.",
        "Keep the top 20 repositories by that count.",
    ],
    "language_distribution.png": [
        "List the organisation's repositories and read GitHub's primary-language field for each.",
        (
            "Count repositories per language. This is GitHub's own per-repository classification — one "
            "language per repository, not a line-count breakdown."
        ),
    ],
    "push_activity.png": [
        "List the organisation's repositories with their last-push timestamp.",
        "Classify each repository by whether it received a push in the last 30 days.",
        "Count repositories in each state. Pushes are counted, not merged PRs.",
    ],
    "contributor_activity_heatmap.png": [
        (
            "Take every tracked event in the last six months — issues opened, PRs opened, reviews, merges — "
            "excluding bots."
        ),
        ("Weight each event (issues ×2, reviews ×3, PRs opened ×3, merges ×2) and bucket it by the month it happened."),
        "Sum the weighted score per contributor per month.",
        "Rank contributors by their six-month total and keep the top 25.",
        "Colour each cell by its monthly score (greener = more active).",
    ],
    "org_activity_heatmap.png": [
        "Start from the contributor activity matrix (weighted monthly scores, bots excluded).",
        "Map each contributor to an organisation via the affiliations file; drop those with no organisation.",
        "Sum the contributors' monthly scores within each organisation.",
        "Rank organisations by total and colour each cell by its monthly score.",
    ],
    "team_activity_heatmap.png": [
        "Start from the contributor activity matrix (weighted monthly scores, bots excluded).",
        "For each governance team, add up the monthly scores of its members.",
        (
            "A contributor on several teams counts toward each, so team totals overlap — this measures each "
            "team's activity, not a partition."
        ),
        "Rank teams by total, show the busiest 25, and colour each cell by its monthly score.",
    ],
    "repo_activity_heatmap.png": [
        "Take every tracked event in the last six months (bots excluded), keyed by the repository it occurred in.",
        "Weight each event (issues ×2, reviews ×3, PRs opened ×3, merges ×2) and bucket by month.",
        "Sum the weighted score per repository per month — each event counts once.",
        "Rank repositories by total, show the busiest 25, and colour each cell by its monthly score.",
    ],
}
