#!/usr/bin/env python3
"""Fetch, inventory and cite the data API documents behind an LFDT TAC report.

Standard library only. The API is static JSON, so this script never guesses:
it downloads exactly what the manifest references, prints what is there, and
turns the ids a draft cites into numbered Sources-appendix entries.

Usage:
    inventory.py fetch   ORG [--base URL] [--work DIR] [--refresh]
    inventory.py show    ORG [--work DIR] [--json]
    inventory.py sources ORG ID... [--work DIR] [--start N] [--base TEXT]

WORK defaults to ``$WORK`` when set (the SKILL's convention), else
``lfdt-report-work`` under the system temp directory, so the three commands
find each other's files without being told.

``fetch`` saves ``manifest.json`` and every document the org references
(sections, chart variants, views, the two entity indexes) under WORK with
their relative paths, skipping files already there unless ``--refresh``. It
fails loudly on any HTTP or JSON error and prints one provenance line.

``show`` prints a markdown inventory: which macros the org has (and the
manifest's note for each one it lacks), every section with its all-time and
per-period row counts, every chart variant with its frequency or window,
partial buckets and comparison pair, the views, the headline tiles and the
entity counts. ``--json`` emits the same content as one JSON object.

``sources`` takes ids and prints Sources-appendix entries, numbered from
``--start``. An id may be a section id, a card id (every variant of every
chart on it), a chart document id (for example ``maintainer_pipeline_yearly``),
a view id, or ``tile:<Macro>/<label>``. The JSON path is printed as
``BASE/<path>`` (``--base`` replaces the literal ``BASE``) because the report's
data-notes appendix defines BASE once.

Exit codes: 0 success; 1 a fetch failed or ``sources`` met an unknown id
(warned on stderr, the rest still printed); 2 bad input (org not in the
manifest, or WORK has no manifest yet).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

DEFAULT_BASE = "https://hiero-hackers.github.io/analytics/data/api/v1"
DASHBOARD_URL = "https://hiero-hackers.github.io/analytics/"
MANIFEST_NAME = "manifest.json"
ENTITY_KEYS = ("repositories", "contributors")
FETCH_TIMEOUT_SECONDS = 60


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


def _read_url(url: str) -> bytes:
    """Download ``url`` and return its bytes; any failure exits with a message that names the URL."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https", "file"):
        _die(f"refusing {url}: only http, https and file URLs are supported")
    try:
        with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as response:  # noqa: S310 - scheme checked above
            return response.read()
    except urllib.error.HTTPError as exc:
        hint = " (check --base; the published API is " + DEFAULT_BASE + ")" if exc.code == 404 else ""
        _die(
            f"fetch failed for {url}: HTTP {exc.code} {exc.reason}{hint}. The API is unreachable: do not draft from memory or a stale copy"
        )
    except OSError as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        _die(
            f"fetch failed for {url}: host unreachable or not found ({reason}). Check the network and --base; do not draft from memory or a stale copy"
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


def _document_source(kind: str, ref: dict, ws: Workspace, fallback: str) -> dict:
    """Build the source record for a section or view listed in the manifest."""
    return {
        "kind": kind,
        "id": ref["id"],
        "macro": ref["macro"],
        "path": ref["path"],
        "widget": ref["id"],
        "as_of": _as_of(ws, ref["path"], fallback),
    }


def _chart_source(card: dict, variant: dict, ws: Workspace, fallback: str) -> dict:
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
    }


