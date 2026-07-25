"""Prebuilt dashboard sections for the HIPs family: governance board + matrix.

The generic dashboard renderer assembles sections from the declarative specs in
``dashboard_spec``; a family whose view cannot be expressed as a table or a
chart gallery (here: a kanban-style governance board and a clickable coverage
matrix) declares this module via ``CUSTOM_SECTIONS_MODULE`` and gets
``build_sections`` called with its org's data directory.

Everything is derived mechanically from the pipeline's own CSVs — no fetching,
no interpretation. Structure and vocabulary (component columns, board columns,
status ordering) live in ``dashboard_spec.hips``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from hiero_analytics.config.charts import HIP_EVIDENCE_RAMP
from hiero_analytics.dashboard_spec import hips as hips_spec
from hiero_analytics.export.artifacts import csv_data_uri, load_csv, stamp_freshness
from hiero_analytics.provenance import resolve_provenance


def _stamped_csv_uri(frame: pd.DataFrame, view: str) -> str:
    """A download whose file names the view, the data watermark, and the code.

    These sections embed their CSV as a ``data:`` URI rather than exporting the
    rendered table through ``exportCSV``, so the JS preamble never runs — this
    reproduces it, keeping every CSV leaving the dashboard self-describing.
    """
    provenance = resolve_provenance()
    stamp = provenance.footer(record_count=len(frame))
    preamble = f"# Hiero analytics — {view}\n"
    if stamp:
        preamble += f"# {stamp}\n"
    return csv_data_uri(preamble + frame.to_csv(index=False))


# Merged-PR count -> colour bucket (class suffix). Bucketed so one 200-PR cell
# doesn't wash out the single-PR cells that carry the parity signal.
_RAMP_BUCKETS = ((2, "m1"), (5, "m2"), (15, "m3"), (40, "m4"))


def _cell_class(count: int) -> str:
    for ceiling, cls in _RAMP_BUCKETS:
        if count <= ceiling:
            return cls
    return "m5"


def _matrix_rows(activity: pd.DataFrame, summary: pd.DataFrame, components: list) -> tuple | None:
    """Assemble matrix data for every spec; returns (hips, merged, opened, meta, sdk_gaps)."""
    meta = summary.drop_duplicates("hip").set_index("hip")
    if meta.empty:
        return None
    merged = activity.pivot_table(index="hip", columns="repo", values="merged_prs", aggfunc="sum", fill_value=0)
    opened = activity.pivot_table(index="hip", columns="repo", values="open_prs", aggfunc="sum", fill_value=0)
    # Every spec gets a row — a HIP with no activity anywhere renders as a row
    # of dashes, which is itself the finding. Newest spec first.
    merged = merged.reindex(meta.index, fill_value=0)
    opened = opened.reindex(meta.index, fill_value=0)
    for repo, _label, _group in components:
        for frame in (merged, opened):
            if repo not in frame.columns:
                frame[repo] = 0
    sdk_gaps = {
        hip: [label for repo, label, group in components if group == "SDKs" and merged.at[hip, repo] == 0]
        for hip in merged.index
    }
    # Hottest specs first: total referencing activity (merged + open) across
    # the matrix components, descending; newest spec breaks ties. Untouched
    # specs sink to the bottom but stay visible.
    component_repos = [repo for repo, _label, _group in components]
    heat = merged[component_repos].sum(axis=1) + opened[component_repos].sum(axis=1)
    ordered = sorted(meta.index, key=lambda hip: (int(heat.at[hip]), hip), reverse=True)
    return ordered, merged, opened, meta, sdk_gaps


def _cell_evidence(evidence: pd.DataFrame, components: list) -> dict[str, list[dict]]:
    """Per-cell PR lists for the click-through panel, keyed "<hip>|<repo>".

    Every evidence row for a matrix component is included — qualified
    (not-counted) references too, flagged so the panel can show *why* a listed
    PR is excluded from the cell's count.
    """
    if evidence.empty:
        return {}
    component_repos = {repo for repo, _label, _group in components}
    cells: dict[str, list[dict]] = {}
    for row in evidence.itertuples():
        if row.repo not in component_repos:
            continue
        merged_at = row.pr_merged_at if isinstance(row.pr_merged_at, str) else ""
        qualifier = row.qualifier if isinstance(row.qualifier, str) else ""
        cells.setdefault(f"{row.hip}|{row.repo}", []).append(
            {
                "n": int(row.pr_number),
                "t": str(row.pr_title)[:100],
                "st": row.pr_state,
                "d": merged_at[:10],
                "m": row.match_sources,
                "q": qualifier,
                "x": str(row.snippet)[:90],
            }
        )
    for rows in cells.values():
        rows.sort(key=lambda item: item["d"], reverse=True)
    return cells


def _matrix_html(hips: list, merged, opened, meta, sdk_gaps, components: list, cell_evidence: dict) -> str:
    """Render the coverage matrix fragment (see .hipmx styles)."""
    e = html.escape
    bands: list[tuple[str, int]] = []
    for _repo, _label, group in components:
        if bands and bands[-1][0] == group:
            bands[-1] = (group, bands[-1][1] + 1)
        else:
            bands.append((group, 1))
    band_cells = "".join(f"<th colspan='{span}'>{e(group)}</th>" for group, span in bands)
    head = (
        f"<tr class='hipmx-grp'><th></th><th></th>{band_cells}<th></th></tr>"
        "<tr><th></th><th class='hipmx-status-h'>Governance</th>"
        + "".join(f"<th>{e(label)}</th>" for _repo, label, _group in components)
        + "<th>No SDK PRs found in</th></tr>"
    )
    sdk_total = sum(1 for _repo, _label, group in components if group == "SDKs")
    body = []
    for hip in hips:
        title = str(meta.at[hip, "hip_title"])[:60] if hip in meta.index else ""
        status = str(meta.at[hip, "hip_status"]) if hip in meta.index and "hip_status" in meta.columns else ""
        cells = []
        row_has_any = False
        for repo, _label, _group in components:
            merged_count = int(merged.at[hip, repo])
            open_count = int(opened.at[hip, repo])
            row_has_any = row_has_any or merged_count > 0 or open_count > 0
            click = ""
            if f"{hip}|{repo}" in cell_evidence:
                click = f" onclick=\"hipEv(this,'{hip}','{e(repo)}')\" tabindex='0' role='button'"
            if merged_count > 0:
                cells.append(
                    f"<td class='{_cell_class(merged_count)} ck'{click} "
                    f"title='{merged_count} merged PRs — click for the list'>{merged_count}</td>"
                )
            elif open_count > 0:
                cells.append(
                    f"<td class='mo ck'{click} title='{open_count} open PRs, none merged — click for the list'>"
                    "&#9675;</td>"
                )
            else:
                cells.append("<td class='m0' title='no PRs found'>&mdash;</td>")
        gaps = sdk_gaps[hip]
        if not gaps:
            gap_cell = "<td class='hipmx-gaps'><span class='ok'>&#10003; all SDKs</span></td>"
        elif not row_has_any:
            # A fully blank row shouldn't single out the SDKs — nothing was
            # found anywhere, services included.
            gap_cell = "<td class='hipmx-gaps'><span class='none'>no activity found</span></td>"
        elif len(gaps) == sdk_total:
            gap_cell = "<td class='hipmx-gaps'><span class='none'>no SDK activity found</span></td>"
        else:
            gap_cell = f"<td class='hipmx-gaps'>{e(' · '.join(gaps))}</td>"
        status_cell = f"<td class='hipmx-status'>{e(status)}</td>"
        body.append(
            f"<tr id='hipmx-row-{hip}'><th>HIP-{hip}<small>{e(title)}</small></th>"
            f"{status_cell}{''.join(cells)}{gap_cell}</tr>"
        )
    legend = (
        "<div class='hipmx-legend'>fewer"
        + "".join(f"<i style='background:{shade}'></i>" for shade in HIP_EVIDENCE_RAMP)
        + "more merged PRs&nbsp;&nbsp;&middot;&nbsp;&nbsp;&#9675; open PRs only"
        "&nbsp;&nbsp;&middot;&nbsp;&nbsp;&mdash; no reference found</div>"
    )
    # "</" must not appear inside the JSON script element.
    blob = json.dumps(cell_evidence, separators=(",", ":")).replace("</", "<\\/")
    panel = (
        "<div class='hipev' id='hip-ev-panel' hidden>"
        "<div class='hipev-head'><h3 id='hip-ev-title'></h3><span class='n' id='hip-ev-count'></span>"
        "<button type='button' class='dl' onclick='hipEvClose()'>Close</button></div>"
        "<ol id='hip-ev-list'></ol></div>"
        f"<script id='hip-ev-data' type='application/json'>{blob}</script>"
    )
    present = []
    if "hip_status" in meta.columns:
        seen = {str(meta.at[hip, "hip_status"]) for hip in hips if hip in meta.index}
        seen.discard("")
        present = [s for s in hips_spec.STATUS_READINESS_ORDER if s in seen]
        present += sorted(seen - set(present))
    pills = "".join(
        f"<button type='button' class='hipmx-fbtn' data-s='{e(s)}' onclick='hipMxStatus(this)'>{e(s)}</button>"
        for s in present
    )
    filters = (
        "<div class='hipmx-filters'>"
        "<input class='search' placeholder='Filter by HIP number or title\u2026' "
        "oninput='hipMxFilter(this.value)'>"
        f"<div class='hipmx-fbar'><span>Governance:</span>{pills}</div></div>"
    )
    return (
        f"{filters}"
        f"<div class='hipmx-wrap'><table class='hipmx' id='hip-matrix-tbl'><thead>{head}</thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>{legend}{panel}"
        f"<p class='count' id='hip-matrix-tbl-count'>{len(hips)} rows</p>"
    )


def _matrix_csv_uri(hips: list, merged, opened, meta, sdk_gaps, components: list) -> str:
    """The matrix as the reader sees it, wide format, as a data: CSV download.

    Cells carry the merged-PR count; an open-only cell downloads as
    ``open:<n>`` so the spreadsheet keeps the same three states as the view.
    The long-format source stays in hip_repo_activity.csv.
    """
    rows = []
    for hip in hips:
        row: dict[str, object] = {
            "hip": hip,
            "title": str(meta.at[hip, "hip_title"]) if hip in meta.index else "",
            "status": str(meta.at[hip, "hip_status"]) if hip in meta.index and "hip_status" in meta.columns else "",
        }
        for repo, label, _group in components:
            merged_count = int(merged.at[hip, repo])
            open_count = int(opened.at[hip, repo])
            row[label] = merged_count if merged_count > 0 else (f"open:{open_count}" if open_count > 0 else 0)
        row["no_merged_sdk_prs_in"] = " | ".join(sdk_gaps[hip])
        rows.append(row)
    return _stamped_csv_uri(pd.DataFrame(rows), "HIP implementation coverage matrix")


def _matrix_section(org: str, org_data_dir: Path) -> dict | None:
    """The HIPs tab's coverage matrix, or None when the org has no data for it."""
    components = hips_spec.MATRIX_COMPONENTS.get(org)
    if not components:
        return None
    activity = load_csv(org_data_dir / "hip_repo_activity.csv")
    summary = load_csv(org_data_dir / "hip_summary.csv")
    if activity.empty or summary.empty:
        return None
    selected = _matrix_rows(activity, summary, components)
    if selected is None:
        return None
    hips, merged, opened, meta, sdk_gaps = selected
    cell_evidence = _cell_evidence(load_csv(org_data_dir / "hip_pr_evidence.csv"), components)
    section = {
        "id": "hip-matrix",
        "title": "Implementation coverage matrix",
        "description": (
            "Merged PRs referencing each HIP, per component — every spec in the inventory: specs "
            "hottest first (most referencing activity), untouched specs at the bottom. The governance "
            "column is each spec's lifecycle status — often the explanation for a blank row (a "
            "deferred or review-stage spec has no implementation yet by design). A dash means no PR reference "
            "was found: a lead to check, not proof the work is "
            "missing (older specs and the younger SDKs are especially prone to missing references). "
            "Click a filled cell to list its PRs — every count is independently checkable. The "
            "long-format source ships as hip_repo_activity.csv alongside the wide download here."
        ),
        "group": "Charts",
        "badge": f"{len(hips)} HIPs",
        "download": {
            "name": "hip_coverage_matrix.csv",
            "href": _matrix_csv_uri(hips, merged, opened, meta, sdk_gaps, components),
        },
        "html": _matrix_html(hips, merged, opened, meta, sdk_gaps, components, cell_evidence),
    }
    stamp_freshness(section, org_data_dir / "hip_repo_activity.csv")
    return section


