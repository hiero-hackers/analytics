"""Tests for the versioned JSON data API emitter."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from hiero_analytics.export import data_api
from hiero_analytics.export.data_api import API_VERSION, DataApiContractError, emit_data_api

ORG = "test-org"


def _family(section: dict) -> SimpleNamespace:
    """A minimal dashboard-spec family module carrying one table section."""
    return SimpleNamespace(
        SECTION_SPECS=[section],
        SECTION_ORDER=[section["id"]],
        SECTION_GROUP_OF={section["id"]: "A group"},
        CHART_MACRO={"name": "Testing", "charts": {}},
    )


@pytest.fixture
def api_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the output tree and spec surface to a temp sandbox."""
    org_data = tmp_path / "data" / "org" / ORG
    org_data.mkdir(parents=True)
    monkeypatch.setattr(data_api.paths, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(data_api.paths, "ORG_DATA_DIR", tmp_path / "data" / "org")
    monkeypatch.setattr(data_api.paths, "ORG_CHARTS_DIR", tmp_path / "charts" / "org")
    monkeypatch.setattr(data_api.paths, "ORG", ORG)
    section = {
        "id": "widgets",
        "file": "widgets.csv",
        "title": "Widgets",
        "description": "All widgets.",
        "columns": [("name", "widget"), ("count", "count"), ("last_seen", "last seen", "date")],
    }
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(section)})
    monkeypatch.setattr(data_api, "CHART_MACROS", [{"name": "Testing", "charts": {}}])
    monkeypatch.setattr(data_api, "CUSTOM_VIEW_MODULES", {})
    monkeypatch.setattr(data_api, "MACRO_GLOSSARIES", {})
    return org_data


def _write_widgets(org_data: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(org_data / "widgets.csv", index=False)
    Path(f"{org_data / 'widgets.csv'}.meta.json").write_text(
        json.dumps({"generated_at": "2026-07-25T10:00:00+00:00", "record_count": len(frame)})
    )


def test_emits_section_document_and_manifest(api_env: Path, tmp_path: Path):
    """A produced table becomes a section JSON, listed in the manifest."""
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [3], "last_seen": ["2026-07-01"]}))

    manifest_path = emit_data_api()

    manifest = json.loads(manifest_path.read_text())
    assert manifest["version"] == API_VERSION
    assert manifest["orgs"][ORG]["sections"] == [
        {"id": "widgets", "macro": "Testing", "title": "Widgets", "row_count": 1, "path": f"{ORG}/widgets.json"}
    ]
    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert document["rows"] == [{"name": "a", "count": 3, "last_seen": "2026-07-01"}]
    assert document["generated_at"] == "2026-07-25T10:00:00+00:00"
    assert document["group"] == "A group"
    # Column objects mirror the spec tuples, including the optional format.
    assert document["columns"][0] == {"key": "name", "label": "widget"}
    assert document["columns"][2] == {"key": "last_seen", "label": "last seen", "format": "date"}


def test_section_action_link_is_shipped(api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A spec section's call to action (e.g. "Suggest a correction") travels with the document."""
    section = {
        "id": "widgets",
        "file": "widgets.csv",
        "title": "Widgets",
        "description": "All widgets.",
        "action_url": "https://example.test/issues/new",
        "action_label": "Suggest a correction",
        "columns": [("name", "widget")],
    }
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(section)})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"]}))

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert document["action"] == {"url": "https://example.test/issues/new", "label": "Suggest a correction"}


def test_data_within_stale_after_is_not_stale(api_env: Path, tmp_path: Path):
    """A section stamped just inside STALE_AFTER is not flagged stale."""
    generated_at = datetime.now(UTC) - data_api.STALE_AFTER + timedelta(minutes=5)
    frame = pd.DataFrame({"name": ["a"], "count": [3], "last_seen": ["2026-07-01"]})
    frame.to_csv(api_env / "widgets.csv", index=False)
    Path(f"{api_env / 'widgets.csv'}.meta.json").write_text(
        json.dumps({"generated_at": generated_at.isoformat(), "record_count": len(frame)})
    )

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert document["stale"] is False


def test_data_past_stale_after_is_stale(api_env: Path, tmp_path: Path):
    """A section stamped past STALE_AFTER is flagged stale for the dashboard badge."""
    generated_at = datetime.now(UTC) - data_api.STALE_AFTER - timedelta(minutes=5)
    frame = pd.DataFrame({"name": ["a"], "count": [3], "last_seen": ["2026-07-01"]})
    frame.to_csv(api_env / "widgets.csv", index=False)
    Path(f"{api_env / 'widgets.csv'}.meta.json").write_text(
        json.dumps({"generated_at": generated_at.isoformat(), "record_count": len(frame)})
    )

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert document["stale"] is True


