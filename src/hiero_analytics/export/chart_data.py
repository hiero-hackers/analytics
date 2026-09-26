"""Validated numeric datasets for interactive charts.

One document shape serves every migrated chart. A dashboard spec declares a
chart's source under ``interactive_sources`` (keyed by the PNG it replaces):
which CSV, which column is the category, which columns are series, and how to
draw them. This module reads the CSV, checks it, and emits the JSON document
the web app renders — it never aggregates, so the numbers are the analysis's.

Five kinds:

``timeseries``
    Rows are calendar buckets (year / month / ISO week / day), or ``snapshot``
    dates for point-in-time measurements. Calendar series are completed to the
    source's generation time: flows fill with zero, stocks carry forward.
``categories``
    Rows are repositories, organisations, stages… optionally split by a
    ``group`` column (e.g. a funnel cohort) that the reader selects.
``matrix``
    A heatmap: one row per entity, one value per column (months, checks),
    drawn as a table of coloured cells on an explicit, fixed scale.
``network``
    Repositories linked by shared members, with the node positions the PNG's
    layout computed, from a nodes CSV plus an edges CSV.
``events``
    Individual timestamped events (releases) in a trailing window, one row each.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from hiero_analytics.analysis.maintainer_pipeline import last_calendar_buckets
from hiero_analytics.config.charts import REPO_CATEGORY_COLORS
from hiero_analytics.domain.repo_categories import CATEGORY_ORDER

FORMATS = {"year": "%Y", "month": "%Y-%m", "week": "%G-W%V-%u", "day": "%Y-%m-%d", "snapshot": "%Y-%m-%d"}
MARKS = {"bar", "line", "area"}
DETAIL_FORMATS = {"number", "decimal", "percent"}

# Colours for series with no declared colour, cycling. Mirrors the web
# `--chart-1`..`--chart-5` tokens, which carry their own dark-mode values.
FALLBACK_COLORS = [f"var(--chart-{index})" for index in range(1, 6)]


def bucket_start(value: str, frequency: str) -> datetime:
    """Parse a canonical UTC calendar bucket, including ISO week years."""
    text = f"{value}-1" if frequency == "week" else value
    parsed = datetime.strptime(text, FORMATS[frequency]).replace(tzinfo=UTC)
    if parsed.strftime(FORMATS[frequency]) != text:
        raise ValueError(f"Invalid {frequency} bucket: {value}")
    return parsed


def _parse_time(value: str | None) -> datetime | None:
    """An ISO timestamp as aware UTC, or None when absent or unparseable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _numbers(frame: pd.DataFrame, column: str, values: str, name: str) -> pd.Series:
    """One column as finite numbers; ``count`` also demands safe nonnegative integers."""
    series = pd.to_numeric(frame[column], errors="raise")
    if series.isna().any() or not series.map(math.isfinite).all():
        raise ValueError(f"{name}: {column} must contain finite numbers")
    if values == "count":
        if ((series < 0) | (series > 2**53 - 1) | (series % 1 != 0)).any():
            raise ValueError(f"{name}: {column} must contain safe nonnegative integer counts")
        return series.astype("int64")
    return series.astype("float64")


def _integral(values: pd.Series) -> pd.Series:
    """Whole-number values as integers (4957, not 4957.0); anything else unchanged."""
    return values.astype("int64") if (values % 1 == 0).all() else values


def _series(source: dict, frame: pd.DataFrame, category: str, group: str | None) -> list[dict]:
    """The declared series, or every remaining CSV column for ``series: "columns"``."""
    declared = source["series"]
    if declared == "columns":
        excluded = {category, group, *(detail["key"] for detail in source.get("details", []))}
        declared = [{"key": column, "label": column} for column in frame.columns if column not in excluded]
    palette = source.get("palette") or {}
    if palette == "organisation":
        # Deferred: the affiliation pipeline pulls in plotting, which the rest of the export never needs.
        from hiero_analytics.pipelines.affiliation import segment_colors

        palette = segment_colors([entry["key"] for entry in declared])
    series = []
    for index, entry in enumerate(declared):
        color = entry.get("color") or palette.get(entry["key"]) or FALLBACK_COLORS[index % len(FALLBACK_COLORS)]
        series.append({"key": entry["key"], "label": entry["label"], "color": color})
    if not series:
        raise ValueError("a chart needs at least one series")
    return series


