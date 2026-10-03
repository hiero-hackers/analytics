"""Guards against drift inside the dashboard spec package."""

from __future__ import annotations

import importlib

from hiero_analytics.dashboard_spec import (
    CHART_MACROS,
    CHART_METHODOLOGY,
    CHART_NOTES,
    COLUMN_FORMATS,
    CUSTOM_VIEW_MODULES,
    FULL_ROW_CHARTS,
    MACRO_GLOSSARIES,
    MACRO_SUMMARIES,
    TABLE_FAMILIES,
    WIDE_CHARTS,
    table_variants,
)
from hiero_analytics.export.data_api import variant_annotations


def _referenced_ids() -> set[str]:
    """Every chart id any macro actually lists."""
    ids: set[str] = set()
    for macro in CHART_MACROS:
        for specs in macro["charts"].values():
            for spec in specs:
                for _caption, variants in spec["variants"]:
                    ids.update(chart_id for _label, chart_id in variants)
    return ids


def test_chart_annotations_reference_existing_charts():
    """Notes, methodology, and layout flags may only point at charts a macro lists.

    An entry keyed by a chart no macro references is dead weight — usually a
    leftover from a removed chart — and fails here instead of drifting silently.
    """
    referenced = _referenced_ids()

    assert set(CHART_NOTES) <= referenced, sorted(set(CHART_NOTES) - referenced)
    assert set(CHART_METHODOLOGY) <= referenced, sorted(set(CHART_METHODOLOGY) - referenced)
    assert referenced >= WIDE_CHARTS, sorted(WIDE_CHARTS - referenced)
    assert referenced >= FULL_ROW_CHARTS, sorted(FULL_ROW_CHARTS - referenced)
    # A chart is either scrolled wide or spanned full-row, never both.
    assert not WIDE_CHARTS & FULL_ROW_CHARTS, sorted(WIDE_CHARTS & FULL_ROW_CHARTS)


def test_every_chart_annotation_reaches_a_variant():
    """Every note and methodology entry must reach the tab it was written for.

    The emitter used to pick one entry per chart (the first listed filename
    that happened to be keyed), so an entry belonging to any later tab was
    dead text: the committer tabs rendered the maintainer note, and the period
    tabs the all-time one. This walks the real spec through the emitter's own
    per-variant lookup, so reverting to per-chart selection fails here rather
    than shipping unreachable copy.
    """
    reached_notes, reached_methods = set(), set()
    for macro in CHART_MACROS:
        for specs in macro["charts"].values():
            for spec in specs:
                for _caption, variants in spec["variants"]:
                    for _label, chart_id in variants:
                        annotations = variant_annotations(chart_id)
                        if "note" in annotations:
                            reached_notes.add(chart_id)
                        if "methodology" in annotations:
                            reached_methods.add(chart_id)

    assert set(CHART_NOTES) == reached_notes, sorted(set(CHART_NOTES) ^ reached_notes)
    assert set(CHART_METHODOLOGY) == reached_methods, sorted(set(CHART_METHODOLOGY) ^ reached_methods)


def test_section_groups_match_section_specs():
    """Every section id is grouped exactly once, and every grouped id exists.

    A drifted id would otherwise only surface as a KeyError mid-dashboard-build.
    """
    for macro_name, family in TABLE_FAMILIES.items():
        spec_ids = [spec["id"] for spec in family.SECTION_SPECS]
        grouped_ids = [section_id for _name, ids in family.SECTION_GROUPS for section_id in ids]

        assert len(set(spec_ids)) == len(spec_ids), macro_name  # no duplicate section ids
        assert sorted(grouped_ids) == sorted(spec_ids), macro_name


def test_chart_variants_are_canonical():
    """After assembly, every variants entry is ``(caption, [(label, chart_id), ...])``.

    A chart id doubles as the chart document's filename stem and the key of the
    dashboard's URL state for that view, so it is a plain slug: no extension,
    no path separators.
    """
    for macro in CHART_MACROS:
        for specs in macro["charts"].values():
            for spec in specs:
                for _caption, variants in spec["variants"]:
                    assert isinstance(variants, list) and variants
                    for label, chart_id in variants:
                        assert isinstance(label, str) and label
                        assert isinstance(chart_id, str) and chart_id
                        assert "." not in chart_id and "/" not in chart_id, chart_id


def test_every_chart_variant_has_exactly_one_source():
    """A card's variant ids and its ``sources`` keys are the same set.

    Every listed variant is drawn from its source dataset — there is no other
    way to render one — so a variant without a source would be a tab that can
    never appear, and a source without a variant is dead configuration.
    """
    for macro in CHART_MACROS:
        for specs in macro["charts"].values():
            for spec in specs:
                listed = {chart_id for _caption, variants in spec["variants"] for _label, chart_id in variants}
                assert listed == set(spec["sources"]), (macro["name"], spec["id"], listed ^ set(spec["sources"]))


def test_chart_ids_are_unique_within_an_org():
    """Two cards in one org may not share a chart id.

    The data API writes one ``<org>/charts/<id>.json`` per id and the dashboard
    keys the view's URL state by it, so a collision would make one chart
    silently overwrite the other's document and state.
    """
    for macro in CHART_MACROS:
        for org, specs in macro["charts"].items():
            seen: dict[str, str] = {}
            for spec in specs:
                for _caption, variants in spec["variants"]:
                    for _label, chart_id in variants:
                        assert chart_id not in seen, (org, chart_id, seen[chart_id], spec["id"])
                        seen[chart_id] = spec["id"]


def _macro_names() -> set[str]:
    """Every macro (family) name the dashboard renders."""
    return {macro["name"] for macro in CHART_MACROS}


