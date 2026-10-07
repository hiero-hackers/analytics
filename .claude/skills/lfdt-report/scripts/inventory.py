#!/usr/bin/env python3
"""Fetch, inventory, define and cite the data API documents behind an LFDT TAC report.

Standard library only. The API is static JSON, so this script never guesses:
it downloads exactly what the manifest references, prints what is there,
prints each document's own definitions, and turns the ids a draft cites into
numbered Sources-appendix entries. A fifth command reads the TAC's own
instruction and schedule pages.

Usage:
    inventory.py fetch   ORG [--base URL] [--work DIR] [--refresh]
    inventory.py show    ORG [--work DIR] [--json]
    inventory.py doc     ORG ID... [--work DIR]
    inventory.py sources ORG ID... [--work DIR] [--start N] [--sorted] [--base TEXT]
    inventory.py tac     [--work DIR] [--year YYYY] [--project Hiero]

WORK defaults to ``$WORK`` when set (the SKILL's convention), else
``lfdt-report-work`` under the system temp directory, so the commands find
each other's files without being told.

``fetch`` saves ``manifest.json`` and every document the org references
(sections, chart variants, views, the two entity indexes) under WORK with
their relative paths, skipping files already there unless ``--refresh``. It
fails loudly on any HTTP or JSON error and prints one provenance line.

``show`` prints a markdown inventory: which macros the org has (and the
manifest's note for each one it lacks), every section with its all-time and
per-period row counts, every chart variant with its frequency or window,
partial buckets and comparison pair, the views, the headline tiles and the
entity counts. ``--json`` emits the same content as one JSON object.

``doc`` and ``sources`` take the same ids. An id is one of:

    understaffed          a section id
    maintainer-pipeline   a card id (every variant of every chart on it)
    maintainer_pipeline_yearly
                          a chart document id (cited as its card and variant)
    hip-board             a view id
    tile:Governance/maintainers
                          a headline tile, as tile:<Macro>/<label>
    understaffed@365d     a section's period table (``sources`` and ``doc``;
                          the period must be one the document has, for
                          example 7d, 30d or 365d)

``doc`` prints, per id, the definitions to read before citing: title, kind,
generated_at, stale, note and methodology (for a chart variant, the document's
own, else the manifest variant's, else the manifest chart's, each labelled
with the level it came from), population, window, frequency, comparison,
top_n, row and period row counts, and a section's columns. Rows are never
printed and long text is clipped.

``sources`` prints Sources-appendix entries, numbered from ``--start``. The
JSON path is printed as ``BASE/<path>`` (``--base`` replaces the literal
``BASE``) because the report's data-notes appendix defines BASE once.
``--sorted`` orders the entries by id (ASCII order; variants of one card keep
their manifest order) before numbering, so adding an id changes the numbers
predictably.

``tac`` fetches the LFDT annual-review and mid-year instruction pages and the
year's schedule page, saves their text under WORK/tac/, and prints the
questions each report must answer, what the TAC evaluates, the file-naming
sentence and the schedule rows that mention the project. When the schedule
page does not exist it lists the governance repository's directory for that
year instead and says so.

Exit codes: 0 success; 1 a fetch failed, ``sources``/``doc`` met an unknown id
(warned on stderr, the rest still printed) or ``tac`` could not find an
expected part of a page; 2 bad input (org not in the manifest, or WORK has no
manifest yet).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import NoReturn

DEFAULT_BASE = "https://hiero-hackers.github.io/analytics/data/api/v1"
DASHBOARD_URL = "https://hiero-hackers.github.io/analytics/"
MANIFEST_NAME = "manifest.json"
ENTITY_KEYS = ("repositories", "contributors")
FETCH_TIMEOUT_SECONDS = 60
TAC_SITE = "https://lf-decentralized-trust.github.io/governance/project-updates"
TAC_API = "https://api.github.com/repos/lf-decentralized-trust/governance/contents/tac/project-updates"
TAC_PAGES = (
    ("Annual review", "annual-review-instructions"),
    ("Mid-year update", "mid-year-update-instructions"),
)
MAX_DOC_LINES = 60
MAX_STEPS = 12


def _die(message: str, code: int = 1) -> NoReturn:
    """Print an error to stderr and exit with ``code``."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def default_work() -> Path:
    """Return the scratch directory used when ``--work`` is not given."""
    env = os.environ.get("WORK")
    return Path(env) if env else Path(tempfile.gettempdir()) / "lfdt-report-work"


# --------------------------------------------------------------------------
# Manifest walking (pure functions over parsed JSON)
# --------------------------------------------------------------------------


def iter_variants(entry: dict) -> Iterator[tuple[dict, dict, dict]]:
    """Yield ``(card, chart, variant)`` for every chart variant of an org entry."""
    for card in entry.get("chart_sections") or []:
        for chart in card.get("charts") or []:
            for variant in chart.get("variants") or []:
                yield card, chart, variant


def collect_paths(entry: dict) -> list[str]:
    """Return every document path an org entry references, in manifest order, without duplicates.

    That is each ``sections[].path``, every chart variant's ``interactive.path``,
    each ``views[].path`` and the two entity index paths.
    """
    paths = [section["path"] for section in entry.get("sections") or []]
    paths.extend(variant["interactive"]["path"] for _card, _chart, variant in iter_variants(entry))
    paths.extend(view["path"] for view in entry.get("views") or [])
    entities = entry.get("entities") or {}
    for key in ENTITY_KEYS:
        ref = entities.get(key)
        if ref and ref.get("path"):
            paths.append(ref["path"])
    return list(dict.fromkeys(paths))


def org_entry(manifest: dict, org: str) -> dict:
    """Return ``manifest.orgs[org]``, or exit 2 listing the orgs that do exist."""
    orgs = manifest.get("orgs") or {}
    if org not in orgs:
        _die(f"org {org!r} is not in the manifest; orgs in the manifest: {', '.join(orgs) or '(none)'}", 2)
    return orgs[org]


def provenance(manifest: dict) -> dict:
    """Return the manifest facts a report must record: version, wip, generated_at, git_sha, data_as_of."""
    prov = manifest.get("provenance") or {}
    return {
        "version": manifest.get("version"),
        "wip": manifest.get("wip"),
        "generated_at": manifest.get("generated_at"),
        "git_sha": prov.get("git_sha"),
        "data_as_of": prov.get("data_as_of"),
    }


def _wip_text(wip: object) -> str:
    """Spell the manifest's ``wip`` flag; absent is called out because the dashboard treats it as true."""
    return "absent (the dashboard treats absent as true)" if wip is None else str(bool(wip)).lower()


def provenance_text(manifest: dict) -> str:
    """Render the provenance facts as ``key=value`` pairs on one line."""
    prov = provenance(manifest)
    prov["wip"] = _wip_text(prov["wip"])
    return " ".join(f"{key}={value}" for key, value in prov.items())