def _board_html(summary: pd.DataFrame) -> str:
    """The governance board: one column per lifecycle stage, chips per spec."""
    e = html.escape
    specs = summary.drop_duplicates("hip").sort_values("hip", ascending=False)
    columns: list[tuple[str, list]] = [(title, []) for title, _statuses in hips_spec.BOARD_COLUMNS]
    status_of = {title: set(statuses) for title, statuses in hips_spec.BOARD_COLUMNS}
    other: list = []
    for row in specs.itertuples():
        status = str(row.hip_status).strip()
        target = next((held for title, held in columns if status in status_of[title]), other)
        target.append(row)
    if other:
        columns.append(("Other", other))

    rendered = []
    for title, rows in columns:
        chips = "".join(
            f"<button type='button' class='hipchip' onclick='hipBoardPick(this,{row.hip})' "
            f'data-t="{e(str(row.hip_title))}" data-st="{e(str(row.hip_status))}" '
            f'title="{e(str(row.hip_title))} \u00b7 {e(str(row.hip_status))}">HIP-{row.hip}</button>'
            for row in rows
        )
        chips = chips or "<span class='none'>none</span>"
        rendered.append(
            f"<div class='hipboard-col'><h3>{e(title)} <span class='n'>{len(rows)}</span></h3>"
            f"<div class='hipboard-chips'>{chips}</div></div>"
        )
    info = (
        "<div class='hipboard-info' id='hip-board-info' hidden>"
        "<strong id='hip-board-info-num'></strong>"
        "<span class='t' id='hip-board-info-title'></span>"
        "<span class='chip chip-spec' id='hip-board-info-status'></span>"
        "<button type='button' class='dl' id='hip-board-info-jump'>Show in coverage matrix &darr;</button>"
        "</div>"
    )
    return f"<div class='hipboard'>{''.join(rendered)}</div>{info}"


