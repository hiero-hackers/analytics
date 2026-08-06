"""Emit the versioned JSON data API from the produced analytics tables.

The CSVs under ``outputs/data/org/<org>/`` are the pipelines' artifacts; this
module graduates them into a *contract*: one JSON document per spec-listed
section plus a top-level manifest, under ``outputs/data/api/<version>/``. Any
frontend (the current dashboard's successor, a notebook, someone else's tool)
can consume the API without knowing how the tables were produced — and the
producer↔spec agreement is enforced here, loudly, instead of degrading into
blank dashboard columns.

Layout::

    outputs/data/api/v1/
        manifest.json                  # orgs, sections, charts, provenance
        <org>/<section-id>.json        # columns, rows, period variants

Contract: every column a section spec declares must exist in the produced
CSV. A missing column raises :class:`DataApiContractError` and fails the run —
a renamed pipeline output becomes a red build, not a silently empty column.
The published rows carry *exactly* the declared columns: an extra column a
pipeline writes stays in the CSV rather than becoming an undeclared part of
the API's shape.

Versioning: breaking shape changes (renamed keys, removed sections) bump the
version directory so consumers migrate deliberately; additive changes land in
place. ``v1`` is additive-only from here.
"""

from __future__ import annotations

import importlib
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from PIL import Image

# Paths are read through the module at call time (never bound at import), so
# the contract tests' path redirection applies no matter the import order.
from hiero_analytics.config import paths
from hiero_analytics.dashboard_spec import (
    CHART_MACROS,
    CHART_METHODOLOGY,
    CHART_NOTES,
    CUSTOM_VIEW_MODULES,
    MACRO_ABSENT_NOTES,
    MACRO_GLOSSARIES,
    MACRO_GROUP_ORDER,
    MACRO_PARENTS,
    METRIC_ANNOTATIONS,
    PROJECT_ISSUES_URL,
    TABLE_FAMILIES,
    WIDE_CHARTS,
)
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.export.csv_safety import sanitize_csv_text
from hiero_analytics.export.macro_metrics import macro_metrics
from hiero_analytics.provenance import resolve_provenance

logger = logging.getLogger(__name__)

API_VERSION = "v1"

# The rolling windows the API publishes as period variants. The all-time period
# is deliberately excluded: a document's own ``rows`` already are the all-time
# table, so emitting it again duplicated every such row in the payload and gave
# the dashboard two identical "All time" tabs (the selector's own no-period
# state, plus this variant).
API_PERIODS = tuple(period for period in ACTIVITY_PERIODS if period.days is not None)

# A section counts as stale when its data is older than the scheduled refresh
# cadence plus slack for a slow run. The analytics refresh runs every 5 days,
# and we add 12 hours of slack for slow or delayed runs. The legacy dashboard
# imports this value so the two cannot drift.
STALE_AFTER = timedelta(hours=132)


class DataApiContractError(RuntimeError):
    """A produced table is missing columns its dashboard spec declares."""


def _api_dir() -> Path:
    """Read the output root at call time so tests can redirect ``DATA_DIR``."""
    return paths.DATA_DIR / "api" / API_VERSION


def _read_meta(csv_path: Path) -> dict:
    """The artifact's provenance sidecar, or an empty dict if absent/unreadable."""
    meta_path = Path(f"{csv_path}.meta.json")
    if not meta_path.exists():
        return {}
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _stamp_freshness(document: dict, csv_path: Path) -> None:
    """Attach ``generated_at``/``stale`` from the source CSV's sidecar, if any."""
    generated_at = _read_meta(csv_path).get("generated_at")
    if not generated_at:
        return
    document["generated_at"] = generated_at
    try:
        generated = datetime.fromisoformat(generated_at)
    except ValueError:
        # Ship the raw stamp without a staleness verdict, but say so — a sidecar
        # that stops parsing should show up in the run log, not vanish.
        logger.warning("Unparseable generated_at %r in sidecar for %s", generated_at, csv_path)
        return
    # Sidecars are written UTC-aware, but a hand-edited or legacy one may be
    # naive; assume UTC rather than letting the subtraction raise TypeError and
    # fail the entire emit over one stamp.
    if generated.tzinfo is None:
        logger.warning("Naive generated_at %r in sidecar for %s; assuming UTC", generated_at, csv_path)
        generated = generated.replace(tzinfo=UTC)
    document["stale"] = datetime.now(UTC) - generated > STALE_AFTER