def test_missing_declared_column_fails_loudly(api_env: Path):
    """The column contract: a renamed CSV column is an error, not a blank."""
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "n": [3], "last_seen": ["2026-07-01"]}))

    with pytest.raises(DataApiContractError, match=r"widgets.csv is missing .*'count'"):
        emit_data_api()


def test_undeclared_columns_stay_out_of_the_payload(api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Rows carry the spec's columns only \u2014 a pipeline's extra column isn't API.

    Publishing whatever the CSV happens to hold would make every incidental
    column part of an additive-only contract. Base table and period variants
    both project down to the declared set.
    """
    section = {
        "id": "widgets",
        "file": "widgets.csv",
        "title": "Widgets",
        "description": "All widgets.",
        "columns": [("name", "widget"), ("count", "count")],
        "periods": True,
    }
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(section)})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [3], "scratch": ["internal"]}))
    period = data_api.ACTIVITY_PERIODS[0]
    pd.DataFrame({"name": ["a"], "count": [1], "scratch": ["internal"]}).to_csv(
        api_env / period.filename("widgets"), index=False
    )

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert document["rows"] == [{"name": "a", "count": 3}]
    assert document["periods"][period.key] == [{"name": "a", "count": 1}]
    assert document["row_count"] == 1


def test_declared_column_order_wins_over_csv_order(api_env: Path, tmp_path: Path):
    """Row keys follow the spec's order, not the order the pipeline wrote."""
    _write_widgets(api_env, pd.DataFrame({"last_seen": ["2026-07-01"], "count": [3], "name": ["a"]}))

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert list(document["rows"][0]) == ["name", "count", "last_seen"]


def test_unproduced_table_is_skipped_not_failed(api_env: Path):
    """A section whose pipeline didn't run is absent, and an empty org is omitted."""
    manifest = json.loads(emit_data_api().read_text())

    assert manifest["orgs"] == {}


def test_nan_serializes_as_null(api_env: Path, tmp_path: Path):
    """Rows are JSON-safe: pandas NaN becomes null, never the string 'nan'."""
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [None], "last_seen": [None]}))

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert document["rows"] == [{"name": "a", "count": None, "last_seen": None}]


