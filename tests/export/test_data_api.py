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
    """Boundary check: STALE_AFTER minus a few minutes stays fresh."""
    assert timedelta(hours=132) == data_api.STALE_AFTER
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
    """Boundary check: the other side of the same line trips the badge."""
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


def test_all_time_is_never_a_period_variant(api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The all-time window never rides along: ``rows`` already is that table.

    Emitting it duplicated every row in the payload and gave the dashboard two
    identical "All time" tabs. The period vocabulary now excludes it by
    construction; this pins both the exclusion and that an ``_all.csv`` left on
    disk by an older pipeline is ignored rather than shipped.
    """
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
    # A stale all-time variant from before the vocabulary change.
    pd.DataFrame({"name": ["a", "b"]}).to_csv(api_env / "widgets_all.csv", index=False)

    emit_data_api()

    document = json.loads((tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.json").read_text())
    assert "all" not in document.get("periods", {})
    manifest = json.loads((tmp_path / "data" / "api" / API_VERSION / "manifest.json").read_text())
    assert "all" not in manifest["period_labels"]
    assert "All time" not in manifest["period_labels"].values()


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
    # Only the produced variant is listed. Its own note and methodology travel
    # with it — the tab a reader is looking at has to explain that tab — and the
    # chart-level copies stay as the fallback for a variant with no entry.
    assert chart["variants"] == [
        {
            "label": "All",
            "file": f"charts/org/{ORG}/widgets.png",
            "note": "How to read widgets.",
            "methodology": ["Step one."],
        }
    ]
    assert chart["note"] == "How to read widgets."
    assert chart["methodology"] == ["Step one."]
    assert chart["wide"] is True


ROLE_TABBED_SECTION = {
    "id": "widgets",
    "file": "widgets.csv",
    "title": "Widgets",
    "description": "All widgets.",
    "columns": [("name", "widget"), ("count", "count"), ("last_seen", "last seen", "date")],
    "variants": [
        {"id": "widgets", "label": "Maintainers"},
        {
            "id": "committerwidgets",
            "label": "Committers",
            "file": "committer_widgets.csv",
            "description": "The committer view.",
            # A genuinely different shape, not just a relabel: the count column
            # is named for the role it counts in each produced CSV.
            "columns": [("name", "widget"), ("committers", "committers"), ("last_seen", "last seen", "date")],
        },
    ],
}


def _write_committer_widgets(org_data: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(org_data / "committer_widgets.csv", index=False)


def test_role_variants_publish_one_tabbed_document(api_env: Path, monkeypatch: pytest.MonkeyPatch):
    """A role-tabbed section ships every variant, hoisting the first to the top.

    Hoisting is what keeps ``v1`` additive: a consumer that predates variants
    reads the same ``columns``/``rows`` it always did, while the dashboard
    renders one card with a tab per role instead of two stacked cards.
    """
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(ROLE_TABBED_SECTION)})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))
    _write_committer_widgets(api_env, pd.DataFrame({"name": ["b"], "committers": [2], "last_seen": ["2026-07-02"]}))

    api_dir = emit_data_api().parent
    document = json.loads((api_dir / ORG / "widgets.json").read_text())

    assert document["rows"] == [{"name": "a", "count": 1, "last_seen": "2026-07-01"}]
    assert [variant["label"] for variant in document["variants"]] == ["Maintainers", "Committers"]
    committer = document["variants"][1]
    assert committer["id"] == "committerwidgets"
    assert committer["description"] == "The committer view."
    assert committer["rows"] == [{"name": "b", "committers": 2, "last_seen": "2026-07-02"}]
    assert [column["key"] for column in committer["columns"]] == ["name", "committers", "last_seen"]


def test_absorbed_variants_keep_their_own_id_and_document(api_env: Path, monkeypatch: pytest.MonkeyPatch):
    """Merging two cards into one must not withdraw ids consumers already resolve.

    ``v1`` is additive-only and shared ``#widget=`` links name section ids, so
    an absorbed variant keeps its own document and manifest entry, tagged with
    the card that now renders it.
    """
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(ROLE_TABBED_SECTION)})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))
    _write_committer_widgets(api_env, pd.DataFrame({"name": ["b"], "committers": [2], "last_seen": ["2026-07-02"]}))

    manifest_path = emit_data_api()
    manifest = json.loads(manifest_path.read_text())

    entries = {section["id"]: section for section in manifest["orgs"][ORG]["sections"]}
    assert set(entries) == {"widgets", "committerwidgets"}
    assert "absorbed_by" not in entries["widgets"]
    assert entries["committerwidgets"]["absorbed_by"] == "widgets"
    assert entries["committerwidgets"]["row_count"] == 1
    absorbed = json.loads((manifest_path.parent / ORG / "committerwidgets.json").read_text())
    assert absorbed["rows"] == [{"name": "b", "committers": 2, "last_seen": "2026-07-02"}]
    assert absorbed["group"] == "A group"


def test_a_role_variant_without_its_table_is_simply_absent(api_env: Path, monkeypatch: pytest.MonkeyPatch):
    """One surviving variant is an ordinary single-table section, tab row and all."""
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(ROLE_TABBED_SECTION)})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest_path = emit_data_api()

    document = json.loads((manifest_path.parent / ORG / "widgets.json").read_text())
    assert "variants" not in document
    assert [section["id"] for section in json.loads(manifest_path.read_text())["orgs"][ORG]["sections"]] == ["widgets"]


def test_a_role_variant_faces_the_column_contract(api_env: Path, monkeypatch: pytest.MonkeyPatch):
    """A renamed column in a variant's CSV fails the emit like the base table's."""
    monkeypatch.setattr(data_api, "TABLE_FAMILIES", {"Testing": _family(ROLE_TABBED_SECTION)})
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))
    _write_committer_widgets(api_env, pd.DataFrame({"name": ["b"], "commiters": [2], "last_seen": ["2026-07-02"]}))

    with pytest.raises(DataApiContractError, match="committer_widgets.csv"):
        emit_data_api()


def test_chart_variants_carry_their_own_note_and_methodology(
    api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Each tab explains the population it shows, not the first tab's.

    A role-tabbed card's committer note used to be unreachable: the emitter
    picked one entry per chart, so the reader on the Committers tab was told
    they were looking at maintainers.
    """
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
                            "files": [
                                ("Widgets", [("All", "widgets.png"), ("Active", "widgets_active.png")]),
                            ],
                        }
                    ]
                },
            }
        ],
    )
    monkeypatch.setattr(
        data_api,
        "CHART_NOTES",
        {"widgets.png": "Every widget.", "widgets_active.png": "Only the active ones."},
    )
    monkeypatch.setattr(
        data_api,
        "CHART_METHODOLOGY",
        {"widgets.png": ["Count them all."], "widgets_active.png": ["Filter, then count."]},
    )
    chart_dir = tmp_path / "charts" / "org" / ORG
    chart_dir.mkdir(parents=True)
    for name in ("widgets.png", "widgets_active.png"):
        (chart_dir / name).write_bytes(b"\x89PNG")
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    ((chart,),) = [section["charts"] for section in manifest["orgs"][ORG]["chart_sections"]]
    assert [(variant["label"], variant["note"]) for variant in chart["variants"]] == [
        ("All", "Every widget."),
        ("Active", "Only the active ones."),
    ]
    assert chart["variants"][1]["methodology"] == ["Filter, then count."]