# --------------------------------------------------------------------------
# Time and text helpers
# --------------------------------------------------------------------------


def parse_ts(value: object) -> datetime | None:
    """Parse an ISO timestamp or date into an aware UTC datetime; None when it is not one."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def date_only(value: object) -> str | None:
    """Return the UTC calendar date (YYYY-MM-DD) of a timestamp, or None."""
    parsed = parse_ts(value)
    return parsed.date().isoformat() if parsed else None


def short_ts(value: object) -> str | None:
    """Return a timestamp as ``YYYY-MM-DD HH:MMZ`` (UTC); unparseable text is returned as is."""
    parsed = parse_ts(value)
    if parsed:
        return parsed.strftime("%Y-%m-%d %H:%MZ")
    return value if isinstance(value, str) and value else None


def window_text(window: object) -> str | None:
    """Describe a chart document's ``window`` in one phrase (kind, days, end date)."""
    if not isinstance(window, dict):
        return None
    kind = window.get("kind")
    if kind == "calendar":
        return f"{window.get('first')}..{window.get('last')}"
    end = date_only(window.get("end")) or "?"
    if kind == "trailing":
        return f"trailing {window.get('days')}d to {end}"
    if kind == "all":
        return f"all time to {end}"
    return f"{kind} at {end}"


def _cell(value: object) -> str:
    """Format one markdown table cell: None as a dash, booleans as yes/no, pipes escaped."""
    if value is None or value == "":
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    """Render a markdown table as a list of lines."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows)
    return lines


# --------------------------------------------------------------------------
# Local workspace
# --------------------------------------------------------------------------


class Workspace:
    """A directory of fetched API documents, read lazily and cached."""

    def __init__(self, root: Path) -> None:
        """Remember the root directory; nothing is read until a document is asked for."""
        self.root = root
        self._cache: dict[str, dict | None] = {}

    def doc(self, rel: str) -> dict | None:
        """Return the parsed document at ``rel``, or None when the file is not there."""
        if rel not in self._cache:
            path = self.root / rel
            if not path.is_file():
                self._cache[rel] = None
            else:
                try:
                    self._cache[rel] = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    _die(f"{path} is not valid JSON ({exc}); re-run fetch with --refresh", 2)
        return self._cache[rel]

    def require(self, rel: str) -> dict:
        """Return the document at ``rel``, exiting 2 with a fetch hint when it is missing."""
        found = self.doc(rel)
        if found is None:
            _die(f"{self.root / rel} is missing; run: inventory.py fetch ORG --work {self.root}", 2)
        return found

    def manifest(self) -> dict:
        """Return the saved manifest."""
        return self.require(MANIFEST_NAME)


# --------------------------------------------------------------------------
# fetch
# --------------------------------------------------------------------------


class FetchError(Exception):
    """A download failed: ``status`` is the HTTP code (None when the host or file was unreachable)."""

    def __init__(self, detail: str, status: int | None = None, not_found: bool = False) -> None:
        """Keep the one-line cause, the HTTP status if any, and whether the target simply does not exist."""
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.not_found = not_found


def _open_url(url: str, headers: dict[str, str] | None = None) -> bytes:
    """Download ``url`` (http, https or file) and return its bytes; raise FetchError on any failure.

    A ``file:`` URL naming a directory reads that directory's ``index.html``, as a web server would.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https", "file"):
        _die(f"refusing {url}: only http, https and file URLs are supported")
    target = url
    if parsed.scheme == "file":
        local = Path(urllib.request.url2pathname(parsed.path))
        if local.is_dir():
            target = (local / "index.html").as_uri()
    request = urllib.request.Request(target, headers=headers or {})  # noqa: S310 - scheme checked above
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310 - same
            return response.read()
    except urllib.error.HTTPError as exc:
        raise FetchError(str(exc.reason), status=exc.code, not_found=exc.code == 404) from exc
    except OSError as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        raise FetchError(str(reason), not_found=isinstance(reason, FileNotFoundError)) from exc


def _read_url(url: str) -> bytes:
    """Download an API document; any failure exits with a message that names the URL."""
    try:
        return _open_url(url)
    except FetchError as exc:
        if exc.status is not None:
            hint = " (check --base; the published API is " + DEFAULT_BASE + ")" if exc.status == 404 else ""
            _die(
                f"fetch failed for {url}: HTTP {exc.status} {exc.detail}{hint}. The API is unreachable: do not draft from memory or a stale copy"
            )
        _die(
            f"fetch failed for {url}: host unreachable or not found ({exc.detail}). Check the network and --base; do not draft from memory or a stale copy"
        )


def _destination(work: Path, rel: str) -> Path:
    """Return ``work/rel``, refusing any path that would land outside ``work``."""
    root = work.resolve()
    dest = (root / rel).resolve()
    if rel.startswith("/") or root not in dest.parents:
        _die(f"refusing manifest path {rel!r}: it resolves outside {work}")
    return dest


def _fetch_one(base: str, rel: str, work: Path, refresh: bool) -> bool:
    """Download one document into WORK; return False when an existing copy was kept."""
    dest = _destination(work, rel)
    if dest.is_file() and not refresh:
        return False
    url = f"{base}/{urllib.parse.quote(rel)}"
    data = _read_url(url)
    try:
        json.loads(data)
    except ValueError as exc:
        _die(f"{url} did not return JSON ({exc}); nothing was saved for it")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    part.write_bytes(data)
    os.replace(part, dest)
    return True


