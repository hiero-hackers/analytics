"""Governance — authority, coverage, and concentration.

The risk-focused family: who holds which role, where coverage is thin or
quiet, how the maintainer pipeline is developing, and how concentrated
authority is across employers. Pure data; see the package __init__ for
assembly.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec.glossary import GLOSSARY_NOTE, glossary_of

# "Suggest a correction" target for the affiliations reference table — the analytics
# repo's issues page. The affiliations map is the source of truth, so a correction is
# either a one-line edit to data/affiliations.yaml (append '# manual') or a new issue here.
AFFILIATION_ISSUE_URL = "https://github.com/hiero-hackers/analytics/issues"

CHART_MACRO = {
    "name": "Governance",
    "charts": {
        "hiero-ledger": [
            {
                "id": "maintainer-pipeline",
                "title": "Maintainer pipeline",
                "description": (
                    "How the maintainer/committer pipeline has moved over time and across repos — "
                    "is the bench of future maintainers developing?"
                ),
                # One chart, four views: a tab switcher (By year / month / week / repo)
                # shows a single chart at a time instead of stacking all four.
                "files": [
                    (
                        "Unique active contributors by role",
                        [
                            ("By year", "maintainer_pipeline_yearly.png"),
                            ("By year (active at year end)", "maintainer_pipeline_yearly_h2.png"),
                            ("By month", "maintainer_pipeline_monthly.png"),
                            ("By week", "maintainer_pipeline_weekly.png"),
                            ("By repo", "maintainer_pipeline_by_repo.png"),
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
            {
                "id": "org-diversity",
                "title": "Organisation diversity",
                "description": (
                    "Where maintainer authority sits — org-wide, per team and per repo. The first chart is "
                    "the ecosystem-wide split of maintainers by employer (solo contributors pooled as "
                    "'Independent'); the next two count the governance teams and the repositories that a "
                    "single employer solely controls (an organisational bus-factor); the last two break "
                    "down each repository's and each team's maintainer mix. See the affiliations and "
                    "repo-diversity tables below for the underlying detail."
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
            "person who can merge — committer or maintainer. 'mergers' is how many reviewed/merged; "
            "'top role' is whether the busiest is a committer or maintainer; 'top %' is their share, "
            "'top-2 %' the top two combined. Highest concentration first; repos with under 20 recent "
            "review+merge actions are omitted."
        ),
        "columns": [
            ("repo", "repo"),
            ("mergers", "mergers", "number"),
            ("load_recent", "review+merge", "number"),
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
            ("maintainers", "maintainers", "number"),
            ("distinct_orgs", "distinct orgs", "number"),
            ("top_org", "largest org"),
            ("top_org_pct", "largest org %", "number"),
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
            ("repos_held", "repos", "number"),
            ("days_since_active", "days since active", "number"),
            ("last_active", "last active", "date"),
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
# This tab's "how to read this": role and activity columns, plus the
# affiliation and organisation-diversity vocabulary its reference tables use.
GLOSSARY = glossary_of(
    (
        "contributor / account / member / user",
        "PRs",
        "reviews",
        "merges",
        "issues",
        "labels",
        "actions",
        "review+merge",
        "mergers",
        "top carrier / top % / top role",
        "role / role here",
        "highest role",
        "roles held",
        "how roles are set",
        "maintainers / committers / triage",
        "members",
        "active / members active",
        "org-wide teams",
        "status",
        "days since active",
        "last active",
        "repos",
        "period tabs",
        "organisation",
        "method",
        "resolved",
        "distinct orgs",
        "largest org / largest org %",
        "HHI",
        "single employer",
        "independent",
        "unknown",
        "organisation mix",
    ),
    note=GLOSSARY_NOTE,
)

SECTION_GROUPS = [
    # The actionable headlines — where coverage is thin or work is concentrated.
    ("Coverage & risk", ["repoactivity", "understaffed", "loadshare", "gonedark"]),
    # Who is affiliated with which organisation, and how concentrated that is — the
    # table companions to the Organisation-diversity charts.
    ("Organisation diversity", ["affiliations", "repodiversity", "teamdiversity"]),
    # Reference: who holds which role, per repo and per team.
    ("Roles & teams", ["repo", "tscrepo", "teams", "teamrepo"]),
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
    "maintainer_pipeline_yearly.png": "Each bar is a calendar year, counting everyone active at any point in it — the same "
    "whole-bucket rule as the month and week views, at a coarser resolution. Each person is counted "
    "once, under the highest governance role they hold in any repo (general → triage → committer → "
    "maintainer), so the bar's total is the distinct people active. Past bars never move; the current "
    "year is still in progress, so its bar is partial by definition. For who was still active by the "
    "end of each year, use the 'active at year end' view.",
    "maintainer_pipeline_yearly_h2.png": "The same yearly bars narrowed to people active *near the end* of each year — a fixed Jul–Dec "
    "window for past years (so old bars stay put) and a trailing six-month window for the current one, "
    "which early in the year reaches back into the previous December. It answers 'who was still here by "
    "year end?' rather than 'who showed up at all?', so it reads lower than the plain yearly view and "
    "the gap between them is roughly the people who drifted away mid-year.",
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
    "committer_network.png": "Each bubble is a repository, sized by how many committers are active in it; two repos are "
    "linked when they share a committer (thicker line = more shared). Bubble colour is the repo's "
    "category.",
    "triage_network.png": "Each bubble is a repository, sized by how many triage-role holders are active in it; two repos "
    "are linked when they share a triage holder (thicker line = more shared). Bubble colour is the "
    "repo's category.",
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
    "maintainer_pipeline_yearly_h2.png": [
        "Start from the same role-attached activity events as the plain yearly view.",
        (
            "Keep only events inside each year's end-window: a fixed Jul 1 – Dec 31 for completed "
            "years, so historical bars never move on a refresh; a trailing six-month window from today "
            "for the year in progress."
        ),
        (
            "Because the current year's window trails from today, early in the year it reaches into the "
            "previous December; those events are counted toward the current bar, not the previous one."
        ),
        (
            "Count distinct people per year at their highest role, exactly as the other variants do — "
            "only the membership window differs."
        ),
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
}

# The committer and triage networks are the same construction over a different
# role, so they share the maintainer network's steps rather than restating them.
CHART_METHODOLOGY["committer_network.png"] = CHART_METHODOLOGY["maintainer_network.png"]
CHART_METHODOLOGY["triage_network.png"] = CHART_METHODOLOGY["maintainer_network.png"]
