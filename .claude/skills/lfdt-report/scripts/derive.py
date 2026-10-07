#!/usr/bin/env python3
"""Derive the figures a TAC report needs but no published document states.

Standard library only. Each subcommand reads one data-API document, prints a
markdown table, and ends with one line beginning ``Derived:`` that says exactly
what was computed and from which document, so a drafter can paste it into the
appendix as the derivation note.

Usage:
    derive.py releases RELEASE_TIMELINE.json --from YYYY-MM --to YYYY-MM
    derive.py months TIMESERIES.json --from YYYY-MM --to YYYY-MM [--compare YYYY-MM,YYYY-MM]
    derive.py period SECTION.json [--period 7d|30d|365d|all] [--where COL=VALUE ...]
    derive.py hips HIP_EVIDENCE.json [--funnel HIP_ADOPTION_FUNNEL.json] [--board HIP_BOARD.json]
                   [--from YYYY-MM --to YYYY-MM]
    derive.py single-employer REPODIVERSITY_OR_TEAMDIVERSITY.json

Exit status is 0 on success and 2 when the input is unusable (unreadable file,
wrong document shape, unknown column). Nothing here touches the network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
PERIOD_ORDER = ("7d", "30d", "365d")
COMPARISON_OPS = ("<=", ">=", "<", ">")
# The funnel's stage 2 keeps only specs with one of these frontmatter statuses.
FUNNEL_STATUSES = ("Approved", "Accepted", "Final", "Active")
FUNNEL_STAGE = "implementation evidence"
DEFAULT_COHORT = "all specs"
MERGED_FIELD = "pr_merged_at"  # the only date a hip-evidence row carries
TOTAL_KEY = "\0total"  # synthetic column key for the per-month sum of the series


class DeriveError(Exception):
    """The input cannot support the requested derivation."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _month_arg(text: str) -> str:
    """Validate a YYYY-MM argument for argparse."""
    if not MONTH_RE.match(text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a month in YYYY-MM form")
    return text


def _months_arg(text: str) -> list[str]:
    """Validate a comma-separated list of YYYY-MM months for argparse."""
    return [_month_arg(part.strip()) for part in text.split(",") if part.strip()]


def _load(path: str) -> dict:
    """Read a JSON document whose root is an object."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise DeriveError(f"cannot read {path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise DeriveError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise DeriveError(f"{path} is not a JSON object")
    return doc


def _rows(doc: dict, path: str) -> list[dict]:
    """Return the document's rows list, or fail with the file name."""
    rows = doc.get("rows")
    if not isinstance(rows, list):
        raise DeriveError(f"{path} has no 'rows' list; is it a section or chart document?")
    return rows


def _source(doc: dict, path: str) -> str:
    """Name a document for the Derived line: its id, or the file stem, plus when it was generated."""
    name = doc.get("id") or Path(path).stem
    generated = doc.get("generated_at")
    return f"{name} (generated {generated})" if generated else str(name)


def _stale_notes(doc: dict, path: str) -> list[str]:
    """A note line when the document says its own data is stale."""
    if doc.get("stale") is True:
        return [f"Note: {doc.get('id') or Path(path).stem} says stale: true; say so next to any figure taken from it."]
    return []


def _num(value: object) -> float | None:
    """A number from an int, float or numeric string; None for anything else (bool included)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _fmt(value: object) -> str:
    """Render a table cell: integers without a decimal point, missing values as n/a."""
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else f"{value:g}"
    return str(value)


def _table(headers: list[str], rows: list[list[object]], right: tuple[int, ...] = ()) -> list[str]:
    """Render a markdown table; columns listed in `right` are right-aligned."""

    def cell(value: object) -> str:
        """Escape pipes so a value cannot break the table."""
        return _fmt(value).replace("|", "\\|")

    lines = ["| " + " | ".join(cell(h) for h in headers) + " |"]
    lines.append("|" + "|".join("---:" if i in right else "---" for i in range(len(headers))) + "|")
    lines.extend("| " + " | ".join(cell(c) for c in row) + " |" for row in rows)
    return lines


def _month_range(start: str, end: str) -> list[str]:
    """Every YYYY-MM from start to end inclusive."""
    if start > end:
        raise DeriveError(f"--from {start} is after --to {end}")
    year, month = int(start[:4]), int(start[5:7])
    out = []
    while f"{year:04d}-{month:02d}" <= end:
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _parse_dt(text: object) -> datetime | None:
    """Parse an ISO timestamp as UTC; None when it is missing or malformed."""
    if not isinstance(text, str):
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# releases
# ---------------------------------------------------------------------------


def _window_warnings(doc: dict, start: str, end: str) -> list[str]:
    """Warn when the month range runs outside the release document's trailing window."""
    window = doc.get("window")
    if not isinstance(window, dict):
        return []
    out = []
    window_end = _parse_dt(window.get("end")) or _parse_dt(doc.get("generated_at"))
    days = window.get("days")
    if window.get("kind") == "trailing" and window_end is not None and isinstance(days, int):
        window_start = window_end - timedelta(days=days)
        first = datetime(int(start[:4]), int(start[5:7]), 1, tzinfo=UTC)
        if first < window_start:
            out.append(
                f"Warning: --from {start} begins before the document's window start "
                f"({window_start:%Y-%m-%d}), so months it only partly covers are undercounted."
            )
    if window_end is not None and f"{window_end:%Y-%m}" <= end:
        out.append(
            f"Warning: --to {end} is the month the document was generated ({window_end:%Y-%m-%d}), "
            "so it is a partial month; end at the last complete month."
        )
    return out


def releases_report(doc: dict, path: str, start: str, end: str) -> list[str]:
    """Count release and prerelease events per repository whose time month is in start..end inclusive."""
    rows = _rows(doc, path)
    per_repo: dict[str, Counter] = {}
    before = 0
    after: Counter = Counter()
    unreadable = 0
    other_types: Counter = Counter()
    for row in rows:
        month = str(row.get("time", ""))[:7]
        if not MONTH_RE.match(month):
            unreadable += 1
        elif month < start:
            before += 1
        elif month > end:
            after[month] += 1
        elif row.get("type") in ("release", "prerelease"):
            per_repo.setdefault(str(row.get("repo", "(no repo)")), Counter())[row["type"]] += 1
        else:
            other_types[str(row.get("type"))] += 1
    if not per_repo:
        raise DeriveError(f"no release or prerelease events between {start} and {end} in {path}")
    ordered = sorted(per_repo.items(), key=lambda kv: (-kv[1]["release"], -kv[1]["prerelease"], kv[0]))
    releases = sum(c["release"] for c in per_repo.values())
    prereleases = sum(c["prerelease"] for c in per_repo.values())
    table = [[repo, c["release"], c["prerelease"]] for repo, c in ordered]
    table.append(["**Total**", f"**{releases}**", f"**{prereleases}**"])
    out = _table(["Repository", "Releases", "Prereleases"], table, right=(1, 2))
    out.append("")
    excluded_after = sum(after.values())
    months_after = ", ".join(f"{m}: {n}" for m, n in sorted(after.items())) or "none"
    out.append(f"Excluded after {end}: {excluded_after} events ({months_after}).")
    out.append(f"Excluded before {start}: {before} events.")
    out.append(
        f"Reconciliation: {releases + prereleases} in range + {before} before + {excluded_after} after"
        f"{f' + {unreadable} without a readable time' if unreadable else ''} = {len(rows)} events in the document."
    )
    if other_types:
        kinds = ", ".join(f"{k}: {n}" for k, n in sorted(other_types.items()))
        out.append(f"Warning: events with an unrecognised type were left out of the table ({kinds}).")
    out.extend(_window_warnings(doc, start, end))
    out.extend(_stale_notes(doc, path))
    out.append(
        f"Derived: {releases} releases and {prereleases} prereleases across {len(per_repo)} repositories, counted from "
        f"each event's `time` (UTC) month in {_source(doc, path)}, {start} to {end} inclusive; "
        f"{excluded_after} events dated after {end} were excluded ({months_after})."
    )
    return out


# ---------------------------------------------------------------------------
# months
# ---------------------------------------------------------------------------


def _series_of(doc: dict, cat_key: str) -> list[tuple[str, str]]:
    """The (key, label) of every series; falls back to the numeric row keys when none are declared."""
    declared = doc.get("series")
    if isinstance(declared, list) and declared:
        return [
            (str(s["key"]), str(s.get("label") or s["key"])) for s in declared if isinstance(s, dict) and "key" in s
        ]
    keys: list[str] = []
    for row in _rows(doc, "document"):
        keys.extend(k for k in row if k not in (cat_key, "partial") and k not in keys)
    return [(k, k) for k in keys]


def _total_label(doc: dict) -> str:
    """Label the per-month sum; 'distinct people' only when the document counts each person once per bucket."""
    if "counted once" in str(doc.get("population", "")).lower():
        return "Total (distinct people, all roles)"
    return "Total (sum of series)"


def _value(row: dict, key: str, series: list[tuple[str, str]]) -> float | None:
    """One cell of a month row; the synthetic total is the sum of the series, or None if any is missing."""
    if key != TOTAL_KEY:
        return _num(row.get(key))
    parts = [_num(row.get(k)) for k, _ in series]
    return None if any(part is None for part in parts) else float(sum(p for p in parts if p is not None))


def months_report(doc: dict, path: str, start: str, end: str, compare: list[str] | None) -> list[str]:
    """Per-month series values and their total over start..end, skipping partial months, with min, max and comparisons."""
    if doc.get("frequency") != "month":
        raise DeriveError(
            f"{path} has frequency {doc.get('frequency')!r}; the months command needs a monthly timeseries"
        )
    rows = _rows(doc, path)
    cat_key = (doc.get("category") or {}).get("key", "bucket")
    series = _series_of(doc, cat_key)
    columns = [*series, (TOTAL_KEY, _total_label(doc))] if len(series) > 1 else series
    by_bucket = {str(r[cat_key]): r for r in rows if cat_key in r}
    shown: list[str] = []
    skipped: list[str] = []
    missing: list[str] = []
    for month in _month_range(start, end):
        row = by_bucket.get(month)
        if row is None:
            missing.append(month)
        elif row.get("partial"):
            skipped.append(month)
        else:
            shown.append(month)
    if not shown:
        covered = f"{min(by_bucket)} to {max(by_bucket)}" if by_bucket else "no buckets"
        raise DeriveError(f"no complete month in {start}..{end} in {path} (document covers {covered})")

    table = [[m, *[_value(by_bucket[m], key, series) for key, _ in columns]] for m in shown]
    out = _table(["Month", *[label for _, label in columns]], table, right=tuple(range(1, len(columns) + 1)))
    out.append("")
    extremes = []
    for key, label in columns:
        known = [(m, n) for m in shown if (n := _value(by_bucket[m], key, series)) is not None]
        if not known:
            extremes.append([label, "n/a", "n/a", "n/a", "n/a"])
            continue
        low = min(n for _, n in known)
        high = max(n for _, n in known)
        low_months = [m for m, n in known if n == low]
        high_months = [m for m, n in known if n == high]
        extremes.append([label, low, _tied(low_months), high, _tied(high_months)])
    out.extend(_table(["Series", "Min", "Min month", "Max", "Max month"], extremes, right=(1, 3)))
    out.append("")
    all_partial = sorted(b for b, r in by_bucket.items() if r.get("partial"))
    outside = [b for b in all_partial if b not in skipped]
    out.append(
        f"Skipped partial months in range: {', '.join(skipped) if skipped else 'none'}"
        + (f"; the document's other partial buckets, outside the range: {', '.join(outside)}" if outside else "")
        + "."
    )
    if missing:
        out.append(f"Months in range not in the document: {', '.join(missing)}.")
    if compare:
        out.append("")
        out.append("Comparison months (as asked with --compare):")
        out.extend(_comparison_table(by_bucket, columns, series, compare))
    pair = doc.get("comparison")
    out.append("")
    if isinstance(pair, dict) and pair.get("current") and pair.get("previous"):
        out.append("The document's own `comparison` pair, two adjacent buckets (not 'since the last report'):")
        out.extend(
            _comparison_table(by_bucket, columns, series, [str(pair["previous"]), str(pair["current"])], tag_pair=pair)
        )
    else:
        out.append("The document has no `comparison` pair.")
    out.extend(_stale_notes(doc, path))
    keys = ", ".join(k for k, _ in series)
    compared = f"; comparison months {', '.join(compare)} read from the same document" if compare else ""
    skipped_text = f"skipped partial month(s) {', '.join(skipped)}" if skipped else "no partial month fell in the range"
    total_text = (
        f"; {columns[-1][1]} is the sum of the series within a single month"
        + (", valid because the document counts each person once per bucket" if "distinct" in columns[-1][1] else "")
        if len(columns) > len(series)
        else ""
    )
    out.append(
        f"Derived: per-month values of series {keys} (unit: {doc.get('unit', 'as published')}; one value per month, "
        f"never summed across months) read from {_source(doc, path)} for {start} to {end}; {skipped_text}; "
        f"min and max are over the {len(shown)} complete months shown{total_text}{compared}."
    )
    return out


def _tied(months: list[str]) -> str:
    """The first month at an extreme, with a count of other months that share it."""
    return months[0] if len(months) == 1 else f"{months[0]} (+{len(months) - 1} tied)"


def _comparison_table(
    by_bucket: dict[str, dict],
    columns: list[tuple[str, str]],
    series: list[tuple[str, str]],
    months: list[str],
    tag_pair: dict | None = None,
) -> list[str]:
    """Column values for chosen months; a partial or absent bucket is named and not used."""
    table = []
    for month in months:
        row = by_bucket.get(month)
        tags = []
        if tag_pair:
            tags.append("current" if month == tag_pair.get("current") else "previous")
        if row is None:
            tags.append("not in the document")
        elif row.get("partial"):
            tags.append("partial, not used")
        name = month + (f" ({', '.join(tags)})" if tags else "")
        usable = row is not None and not row.get("partial")
        table.append([name, *[_value(row, k, series) if usable else None for k, _ in columns]])
    return _table(["Month", *[label for _, label in columns]], table, right=tuple(range(1, len(columns) + 1)))


# ---------------------------------------------------------------------------
# period
# ---------------------------------------------------------------------------


def _parse_where(text: str) -> tuple[str, str, str]:
    """Split COL=VALUE into (column, operator, operand); VALUE may start with <, >, <= or >=."""
    if "=" not in text:
        raise DeriveError(f"--where {text!r} needs the form COL=VALUE, for example maintainers=<=1")
    column, _, value = text.partition("=")
    column = column.strip()
    for op in COMPARISON_OPS:
        if value.startswith(op):
            operand = value[len(op) :].strip()
            if _num(operand) is None:
                raise DeriveError(f"--where {text!r}: {operand!r} after {op} is not a number")
            return column, op, operand
    return column, "=", value


def _cell_matches(cell: object, op: str, operand: str) -> bool:
    """Compare one cell: equality on strings (numbers and booleans by value), ordering only on numbers."""
    if op != "=":
        number = _num(cell)
        if number is None:
            return False
        target = float(operand)
        return {"<": number < target, ">": number > target, "<=": number <= target, ">=": number >= target}[op]
    if isinstance(cell, bool):
        return operand.lower() == ("true" if cell else "false")
    if cell is None:
        return operand.lower() in ("", "null", "none")
    if isinstance(cell, int | float):
        target = _num(operand)
        return target is not None and float(cell) == target
    return str(cell) == operand


def _filter_rows(rows: list[dict], filters: list[tuple[str, str, str]]) -> tuple[list[dict], int]:
    """Rows that satisfy every filter, and how many cells were skipped for a numeric test on a non-number."""
    matched = []
    unusable = 0
    for row in rows:
        keep = True
        for column, op, operand in filters:
            cell = row.get(column)
            if op != "=" and _num(cell) is None:
                unusable += 1
            if not _cell_matches(cell, op, operand):
                keep = False
                break
        if keep:
            matched.append(row)
    return matched, unusable


def period_report(doc: dict, path: str, period: str, where: list[str]) -> list[str]:
    """Row counts for all-time and every period, then the count matching the filters in the chosen period."""
    all_rows = _rows(doc, path)
    periods = doc.get("periods") if isinstance(doc.get("periods"), dict) else {}
    tables: list[tuple[str, list[dict]]] = [("all", all_rows)]
    ordered = [p for p in PERIOD_ORDER if p in periods] + sorted(p for p in periods if p not in PERIOD_ORDER)
    tables.extend((p, periods[p]) for p in ordered)
    if period not in dict(tables):
        have = ", ".join(["all", *ordered])
        raise DeriveError(f"{path} has no {period} table (available: {have})")
    chosen = dict(tables)[period]
    filters = [_parse_where(w) for w in where]
    known = {c["key"] for c in doc.get("columns", []) if isinstance(c, dict) and "key" in c}
    for _, rows in tables:
        for row in rows:
            known.update(row)
    for column, _, _ in filters:
        if column not in known:
            hint = (
                f" Write the operator after the equals sign, for example {column.rstrip('<>')}=<=1."
                if column.endswith(("<", ">"))
                else ""
            )
            raise DeriveError(
                f"--where column {column!r} is not in {path}; columns are: {', '.join(sorted(known))}.{hint}"
            )
    matched, unusable = _filter_rows(chosen, filters)
    name = {"all": "all-time"}.get(period, period)
    headers = ["Period", "Rows"] + (["Matching the --where filters"] if filters else [])
    table = []
    for key, rows in tables:
        row = [{"all": "all-time"}.get(key, key), len(rows)]
        if filters:
            row.append(len(matched) if key == period else "-")
        table.append(row)
    out = _table(headers, table, right=(1, 2) if filters else (1,))
    out.append("")
    if doc.get("row_count") is not None and doc["row_count"] != len(all_rows):
        out.append(f"Warning: row_count says {doc['row_count']} but the all-time rows list has {len(all_rows)}.")
    if not periods:
        out.append("Note: the document has no `periods`; only the all-time table exists.")
    if period != "all" and chosen == all_rows:
        out.append(f"Note: the {period} rows are identical to the all-time rows (an org younger than the period).")
    if unusable:
        out.append(f"Warning: {unusable} cell(s) in a numeric --where column were not numbers and did not match.")
    final = len(matched) if filters else len(chosen)
    if final == 0:
        out.append(
            "Note: zero rows. Read the section's own description: for an exception list it is a measured 'none'; "
            "for a population it is a gap, not a zero."
        )
    out.extend(_stale_notes(doc, path))
    counts = ", ".join(f"{'all-time' if k == 'all' else k} {len(r)}" for k, r in tables)
    if filters:
        shown = " and ".join(f"{c} {'==' if op == '=' else op} {v}" for c, op, v in filters)
        out.append(
            f"Derived: {len(matched)} of the {len(chosen)} rows in the {name} table of {_source(doc, path)} match {shown} "
            f"(strings compared exactly, numbers numerically; counts by table: {counts})."
        )
    else:
        out.append(
            f"Derived: {len(chosen)} rows in the {name} table of {_source(doc, path)}, counted as the length of that "
            f"rows list (counts by table: {counts})."
        )
        keys = [c["key"] for c in doc.get("columns", []) if isinstance(c, dict) and "key" in c]
        keys = keys or list(dict.fromkeys(k for r in chosen or all_rows for k in r))
        out.append(f"add --where COL=VALUE to count matching rows; columns: {', '.join(keys)}")
    return out


# ---------------------------------------------------------------------------
# hips
# ---------------------------------------------------------------------------


def _funnel_value(funnel: dict, path: str, cohort: str) -> int:
    """The funnel's implementation-evidence value for a cohort."""
    rows = _rows(funnel, path)
    series_key = ((funnel.get("series") or [{}])[0]).get("key", "hips")
    has_cohort = any("cohort" in r for r in rows)
    for row in rows:
        if str(row.get("stage", "")).lower() == FUNNEL_STAGE and (not has_cohort or row.get("cohort") == cohort):
            value = _num(row.get(series_key))
            if value is not None:
                return int(value)
    pairs = ", ".join(f"{r.get('stage')} / {r.get('cohort')}" for r in rows)
    raise DeriveError(f"{path} has no stage {FUNNEL_STAGE!r} for cohort {cohort!r} (stage / cohort rows: {pairs})")


def _board_statuses(board: dict, path: str) -> dict[int, str]:
    """Map HIP number to frontmatter status from the hip-board document's columns of items."""
    out: dict[int, str] = {}
    columns = board.get("columns")
    if not isinstance(columns, list):
        raise DeriveError(f"{path} has no 'columns' list of HIP items; is it the hip-board section?")
    for col in columns:
        for item in col.get("items", []) if isinstance(col, dict) else []:
            number = _num(item.get("key"))
            if number is not None:
                out[int(number)] = str(item.get("status"))
    return out


def _merge_month(row: dict) -> str | None:
    """The YYYY-MM of a row's pr_merged_at (ISO date or timestamp), or None when it is missing or unreadable."""
    month = str(row.get(MERGED_FIELD) or "")[:7]
    return month if MONTH_RE.match(month) else None


def _hip_numbers(rows: list[dict]) -> set[int]:
    """Distinct HIP numbers among evidence rows."""
    return {int(r["hip"]) for r in rows if _num(r.get("hip")) is not None}


def hips_report(
    doc: dict,
    path: str,
    funnel: dict | None = None,
    funnel_path: str = "funnel",
    cohort: str = DEFAULT_COHORT,
    board: dict | None = None,
    board_path: str = "board",
    start: str | None = None,
    end: str | None = None,
) -> list[str]:
    """Distinct HIPs with a counted, merged citing PR (optionally merged within start..end), versus the funnel."""
    rows = _rows(doc, path)
    for needed in ("hip", "counted", "pr_state", *([MERGED_FIELD] if start else [])):
        if rows and needed not in rows[0]:
            raise DeriveError(f"{path} rows have no {needed!r} column; is it the hip-evidence section?")
    odd = {type(r.get("counted")).__name__ for r in rows if not isinstance(r.get("counted"), bool | type(None))}
    if odd:
        raise DeriveError(f"{path}: `counted` holds {', '.join(sorted(odd))} values, expected booleans")
    merged = [r for r in rows if r.get("counted") is True and str(r.get("pr_state", "")).upper() == "MERGED"]
    hips = _hip_numbers(merged)
    table: list[list[object]] = [
        ["hip-evidence rows", len(rows)],
        ["Rows with counted = true and pr_state = MERGED", len(merged)],
    ]
    notes: list[str] = []
    if start is not None and end is not None:
        dated = [(r, _merge_month(r)) for r in merged]
        scoped = [r for r, month in dated if month is not None and start <= month <= end]
        undated = sum(1 for _, month in dated if month is None)
        scoped_hips = _hip_numbers(scoped)
        table.append([f"...of those, rows whose {MERGED_FIELD} month is {start} to {end}", len(scoped)])
        table.append([f"Distinct HIP numbers among the {start} to {end} rows", len(scoped_hips)])
        derived = (
            f"{len(scoped_hips)} distinct HIP numbers have at least one row with counted = true and "
            f"pr_state = MERGED whose {MERGED_FIELD} month is {start} to {end} inclusive "
            f"({len(scoped)} such rows of {len(merged)} counted merged rows, {len(rows)} rows in all) "
            f"in {_source(doc, path)}"
        )
        notes.append(
            f"Note: a HIP is counted if any counted merged PR citing it was merged in {start} to {end}, including HIPs "
            "that already had earlier evidence; this is not 'first implemented in the range'."
        )
        if undated:
            derived += (
                f"; {undated} counted merged rows have no readable {MERGED_FIELD} and are excluded from the range"
            )
            notes.append(
                f"Warning: {undated} counted merged rows have no readable {MERGED_FIELD}; the rows carry no other "
                "date field, so they are excluded from the range."
            )
        generated = _parse_dt(doc.get("generated_at"))
        if generated is not None and f"{generated:%Y-%m}" <= end:
            notes.append(
                f"Warning: --to {end} is the month the document was generated ({generated:%Y-%m-%d}), so it is a "
                "partial month; end at the last complete month."
            )
    else:
        table.append(["Distinct HIP numbers among those rows", len(hips)])
        derived = (
            f"{len(hips)} distinct HIP numbers have at least one row with counted = true and pr_state = MERGED "
            f"({len(merged)} such rows of {len(rows)}) in {_source(doc, path)}"
        )
    if funnel is not None:
        value = _funnel_value(funnel, funnel_path, cohort)
        diff = len(hips) - value
        scoped_run = start is not None
        if scoped_run:
            table.append(["Distinct HIP numbers among all counted merged rows, any merge date", len(hips)])
        table.append([f"Funnel stage '{FUNNEL_STAGE}', cohort '{cohort}'", value])
        table.append(["Difference (evidence minus funnel)" + (", any merge date" if scoped_run else ""), diff])
        if scoped_run:
            notes.append(
                f"Note: the funnel comparison is unscoped. The funnel is cohort-based, not period-based, so the "
                f"funnel's {value} is compared with the {len(hips)} HIPs counted across all merge dates, not with the "
                f"{start} to {end} count."
            )
            derived += (
                f"; the funnel comparison is unscoped because the funnel is cohort-based, not period-based: "
                f"{len(hips)} HIPs across all merge dates against"
            )
        else:
            derived += "; against"
        derived += (
            f" the funnel's '{FUNNEL_STAGE}' stage for cohort '{cohort}' in {_source(funnel, funnel_path)}, "
            f"which is {value}, difference {diff}"
        )
        notes.extend(_funnel_reason(funnel, funnel_path, board is not None))
        if _funnel_stage2(funnel):
            derived += (
                "; the funnel's stage 2 admits only specs with status "
                f"{', '.join(FUNNEL_STATUSES[:-1])} or {FUNNEL_STATUSES[-1]}, so Deferred specs are not in it"
            )
        notes.extend(_stale_notes(funnel, funnel_path))
        if board is not None:
            statuses = _board_statuses(board, board_path)
            outside = sorted(h for h in hips if statuses.get(h) not in FUNNEL_STATUSES)
            named = ", ".join(f"HIP-{h} ({statuses.get(h, 'no board entry')})" for h in outside) or "none"
            verdict = (
                "equal to the difference"
                if len(outside) == diff
                else f"{len(outside)} against a difference of {diff}, so the gap is not fully explained"
            )
            notes.append(
                f"Counted HIPs whose status in {board.get('id') or board_path} is not "
                f"{'/'.join(FUNNEL_STATUSES)}: {named} ({verdict})."
            )
            derived += (
                f"; HIPs counted here but outside the funnel's statuses per {_source(board, board_path)}: {named}"
            )
    out = _table(["Measure", "Count"], table, right=(1,))
    out.append("")
    out.extend(notes)
    out.extend(_stale_notes(doc, path))
    out.append(f"Derived: {derived}.")
    return out


def _funnel_stage2(funnel: dict) -> str | None:
    """The funnel's stage 2 methodology line when it admits only the approved-or-later statuses."""
    lines = funnel.get("methodology")
    if not isinstance(lines, list):
        return None
    stage2 = next((m for m in lines if isinstance(m, str) and m.startswith("Stage 2")), None)
    return stage2 if stage2 and all(s in stage2 for s in FUNNEL_STATUSES) else None


def _funnel_reason(funnel: dict, path: str, board_given: bool = False) -> list[str]:
    """Quote the funnel's stage 2 rule as the reason Deferred specs are missing from it; empty if it is not stated."""
    stage2 = _funnel_stage2(funnel)
    if stage2 is None:
        return []
    return [
        f'Note: {funnel.get("id") or path} excludes Deferred specs. Its methodology says: "{stage2}" '
        + (
            "The hip-board check below names the counted HIPs outside them."
            if board_given
            else "Evidence rows carry no status, so this script cannot say which counted HIPs fall outside those "
            "statuses; pass --board with the hip-board document to name them."
        )
    ]


# ---------------------------------------------------------------------------
# single-employer
# ---------------------------------------------------------------------------


def single_employer_report(doc: dict, path: str) -> list[str]:
    """Single-employer rows by the table's reading and by the reading that approximates the dashboard chart."""
    rows = _rows(doc, path)
    if rows and "distinct_orgs" not in rows[0]:
        raise DeriveError(f"{path} rows have no 'distinct_orgs' column; is it repodiversity or teamdiversity?")
    first = [r for r in rows if r.get("distinct_orgs") == 1]
    table: list[list[object]] = [
        ["Rows in the document", len(rows)],
        ["distinct_orgs == 1 (the table's reading)", len(first)],
    ]
    sample = rows[0] if rows else {}
    notes = []
    if "independent" in sample and "unknown" in sample:
        second = [r for r in first if r.get("independent") == 0 and r.get("unknown") == 0]
        rule = "distinct_orgs == 1 and independent == 0 and unknown == 0"
        notes.append("Columns used for the second reading: distinct_orgs, independent, unknown.")
    elif "single_employer" in sample:
        second = [r for r in first if r.get("single_employer") is True]
        rule = "distinct_orgs == 1 and single_employer is true"
        notes.append(
            "Columns used for the second reading: distinct_orgs, single_employer. This document has no independent "
            "column, so its own single_employer flag (every resolved seat shares one employer) stands in for it."
        )
    else:
        second = None
        rule = ""
        notes.append(
            "Warning: no independent/unknown columns and no single_employer flag, so only the table's reading is available."
        )
    derived = f"{len(first)} rows have distinct_orgs == 1 in {_source(doc, path)}"
    if second is not None:
        table.append([f"{rule} (approximates the dashboard chart)", len(second)])
        derived += (
            f"; {len(second)} of them also satisfy {rule}, which approximates the dashboard's single-employer chart "
            "(the table's count includes rows whose other seats are independent or unknown; the chart does not)"
        )
    out = _table(["Reading", "Rows"], table, right=(1,))
    out.append("")
    out.extend(notes)
    out.extend(_stale_notes(doc, path))
    out.append(f"Derived: {derived}.")
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per derivation."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("releases", help="release and prerelease events per repository in a month range")
    p.add_argument("doc")
    p.add_argument("--from", dest="start", type=_month_arg, required=True, metavar="YYYY-MM")
    p.add_argument("--to", dest="end", type=_month_arg, required=True, metavar="YYYY-MM")

    p = sub.add_parser("months", help="per-month values of a monthly timeseries, skipping partial months")
    p.add_argument("doc")
    p.add_argument("--from", dest="start", type=_month_arg, required=True, metavar="YYYY-MM")
    p.add_argument("--to", dest="end", type=_month_arg, required=True, metavar="YYYY-MM")
    p.add_argument("--compare", type=_months_arg, metavar="YYYY-MM,YYYY-MM", help="months to print beside the range")

    p = sub.add_parser("period", help="row counts per period table, and the count matching filters")
    p.add_argument("doc")
    p.add_argument("--period", choices=["7d", "30d", "365d", "all"], default="all")
    p.add_argument("--where", nargs="+", action="extend", default=[], metavar="COL=VALUE")

    p = sub.add_parser("hips", help="distinct HIPs with merged counted evidence, versus the adoption funnel")
    p.add_argument("doc")
    p.add_argument("--funnel", metavar="HIP_ADOPTION_FUNNEL.json")
    p.add_argument(
        "--cohort", default=DEFAULT_COHORT, help=f"funnel cohort to compare with (default: {DEFAULT_COHORT!r})"
    )
    p.add_argument("--board", metavar="HIP_BOARD.json", help="name the counted HIPs whose status the funnel excludes")
    p.add_argument(
        "--from",
        dest="start",
        type=_month_arg,
        metavar="YYYY-MM",
        help=f"scope the evidence to PRs whose {MERGED_FIELD} month is in --from..--to (the funnel stays unscoped)",
    )
    p.add_argument("--to", dest="end", type=_month_arg, metavar="YYYY-MM")

    p = sub.add_parser("single-employer", help="single-employer rows of repodiversity or teamdiversity")
    p.add_argument("doc")
    return ap


def _run(a: argparse.Namespace) -> list[str]:
    """Load the documents the chosen subcommand needs and produce its output lines."""
    doc = _load(a.doc)
    if a.command == "releases":
        return releases_report(doc, a.doc, a.start, a.end)
    if a.command == "months":
        return months_report(doc, a.doc, a.start, a.end, a.compare)
    if a.command == "period":
        return period_report(doc, a.doc, a.period, a.where)
    if a.command == "hips":
        funnel = _load(a.funnel) if a.funnel else None
        if a.board and funnel is None:
            raise DeriveError("--board explains the gap to the funnel, so it needs --funnel")
        if (a.start is None) != (a.end is None):
            raise DeriveError("--from and --to go together")
        if a.start is not None and a.start > a.end:
            raise DeriveError(f"--from {a.start} is after --to {a.end}")
        board = _load(a.board) if a.board else None
        return hips_report(
            doc, a.doc, funnel, a.funnel or "funnel", a.cohort, board, a.board or "board", a.start, a.end
        )
    return single_employer_report(doc, a.doc)


def main(argv: list[str]) -> int:
    """Parse arguments, run the subcommand, print its table and Derived line."""
    a = _build_parser().parse_args(argv)
    try:
        lines = _run(a)
    except DeriveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