def cmd_fetch(org: str, base: str, work: Path, refresh: bool) -> int:
    """Download the manifest and every document ``org`` references; print one provenance line."""
    base = base.rstrip("/")
    manifest_cached = not _fetch_one(base, MANIFEST_NAME, work, refresh)
    fetched, skipped = (0, 1) if manifest_cached else (1, 0)
    manifest = Workspace(work).manifest()
    if org not in (manifest.get("orgs") or {}):
        if manifest_cached:
            print("note: the manifest came from WORK; pass --refresh to download it again", file=sys.stderr)
        org_entry(manifest, org)  # exits 2 and lists the orgs that do exist
    for rel in collect_paths(manifest["orgs"][org]):
        if _fetch_one(base, rel, work, refresh):
            fetched += 1
        else:
            skipped += 1
    print(f"{provenance_text(manifest)} fetched={fetched} skipped={skipped} work={work}")
    print(f"next: inventory.py show {org} --work {work}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------
# show
# --------------------------------------------------------------------------


def _doc_row_count(doc: dict) -> int:
    """Count a chart document's data rows (nodes for a network, which has no rows)."""
    return len(doc.get("nodes") or []) if doc.get("kind") == "network" else len(doc.get("rows") or [])


def _macro_rows(manifest: dict, entry: dict) -> list[dict]:
    """Build the macro table: every ``macro_order`` entry, then macros only this org has."""
    sections = entry.get("sections") or []
    cards = entry.get("chart_sections") or []
    views = entry.get("views") or []
    tiles = entry.get("metrics") or {}
    names = list(manifest.get("macro_order") or [])
    for macro in (
        [s["macro"] for s in sections] + [c["macro"] for c in cards] + [v["macro"] for v in views] + list(tiles)
    ):
        if macro not in names:
            names.append(macro)
    notes = manifest.get("macro_absent_notes") or {}
    rows = []
    for macro in names:
        counts = {
            "sections": sum(1 for s in sections if s["macro"] == macro),
            "cards": sum(1 for c in cards if c["macro"] == macro),
            "views": sum(1 for v in views if v["macro"] == macro),
            "tiles": len(tiles.get(macro) or []),
        }
        present = bool(counts["sections"] or counts["cards"] or counts["views"])
        rows.append(
            {
                "macro": macro,
                "present": present,
                "in_macro_order": macro in (manifest.get("macro_order") or []),
                **counts,
                "absent_note": None if present else notes.get(macro),
            }
        )
    return rows


def _section_rows(entry: dict, ws: Workspace) -> list[dict]:
    """Build the sections table from the manifest refs and each section document."""
    rows = []
    for ref in entry.get("sections") or []:
        doc = ws.require(ref["path"])
        variants = [
            {
                "id": v.get("id"),
                "label": v.get("label"),
                "row_count": v.get("row_count"),
                "periods": {k: len(r) for k, r in (v.get("periods") or {}).items()},
            }
            for v in doc.get("variants") or []
        ]
        rows.append(
            {
                "id": ref["id"],
                "macro": ref["macro"],
                "title": ref["title"],
                "row_count": ref["row_count"],
                "document_rows": len(doc.get("rows") or []),
                "periods": {k: len(r) for k, r in (doc.get("periods") or {}).items()},
                "absorbed_by": ref.get("absorbed_by"),
                "stale": doc.get("stale"),
                "generated_at": doc.get("generated_at"),
                "variants": variants,
                "path": ref["path"],
            }
        )
    return rows


def _chart_rows(entry: dict, ws: Workspace) -> list[dict]:
    """Build the chart table: one row per variant, read from the variant's document."""
    rows = []
    for card, chart, variant in iter_variants(entry):
        path = variant["interactive"]["path"]
        doc = ws.require(path)
        timeseries = doc.get("kind") == "timeseries"
        comparison = doc.get("comparison") if timeseries else None
        rows.append(
            {
                "card": card["id"],
                "macro": card["macro"],
                "chart": chart["title"],
                "variant": variant["label"],
                "document_id": doc.get("id") or Path(path).stem,
                "kind": doc.get("kind") or variant["interactive"].get("kind"),
                "frequency": doc.get("frequency") if timeseries else None,
                "window": window_text(doc.get("window")),
                "rows": _doc_row_count(doc),
                "partial": [r.get("bucket") for r in doc.get("rows") or [] if r.get("partial")] if timeseries else [],
                "comparison": comparison,
                "top_n": doc.get("top_n"),
                "stale": doc.get("stale"),
                "generated_at": doc.get("generated_at"),
                "path": path,
            }
        )
    return rows


def build_inventory(manifest: dict, org: str, ws: Workspace) -> dict:
    """Collect everything ``show`` prints into one JSON-able dict."""
    entry = org_entry(manifest, org)
    entities = entry.get("entities") or {}
    return {
        "org": org,
        "provenance": provenance(manifest),
        "macros": _macro_rows(manifest, entry),
        "sections": _section_rows(entry, ws),
        "charts": _chart_rows(entry, ws),
        "views": [
            {"id": v["id"], "macro": v["macro"], "kind": v.get("kind"), "title": v.get("title"), "path": v["path"]}
            for v in entry.get("views") or []
        ],
        "tiles": [
            {"macro": macro, "label": tile.get("label"), "value": tile.get("value")}
            for macro, tiles in (entry.get("metrics") or {}).items()
            for tile in tiles
        ],
        "entities": {key: entities.get(key) for key in ENTITY_KEYS},
    }


def _period_text(periods: dict) -> str | None:
    """Format per-period row counts as ``7d=97 30d=148``; None when there are none."""
    return " ".join(f"{key}={count}" for key, count in periods.items()) or None


def render_markdown(inv: dict) -> str:
    """Render an inventory dict as the markdown report ``show`` prints."""
    prov = inv["provenance"]
    lines = [
        f"# Inventory: {inv['org']}",
        "",
        f"Manifest {prov['version']}, wip={_wip_text(prov['wip'])}, generated {prov['generated_at']}, "
        f"git_sha {prov['git_sha']}, data as of {prov['data_as_of']}.",
        "",
        "## Macros",
        "",
    ]
    lines += _md_table(
        ["Macro", "Status", "Sections", "Cards", "Views", "Tiles", "Absence note"],
        [
            [
                m["macro"] + ("" if m["in_macro_order"] else " (not in macro_order)"),
                "present" if m["present"] else "absent",
                m["sections"],
                m["cards"],
                m["views"],
                m["tiles"],
                m["absent_note"],
            ]
            for m in inv["macros"]
        ],
    )
    lines += ["", f"## Sections ({len(inv['sections'])})", ""]
    lines += _md_table(
        ["Id", "Macro", "Title", "Rows (all time)", "Rows by period", "Absorbed by", "Stale", "Generated"],
        [
            [
                s["id"],
                s["macro"],
                s["title"],
                s["row_count"]
                if s["row_count"] == s["document_rows"]
                else f"{s['row_count']} (document: {s['document_rows']})",
                _period_text(s["periods"]),
                s["absorbed_by"],
                s["stale"],
                short_ts(s["generated_at"]),
            ]
            for s in inv["sections"]
        ],
    )
    lines += ["", f"## Chart cards ({len(inv['charts'])} variants)", ""]
    lines += _md_table(
        [
            "Card",
            "Macro",
            "Chart",
            "Variant",
            "Document",
            "Kind",
            "Frequency / window",
            "Rows",
            "Partial",
            "Comparison",
            "top_n",
            "Stale",
        ],
        [
            [
                c["card"],
                c["macro"],
                c["chart"],
                c["variant"],
                c["document_id"],
                c["kind"],
                f"{c['frequency']} ({c['window']})" if c["frequency"] else c["window"],
                c["rows"],
                ", ".join(c["partial"]) or None,
                f"{c['comparison']['current']} vs {c['comparison']['previous']}" if c["comparison"] else None,
                c["top_n"],
                c["stale"],
            ]
            for c in inv["charts"]
        ],
    )
    lines += ["", f"## Views ({len(inv['views'])})", ""]
    lines += _md_table(["Id", "Macro", "Kind"], [[v["id"], v["macro"], v["kind"]] for v in inv["views"]])
    lines += ["", f"## Tiles ({len(inv['tiles'])})", ""]
    lines += _md_table(["Macro", "Label", "Value"], [[t["macro"], t["label"], t["value"]] for t in inv["tiles"]])
    lines += ["", "## Entities", ""]
    lines += _md_table(
        ["Index", "Count", "Path"],
        [[key, (ref or {}).get("count"), (ref or {}).get("path")] for key, ref in inv["entities"].items()],
    )
    return "\n".join(lines) + "\n"


def cmd_show(org: str, work: Path, as_json: bool) -> int:
    """Print the inventory of ``org`` as markdown, or as JSON with ``--json``."""
    ws = Workspace(work)
    inv = build_inventory(ws.manifest(), org, ws)
    sys.stdout.write(json.dumps(inv, indent=2) + "\n" if as_json else render_markdown(inv))
    return 0


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------


def variant_document_id(ws: Workspace, variant: dict) -> str:
    """Return a variant's document id: the document's own ``id``, else its file name without extension."""
    path = variant["interactive"]["path"]
    return (ws.doc(path) or {}).get("id") or Path(path).stem


def _as_of(ws: Workspace, rel: str, fallback: str) -> str:
    """Return the date a document was generated, or ``fallback`` when it has none (warns if the file is absent)."""
    doc = ws.doc(rel)
    if doc is None:
        print(f"warning: {ws.root / rel} is not in WORK; using the manifest data-as-of date", file=sys.stderr)
        return fallback
    return date_only(doc.get("generated_at")) or fallback


class UnknownIdError(Exception):
    """An id given to ``doc`` or ``sources`` names nothing in the manifest (the message says why)."""


def _document_source(kind: str, ref: dict, ws: Workspace, fallback: str) -> dict:
    """Build the source record for a section or view listed in the manifest."""
    return {
        "kind": kind,
        "id": ref["id"],
        "macro": ref["macro"],
        "path": ref["path"],
        "widget": ref["id"],
        "as_of": _as_of(ws, ref["path"], fallback),
        "ref": ref,
    }


def _chart_source(card: dict, chart: dict, variant: dict, ws: Workspace, fallback: str) -> dict:
    """Build the source record for one chart variant (cited by its card id)."""
    path = variant["interactive"]["path"]
    return {
        "kind": "Chart",
        "id": card["id"],
        "macro": card["macro"],
        "path": path,
        "widget": card["id"],
        "variant": variant["label"],
        "document_id": variant_document_id(ws, variant),
        "as_of": _as_of(ws, path, fallback),
        "card": card,
        "chart": chart,
        "ref": variant,
    }


def _tile_source(entry: dict, ident: str, fallback: str) -> list[dict]:
    """Resolve ``tile:<Macro>/<label>`` to a source record carrying the tile's value."""
    macro, _, label = ident[len("tile:") :].partition("/")
    tiles = (entry.get("metrics") or {}).get(macro) or []
    return [
        {
            "kind": "Tile",
            "id": f"{macro}/{label}",
            "macro": macro,
            "path": MANIFEST_NAME,
            "widget": None,
            "as_of": fallback,
            "value": tile.get("value"),
            "ref": tile,
        }
        for tile in tiles
        if tile.get("label") == label
    ][:1]


def _period_source(record: dict, doc: dict | None, period: str) -> dict:
    """Turn a section record into the record for one of its period tables, or raise UnknownIdError."""
    periods = (doc or {}).get("periods") or {}
    if period not in periods:
        have = ", ".join(periods) or "none"
        raise UnknownIdError(f"section {record['id']!r} has no {period!r} period table (it has: {have})")
    return {**record, "period": period, "period_rows": len(periods[period]), "all_rows": record["ref"]["row_count"]}


def resolve_source(ws: Workspace, manifest: dict, org: str, ident: str) -> list[dict]:
    """Resolve one id to its source records; raise UnknownIdError when it names nothing.

    Each record carries ``kind``, ``id``, ``macro``, ``path``, ``widget`` (None for a tile),
    ``as_of``, the manifest object it came from (``ref``) and, for a chart, ``card``, ``chart``,
    ``variant`` and ``document_id``. ``ID@PERIOD`` resolves a section to one of its period tables.
    """
    entry = org_entry(manifest, org)
    fallback = date_only(provenance(manifest)["data_as_of"]) or "unknown"
    sections = entry.get("sections") or []
    if ident.startswith("tile:"):
        found = _tile_source(entry, ident, fallback)
    elif "@" in ident:
        base_id, _, period = ident.rpartition("@")
        matches = [
            {**_document_source("Section", ref, ws, fallback), "seq": seq}
            for seq, ref in enumerate(sections)
            if ref["id"] == base_id
        ]
        if not matches:
            raise UnknownIdError(f"unknown id {ident!r} for org {org}: no section {base_id!r}; no entry written")
        found = [_period_source(record, ws.doc(record["path"]), period) for record in matches]
    else:
        found = [
            {**_document_source("Section", ref, ws, fallback), "seq": seq}
            for seq, ref in enumerate(sections)
            if ref["id"] == ident
        ]
        found.extend(
            {**_chart_source(card, chart, variant, ws, fallback), "seq": seq}
            for seq, (card, chart, variant) in enumerate(iter_variants(entry))
            if ident in (card["id"], variant_document_id(ws, variant))
        )
        found.extend(
            {**_document_source("View", ref, ws, fallback), "seq": seq}
            for seq, ref in enumerate(entry.get("views") or [])
            if ref["id"] == ident
        )
    if not found:
        raise UnknownIdError(f"unknown id {ident!r} for org {org}; no entry written")
    return found


def dashboard_link(org: str, macro: str, widget: str | None) -> str:
    """Return the dashboard deep link for a tab (and a card or section on it)."""
    link = f"{DASHBOARD_URL}#tab={urllib.parse.quote(macro, safe='')}&org={urllib.parse.quote(org, safe='')}"
    if widget:
        link += f"&widget={urllib.parse.quote(widget, safe='')}"
    return link


def _plural(count: int, noun: str) -> str:
    """Return ``count`` with ``noun`` pluralised by a trailing s unless the count is one."""
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def format_source(number: int, src: dict, org: str, base: str) -> str:
    """Format one Sources-appendix entry on a single line."""
    head = f"[{number}] {src['kind']} {src['id']}"
    if "value" in src:
        head += f" ({src['value']})"
    if "variant" in src:
        head += f", {src['variant']} variant ({src['document_id']})"
    if "period" in src:
        head += f", {src['period']} period table ({_plural(src['period_rows'], 'row')}; {src['all_rows']} all time)"
    return (
        f"{head}; data as of {src['as_of']}. JSON: {base}/{src['path']}. "
        f"Dashboard: {dashboard_link(org, src['macro'], src['widget'])}"
    )


def _resolve_all(ws: Workspace, manifest: dict, org: str, idents: list[str]) -> tuple[list[dict], int]:
    """Resolve every id, dropping repeats of the same source; warn on stderr about unknown ids.

    Returns the distinct records in argument order and the number of ids that were unknown.
    """
    seen: set[tuple] = set()
    records: list[dict] = []
    unknown = 0
    for ident in idents:
        try:
            resolved = resolve_source(ws, manifest, org, ident)
        except UnknownIdError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            unknown += 1
            continue
        for record in resolved:
            key = (record["kind"], record["id"], record.get("document_id"), record.get("period"))
            if key not in seen:
                seen.add(key)
                records.append(record)
    return records, unknown


def cmd_sources(org: str, idents: list[str], work: Path, start: int, base: str, sort_ids: bool = False) -> int:
    """Print one numbered Sources entry per distinct source; warn on unknown ids and exit 1 at the end.

    With ``sort_ids`` the entries are ordered by id, then period, then manifest position before numbering,
    so the variants of one card keep their manifest order whichever way they were cited.
    """
    ws = Workspace(work)
    manifest = ws.manifest()
    org_entry(manifest, org)
    records, unknown = _resolve_all(ws, manifest, org, idents)
    if sort_ids:
        records.sort(key=lambda r: (r["id"], r.get("period") or "", r.get("seq", 0)))
    for number, record in enumerate(records, start=start):
        print(format_source(number, record, org, base))
    return 1 if unknown else 0


# --------------------------------------------------------------------------
# doc
# --------------------------------------------------------------------------


def _clip(value: object, limit: int = 600) -> str:
    """Collapse whitespace and cut text to ``limit`` characters, saying how long it was."""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}... (clipped, {len(text)} characters)"