def _board_csv_uri(summary: pd.DataFrame) -> str:
    """The board as CSV: one row per spec with its column assignment."""
    status_to_column = {status: title for title, statuses in hips_spec.BOARD_COLUMNS for status in statuses}
    specs = summary.drop_duplicates("hip").sort_values("hip", ascending=False)
    frame = pd.DataFrame(
        {
            "hip": specs["hip"],
            "title": specs["hip_title"],
            "status": specs["hip_status"],
            "board_column": specs["hip_status"].map(lambda s: status_to_column.get(str(s).strip(), "Other")),
        }
    )
    return _stamped_csv_uri(frame, "HIP governance board")


def _board_section(org_data_dir: Path) -> dict | None:
    """The 'where specs sit in governance' board, or None without data."""
    summary = load_csv(org_data_dir / "hip_summary.csv")
    if summary.empty:
        return None
    section = {
        "id": "hip-board",
        "title": "Where specs sit in governance",
        "description": (
            "Every HIP spec, placed by its current lifecycle status — the columns read left to right "
            "as the pipeline, and the Approved / Accepted column is the implementation triage queue. "
            "Statuses come from each spec's frontmatter; click a chip to see the spec's title, and "
            "jump from there to its row in the coverage matrix below."
        ),
        "group": "Charts",
        "badge": f"{summary['hip'].nunique()} specs",
        "download": {"name": "hip_governance_board.csv", "href": _board_csv_uri(summary)},
        "html": _board_html(summary),
    }
    stamp_freshness(section, org_data_dir / "hip_summary.csv")
    return section


def build_sections(org: str, org_data_dir: Path) -> list[dict]:
    """The HIPs tab's prebuilt sections: governance board, then coverage matrix.

    Returns an empty list when the org has no HIP data, so the tab simply
    omits them. The tab's "how to read this" explainer is the family's
    ``GLOSSARY_HTML``, rendered by the generic macro chrome, not a section.
    """
    matrix = _matrix_section(org, org_data_dir)
    if matrix is None:
        return []
    board = _board_section(org_data_dir)
    return [board, matrix] if board is not None else [matrix]


# Family-specific prebuilt sections, inserted between the charts and the tables.
