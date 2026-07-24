"""Contributors & governance — the primary dashboard family.

Owns the table sections (and their grouping) as well as its chart macro,
notes and methodology. Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

# "Suggest a correction" target for the affiliations reference table — the analytics
# repo's issues page. The affiliations map is the source of truth, so a correction is
# either a one-line edit to data/affiliations.yaml (append '# manual') or a new issue here.
AFFILIATION_ISSUE_URL = "https://github.com/hiero-hackers/analytics/issues"

# The dashboard is organized as macro (family) → org → section. Today there is a
# single macro built from SECTION_SPECS below; a future dashboard family (e.g.
# onboarding, scorecards) becomes a new macro: build its ``org_tabs`` the same way
# and append ``{"name": ..., "org_tabs": [...]}`` to ``macros`` in main(). The macro
# tab bar appears automatically once there is more than one.
MACRO_NAME = "Contributors & governance"

# This family's chart sections, per org (see CHART_MACROS in the package
# __init__ for how families are assembled and ordered).
CHART_MACRO = {
    "name": MACRO_NAME,
    "charts": {
        "hiero-ledger": [
            {
                "id": "maintainer-pipeline",
                "title": "Maintainer pipeline",
                "description": "How the maintainer/committer pipeline has moved over time and across repos.",
                # One chart, four views: a tab switcher (By year / month / week / repo)
                # shows a single chart at a time instead of stacking all four.
                "files": [
                    (
                        "Unique active contributors by role",
                        [
                            ("By year", "maintainer_pipeline_yearly.png"),
                            ("By month", "maintainer_pipeline_monthly.png"),
                            ("By week", "maintainer_pipeline_weekly.png"),
                            ("By repo", "maintainer_pipeline_by_repo.png"),
                        ],
                    ),
                ],
            },
            {
                "id": "role-networks",
                "title": "Activity networks by role",
                "slideshow": True,
                "description": (
                    "Repositories linked by the people they share, one slide per group (maintainers, "
                    "the smallest and most governance-relevant group, and all contributors, the widest "
                    "view). Each bubble is a repo sized by that group's active members; links mean "
                    "shared members (thicker = more). Colour = repository type. Use Prev/Next; click to "
                    "enlarge."
                ),
                "files": [
                    ("Maintainers", "maintainer_network.png"),
                    ("All contributors", "all_network.png"),
                ],
            },
            {
                "id": "activity-heatmap",
                "title": "Activity heatmaps",
                "slideshow": True,
                "description": (
                    "Weighted monthly activity over the last six months (greener = more active). Slide "
                    "through the same activity zooming steadily out — from each individual contributor, "
                    "to their governance team, to their employer, and finally to the repositories the "
                    "work lands in."
                ),
                "files": [
                    ("By contributor", "contributor_activity_heatmap.png"),
                    ("By team", "team_activity_heatmap.png"),
                    ("By organisation", "org_activity_heatmap.png"),
                    ("By repository", "repo_activity_heatmap.png"),
                ],
            },
            {
                "id": "org-diversity",
                "title": "Organisation diversity",
                "description": (
                    "Where maintainer authority sits — org-wide, per team and per repo. The first chart is "
                    "the ecosystem-wide split of maintainers by employer (solo contributors pooled as "
                    "'Independent'); the next two count the governance teams and the repositories that a "
                    "single employer solely controls (an organisational bus-factor); the last two break "
                    "down each repository's and each team's maintainer mix. See the affiliations and "
                    "repo-diversity tables for the underlying detail."
                ),
                # Each chart offers an All / Active (last 90 days) tab so the roster
                # and the day-to-day active core can be compared in place.
                # The compact charts share the top rows; the two wide
                # composition charts then stack full-width, one row each.
                "files": [
                    (
                        "Maintainers by organisation",
                        [
                            ("All", "affiliation_donut.png"),
                            ("Active 90d", "affiliation_donut_active.png"),
                        ],
                    ),
                    (
                        "Single-employer teams by org",
                        [
                            ("All", "single_employer_teams_by_org.png"),
                            ("Active 90d", "single_employer_teams_by_org_active.png"),
                        ],
                    ),
                    (
                        "Single-employer repos by org",
                        [
                            ("All", "single_employer_repos_by_org.png"),
                            ("Active 90d", "single_employer_repos_by_org_active.png"),
                        ],
                    ),
                    (
                        "Organisation mix by repo",
                        [
                            ("All", "repo_affiliation_composition.png"),
                            ("Active 90d", "repo_affiliation_composition_active.png"),
                        ],
                    ),
                    (
                        "Organisation mix by team",
                        [
                            ("All", "team_affiliation_composition.png"),
                            ("Active 90d", "team_affiliation_composition_active.png"),
                        ],
                    ),
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
# their CSV exists and is non-empty, so governance-only tables (role coverage,
# teams) are simply absent for orgs without a governance config.
SECTION_SPECS = [
    {
        "id": "profiles",
        "file": "contributor_activity_profiles.csv",
        "periods": True,
        "title": "All contributors",
        "description": "Every contributor's org-wide activity in the selected period, most recently active first.",
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
        "periods": True,
        "title": "Repository activity — permission-holders by role",
        "description": (
            "One row per repo: how many maintainers, committers and triage hold it, how many "
            "are active in the selected period, and activity split by role. Sorted by activity "
            "within that period. 'actions' = PRs + reviews + merges + issues + labels, summed."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers"),
            ("committers", "committers"),
            ("triage", "triage"),
            ("active_recent", "active"),
            ("maintainer_actions_recent", "maint. actions"),
            ("committer_actions_recent", "comm. actions"),
            ("triage_actions_recent", "triage actions"),
            ("actions_recent", "actions"),
            ("last_active", "last active"),
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
            ("maintainers", "maintainers"),
            ("active_maintainers", "active maintainers"),
            ("committers", "committers"),
            ("triage", "triage"),
        ],
    },
    {
        "id": "loadshare",
        "file": "review_load_share.csv",
        "periods": True,
        "title": "Who carries the review load",
        "description": (
            "For each repo, the share of review+merge work in the selected period done by the single busiest "
            "person who can merge — committer or maintainer. 'mergers' is how many reviewed/merged; "
            "'top role' is whether the busiest is a committer or maintainer; 'top %' is their share, "
            "'top-2 %' the top two combined. Highest concentration first; repos with under 20 recent "
            "review+merge actions are omitted."
        ),
        "columns": [
            ("repo", "repo"),
            ("mergers", "mergers"),
            ("load_recent", "review+merge"),
            ("top_carrier", "top carrier"),
            ("top_role", "top role"),
            ("top_pct", "top %"),
            ("top2_pct", "top-2 %"),
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
            ("days_since_active", "days since active"),
            ("prs_recent", "PRs"),
            ("reviews_recent", "reviews"),
            ("merges_recent", "merges"),
            ("issues_recent", "issues"),
            ("labels_recent", "labels"),
        ],
    },
    {
        "id": "affiliations",
        "file": "maintainer_affiliations.csv",
        "title": "Maintainer affiliations — reference",
        "description": (
            "Reference: each maintainer, the organisation they were mapped to, and how it was decided — "
            "'automated' (the resolver placed them from public signals) or 'manual' (a hand-correction). "
            "Status is 'affiliated' (named employer), 'independent' (solo / personal-email only), or "
            "'unknown' (no public signal). To fix a mapping or resolve an unknown, edit its row in "
            "data/affiliations.yaml and append '# manual: reason' (it then survives regeneration and reads "
            "'manual' here), or use 'Suggest a correction' to open an issue on the analytics repo."
        ),
        "action_url": AFFILIATION_ISSUE_URL,
        "action_label": "Suggest a correction",
        "columns": [
            ("login", "maintainer"),
            ("organisation", "organisation"),
            ("status", "status"),
            ("method", "method"),
        ],
    },
    {
        "id": "repodiversity",
        "file": "repo_affiliation_diversity.csv",
        "title": "Maintainer organisation diversity by repo",
        "description": (
            "Per repo: how many maintainers it has, how many distinct employers they span, the largest "
            "employer and its share of resolved (mapped) maintainers — the same definition as the team "
            "table — and the independent / unknown counts. Repos where one employer holds every maintainer "
            "seat ('distinct orgs' = 1) are an organisational bus-factor. Single-employer repos first."
        ),
        "columns": [
            ("repo", "repo"),
            ("maintainers", "maintainers"),
            ("distinct_orgs", "distinct orgs"),
            ("top_org", "largest org"),
            ("top_org_pct", "largest org %"),
            ("independent", "independent"),
            ("unknown", "unknown"),
            ("organisations", "organisations"),
        ],
    },
    {
        "id": "teamdiversity",
        "file": "team_affiliation_diversity.csv",
        "title": "Team organisation concentration",
        "description": (
            "Per governance team: how many members resolve to an employer, how many distinct employers "
            "they span, the largest employer and its share, and the concentration (HHI, 10000 = one "
            "employer). 'single employer' = one employer holds every resolved seat — a capture / "
            "bus-factor risk, most serious for admin, release, security, and maintainer teams; teams with "
            "more unmapped than resolved members are never flagged. 'unknown' "
            "is how many members aren't in the affiliations map (mostly non-maintainers), so read a flag "
            "on a mostly-unknown team with caution. Most concentrated first."
        ),
        "columns": [
            ("team", "team"),
            ("members", "members"),
            ("resolved", "resolved"),
            ("distinct_orgs", "distinct orgs"),
            ("top_org", "largest org"),
            ("top_org_pct", "largest org %"),
            ("hhi", "HHI"),
            ("unknown", "unknown"),
            ("single_employer", "single employer"),
            ("organisations", "organisation mix"),
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
        "title": "Team activity by repo (all-time)",
        "description": (
            "Which repos each team is active in — type a team or repo to filter. This is a team-wide "
            "rollup (headcount + totals per repo); for a named maintainer's own by-repo activity, see the "
            "'Roles and recent activity by repo' table, and for individual TSC members, see the TSC table."
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
]


# Tables grouped by purpose so viewers get a short, scannable menu instead of one
# long stack. Each group renders under its own heading (with a jump-bar link), and
# within a group the order goes high-level aggregate → most granular. Groups render
# after the charts. Order here is the on-screen order.
SECTION_GROUPS = [
    # The actionable headlines — where coverage is thin or work is concentrated.
    ("Coverage & risk", ["repoactivity", "understaffed", "loadshare", "gonedark"]),
    # Who is affiliated with which organisation, and how concentrated that is — the
    # table companions to the Organisation-diversity charts.
    ("Organisation diversity", ["affiliations", "repodiversity", "teamdiversity"]),
    # Reference: who holds which role, per repo and per team.
    ("Roles & teams", ["repo", "tscrepo", "teams", "teamrepo"]),
    # The full per-person list.
    ("All contributors", ["profiles"]),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

# Wide charts (vertical bars across many items): the dashboard scrolls these
# horizontally at a readable height instead of squashing them to the card width.
WIDE_CHARTS = {
    "repo_affiliation_composition.png",
    "repo_affiliation_composition_active.png",
    "team_affiliation_composition.png",
    "team_affiliation_composition_active.png",
}

# "How to read this" notes, keyed by chart filename. These describe how to read the
# chart (its encoding and window) — never the current data values — so they stay
# accurate across every refresh. A chart with no entry here simply shows no note.
CHART_NOTES = {
    "maintainer_pipeline_yearly.png": "Each bar is a calendar year, counting people active in its last six months (a fixed Jul–Dec "
    "window for past years, so old bars stay put; a trailing six-month window for the current year). "
    "Each person is counted once, under the highest governance role they hold in any repo "
    "(general → triage → committer → maintainer), so the bar's total is the distinct people active.",
    "maintainer_pipeline_monthly.png": "Each bar is a calendar month, counting the distinct people active that month — once each, under "
    "the highest governance role they hold in any repo (general → triage → committer → maintainer). "
    "Counts are strictly per-month (not a trailing window), so the current month is month-to-date. "
    "Only the most recent 24 months are charted; full history stays in the CSV.",
    "maintainer_pipeline_weekly.png": "Each bar is an ISO week (Mon–Sun), counting the distinct people active that week — once each, "
    "under the highest governance role they hold in any repo (general → triage → committer → "
    "maintainer). Counts are strictly per-week (not a trailing window), so the current week is "
    "week-to-date. Only the most recent 26 weeks are charted; full history stays in the CSV.",
    "maintainer_pipeline_by_repo.png": "Each bar is a repository, counting people active there in the last six months, grouped by the "
    "governance role they hold in that repo (general → triage → committer → maintainer). A person "
    "active in several repos is counted in each; smaller repos are pooled into 'Other Repos'.",
    "maintainer_network.png": "Each bubble is a repository, sized by how many maintainers are active in it; two repos are "
    "linked when they share a maintainer (thicker line = more shared). Bubble colour is the repo's "
    "category.",
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
    "affiliation_donut.png": "The share of maintainers held by the two largest employers, with everyone else (smaller orgs and "
    "solo 'Independent' contributors) pooled into 'Other' — the concentration at a glance; the full "
    "breakdown is in the affiliations table. Switch to the Active tab to count only maintainers active "
    "in the last 90 days.",
    "repo_affiliation_composition.png": "Each bar is a repository, normalised to 100% so the segments show each employer's share of that "
    "repo's maintainers. The dashed line marks 50%: a segment reaching past it means one employer holds "
    "the majority (an organisational bus-factor). Largest employers get their own colour, smaller ones "
    "pool into 'Other orgs', and solo or unmapped maintainers show as 'Independent' and 'Unknown'. Repos "
    "are ordered most-concentrated first — by the largest single employer's share — and repos with the "
    "same concentration are grouped by their leading organisation (colour), so like sits next to like.",
    "team_affiliation_composition.png": "Each bar is a governance team, normalised to 100% so the segments show each employer's share of the "
    "team's members. The dashed line marks 50%: a segment past it means one employer holds the majority "
    "(a capture / bus-factor risk). Largest employers get their own colour, smaller ones pool into "
    "'Other orgs', and solo or unmapped members show as 'Independent' and 'Unknown'. Limited to teams "
    "with at least four resolved members and ordered most-concentrated first; teams with the same "
    "concentration are grouped by their leading organisation (colour). Every team is in the concentration table.",
    "single_employer_teams_by_org.png": "Each bar is an organisation; bar height is how many governance teams it solely controls — every "
    "resolved member of that team shares this one employer. Taller bars mean more single-employer "
    "teams, a governance-capture / bus-factor risk. Teams are counted only where their members "
    "resolve to an employer, so teams dominated by unmapped members are not over-counted here.",
    "single_employer_repos_by_org.png": "Each bar is an organisation; bar height is how many repositories it solely maintains — every "
    "resolved maintainer of that repo shares this one employer (at least two of them, no independents). "
    "Taller bars mean more single-employer repos, an organisational bus-factor. Repos dominated by "
    "unmapped maintainers are not counted here. The Active tab restricts to maintainers active in the last 90 days.",
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
    "affiliation_donut.png": [
        "Collect every maintainer from the governance config — anyone holding the maintainer role in any repo.",
        "Look up each maintainer's organisation in the curated affiliations file.",
        (
            "That file resolves each person from public signals in priority order: GPG-key email, profile email, "
            "the project MAINTAINERS.md, the GitHub company field, profile bio, public org membership, then "
            "commit-author email. Obfuscated noreply addresses are ignored; Swirlds Labs counts as Hashgraph."
        ),
        (
            "Count distinct maintainers per organisation; people with an identity but no employer are pooled as "
            "'Independent'; people with no public signal are excluded."
        ),
        (
            "Keep the two largest employers, fold everyone else (smaller orgs and independents) into 'Other', "
            "and draw a filled pie of their shares."
        ),
    ],
    "single_employer_teams_by_org.png": [
        "Take every team in the governance config and list its members.",
        "Map each member to an organisation via the affiliations file (same resolution as the other org charts).",
        (
            "Flag a team 'single-employer' when every member that resolves to an organisation shares the same one "
            "(at least two such members, and no independents)."
        ),
        "Group those single-employer teams by the organisation that controls them.",
        "Plot one bar per organisation — its height is how many teams it solely controls.",
    ],
    "single_employer_repos_by_org.png": [
        "For each repository, take the maintainers holding the maintainer role there.",
        "Map each to an organisation via the affiliations file (same resolution as the other org charts).",
        (
            "Flag a repo 'single-employer' when every resolved maintainer shares the same organisation "
            "(at least two such maintainers, and no independents)."
        ),
        "Group those single-employer repos by the organisation that maintains them.",
        "Plot one bar per organisation — its height is how many repos it solely maintains.",
    ],
    "repo_affiliation_composition.png": [
        "For each repository, take the maintainers holding the maintainer role there.",
        "Map each to an organisation via the affiliations file.",
        (
            "Count maintainers per organisation within the repo; the largest employers across all repos get their "
            "own colour, the rest pool into 'Other orgs', and solo/unmapped maintainers show as "
            "'Independent'/'Unknown'."
        ),
        (
            "Normalise each repo's counts to 100% and stack them into one bar, ordered most-concentrated first "
            "(by the largest single employer's share); ties are grouped by the leading organisation's colour."
        ),
        (
            "A dashed line marks 50%: a segment past it means one employer holds the majority. Single-colour "
            "bars are single-employer repos; multi-colour bars are cross-org."
        ),
    ],
    "team_affiliation_composition.png": [
        "For each governance team, take its members.",
        "Map each member to an organisation via the affiliations file.",
        (
            "Count members per organisation (top employers coloured individually, the rest as 'Other orgs', plus "
            "'Independent' and 'Unknown')."
        ),
        (
            "Normalise each team's counts to 100% and stack into one bar, ordered most-concentrated first with "
            "same-concentration teams grouped by their leading organisation's colour; only teams with at least "
            "four resolved members are shown (the full set is in the team-concentration table)."
        ),
        (
            "A dashed line marks 50%: a segment past it means one employer holds the majority. Single-colour "
            "bars are employer-controlled teams; multi-colour bars are cross-org."
        ),
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