def _kv(key: str, value: object, limit: int = 600) -> list[str]:
    """Return one ``- key: value`` line, or nothing when the value is absent or empty."""
    if value is None or (isinstance(value, str | list | dict) and not value):
        return []
    if isinstance(value, bool):
        value = "yes" if value else "no"
    return [f"- {key}: {_clip(value, limit)}"]


def _stated(value: object) -> object:
    """Return ``value``, or the words 'not stated' when the document does not say."""
    return "not stated" if value is None else value


def _level_groups(field: str, levels: list[tuple[str, dict]]) -> list[tuple[list[str], object]]:
    """Group the non-empty values of ``field`` across levels, merging levels that hold the same value."""
    groups: list[tuple[list[str], object]] = []
    for name, source in levels:
        value = source.get(field)
        if not value:
            continue
        for names, seen in groups:
            if seen == value:
                names.append(name)
                break
        else:
            groups.append(([name], value))
    return groups


def _level_lines(field: str, levels: list[tuple[str, dict]], say_none: bool) -> list[str]:
    """Render a note or methodology with the level(s) it came from; a differing second value is shown too."""
    groups = _level_groups(field, levels)
    if not groups:
        names = ", ".join(name for name, _ in levels)
        return [f"- {field}: none at any level ({names})"] if say_none else []
    lines: list[str] = []
    for index, (names, value) in enumerate(groups):
        tag = " + ".join(names) + ("" if index == 0 else "; differs from the above")
        if isinstance(value, list):
            lines.append(f"- {field} [{tag}]:")
            lines.extend(f"  - {_clip(step, 300)}" for step in value[:MAX_STEPS])
            if len(value) > MAX_STEPS:
                lines.append(f"  - ... and {len(value) - MAX_STEPS} more steps")
        else:
            lines.append(f"- {field} [{tag}]: {_clip(value)}")
    return lines


