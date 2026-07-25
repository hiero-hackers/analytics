"""HIPs — implementation evidence for Hiero Improvement Proposals.

Evidence-only by design: every number on this tab is derived mechanically from
PRs that reference a HIP (title, branch name, or description), validated
against the spec inventory. PR evidence shows where work happened — it cannot
prove a HIP is complete, and spec approvals (TSC dates, tentative releases)
are a separate registry-sourced concern. Pure data; see the package __init__
for assembly.
"""

from __future__ import annotations

CHART_MACRO = {
    "name": "HIPs",
    "charts": {
        "hiero-ledger": [
            {
                "id": "hip-adoption-funnel",
                "title": "Adoption funnel — specs created since Sep 2024",
                "description": (
                    "How far recent proposals get, mechanically: proposed, approved by the TSC, merged "
                    "implementation evidence found, implemented broadly (merged citing PRs in three or "
                    "more repositories). Restricted to specs created since September 2024 because "
                    "citation-based stages undercount older specs; the CSV download also carries the "
                    "all-time cohort."
                ),
                "files": [("Funnel", "hip_adoption_funnel.png")],
                "csv": "hip_adoption_funnel.csv",
            },
            {
                "id": "hip-activity-by-status",
                "title": "Implementation evidence — approved & final specs",
                "description": (
                    "Narrowed to the statuses where implementation is expected: each spec split by "
                    "the strongest evidence found — merged implementation PRs, open PRs only, or no "
                    "reference at all. 'No reference found' is absence of evidence, not evidence of "
                    "absence — older Final HIPs implemented before the hiero-ledger migration are "
                    "invisible to PR matching."
                ),
                "files": [("By spec status", "hip_activity_by_status.png")],
            },
            {
                "id": "hip-repo-engagement",
                "title": "Which repositories engage with HIPs",
                "description": (
                    "Distinct HIPs each repository has merged referencing PRs for — breadth of "
                    "engagement, not volume. Zero-reference repositories keep their (empty) rows "
                    "deliberately: many are tooling or docs where HIPs may not apply — relevance "
                    "is a human call. The full data downloads as CSV."
                ),
                "files": [("Repositories by distinct HIPs", "hip_repo_engagement.png")],
                "csv": "hip_repo_engagement.csv",
            },
        ],
    },
}

# Each section: which CSV it reads and how to render it. Sections appear only when
# their CSV exists and is non-empty.
SECTION_SPECS = [
    {
        "id": "hip-no-activity",
        "file": "hip_approved_no_activity.csv",
        "title": "Approved, no implementation PRs found",
        "description": (
            "Approved or accepted specs created in the Hiero era (since September 2024) with zero "
            "referencing PRs anywhere, newest first. Older approved specs are deliberately excluded: "
            "the sweep cannot see pre-era implementation history, so the claim would be unreliable — "
            "they remain visible in the governance board's Approved column."
        ),
        "columns": [
            ("hip", "HIP", "hip"),
            ("hip_title", "title"),
            ("hip_status", "spec status", "status"),
            ("hip_created", "spec created", "date"),
        ],
    },
    {
        "id": "hip-evidence",
        "file": "hip_pr_evidence.csv",
        "title": "Evidence (per PR)",
        "description": (
            "The audit trail: every (HIP, PR) reference with where it matched and the matched text. "
            "Filter to a HIP and repository to independently verify a coverage cell. References whose "
            "only mention is a body phrase behind a distancing cue (\u201cwaiting on\u201d, \u201cprepares "
            "for\u201d, \u201cblocked by\u201d\u2026) are kept here but excluded from every count \u2014 "
            "the cue and the counted flag make each exclusion auditable."
        ),
        "columns": [
            ("hip", "HIP", "hip"),
            ("hip_title", "HIP title"),
            ("repo", "repository"),
            ("pr_number", "PR"),
            ("pr_title", "PR title"),
            ("pr_state", "state"),
            ("pr_merged_at", "merged", "date"),
            ("match_sources", "matched in"),
            ("qualifier", "distancing cue"),
            ("counted", "counted", "flag"),
            ("url", "link", "link"),
        ],
    },
    {
        "id": "hip-unknown",
        "file": "hip_unknown_references.csv",
        "title": "Unknown HIP numbers (review)",
        "description": (
            "References to numbers absent from the spec inventory — typically HIP numbers assigned to "
            "in-flight proposals whose spec file has not merged yet, legacy pre-migration numbers, or "
            "the occasional false positive. Kept for review instead of being counted."
        ),
        "columns": [
            ("hip", "number"),
            ("repo", "repository"),
            ("pr_number", "PR"),
            ("pr_title", "PR title"),
            ("snippet", "matched text"),
        ],
    },
]