def _rows(frame: pd.DataFrame) -> list[dict]:
    """DataFrame rows as JSON-safe records (NaN -> null, datetimes -> ISO)."""
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _contract_frame(section: dict, frame: pd.DataFrame, where: str) -> pd.DataFrame:
    """Enforce the producer↔spec column contract, then narrow to the spec.

    ``where`` names the artifact for the error message — the base table or one
    of its period variants.

    The returned frame carries exactly the declared columns, in spec order. The
    API is a versioned contract, so a column a pipeline happens to write must
    not ride along into the published shape: under ``v1``'s additive-only rule
    an accidental key becomes a promise we cannot withdraw. Nothing is hidden —
    the produced CSV under ``outputs/data/org/`` remains the full artifact.
    """
    declared = [column[0] for column in section["columns"]]
    missing = [key for key in declared if key not in frame.columns]
    if missing:
        raise DataApiContractError(
            f"{where} is missing spec-declared column(s) {missing}; produced columns: {list(frame.columns)}"
        )
    return frame[declared]


def _period_variants(section: dict, org: str, org_data_dir: Path) -> dict[str, list[dict]]:
    """Per-period row sets for a ``periods``-flagged section, keyed by period key."""
    if not section.get("periods"):
        return {}
    stem = Path(section["file"]).stem
    variants: dict[str, list[dict]] = {}
    for period in API_PERIODS:
        path = org_data_dir / period.filename(stem)
        if path.exists():
            # Period files carry the same columns as their base table, so they
            # get the same contract: a renamed column here would otherwise ship
            # a silently incomplete row shape while the base table passed.
            frame = _contract_frame(section, pd.read_csv(path), f"{org}/{path.name}")
            variants[period.key] = _rows(frame)
    return variants


def _section_document(section: dict, group_of: dict, org: str, org_data_dir: Path) -> dict | None:
    """Build one section's API document, or None when its table wasn't produced."""
    csv_path = org_data_dir / section["file"]
    if not csv_path.exists():
        return None
    frame = _contract_frame(section, pd.read_csv(csv_path), f"{org}/{section['file']}")
    document = {
        "id": section["id"],
        "title": section["title"],
        "description": section["description"],
        "group": group_of.get(section["id"], ""),
        "source": section["file"],
        # Column entries mirror the spec: (key, label) plus an optional display
        # format — serialized as objects so consumers need no tuple knowledge.
        "columns": [
            {"key": column[0], "label": column[1], **({"format": column[2]} if len(column) > 2 else {})}
            for column in section["columns"]
        ],
        "rows": _rows(frame),
        "row_count": len(frame),
    }
    # A section's call to action (e.g. the affiliations table's "Suggest a
    # correction" issue link) travels with the document.
    if action_url := section.get("action_url"):
        document["action"] = {"url": action_url, "label": section.get("action_label", "Suggest a correction")}
    _stamp_freshness(document, csv_path)
    if periods := _period_variants(section, org, org_data_dir):
        document["periods"] = periods
    return document


def _chart_variant(org: str, chart_dir: Path, label: str, filename: str) -> dict:
    """One chart variant, carrying its pixel size when it can be read.

    The dimensions let the browser reserve the image's box before the PNG
    arrives, so a page of charts doesn't shift under the reader as they load.
    An unreadable PNG simply ships without them rather than failing the emit.
    """
    variant = {"label": label, "file": f"charts/org/{org}/{filename}"}
    try:
        with Image.open(chart_dir / filename) as image:
            variant["width"], variant["height"] = image.width, image.height
    except (OSError, ValueError):
        logger.warning("Could not read dimensions for %s", filename)
    return variant


# Aspect ratio beyond which a chart cannot survive a ~340px gallery cell: a
# panoramic chart (many bars along x) gets illegibly narrow bars, so it earns
# the full-row scroll treatment `wide` renders as. Derived from the actual PNG
# rather than hand-set per chart, so a pipeline that changes a chart's shape
# changes its layout with it; the spec's WIDE_CHARTS remains as the manual
# override. (Tall charts are the frontend's call — it has the same dimensions
# per variant and spans them without the scroll box.)
_WIDE_ASPECT_ABOVE = 2.0


def _needs_full_row(variants: list[dict]) -> bool:
    """Whether any variant is panoramic enough to demand the full-row scroll."""
    for variant in variants:
        width, height = variant.get("width"), variant.get("height")
        if width and height and width / height >= _WIDE_ASPECT_ABOVE:
            return True
    return False