def _chart_doc_lines(rec: dict, doc: dict) -> list[str]:
    """Describe a chart variant: the document's definitions plus the manifest-level note and methodology."""
    variant, chart, card = rec["ref"], rec["chart"], rec["card"]
    timeseries = doc.get("kind") == "timeseries"
    levels = [("document", doc), ("manifest variant", variant), ("manifest chart", chart)]
    comparison = doc.get("comparison") if timeseries else None
    partial = [r.get("bucket") for r in doc.get("rows") or [] if r.get("partial")] if timeseries else []
    series = [f"{s.get('key')} ({s.get('label')})" for s in doc.get("series") or []]
    lines = _kv("card", f"{card['id']} ({card['title']}), macro {card['macro']}")
    lines += _kv("chart", chart["title"])
    lines += _kv("variant", f"{variant['label']} (document {rec['document_id']})")
    lines += _kv("kind", doc.get("kind") or variant["interactive"].get("kind"))
    lines += _kv("generated_at", doc.get("generated_at"))
    lines += _kv("stale", _stated(doc.get("stale")))
    lines += _kv("metric", f"{doc.get('metric')} ({doc.get('unit')})" if doc.get("metric") else doc.get("unit"))
    lines += _kv("population", doc.get("population"), 800)
    lines += _kv("window", window_text(doc.get("window")))
    lines += _kv("frequency", doc.get("frequency"))
    if timeseries:
        lines += _kv("comparison", f"{comparison['current']} vs {comparison['previous']}" if comparison else "none")
        lines += _kv("partial buckets", ", ".join(partial) or "none")
    lines += _kv("top_n", doc.get("top_n"))
    lines += _kv("rows", f"{_doc_row_count(doc)} in the document")
    lines += _kv("series", ", ".join(series[:12]) + (f", +{len(series) - 12} more" if len(series) > 12 else ""))
    lines += _level_lines("note", levels, say_none=True)
    lines += _level_lines("methodology", levels, say_none=True)
    lines += _kv("json", rec["path"])
    return lines


def _section_doc_lines(rec: dict, doc: dict) -> list[str]:
    """Describe a section: its description, row counts by period and column keys and labels."""
    ref = rec["ref"]
    periods = {k: len(v) for k, v in (doc.get("periods") or {}).items()}
    columns = doc.get("columns") or []
    group = f", group {doc['group']}" if doc.get("group") else ""
    lines = _kv("title", doc.get("title") or ref["title"])
    lines += _kv("kind", f"section, macro {ref['macro']}{group}")
    lines += _kv("generated_at", doc.get("generated_at"))
    lines += _kv("stale", _stated(doc.get("stale")))
    lines += _kv("absorbed_by", ref.get("absorbed_by"))
    lines += _kv("description", doc.get("description"), 800)
    lines += _kv("note", doc.get("note"))
    lines += _level_lines("methodology", [("document", doc)], say_none=False)
    lines += _kv("rows", f"{ref['row_count']} all time (manifest); {len(doc.get('rows') or [])} in the document")
    if "period" in rec:
        lines += _kv(
            "period table cited", f"{rec['period']}: {_plural(rec['period_rows'], 'row')}, {rec['all_rows']} all time"
        )
    lines += _kv("period row counts", " ".join(f"{k}={n}" for k, n in periods.items()) or "none")
    variants = [f"{v.get('id')} ({v.get('label')}, {v.get('row_count')} rows)" for v in doc.get("variants") or []]
    lines += _kv("variants", ", ".join(variants))
    if columns:
        lines.append(f"- columns ({len(columns)}):")
        lines.extend(f"  - {c.get('key')}: {_clip(c.get('label'), 80)}" for c in columns[:20])
        if len(columns) > 20:
            lines.append(f"  - ... and {len(columns) - 20} more")
    lines += _kv("json", rec["path"])
    return lines