def _read(source: dict, csv_path: Path, org: str) -> tuple[pd.DataFrame, list[dict], list[dict]]:
    """Read and validate the CSV columns a source declares."""
    category = source["category"]
    group = source.get("group", {}).get("key")
    frame = pd.read_csv(csv_path, dtype={category: str, **({group: str} if group else {})})
    series = _series(source, frame, category, group)
    details = [{"format": "number", **detail} for detail in source.get("details", [])]
    required = [category, *([group] if group else []), *(s["key"] for s in series), *(d["key"] for d in details)]
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{csv_path.name}: missing columns {sorted(missing)}")
    frame = frame[required].copy()
    keys = [group, category] if group else [category]
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"{csv_path.name}: missing or duplicate {category} values")
    if source.get("strip_org_prefix"):
        frame[category] = frame[category].str.removeprefix(f"{org}/")
    for entry in series:
        frame[entry["key"]] = _numbers(frame, entry["key"], source.get("values", "count"), csv_path.name)
    for detail in details:
        if detail["format"] not in DETAIL_FORMATS:
            raise ValueError(f"{csv_path.name}: unknown detail format {detail['format']}")
        frame[detail["key"]] = _integral(_numbers(frame, detail["key"], "number", csv_path.name))
    return frame, series, details


def _calendar(frame: pd.DataFrame, source: dict, series: list[dict], generated_at: str | None) -> pd.DataFrame:
    """Complete a calendar series up to its generation bucket and window it.

    A missing sidecar is not evidence that a historic dataset is current, so
    the series is anchored to its latest bucket, or its generation time if
    that is later — never to today.
    """
    category, frequency = source["category"], source["frequency"]
    anchor = bucket_start(frame.iloc[-1][category], frequency)
    if (generated := _parse_time(generated_at)) is not None:
        anchor = max(anchor, generated)
    if buckets := source.get("buckets"):
        labels = last_calendar_buckets(anchor, buckets, frequency)
    else:
        first = bucket_start(frame.iloc[0][category], frequency)
        labels = list(dict.fromkeys(_bucket_labels(first, anchor, frequency)))
    filled = frame.set_index(category).reindex(labels)
    declared = source["series"] if isinstance(source["series"], list) else []
    carried = {entry["key"] for entry in declared if entry.get("fill") == "carry"}
    for entry in series:
        if entry["key"] in carried:
            # A stock (a running total) holds its level through empty buckets.
            earlier = frame[frame[category] < labels[0]][entry["key"]]
            start = earlier.iloc[-1] if len(earlier) else 0
            filled[entry["key"]] = filled[entry["key"]].ffill().fillna(start)
        else:
            filled[entry["key"]] = filled[entry["key"]].fillna(0)
        filled[entry["key"]] = filled[entry["key"]].astype(frame[entry["key"]].dtype)
    return filled.reset_index(names=category).fillna(0)


def _bucket_labels(first: datetime, last: datetime, frequency: str) -> list[str]:
    """Every calendar bucket label from ``first`` through ``last``'s bucket."""
    if frequency == "year":
        return [str(year) for year in range(first.year, last.year + 1)]
    pandas_freq = {"month": "MS", "week": "W-MON", "day": "D"}[frequency]
    stamps = pd.date_range(first, last, freq=pandas_freq, tz=UTC)
    fmt = FORMATS[frequency].removesuffix("-%u")
    return [stamp.strftime(fmt) for stamp in stamps] or [first.strftime(fmt)]


def _timeseries(source: dict, csv_path: Path, org: str, generated_at: str | None) -> dict:
    """Rows in time order, with calendar gaps completed and partial buckets flagged."""
    frame, series, details = _read(source, csv_path, org)
    category, frequency = source["category"], source["frequency"]
    if source.get("normalize_dates"):
        # CSVs that store a bucket as its start date ("2024-01-01").
        frame[category] = pd.to_datetime(frame[category], utc=True).dt.strftime(FORMATS[frequency].removesuffix("-%u"))
    for value in frame[category]:
        bucket_start(value, frequency)
    frame = frame.sort_values(category)
    calendar = frequency != "snapshot" and not frame.empty
    if calendar:
        frame = _calendar(frame, source, series, generated_at)
    rows = []
    last = frame.iloc[-1][category] if len(frame) else None
    for record in frame.to_dict(orient="records"):
        bucket = record.pop(category)
        rows.append({"bucket": bucket, **record, "partial": calendar and bucket == last})
    return {
        "frequency": frequency,
        "timezone": "UTC",
        "comparison": _comparison(rows, frequency) if source.get("compare", True) else None,
        "category": {"key": "bucket", "label": source.get("category_label", "Period (UTC)")},
        "window": {
            "kind": "calendar",
            "first": rows[0]["bucket"] if rows else None,
            "last": rows[-1]["bucket"] if rows else None,
        },
        "series": series,
        "details": details,
        "rows": rows,
    }


