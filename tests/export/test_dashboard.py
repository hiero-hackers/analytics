"""Tests for the self-contained, macro→org→section HTML dashboard builder."""

from __future__ import annotations

from hiero_analytics.export.dashboard import build_dashboard_html


def _tab(org, sections, metrics=(("contributors", 2),)):
    return {"org": org, "metrics": list(metrics), "sections": sections}


def _macro(org_tabs, name="Contributors & governance"):
    return {"name": name, "org_tabs": list(org_tabs)}


def _doc():
    sections = [
        {
            "id": "people",
            "title": "People",
            "description": "Who did what.",
            "columns": [("name", "name"), ("prs", "PRs")],
            "rows": [{"name": "alice", "prs": 3}, {"name": "bob", "prs": 0}],
        }
    ]
    return build_dashboard_html([_macro([_tab("hiero-ledger", sections)])])


def test_dashboard_is_self_contained_html():
    """Output is a complete HTML doc with inlined styles and script (no CDN)."""
    doc = _doc()
    assert doc.startswith("<!DOCTYPE html>")
    assert "<style>" in doc and "<script>" in doc
    assert "cdn" not in doc.lower() and "http" not in doc  # no external resources


def test_dashboard_renders_metrics_sections_and_rows():
    """Headline metric, section title, and data cells are all present."""
    doc = _doc()
    assert "hiero-ledger" in doc
    assert "contributors" in doc and ">2<" in doc  # metric value
    assert "People" in doc  # section title
    assert "alice" in doc and "bob" in doc  # rows


def test_dashboard_includes_a_glossary():
    """A definitions legend is rendered so columns are self-documenting."""
    doc = _doc()
    assert "class='glossary'" in doc
    assert "what each column means" in doc
    assert "<dt>PRs</dt>" in doc  # raw counts are defined


def test_sort_uses_whole_string_numeric_guard():
    """Sort only treats fully-numeric cells as numbers, so ISO dates sort lexically.

    parseFloat('2026-06-24 ...') would return 2026 and make every date compare equal;
    the guard must require the whole cell to be a number.
    """
    doc = _doc()
    assert "num.test(x)&&num.test(y)" in doc  # whole-string numeric test
    assert "parseFloat(x)" not in doc  # the buggy leading-number parse is gone


def test_single_org_has_no_tab_bar_multi_org_does():
    """The org tab bar appears only with more than one org."""
    sec = [{"id": "p", "title": "P", "description": "d", "columns": [("a", "a")], "rows": [{"a": 1}]}]
    one = build_dashboard_html([_macro([_tab("hiero-ledger", sec)])])
    two = build_dashboard_html([_macro([_tab("hiero-ledger", sec), _tab("hiero-hackers", sec)])])

    assert "class='tabbar'" not in one
    assert "class='tabbar'" in two
    assert "hiero-hackers" in two
    # section ids are namespaced per macro+org so they don't collide
    assert "-hiero-ledger-p'" in two and "-hiero-hackers-p'" in two


def test_macro_bar_shows_even_for_one_family_and_scales_up():
    """The macro bar is always rendered (labels the family), with a button per macro."""
    sec = [{"id": "p", "title": "P", "description": "d", "columns": [("a", "a")], "rows": [{"a": 1}]}]
    one = build_dashboard_html([_macro([_tab("hiero-ledger", sec)], "Governance")])
    two = build_dashboard_html(
        [_macro([_tab("hiero-ledger", sec)], "Governance"), _macro([_tab("hiero-ledger", sec)], "Onboarding")]
    )

    assert "class='macrobar'" in one  # shown even with a single family
    assert "switchMacro('governance')" in one
    assert "class='macrobar'" in two
    assert "switchMacro('onboarding')" in two
    # macro+org namespacing keeps the repeated org's section ids distinct per macro
    assert "id='governance-hiero-ledger-p'" in two and "id='onboarding-hiero-ledger-p'" in two


def test_chart_section_renders_embedded_images():
    """A section with 'charts' renders a gallery of <img> tags, no table."""
    sections = [
        {
            "id": "ch",
            "title": "Charts",
            "description": "pictures",
            "charts": [
                {"title": "Yearly", "src": "data:image/png;base64,AAAA"},
                {"title": "By repo", "src": "data:image/png;base64,BBBB"},
            ],
        }
    ]
    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections, metrics=())], "Community")])
    assert "class='gallery'" in doc
    assert 'src="data:image/png;base64,AAAA"' in doc
    assert "<figcaption>By repo</figcaption>" in doc
    assert "<table" not in doc  # charts don't render a table
    assert 'onclick="openLightbox(this)"' in doc  # click to expand
    assert "id='lightbox'" in doc  # the overlay exists
    assert "id='lightbox-note'" in doc  # the zoom view has a slot for the chart's note
    assert "class='glossary'" not in doc  # column glossary doesn't apply to a chart-only macro


def test_chart_note_and_methodology_only_appear_in_zoom_view():
    """The note and step-by-step methodology are carried hidden, for the lightbox only."""
    sections = [
        {
            "id": "ch",
            "title": "Charts",
            "description": "pictures",
            "charts": [{
                "title": "Yearly",
                "src": "data:image/png;base64,AAAA",
                "note": "How to read this chart.",
                "methodology": ["First do this.", "Then do that."],
            }],
        }
    ]
    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections, metrics=())], "Community")])
    assert "class='lbinfo' hidden" in doc  # note + methodology carried hidden in the figure
    assert "How to read this chart." in doc  # the short note
    assert "Step-by-step methodology" in doc  # the expandable methodology
    assert "<li>First do this.</li>" in doc and "<li>Then do that.</li>" in doc  # steps as a list
    assert "id='lightbox-note'" in doc  # the zoom view has the slot that reveals them


def test_slideshow_section_renders_nav_and_first_slide_only():
    """A slideshow section shows Prev/Next + counter, with only the first slide visible."""
    sections = [
        {
            "id": "nets",
            "title": "Networks",
            "description": "by group",
            "slideshow": True,
            "charts": [
                {"title": "Maintainers", "src": "data:image/png;base64,AAAA"},
                {"title": "Committers", "src": "data:image/png;base64,BBBB"},
            ],
        }
    ]
    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections, metrics=())])])
    assert "class='slideshow'" in doc
    # nav is wired to the namespaced section id (macro+org prefixed)
    assert "-nets',1)" in doc and "-nets',-1)" in doc
    assert "1 / 2" in doc  # counter
    # second slide starts hidden, first visible
    assert 'style="display:none"' in doc
    assert "<figcaption>Committers</figcaption>" in doc


def test_dashboard_escapes_html_in_values():
    """Cell values are HTML-escaped, so data can't inject markup."""
    sections = [
        {
            "id": "x",
            "title": "X",
            "description": "d",
            "columns": [("name", "name")],
            "rows": [{"name": "<script>alert(1)</script>"}],
        }
    ]
    doc = build_dashboard_html([_macro([_tab("org", sections, metrics=())])])
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;" in doc


def test_dashboard_handles_missing_keys_and_nan():
    """A row missing a column, or carrying NaN, renders as an empty cell, not a crash."""
    sections = [
        {
            "id": "x",
            "title": "X",
            "description": "d",
            "columns": [("a", "a"), ("b", "b")],
            "rows": [{"a": float("nan")}],  # 'b' missing, 'a' is NaN
        }
    ]
    doc = build_dashboard_html([_macro([_tab("org", sections, metrics=())])])
    # Both the NaN cell and the missing-key cell render empty (not "nan"/"None").
    assert "<td></td><td></td>" in doc
    assert "None" not in doc
