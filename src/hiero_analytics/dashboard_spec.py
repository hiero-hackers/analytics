"""Declarative spec for the dashboard — which macros, charts and table sections.

Pure data consumed by ``run_dashboard``. Keeping it separate from the assembly
logic makes it easy to add a chart, reorder a table group, or wire in another
org without touching the rendering code.
"""

from __future__ import annotations

# The dashboard is organized as macro (family) → org → section. Today there is a
# single macro built from SECTION_SPECS below; a future dashboard family (e.g.
# onboarding, scorecards) becomes a new macro: build its ``org_tabs`` the same way
# and append ``{"name": ..., "org_tabs": [...]}`` to ``macros`` in main(). The macro
# tab bar appears automatically once there is more than one.
MACRO_NAME = "Contributors & governance"

# Chart families. Each macro lists, per org, image sections built from PNGs under
# outputs/charts/org/<org>/. The first macro's name matches MACRO_NAME, so its
# charts are appended to that macro's existing data tables; the rest become new
# chart-only macro tabs. Missing files are skipped, so a section/macro/tab only
# appears when its charts exist. Org-level charts only (per-repo charts excluded).
CHART_MACROS = [
    {
        "name": MACRO_NAME,
        "charts": {
            "hiero-ledger": [
                {
                    "id": "maintainer-pipeline",
                    "title": "Maintainer pipeline",
                    "description": "How the maintainer/committer pipeline has moved over time and across repos.",
                    "files": [
                        ("By year", "maintainer_pipeline_yearly.png"),
                        ("By repo", "maintainer_pipeline_by_repo.png"),
                    ],
                },
                {
                    "id": "role-networks",
                    "title": "Activity networks by role",
                    "slideshow": True,
                    "description": (
                        "Repositories linked by the people they share, one slide per group "
                        "(maintainers, committers, triage, general contributors, and all contributors). "
                        "Each bubble is a repo sized by that group's active members; links mean shared "
                        "members (thicker = more). Colour = repository type. Use Prev/Next; click to enlarge."
                    ),
                    "files": [
                        ("Maintainers", "maintainer_network.png"),
                        ("Committers", "committer_network.png"),
                        ("Triage", "triage_network.png"),
                        ("General contributors", "general_network.png"),
                        ("All contributors", "all_network.png"),
                    ],
                },
                {
                    "id": "activity-heatmap",
                    "title": "Contributor activity heatmap",
                    "description": (
                        "Weighted monthly activity for the most active contributors over the last six "
                        "months (greener = more active that month). This is the ranked, score-based view "
                        "that complements the networks and the profile tables."
                    ),
                    "files": [("Activity heatmap", "contributor_activity_heatmap.png")],
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
    },
    {
        "name": "Issues & onboarding",
        "charts": {
            "hiero-ledger": [
                {
                    "id": "good-first-issues",
                    "title": "Good first issues",
                    "description": "Good-first-issue (and good-first-issue-candidate) pipeline and history.",
                    "files": [
                        ("GFI pipeline", "gfi_pipeline.png"),
                        ("GFI state by year", "gfi_yearly_state_line.png"),
                        ("GFI + GFIC by repo", "total_gfi_gfic_by_repo.png"),
                    ],
                },
                {
                    "id": "issue-difficulty",
                    "title": "Issue difficulty",
                    "description": "Difficulty mix of open issues and how it has shifted over time.",
                    "files": [
                        ("By repo (30d)", "difficulty_by_repo_30_days.png"),
                        ("Distribution incl. unknown (30d)", "difficulty_distribution_with_unknown_30_days.png"),
                        ("Distribution excl. unknown (30d)", "difficulty_distribution_without_unknown_30_days.png"),
                        ("Over time (weekly)", "difficulty_over_time_event_based_weekly.png"),
                    ],
                },
            ],
        },
    },
    {
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
                        ("Runners", "org_runner_chart.png"),
                    ],
                },
            ],
        },
    },
    {
        "name": "Community",
        "charts": {
            "hiero-ledger": [
                {
                    "id": "discord",
                    "title": "Discord activity",
                    "description": "Discord channel categories, monthly traffic, and recent activity.",
                    "files": [
                        ("Channel categories", "hiero_discord_channel_categories.png"),
                        ("Monthly traffic", "hiero_discord_monthly_traffic.png"),
                        ("Recent activity (30d)", "hiero_discord_recent_activity_30d.png"),
                    ],
                },
            ],
        },
    },
]