SECTION_GROUPS = [
    # The dashboard pipeline prepends the coverage matrix (group "Coverage")
    # before the tables, so the coverage tables lead to keep the group
    # contiguous in the jump bar.
    ("What is left to do", ["hip-no-activity"]),
    ("Evidence", ["hip-evidence", "hip-unknown"]),
]

# The tab's "how to read this" expander: documentation, not data. It states
# the interpretation rules from HIP-1 so every number reads the same way for
# every viewer. The generic macro chrome renders it in place of the shared
# column glossary.
GLOSSARY_HTML = (
    "<details class='glossary'><summary>How to read this tab \u2014 what the numbers mean</summary>"
    "<ul class='hipabout'>"
    "<li><strong>What is measured.</strong> PRs across the organisation's repositories that reference a "
    "HIP number in their title, branch name, or description, validated against the spec inventory. "
    "Counts are referencing PRs — evidence of where work happened, never proof a HIP is complete.</li>"
    "<li><strong>Reading a status (per HIP-1).</strong> <em>Review / Last Call</em>: the spec is still in "
    "governance; any implementation is early prototyping. <em>Approved / Accepted</em>: the TSC said yes — "
    "implementation is expected next, so a blank row is a real \u201cnot started?\u201d question. "
    "<em>Final</em>: the reference implementation merged <em>by definition</em> — a blank row is a citation "
    "gap (PRs that never named the HIP), not missing work. <em>Active</em>: process/informational specs in "
    "effect; code is not expected. Retired statuses (deferred, withdrawn, \u2026) are not being pursued.</li>"
    "<li><strong>The Hiero era.</strong> Only PRs from the Hiero era (since September 2024, when the "
    "codebase moved to hiero-ledger) are counted anywhere on this tab. Earlier references describe "
    "pre-migration work and are kept in the evidence table flagged \u201cpre-Hiero era\u201d.</li>"
    "<li><strong>What keeps the numbers honest.</strong> Every count clicks through to its PR list; "
    "spec-authoring PRs in the proposals repository are excluded; body-only mentions behind a distancing "
    "cue (\u201cwaiting on\u201d, \u201cprepares for\u201d\u2026) are excluded from counts but listed in the "
    "evidence table; numbers not in the inventory go to the review table instead of being counted.</li>"
    "<li><strong>Known blind spots.</strong> PRs that never cite their HIP are invisible; implementations "
    "predating the hiero-ledger migration live in old repositories; commit-message-only citations are not "
    "yet matched.</li>"
    "</ul></details>"
)

# The generic renderer calls ``build_sections(org, org_data_dir)`` here for the
# views this family cannot express as a table or chart gallery.
CUSTOM_SECTIONS_MODULE = "hiero_analytics.export.hip_sections"

# Groups render as the matrix's header bands in first-appearance order; the
# "SDKs" group drives the per-row parity gap list. HIPs land well beyond
# services and SDKs — relay, explorer, solo, and local-node all carry
# implementation PRs — hence the tooling band.
# The matrix's governance filter pills, most ready first: implemented or
# in-effect specs, then the approval pipeline in descending maturity, then the
# retired states.
# Governance-board columns: (column title, statuses it holds), read left to
# right as the HIP-1 lifecycle. "Accepted" shares the Approved column because
# HIP-1 retired it as an alias for Approved (specs before Jan 2025 use it).
# Statuses missing from every tuple land in a trailing "Other" column so new
# ones stay visible.
BOARD_COLUMNS = (
    ("In review", ("Draft", "Review", "Last Call")),
    ("Approved (incl. legacy Accepted)", ("Approved", "Accepted")),
    ("Final", ("Final",)),
    ("Active", ("Active",)),
    ("Retired", ("Deferred", "Stagnant", "Withdrawn", "Rejected", "Replaced")),
)