def test_chart_downloads_can_be_declared_per_variant(api_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A role-tabbed card offers the active tab's companion CSV, not one for all.

    Only the tabs with a declared companion appear, so the frontend can hide
    the button where the active tab has none rather than handing the reader
    another tab's table.
    """
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
                            # "Active" declares a companion that no pipeline
                            # produced, so it must not be offered at all.
                            "csv": {"All": "widgets.csv", "Active": "widgets_active.csv"},
                            "files": [
                                ("Widgets", [("All", "widgets.png"), ("Active", "widgets_active.png")]),
                            ],
                        }
                    ]
                },
            }
        ],
    )
    chart_dir = tmp_path / "charts" / "org" / ORG
    chart_dir.mkdir(parents=True)
    for name in ("widgets.png", "widgets_active.png"):
        (chart_dir / name).write_bytes(b"\x89PNG")
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [1], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    (section,) = manifest["orgs"][ORG]["chart_sections"]
    assert "download" not in section
    assert section["downloads"] == {
        "All": {
            "name": "widgets.csv",
            "path": f"{ORG}/widgets.csv",
            "generated_at": "2026-07-25T10:00:00+00:00",
        }
    }
    assert (tmp_path / "data" / "api" / API_VERSION / ORG / "widgets.csv").exists()


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
    assert manifest["period_labels"]["30d"] == "1 month"


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


def test_manifest_carries_the_wip_flag_and_issues_url(api_env: Path, tmp_path: Path):
    """The WIP banner and the report link are data-side policy (#322).

    ``wip`` ships true today; retiring the banner is then a one-line flip here
    rather than a frontend change. The frontend treats an *absent* flag as
    show-the-banner, so an older cached manifest fails toward warning too long.
    """
    _write_widgets(api_env, pd.DataFrame({"name": ["a"], "count": [3], "last_seen": ["2026-07-01"]}))

    manifest = json.loads(emit_data_api().read_text())

    assert manifest["wip"] is True
    assert manifest["issues_url"].startswith("https://github.com/")
