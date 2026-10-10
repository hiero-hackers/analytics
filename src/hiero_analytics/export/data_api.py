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

Role variants: a section whose spec declares ``variants`` publishes each one
under ``variants`` and hoists the first to the top level, so the dashboard can
render them as one tabbed card while a consumer that predates the field still
reads the same ``columns``/``rows``. Each absorbed variant keeps its own
document and its own manifest entry, tagged ``absorbed_by`` — merging two cards
into one must not withdraw ids that consumers and shared links already resolve.

Versioning: breaking shape changes (renamed keys, removed sections) bump the
version directory so consumers migrate deliberately; additive changes land in
place. ``v1`` is additive-only, with one recorded exception: in October 2026
chart variants lost ``file``, ``width`` and ``height`` (the PNG a variant used
to name, and its pixel size) when chart PNGs stopped being produced. No
consumer read those fields — the dashboard had drawn every chart from
``interactive`` since the chart documents landed — so the version stayed at
``v1`` rather than forcing a migration over a field nothing used. Every listed
variant now carries ``interactive``.
"""

from __future__ import annotations

import importlib
import json
import logging
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

# Paths are read through the module at call time (never bound at import), so
# the contract tests' path redirection applies no matter the import order.
from hiero_analytics.config import paths
from hiero_analytics.dashboard_spec import (
    CHART_MACROS,
    CHART_METHODOLOGY,
    CHART_NOTES,
    CUSTOM_VIEW_MODULES,
    FULL_ROW_CHARTS,
    MACRO_ABSENT_NOTES,
    MACRO_GLOSSARIES,
    MACRO_GROUP_ORDER,
    MACRO_PARENTS,
    MACRO_SUMMARIES,
    METRIC_ANNOTATIONS,
    PROJECT_ISSUES_URL,
    TABLE_FAMILIES,
    WIDE_CHARTS,
    table_variants,
)
from hiero_analytics.domain.periods import ACTIVITY_PERIODS
from hiero_analytics.export.chart_data import chart_document, is_empty
from hiero_analytics.export.csv_safety import sanitize_csv_text
from hiero_analytics.export.entity_views import build_entity_documents
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
# cadence plus slack for a slow run. The analytics refresh runs daily, and we
# add 12 hours of slack for slow or delayed runs, so one missed night shows.
# The legacy dashboard imports this value so the two cannot drift.
STALE_AFTER = timedelta(hours=36)


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


def _freshness(csv_path: Path) -> dict:
    """``generated_at``/``stale`` from the source CSV's sidecar; {} when it has none."""
    generated_at = _read_meta(csv_path).get("generated_at")
    if not generated_at:
        return {}
    try:
        generated = datetime.fromisoformat(generated_at)
    except ValueError:
        # Ship the raw stamp without a staleness verdict, but say so — a sidecar
        # that stops parsing should show up in the run log, not vanish.
        logger.warning("Unparseable generated_at %r in sidecar for %s", generated_at, csv_path)
        return {"generated_at": generated_at}
    # Sidecars are written UTC-aware, but a hand-edited or legacy one may be
    # naive; assume UTC rather than letting the subtraction raise TypeError and
    # fail the entire emit over one stamp.
    if generated.tzinfo is None:
        logger.warning("Naive generated_at %r in sidecar for %s; assuming UTC", generated_at, csv_path)
        generated = generated.replace(tzinfo=UTC)
    return {"generated_at": generated_at, "stale": datetime.now(UTC) - generated > STALE_AFTER}


def _stamp_freshness(document: dict, csv_path: Path) -> None:
    """Attach ``generated_at``/``stale`` from the source CSV's sidecar, if any."""
    document.update(_freshness(csv_path))


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


