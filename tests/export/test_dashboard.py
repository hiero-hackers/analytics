"""Tests for the self-contained, macro→org→section HTML dashboard builder."""

from __future__ import annotations

import re

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
    assert "href='#governance'" in one  # macro tabs are real, shareable links
    assert "class='macrobar'" in two
    assert "href='#onboarding'" in two
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


def test_tabbed_chart_renders_a_switcher_with_one_figcaption():
    """A variant chart renders tab buttons + one image per variant, first visible, one caption."""
    sections = [
        {
            "id": "ch",
            "title": "Charts",
            "description": "pictures",
            "charts": [
                {
                    "title": "Pipeline",
                    "variants": [
                        {"label": "By year", "src": "data:image/png;base64,AAAA"},
                        {"label": "By month", "src": "data:image/png;base64,BBBB"},
                    ],
                }
            ],
        }
    ]
    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections, metrics=())], "Community")])
    assert 'class="charttabs"' in doc  # the tab bar
    assert "chartTab(this,0)" in doc and "chartTab(this,1)" in doc  # a button per view
    assert ">By year<" in doc and ">By month<" in doc  # tab labels
    assert 'data-i="1"' in doc  # second variant image present
    assert 'style="display:none"' in doc  # non-first variant starts hidden
    assert doc.count("<figcaption>Pipeline</figcaption>") == 1  # one caption for the whole switcher


def test_tabbed_table_renders_independent_period_variants():
    """Each table period has its own controls and only the first starts visible."""
    sections = [
        {
            "id": "people",
            "title": "People",
            "description": "Activity by period.",
            "variants": [
                {
                    "label": "90 days",
                    "columns": [("name", "name"), ("prs", "PRs")],
                    "rows": [{"name": "alice", "prs": 2}],
                },
                {
                    "label": "All time",
                    "columns": [("name", "name"), ("prs", "PRs")],
                    "rows": [{"name": "alice", "prs": 8}, {"name": "bob", "prs": 1}],
                },
            ],
        }
    ]

    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections)])])

    assert "class='periodtabs'" in doc
    assert "periodTab(this,0)" in doc and "periodTab(this,1)" in doc
    assert ">90 days<" in doc and ">All time<" in doc
    assert "id='contributors-governance-hiero-ledger-people-period-0'" in doc
    assert "id='contributors-governance-hiero-ledger-people-period-1'" in doc
    assert "class='periodview' style='display:none'" in doc
    assert "exportCSV('contributors-governance-hiero-ledger-people-period-1'" in doc
    assert "<span class='sbadge'>2 rows</span>" in doc


def test_tabbed_table_opens_on_the_configured_default_variant():
    """active_variant, not tab order, decides which period starts visible."""
    sections = [
        {
            "id": "people",
            "title": "People",
            "description": "Activity by period.",
            "active_variant": 1,
            "variants": [
                {"label": "30 days", "columns": [("name", "name")], "rows": [{"name": "a"}]},
                {"label": "90 days", "columns": [("name", "name")], "rows": [{"name": "a"}, {"name": "b"}]},
            ],
        }
    ]

    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections)])])
    prefix = "contributors-governance-hiero-ledger-people-period-"

    # The 90-day tab (index 1) is active; the 30-day tab is not.
    assert "class='periodtab active' onclick='periodTab(this,1)'" in doc
    assert "class='periodtab' onclick='periodTab(this,0)'" in doc
    # The 90-day view is shown; the 30-day view carries display:none.
    assert f"<div class='periodview'><button class='dl' onclick=\"exportCSV('{prefix}1'" in doc
    assert f"<div class='periodview' style='display:none'><button class='dl' onclick=\"exportCSV('{prefix}0'" in doc


def test_tabbed_chart_carries_per_variant_override_notes():
    """A variant whose note differs from the shared one gets its own data-i lightbox note."""
    sections = [
        {
            "id": "ch",
            "title": "Charts",
            "description": "pictures",
            "charts": [
                {
                    "title": "Pipeline",
                    "note": "Yearly note.",  # shared = first variant's note
                    "variants": [
                        {"label": "By year", "src": "data:image/png;base64,AAAA", "note": "Yearly note."},
                        {"label": "By repo", "src": "data:image/png;base64,BBBB", "note": "By-repo note."},
                    ],
                }
            ],
        }
    ]
    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections, metrics=())], "Community")])
    assert "<div class='lbinfo' hidden>" in doc and "Yearly note." in doc  # shared note (fallback)
    assert "class='lbinfo' data-i='1'" in doc and "By-repo note." in doc  # differing variant overrides
    assert "class='lbinfo' data-i='0'" not in doc  # matching variant reuses the shared note, no dup


