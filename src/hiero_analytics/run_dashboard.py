"""Render the analytics CSVs and charts into a single self-contained ``dashboard.html``.

A no-server local frontend organized as macro (dashboard family) → org → section.
It auto-discovers each org's data under ``outputs/data/org/<org>/`` (rendered as
tables) and charts under ``outputs/charts/org/<org>/`` (embedded as base64 images),
and renders only the sections that have a CSV or PNG — so an org with no governance
config simply shows the contributor tables, and a chart macro/tab appears only when
its images exist. Run after the data pipelines (last step in ``run_all``).
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import pandas as pd

from hiero_analytics.config.logging_config import setup_logging
from hiero_analytics.config.paths import ORG, ORG_CHARTS_DIR, ORG_DATA_DIR, OUTPUTS_DIR, ensure_output_dirs
from hiero_analytics.dashboard_spec import (
    CHART_MACROS,
    CHART_METHODOLOGY,
    CHART_NOTES,
    CHARTS_GROUP,
    MACRO_NAME,
    SECTION_GROUP_OF,
    SECTION_ORDER,
    SECTION_SPECS,
    WIDE_CHARTS,
)
from hiero_analytics.export.dashboard import build_dashboard_html

logger = logging.getLogger(__name__)


def _load(path: Path) -> pd.DataFrame:
    """Read a CSV, or an empty frame if it doesn't exist."""
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


# Counted at each person's highest role across all repos, so the three buckets
# partition the permission-holders (no double-counting someone who is, say,
# maintainer in one repo and triage in another).
_ROLE_RANK = {"triage": 1, "committer": 2, "maintainer": 3}


def _holders_by_highest_role(coverage: pd.DataFrame) -> dict[str, int]:
    """Distinct permission-holders per highest role, from ``role_coverage_all``."""
    if coverage.empty or "granted_role" not in coverage or "user" not in coverage:
        return {}
    df = coverage.assign(
        _u=coverage["user"].str.lower(),
        _r=coverage["granted_role"].map(_ROLE_RANK).fillna(0),
    )
    highest = df.sort_values("_r").groupby("_u")["granted_role"].last()
    counts = highest.value_counts()
    return {role: int(counts.get(role, 0)) for role in _ROLE_RANK}


def _img_data_uri(path: Path) -> str | None:
    """Base64 ``data:`` URI for a PNG, or None if missing (keeps the file self-contained)."""
    if not path.exists():
        return None
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _chart_sections(org: str, chart_specs: list[dict]) -> list[dict]:
    """Build image-gallery sections for an org from its chart specs (missing files skipped).

    A chart filename present in ``CHART_NOTES`` gets a "how to read this" expander
    under it; the note describes how to read the chart (not the current data), so it
    stays accurate across refreshes.
    """
    chart_dir = ORG_CHARTS_DIR / org
    sections = []
    for spec in chart_specs:
        charts = []
        for caption, target in spec["files"]:
            # ``target`` is a filename, or a list of (tab label, filename) variants
            # that render as an All / Active toggle on one chart.
            if isinstance(target, str):
                src = _img_data_uri(chart_dir / target)
                if src is None:
                    continue
                chart = {"title": caption, "src": src}
                if note := CHART_NOTES.get(target):
                    chart["note"] = note
                if methodology := CHART_METHODOLOGY.get(target):
                    chart["methodology"] = methodology
                if target in WIDE_CHARTS:
                    chart["wide"] = True
                charts.append(chart)
                continue

            variants, note, methodology, wide = [], None, None, False
            for label, filename in target:
                src = _img_data_uri(chart_dir / filename)
                if src is None:
                    continue
                variants.append({"label": label, "src": src})
                note = note or CHART_NOTES.get(filename)
                methodology = methodology or CHART_METHODOLOGY.get(filename)
                wide = wide or filename in WIDE_CHARTS
            if not variants:
                continue
            chart = {"title": caption}
            if len(variants) == 1:
                # Only one image survived. If it came from a labelled All / Active pair,
                # keep the label in the title so an active-only (or all-only) survivor
                # isn't silently shown as the base chart.
                only = variants[0]
                chart["title"] = f"{caption} — {only['label']}" if len(target) > 1 else caption
                chart["src"] = only["src"]
            else:
                chart["variants"] = variants
            if note:
                chart["note"] = note
            if methodology:
                chart["methodology"] = methodology
            if wide:
                chart["wide"] = True
            charts.append(chart)
        if charts:
            section = {
                "id": spec["id"], "title": spec["title"], "description": spec["description"],
                "group": CHARTS_GROUP, "charts": charts,
            }
            if spec.get("slideshow"):
                section["slideshow"] = True
            sections.append(section)
    return sections