def _categories(source: dict, csv_path: Path, org: str, generated_at: str | None) -> dict:
    """Category rows in the source's order (the analysis's ranking or sequence)."""
    frame, series, details = _read(source, csv_path, org)
    category = source["category"]
    group = source.get("group")
    if group:
        values = list(dict.fromkeys(frame[group["key"]]))
        if group["default"] not in values:
            raise ValueError(f"{csv_path.name}: default {group['key']} {group['default']!r} is absent")
        group = {**group, "values": values}
    return {
        "category": {"key": category, "label": source["category_label"]},
        "window": _window(source, generated_at),
        "group": group,
        "series": series,
        "details": details,
        "rows": frame.to_dict(orient="records"),
    }


def _window(source: dict, generated_at: str | None) -> dict:
    """``snapshot``: the state at ``end``; ``all``: every recorded event; an integer: trailing days to ``end``."""
    window = source.get("window", "all")
    return {
        "kind": "trailing" if isinstance(window, int) else window,
        "days": window if isinstance(window, int) else None,
        "end": generated_at,
    }


MONTH_COLUMN = re.compile(r"^\d{4}-\d{2}$")


def _matrix(source: dict, csv_path: Path, org: str, generated_at: str | None) -> dict:
    """A wide table as heatmap rows, in the source's order (the analysis's ranking).

    ``columns: "months"`` takes every ``YYYY-MM`` column, oldest first. A
    ``missing`` sentinel (Scorecard's -1 "inconclusive") becomes null rather
    than a value, so it can never be coloured as a score.
    """
    row_key = source["row"]
    frame = pd.read_csv(csv_path, dtype={row_key: str})
    if source["columns"] == "months":
        columns = [{"key": c, "label": c} for c in sorted(c for c in frame.columns if MONTH_COLUMN.match(c))]
    else:
        columns = source["columns"]
    extras = [source[key] for key in ("sublabel", "total") if source.get(key)]
    required = [row_key, *(extra["key"] for extra in extras), *(column["key"] for column in columns)]
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{csv_path.name}: missing columns {sorted(missing)}")
    if not columns:
        raise ValueError(f"{csv_path.name}: no matrix columns")
    frame = frame[required].copy()
    if frame[row_key].isna().any() or frame[row_key].duplicated().any():
        raise ValueError(f"{csv_path.name}: missing or duplicate {row_key} values")
    if source.get("strip_org_prefix"):
        frame[row_key] = frame[row_key].str.removeprefix(f"{org}/")
    values = source.get("values", "count")
    sentinel = source.get("missing", {}).get("value")
    for column in columns:
        cells = frame[column["key"]]
        # A blank cell is "not reported"; the sentinel is the source's own "could not score".
        absent = cells.isna() | (cells == sentinel if sentinel is not None else False)
        checked = _numbers(frame[~absent], column["key"], values, csv_path.name)
        frame[column["key"]] = checked.reindex(frame.index).astype(object).where(~absent, None)
    if total := source.get("total"):
        frame[total["key"]] = _integral(_numbers(frame, total["key"], "number", csv_path.name))
    if sublabel := source.get("sublabel"):
        frame[sublabel["key"]] = frame[sublabel["key"]].fillna("").astype(str)
    observed = [v for column in columns for v in frame[column["key"]] if v is not None]
    # Linear from zero like the PNG's colour bar; a declared maximum (Scorecard's
    # 10) keeps the scale meaningful when no repository reaches it.
    maximum = source.get("scale_max") or max([*observed, 1])
    return {
        "row": {"key": row_key, "label": source["row_label"]},
        "sublabel": source.get("sublabel"),
        "total": source.get("total"),
        "columns": columns,
        "value_label": source["value_label"],
        "scale": {"min": 0, "max": maximum, "steps": 5},
        "missing": source.get("missing", {}).get("label"),
        "avatars": bool(source.get("avatars", False)),
        "top_n": source.get("top_n"),
        "value_format": "integer" if values == "count" else "decimal",
        "window": _window(source, generated_at),
        "rows": frame.to_dict(orient="records"),
    }


