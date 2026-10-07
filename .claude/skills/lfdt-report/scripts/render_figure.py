#!/usr/bin/env python3
"""Render a data-API chart document as a static SVG figure for the TAC report.

Standard library only, so it runs anywhere the draft is written. Handles the
two document kinds a report figure needs:

- ``timeseries`` (bar, stacked or not; line): one group per bucket, partial
  buckets outlined with a dashed border, starred, and given no total label.
- ``categories`` (horizontal bars): one bar per row, ``top_n`` rows kept,
  the rest folded into "Other (n)".

Usage:
    render_figure.py DOC.json OUT.svg [--title TEXT] [--subtitle TEXT]
                     [--series key,key] [--top N] [--width PX] [--every N]

Long monthly series thin their x-axis labels automatically (year boundaries
are kept); ``--every`` overrides the step.

The caption and Source line belong in the report, not the image; keep
``--subtitle`` to the population and window the document states.
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape

PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#64748b"]
FONT = "font-family='Helvetica, Arial, sans-serif'"
W_DEFAULT = 960
PAD_L, PAD_R, PAD_T, PAD_B = 70, 24, 64, 56


def _nice_ceiling(v: float) -> float:
    if v <= 0:
        return 1
    mag = 10 ** (len(str(int(v))) - 1)
    for step in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if mag * step >= v:
            return mag * step
    return mag * 10


def _axis(y0: float, y1: float, x0: float, x1: float, vmax: float, n: int = 5) -> list[str]:
    out = []
    for i in range(n + 1):
        v = vmax * i / n
        y = y1 - (y1 - y0) * i / n
        out.append(f"<line x1='{x0}' y1='{y:.1f}' x2='{x1}' y2='{y:.1f}' stroke='#e5e7eb'/>")
        out.append(
            f"<text x='{x0 - 8}' y='{y + 4:.1f}' text-anchor='end' font-size='12' fill='#374151' {FONT}>{int(v) if v == int(v) else v:g}</text>"
        )
    return out


def _header(parts: list[str], w: int, title: str, subtitle: str) -> None:
    parts.append(f"<rect width='{w}' height='100%' fill='white'/>")
    parts.append(
        f"<text x='{PAD_L}' y='26' font-size='17' font-weight='bold' fill='#111827' {FONT}>{escape(title)}</text>"
    )
    if subtitle:
        parts.append(f"<text x='{PAD_L}' y='46' font-size='12' fill='#4b5563' {FONT}>{escape(subtitle)}</text>")


def _legend(parts: list[str], series: list[dict], colors: dict, x: float, y: float) -> None:
    for s in series:
        parts.append(f"<rect x='{x}' y='{y - 10}' width='12' height='12' fill='{colors[s['key']]}'/>")
        parts.append(f"<text x='{x + 16}' y='{y}' font-size='12' fill='#374151' {FONT}>{escape(s['label'])}</text>")
        x += 16 + 7 * len(s["label"]) + 18


def render_timeseries(
    doc: dict, title: str, subtitle: str, keys: list[str] | None, w: int, every: int | None = None
) -> str:
    """Bars (stacked or grouped) or a line per series, one slot per bucket."""
    series = [s for s in doc["series"] if not keys or s["key"] in keys]
    rows = doc["rows"]
    colors = {s["key"]: PALETTE[i % len(PALETTE)] for i, s in enumerate(series)}
    stacked = bool(doc.get("stacked")) and doc.get("mark") != "line"
    h = 420
    x0, x1, y0, y1 = PAD_L, w - PAD_R, PAD_T + 16, h - PAD_B
    if stacked:
        vmax = max(sum(float(r.get(s["key"]) or 0) for s in series) for r in rows)
    else:
        vmax = max(float(r.get(s["key"]) or 0) for r in rows for s in series)
    vmax = _nice_ceiling(vmax)
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"]
    _header(parts, w, title, subtitle)
    parts += _axis(y0, y1, x0, x1, vmax)
    n = len(rows)
    slot = (x1 - x0) / max(n, 1)
    scale = (y1 - y0) / vmax

    if doc.get("mark") == "line":
        for s in series:
            pts = []
            for i, r in enumerate(rows):
                v = float(r.get(s["key"]) or 0)
                pts.append(f"{x0 + slot * (i + 0.5):.1f},{y1 - v * scale:.1f}")
            parts.append(
                f"<polyline points='{' '.join(pts)}' fill='none' stroke='{colors[s['key']]}' stroke-width='2.5'/>"
            )
            for i, r in enumerate(rows):
                v = float(r.get(s["key"]) or 0)
                cx, cy = x0 + slot * (i + 0.5), y1 - v * scale
                fill = "white" if r.get("partial") else colors[s["key"]]
                parts.append(
                    f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='4' fill='{fill}' stroke='{colors[s['key']]}' stroke-width='2'/>"
                )
    else:
        bw = slot * (0.7 if stacked else 0.8 / max(len(series), 1))
        for i, r in enumerate(rows):
            base = y1
            partial = bool(r.get("partial"))
            for j, s in enumerate(series):
                v = float(r.get(s["key"]) or 0)
                hgt = v * scale
                if stacked:
                    x = x0 + slot * i + (slot - bw) / 2
                    y = base - hgt
                    base = y
                else:
                    x = x0 + slot * i + slot * 0.1 + bw * j
                    y = y1 - hgt
                style = (
                    f"fill='white' stroke='{colors[s['key']]}' stroke-width='1.5' stroke-dasharray='4 2'"
                    if partial
                    else f"fill='{colors[s['key']]}'"
                )
                parts.append(f"<rect x='{x:.1f}' y='{y:.1f}' width='{bw:.1f}' height='{hgt:.1f}' {style}/>")
            if stacked and not partial:
                total = sum(float(r.get(s["key"]) or 0) for s in series)
                parts.append(
                    f"<text x='{x0 + slot * (i + 0.5):.1f}' y='{base - 5:.1f}' text-anchor='middle' font-size='11' fill='#111827' {FONT}>{total:g}</text>"
                )
    # Label every bucket when they fit. Longer series label only the year
    # starts (as the year) plus the last bucket; --every N labels every Nth.
    thin = every is not None or n > 24
    for i, r in enumerate(rows):
        label = str(r.get("bucket", ""))
        is_year_start = len(label) == 7 and label.endswith("-01")
        last = i == n - 1
        if thin and not last:
            keep = (i % every == 0) if every else is_year_start
            if not keep:
                continue
            if is_year_start and not every:
                label = label[:4]
        if r.get("partial"):
            label += "*"
        parts.append(
            f"<text x='{x0 + slot * (i + 0.5):.1f}' y='{y1 + 18}' text-anchor='middle' font-size='11' fill='#374151' {FONT}>{escape(label)}</text>"
        )
    if any(r.get("partial") for r in rows):
        parts.append(
            f"<text x='{x0}' y='{h - 14}' font-size='11' fill='#6b7280' {FONT}>* period not complete at the data-as-of date: outlined, not final, not comparable</text>"
        )
    _legend(parts, series, colors, x0, PAD_T + 2)
    parts.append("</svg>")
    return "\n".join(parts)


def render_categories(doc: dict, title: str, subtitle: str, keys: list[str] | None, top: int | None, w: int) -> str:
    """Horizontal bars, largest first, the tail folded into one "Other" row."""
    series = [s for s in doc["series"] if not keys or s["key"] in keys]
    cat = doc["category"]["key"]
    rows = list(doc["rows"])
    key0 = series[0]["key"]
    rows.sort(key=lambda r: (-float(r.get(key0) or 0), str(r.get(cat, ""))))
    top = top or doc.get("top_n") or len(rows)
    if len(rows) > top:
        rest = rows[top:]
        folded = {cat: f"Other ({len(rest)} more)"}
        for s in series:
            folded[s["key"]] = sum(float(r.get(s["key"]) or 0) for r in rest)
        rows = rows[:top] + [folded]
    colors = {s["key"]: PALETTE[i % len(PALETTE)] for i, s in enumerate(series)}
    row_h = 26 if len(series) == 1 else 18 * len(series) + 10
    h = PAD_T + 16 + row_h * len(rows) + PAD_B
    label_w = min(260, 8 * max(len(str(r[cat])) for r in rows) + 16)
    x0, x1 = PAD_L - 40 + label_w, w - PAD_R - 48
    vmax = _nice_ceiling(max(float(r.get(s["key"]) or 0) for r in rows for s in series))
    scale = (x1 - x0) / vmax
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"]
    _header(parts, w, title, subtitle)
    y = PAD_T + 16
    for r in rows:
        parts.append(
            f"<text x='{x0 - 8}' y='{y + row_h / 2 + 4:.1f}' text-anchor='end' font-size='12' fill='#111827' {FONT}>{escape(str(r[cat]))}</text>"
        )
        bh = (row_h - 8) / len(series)
        for j, s in enumerate(series):
            v = float(r.get(s["key"]) or 0)
            by = y + 4 + bh * j
            parts.append(
                f"<rect x='{x0}' y='{by:.1f}' width='{v * scale:.1f}' height='{bh - 2:.1f}' fill='{colors[s['key']]}'/>"
            )
            parts.append(
                f"<text x='{x0 + v * scale + 6:.1f}' y='{by + bh / 2 + 3:.1f}' font-size='11' fill='#374151' {FONT}>{v:g}</text>"
            )
        y += row_h
    if len(series) > 1:
        _legend(parts, series, colors, x0, PAD_T + 2)
    parts.append("</svg>")
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    """Parse arguments, pick the renderer by document kind, write the SVG."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc")
    ap.add_argument("out")
    ap.add_argument("--title")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--series", help="comma-separated series keys to keep")
    ap.add_argument("--top", type=int)
    ap.add_argument("--width", type=int, default=W_DEFAULT)
    ap.add_argument("--every", type=int, help="label every Nth bucket (default: auto, all when they fit)")
    a = ap.parse_args(argv)
    with open(a.doc) as fh:
        doc = json.load(fh)
    keys = a.series.split(",") if a.series else None
    title = a.title or doc.get("unit") or doc.get("metric") or doc.get("id", "")
    kind = doc.get("kind")
    if kind == "timeseries":
        svg = render_timeseries(doc, title, a.subtitle, keys, a.width, a.every)
    elif kind == "categories":
        svg = render_categories(doc, title, a.subtitle, keys, a.top, a.width)
    else:
        print(f"unsupported kind {kind!r}: this script draws timeseries and categories documents only", file=sys.stderr)
        return 2
    with open(a.out, "w") as fh:
        fh.write(svg)
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