def _view_doc_lines(rec: dict, doc: dict) -> list[str]:
    """Describe a view: its description and the shape of its content, never its items."""
    ref = rec["ref"]
    board = [f"{c.get('title')} ({len(c.get('items') or [])})" for c in doc.get("columns") or [] if "items" in c]
    lines = _kv("title", doc.get("title") or ref.get("title"))
    lines += _kv("kind", f"view ({doc.get('kind') or ref.get('kind')}), macro {ref['macro']}")
    lines += _kv("generated_at", doc.get("generated_at"))
    lines += _kv("stale", _stated(doc.get("stale")))
    lines += _kv("badge", doc.get("badge"))
    lines += _kv("description", doc.get("description"), 800)
    lines += _kv("evidence section", doc.get("evidence_section"))
    if doc.get("rows") is not None:
        lines += _kv("rows", f"{len(doc['rows'])} in the document")
    lines += _kv("board columns", ", ".join(board))
    lines += _kv("json", rec["path"])
    return lines


def _tile_doc_lines(rec: dict, manifest: dict) -> list[str]:
    """Describe a headline tile: label, value, note and methodology as the manifest states them."""
    tile = rec["ref"]
    lines = _kv("label", tile.get("label"))
    lines += _kv("value", tile.get("value"))
    lines += _kv("macro", rec["macro"])
    lines += _kv("data as of (manifest)", provenance(manifest)["data_as_of"])
    lines += _level_lines("note", [("manifest tile", tile)], say_none=True)
    lines += _level_lines("methodology", [("manifest tile", tile)], say_none=True)
    return lines


def render_doc(ws: Workspace, manifest: dict, rec: dict) -> str:
    """Render one ``###`` block of definitions for a source record, at most MAX_DOC_LINES lines."""
    kind = rec["kind"]
    if kind == "Tile":
        heading = f"### Tile {rec['id']} ({rec['value']})"
        lines = _tile_doc_lines(rec, manifest)
    else:
        doc = ws.require(rec["path"])
        if kind == "Chart":
            heading = f"### Chart {rec['id']}, {rec['variant']} variant ({rec['document_id']})"
            lines = _chart_doc_lines(rec, doc)
        elif kind == "Section":
            period = f", {rec['period']} period table" if "period" in rec else ""
            heading = f"### Section {rec['id']}{period}"
            lines = _section_doc_lines(rec, doc)
        else:
            heading = f"### View {rec['id']}"
            lines = _view_doc_lines(rec, doc)
    if len(lines) > MAX_DOC_LINES:
        lines = [*lines[: MAX_DOC_LINES - 1], f"- ... {len(lines) - MAX_DOC_LINES + 1} more lines clipped"]
    return "\n".join([heading, "", *lines])


def cmd_doc(org: str, idents: list[str], work: Path) -> int:
    """Print the definitions to read before citing each id; warn on unknown ids and exit 1 at the end."""
    ws = Workspace(work)
    manifest = ws.manifest()
    org_entry(manifest, org)
    records, unknown = _resolve_all(ws, manifest, org, idents)
    print("\n\n".join(render_doc(ws, manifest, record) for record in records))
    return 1 if unknown else 0


# --------------------------------------------------------------------------
# tac
# --------------------------------------------------------------------------


