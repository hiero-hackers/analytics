"""Build the HIP-implementation evidence tables and charts for an organization.

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
- ``hip_repo_engagement.png`` / ``hip_adoption_funnel.png`` /
  ``hip_activity_by_status.png`` — the three charts the HIPs macro renders.

Deliberately evidence-only: PR references show where work happened, never that
a HIP is complete, and spec approvals (TSC dates, tentative releases) are a
separate registry-sourced concern. An offline run without the cached datasets
skips cleanly — the dashboard omits sections whose CSVs are absent.
"""

from __future__ import annotations

import logging

import pandas as pd

from hiero_analytics.analysis.hip_implementation import (
    RECENT_COHORT,
    build_adoption_funnel,
    build_evidence_tables,
    build_hip_summary,
    build_process_checks,
    build_repo_activity,
    build_repo_engagement,
)
from hiero_analytics.config.analysis import HIERO_ERA_START
from hiero_analytics.config.charts import HIP_EVIDENCE_RAMP
from hiero_analytics.config.github import HIP_PROPOSALS_REPO
from hiero_analytics.config.paths import ORG
from hiero_analytics.data_sources.dataset_store import OfflineDatasetMissingError
from hiero_analytics.data_sources.github_ingest import fetch_hip_inventory, fetch_org_pr_hip_refs_graphql
from hiero_analytics.export.save import save_dataframe
from hiero_analytics.pipelines._shared import org_context
from hiero_analytics.plotting.bars import plot_bar, plot_stacked_bar
from hiero_analytics.plotting.funnel import plot_funnel

logger = logging.getLogger(__name__)

# Display names for the status buckets on the activity chart. The chart keeps
# only the buckets where implementation is expected — the spec-status funnel
# chart covers the full governance picture.
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


def _plot_engagement(engagement: pd.DataFrame, org: str, charts_dir) -> None:
    """Repos ranked by distinct HIPs with merged referencing PRs.

    Zero-reference repos are kept deliberately: the empty labelled rows at the
    bottom are the "not partaking" finding, and the chart's companion CSV is
    the downloadable source (no separate table duplicates it).
    """
    if engagement.empty or not (engagement["distinct_hips_merged"] > 0).any():
        return
    plot_bar(
        df=engagement.rename(columns={"distinct_hips_merged": "distinct HIPs"}),
        x_col="repo",
        y_col="distinct HIPs",
        title=f"{org} — repositories by distinct HIPs with merged PRs",
        output_path=charts_dir / "hip_repo_engagement.png",
    )


# Funnel bands darken with depth, drawn from the family's shared ramp.
_FUNNEL_SHADES = HIP_EVIDENCE_RAMP[:4]


def _plot_adoption_funnel(funnel: pd.DataFrame, org: str, charts_dir) -> None:
    """The recent-cohort funnel as a centred funnel silhouette, percent-only.

    Band width is the stage's share of proposed; the only number shown is the
    percentage — counts stay in the CSV download. The CSV keeps both cohorts.
    """
    recent = funnel[funnel["cohort"] == RECENT_COHORT]
    if recent.empty or int(recent.iloc[0]["hips"]) == 0:
        return
    plot_funnel(
        df=recent.rename(columns={"pct_of_proposed": "share"}),
        stage_col="stage",
        share_col="share",
        title=f"{org} — adoption funnel, specs {RECENT_COHORT.replace('created ', '')}",
        output_path=charts_dir / "hip_adoption_funnel.png",
        shades=_FUNNEL_SHADES,
    )


def _plot_activity_by_status(summary: pd.DataFrame, org: str, charts_dir) -> None:
    """Implementation evidence for the statuses where implementation is expected.

    "No evidence" splits by what HIP-1 implies: for an approved spec it means
    awaiting implementation (actionable); for a Final/Active spec the
    implementation merged by definition, so it is a citation gap instead.
    """
    summary = summary[summary["status_bucket"].isin(_BUCKET_LABELS)]
    if summary.empty:
        return
    counts = summary.groupby(["status_bucket", "evidence_class"]).size().unstack(fill_value=0).reindex(_BUCKET_LABELS)
    for column in ("merged", "open_only", "none"):
        if column not in counts:
            counts[column] = 0
    counts = counts.fillna(0).astype(int)
    frame = counts.reset_index().assign(bucket=lambda d: d["status_bucket"].map(_BUCKET_LABELS))
    is_approved = frame["status_bucket"] == "approved_accepted"
    frame["none_awaiting"] = frame["none"].where(is_approved, 0)
    frame["citation_gap"] = frame["none"].where(~is_approved, 0)
    labels = [
        "Merged implementation PRs",
        "Open PRs only",
        "No evidence — awaiting implementation",
        "No citing PRs found (implemented per HIP-1)",
    ]
    plot_stacked_bar(
        df=frame,
        x_col="bucket",
        stack_cols=["merged", "open_only", "none_awaiting", "citation_gap"],
        labels=labels,
        title=f"{org} — implementation evidence, approved & final specs",
        output_path=charts_dir / "hip_activity_by_status.png",
        colors={
            "Merged implementation PRs": "#2a78d6",
            "Open PRs only": "#86b6ef",
            "No evidence — awaiting implementation": "#eda100",
            "No citing PRs found (implemented per HIP-1)": "#c3c2b7",
        },
        sort_categorical=False,
        value_label="HIPs",
    )


def main(org: str = ORG) -> None:
    """Build the HIP-implementation evidence tables and charts for ``org``."""
    client, org_data_dir, org_charts_dir = org_context(org)

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

    _plot_engagement(engagement, org, org_charts_dir)
    _plot_adoption_funnel(tables["hip_adoption_funnel.csv"], org, org_charts_dir)
    _plot_activity_by_status(summary, org, org_charts_dir)

    logger.info(
        "HIP implementation: %d evidence rows across %d HIPs (%d unknown-number rows for review)",
        len(evidence),
        int((summary["evidence_class"] != "none").sum()) if not summary.empty else 0,
        len(unknown),
    )