def _org_chart_sections(org: str, org_data_dir: Path, org_dir: Path) -> list[dict]:
    """The org's chart sections with their full presentation structure.

    Mirrors what the legacy dashboard renders: each spec entry is a card with
    a title and description; each chart inside carries its variant tabs
    (e.g. All / Active 90d), its "how to read this" note, its step-by-step
    methodology, and the wide flag (rendered as a horizontal scroll). Only
    variants whose PNG was actually produced are listed.
    """
    chart_dir = paths.ORG_CHARTS_DIR / org
    sections = []
    for macro in CHART_MACROS:
        # "*" declares org-independent cards: they apply to any org, and the
        # per-variant existence filter below drops whatever an org's pipelines
        # didn't produce. An explicit org key overrides the wildcard.
        for spec in macro["charts"].get(org) or macro["charts"].get("*", []):
            charts = []
            for caption, variant_specs in spec["files"]:
                variants = [
                    _chart_variant(org, chart_dir, label, filename)
                    for label, filename in variant_specs
                    if (chart_dir / filename).exists()
                ]
                if not variants:
                    continue
                filenames = [filename for _label, filename in variant_specs]
                chart = {"title": caption, "variants": variants}
                if note := next((CHART_NOTES[f] for f in filenames if f in CHART_NOTES), None):
                    chart["note"] = note
                if methodology := next((CHART_METHODOLOGY[f] for f in filenames if f in CHART_METHODOLOGY), None):
                    chart["methodology"] = methodology
                # Two different treatments: hand-flagged WIDE_CHARTS have many
                # bars and need the horizontal scroll box; a merely wide-aspect
                # chart (few bars, long legend) just spans the full row, scaled
                # to fit — a scroll box would crop its title and legend.
                if any(f in WIDE_CHARTS for f in filenames):
                    chart["wide"] = True
                elif _needs_full_row(variants):
                    chart["full_row"] = True
                charts.append(chart)
            if charts:
                section = {
                    "id": spec["id"],
                    "macro": macro["name"],
                    "title": spec["title"],
                    "description": spec["description"],
                    "charts": charts,
                }
                if spec.get("slideshow"):
                    section["slideshow"] = True
                # Every chart card belongs to a named section group — the tab
                # renders as ordered groups (see the manifest's group_order),
                # never a generic "Charts" block. A card without an explicit
                # group is its own section, named by its title.
                section["group"] = spec.get("group") or spec["title"]
                _attach_download(section, spec, org, org_data_dir, org_dir)
                sections.append(section)
    return sections


def _attach_download(section: dict, spec: dict, org: str, org_data_dir: Path, org_dir: Path) -> None:
    """Copy a chart's declared companion CSV into the API tree and reference it.

    The Pages deploy publishes only the API tree and the chart PNGs, so a CSV
    the dashboard offers for download has to travel inside the API. The copy
    keeps the raw ``outputs/data`` artifact untouched.
    """
    csv_name = spec.get("csv")
    if not csv_name:
        return
    csv_path = org_data_dir / csv_name
    if not csv_path.exists():
        return
    # This copy exists to be downloaded and opened in a spreadsheet, so it is
    # neutralised against formula injection; the artifact under outputs/data
    # stays verbatim for pandas consumers.
    (org_dir / csv_name).write_text(sanitize_csv_text(csv_path.read_text(encoding="utf-8")), encoding="utf-8")
    download = {"name": csv_name, "path": f"{org}/{csv_name}"}
    if generated_at := _read_meta(csv_path).get("generated_at"):
        download["generated_at"] = generated_at
    section["download"] = download


def _org_views(org: str, org_data_dir: Path, org_dir: Path) -> list[dict]:
    """Emit each family's bespoke views (board, matrix, …) as documents.

    A family that needs more than tables and chart galleries declares a module
    exposing ``build_views(org, org_data_dir)``; each returned view is written
    as its own document (they can run to hundreds of rows) and listed in the
    manifest by reference, like sections.
    """
    refs = []
    for macro_name, module_path in CUSTOM_VIEW_MODULES.items():
        module = importlib.import_module(module_path)
        for view in module.build_views(org, org_data_dir):
            view["macro"] = macro_name
            if source := view.get("source"):
                _stamp_freshness(view, org_data_dir / source)
            (org_dir / f"{view['id']}.json").write_text(json.dumps(view, indent=1), encoding="utf-8")
            refs.append(
                {
                    "id": view["id"],
                    "macro": macro_name,
                    "kind": view["kind"],
                    "title": view["title"],
                    "path": f"{org}/{view['id']}.json",
                }
            )
    return refs


def _metric_tiles(family, org_data_dir: Path) -> list[dict]:
    """The macro's headline tiles as JSON objects, [] when none apply.

    Each carries its "how to read this" note and derivation steps: a tile is a
    lone number with nothing to click through to, so it needs the same
    explanation a chart gets.
    """
    return [
        {"label": label, "value": value, **METRIC_ANNOTATIONS.get(label, {})}
        for label, value in macro_metrics(family.CHART_MACRO["name"], family, org_data_dir)
    ]


