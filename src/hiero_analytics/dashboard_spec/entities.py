"""Repository and contributor detail views: what they read, publish and say.

Pure data, like the family modules, but not a tab: the detail views open from a
repository or contributor name anywhere on the dashboard. The ``entity_activity``
pipeline writes the ``*_FILE`` tables; ``export/entity_views`` joins them with
the optional per-repository tables below and publishes, per org:

- ``<org>/entities/repositories.json`` and ``<org>/entities/contributors.json``,
  the indexes the dashboard loads to know which names have a detail view, and
- ``<org>/entities/repositories/<id>.json`` and
  ``<org>/entities/contributors/<id>.json``, one detail document each, fetched
  only when a reader opens one.
"""

from __future__ import annotations

from hiero_analytics.config.analysis import ROLE_ACTIVE_DAYS

# Tables the entity_activity pipeline writes into each org's data directory.
REPO_ACTIVITY_FILE = "entity_repo_activity.csv"
CONTRIBUTOR_ACTIVITY_FILE = "entity_contributor_activity.csv"
PAIR_ACTIVITY_FILE = "entity_repo_contributor_activity.csv"
REPO_MONTHLY_FILE = "entity_repo_monthly.csv"
CONTRIBUTOR_MONTHLY_FILE = "entity_contributor_monthly.csv"
ENTITY_FILES = (
    REPO_ACTIVITY_FILE,
    CONTRIBUTOR_ACTIVITY_FILE,
    PAIR_ACTIVITY_FILE,
    REPO_MONTHLY_FILE,
    CONTRIBUTOR_MONTHLY_FILE,
)

# Stated on every detail view: what the counts are, and what they are not.
SCOPE = (
    "Tracked activity covers pull requests opened, reviews submitted, pull requests "
    "merged, issues opened and labels applied. It does not measure commits, comments, "
    "reactions or anything else, and it is not a measure of individual performance."
)

COUNT_LABELS = {
    "prs_opened": "PRs opened",
    "reviews_given": "Reviews",
    "merges_done": "Merges",
    "issues_opened": "Issues opened",
    "labels_applied": "Labels applied",
}

FAMILY_LABELS = {
    "building_and_fixing": "Building & fixing",
    "reviewing_and_guiding": "Reviewing & guiding",
    "organizing_and_answering": "Organizing & answering",
}

REPOSITORY_POPULATION = (
    "Every tracked action in this repository by a person (automation accounts are "
    "excluded). A person active in several repositories is counted in each."
)
CONTRIBUTOR_POPULATION = (
    "Every tracked action by this person across the organisation's repositories. "
    "Merges are credited to the person who merged, not the pull request's author."
)

METHODOLOGY = [
    (
        "Read the persisted GitHub activity for the organisation: pull requests with their "
        "reviews and merges, issues, and issue label events."
    ),
    (
        "Count one action per event: a pull request opened (at creation), a review "
        "submitted, a pull request merged (by the merger), an issue opened, and a label "
        "applied (label removals are not counted)."
    ),
    "Drop automation accounts and events whose author GitHub no longer reports.",
    (
        "Count each window from the events inside it: Week, 1 month and 1 year are the "
        "7, 30 and 365 days before the analysis ran; All time is everything recorded."
    ),
    (
        "Active contributors are distinct people with at least one action in the window, "
        "counted from the events rather than summed from other tables."
    ),
    (
        "Work mix splits the same actions into building & fixing (PRs opened), reviewing & "
        "guiding (reviews and merges) and organizing & answering (issues and labels)."
    ),
]

LIMITS = [
    (
        "At most 100 reviews per pull request and 100 label events per issue are read, so "
        "unusually long threads can undercount."
    ),
    "A pull request's merge counts for the person who merged it, which may not be its author.",
]

# Optional per-repository tables a repository's detail view joins, by section.
# Each names its org-level CSV (the repository is matched in its ``repo``
# column, bare or owner/repo) and the columns published. A table that was not
# produced — an offline run skips the network-only pipelines — is listed as
# unavailable on the view. Each section links to the dashboard sections its
# tables feed, so every figure leads back to its evidence.
REPO_RELATED = {
    "releases": {
        "title": "Releases",
        "file": "release_repo_summary.csv",
        "columns": [
            ("latest_release", "Latest release", "date"),
            ("days_since_last_release", "Days since last release", "number"),
            ("median_gap_days", "Median days between releases", "number"),
            ("release_status", "Release cadence", "status"),
        ],
        "list": {
            "file": "release_timeline.csv",
            "title": "Recent releases",
            "sort": "published_at",
            "limit": 10,
            "columns": [
                ("tag_name", "Tag"),
                ("published_at", "Published (UTC)", "date"),
                ("is_prerelease", "Pre-release", "flag"),
            ],
        },
    },
    "governance": {
        "title": "Governance",
        "file": "repo_activity_overview.csv",
        "columns": [
            ("maintainers", "Maintainers", "number"),
            ("committers", "Committers", "number"),
            ("triage", "Triage", "number"),
            ("active_recent", f"Permission-holders active in the last {ROLE_ACTIVE_DAYS} days", "number"),
        ],
        "extra": [
            {
                "file": "repo_affiliation_diversity.csv",
                "columns": [
                    ("distinct_orgs", "Maintainer organisations", "number"),
                    ("top_org", "Largest organisation"),
                    ("top_org_pct", "Largest organisation's share", "percent"),
                ],
            },
            {
                "file": "review_load_share.csv",
                "columns": [
                    ("mergers", "People merging recently", "number"),
                    ("top_carrier", "Largest review load"),
                    ("top_pct", "Their share of recent merges", "percent"),
                ],
            },
            {
                "file": "repo_wise_codeowner_status.csv",
                "columns": [("status", "CODEOWNERS file", "presence")],
            },
        ],
        "list": {
            "file": "role_coverage_all.csv",
            "title": "Role holders",
            "sort": "granted_role",
            "columns": [
                ("user", "Person"),
                ("granted_role", "Role"),
                ("status", "Status", "status"),
                ("last_active", "Last active (UTC)", "date"),
            ],
        },
    },
    "hips": {
        "title": "HIP engagement",
        "file": "hip_repo_engagement.csv",
        "columns": [
            ("distinct_hips_merged", "Distinct HIPs with merged PRs", "number"),
            ("matched_prs", "PRs referencing a HIP", "number"),
            ("total_prs", "PRs checked", "number"),
        ],
    },
    "onboarding": {
        "title": "Onboarding",
        "file": "difficulty_by_repo.csv",
        "columns": [
            ("Good First Issue", "Open good first issues", "number"),
            ("Beginner", "Open beginner issues", "number"),
            ("Intermediate", "Open intermediate issues", "number"),
            ("Advanced", "Open advanced issues", "number"),
            ("Unknown", "Open issues without a difficulty label", "number"),
        ],
    },
    "security": {
        "title": "Security",
        "file": "org_scorecard_checks.csv",
        "columns": [
            ("score", "OpenSSF Scorecard", "number"),
            ("date", "Scored on", "date"),
            ("Maintained", "Maintained", "number"),
            ("Code-Review", "Code review", "number"),
            ("Branch-Protection", "Branch protection", "number"),
            ("Token-Permissions", "Token permissions", "number"),
            ("Pinned-Dependencies", "Pinned dependencies", "number"),
            ("Dangerous-Workflow", "Dangerous workflow", "number"),
            ("Security-Policy", "Security policy", "number"),
            ("Signed-Releases", "Signed releases", "number"),
        ],
    },
}
