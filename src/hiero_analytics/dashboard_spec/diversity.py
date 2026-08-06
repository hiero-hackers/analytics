"""Organisation diversity — where maintainer authority sits, by employer.

The employer-concentration view: the ecosystem-wide split of maintainers by
organisation, the teams and repos a single employer solely controls, and the
reference tables behind them. Split out of the Governance tab so each tab
stays a readable size. Pure data; see the package __init__ for assembly.
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

CHART_MACRO = {
    "name": "Organisation diversity",
    "charts": {
        "hiero-ledger": [
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
                # Deliberately not time-filterable (charts and tables alike):
                # diversity is a property of the roster, and windowing it mostly
                # re-measures activity, which the activity views already show.
                # The compact charts share the top rows; the two wide
                # composition charts then stack full-width, one row each.
                "files": [
                    ("Maintainers by organisation", "affiliation_donut.png"),
                    ("Single-employer teams by org", "single_employer_teams_by_org.png"),
                    ("Single-employer repos by org", "single_employer_repos_by_org.png"),
                    ("Organisation mix by repo", "repo_affiliation_composition.png"),
                    ("Organisation mix by team", "team_affiliation_composition.png"),
                ],
            },
        ],
    },
}

SECTION_SPECS = [
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

# This tab's "how to read this": the affiliation and concentration vocabulary.
GLOSSARY = glossary_of(
    (
        "organisation",
        "method",
        "status",
        "members",
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
    ("Tables", ["affiliations", "repodiversity", "teamdiversity"]),
]
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

# Wide charts (vertical bars across many items): the dashboard scrolls these
# horizontally at a readable height instead of squashing them to the card width.
WIDE_CHARTS = {
    "repo_affiliation_composition.png",
    "team_affiliation_composition.png",
}

# "How to read this" notes, keyed by chart filename — encoding and window only,
# never current values, so they stay accurate across refreshes.
CHART_NOTES = {
    "affiliation_donut.png": "The share of maintainers held by the two largest employers, with everyone else (smaller orgs and "
    "solo 'Independent' contributors) pooled into 'Other' — the concentration at a glance; the full "
    "breakdown is in the affiliations table.",
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
    "unmapped maintainers are not counted here.",
}

# Step-by-step "how this was built" methodology, keyed by chart filename. Shown
# in the zoom (lightbox) view under the short note; method only, never values.
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
}