def resolve_source(ws: Workspace, manifest: dict, org: str, ident: str) -> list[dict]:
    """Resolve one id to its source records (empty when the id is unknown).

    Each record carries ``kind``, ``id``, ``macro``, ``path``, ``widget`` (None for a tile),
    ``as_of`` and, for a chart, ``variant`` and ``document_id``.
    """
    entry = org_entry(manifest, org)
    fallback = date_only(provenance(manifest)["data_as_of"]) or "unknown"
    if ident.startswith("tile:"):
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
            }
            for tile in tiles
            if tile.get("label") == label
        ][:1]
    found = [
        _document_source("Section", ref, ws, fallback) for ref in entry.get("sections") or [] if ref["id"] == ident
    ]
    found.extend(
        _chart_source(card, variant, ws, fallback)
        for card, _chart, variant in iter_variants(entry)
        if ident in (card["id"], variant_document_id(ws, variant))
    )
    found.extend(_document_source("View", ref, ws, fallback) for ref in entry.get("views") or [] if ref["id"] == ident)
    return found


def dashboard_link(org: str, macro: str, widget: str | None) -> str:
    """Return the dashboard deep link for a tab (and a card or section on it)."""
    link = f"{DASHBOARD_URL}#tab={urllib.parse.quote(macro, safe='')}&org={urllib.parse.quote(org, safe='')}"
    if widget:
        link += f"&widget={urllib.parse.quote(widget, safe='')}"
    return link


def format_source(number: int, src: dict, org: str, base: str) -> str:
    """Format one Sources-appendix entry on a single line."""
    head = f"[{number}] {src['kind']} {src['id']}"
    if "variant" in src:
        head += f", {src['variant']} variant ({src['document_id']})"
    return (
        f"{head}; data as of {src['as_of']}. JSON: {base}/{src['path']}. "
        f"Dashboard: {dashboard_link(org, src['macro'], src['widget'])}"
    )


def cmd_sources(org: str, idents: list[str], work: Path, start: int, base: str) -> int:
    """Print one numbered Sources entry per distinct source; warn on unknown ids and exit 1 at the end."""
    ws = Workspace(work)
    manifest = ws.manifest()
    org_entry(manifest, org)
    seen: set[tuple] = set()
    number = start
    unknown = 0
    for ident in idents:
        records = resolve_source(ws, manifest, org, ident)
        if not records:
            print(f"warning: unknown id {ident!r} for org {org}; no entry written", file=sys.stderr)
            unknown += 1
            continue
        for record in records:
            key = (record["kind"], record["id"], record.get("document_id"))
            if key in seen:
                continue
            seen.add(key)
            print(format_source(number, record, org, base))
            number += 1
    return 1 if unknown else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the three subcommands."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    work_help = "directory holding the fetched files (default: $WORK, else lfdt-report-work in the system temp dir)"
    fetch = sub.add_parser("fetch", help="download the manifest and every document the org references")
    fetch.add_argument("org")
    fetch.add_argument("--base", default=DEFAULT_BASE, help="API root (default: %(default)s)")
    fetch.add_argument("--work", help=work_help)
    fetch.add_argument("--refresh", action="store_true", help="download again even when a file is already in WORK")
    show = sub.add_parser("show", help="print a markdown inventory of what the org publishes")
    show.add_argument("org")
    show.add_argument("--work", help=work_help)
    show.add_argument("--json", action="store_true", help="emit the inventory as JSON instead of markdown")
    sources = sub.add_parser("sources", help="print numbered Sources-appendix entries for the given ids")
    sources.add_argument("org")
    sources.add_argument(
        "ids", nargs="+", metavar="ID", help="section, card, chart document or view id, or tile:<Macro>/<label>"
    )
    sources.add_argument("--work", help=work_help)
    sources.add_argument("--start", type=int, default=1, help="number of the first entry (default: 1)")
    sources.add_argument("--base", default="BASE", help="text printed before each JSON path (default: %(default)s)")
    return ap


def main(argv: list[str]) -> int:
    """Dispatch to fetch, show or sources."""
    args = build_parser().parse_args(argv)
    work = Path(args.work) if args.work else default_work()
    if args.cmd == "fetch":
        return cmd_fetch(args.org, args.base, work, args.refresh)
    if args.cmd == "show":
        return cmd_show(args.org, work, args.json)
    return cmd_sources(args.org, args.ids, work, args.start, args.base)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