def _variant_document(variant: dict, org: str, org_data_dir: Path) -> dict | None:
    """One variant's payload, or None when its table wasn't produced."""
    csv_path = org_data_dir / variant["file"]
    if not csv_path.exists():
        return None
    frame = _contract_frame(variant, pd.read_csv(csv_path), f"{org}/{variant['file']}")
    document = {
        "id": variant["id"],
        "title": variant["title"],
        "description": variant["description"],
        "source": variant["file"],
        # Column entries mirror the spec: (key, label) plus an optional display
        # format — serialized as objects so consumers need no tuple knowledge.
        "columns": [
            {"key": column[0], "label": column[1], **({"format": column[2]} if len(column) > 2 else {})}
            for column in variant["columns"]
        ],
        "rows": _rows(frame),
        "row_count": len(frame),
    }
    if label := variant.get("label"):
        document["label"] = label
    # A section's call to action (e.g. the affiliations table's "Suggest a
    # correction" issue link) travels with the document.
    if action_url := variant.get("action_url"):
        document["action"] = {"url": action_url, "label": variant.get("action_label", "Suggest a correction")}
    _stamp_freshness(document, csv_path)
    if periods := _period_variants(variant, org, org_data_dir):
        document["periods"] = periods
    return document


def _section_document(section: dict, group_of: dict, org: str, org_data_dir: Path) -> dict | None:
    """Build one section's API document, or None when its table wasn't produced.

    A role-tabbed section publishes each variant under ``variants`` *and*
    hoists the first one to the top level, so a v1 consumer that knows nothing
    about variants still reads the same ``columns``/``rows`` it always did.
    """
    documents = [
        document
        for variant in table_variants(section)
        if (document := _variant_document(variant, org, org_data_dir)) is not None
    ]
    if not documents:
        return None
    # The card's heading is the section's own, role-neutral title; each variant
    # keeps the role-specific one for its standalone document and CSV export.
    document = {
        **documents[0],
        "id": section["id"],
        "title": section["title"],
        "group": group_of.get(section["id"], ""),
    }
    # One surviving variant is an ordinary single-table section: no tab row to
    # render, so no reason to ship the wrapper.
    if len(documents) > 1:
        document["variants"] = documents
    return document


def variant_annotations(chart_id: str) -> dict:
    """The note and methodology declared for one chart variant, keyed by chart id.

    The lookup is per *variant*, not per card: a card's tabs show different
    populations (maintainers / committers) or different spans, and each has its
    own entry in the spec. Selecting one entry per card — as the emitter used
    to — made every entry belonging to a non-first tab unreachable.
    """
    annotations = {}
    if note := CHART_NOTES.get(chart_id):
        annotations["note"] = note
    if methodology := CHART_METHODOLOGY.get(chart_id):
        annotations["methodology"] = methodology
    return annotations


def _source_files(source: dict, org_data_dir: Path) -> list[Path]:
    """Every CSV a chart source reads: its dataset and, for networks, the edge list."""
    files = [org_data_dir / source["file"]]
    if edges := source.get("edges_file"):
        files.append(org_data_dir / edges)
    return files


def _has_rows(csv_path: Path) -> bool:
    """Whether the dataset's sidecar records at least one row.

    A pipeline writes the CSV even when the analysis found nothing (so a
    consumer can tell "no data" from "not run"). Skipping such a dataset here
    also spares ``chart_document`` a header-less file. A sidecar without
    ``record_count`` (written by an older ``save_dataframe``) counts as
    populated; the document's own emptiness check below is the arbiter then.
    """
    return _read_meta(csv_path).get("record_count", 1) > 0


def _chart_variant(org: str, org_dir: Path, spec: dict, org_data_dir: Path, label: str, chart_id: str) -> dict | None:
    """One chart variant with its chart document written, or None when its dataset is absent.

    A variant is listed exactly when the CSV its spec names exists and the
    document built from it shows something: a span tab whose window holds
    nothing stays off the card, as it did when nothing was drawn for it. The
    output contract tests make the spec and the pipelines agree on the
    filenames. The document gets the variant's own note (a
    source's ``note`` describes the interactive view and wins over the card's)
    and is written under the chart id, which the dashboard also uses to key the
    view's URL state — so ids are stable identifiers, not derived names.
    """
    source = spec["sources"][chart_id]
    files = _source_files(source, org_data_dir)
    csv_path = files[0]
    if not all(path.exists() for path in files) or not _has_rows(csv_path):
        return None
    try:
        document = chart_document(source, csv_path, org, _read_meta(csv_path).get("generated_at"))
    except (ValueError, TypeError, OSError) as exc:
        raise DataApiContractError(f"Invalid chart dataset {org}/{source['file']}: {exc}") from exc
    if is_empty(document, source):
        return None
    _stamp_freshness(document, csv_path)
    document = {**variant_annotations(chart_id), **document, "id": chart_id}
    target = org_dir / "charts" / f"{chart_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=1, allow_nan=False), encoding="utf-8")
    return {
        "label": label,
        "interactive": {"kind": document["kind"], "path": f"{org}/charts/{target.name}"},
        **variant_annotations(chart_id),
    }


