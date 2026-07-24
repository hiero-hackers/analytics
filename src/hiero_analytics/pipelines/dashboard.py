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
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

import pandas as pd

from hiero_analytics.config.paths import ORG, ORG_CHARTS_DIR, ORG_DATA_DIR, OUTPUTS_DIR, ensure_output_dirs
from hiero_analytics.dashboard_spec import (
    CHART_MACROS,
    CHART_METHODOLOGY,
    CHART_NOTES,
    CHARTS_GROUP,
    TABLE_FAMILIES,
    WIDE_CHARTS,
)
from hiero_analytics.domain.periods import ACTIVITY_PERIODS, DEFAULT_ACTIVITY_PERIOD
from hiero_analytics.domain.roles import ROLE_PRIORITY
from hiero_analytics.export.dashboard import build_dashboard_html

logger = logging.getLogger(__name__)


# A section counts as stale when its data is older than the scheduled refresh
# cadence (daily) plus slack for a slow run.
STALE_AFTER = timedelta(hours=36)


def _generated_at(path: Path) -> datetime | None:
    """Read an artifact's freshness sidecar, or None if absent/unreadable."""
    meta_path = Path(f"{path}.meta.json")
    if not meta_path.exists():
        return None
    try:
        return datetime.fromisoformat(json.loads(meta_path.read_text(encoding="utf-8"))["generated_at"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def _load(path: Path) -> pd.DataFrame:
    """Read a CSV, or an empty frame if it doesn't exist."""
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _load_period_variants(spec: dict, org_data_dir: Path) -> list[dict]:
    """Load a flagged spec's per-period CSVs, preserving variants with zero rows.

    Filenames derive from the spec's base ``file`` stem via the shared
    ``ACTIVITY_PERIODS``, so the base table and its period tabs cannot drift.
    """
    if not spec.get("periods"):
        return []
    stem = Path(spec["file"]).stem
    variants = []
    for period in ACTIVITY_PERIODS:
        path = org_data_dir / period.filename(stem)
        if path.exists():
            variants.append({"label": period.label, "data": pd.read_csv(path)})
    return variants


# Counted at each person's highest role across all repos, so the buckets
# partition the permission-holders (no double-counting someone who is, say,
# maintainer in one repo and triage in another). Seniority comes from the shared
# ROLE_PRIORITY; general_user is not a granted role, so it is excluded.
_GRANTED_ROLES = tuple(role for role in ROLE_PRIORITY if role != "general_user")


def _holders_by_highest_role(coverage: pd.DataFrame) -> dict[str, int]:
    """Distinct permission-holders per highest role, from ``role_coverage_all``."""
    if coverage.empty or "granted_role" not in coverage or "user" not in coverage:
        return {}
    df = coverage.assign(
        _u=coverage["user"].str.lower(),
        _r=coverage["granted_role"].map(ROLE_PRIORITY).fillna(0),
    )
    highest = df.sort_values("_r").groupby("_u")["granted_role"].last()
    counts = highest.value_counts()
    return {role: int(counts.get(role, 0)) for role in _GRANTED_ROLES}


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
        for caption, variant_specs in spec["files"]:
            # ``variant_specs`` is always ``[(tab label, filename), ...]`` — the spec
            # package canonicalizes single-file entries into one-variant lists.
            variants, note, methodology, wide = [], None, None, False
            for label, filename in variant_specs:
                src = _img_data_uri(chart_dir / filename)
                if src is None:
                    continue
                variant = {"label": label, "src": src}
                # Each variant carries its own note/methodology when it has one (the
                # maintainer-pipeline tabs are genuinely different charts). The chart-level
                # note stays the first available one, shared by variants without their own
                # (as with the All/Active pairs, where only the base image is annotated).
                if v_note := CHART_NOTES.get(filename):
                    variant["note"] = v_note
                if v_methodology := CHART_METHODOLOGY.get(filename):
                    variant["methodology"] = v_methodology
                variants.append(variant)
                note = note or variant.get("note")
                methodology = methodology or variant.get("methodology")
                wide = wide or filename in WIDE_CHARTS
            if not variants:
                continue
            chart = {"title": caption}
            if len(variants) == 1:
                # Only one image survived. If it came from a labelled multi-variant
                # entry, keep the label in the title so an active-only (or all-only)
                # survivor isn't silently shown as the base chart.
                only = variants[0]
                chart["title"] = f"{caption} — {only['label']}" if len(variant_specs) > 1 else caption
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
                "id": spec["id"],
                "title": spec["title"],
                "description": spec["description"],
                "group": CHARTS_GROUP,
                "charts": charts,
            }
            if spec.get("slideshow"):
                section["slideshow"] = True
            sections.append(section)
    return sections


def _contributors_metrics(loaded: dict[str, pd.DataFrame]) -> list:
    """Headline tiles for the Contributors macro."""
    return [("contributors", len(loaded["profiles"]))] if not loaded["profiles"].empty else []


def _governance_metrics(loaded: dict[str, pd.DataFrame]) -> list:
    """Headline tiles for the Governance macro."""
    metrics: list = []
    role_counts = _holders_by_highest_role(loaded["repo"])
    for role, label in (("maintainer", "maintainers"), ("committer", "committers"), ("triage", "triage")):
        if role in role_counts:
            metrics.append((label, role_counts[role]))
    if not loaded["gonedark"].empty:
        metrics.append(("quiet permission-holders (180d+)", len(loaded["gonedark"])))
    if "status" in loaded["teams"]:
        metrics.append(("quiet teams", int((loaded["teams"]["status"] == "quiet").sum())))
    return metrics


_METRICS_BY_MACRO = {"Contributors": _contributors_metrics, "Governance": _governance_metrics}


def _org_table_tab(family: ModuleType, org_name: str, org_data_dir: Path) -> dict | None:
    """Build one family's table tab for an org, or None if it has no data."""
    specs = family.SECTION_SPECS
    loaded = {spec["id"]: _load(org_data_dir / spec["file"]) for spec in specs}
    period_variants = {spec["id"]: _load_period_variants(spec, org_data_dir) for spec in specs if spec.get("periods")}

    # High-level → individual order (see the family's SECTION_ORDER), non-empty tables only.
    specs_by_id = {spec["id"]: spec for spec in specs}
    sections = []
    for section_id in family.SECTION_ORDER:
        spec = specs_by_id[section_id]
        variants = period_variants.get(section_id, [])
        if loaded[section_id].empty and not variants:
            continue
        section = {
            "id": spec["id"],
            "title": spec["title"],
            "description": spec["description"],
            "group": family.SECTION_GROUP_OF[section_id],
            # Optional "Suggest a correction" action link (e.g. the affiliations table).
            **({"action_url": spec["action_url"]} if spec.get("action_url") else {}),
            **({"action_label": spec["action_label"]} if spec.get("action_label") else {}),
        }
        # Freshness: stamp the section from its base CSV's sidecar (period
        # variants are written by the same run) and flag it when older than the
        # scheduled refresh — so a silently-reused stale CSV is visible.
        generated = _generated_at(org_data_dir / spec["file"])
        if generated is not None:
            section["data_as_of"] = generated.strftime("%Y-%m-%d %H:%M UTC")
            section["stale"] = datetime.now(UTC) - generated > STALE_AFTER
        if variants:
            section["variants"] = [
                {
                    "label": variant["label"],
                    "columns": spec["columns"],
                    "rows": variant["data"].to_dict("records"),
                }
                for variant in variants
            ]
            # Open on the shared default period, falling back to the first tab if that
            # period produced no file for this org.
            section["active_variant"] = next(
                (i for i, v in enumerate(section["variants"]) if v["label"] == DEFAULT_ACTIVITY_PERIOD.label),
                0,
            )
        else:
            section["columns"] = spec["columns"]
            section["rows"] = loaded[section_id].to_dict("records")
        sections.append(section)

    if not sections:
        return None  # this org has no data for this family
    metrics_builder = _METRICS_BY_MACRO.get(family.CHART_MACRO["name"])
    metrics = metrics_builder(loaded) if metrics_builder is not None else []
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

    macros = []
    for macro in CHART_MACROS:
        # A family with table sections renders them inside its own macro.
        family = TABLE_FAMILIES.get(macro["name"])
        org_tabs = []
        for org in orgs:
            table_tab = _org_table_tab(family, org, ORG_DATA_DIR / org) if family is not None else None
            table_sections = list(table_tab["sections"]) if table_tab is not None else []
            metrics = table_tab["metrics"] if table_tab is not None else []
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
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    output.write_text(build_dashboard_html(macros, generated_at=generated_at), encoding="utf-8")
    logger.info("Wrote %s — %d macro(s): %s", output, len(macros), ", ".join(m["name"] for m in macros))
