"""Build the HIP-implementation evidence tables for an organization.

Maps Hiero Improvement Proposals onto the PRs that reference them across every
org repository, producing the artifacts behind the dashboard's HIPs tab:

- ``hip_pr_evidence.csv``        — one row per (HIP, PR): the audit trail. A
  reviewer verifying "did repo X implement HIP Y?" filters this to the exact
  PR list, each with where it matched and the matched snippet.
- ``hip_unknown_references.csv`` — mentions of numbers absent from the spec
  inventory (assigned-but-unmerged HIPs, legacy numbers, false positives),
  kept for review instead of being counted.
- ``hip_repo_activity.csv``      — per (HIP, repo) merged/open counts: the
  long-format cells of the coverage matrix.
- ``hip_repo_engagement.csv``    — per repo: distinct HIPs with merged PRs
  against the swept-PR denominator (repos with zero references included).
- ``hip_summary.csv``            — one row per spec: status, status bucket,
  and the mechanical evidence class (merged / open_only / none).
- ``hip_approved_no_activity.csv`` — Hiero-era approved specs with no
  implementation PRs found anywhere: the attention list.
- ``hip_process_checks.csv`` — HIP-1 conformance findings (a Final spec must
  carry a release number; a Final spec with no citing PRs is a citation gap).
- ``hip_adoption_funnel.csv`` — proposal-to-implementation funnel, all-time
  and for the Hiero-era cohort.
- ``hip_activity_by_status.csv`` — implementation evidence per status bucket
  (approved/final); written only when there are rows.

Deliberately evidence-only: PR references show where work happened, never that
a HIP is complete, and spec approvals (TSC dates, tentative releases) are a
separate registry-sourced concern. An offline run without the cached datasets
skips cleanly — the dashboard omits sections whose CSVs are absent.
"""

from __future__ import annotations

import logging

import pandas as pd

from hiero_analytics.analysis.hip_implementation import (
    build_adoption_funnel,
    build_evidence_tables,
    build_hip_summary,
    build_process_checks,
    build_repo_activity,
    build_repo_engagement,
)
from hiero_analytics.config.analysis import HIERO_ERA_START
from hiero_analytics.config.github import HIP_PROPOSALS_REPO
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.dataset_store import OfflineDatasetMissingError
from hiero_analytics.data_sources.github_ingest import fetch_hip_inventory, fetch_org_pr_hip_refs_graphql
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context

logger = logging.getLogger(__name__)

# Display names for the status buckets in the activity table. It keeps only the
# buckets where implementation is expected — the spec-status funnel covers the
# full governance picture.
_BUCKET_LABELS = {
    "approved_accepted": "Approved / Accepted",
    "final_active": "Final / Active",
}


_NO_ACTIVITY_COLUMNS = ["hip", "hip_title", "hip_status", "hip_created"]


def _approved_no_activity(summary: pd.DataFrame) -> pd.DataFrame:
    """Hiero-era approved/accepted specs with zero implementation PRs, newest first.

    Restricted to specs *created* in the Hiero era: for older approved specs
    the sweep cannot see pre-era implementation history, so "no PRs found"
    would be an unreliable claim. Legacy approved specs stay visible in the
    governance board's Approved column — as status, not as an evidence claim.
    """
    if summary.empty:
        return pd.DataFrame(columns=_NO_ACTIVITY_COLUMNS)
    rows = summary[
        (summary["status_bucket"] == "approved_accepted")
        & (summary["evidence_class"] == "none")
        & (summary["hip_created"].astype(str) >= HIERO_ERA_START)
    ]
    return rows[_NO_ACTIVITY_COLUMNS].sort_values("hip", ascending=False).reset_index(drop=True)


def activity_by_status(summary: pd.DataFrame) -> pd.DataFrame:
    """Implementation evidence for the statuses where implementation is expected.

    "No evidence" splits by what HIP-1 implies: for an approved spec it means
    awaiting implementation (actionable); for a Final/Active spec the
    implementation merged by definition, so it is a citation gap instead.
    """
    summary = summary[summary["status_bucket"].isin(_BUCKET_LABELS)]
    if summary.empty:
        return pd.DataFrame(columns=["bucket", "merged", "open_only", "none_awaiting", "citation_gap"])
    counts = summary.groupby(["status_bucket", "evidence_class"]).size().unstack(fill_value=0).reindex(_BUCKET_LABELS)
    for column in ("merged", "open_only", "none"):
        if column not in counts:
            counts[column] = 0
    counts = counts.fillna(0).astype(int)
    frame = counts.reset_index().assign(bucket=lambda d: d["status_bucket"].map(_BUCKET_LABELS))
    is_approved = frame["status_bucket"] == "approved_accepted"
    frame["none_awaiting"] = frame["none"].where(is_approved, 0)
    frame["citation_gap"] = frame["none"].where(~is_approved, 0)
    return frame


def main(org: str = ORG) -> None:
    """Build the HIP-implementation evidence tables for ``org``."""
    client, org_data_dir = org_context(org)

    logger.info("Building HIP implementation tables for org: %s", org)

    # Offline runs without the cached datasets skip cleanly: the tab's sections
    # simply don't render until a live run (or the CI refresh) populates them.
    try:
        inventory = fetch_hip_inventory(client)
        references = fetch_org_pr_hip_refs_graphql(client, org)
    except OfflineDatasetMissingError:
        logger.warning("No cached HIP datasets for %s in offline mode; skipping HIP implementation tables", org)
        return
    # Spec-authoring PRs in the proposals repo reference their own HIP numbers
    # constantly; they are the specification, not its implementation.
    references = [r for r in references if r.repo != HIP_PROPOSALS_REPO]
    swept_prs = len({(r.repo, r.pr_number) for r in references})
    logger.info("Using %d HIP specs and %d swept PRs", len(inventory), swept_prs)

    evidence, unknown = build_evidence_tables(references, inventory)
    engagement = build_repo_engagement(references, evidence)
    summary = build_hip_summary(inventory, evidence)
    tables = {
        "hip_pr_evidence.csv": evidence,
        "hip_unknown_references.csv": unknown,
        "hip_repo_activity.csv": build_repo_activity(evidence),
        "hip_repo_engagement.csv": engagement,
        "hip_summary.csv": summary,
        "hip_approved_no_activity.csv": _approved_no_activity(summary),
        "hip_process_checks.csv": build_process_checks(summary),
        "hip_adoption_funnel.csv": build_adoption_funnel(summary),
    }
    for filename, frame in tables.items():
        save_dataframe(frame, org_data_dir / filename)
    # Unlike the tables above, no rows means no file.
    if not (activity := activity_by_status(summary)).empty:
        save_dataframe(activity, org_data_dir / "hip_activity_by_status.csv")

    logger.info(
        "HIP implementation: %d evidence rows across %d HIPs (%d unknown-number rows for review)",
        len(evidence),
        int((summary["evidence_class"] != "none").sum()) if not summary.empty else 0,
        len(unknown),
    )
