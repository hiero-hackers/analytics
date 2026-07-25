"""Guards against drift inside the dashboard spec package."""

from __future__ import annotations

import importlib

from hiero_analytics.dashboard_spec import (
    CHART_MACROS,
    CHART_METHODOLOGY,
    CHART_NOTES,
    CUSTOM_SECTION_MODULES,
    MACRO_GLOSSARIES,
    TABLE_FAMILIES,
    WIDE_CHARTS,
)


def _referenced_files() -> set[str]:
    """Every chart filename any macro actually lists."""
    files: set[str] = set()
    for macro in CHART_MACROS:
        for specs in macro["charts"].values():
            for spec in specs:
                for _caption, variants in spec["files"]:
                    files.update(filename for _label, filename in variants)
    return files


def test_chart_annotations_reference_existing_charts():
    """Notes, methodology, and wide flags may only point at charts a macro lists.

    An entry keyed by a chart no macro references is dead weight — usually a
    leftover from a removed chart — and fails here instead of drifting silently.
    """
    referenced = _referenced_files()

    assert set(CHART_NOTES) <= referenced, sorted(set(CHART_NOTES) - referenced)
    assert set(CHART_METHODOLOGY) <= referenced, sorted(set(CHART_METHODOLOGY) - referenced)
    assert referenced >= WIDE_CHARTS, sorted(WIDE_CHARTS - referenced)


def test_section_groups_match_section_specs():
    """Every section id is grouped exactly once, and every grouped id exists.

    A drifted id would otherwise only surface as a KeyError mid-dashboard-build.
    """
    for macro_name, family in TABLE_FAMILIES.items():
        spec_ids = [spec["id"] for spec in family.SECTION_SPECS]
        grouped_ids = [section_id for _name, ids in family.SECTION_GROUPS for section_id in ids]

        assert len(set(spec_ids)) == len(spec_ids), macro_name  # no duplicate section ids
        assert sorted(grouped_ids) == sorted(spec_ids), macro_name


def test_chart_files_are_canonical():
    """After assembly, every files entry is ``(caption, [(label, filename), ...])``."""
    for macro in CHART_MACROS:
        for specs in macro["charts"].values():
            for spec in specs:
                for _caption, variants in spec["files"]:
                    assert isinstance(variants, list) and variants
                    assert all(isinstance(label, str) and filename.endswith(".png") for label, filename in variants)


def _macro_names() -> set[str]:
    """Every macro (family) name the dashboard renders."""
    return {macro["name"] for macro in CHART_MACROS}


def test_custom_section_modules_are_importable_builders():
    """A declared custom-sections module must exist and expose build_sections.

    The renderer resolves these by import path at render time, so a typo would
    otherwise surface as a missing dashboard section rather than an error.
    """
    assert set(CUSTOM_SECTION_MODULES) <= _macro_names()
    for macro_name, module_path in CUSTOM_SECTION_MODULES.items():
        module = importlib.import_module(module_path)
        builder = getattr(module, "build_sections", None)
        assert callable(builder), f"{macro_name}: {module_path} has no build_sections()"


def test_macro_glossaries_belong_to_real_macros():
    """A family-specific glossary must attach to a macro that is rendered."""
    assert set(MACRO_GLOSSARIES) <= _macro_names()
    for macro_name, glossary in MACRO_GLOSSARIES.items():
        assert glossary.startswith("<details"), f"{macro_name}: glossary must be its own expander"