STATUS_READINESS_ORDER = (
    "Final",
    "Active",
    "Approved",
    "Accepted",
    "Last Call",
    "Review",
    "Draft",
    "Deferred",
    "Stagnant",
    "Withdrawn",
    "Rejected",
    "Replaced",
)

MATRIX_COMPONENTS = {
    "hiero-ledger": [
        ("hiero-ledger/hiero-consensus-node", "consensus", "Services"),
        ("hiero-ledger/hiero-mirror-node", "mirror", "Services"),
        ("hiero-ledger/hiero-block-node", "block-node", "Services"),
        ("hiero-ledger/hiero-sdk-java", "java", "SDKs"),
        ("hiero-ledger/hiero-sdk-go", "go", "SDKs"),
        ("hiero-ledger/hiero-sdk-js", "js", "SDKs"),
        ("hiero-ledger/hiero-sdk-cpp", "cpp", "SDKs"),
        ("hiero-ledger/hiero-sdk-rust", "rust", "SDKs"),
        ("hiero-ledger/hiero-sdk-swift", "swift", "SDKs"),
        ("hiero-ledger/hiero-sdk-python", "python", "SDKs"),
        ("hiero-ledger/hiero-json-rpc-relay", "relay", "Tooling & clients"),
        ("hiero-ledger/hiero-mirror-node-explorer", "explorer", "Tooling & clients"),
        ("hiero-ledger/solo", "solo", "Tooling & clients"),
        ("hiero-ledger/hiero-local-node", "local-node", "Tooling & clients"),
    ],
}
SECTION_ORDER = [sid for _name, ids in SECTION_GROUPS for sid in ids]
SECTION_GROUP_OF = {sid: name for name, ids in SECTION_GROUPS for sid in ids}

WIDE_CHARTS: set[str] = set()

CHART_NOTES = {
    "hip_adoption_funnel.png": "Each band is a funnel stage for specs created since September 2024; its width and label are "
    "the share of proposed specs. Each stage is a subset of the one above; broad = merged citing PRs "
    "in five or more repositories. Counts and the all-time cohort are in the CSV download.",
    "hip_activity_by_status.png": "Each bar is a spec-status bucket where implementation is expected. \u201cNo evidence\u201d is "
    "split by what HIP-1 implies: for approved specs it means awaiting implementation (actionable); for "
    "Final/Active specs the implementation merged by definition, so it is a citation gap instead. "
    "Derived from hip_summary.csv.",
    "hip_repo_engagement.png": "Repositories ranked by how many distinct HIPs they have merged referencing PRs for. Breadth, "
    "not volume — one PR per HIP counts the same as fifty. Derived from hip_repo_engagement.csv.",
}

# Methodology entries are ordered lists of steps (rendered as <li> items).
CHART_METHODOLOGY = {
    "hip_activity_by_status.png": [
        (
            "Sweep every merged and open PR in the organisation and match HIP references locally from "
            "titles, branch names, and descriptions, across the naming variants seen in the wild "
            "(HIP-1200, HIP 1200, hip_1200, hip1200, URL forms). Bare issue numbers (#1200) never match."
        ),
        (
            "Validate every matched number against the spec inventory parsed from the proposals "
            "repository's frontmatter; unknown numbers go to the review table instead of being counted."
        ),
        (
            "Exclude PRs from the proposals repository itself — spec-authoring PRs are the "
            "specification, not its implementation."
        ),
        (
            "Drop references whose only mention sits in a PR body behind a distancing cue "
            "(\u201cwaiting on\u201d, \u201cprepares for\u201d, \u201cblocked by\u201d\u2026) from every count; "
            "they stay in the evidence table with the cue shown, so each exclusion is auditable."
        ),
        (
            "Classify each spec by its strongest remaining evidence: merged implementation PRs, open "
            "PRs only, or no reference found — absence of evidence, not evidence of absence."
        ),
    ],
}
