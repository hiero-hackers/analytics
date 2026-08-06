"""HIP views the dashboard cannot express as a plain table or chart gallery.

Pure data assembly: the coverage matrix and the governance board are returned as
structures the data API ships and the web dashboard renders. Nothing here knows
about markup.

The matrix is deliberately shaped as a generic *entity x category* matrix —
banded columns, one row per entity, a value per cell, an optional trailing note —
so the same frontend component serves any future pivot, not just HIPs. What stays
HIP-specific is the arithmetic below: which repositories form the bands, how rows
are ordered by "heat", and how the SDK parity gap reads.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hiero_analytics.config.charts import HIP_EVIDENCE_RAMP
from hiero_analytics.dashboard_spec import hips as hips_spec
from hiero_analytics.export.artifacts import load_csv

# Merged-PR count -> ramp index. Bucketed so one 200-PR cell doesn't wash out the
# single-PR cells that carry the parity signal. Shipped to the frontend so it
# shades cells by exactly this rule.
RAMP_CEILINGS = (2, 5, 15, 40)

MATRIX_ID = "hip-matrix"
BOARD_ID = "hip-board"

MATRIX_TITLE = "Implementation coverage matrix"
MATRIX_DESCRIPTION = (
    "Merged PRs referencing each HIP, per component — every spec in the inventory: specs "
    "hottest first (most referencing activity), untouched specs at the bottom. The governance "
    "column is each spec's lifecycle status — often the explanation for a blank row (a "
    "deferred or review-stage spec has no implementation yet by design). A dash means no PR reference "
    "was found: a lead to check, not proof the work is "
    "missing (older specs and the younger SDKs are especially prone to missing references). "
    "Click a filled cell to list its PRs — every count is independently checkable. The "
    "long-format source ships as hip_repo_activity.csv alongside the wide download here."
)
BOARD_TITLE = "Where specs sit in governance"
BOARD_DESCRIPTION = (
    "Every HIP spec, placed by its current lifecycle status — the columns read left to right "
    "as the pipeline, and the Approved / Accepted column is the implementation triage queue. "
    "Statuses come from each spec's frontmatter; click a chip to see the spec's title, and "
    "jump from there to its row in the coverage matrix below."
)
# The trailing column: which SDKs have no merged PR for this spec.
GAP_HEADER = "No SDK PRs found in"
SDK_BAND = "SDKs"


def _bands(components: list) -> list[dict]:
    """Consecutive component groups as header bands, in first-appearance order."""
    bands: list[dict] = []
    for _repo, _label, group in components:
        if bands and bands[-1]["label"] == group:
            bands[-1]["span"] += 1
        else:
            bands.append({"label": group, "span": 1})
    return bands


def _matrix_frames(activity: pd.DataFrame, summary: pd.DataFrame, components: list) -> tuple | None:
    """Assemble matrix data for every spec; returns (hips, merged, opened, meta, sdk_gaps)."""
    meta = summary.drop_duplicates("hip").set_index("hip")
    if meta.empty:
        return None
    merged = activity.pivot_table(index="hip", columns="repo", values="merged_prs", aggfunc="sum", fill_value=0)
    opened = activity.pivot_table(index="hip", columns="repo", values="open_prs", aggfunc="sum", fill_value=0)
    # Every spec gets a row — a HIP with no activity anywhere renders as a row
    # of dashes, which is itself the finding.
    merged = merged.reindex(meta.index, fill_value=0)
    opened = opened.reindex(meta.index, fill_value=0)
    for repo, _label, _group in components:
        for frame in (merged, opened):
            if repo not in frame.columns:
                frame[repo] = 0
    sdk_gaps = {
        hip: [label for repo, label, group in components if group == SDK_BAND and merged.at[hip, repo] == 0]
        for hip in merged.index
    }
    # Hottest specs first: total referencing activity (merged + open) across the
    # matrix components, descending; newest spec breaks ties. Untouched specs
    # sink to the bottom but stay visible.
    component_repos = [repo for repo, _label, _group in components]
    heat = merged[component_repos].sum(axis=1) + opened[component_repos].sum(axis=1)
    ordered = sorted(meta.index, key=lambda hip: (int(heat.at[hip]), hip), reverse=True)
    return ordered, merged, opened, meta, sdk_gaps


def _gap_note(gaps: list[str], row_has_any: bool, sdk_total: int) -> dict:
    """The trailing parity cell: complete, absent everywhere, absent in SDKs, or a list."""
    if not gaps:
        return {"kind": "complete", "text": "✓ all SDKs"}
    if not row_has_any:
        # A fully blank row shouldn't single out the SDKs — nothing was found
        # anywhere, services included.
        return {"kind": "none", "text": "no activity found"}
    if len(gaps) == sdk_total:
        return {"kind": "none", "text": "no SDK activity found"}
    return {"kind": "partial", "text": " · ".join(gaps), "items": gaps}


def _statuses_present(hips: list, meta: pd.DataFrame) -> list[str]:
    """Governance filter values actually present, most ready first (spec order)."""
    if "hip_status" not in meta.columns:
        return []
    seen = {str(meta.at[hip, "hip_status"]) for hip in hips if hip in meta.index}
    seen.discard("")
    present = [status for status in hips_spec.STATUS_READINESS_ORDER if status in seen]
    return present + sorted(seen - set(present))


def coverage_matrix(org: str, org_data_dir: Path) -> dict | None:
    """The HIP implementation coverage matrix, or None when the org has no data."""
    components = hips_spec.MATRIX_COMPONENTS.get(org)
    if not components:
        return None
    activity = load_csv(org_data_dir / "hip_repo_activity.csv")
    summary = load_csv(org_data_dir / "hip_summary.csv")
    if activity.empty or summary.empty:
        return None
    assembled = _matrix_frames(activity, summary, components)
    if assembled is None:
        return None
    hips, merged, opened, meta, sdk_gaps = assembled
    sdk_total = sum(1 for _repo, _label, group in components if group == SDK_BAND)

    rows = []
    for hip in hips:
        cells = []
        row_has_any = False
        for repo, _label, _group in components:
            merged_count = int(merged.at[hip, repo])
            open_count = int(opened.at[hip, repo])
            row_has_any = row_has_any or merged_count > 0 or open_count > 0
            cells.append({"key": repo, "merged": merged_count, "open": open_count})
        rows.append(
            {
                "key": int(hip),
                "label": f"HIP-{hip}",
                # Titles are trimmed here, as the legacy row header did.
                "sublabel": str(meta.at[hip, "hip_title"])[:60] if hip in meta.index else "",
                "status": str(meta.at[hip, "hip_status"]) if hip in meta.index and "hip_status" in meta.columns else "",
                "cells": cells,
                "note": _gap_note(sdk_gaps[hip], row_has_any, sdk_total),
            }
        )

    return {
        "id": MATRIX_ID,
        "kind": "matrix",
        "group": "Status & coverage",
        "title": MATRIX_TITLE,
        "description": MATRIX_DESCRIPTION,
        "badge": f"{len(hips)} HIPs",
        "source": "hip_repo_activity.csv",
        "row_header": "Governance",
        "note_header": GAP_HEADER,
        "bands": _bands(components),
        "columns": [{"key": repo, "label": label, "band": group} for repo, label, group in components],
        "rows": rows,
        "ramp": list(HIP_EVIDENCE_RAMP),
        "ramp_ceilings": list(RAMP_CEILINGS),
        "filters": _statuses_present(hips, meta),
        "evidence_section": "hip-evidence",
    }


def governance_board(org_data_dir: Path) -> dict | None:
    """Specs placed in lifecycle columns, or None without data."""
    summary = load_csv(org_data_dir / "hip_summary.csv")
    if summary.empty:
        return None
    specs = summary.drop_duplicates("hip").sort_values("hip", ascending=False)
    columns: list[dict] = [{"title": title, "items": []} for title, _statuses in hips_spec.BOARD_COLUMNS]
    status_of = {title: set(statuses) for title, statuses in hips_spec.BOARD_COLUMNS}
    # Statuses missing from every tuple land in a trailing "Other" column so new
    # ones stay visible rather than vanishing.
    other: list = []
    for row in specs.itertuples():
        status = str(row.hip_status).strip()
        target = next(
            (column["items"] for column in columns if status in status_of[column["title"]]),
            other,
        )
        target.append({"key": int(row.hip), "label": f"HIP-{row.hip}", "title": str(row.hip_title), "status": status})
    if other:
        columns.append({"title": "Other", "items": other})

    return {
        "id": BOARD_ID,
        "kind": "board",
        "group": "Status & coverage",
        "title": BOARD_TITLE,
        "description": BOARD_DESCRIPTION,
        "badge": f"{specs['hip'].nunique()} specs",
        "source": "hip_summary.csv",
        "columns": columns,
        "target_view": MATRIX_ID,
    }


def build_views(org: str, org_data_dir: Path) -> list[dict]:
    """The HIPs tab's bespoke views: governance board, then coverage matrix.

    Empty when the org has no HIP data, so the tab simply omits them.
    """
    matrix = coverage_matrix(org, org_data_dir)
    if matrix is None:
        return []
    board = governance_board(org_data_dir)
    return [board, matrix] if board is not None else [matrix]