def test_period_variants_ride_along(api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A periods-flagged section carries its per-period row sets."""
    section = {
        "id": "widgets",
        "file": "widgets.csv",
        "title": "Widgets",
        "description": "All widgets.",
        "columns": [("name", "widget")],
        "periods": True,
    }
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(section)})
    _write_widgets(api_env, pd.DataFrame({"name": ["a", "b"]}))
    period = data_api.ACTIVITY_PERIODS[0]
    pd.DataFrame({"name": ["a"]}).to_csv(api_env / period.filename("widgets"), index=False)

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert document["periods"][period.key] == [{"name": "a"}]


def test_chart_sections_carry_presentation_structure(api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Chart sections keep their card structure: variants, notes, wide, slideshow."""
    monkeypatch.setattr(
        data_api,
        "CHART_MACROS",
        [
            {
                "name": "Testing",
                "charts": {
                    ORG: [
                        {
                            "id": "w-chart",
                            "title": "Widget charts",
                            "description": "All widget charts.",
                            "slideshow": True,
                            "files": [
                                ("Widgets", [("All", "widgets.png"), ("Active", "widgets_active.png")]),
                            ],
                        }
                    ]
                },
            }
        ],
    )
    monkeypatch.setattr(data_api, "CHART_NOTES", {"widgets.png": "How to read widgets."})
    monkeypatch.setattr(data_api, "CHART_METHODOLOGY", {"widgets.png": ["Step one."]})
    monkeypatch.setattr(data_api, "WIDE_CHARTS", {"widgets.png"})
    chart_dir = tmp_path / "charts" / "org" / ORG
    chart_dir.mkdir(parents=True)
    (chart_dir / "widgets.png").write_bytes(b"\x89PNG")  # the Active variant is not produced
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    (section,) = manifest["orgs"][ORG]["chart_sections"]
    assert section["title"] == "Widget charts" and section["slideshow"] is True
    (chart,) = section["charts"]
    # Only the produced variant is listed; note, methodology and wide survive.
    assert chart["variants"] == [{"label": "All", "file": f"charts/org/{ORG}/widgets.png"}]
    assert chart["note"] == "How to read widgets."
    assert chart["methodology"] == ["Step one."]
    assert chart["wide"] is True


def test_manifest_ships_only_per_macro_glossaries(api_env: Path, monkeypatch: pytest.MonkeyPatch):
    """Each macro carries its own explainer; there is no shared fallback."""
    glossary = {
        "title": "How to read this",
        "layout": "definitions",
        "terms": [{"term": "PRs", "definition": "pull requests opened."}],
    }
    monkeypatch.setattr(data_api, "MACRO_GLOSSARIES", {"Testing": glossary})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    assert "glossary" not in manifest
    assert manifest["macro_glossaries"] == {"Testing": glossary}
    # Data, not markup: the frontend owns the glossary's HTML.
    assert "<" not in json.dumps(manifest["macro_glossaries"])
    # The fake Testing family has no metric builder, so tiles are absent.
    assert manifest["orgs"][ORG]["metrics"] == {}


def test_manifest_ships_macro_glossaries_and_period_labels(api_env: Path, monkeypatch: pytest.MonkeyPatch):
    """Per-macro explainers and period display labels ride in the manifest."""
    hip_glossary = {"title": "How to read this tab", "layout": "notes", "terms": [{"term": "x", "definition": "y"}]}
    monkeypatch.setattr(data_api, "MACRO_GLOSSARIES", {"Testing": hip_glossary})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    assert manifest["macro_glossaries"] == {"Testing": hip_glossary}
    assert manifest["period_labels"]["30d"] == "30 days"


def test_chart_companion_csv_is_copied_and_referenced(api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A chart's declared CSV travels inside the API tree with a download ref."""
    charts_dir = tmp_path / "charts" / "org" / ORG
    charts_dir.mkdir(parents=True)
    (charts_dir / "funnel.png").write_bytes(b"\x89PNG\r\n\x1a\nnot-a-real-png")
    monkeypatch.setattr(
        data_api,
        "CHART_MACROS",
        [
            {
                "name": "Testing",
                "charts": {
                    ORG: [
                        {
                            "id": "funnel",
                            "title": "Funnel",
                            "description": "Stages.",
                            "files": [("Funnel", [("Funnel", "funnel.png")])],
                            "csv": "funnel_data.csv",
                        }
                    ]
                },
            }
        ],
    )
    pd.DataFrame({"stage": ["a"], "share": [100]}).to_csv(api_env / "funnel_data.csv", index=False)
    Path(f"{api_env / 'funnel_data.csv'}.meta.json").write_text(
        json.dumps({"generated_at": "2026-07-25T10:00:00+00:00"})
    )
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    section = manifest["orgs"][ORG]["chart_sections"][0]
    assert section["download"] == {
        "name": "funnel_data.csv",
        "path": f"{ORG}/funnel_data.csv",
        "generated_at": "2026-07-25T10:00:00+00:00",
    }
    copied = tmp_path / "data" / "api" / API_VERSION / ORG / "funnel_data.csv"
    assert copied.read_text() == (api_env / "funnel_data.csv").read_text()


def test_views_are_emitted_as_documents_with_manifest_refs(
    api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A family's bespoke views ship as their own stamped documents.

    Uses the real HIP views module end to end, so the emitted matrix is the
    genuine article rather than a stand-in shape.
    """
    from hiero_analytics.export import hip_views

    components = [(f"{ORG}/consensus", "consensus", "Services"), (f"{ORG}/sdk-java", "java", "SDKs")]
    monkeypatch.setattr(hip_views.hips_spec, "MATRIX_COMPONENTS", {ORG: components})
    monkeypatch.setattr(data_api, "CUSTOM_VIEW_MODULES", {"Testing": "hiero_analytics.export.hip_views"})
    pd.DataFrame([{"hip": 100, "hip_title": "Spec", "hip_status": "Approved"}]).to_csv(
        api_env / "hip_summary.csv", index=False
    )
    pd.DataFrame([{"hip": 100, "repo": f"{ORG}/consensus", "merged_prs": 2, "open_prs": 0}]).to_csv(
        api_env / "hip_repo_activity.csv", index=False
    )
    Path(f"{api_env / 'hip_repo_activity.csv'}.meta.json").write_text(
        json.dumps({"generated_at": "2026-07-25T09:00:00+00:00"})
    )
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    refs = manifest["orgs"][ORG]["views"]
    assert [(ref["id"], ref["kind"], ref["macro"]) for ref in refs] == [
        ("hip-board", "board", "Testing"),
        ("hip-matrix", "matrix", "Testing"),
    ]
    matrix = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "hip-matrix.json").read_text())
    assert matrix["rows"][0]["cells"][0]["merged"] == 2
    assert matrix["generated_at"] == "2026-07-25T09:00:00+00:00"
    assert len(matrix["ramp"]) == 5