def test_chart_note_and_methodology_only_appear_in_zoom_view():
    """The note and step-by-step methodology are carried hidden, for the lightbox only."""
    sections = [
        {
            "id": "ch",
            "title": "Charts",
            "description": "pictures",
            "charts": [
                {
                    "title": "Yearly",
                    "src": "data:image/png;base64,AAAA",
                    "note": "How to read this chart.",
                    "methodology": ["First do this.", "Then do that."],
                }
            ],
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


def test_section_renders_freshness_stamp_and_stale_warning():
    """Sections carry their "data as of" stamp; stale ones get the warning class."""
    from hiero_analytics.export.dashboard import build_dashboard_html

    def _macro(section_extra: dict) -> list[dict]:
        section = {
            "id": "s1",
            "title": "T",
            "description": "D",
            "columns": [("a", "A")],
            "rows": [{"a": 1}],
            **section_extra,
        }
        return [{"name": "M", "org_tabs": [{"org": "o", "metrics": [], "sections": [section]}]}]

    fresh = build_dashboard_html(_macro({"data_as_of": "2026-07-24 10:00 UTC"}), generated_at="2026-07-24 11:00 UTC")
    assert "data as of 2026-07-24 10:00 UTC" in fresh
    assert "asof stale" not in fresh
    assert "generated 2026-07-24 11:00 UTC" in fresh

    stale = build_dashboard_html(_macro({"data_as_of": "2026-07-01 10:00 UTC", "stale": True}))
    assert "asof stale" in stale
    assert "older than the scheduled refresh" in stale


def test_tables_carry_the_attributes_the_csv_export_stamps():
    """The export reads title/watermark/total off the table, so they must be emitted."""
    sections = [
        {
            "id": "people",
            "title": "People",
            "description": "Who did what.",
            "columns": [("name", "name"), ("prs", "PRs")],
            "rows": [{"name": "alice", "prs": 3}, {"name": "bob", "prs": 0}],
            "data_as_of": "2026-07-24 09:00 UTC",
        }
    ]
    doc = build_dashboard_html(
        [_macro([_tab("hiero-ledger", sections)])],
        generated_at="2026-07-25 09:14 UTC",
        git_sha="abc1234",
    )

    assert 'data-title="People"' in doc
    assert 'data-asof="2026-07-24 09:00 UTC"' in doc
    # The total is what lets a filtered download admit it is a subset.
    assert "data-total='2'" in doc
    # Section ids are namespaced per macro+org; the export finds the filter box
    # by "<table id>-q", so that pairing is the invariant worth pinning.
    table_id = re.search(r"<table id='([^']+)'", doc).group(1)
    assert f"id='{table_id}-q'" in doc
    assert '"sha": "abc1234"' in doc


def test_period_variants_name_themselves_in_the_export():
    """Each period is a different row set, so "People.csv" alone would be ambiguous."""
    sections = [
        {
            "id": "people",
            "title": "People",
            "description": "D",
            "variants": [
                {"label": "30d", "columns": [("a", "A")], "rows": [{"a": 1}]},
                {"label": "90d", "columns": [("a", "A")], "rows": [{"a": 1}, {"a": 2}]},
            ],
        }
    ]
    doc = build_dashboard_html([_macro([_tab("hiero-ledger", sections)])])

    assert 'data-title="People — 30d"' in doc
    assert 'data-title="People — 90d"' in doc
    assert "data-total='1'" in doc
    assert "data-total='2'" in doc


def test_provenance_global_is_json_encoded():
    """The values land inside a <script> block, so they are encoded, not interpolated."""
    doc = build_dashboard_html([], generated_at='2026 "quoted"', git_sha=None)

    assert 'var PROVENANCE={"generated": "2026 \\"quoted\\"", "sha": ""};' in doc


def test_export_stamps_a_preamble_and_admits_a_filtered_subset():
    """The CSV export must state the subset, not ship a filtered file that looks whole.

    The export takes *visible* rows, so a filtered download is a subset that is
    indistinguishable from the full table once it leaves the dashboard. Browser
    behaviour is exercised manually; these guards pin the shape the export
    depends on so a refactor cannot quietly drop it.
    """
    doc = _doc()
    assert "csvPreamble(table,id,shown)" in doc  # preamble is prepended, not optional
    assert "data-total" in doc  # the total the subset is measured against
    assert "shown+' of '+total+' rows'" in doc
    assert "(filtered: \"'+query+'\")" in doc
    # An unfiltered export must not carry a spurious "filtered" note.
    assert "shown===total?total+' rows'" in doc