def _orgs_with_data() -> list[str]:
    """Orgs with produced tables, primary org first for stable manifests."""
    if not paths.ORG_DATA_DIR.exists():
        return []
    orgs = sorted(path.name for path in paths.ORG_DATA_DIR.iterdir() if path.is_dir())
    return [paths.ORG, *[org for org in orgs if org != paths.ORG]] if paths.ORG in orgs else orgs


def emit_data_api() -> Path:
    """Write the JSON API for every org with data; returns the manifest path.

    Enforces the column contract for each emitted section — a spec-listed
    table with missing columns fails the emit (and therefore the run).
    """
    api_dir = _api_dir()
    api_dir.mkdir(parents=True, exist_ok=True)

    provenance = resolve_provenance()
    manifest: dict = {
        # Every macro's "how to read this" explainer, keyed by macro name.
        # Each lists only what its own tab shows; the shared prose behind the
        # column definitions lives in dashboard_spec.glossary.
        "macro_glossaries": MACRO_GLOSSARIES,
        # Sub-tab macros, macro name -> umbrella tab name. The frontend shows
        # one top-level tab per umbrella with a second tab row for its members.
        "macro_parents": MACRO_PARENTS,
        # Why a tab may be empty for an org — shown in place of a blank tab.
        "macro_absent_notes": MACRO_ABSENT_NOTES,
        # Macro name -> ordered section-group names; the frontend renders each
        # tab as this sequence of named sections (views + charts + tables).
        "group_order": MACRO_GROUP_ORDER,
        # Family display order. The frontend otherwise derives tab order from
        # the sections lists, which puts a chart-only macro after every
        # table-bearing one regardless of where its family sits.
        "macro_order": [macro["name"] for macro in CHART_MACROS],
        # Display labels for the rolling activity periods ("30d" -> "30 days").
        "period_labels": {period.key: period.label for period in API_PERIODS},
        # Where the dashboard footer points "spotted something wrong?".
        "issues_url": PROJECT_ISSUES_URL,
        # The WIP banner is data-side policy like everything else the manifest
        # carries: flip to False here to retire it, no frontend change needed.
        "wip": True,
        "version": API_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "provenance": {
            "git_sha": provenance.git_sha,
            "data_as_of": provenance.data_as_of.isoformat() if provenance.data_as_of else None,
        },
        "orgs": {},
    }

    for org in _orgs_with_data():
        org_dir = api_dir / org
        org_dir.mkdir(parents=True, exist_ok=True)
        org_data_dir = paths.ORG_DATA_DIR / org
        sections = []
        for family in TABLE_FAMILIES.values():
            group_of = family.SECTION_GROUP_OF
            # SECTION_ORDER, not SECTION_SPECS: the order groups sections
            # contiguously (high-level -> individual), exactly as the legacy
            # dashboard renders — spec-declaration order interleaves groups.
            specs_by_id = {spec["id"]: spec for spec in family.SECTION_SPECS}
            for section_id in family.SECTION_ORDER:
                section = specs_by_id[section_id]
                document = _section_document(section, group_of, org, org_data_dir)
                if document is None:
                    continue
                document["macro"] = family.CHART_MACRO["name"]
                path = org_dir / f"{document['id']}.json"
                path.write_text(json.dumps(document, indent=1), encoding="utf-8")
                sections.append(
                    {
                        "id": document["id"],
                        "macro": document["macro"],
                        "title": document["title"],
                        "row_count": document["row_count"],
                        "path": f"{org}/{document['id']}.json",
                    }
                )
        chart_sections = _org_chart_sections(org, org_data_dir, org_dir)
        views = _org_views(org, org_data_dir, org_dir)
        if sections or chart_sections or views:
            metrics = {
                family.CHART_MACRO["name"]: tiles
                for family in TABLE_FAMILIES.values()
                if (tiles := _metric_tiles(family, org_data_dir))
            }
            manifest["orgs"][org] = {
                "sections": sections,
                "chart_sections": chart_sections,
                "views": views,
                "metrics": metrics,
            }

    manifest_path = api_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    section_count = sum(len(entry["sections"]) for entry in manifest["orgs"].values())
    logger.info(
        "Data API %s: %d section document(s) across %d org(s) -> %s",
        API_VERSION,
        section_count,
        len(manifest["orgs"]),
        api_dir,
    )
    return manifest_path
