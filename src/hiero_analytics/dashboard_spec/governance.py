"""Governance — authority, coverage, teams, and concentration.

The risk-focused family: who holds which role, where coverage is thin or
quiet, how the maintainer pipeline is developing, what the governance bodies
are doing, and how concentrated authority is across employers. One tab; the
jump bar links each themed section group. Pure data; see the package
__init__ for assembly.
"""

from __future__ import annotations

from hiero_analytics.dashboard_spec.constants import PROJECT_ISSUES_URL
from hiero_analytics.dashboard_spec.glossary import GLOSSARY_NOTE, glossary_of

# "Suggest a correction" target for the affiliations reference table. That table
# earns a contextual link because its data is hand-curated: a correction is either
# a one-line edit to data/affiliations.yaml (append '# manual') or an issue. Tables
# of computed counts get no such link — the footer's general report link covers
# "this looks wrong" everywhere else.
AFFILIATION_ISSUE_URL = PROJECT_ISSUES_URL

# Shown when the selected org has no content for this tab (see the manifest's
# macro_absent_notes): say *why*, so absence reads as a property of the data,
# not a bug.
ABSENT_NOTE = (
    "Governance analytics are derived from the org's published governance config "
    "(team → permission grants). This org doesn't publish one, so roles, coverage, "
    "teams, and organisation diversity can't be inferred."
)

