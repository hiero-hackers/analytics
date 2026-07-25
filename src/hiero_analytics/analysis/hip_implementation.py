"""Transforms mapping PR HIP references onto the HIP spec inventory.

Everything here is mechanical aggregation of two record lists — no scoring, no
judgment calls. PR evidence shows where implementation work happened; whether a
HIP is *complete* stays a human decision, which is why every table traces back
to the per-PR evidence rows.

Reference validation happens here (not at ingestion): a mentioned number that
matches no inventory spec lands in the unknown-references table for review
instead of being counted or silently dropped.
"""

from __future__ import annotations

import pandas as pd

from hiero_analytics.analysis.dataframe_utils import records_to_dataframe
from hiero_analytics.config.analysis import HIERO_ERA_START
from hiero_analytics.data_sources.models import HipReferenceRecord, HipSpecRecord

# Spec lifecycle statuses grouped for reporting. Anything unlisted (Replaced,
# Deferred, Stagnant, Withdrawn, Rejected, ...) is bucketed as "retired".
_STATUS_BUCKETS = {
    "final": "final_active",
    "active": "final_active",
    "approved": "approved_accepted",
    "accepted": "approved_accepted",
    "draft": "in_review",
    "review": "in_review",
    "last call": "in_review",
}

_EVIDENCE_COLUMNS = [
    "hip",
    "hip_title",
    "hip_status",
    "repo",
    "pr_number",
    "pr_title",
    "pr_state",
    "pr_created_at",
    "pr_merged_at",
    "author",
    "match_sources",
    "qualifier",
    "counted",
    "snippet",
    "url",
]


def status_bucket(status: str) -> str:
    """Reporting bucket for a spec lifecycle status."""
    return _STATUS_BUCKETS.get(status.strip().lower(), "retired")


def _in_hiero_era(record: HipReferenceRecord) -> bool:
    """Whether a PR belongs to the Hiero era (merged — or, if open, created — since the era began)."""
    stamp = record.pr_merged_at or record.pr_created_at
    return stamp is not None and stamp.date().isoformat() >= HIERO_ERA_START


def _mention_frame(references: list[HipReferenceRecord]) -> pd.DataFrame:
    """All HIP-mention rows (markers excluded) as a DataFrame."""
    mentions = [r for r in references if r.hip is not None]
    return records_to_dataframe(
        mentions,
        lambda r: {
            "hip": r.hip,
            "repo": r.repo,
            "pr_number": r.pr_number,
            "pr_title": r.pr_title,
            "pr_state": r.pr_state,
            "pr_created_at": r.pr_created_at,
            "pr_merged_at": r.pr_merged_at,
            "author": r.author,
            "match_sources": r.match_sources,
            # counted: excluded from every aggregate when the PR predates the
            # Hiero era, or when a distancing cue qualified a body-only
            # mention ("waiting on HIP-991", ...). The row itself stays —
            # every exclusion is auditable via the qualifier column.
            "qualifier": (r.qualifier or "") if _in_hiero_era(r) else "pre-Hiero era",
            "counted": r.qualifier == "" and _in_hiero_era(r),
            "snippet": r.snippet,
            "url": f"https://github.com/{r.repo}/pull/{r.pr_number}",
        },
        [c for c in _EVIDENCE_COLUMNS if c not in ("hip_title", "hip_status")],
    )


def _inventory_frame(inventory: list[HipSpecRecord]) -> pd.DataFrame:
    """The spec inventory as a DataFrame, one row per HIP number."""
    return records_to_dataframe(
        inventory,
        lambda r: {
            "hip": r.number,
            "hip_title": r.title,
            "hip_status": r.status,
            "hip_category": r.category,
            "hip_type": r.hip_type,
            "hip_created": r.created,
            "hip_release": r.release,
            "status_bucket": status_bucket(r.status),
        },
        ["hip", "hip_title", "hip_status", "hip_category", "hip_type", "hip_created", "hip_release", "status_bucket"],
    ).drop_duplicates(subset="hip")


def _counted(evidence: pd.DataFrame) -> pd.DataFrame:
    """Evidence rows that count: era-eligible and free of a distancing cue."""
    return evidence[evidence["counted"]]