def test_custom_view_modules_are_importable_builders():
    """A declared custom-views module must exist and expose build_views.

    The data API resolves these by import path at emit time, so a typo would
    otherwise surface as a silently missing view rather than an error.
    """
    assert set(CUSTOM_VIEW_MODULES) <= _macro_names()
    for macro_name, module_path in CUSTOM_VIEW_MODULES.items():
        module = importlib.import_module(module_path)
        builder = getattr(module, "build_views", None)
        assert callable(builder), f"{macro_name}: {module_path} has no build_views()"


def test_macro_glossaries_belong_to_real_macros():
    """A family glossary must attach to a rendered macro and carry no markup."""
    assert set(MACRO_GLOSSARIES) <= _macro_names()
    for macro_name, glossary in MACRO_GLOSSARIES.items():
        assert glossary["title"], f"{macro_name}: glossary needs a title"
        assert glossary["terms"], f"{macro_name}: glossary needs terms"
        # Data, not markup — the frontend owns the rendering.
        assert "<" not in str(glossary), f"{macro_name}: glossary must not carry HTML"


def test_every_macro_has_a_plain_one_line_summary():
    """Each tab states its purpose under its title: one line of text, no markup."""
    assert set(MACRO_SUMMARIES) == _macro_names()
    for macro_name, summary in MACRO_SUMMARIES.items():
        assert summary.strip(), f"{macro_name}: summary is empty"
        assert "\n" not in summary, f"{macro_name}: summary must be one line"
        assert "<" not in summary, f"{macro_name}: summary must not carry HTML"


def test_activity_specs_use_the_shared_period_set():
    """The tabbed activity tables opt in via the flag; filenames derive centrally."""
    all_specs = [spec for family in TABLE_FAMILIES.values() for spec in family.SECTION_SPECS]
    tabbed = {spec["id"]: spec for spec in all_specs if spec.get("periods")}

    assert set(tabbed) == {
        "profiles",
        "repoactivity",
        "understaffed",
        "loadshare",
        "gonedark",
        "repo",
        "teams",
        "teamrepo",
        "tscrepo",
    }
    assert all(spec["periods"] is True for spec in tabbed.values())


def test_every_macro_has_its_own_explainer():
    """A tab without a "how to read this" leaves its numbers unexplained."""
    missing = sorted(_macro_names() - set(MACRO_GLOSSARIES))
    assert not missing, f"macros with no glossary: {missing}"


def test_column_glossaries_cover_the_columns_their_tables_show():
    """A definitions-layout glossary must explain the labels on its own tab.

    Guards the "exclusively relevant" rule in both directions: a tab must not
    define columns it never shows, and every label it does show should be
    explained (or deliberately listed as self-evident below).
    """
    # Labels needing no gloss: they name the thing itself, not a derived metric.
    SELF_EVIDENT = {
        "repo",
        "team",
        "maintainer",
        "member",
        "user",
        "organisations",
        "active maintainers",
        "comm. actions",
        "maint. actions",
        "triage actions",
        "committers",
        "maintainers",
        "triage",
        "top %",
        "top-2 %",
        "top role",
        "largest org",
        "largest org %",
        "members active",
        "active",
        "role here",
        "role",
    }
    for macro_name, family in TABLE_FAMILIES.items():
        glossary = MACRO_GLOSSARIES.get(macro_name, {})
        if glossary.get("layout") != "definitions":
            continue
        # Each glossary key may name several labels ("a / b / c").
        defined = {part.strip() for entry in glossary["terms"] for part in entry["term"].split("/")}
        # Through the role variants: a label that only appears on a tab is
        # still a label the tab shows, and must still be explained.
        shown = {
            column[1]
            for spec in family.SECTION_SPECS
            for variant in table_variants(spec)
            for column in variant["columns"]
        }
        unexplained = shown - defined - SELF_EVIDENT
        assert not unexplained, f"{macro_name}: columns shown but not explained: {sorted(unexplained)}"


def test_every_chart_has_a_note_and_a_methodology():
    """Each chart must explain what it shows and how it was derived.

    The reverse check (annotations referencing real charts) already exists; this
    is the coverage direction — without it, annotations accrue ad-hoc and a new
    chart ships with an empty lightbox. Variants share their chart's entry, so a
    chart counts as annotated if any of its variant ids is keyed.
    """
    missing_note, missing_method = [], []
    for macro in CHART_MACROS:
        for specs in macro["charts"].values():
            for spec in specs:
                for caption, variants in spec["variants"]:
                    ids = [chart_id for _label, chart_id in variants]
                    where = f"{macro['name']} / {caption}"
                    if not any(i in CHART_NOTES for i in ids):
                        missing_note.append(where)
                    if not any(i in CHART_METHODOLOGY for i in ids):
                        missing_method.append(where)

    assert not missing_note, f"charts with no 'how to read this' note: {sorted(set(missing_note))}"
    assert not missing_method, f"charts with no step-by-step methodology: {sorted(set(missing_method))}"


def test_column_formats_are_ones_the_frontend_implements():
    """A column may only declare a format the dashboard knows how to render.

    An unknown format is not an error at render time — it falls through to
    plain text — so without this a typo ships as a quietly unformatted column.
    """
    unknown = {
        (family.CHART_MACRO["name"], spec["id"], column[0], column[2])
        for family in TABLE_FAMILIES.values()
        for spec in family.SECTION_SPECS
        for column in spec["columns"]
        if len(column) > 2 and column[2] not in COLUMN_FORMATS
    }
    assert not unknown, f"columns declaring an unknown format: {sorted(unknown)}"