CHART_MACRO = {
    "name": "Governance",
    "charts": {
        "hiero-ledger": [
            {
                "id": "maintainer-pipeline",
                "title": "Maintainer pipeline over time",
                "group": "Maintainer pipeline",
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
                "group": "Maintainer pipeline",
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
                "group": "Roles",
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
                # Renders inside the Organisation-diversity section, directly
                # above its companion tables — the jump bar lands on charts +
                # tables together.
                "group": "Organisation diversity",
                "description": (
                    "Where write authority sits — org-wide, per team and per repo. The role tabs switch "
                    "between maintainers (merge rights) and committers (write access, but no maintainer "
                    "seat anywhere), so the two benches can be compared: a committer bench spread across "
                    "more employers is the leading indicator that maintainer diversity will follow. The "
                    "first chart is the ecosystem-wide split by employer (solo contributors pooled as "
                    "'Independent', unmapped people shown as their own 'Unknown' band rather than dropped); "
                    "the next two count the governance teams and the repositories that a single employer "
                    "solely controls (an organisational bus-factor); the last two break down each "
                    "repository's and each team's mix. The team charts are membership-based and so have no "
                    "role tabs. See the affiliations and repo-diversity tables below for the underlying detail."
                ),
                # Deliberately not time-filterable (charts and tables alike):
                # diversity is a property of the roster, and windowing it mostly
                # re-measures activity, which the activity views already show.
                # The compact charts share the top rows; the two wide
                # composition charts then stack full-width, one row each.
                "files": [
                    (
                        "Role-holders by organisation",
                        [
                            ("Maintainers", "affiliation_donut.png"),
                            ("Committers", "affiliation_donut_committers.png"),
                        ],
                    ),
                    ("Single-employer teams by org", "single_employer_teams_by_org.png"),
                    (
                        "Single-employer repos by org",
                        [
                            ("Maintainers", "single_employer_repos_by_org.png"),
                            ("Committers", "single_employer_repos_by_org_committers.png"),
                        ],
                    ),
                    (
                        "Organisation mix by repo",
                        [
                            ("Maintainers", "repo_affiliation_composition.png"),
                            ("Committers", "repo_affiliation_composition_committers.png"),
                        ],
                    ),
                    ("Organisation mix by team", "team_affiliation_composition.png"),
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
        "id": "committeraffiliations",
        "file": "committer_affiliations.csv",
        "title": "Committer affiliations — reference",
        "description": (
            "The same reference as the maintainer table, for people whose highest role anywhere is "
            "committer — write access, but no maintainer seat in any repository. The two populations are "
            "disjoint, so nobody appears in both. Curation coverage is thinner here than for maintainers, "
            "so expect more 'unknown' rows; each one resolved makes the committer diversity chart sharper. "
            "To fix a mapping or resolve an unknown, edit its row in data/affiliations.yaml and append "
            "'# manual: reason', or use 'Suggest a correction' to open an issue on the analytics repo."
        ),
        "action_url": AFFILIATION_ISSUE_URL,
        "action_label": "Suggest a correction",
        "columns": [
            ("login", "committer"),
            ("organisation", "organisation"),
            ("status", "status"),
            ("method", "method"),
        ],
    },
    {
        "id": "repodiversity",
        "file": "repo_affiliation_diversity.csv",
        # Deliberately not time-filterable (like the diversity charts):
        # diversity is a property of the roster, not of a window's activity.
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
        "id": "committerrepodiversity",
        "file": "repo_affiliation_diversity_committers.csv",
        # Deliberately not time-filterable — see repodiversity above.
        "title": "Committer organisation diversity by repo",
        "description": (
            "The repo table above, over committers instead of maintainers: per repo, how many committers "
            "it has, how many distinct employers they span, the largest employer and its share of resolved "
            "committers, and the independent / unknown counts. Read it against the maintainer table — a "
            "repo whose maintainers are single-employer but whose committers are not has a bench it could "
            "promote from. The 'unknown' count is higher here, so weigh a single-employer reading against it."
        ),
        "columns": [
            ("repo", "repo"),
            ("committers", "committers", "number"),
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
        # Deliberately not time-filterable — see repodiversity above.
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
]


# This tab's "how to read this": role and activity columns, plus the team,
# affiliation, and organisation-diversity vocabulary its sections use.
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
        "committer",
        "role tabs",
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

# Everything grouped by purpose so viewers get a short, scannable menu instead
# of one long stack. Each group renders under its own heading (with a jump-bar
# link); chart cards join the group they name via their "group" key, and a
# group with no table ids is chart-only. Within a group the order goes
# high-level aggregate → most granular. Order here is the on-screen order.
SECTION_GROUPS = [
    # The bench of future maintainers, over time and by repo (chart-only).
    ("Maintainer pipeline", []),
    # The actionable headlines — where coverage is thin or work is concentrated.
    ("Coverage & risk", ["repoactivity", "understaffed", "loadshare", "gonedark"]),
    # Who holds which role: the role networks, then per repo.
    ("Roles", ["repo"]),
    # The governance bodies: teams as groups, then the TSC members individually.
    ("Teams & TSC", ["teams", "teamrepo", "tscrepo"]),
    # Who is affiliated with which organisation, and how concentrated that is —
    # the org-diversity chart card renders at the top of this group. Each role's
    # reference table sits beside its repo-diversity breakdown.
    (
        "Organisation diversity",
        ["affiliations", "repodiversity", "committeraffiliations", "committerrepodiversity", "teamdiversity"],
    ),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

# Wide charts (vertical bars across many items): the dashboard scrolls these
# horizontally at a readable height instead of squashing them to the card width.
WIDE_CHARTS = {
    "repo_affiliation_composition.png",
    "repo_affiliation_composition_committers.png",
    "team_affiliation_composition.png",
}

LIVE_VIEW_IDS: dict[str, str] = {}

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
    "affiliation_donut.png": "The share of role-holders employed by the two largest organisations, with everyone else (smaller "
    "orgs and solo 'Independent' contributors) pooled into 'Other' — the concentration at a glance. "
    "People with no curated affiliation are shown as their own 'Unknown' slice rather than dropped, and "
    "the title states what share of the population is known, so a small slice can be read against how "
    "much of the roster is resolved. The role tabs switch between maintainers and committers; the full "
    "breakdown is in the affiliations tables.",
    "affiliation_donut_committers.png": "The committer view of the same chart: people whose highest role anywhere is committer (write "
    "access, no maintainer seat), so this population never overlaps the maintainer tab. Curation is "
    "thinner here, which is why the 'Unknown' slice is larger and the known share in the title matters "
    "more — every percentage is a share of all committers, unknowns included, so weigh the employer "
    "slices against how big the 'Unknown' one is.",
    "repo_affiliation_composition.png": "Each bar is a repository, normalised to 100% so the segments show each employer's share of that "
    "repo's role-holders. The dashed line marks 50%: a segment reaching past it means one employer holds "
    "the majority (an organisational bus-factor). Largest employers get their own colour, smaller ones "
    "pool into 'Other orgs', and solo or unmapped holders show as 'Independent' and 'Unknown'. Repos "
    "are ordered most-concentrated first — by the largest single employer's share — and repos with the "
    "same concentration are grouped by their leading organisation (colour), so like sits next to like. "
    "The role tabs switch between maintainers and committers; a repo counts only where it grants that role.",
    "repo_affiliation_composition_committers.png": "The committer view of the same chart. Repos appear only where someone holds committer as their "
    "highest role, so the set of bars differs from the maintainer tab — a repo whose committer bar is "
    "multi-colour while its maintainer bar is single-colour has a cross-org bench it could promote from.",
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
    "single_employer_repos_by_org.png": "Each bar is an organisation; bar height is how many repositories it solely holds — every "
    "resolved holder of that role in the repo shares this one employer (at least two of them, no "
    "independents). Taller bars mean more single-employer repos, an organisational bus-factor. Repos "
    "dominated by unmapped holders are not counted here. The role tabs switch between maintainers and "
    "committers.",
    "single_employer_repos_by_org_committers.png": "The committer view of the same chart: repositories where every resolved committer shares one "
    "employer. Because committer curation is thinner, more repos fall below the 'enough of the roster "
    "is known' bar and are left uncounted — treat this as a floor, not a total.",
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
    "affiliation_donut.png": [
        (
            "Resolve every person's role per repository from the governance config, then reduce each to the "
            "most senior role they hold anywhere — so the maintainer and committer tabs are disjoint "
            "populations and can be compared directly."
        ),
        "Look up each person's organisation in the curated affiliations file.",
        (
            "That file resolves each person from public signals in priority order: GPG-key email, profile email, "
            "the project MAINTAINERS.md, the GitHub company field, profile bio, public org membership, then "
            "commit-author email. Obfuscated noreply addresses are ignored; Swirlds Labs counts as Hashgraph."
        ),
        (
            "Count distinct people per organisation; people with an identity but no employer are pooled as "
            "'Independent', and people with no public signal form their own 'Unknown' slice — the chart's "
            "total is the whole population, never a silently trimmed one."
        ),
        (
            "Keep the two largest slices, fold everyone else into 'Other', draw a filled pie of their shares, "
            "and state the share of the population with a known affiliation in the title."
        ),
    ],
    "affiliation_donut_committers.png": [
        (
            "Same construction as the maintainer tab, over the people whose highest role anywhere is "
            "committer: write access in at least one repository and a maintainer seat in none."
        ),
        "Look up each committer's organisation in the same curated affiliations file, by the same priority order.",
        (
            "Count distinct committers per organisation, pooling employer-less people as 'Independent' and "
            "unmapped people as 'Unknown'; the title states what share is known, which is materially lower "
            "than for maintainers."
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
        "For each repository, take the people holding the selected role there (the tabs pick maintainer or committer).",
        "Map each to an organisation via the affiliations file (same resolution as the other org charts).",
        (
            "Flag a repo 'single-employer' when every resolved holder shares the same organisation "
            "(at least two such holders, and no independents)."
        ),
        "Group those single-employer repos by the organisation that holds them.",
        "Plot one bar per organisation — its height is how many repos it solely holds.",
    ],
    "single_employer_repos_by_org_committers.png": [
        "Same construction over each repository's committers — people with write access there and no maintainer seat anywhere.",
        "Repos where unmapped committers outnumber resolved ones are never flagged, so thin curation under-counts rather than over-claims.",
    ],
    "repo_affiliation_composition.png": [
        "For each repository, take the people holding the selected role there (the tabs pick maintainer or committer).",
        "Map each to an organisation via the affiliations file.",
        (
            "Count holders per organisation within the repo; the largest employers across all repos get their "
            "own colour, the rest pool into 'Other orgs', and solo/unmapped holders show as "
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
    "repo_affiliation_composition_committers.png": [
        "Same construction over each repository's committers, so only repos that grant committer appear.",
        (
            "Compare a repo's two bars: a single-colour maintainer bar beside a multi-colour committer bar is "
            "a concentrated top with a diverse bench underneath it."
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