def build_evidence_tables(
    references: list[HipReferenceRecord],
    inventory: list[HipSpecRecord],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(validated evidence, unknown references) — one row per (HIP, PR).

    Validated rows carry the spec title/status; unknown rows are mentions of
    numbers absent from the inventory (early assigned-but-unmerged HIP numbers,
    legacy pre-migration HIPs, or plain false positives) kept for human review.
    """
    mentions = _mention_frame(references)
    specs = _inventory_frame(inventory)
    if mentions.empty:
        return pd.DataFrame(columns=_EVIDENCE_COLUMNS), mentions

    known = mentions["hip"].isin(set(specs["hip"]))
    evidence = mentions[known].merge(specs[["hip", "hip_title", "hip_status"]], on="hip", how="left")
    # Newest HIPs first — the active end of the spec range is what readers scan.
    evidence = evidence[_EVIDENCE_COLUMNS].sort_values(["hip", "repo", "pr_number"], ascending=[False, True, True])
    unknown = mentions[~known].sort_values(["hip", "repo", "pr_number"], ascending=[False, True, True])
    return evidence.reset_index(drop=True), unknown.reset_index(drop=True)


def build_repo_activity(evidence: pd.DataFrame) -> pd.DataFrame:
    """Per (HIP, repo): merged/open PR counts and the merged-activity span.

    The long-format cell table behind the coverage matrix — pivot on
    (hip, repo) to render it.
    """
    evidence = _counted(evidence)
    if evidence.empty:
        return pd.DataFrame(columns=["hip", "repo", "merged_prs", "open_prs", "first_merged_at", "last_merged_at"])
    grouped = (
        evidence.assign(is_merged=evidence["pr_state"] == "MERGED")
        .groupby(["hip", "repo"])
        .agg(
            merged_prs=("is_merged", "sum"),
            open_prs=("is_merged", lambda s: int((~s).sum())),
            first_merged_at=("pr_merged_at", "min"),
            last_merged_at=("pr_merged_at", "max"),
        )
        .reset_index()
    )
    grouped["merged_prs"] = grouped["merged_prs"].astype(int)
    return grouped.sort_values(["hip", "repo"]).reset_index(drop=True)


def build_repo_engagement(
    references: list[HipReferenceRecord],
    evidence: pd.DataFrame,
) -> pd.DataFrame:
    """Per repo: breadth of HIP engagement against the swept-PR denominator.

    ``total_prs`` counts every PR swept in the repo (the no-mention markers
    supply the denominator), so repos with zero HIP references still appear —
    their absence from the engaged list is the finding.
    """
    swept = (
        records_to_dataframe(
            [r for r in references if _in_hiero_era(r)],
            lambda r: {"repo": r.repo, "pr_number": r.pr_number},
            ["repo", "pr_number"],
        )
        .drop_duplicates()
        .groupby("repo")
        .size()
        .rename("total_prs")
    )
    evidence = _counted(evidence)
    if evidence.empty:
        engagement = pd.DataFrame({"repo": swept.index, "distinct_hips_merged": 0, "matched_prs": 0})
    else:
        merged = evidence[evidence["pr_state"] == "MERGED"]
        engagement = (
            merged.groupby("repo")
            .agg(distinct_hips_merged=("hip", "nunique"), matched_prs=("pr_number", "nunique"))
            .reset_index()
        )
        engagement = pd.DataFrame({"repo": swept.index}).merge(engagement, on="repo", how="left").fillna(0)
        engagement[["distinct_hips_merged", "matched_prs"]] = engagement[
            ["distinct_hips_merged", "matched_prs"]
        ].astype(int)
    result = engagement.merge(swept, on="repo")
    return result.sort_values(["distinct_hips_merged", "total_prs"], ascending=[False, False]).reset_index(drop=True)


def build_hip_summary(
    inventory: list[HipSpecRecord],
    evidence: pd.DataFrame,
) -> pd.DataFrame:
    """The per-HIP ledger: one row per spec, with its implementation evidence.

    ``evidence_class`` is the mechanical three-way split the dashboard renders:
    ``merged`` (merged implementation PRs exist), ``open_only``, or ``none``
    (no reference found — absence of evidence, not evidence of absence).
    """
    specs = _inventory_frame(inventory)
    if specs.empty:
        return specs
    evidence = _counted(evidence)
    if evidence.empty:
        per_hip = pd.DataFrame(columns=["hip", "merged_prs", "open_prs", "repos_with_merged", "last_merged_at"])
    else:
        merged = evidence[evidence["pr_state"] == "MERGED"]
        per_hip = (
            evidence.assign(is_merged=evidence["pr_state"] == "MERGED")
            .groupby("hip")
            .agg(
                merged_prs=("is_merged", "sum"),
                open_prs=("is_merged", lambda s: int((~s).sum())),
            )
            .reset_index()
        )
        repo_counts = merged.groupby("hip").agg(
            repos_with_merged=("repo", "nunique"), last_merged_at=("pr_merged_at", "max")
        )
        per_hip = per_hip.merge(repo_counts, on="hip", how="left")

    summary = specs.merge(per_hip, on="hip", how="left")
    for column in ("merged_prs", "open_prs", "repos_with_merged"):
        summary[column] = summary.get(column, 0)
        summary[column] = summary[column].fillna(0).astype(int)
    if "last_merged_at" not in summary:
        summary["last_merged_at"] = pd.NaT

    def classify(row: pd.Series) -> str:
        if row["merged_prs"] > 0:
            return "merged"
        if row["open_prs"] > 0:
            return "open_only"
        return "none"

    summary["evidence_class"] = summary.apply(classify, axis=1)
    return summary.sort_values("hip").reset_index(drop=True)


# HIP-1 conformance checks — each is a mechanical reading of the process spec:
# a Final Standards Track HIP must carry a release number, and Final means the
# reference implementation was merged, so a Final spec with no citing PRs is a
# citation gap (the work exists per process; the references are missing).
_PROCESS_CHECK_COLUMNS = ["hip", "hip_title", "hip_status", "check", "detail"]


def build_process_checks(summary: pd.DataFrame) -> pd.DataFrame:
    """HIP-1 conformance findings, one row per (spec, check)."""
    if summary.empty:
        return pd.DataFrame(columns=_PROCESS_CHECK_COLUMNS)
    findings = []
    final = summary[summary["hip_status"].str.strip().str.lower() == "final"]
    for row in final.itertuples():
        if not str(row.hip_release).strip():
            findings.append(
                {
                    "hip": row.hip,
                    "hip_title": row.hip_title,
                    "hip_status": row.hip_status,
                    "check": "final_missing_release",
                    "detail": "HIP-1 requires a release number when a spec goes Final; frontmatter has none.",
                }
            )
        if row.evidence_class == "none":
            findings.append(
                {
                    "hip": row.hip,
                    "hip_title": row.hip_title,
                    "hip_status": row.hip_status,
                    "check": "final_no_citing_prs",
                    "detail": (
                        "Final means the reference implementation merged (HIP-1), but no PR citing "
                        "this HIP was found — a citation gap to close, not missing work."
                    ),
                }
            )
    frame = pd.DataFrame(findings, columns=_PROCESS_CHECK_COLUMNS)
    return frame.sort_values(["check", "hip"]).reset_index(drop=True)


# Adoption funnel: how far proposals get, measured mechanically. The two
# citation-based stages are also computed for a recent cohort because older
# specs predate the practice of citing HIP numbers in PRs — an all-time
# "success rate" from citations alone would understate history.
_FUNNEL_BREADTH_REPOS = 5
RECENT_COHORT = f"created since {HIERO_ERA_START[:7]}"  # the label both the CSV and the chart use
_APPROVED_BUCKETS = ("approved_accepted", "final_active")


def _funnel_rows(cohort: str, summary: pd.DataFrame) -> list[dict]:
    proposed = len(summary)
    if proposed == 0:
        return []
    approved = summary[summary["status_bucket"].isin(_APPROVED_BUCKETS)]
    merged = approved[approved["evidence_class"] == "merged"]
    broad = merged[merged["repos_with_merged"] >= _FUNNEL_BREADTH_REPOS]

    def row(stage: str, count: int) -> dict:
        return {"cohort": cohort, "stage": stage, "hips": count, "pct_of_proposed": round(100 * count / proposed)}

    # Stage names double as the funnel chart's axis labels, so they stay short;
    # the dashboard section's description defines each one in full.
    return [
        row("proposed", proposed),
        row("approved by TSC", len(approved)),
        row("implementation evidence", len(merged)),
        row(f"implemented in \u2265{_FUNNEL_BREADTH_REPOS} repos", len(broad)),
    ]


def build_adoption_funnel(summary: pd.DataFrame) -> pd.DataFrame:
    """Proposal-to-implementation funnel, all-time and for the recent cohort."""
    columns = ["cohort", "stage", "hips", "pct_of_proposed"]
    if summary.empty:
        return pd.DataFrame(columns=columns)
    recent = summary[summary["hip_created"].astype(str) >= HIERO_ERA_START]
    rows = _funnel_rows("all specs", summary) + _funnel_rows(RECENT_COHORT, recent)
    return pd.DataFrame(rows, columns=columns)