def _network(source: dict, csv_path: Path, _org: str, generated_at: str | None) -> dict:
    """Nodes (with the PNG's layout) and the links between them, from two CSVs."""
    nodes = pd.read_csv(csv_path, dtype={"repo": str, "category": str})
    edges_path = csv_path.with_name(source["edges_file"])
    edges = pd.read_csv(edges_path, dtype={"repo_a": str, "repo_b": str})
    for frame, required, name in [
        (nodes, ["repo", "active_members", "total_members", "category", "x", "y"], csv_path.name),
        (edges, ["repo_a", "repo_b", "shared"], edges_path.name),
    ]:
        missing = set(required) - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: missing columns {sorted(missing)}")
    if nodes["repo"].isna().any() or nodes["repo"].duplicated().any():
        raise ValueError(f"{csv_path.name}: missing or duplicate repositories")
    for column in ["active_members", "total_members"]:
        nodes[column] = _numbers(nodes, column, "count", csv_path.name)
    for column in ["x", "y"]:
        nodes[column] = _numbers(nodes, column, "number", csv_path.name)
    edges["shared"] = _numbers(edges, "shared", "count", edges_path.name)
    known = set(nodes["repo"])
    if not (edges["repo_a"].isin(known) & edges["repo_b"].isin(known)).all():
        raise ValueError(f"{edges_path.name}: links a repository that is not a node")
    if (edges["repo_a"] == edges["repo_b"]).any() or edges[["repo_a", "repo_b"]].apply(
        frozenset, axis=1
    ).duplicated().any():
        raise ValueError(f"{edges_path.name}: self or duplicate links")
    present = set(nodes["category"])
    categories = [
        {"key": name, "label": name, "color": REPO_CATEGORY_COLORS[name]}
        for name in [*CATEGORY_ORDER, *sorted(present - set(CATEGORY_ORDER))]
        if name in present and name in REPO_CATEGORY_COLORS
    ]
    if unknown := present - {c["key"] for c in categories}:
        raise ValueError(f"{csv_path.name}: unknown repository categories {sorted(unknown)}")
    member = source["member_label"]
    return {
        "member_label": member,
        "categories": categories,
        "window": _window(source, generated_at),
        "nodes": [
            {
                "id": row.repo,
                "active": int(row.active_members),
                "total": int(row.total_members),
                "category": row.category,
                "x": float(row.x),
                "y": float(row.y),
            }
            for row in nodes.itertuples()
        ],
        "edges": [
            {"source": row.repo_a, "target": row.repo_b, "shared": int(row.shared)} for row in edges.itertuples()
        ],
    }


def _events(source: dict, csv_path: Path, org: str, generated_at: str | None) -> dict:
    """Timestamped events inside the source's trailing window, one row each.

    The window ends at the source's generation time (the pipeline's "now"),
    or at the latest event when no sidecar says when that was.
    """
    category, time, label, flag = source["category"], source["time"], source["label"], source["flag"]
    frame = pd.read_csv(csv_path, dtype={category: str, label: str})
    missing = {category, time, label, flag["key"]} - set(frame.columns)
    if missing:
        raise ValueError(f"{csv_path.name}: missing columns {sorted(missing)}")
    stamps = pd.to_datetime(frame[time], utc=True, errors="coerce")
    if stamps.isna().any() or frame[category].isna().any():
        raise ValueError(f"{csv_path.name}: every event needs a {category} and a valid {time}")
    flags = frame[flag["key"]].map(
        {True: True, False: False, "True": True, "False": False, "true": True, "false": False}
    )
    if flags.isna().any():
        raise ValueError(f"{csv_path.name}: {flag['key']} must be true or false")
    if source.get("strip_org_prefix"):
        frame[category] = frame[category].str.removeprefix(f"{org}/")
    end = _parse_time(generated_at) or (stamps.max().to_pydatetime() if len(stamps) else None)
    days = source["window"]
    keep = (
        (stamps > pd.Timestamp(end) - pd.Timedelta(days=days)) & (stamps <= pd.Timestamp(end))
        if end
        else stamps.notna()
    )
    events = pd.DataFrame(
        {
            category: frame[category],
            "time": stamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            label: frame[label].fillna(""),
            "type": flags.map({True: flag["true"]["key"], False: flag["false"]["key"]}),
        }
    )[keep].sort_values(["time", category])
    counts = events[category].value_counts()
    return {
        "category": {"key": category, "label": source["category_label"]},
        "label": {"key": label, "label": source["label_label"]},
        "types": [flag["false"], flag["true"]],
        # Busiest first, ties alphabetical: the order the timeline's rows take.
        "categories": sorted(counts.index, key=lambda name: (-counts[name], name)),
        "window": {"kind": "trailing", "days": days, "end": end.isoformat() if end else None},
        "rows": events.to_dict(orient="records"),
    }


