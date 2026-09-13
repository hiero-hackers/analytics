"""How each KPI tile is derived — the tile's "how to read this" and steps.

A tile is a single number with no axis, no rows, and nothing to click through
to, so it is the easiest figure on the dashboard to misread. Every tile
therefore carries the same annotation a chart does: what it counts, and the
steps that produced it. Keyed by the tile's label, which is what the reader
sees; the values themselves come from ``export/macro_metrics.py``.

Pure data: definitions may mark emphasis with ``*asterisks*``; no other markup.
"""

from __future__ import annotations

METRIC_ANNOTATIONS: dict[str, dict] = {
    "contributors": {
        "note": (
            "Distinct people with any tracked activity in the organisation, all-time. The denominator "
            "for every percentage tile on this tab."
        ),
        "methodology": [
            "Collect every tracked activity event: PRs opened, reviews, merges, issues opened, labels applied.",
            "Drop known bot accounts (domain/bots.py), which would otherwise dominate the counts.",
            "Count the distinct actors that remain, across all repositories and all time.",
        ],
    },
    "active last month %": {
        "note": (
            "The share of all-time contributors who did something in the last 30 days — a staleness "
            "check on the contributor base, not a measure of output."
        ),
        "methodology": [
            "Take the 30-day activity table, which lists exactly the contributors active in that window.",
            "Divide its row count by the all-time contributor total and round to a whole percent.",
        ],
    },
    "multi-repo %": {
        "note": (
            "The share of contributors active in two or more repositories — how much the contributor "
            "base spans the organisation rather than sitting in one project."
        ),
        "methodology": [
            "For each contributor, count the distinct repositories they were active in (all-time).",
            "Count those with two or more, and divide by the all-time contributor total.",
        ],
    },
    "file issues %": {
        "note": "The share of contributors who have opened at least one issue.",
        "methodology": [
            "Count contributors whose all-time issues-opened total is above zero.",
            "Divide by the all-time contributor total.",
        ],
    },
    "open PRs %": {
        "note": (
            "The share of contributors who have authored at least one pull request. Used as the proxy "
            "for “writes code”: commits themselves are not ingested, only PRs."
        ),
        "methodology": [
            "Count contributors whose all-time PRs-opened total is above zero.",
            "Divide by the all-time contributor total.",
        ],
    },
    "give reviews %": {
        "note": (
            "The share of contributors who have reviewed at least one pull request — the review load's "
            "breadth, not its volume."
        ),
        "methodology": [
            "Count contributors whose all-time reviews-given total is above zero.",
            "Divide by the all-time contributor total.",
        ],
    },
    "completed a GFI %": {
        "note": (
            "The share of contributors who have merged a PR closing an onboarding (good-first-issue) "
            "ticket — the clearest signal that onboarding paths actually convert."
        ),
        "methodology": [
            "Find merged PRs that closed an issue labelled as onboarding-friendly.",
            "Count the distinct authors of those PRs.",
            "Divide by the all-time contributor total.",
        ],
    },
    "maintainers": {
        "note": (
            "People whose *highest* role anywhere in the organisation is maintainer. Counted at the "
            "highest role so the role tiles partition the permission-holders without double-counting."
        ),
        "methodology": [
            (
                "Resolve every person's role per repository from the governance config's team→permission "
                "grants (maintain/admin → maintainer, write → committer, triage → triage)."
            ),
            "Reduce each person to the most senior role they hold in any repository.",
            "Count the people whose highest role is maintainer.",
        ],
    },
    "committers": {
        "note": "People whose highest role anywhere is committer (write access, but not maintainer).",
        "methodology": [
            "Resolve every person's role per repository from the governance config's team→permission grants.",
            "Reduce each person to the most senior role they hold in any repository.",
            "Count the people whose highest role is committer.",
        ],
    },
    "triage": {
        "note": "People whose highest role anywhere is triage (label and issue management, no merge rights).",
        "methodology": [
            "Resolve every person's role per repository from the governance config's team→permission grants.",
            "Reduce each person to the most senior role they hold in any repository.",
            "Count the people whose highest role is triage.",
        ],
    },
    "maintainer affiliations known": {
        "note": (
            "The share of maintainers whose affiliation is resolved to a named employer or Independent. "
            "The organisation-diversity pie uses this resolved population as its denominator."
        ),
        "methodology": [
            "Take every row in the maintainer affiliations reference table.",
            "Count rows whose status is affiliated or independent.",
            "Divide by all maintainer rows, including unknowns, and round to a whole percent.",
        ],
    },
    "committer affiliations known": {
        "note": (
            "The share of highest-role committers whose affiliation is resolved to a named employer or "
            "Independent. Read the committer organisation-diversity pie against this coverage."
        ),
        "methodology": [
            "Take every row in the committer affiliations reference table.",
            "Count rows whose status is affiliated or independent.",
            "Divide by all committer rows, including unknowns, and round to a whole percent.",
        ],
    },
    "quiet permission-holders (180d+)": {
        "note": (
            "People holding a granted role who have had no tracked activity for 180 days or more — an "
            "access-hygiene list, not a judgement about the people on it."
        ),
        "methodology": [
            "Take everyone holding a triage, committer, or maintainer role in any repository.",
            "Find each person's most recent tracked activity across the organisation.",
            (
                "Keep those whose last activity is 180 days or more ago, or who have none at all. The "
                "threshold is fixed, not the tab's selected period."
            ),
        ],
    },
    "quiet teams": {
        "note": (
            "Governance teams where no member has had tracked activity for 180 days or more — a team "
            "that exists on paper but is not currently doing the work its grants imply. The threshold "
            "is fixed, not the tab's selected period."
        ),
        "methodology": [
            "Take each governance team and its resolved members.",
            "Find the team's most recent tracked activity by any member, anywhere.",
            "Count the teams whose latest activity is 180 days or more ago, or who have none at all.",
        ],
    },
    "repos with releases": {
        "note": (
            "How many repos have ever published a GitHub Release, out of the org's full repo count. "
            "Most zero-release repos are docs/governance/meta repos, not neglected code — this tile is "
            "the denominator the other release tiles are scoped to, so that scoping is visible."
        ),
        "methodology": [
            "Fetch every published, non-draft GitHub Release for each repo in the org.",
            "Count repos with at least one release, against the org's full repo count.",
        ],
    },
    "released last 90d %": {
        "note": (
            "Of repos that have ever released (not the full repo universe), the share that shipped a "
            "release in the last 90 days."
        ),
        "methodology": [
            "Take repos with at least one release ever.",
            "Count those whose most recent release is 90 days old or less.",
            "Divide by the count of repos that have ever released.",
        ],
    },
    ">3x their own typical gap": {
        "note": (
            "Repos currently more than 3x past their own typical release gap — furthest behind "
            "*relative to their own pace*, not by raw days. A repo with a naturally long cadence isn't "
            "counted just for having one; only repos with an established cadence (2+ releases) are "
            "eligible."
        ),
        "methodology": [
            "For each repo with 2+ releases, compute the median gap between consecutive releases.",
            "Divide days since the most recent release by that median gap.",
            "Count repos where that ratio exceeds 3.",
        ],
    },
}