def _org_chart_sections(org: str, org_data_dir: Path, org_dir: Path) -> list[dict]:
    """The org's chart sections with their full presentation structure.

    Each spec entry is a card with a title and description; each chart inside
    carries its variant tabs (e.g. All / Active 90d), its "how to read this"
    note, its step-by-step methodology, and its layout flag. Only variants
    whose dataset was produced are listed, so a card whose pipeline did not
    run for this org drops out rather than rendering empty.
    """
    sections = []
    for macro in CHART_MACROS:
        # "*" declares org-independent cards: they apply to any org, and the
        # per-variant existence filter below drops whatever an org's pipelines
        # didn't produce. An explicit org key overrides the wildcard.
        for spec in macro["charts"].get(org) or macro["charts"].get("*", []):
            charts = []
            for caption, variant_specs in spec["variants"]:
                variants = [
                    variant
                    for label, chart_id in variant_specs
                    if (variant := _chart_variant(org, org_dir, spec, org_data_dir, label, chart_id))
                ]
                if not variants:
                    continue
                chart_ids = [chart_id for _label, chart_id in variant_specs]
                chart = {"title": caption, "variants": variants}
                if note := next((CHART_NOTES[c] for c in chart_ids if c in CHART_NOTES), None):
                    chart["note"] = note
                if methodology := next((CHART_METHODOLOGY[c] for c in chart_ids if c in CHART_METHODOLOGY), None):
                    chart["methodology"] = methodology
                # Two different treatments: WIDE_CHARTS have many bars and need
                # the horizontal scroll box; FULL_ROW_CHARTS (few categories,
                # long legend, or a panoramic timeline) just span the full row,
                # scaled to fit — a scroll box would crop their legend.
                if any(c in WIDE_CHARTS for c in chart_ids):
                    chart["wide"] = True
                elif any(c in FULL_ROW_CHARTS for c in chart_ids):
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


def _copy_download(csv_name: str, org: str, org_data_dir: Path, org_dir: Path) -> dict | None:
    """Copy one companion CSV into the API tree and describe it, or None."""
    csv_path = org_data_dir / csv_name
    if not csv_path.exists():
        return None
    # This copy exists to be downloaded and opened in a spreadsheet, so it is
    # neutralised against formula injection; the artifact under outputs/data
    # stays verbatim for pandas consumers.
    (org_dir / csv_name).write_text(sanitize_csv_text(csv_path.read_text(encoding="utf-8")), encoding="utf-8")
    download = {"name": csv_name, "path": f"{org}/{csv_name}"}
    if generated_at := _read_meta(csv_path).get("generated_at"):
        download["generated_at"] = generated_at
    return download


def _attach_download(section: dict, spec: dict, org: str, org_data_dir: Path, org_dir: Path) -> None:
    """Copy a chart card's declared companion CSV(s) into the API and reference them.

    The Pages deploy publishes only the API tree, so a CSV
    the dashboard offers for download has to travel inside the API. The copy
    keeps the raw ``outputs/data`` artifact untouched.

    ``csv`` is one filename for a card whose tabs all read the same table, or a
    ``{variant label: filename}`` map for a card whose tabs show different
    populations — a single download on a role-tabbed card would hand the reader
    the maintainer table while they are looking at committers. The frontend
    offers the active tab's entry and hides the button where a tab has none.
    """
    declared = spec.get("csv")
    if not declared:
        return
    if isinstance(declared, str):
        if download := _copy_download(declared, org, org_data_dir, org_dir):
            section["download"] = download
        return
    downloads = {
        label: download
        for label, csv_name in declared.items()
        if (download := _copy_download(csv_name, org, org_data_dir, org_dir))
    }
    if downloads:
        section["downloads"] = downloads


