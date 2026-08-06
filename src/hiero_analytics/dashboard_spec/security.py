"""Security & scorecards — OpenSSF scores, CODEOWNERS and CI runners.

Pure data; see the package __init__ for assembly.
"""

from __future__ import annotations

# Shown when the selected org has no content for this tab.
ABSENT_NOTE = (
    "Nothing generated for this org yet: the scorecard and repo-compliance "
    "pipelines are org-independent, so this fills in on the next full run."
)

CHART_MACRO = {
    "name": "Security & scorecards",
    "charts": {
        # "*": org-independent — these cards render for any org whose pipelines
        # produced the files (missing variants drop out per org).
        "*": [
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
                "description": (
                    "How many repositories declare code owners, and which CI runners the rest of the "
                    "organisation's workflows use. The per-repository CODEOWNERS answer is a yes/no, so it "
                    "reads as the table below rather than a chart."
                ),
                "files": [
                    ("Code-owner coverage", "org_codeowner_summary.png"),
                    ("Runners", "org_runner_chart.png"),
                ],
            },
        ],
    },
}

# Each section: which CSV it reads and how to render it. Sections appear only when
# their CSV exists and is non-empty.
SECTION_SPECS = [
    {
        "id": "codeowners",
        "file": "repo_wise_codeowner_status.csv",
        "title": "CODEOWNERS by repository",
        "description": (
            "Whether each repository declares code owners, repositories without a file first — a yes/no "
            "per repository, which is why this is a table and not a chart. A missing file is a lead, not "
            "a defect: docs, archive, and meta repositories may have no meaningful owner to name, so "
            "relevance is a human call. Checked in the standard locations (root, .github/, docs/)."
        ),
        "columns": [
            ("repo", "repository"),
            ("status", "CODEOWNERS", "presence"),
        ],
    },
]

SECTION_GROUPS = [
    ("Ownership", ["codeowners"]),
]

SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

# This tab's "how to read this" explainer. Prose only; *asterisks* mark
# emphasis. The "notes" layout renders lead-in + prose rather than the
# term/definition grid the column-heavy tabs use.
GLOSSARY = {
    "title": "How to read this tab — what the numbers mean",
    "layout": "notes",
    "terms": [
        {
            "term": "OpenSSF Scorecard.",
            "definition": (
                "An automated score from 0–10 published by the OpenSSF for a repository's security "
                "practices — branch protection, code review, dependency pinning, and similar checks. "
                "Scores are read from the public Scorecard API, not computed here; a repository with no "
                "published scorecard is omitted rather than shown as zero."
            ),
        },
        {
            "term": "Score breakdown.",
            "definition": (
                "The same score split into the individual checks that produced it, one colour per check, "
                "so a low total can be traced to the practice behind it."
            ),
        },
        {
            "term": "CODEOWNERS.",
            "definition": (
                "A file naming who reviews changes to which paths. Presence is checked in the standard "
                "locations (root, *.github/*, *docs/*) — the check is *has a file*, not whether the owners "
                "listed are correct or active."
            ),
        },
        {
            "term": "CI runners.",
            "definition": (
                "Where each repository's GitHub Actions workflows execute: *self-hosted* (org-provided "
                "machines), *standard* (GitHub-hosted), or *indeterminate* when the label could not be "
                "classified. Counted per workflow job, so a repository with many jobs contributes many."
            ),
        },
        {
            "term": "What this tab cannot tell you.",
            "definition": (
                "It measures declared configuration, not enforcement: a CODEOWNERS file does not prove "
                "reviews happen, and a high scorecard does not prove the code is secure. Treat every row "
                "as a prompt to look, not a verdict."
            ),
        },
    ],
}

CHART_NOTES = {
    "org_scorecard.png": "Each repository's overall OpenSSF Scorecard score (0–10), a measure of security practices. "
    "Repositories without a published scorecard are omitted.",
    "org_scorecard_breakdown.png": "Each repository's OpenSSF score split into its individual checks (one colour per check, e.g. "
    "Code-Review, Branch-Protection), so you can see which practices contribute.",
    "org_codeowner_summary.png": "How many repositories have a CODEOWNERS file (Present) versus none (Missing). "
    "Which repositories are missing one is in the table below.",
    "org_runner_chart.png": "GitHub Actions runner usage per repository, stacked by type: self-hosted, standard "
    "(GitHub-hosted), or indeterminate (could not be classified).",
}

CHART_METHODOLOGY = {
    "org_scorecard.png": [
        "List the organisation's public repositories.",
        (
            "Request each repository's published score from the public OpenSSF Scorecard API — the score "
            "is read, never computed here."
        ),
        (
            "Omit repositories with no published scorecard rather than plotting them as zero, since "
            "'unscored' and 'scored badly' are different findings."
        ),
        "Plot the remaining repositories by overall score (0–10).",
    ],
    "org_scorecard_breakdown.png": [
        "Take the same published scorecards as the overall-score chart.",
        (
            "Split each repository's result into the individual checks that produced it (Code-Review, "
            "Branch-Protection, Maintained, and so on)."
        ),
        "Stack the per-check scores per repository, one colour per check, so a low total traces to a practice.",
    ],
    "org_runner_chart.png": [
        "Read every GitHub Actions workflow file in each repository.",
        (
            "Classify each job's `runs-on` label as self-hosted, standard (a GitHub-hosted image), or "
            "indeterminate when the label cannot be resolved (e.g. a variable or a custom group name)."
        ),
        (
            "Count jobs, not repositories, and stack them per repository — so a repository with many jobs "
            "contributes proportionally more."
        ),
    ],
    "org_codeowner_summary.png": [
        "Check each repository for a CODEOWNERS file in the standard locations (root, .github/, or docs/).",
        (
            "Resolve duplicates presence-wins: if any check for a repository found a file, the repository "
            "counts as having one."
        ),
        "Count repositories by that answer — present versus missing — across the organisation.",
    ],
}

WIDE_CHARTS: set[str] = set()