# Each section: which CSV it reads and how to render it. Sections appear only when
# their CSV exists and is non-empty, so governance-only tables (role coverage,
# teams) are simply absent for orgs without a governance config.
SECTION_SPECS = [
    {
        "id": "profiles",
        "file": "contributor_activity_profiles.csv",
        "title": "All contributors",
        "description": "Every contributor's org-wide activity (all-time), most recently active first.",
        "columns": [
            ("contributor", "contributor"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("repos_touched", "repos"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "repoactivity",
        "file": "repo_activity_overview.csv",
        "title": "Repository activity — permission-holders by role",
        "description": (
            "One row per repo: how many maintainers, committers and triage hold it, how many "
            "are active in the last 90 days, and recent activity split by role. Sorted by recent "
            "activity (most active first). 'actions' = PRs + reviews + merges + issues + labels, "
            "summed; '90d' columns are the last 90 days, 'all-time' is cumulative."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers"),
            ("committers", "committers"),
            ("triage", "triage"),
            ("active_recent", "active 90d"),
            ("maintainer_actions_recent", "maint. actions 90d"),
            ("committer_actions_recent", "comm. actions 90d"),
            ("triage_actions_recent", "triage actions 90d"),
            ("actions_recent", "actions 90d"),
            ("actions_all_time", "actions all-time"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "understaffed",
        "file": "maintainer_coverage_risk.csv",
        "title": "Repos with one or fewer active maintainers",
        "description": (
            "Repos where at most one maintainer has been active in the last 90 days. 'maintainers' is "
            "the total on paper; 'committers' and 'triage' show others with access to the repo. Fewest "
            "active maintainers first."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers"),
            ("active_maintainers", "active maintainers"),
            ("committers", "committers"),
            ("triage", "triage"),
        ],
    },
    {
        "id": "loadshare",
        "file": "review_load_share.csv",
        "title": "Who carries the review load",
        "description": (
            "For each repo, the share of review+merge work (last 90 days) done by the single busiest "
            "person who can merge — committer or maintainer. 'mergers' is how many reviewed/merged; "
            "'top role' is whether the busiest is a committer or maintainer; 'top %' is their share, "
            "'top-2 %' the top two combined. Highest concentration first; repos with under 20 recent "
            "review+merge actions are omitted."
        ),
        "columns": [
            ("repo", "repo"),
            ("mergers", "mergers"),
            ("load_recent", "review+merge 90d"),
            ("top_carrier", "top carrier"),
            ("top_role", "top role"),
            ("top_pct", "top %"),
            ("top2_pct", "top-2 %"),
        ],
    },
    {
        "id": "account",
        "file": "maintainer_activity_by_repo.csv",
        "title": "Maintainer activity by repo (all-time)",
        "description": "Type a name to see which repos a maintainer works in and the role they hold there.",
        "columns": [
            ("account", "account"),
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
    {
        "id": "repo",
        "file": "role_coverage_all.csv",
        "title": "Roles and recent activity by repo",
        "description": (
            "Type a repo to see its permission-holders and their contributions in this repo "
            "— both all-time and over the last 90 days (the '90d' columns) — plus whether "
            "each has recent activity here. Status counts a holder 'active' with any activity "
            "in the last 90 days."
        ),
        "columns": [
            ("repo", "repo"),
            ("user", "user"),
            ("granted_role", "role"),
            ("status", "status"),
            ("days_since_active", "days since active"),
            ("prs_opened", "PRs"),
            ("reviews_given", "reviews"),
            ("merges_done", "merges"),
            ("issues_opened", "issues"),
            ("labels_applied", "labels"),
            ("prs_recent", "PRs 90d"),
            ("reviews_recent", "reviews 90d"),
            ("merges_recent", "merges 90d"),
            ("issues_recent", "issues 90d"),
            ("labels_recent", "labels 90d"),
        ],
    },
    {
        "id": "gonedark",
        "file": "role_coverage_globally_quiet.csv",
        "title": "Permission-holders with no recent activity (180+ days)",
        "description": (
            "Permission-holders with no recorded activity in any repo in the last 180 days. "
            "Useful for keeping access lists current. A blank 'days since active' means no "
            "recorded activity yet."
        ),
        "columns": [
            ("user", "user"),
            ("highest_role", "highest role"),
            ("roles", "roles held"),
            ("repos_held", "repos"),
            ("days_since_active", "days since active"),
            ("last_active", "last active"),
        ],
    },
    {
        "id": "tscrepo",
        "file": "tsc_activity_by_repo.csv",
        "title": "TSC activity by repo (all-time)",
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
    {
        "id": "teams",
        "file": "team_activity_summary.csv",
        "title": "Team activity overview",
        "description": (
            "Each governance team's size, how many members have recent activity, and the "
            "team's recent-activity status (180-day window). Teams with no recent activity "
            "are listed first."
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
        "title": "Team activity by repo (all-time)",
        "description": "Which repos each team is active in — type a team or repo to filter.",
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
]


# Tables grouped by purpose so viewers get a short, scannable menu instead of one
# long stack. Each group renders under its own heading (with a jump-bar link), and
# within a group the order goes high-level aggregate → most granular. Groups render
# after the charts. Order here is the on-screen order.
SECTION_GROUPS = [
    # The actionable headlines — where coverage is thin or work is concentrated.
    ("Coverage & risk", ["repoactivity", "understaffed", "loadshare", "gonedark"]),
    # Reference: who holds which role, per repo and per team.
    ("Roles & teams", ["repo", "account", "tscrepo", "teams", "teamrepo"]),
    # The full per-person list.
    ("All contributors", ["profiles"]),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}
CHARTS_GROUP = "Charts"

# "How to read this" notes, keyed by chart filename. These describe how to read the
# chart (its encoding and window) — never the current data values — so they stay
# accurate across every refresh. A chart with no entry here simply shows no note.
CHART_NOTES = {
    "maintainer_pipeline_yearly.png": (
        "Each bar is a calendar year, counting people active in its last six months (a fixed Jul–Dec "
        "window for past years, so old bars stay put; a trailing six-month window for the current year). "
        "Each person is counted once, under the highest governance role they hold in any repo "
        "(general → triage → committer → maintainer), so the bar's total is the distinct people active."
    ),
    "maintainer_pipeline_by_repo.png": (
        "Each bar is a repository, counting people active there in the last six months, grouped by the "
        "governance role they hold in that repo (general → triage → committer → maintainer). A person "
        "active in several repos is counted in each; smaller repos are pooled into 'Other Repos'."
    ),
    "maintainer_network.png": (
        "Each bubble is a repository, sized by how many maintainers are active in it; two repos are "
        "linked when they share a maintainer (thicker line = more shared). Bubble colour is the repo's "
        "category."
    ),
    "committer_network.png": (
        "Each bubble is a repository, sized by its active committers; two repos are linked when they "
        "share at least two committers (thicker line = more shared). Bubble colour is the repo's category."
    ),
    "triage_network.png": (
        "Each bubble is a repository, sized by its active triage members; two repos are linked when they "
        "share a triage member (thicker line = more shared). Bubble colour is the repo's category."
    ),
    "general_network.png": (
        "Each bubble is a repository, sized by its general contributors (people with no governance role); "
        "two repos are linked when they share at least four of them. Bubble colour is the repo's category."
    ),
    "all_network.png": (
        "Each bubble is a repository, sized by its active contributors; two repos are linked when they "
        "share contributors. Bubble colour is the repo's category; the link threshold scales with org size."
    ),
    "contributor_activity_heatmap.png": (
        "Rows are the 25 busiest contributors over the last six months; columns are those months. The "
        "colour and number in each cell are a weighted activity score (issues ×2, reviews ×3, PRs opened "
        "×3, merges ×2) for that month — greener = more active, redder = less. Bots are excluded."
    ),
    "contributor_counts.png": (
        "The 20 repositories with the most distinct contributors over the last six months; bar height is "
        "the number of unique contributors."
    ),
    "language_distribution.png": (
        "How many repositories use each primary language (current snapshot). Repositories with no "
        "detected language are grouped as 'Unknown'."
    ),
    "push_activity.png": (
        "The share of repositories that received a push in the last 30 days (active) versus those that "
        "did not (inactive)."
    ),
    "gfi_pipeline.png": (
        "Good-first-issue pipeline by year: each bar stacks candidate issues (flagged as potential "
        "good-first-issues) and approved good-first-issues, counted by the year they were created."
    ),
    "gfi_yearly_state_line.png": (
        "Good-first-issues per year — one line per issue state (e.g. open, closed) plus a total line. "
        "Each point is the count for that year."
    ),
    "total_gfi_gfic_by_repo.png": (
        "The total good-first-issue pool per repository (all-time): each bar stacks approved "
        "good-first-issues and candidate issues."
    ),
    "difficulty_by_repo_30_days.png": (
        "Open issues per repository, stacked by difficulty level. Limited to issues labelled with a "
        "difficulty (or newly created) in the last 30 days; 'Unknown' = recent open issues not yet triaged."
    ),
    "difficulty_distribution_with_unknown_30_days.png": (
        "The same last-30-days open issues taken as a whole and split by difficulty level, including "
        "untriaged ('Unknown') issues."
    ),
    "difficulty_distribution_without_unknown_30_days.png": (
        "Open issues from the last 30 days by difficulty, excluding untriaged ('Unknown') ones — the mix "
        "among issues that already have a difficulty label."
    ),
    "difficulty_over_time_event_based_weekly.png": (
        "Open issues by difficulty over the last year, reconstructed from when difficulty labels were "
        "actually applied (label events). Each band is a difficulty level; the height is how many open "
        "issues sat at that difficulty on that date."
    ),
    "org_scorecard.png": (
        "Each repository's overall OpenSSF Scorecard score (0–10), a measure of security practices. "
        "Repositories without a published scorecard are omitted."
    ),
    "org_scorecard_breakdown.png": (
        "Each repository's OpenSSF score split into its individual checks (one colour per check, e.g. "
        "Code-Review, Branch-Protection), so you can see which practices contribute."
    ),
    "org_codeowner_summary.png": (
        "How many repositories have a CODEOWNERS file (Present) versus none (Missing)."
    ),
    "org_runner_chart.png": (
        "GitHub Actions runner usage per repository, stacked by type: self-hosted, standard "
        "(GitHub-hosted), or indeterminate (could not be classified)."
    ),
    "hiero_discord_channel_categories.png": (
        "Discord message volume grouped by topic area, split into the last 90 days versus earlier history. "
        "From a manual Discord export (counts are as of the export date)."
    ),
    "hiero_discord_monthly_traffic.png": (
        "Total Discord messages per month across the export's date range."
    ),
    "hiero_discord_recent_activity_30d.png": (
        "The five Discord channels with the most messages in the last 30 days (relative to the export "
        "snapshot date)."
    ),
}