def _write_section(document: dict, org: str, org_dir: Path) -> dict:
    """Write one section document and return the manifest entry pointing at it."""
    (org_dir / f"{document['id']}.json").write_text(json.dumps(document, indent=1), encoding="utf-8")
    entry = {
        "id": document["id"],
        "macro": document["macro"],
        "title": document["title"],
        "row_count": document["row_count"],
        "path": f"{org}/{document['id']}.json",
    }
    if absorbed_by := document.get("absorbed_by"):
        entry["absorbed_by"] = absorbed_by
    return entry


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


def _source_sections(
    org: str, table_sources: list[tuple[str, dict]], chart_sections: list[dict]
) -> dict[str, list[dict]]:
    """Each table file the org published -> the dashboard sections it feeds.

    Tables by their documents' ``source`` (``table_sources`` pairs a file with the
    card that shows it); chart cards by the CSVs their charts and downloads read
    (from the spec). Only sections emitted for this org are named, so a link
    never leads to a section the org lacks.
    """
    index: dict[str, list[dict]] = {}

    def add(name: str | None, entry: dict) -> None:
        if name and entry not in index.setdefault(name, []):
            index[name].append(entry)

    for name, ref in table_sources:
        add(name, {"macro": ref["macro"], "id": ref["id"], "title": ref["title"]})
    emitted = {section["id"]: section for section in chart_sections}
    for macro in CHART_MACROS:
        for spec in macro["charts"].get(org) or macro["charts"].get("*", []):
            section = emitted.get(spec["id"])
            if section is None:
                continue
            entry = {"macro": section["macro"], "id": section["id"], "title": section["title"]}
            for source in spec.get("sources", {}).values():
                add(source.get("file"), entry)
                add(source.get("edges_file"), entry)
            csv = spec.get("csv")
            for name in csv.values() if isinstance(csv, dict) else [csv]:
                add(name, entry)
    return index


def _org_entities(
    org: str,
    org_data_dir: Path,
    org_dir: Path,
    sources: dict[str, list[dict]] | None = None,
) -> dict | None:
    """Emit the org's repository and contributor documents; their manifest entry, or None.

    The whole ``entities/`` tree is rewritten each emit, so a repository or
    person no longer in the data does not leave a stale document behind.
    """
    entities_dir = org_dir / "entities"
    if entities_dir.exists():
        shutil.rmtree(entities_dir)
    built = build_entity_documents(org, org_data_dir, _freshness, sources)
    if built is None:
        return None
    api_dir = org_dir.parent
    for relative, document in built.documents.items():
        path = api_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        # Compact: hundreds of small documents, each fetched on demand.
        path.write_text(json.dumps(document, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    logger.info("Entity documents for %s: %d", org, len(built.documents))
    return built.manifest_entry


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
        # Each tab's one-line purpose, shown under its title.
        "macro_summaries": MACRO_SUMMARIES,
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
        # (source CSV, the card showing it): where an entity view's figures link back to.
        table_sources: list[tuple[str, dict]] = []
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
                sections.append(_write_section(document, org, org_dir))
                card = sections[-1]
                table_sources.extend((variant["source"], card) for variant in document.get("variants", [document]))
                # A role-tabbed card absorbs what used to be sibling sections.
                # Each absorbed variant keeps its own document *and* its own
                # manifest entry, tagged with the card that now renders it:
                # v1 is additive-only, so merging two cards into one must not
                # withdraw ids that consumers — and shared `#widget=` links —
                # already resolve. The dashboard skips these and reads the
                # rows from the merged card's `variants` instead.
                for variant in document.get("variants", [])[1:]:
                    absorbed = {
                        **variant,
                        "group": document["group"],
                        "macro": document["macro"],
                        "absorbed_by": document["id"],
                    }
                    sections.append(_write_section(absorbed, org, org_dir))
        chart_sections = _org_chart_sections(org, org_data_dir, org_dir)
        views = _org_views(org, org_data_dir, org_dir)
        entities = _org_entities(org, org_data_dir, org_dir, _source_sections(org, table_sources, chart_sections))
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
            # The repository and contributor detail views: an index of each,
            # whose rows name their lazily fetched documents. Additive: absent
            # when the entity tables were not produced.
            if entities:
                manifest["orgs"][org]["entities"] = entities

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