class _PageText(HTMLParser):
    """Turn an HTML page into plain-text blocks: headings, paragraphs, list items and table rows.

    Scripts, styles, SVG, navigation, headers and footers are dropped, as are the permalink anchors
    mkdocs adds to headings. Text inside ``<code>`` is wrapped in backticks. Inside an ``<article>``
    only the article's blocks are kept (see ``html_to_blocks``).
    """

    SKIPPED = frozenset({"script", "style", "svg", "noscript", "template", "nav", "header", "footer", "button"})
    FLUSHING = frozenset({"ul", "ol", "table", "tr", "div", "section", "article", "main", "blockquote", "pre", "hr"})

    def __init__(self) -> None:
        """Start with no blocks and nothing open."""
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self._skip = 0
        self._skip_anchor = False
        self._article = 0
        self._lists: list[str] = []
        self._block: dict | None = None
        self._row: list[str] | None = None
        self._row_header = False
        self._cell: list[str] | None = None

    def _begin(self, kind: str, level: int | None = None, ordered: bool = False) -> None:
        """Close any open block and open a new one."""
        self._flush()
        self._block = {"kind": kind, "level": level, "ordered": ordered, "parts": [], "article": self._article > 0}

    def _flush(self) -> None:
        """Emit the open block as text, if it has any."""
        block, self._block = self._block, None
        if not block:
            return
        text = " ".join("".join(block["parts"]).replace("¶", " ").split())
        if text:
            self.blocks.append({**{k: v for k, v in block.items() if k != "parts"}, "text": text})

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Open blocks, rows, cells and lists as their tags start."""
        if tag in self.SKIPPED:
            self._skip += 1
            return
        if tag == "a" and "headerlink" in (dict(attrs).get("class") or ""):
            self._skip += 1
            self._skip_anchor = True
            return
        if self._skip:
            return
        if tag == "article":
            self._flush()
            self._article += 1
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._begin("h", level=int(tag[1]))
        elif tag == "p":
            if self._block and self._block["kind"] == "li":
                self._block["parts"].append(" ")
            elif self._cell is not None:
                self._cell.append(" ")
            else:
                self._begin("p")
        elif tag == "li":
            self._begin("li", ordered=bool(self._lists) and self._lists[-1] == "ol")
        elif tag in ("ul", "ol"):
            self._flush()
            self._lists.append(tag)
        elif tag == "tr":
            self._flush()
            self._row, self._row_header = [], False
        elif tag in ("td", "th"):
            self._cell = []
            self._row_header = self._row_header or tag == "th"
        elif tag == "br":
            self._add(" ")
        elif tag == "code" and not (self._block and self._block["kind"] == "pre"):
            self._add("`")
        elif tag in self.FLUSHING:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        """Close blocks, rows, cells and lists as their tags end."""
        if tag == "a" and self._skip_anchor:
            self._skip -= 1
            self._skip_anchor = False
            return
        if tag in self.SKIPPED:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "article":
            self._flush()
            self._article = max(0, self._article - 1)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self._flush()
        elif tag == "p":
            if not (self._block and self._block["kind"] == "li") and self._cell is None:
                self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            if self._lists:
                self._lists.pop()
        elif tag in ("td", "th"):
            if self._cell is not None and self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr":
            if self._row and any(self._row):
                self.blocks.append(
                    {
                        "kind": "tr",
                        "text": " | ".join(self._row),
                        "cells": self._row,
                        "header": self._row_header,
                        "article": self._article > 0,
                    }
                )
            self._row = None
        elif tag == "code" and not (self._block and self._block["kind"] == "pre"):
            self._add("`")
        elif tag in self.FLUSHING:
            self._flush()

    def _add(self, text: str) -> None:
        """Append text to the open cell or block."""
        if self._cell is not None:
            self._cell.append(text)
        elif self._block is not None:
            self._block["parts"].append(text)

    def handle_data(self, data: str) -> None:
        """Collect text; stray text outside any block becomes its own paragraph."""
        if self._skip:
            return
        if self._cell is None and self._block is None and data.strip():
            self._begin("p")
        self._add(data)

    def close(self) -> None:
        """Finish parsing and emit whatever is still open."""
        super().close()
        self._flush()


def html_to_blocks(html_text: str) -> list[dict]:
    """Parse an HTML page into text blocks, keeping only the ``<article>`` content when the page has one."""
    parser = _PageText()
    parser.feed(html_text)
    parser.close()
    article = [block for block in parser.blocks if block["article"]]
    return article or parser.blocks


def blocks_to_text(blocks: list[dict]) -> str:
    """Render blocks as plain text: markdown-style headings, ``-`` list items, ``|`` table rows."""
    lines: list[str] = []
    for block in blocks:
        kind = block["kind"]
        if kind == "h":
            lines += ["", f"{'#' * (block.get('level') or 1)} {block['text']}", ""]
        elif kind == "li":
            lines.append(f"- {block['text']}")
        else:
            lines.append(block["text"])
    return "\n".join(lines).strip() + "\n"


def _items_after(blocks: list[dict], index: int) -> list[str]:
    """Return the consecutive list items that follow ``blocks[index]``."""
    items: list[str] = []
    for block in blocks[index + 1 :]:
        if block["kind"] != "li":
            break
        items.append(block["text"])
    return items


def questions_of(blocks: list[dict]) -> list[str]:
    """Return the list under the paragraph that says the report 'should answer the following questions'."""
    for index, block in enumerate(blocks):
        if block["kind"] == "p" and "following questions" in block["text"].lower():
            return _items_after(blocks, index)
    return []


def evaluation_of(blocks: list[dict]) -> list[str]:
    """Return the bullets under the 'What does the TAC evaluate' heading (up to the next heading)."""
    for index, block in enumerate(blocks):
        if block["kind"] == "h" and "what does the tac evaluate" in block["text"].lower():
            items: list[str] = []
            for follower in blocks[index + 1 :]:
                if follower["kind"] == "h":
                    break
                if follower["kind"] == "li":
                    items.append(follower["text"])
            return items
    return []


def naming_sentence_of(blocks: list[dict]) -> str | None:
    """Return the sentence that tells the project what to name its report file."""
    for block in blocks:
        if block["kind"] == "p" and "name the file" in block["text"]:
            for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z])", block["text"]):
                if "name the file" in sentence:
                    return sentence
    return None


def report_type_of(label: str) -> str:
    """Gloss a schedule's quarter cell: 1H is the annual review, 2H the mid-year update."""
    lowered = label.lower()
    if "annual" in lowered or lowered.startswith("1h"):
        return "annual review"
    if lowered.startswith("2h") or "mid" in lowered:
        return "mid-year update"
    return "report type not stated"


def schedule_rows(blocks: list[dict], project: str) -> list[dict]:
    """Return the schedule table rows that mention ``project``, as date, the page's label and the report type."""
    mention = re.compile(rf"\b{re.escape(project)}\b", re.IGNORECASE)
    rows = []
    for block in blocks:
        if block["kind"] != "tr" or block.get("header"):
            continue
        cells = block["cells"]
        if not any(mention.search(cell) for cell in cells):
            continue
        date = next((c for c in cells if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c)), "")
        label = next((c for c in cells if c != date and not mention.search(c)), "")
        rows.append({"date": date, "label": label, "report": report_type_of(label), "cells": cells})
    return sorted(rows, key=lambda row: row["date"])


def _fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    """Download a page as text; any failure exits with a message that names the URL."""
    try:
        return _open_url(url, headers).decode("utf-8")
    except FetchError as exc:
        status = f"HTTP {exc.status} " if exc.status is not None else ""
        _die(f"fetch failed for {url}: {status}{exc.detail}")


def _numbered(items: list[str]) -> list[str]:
    """Number list items from 1."""
    return [f"{number}. {item}" for number, item in enumerate(items, start=1)]


class TacScheduleError(Exception):
    """The year's schedule could not be read; the instructions are still printed and the exit code is 1."""