# Dimension names as the dashboard's focus knows them: one name per concept,
# whatever the source CSV calls its column.
CANONICAL_DIMENSIONS = {
    "contributor name": "contributor",
    "login": "contributor",
    "user": "contributor",
    "repository": "repo",
}


def _dimension(key: str) -> str:
    return CANONICAL_DIMENSIONS.get(key, key)


def _comparison(rows: list[dict], frequency: str) -> dict | None:
    """The last complete bucket against the one before it, when both exist.

    Calendar buckets of one size are comparable windows; the partial current
    bucket never is, and a snapshot series has no buckets to compare. The
    counts themselves stay in ``rows`` — this only names the pair.
    """
    if frequency == "snapshot":
        return None
    complete = [row["bucket"] for row in rows if not row["partial"]]
    if len(complete) < 2:
        return None
    return {"current": complete[-1], "previous": complete[-2]}


SERIES_KINDS = {"timeseries": _timeseries, "categories": _categories}
OTHER_KINDS = {"matrix": _matrix, "network": _network, "events": _events}


def chart_document(source: dict, csv_path: Path, org: str, generated_at: str | None = None) -> dict:
    """Build the interactive document a dashboard spec source declares."""
    kind = source.get("kind")
    if kind not in SERIES_KINDS and kind not in OTHER_KINDS:
        raise ValueError(f"Unknown interactive chart kind: {kind}")
    document = {
        "schema_version": 1,
        "id": csv_path.stem,
        "kind": kind,
        "org": org,
        "source": csv_path.name,
        "metric": source["metric"],
        "unit": source["unit"],
        "population": source["population"],
    }
    if kind in OTHER_KINDS:
        body = OTHER_KINDS[kind](source, csv_path, org, generated_at)
        # What the rows can be sliced by; the UI must not offer anything else.
        document["dimensions"] = {
            "matrix": [_dimension(body.get("row", {}).get("key")), "column"],
            "network": ["repo", "link"],
            "events": [_dimension(body.get("category", {}).get("key")), "type"],
        }[kind]
        document.update(body)
        if note := source.get("note"):
            document["note"] = note
        return document
    mark = source.get("mark", "bar")
    if mark not in MARKS:
        raise ValueError(f"Unknown chart mark: {mark}")
    body = SERIES_KINDS[kind](source, csv_path, org, generated_at)
    document = {
        **document,
        # What the rows can be sliced by; the UI must not offer anything else.
        "dimensions": [
            "period" if kind == "timeseries" else _dimension(body["category"]["key"]),
            *([body["group"]["key"]] if body.get("group") else []),
            *(["series"] if len(body["series"]) > 1 else []),
        ],
        "mark": mark,
        "stacked": bool(source.get("stacked", False)),
        "normalize": bool(source.get("normalize", False)),
        "orientation": source.get("orientation", "vertical"),
        "value_format": "integer" if source.get("values", "count") == "count" else "decimal",
        # Re-rank by the series on show; otherwise keep the source's order.
        "rank": bool(source.get("rank", False)),
        "top_n": source.get("top_n"),
        "reference": source.get("reference"),
        "group": None,
        **body,
    }
    if note := source.get("note"):
        document["note"] = note
    return document