def _org_tab(org_name: str, org_data_dir: Path) -> dict | None:
    """Build one org's tab from whatever CSVs it has, or None if it has no data."""
    loaded = {spec["id"]: _load(org_data_dir / spec["file"]) for spec in SECTION_SPECS}
    if loaded["profiles"].empty:
        return None  # no core contributor data for this org

    # High-level → individual order (see SECTION_ORDER), non-empty tables only.
    specs_by_id = {spec["id"]: spec for spec in SECTION_SPECS}
    sections = [
        {
            "id": spec["id"],
            "title": spec["title"],
            "description": spec["description"],
            "group": SECTION_GROUP_OF[section_id],
            "columns": spec["columns"],
            "rows": loaded[spec["id"]].to_dict("records"),
            # Optional "Suggest a correction" action link (e.g. the affiliations table).
            **({"action_url": spec["action_url"]} if spec.get("action_url") else {}),
            **({"action_label": spec["action_label"]} if spec.get("action_label") else {}),
        }
        for section_id in SECTION_ORDER
        if (spec := specs_by_id[section_id]) and not loaded[section_id].empty
    ]

    metrics = [("contributors", len(loaded["profiles"]))]
    role_counts = _holders_by_highest_role(loaded["repo"])
    for role, label in (("maintainer", "maintainers"), ("committer", "committers"), ("triage", "triage")):
        if role in role_counts:
            metrics.append((label, role_counts[role]))
    if not loaded["gonedark"].empty:
        metrics.append(("quiet permission-holders (180d+)", len(loaded["gonedark"])))
    if "status" in loaded["teams"]:
        metrics.append(("quiet teams", int((loaded["teams"]["status"] == "quiet").sum())))

    return {"org": org_name, "metrics": metrics, "sections": sections}


def _ordered_orgs() -> list[str]:
    """All orgs that have data or charts, the configured ORG first then alphabetical."""
    names: set[str] = set()
    for base in (ORG_DATA_DIR, ORG_CHARTS_DIR):
        if base.exists():
            names |= {p.name for p in base.iterdir() if p.is_dir()}
    return sorted(names, key=lambda n: (n != ORG, n))


def main() -> None:
    """Build the local macro→org→section HTML dashboard from CSV tables and chart PNGs."""
    ensure_output_dirs()
    ORG_DATA_DIR.mkdir(parents=True, exist_ok=True)

    orgs = _ordered_orgs()
    table_tabs = {org: tab for org in orgs if (tab := _org_tab(org, ORG_DATA_DIR / org)) is not None}

    macros = []
    for macro in CHART_MACROS:
        is_tables_macro = macro["name"] == MACRO_NAME
        org_tabs = []
        for org in orgs:
            table_sections: list[dict] = []
            metrics: list = []
            if is_tables_macro and org in table_tabs:
                table_sections = list(table_tabs[org]["sections"])
                metrics = table_tabs[org]["metrics"]
            # Charts first, then tables (high-level → individual within the tables).
            sections = _chart_sections(org, macro["charts"].get(org, [])) + table_sections
            if sections:
                org_tabs.append({"org": org, "metrics": metrics, "sections": sections})
        if org_tabs:
            macros.append({"name": macro["name"], "org_tabs": org_tabs})

    if not macros:
        # Still write the (empty) page so the file always exists — callers and the
        # Pages deploy expect it, and it matches the README's "no data → empty page".
        logger.warning("No org data or charts found; writing an empty dashboard")

    output = OUTPUTS_DIR / "dashboard.html"
    output.write_text(build_dashboard_html(macros), encoding="utf-8")
    logger.info(
        "Wrote %s — %d macro(s): %s", output, len(macros), ", ".join(m["name"] for m in macros)
    )


if __name__ == "__main__":
    setup_logging()
    main()