def _schedule_section(site: str, api: str, year: int, project: str, tac_dir: Path) -> list[str]:
    """Fetch the year's schedule (or, when it has no page, the repository directory listing) and describe it."""
    page_url = f"{site}/{year}/{year}-schedule/"
    lines = [f"## Schedule {year}: entries for {project}", ""]
    try:
        html_text = _open_url(page_url).decode("utf-8")
    except FetchError as exc:
        if not exc.not_found:
            status = f"HTTP {exc.status} " if exc.status is not None else ""
            raise TacScheduleError(f"fetch failed for {page_url}: {status}{exc.detail}") from exc
        listing_url = f"{api}/{year}"
        github_headers = {"Accept": "application/vnd.github+json", "User-Agent": "lfdt-report-inventory"}
        try:
            entries = json.loads(_open_url(listing_url, github_headers))
        except FetchError as listing_exc:
            raise TacScheduleError(
                f"no schedule page for {year} ({page_url}: {exc.detail}) and the directory listing also failed "
                f"({listing_url}: {listing_exc.detail})"
            ) from listing_exc
        except ValueError as value_exc:
            raise TacScheduleError(f"{listing_url} did not return JSON ({value_exc})") from value_exc
        if not isinstance(entries, list):
            raise TacScheduleError(f"{listing_url} did not return a directory listing: {str(entries)[:200]}") from None
        names = sorted(e["name"] for e in entries if isinstance(e, dict) and "name" in e)
        (tac_dir / f"{year}-listing.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
        matching = [n for n in names if project.lower() in n.lower()]
        lines += [
            f"No schedule page exists for {year} ({page_url}: {exc.detail}). Fell back to the directory listing",
            f"{listing_url}; it names files, not meeting dates.",
            "",
            *([f"- {name}" for name in matching] or [f"- no file in the {year} directory mentions {project}"]),
        ]
        return lines
    blocks = html_to_blocks(html_text)
    (tac_dir / f"{year}-schedule.txt").write_text(blocks_to_text(blocks), encoding="utf-8")
    rows = schedule_rows(blocks, project)
    lines.append(f"Source: {page_url}")
    lines.append("")
    lines += [f"- {r['date'] or 'no date'}: {r['report']} (schedule says {r['label']!r})" for r in rows] or [
        f"- no row of the {year} schedule mentions {project}"
    ]
    return lines


def cmd_tac(work: Path, year: int, project: str, site: str, api: str) -> int:
    """Read the TAC's instruction and schedule pages and print what a drafter needs from them."""
    site, api = site.rstrip("/"), api.rstrip("/")
    tac_dir = work / "tac"
    tac_dir.mkdir(parents=True, exist_ok=True)
    out = [f"# TAC instructions and schedule ({year}, {project})", ""]
    missing: list[str] = []
    naming: list[str] = []
    for title, slug in TAC_PAGES:
        url = f"{site}/{slug}/"
        blocks = html_to_blocks(_fetch_text(url))
        (tac_dir / f"{slug}.txt").write_text(blocks_to_text(blocks), encoding="utf-8")
        questions, evaluation, sentence = questions_of(blocks), evaluation_of(blocks), naming_sentence_of(blocks)
        for label, found in (("questions", questions), ("evaluation list", evaluation), ("naming sentence", sentence)):
            if not found:
                missing.append(f"{title}: {label} ({url})")
        out += [f"## {title}: the report should answer", "", f"Source: {url}", "", *_numbered(questions), ""]
        out += [f"## {title}: what the TAC evaluates", "", *[f"- {item}" for item in evaluation], ""]
        naming.append(f"- {title}: {sentence or 'NOT FOUND'}")
    out += ["## File naming", "", *naming, ""]
    try:
        out += _schedule_section(site, api, year, project, tac_dir)
    except TacScheduleError as exc:
        out += [f"## Schedule {year}: entries for {project}", "", f"NOT AVAILABLE: {exc}"]
        missing.append(f"schedule: {exc}")
    out += [
        "",
        f"Page text saved under {tac_dir}/ (the lists above are bullets on the pages; numbered here for reference).",
    ]
    print("\n".join(out))
    if missing:
        print(
            "error: could not read everything the TAC pages should hold (a changed layout, or a missing page); "
            "read the saved text under " + str(tac_dir) + ". Missing: " + "; ".join(missing),
            file=sys.stderr,
        )
        return 1
    return 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


ID_FORMS = """\
ID forms (the same for doc and sources):
  understaffed                 a section id
  maintainer-pipeline          a card id: every variant of every chart on it
  maintainer_pipeline_yearly   a chart document id: cited as its card plus the variant
  hip-board                    a view id
  tile:Governance/maintainers  a headline tile, tile:<Macro>/<label>
  understaffed@365d            a section's period table (@7d, @30d, @365d: whichever
                               the document has)
Unknown ids are warned about on stderr, the rest are still printed, and the exit code is 1."""


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the subcommands."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    work_help = "directory holding the fetched files (default: $WORK, else lfdt-report-work in the system temp dir)"
    raw = argparse.RawDescriptionHelpFormatter
    fetch = sub.add_parser("fetch", help="download the manifest and every document the org references")
    fetch.add_argument("org")
    fetch.add_argument("--base", default=DEFAULT_BASE, help="API root (default: %(default)s)")
    fetch.add_argument("--work", help=work_help)
    fetch.add_argument("--refresh", action="store_true", help="download again even when a file is already in WORK")
    show = sub.add_parser("show", help="print a markdown inventory of what the org publishes")
    show.add_argument("org")
    show.add_argument("--work", help=work_help)
    show.add_argument("--json", action="store_true", help="emit the inventory as JSON instead of markdown")
    doc = sub.add_parser(
        "doc",
        help="print the definitions to read before citing each id",
        description="Print, per id, the title, kind, generated_at, stale, note, methodology (with the level each "
        "came from), population, window, frequency, comparison, top_n, row and period counts and a section's "
        "columns. Rows are never printed.",
        epilog=ID_FORMS,
        formatter_class=raw,
    )
    doc.add_argument("org")
    doc.add_argument("ids", nargs="+", metavar="ID", help="what to describe (see the ID forms below)")
    doc.add_argument("--work", help=work_help)
    sources = sub.add_parser(
        "sources",
        help="print numbered Sources-appendix entries for the given ids",
        description="Print one Sources-appendix line per distinct source, numbered from --start.",
        epilog=ID_FORMS,
        formatter_class=raw,
    )
    sources.add_argument("org")
    sources.add_argument("ids", nargs="+", metavar="ID", help="what to cite (see the ID forms below)")
    sources.add_argument("--work", help=work_help)
    sources.add_argument("--start", type=int, default=1, help="number of the first entry (default: 1)")
    sources.add_argument(
        "--sorted",
        action="store_true",
        dest="sort_ids",
        help="order entries by id (ASCII; a card's variants keep manifest order) before numbering, so adding an "
        "id changes the numbers predictably",
    )
    sources.add_argument("--base", default="BASE", help="text printed before each JSON path (default: %(default)s)")
    tac = sub.add_parser(
        "tac",
        help="read the TAC instruction pages and the year's schedule",
        description="Fetch the LFDT annual-review and mid-year instruction pages and the year's schedule page, save "
        "their text under WORK/tac/, and print the questions, what the TAC evaluates, the file-naming sentence and "
        "the schedule rows that mention the project. Needs the network.",
    )
    tac.add_argument("--work", help=work_help)
    tac.add_argument("--year", type=int, default=datetime.now(UTC).year, help="schedule year (default: this year)")
    tac.add_argument("--project", default="Hiero", help="project to look for in the schedule (default: %(default)s)")
    tac.add_argument("--site", default=TAC_SITE, help="project-updates site root (default: %(default)s)")
    tac.add_argument("--api", default=TAC_API, help="GitHub contents API root for the fallback (default: %(default)s)")
    return ap


def main(argv: list[str]) -> int:
    """Dispatch to fetch, show, doc, sources or tac."""
    args = build_parser().parse_args(argv)
    work = Path(args.work) if args.work else default_work()
    if args.cmd == "fetch":
        return cmd_fetch(args.org, args.base, work, args.refresh)
    if args.cmd == "show":
        return cmd_show(args.org, work, args.json)
    if args.cmd == "doc":
        return cmd_doc(args.org, args.ids, work)
    if args.cmd == "tac":
        return cmd_tac(work, args.year, args.project, args.site, args.api)
    return cmd_sources(args.org, args.ids, work, args.start, args.base, args.sort_ids)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
