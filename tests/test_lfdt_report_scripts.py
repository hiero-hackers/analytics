"""Tests for the lfdt-report skill's helper scripts (SVG figures and export)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "lfdt-report" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def render():
    """Load render_figure.py from the skill directory."""
    return _load("render_figure")


@pytest.fixture(scope="module")
def export():
    """Load export_report.py from the skill directory."""
    return _load("export_report")


def _timeseries(n_months: int) -> dict:
    rows = []
    year, month = 2019, 1
    for i in range(n_months):
        rows.append({"bucket": f"{year}-{month:02d}", "a": i, "b": 2 * i, "partial": i == n_months - 1})
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return {
        "kind": "timeseries",
        "mark": "bar",
        "stacked": True,
        "frequency": "month",
        "category": {"key": "bucket", "label": "Period"},
        "series": [{"key": "a", "label": "A", "color": "x"}, {"key": "b", "label": "B", "color": "y"}],
        "rows": rows,
    }


def test_timeseries_marks_partial_bucket_hollow_and_starred(render):
    """A partial bucket is drawn with a dashed outline and a starred label."""
    svg = render.render_timeseries(_timeseries(4), "t", "s", None, 800)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "stroke-dasharray" in svg
    assert ">2019-04*<" in svg
    assert svg.count("<rect") >= 8  # two series x four buckets, plus background


def test_timeseries_thins_long_axis_to_year_starts(render):
    """More than 24 buckets label only year starts (as years) and the last bucket."""
    svg = render.render_timeseries(_timeseries(40), "t", "", None, 800)
    assert ">2020<" in svg and ">2021<" in svg
    assert ">2019-02<" not in svg
    assert ">2022-04*<" in svg  # last (partial) bucket is always labelled


def test_timeseries_every_overrides_thinning(render):
    """--every N labels every Nth bucket instead of year starts."""
    svg = render.render_timeseries(_timeseries(40), "t", "", None, 800, every=10)
    assert ">2019-11<" in svg  # index 10
    assert ">2020<" not in svg


def test_categories_folds_tail_into_other(render):
    """Rows past top_n collapse into one Other row carrying the count folded."""
    doc = {
        "kind": "categories",
        "category": {"key": "org", "label": "Org"},
        "series": [{"key": "n", "label": "N", "color": "x"}],
        "top_n": 2,
        "rows": [{"org": f"o{i}", "n": 10 - i} for i in range(5)],
    }
    svg = render.render_categories(doc, "t", "", None, None, 800)
    assert ">o0<" in svg and ">o1<" in svg
    assert ">Other (3 more)<" in svg
    assert ">o4<" not in svg


def test_nice_ceiling_leaves_headroom_without_waste(render):
    """The axis ceiling is the next step above the maximum, not a power of ten."""
    assert render._nice_ceiling(621) == 800
    assert render._nice_ceiling(44) == 50
    assert render._nice_ceiling(0) == 1


def test_main_rejects_unsupported_kind(render, tmp_path: Path):
    """Kinds the renderer cannot draw exit with code 2 and no output file."""
    doc = tmp_path / "m.json"
    doc.write_text(json.dumps({"kind": "matrix", "rows": []}))
    assert render.main([str(doc), str(tmp_path / "out.svg")]) == 2


def test_export_prefers_png_and_drops_spdx(export, monkeypatch, tmp_path: Path):
    """The PDF path strips the SPDX comment, swaps SVG for PNG, and explains a missing browser."""
    draft = tmp_path / "r.md"
    draft.write_text("[//]: # (SPDX-License-Identifier: CC-BY-4.0)\n# T\n\n![a](figures/x.svg)\n\nSource: y\n")
    captured: dict[str, str] = {}

    def fake_md(text: str) -> str:
        captured["text"] = text
        return "<p>Source: y</p>"

    monkeypatch.setattr(export, "_markdown_to_html", fake_md)
    monkeypatch.setattr(export, "_first_tool", lambda _names: None)
    assert export.cmd_pdf(str(draft), None) == 3  # no chrome: explained, not crashed
    monkeypatch.setattr(export, "_first_tool", lambda _names: "/bin/echo")
    assert export.cmd_pdf(str(draft), str(tmp_path / "r.pdf")) == 0
    assert "SPDX" not in captured["text"]
    assert "figures/x.png" in captured["text"]
