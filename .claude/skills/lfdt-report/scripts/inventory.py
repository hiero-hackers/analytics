#!/usr/bin/env python3
"""Fetch the data API documents behind an LFDT TAC report and number their sources.

Standard library only. The API is static JSON, so this script never guesses:
it downloads exactly what the manifest references, and turns the ids a draft
cites into numbered Sources-appendix entries.

Usage:
    inventory.py fetch   ORG [--base URL] [--work DIR] [--refresh]
    inventory.py sources ORG ID... [--work DIR] [--start N] [--sorted] [--base TEXT]

WORK defaults to ``$WORK`` when set (the SKILL's convention), else
``lfdt-report-work`` under the system temp directory.

``fetch`` saves ``manifest.json`` and every document the org references
(sections, chart variants, views, the two entity indexes) under WORK with
their relative paths, skipping files already there unless ``--refresh``. It
fails loudly on any HTTP or JSON error and prints one provenance line.

``sources`` prints Sources-appendix entries, numbered from ``--start``. An id
is one of:

    understaffed          a section id
    maintainer-pipeline   a card id (every variant of every chart on it)
    maintainer_pipeline_yearly
                          a chart document id (cited as its card and variant)
    hip-board             a view id
    tile:Governance/maintainers
                          a headline tile, as tile:<Macro>/<label>
    understaffed@365d     a section's period table (the period must be one the
                          document has, for example 7d, 30d or 365d)

The JSON path is printed as ``BASE/<path>`` (``--base`` replaces the literal
``BASE``) because the report's data-notes appendix defines BASE once.
``--sorted`` orders the entries by id before numbering, so adding an id
changes the numbers predictably.

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
    return 0


# --------------------------------------------------------------------------
# show
# --------------------------------------------------------------------------


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
    """An id given to ``sources`` names nothing in the manifest (the message says why)."""


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


# --------------------------------------------------------------------------
# tac
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


ID_FORMS = """\
ID forms for sources:
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
    return ap


def main(argv: list[str]) -> int:
    """Dispatch to fetch or sources."""
    args = build_parser().parse_args(argv)
    work = Path(args.work) if args.work else default_work()
    if args.cmd == "fetch":
        return cmd_fetch(args.org, args.base, work, args.refresh)
    return cmd_sources(args.org, args.ids, work, args.start, args.base, args.sort_ids)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
