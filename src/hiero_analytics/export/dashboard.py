"""Generate a single self-contained HTML dashboard from the analytics tables.

No server required: open the produced file in any browser. The data is rendered
into static tables, and a small amount of dependency-free vanilla JS adds
per-section search and click-to-sort, so the file works fully offline.
"""

from __future__ import annotations

import html
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path


def _read_asset(name: str) -> str:
    """Read a bundled CSS/JS asset, inlined verbatim into the self-contained output."""
    return (Path(__file__).parent / "assets" / name).read_text(encoding="utf-8")


_CSS = _read_asset("dashboard.css")

_JS = _read_asset("dashboard.js")


# A fixed legend (no user data) so anyone opening the file knows what each column
# means. Every table uses the same five raw contribution counts. Lives alongside
# the CSS/JS in assets/ and is inlined verbatim into the self-contained output.
_GLOSSARY = _read_asset("glossary.html")


def _fmt(value: object) -> str:
    """Format a cell value for display (drop NaN/None, ints stay ints)."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value)


def _lbinfo_inner(note: object, methodology: object, esc) -> str:
    """Inner HTML for a lightbox note block (the short note + expandable methodology).

    Returns an empty string when there is nothing to show, so callers can skip the
    wrapping ``.lbinfo`` div entirely.
    """
    if not note and not methodology:
        return ""
    info = f"<p class='chartnote'>{esc(note)}</p>" if note else ""
    if methodology:
        steps = "".join(f"<li>{esc(step)}</li>" for step in methodology)
        info += f"<details class='lbmethod'><summary>Step-by-step methodology</summary><ol>{steps}</ol></details>"
    return info


def _chart_caption_html(chart: Mapping, esc) -> str:
    """A chart's caption; the note and methodology are carried hidden, revealed only on zoom.

    For a tabbed chart this carries the *shared* note (used by any variant that has no
    note of its own); per-variant overrides are emitted separately by ``_figure_html``.
    """
    caption = f"<figcaption>{esc(chart['title'])}</figcaption>"
    info = _lbinfo_inner(chart.get("note"), chart.get("methodology"), esc)
    if not info:
        return caption
    return f"{caption}<div class='lbinfo' hidden>{info}</div>"


def _slideshow_section_html(section: Mapping, esc) -> str:
    """Render a chart slideshow: one image at a time with Prev/Next navigation."""
    section_id = section["id"]
    slides = "".join(
        f'<figure class="slide" style="{"" if i == 0 else "display:none"}">'
        f'<img src="{chart["src"]}" alt="{esc(chart["title"])}" loading="lazy" '
        f'onclick="openLightbox(this)">'
        f"{_chart_caption_html(chart, esc)}</figure>"
        for i, chart in enumerate(section["charts"])
    )
    count = len(section["charts"])
    return (
        f"<section class='card'><h2>{esc(section['title'])}</h2>"
        f"<p class='desc'>{esc(section['description'])}</p>"
        f"<div class='slideshow' id='{section_id}-show'>"
        f"<div class='slidenav'>"
        f"<button class='snav' onclick=\"slide('{section_id}',-1)\">‹ Prev</button>"
        f"<span class='scount' id='{section_id}-counter'>1 / {count}</span>"
        f"<button class='snav' onclick=\"slide('{section_id}',1)\">Next ›</button>"
        f"</div>"
        f"<div class='slides'>{slides}</div></div></section>"
    )


def _figure_html(chart: Mapping, esc) -> str:
    """A gallery figure: a single image, or an All/Active tab switcher if it has variants.

    'wide' charts (vertical bars over many items) are wrapped in a horizontally
    scrollable box so they show at a readable size instead of being squashed to fit.
    """
    caption = _chart_caption_html(chart, esc)
    wide = chart.get("wide")
    # Wide charts get their own full-width row so the horizontal scroll has room.
    fig_cls = "chart wide" if wide else "chart"
    open_scroll = "<div class='chartscroll'>" if wide else ""
    close_scroll = "</div>" if wide else ""
    if not chart.get("variants"):
        img = f'<img src="{chart["src"]}" alt="{esc(chart["title"])}" loading="lazy" onclick="openLightbox(this)">'
        return f'<figure class="{fig_cls}">{open_scroll}{img}{close_scroll}{caption}</figure>'
    tabs, imgs, var_notes = "", "", ""
    shared_note, shared_meth = chart.get("note"), chart.get("methodology")
    for i, variant in enumerate(chart["variants"]):
        active = " active" if i == 0 else ""
        hidden = "" if i == 0 else ' style="display:none"'
        tabs += f'<button class="ctab{active}" onclick="chartTab(this,{i})">{esc(variant["label"])}</button>'
        imgs += (
            f'<img class="cimg" data-i="{i}" src="{variant["src"]}" alt="{esc(chart["title"])}" '
            f'loading="lazy" onclick="openLightbox(this)"{hidden}>'
        )
        # Emit an override note (tagged with the variant index) only when this variant's
        # note differs from the shared one; otherwise the lightbox falls back to shared.
        note = variant.get("note") or shared_note
        meth = variant.get("methodology") or shared_meth
        differs = note != shared_note or meth != shared_meth
        if differs and (info := _lbinfo_inner(note, meth, esc)):
            var_notes += f"<div class='lbinfo' data-i='{i}' hidden>{info}</div>"
    return (
        f'<figure class="{fig_cls}"><div class="charttabs">{tabs}</div>'
        f"{open_scroll}{imgs}{close_scroll}{caption}{var_notes}</figure>"
    )


def _charts_section_html(section: Mapping, esc) -> str:
    """Render an image section: a slideshow if flagged, else a gallery grid."""
    if section.get("slideshow"):
        return _slideshow_section_html(section, esc)
    figures = "".join(_figure_html(chart, esc) for chart in section["charts"])
    return (
        f"<section class='card'><h2>{esc(section['title'])}</h2>"
        f"<p class='desc'>{esc(section['description'])}</p>"
        f"<div class='gallery'>{figures}</div></section>"
    )


def _table_view_html(section_id: str, columns: Sequence[tuple[str, str]], rows: Sequence[Mapping], esc) -> str:
    head = "".join(
        f"<th onclick=\"sortTable('{section_id}',{i},this)\">{esc(label)}</th>"
        for i, (_key, label) in enumerate(columns)
    )
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(_fmt(row.get(key)))}</td>" for key, _label in columns) + "</tr>" for row in rows
    )
    return (
        f"<button class='dl' onclick=\"exportCSV('{section_id}','{section_id}.csv')\">Download CSV</button>"
        f"<input class='search' placeholder='Filter…' "
        f"oninput=\"filterTable('{section_id}',this.value)\">"
        f"<div class='tablewrap'><table id='{section_id}'><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        f"<p class='count' id='{section_id}-count'>{len(rows)} rows</p>"
    )


def _section_html(section: Mapping, esc) -> str:
    if "charts" in section:
        return _charts_section_html(section, esc)
    section_id = section["id"]
    variants = section.get("variants")
    row_count = max((len(variant["rows"]) for variant in variants), default=0) if variants else len(section["rows"])
    asof = ""
    if section.get("data_as_of"):
        stale = section.get("stale")
        suffix = " — older than the scheduled refresh" if stale else ""
        asof = f"<span class='asof{' stale' if stale else ''}'>data as of {esc(section['data_as_of'])}{suffix}</span>"
    action = (
        f"<a class='dl' href=\"{esc(section['action_url'])}\" target='_blank' rel='noopener'>"
        f"{esc(section.get('action_label', 'Suggest a correction'))}</a>"
        if section.get("action_url")
        else ""
    )
    if variants:
        active_idx = section.get("active_variant", 0)
        tabs = "".join(
            f"<button class='periodtab{' active' if i == active_idx else ''}' onclick='periodTab(this,{i})'>"
            f"{esc(variant['label'])}</button>"
            for i, variant in enumerate(variants)
        )
        tables = "".join(
            ("<div class='periodview'>" if i == active_idx else "<div class='periodview' style='display:none'>")
            + f"{_table_view_html(f'{section_id}-period-{i}', variant['columns'], variant['rows'], esc)}</div>"
            for i, variant in enumerate(variants)
        )
        content = f"<div class='periodtabs'>{tabs}</div>{tables}"
    else:
        content = _table_view_html(section_id, section["columns"], section["rows"], esc)
    return (
        f"<details class='card tsec' open>"
        f"<summary class='tsum'><h2>{esc(section['title'])}</h2>"
        f"<span class='sbadge'>{row_count} rows</span></summary>"
        f"<div class='sbody'>"
        f"<div class='shead'><p class='desc'>{esc(section['description'])}</p>"
        f"{asof}{action}"
        f"</div>"
        f"{content}"
        f"</div></details>"
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "org"


def _metric_cards(metrics: Sequence[tuple[str, object]], esc) -> str:
    return "".join(
        f"<div class='metric'><div class='label'>{esc(label)}</div><div class='value'>{esc(_fmt(value))}</div></div>"
        for label, value in metrics
    )


def _org_panels_html(mslug: str, org_tabs: Sequence[Mapping], esc) -> str:
    """Org tab bar (shown only when >1 org) plus one panel per org for a macro."""
    tab_bar = ""
    if len(org_tabs) > 1:
        buttons = "".join(
            f"<button class='tab{' active' if i == 0 else ''}' id='tabbtn-{mslug}-{_slug(tab['org'])}' "
            f"onclick=\"switchTab('{mslug}','{_slug(tab['org'])}')\">{esc(tab['org'])}</button>"
            for i, tab in enumerate(org_tabs)
        )
        tab_bar = f"<div class='tabbar'>{buttons}</div>"

    panels = []
    for i, tab in enumerate(org_tabs):
        oslug = _slug(tab["org"])
        panel_id = f"tab-{mslug}-{oslug}"
        namespaced = [{**section, "id": f"{mslug}-{oslug}-{section['id']}"} for section in tab["sections"]]

        # Group sections by their "group" key, preserving order of appearance.
        groups: list[tuple[str, list[Mapping]]] = []
        for section in namespaced:
            gname = section.get("group", "")
            if not groups or groups[-1][0] != gname:
                groups.append((gname, []))
            groups[-1][1].append(section)

        # Jump bar: a link per group (each group heading is itself collapsible).
        links = "".join(f"<a class='jbtn' href='#grp-{mslug}-{oslug}-{_slug(g)}'>{esc(g)}</a>" for g, _ in groups)
        jumpbar = f"<div class='jump'><span class='jlabel'>Jump to</span>{links}</div>" if len(groups) > 1 else ""

        # Each group is a collapsible <details>: click its heading to show/hide the
        # whole group. With only one group (e.g. a chart-only macro) the heading is
        # redundant, so the sections render bare.
        show_headers = len(groups) > 1
        blocks = "".join(
            (
                f"<details class='group' id='grp-{mslug}-{oslug}-{_slug(g)}' open>"
                f"<summary class='grouphdr'>{esc(g)}</summary>"
                + "".join(_section_html(s, esc) for s in secs)
                + "</details>"
            )
            if show_headers
            else "".join(_section_html(s, esc) for s in secs)
            for g, secs in groups
        )

        display = "" if i == 0 else "display:none"
        panels.append(
            f"<div class='tabpanel' id='{panel_id}' style='{display}'>"
            f"<div class='metrics'>{_metric_cards(tab['metrics'], esc)}</div>"
            f"{jumpbar}{blocks}</div>"
        )
    return tab_bar + "".join(panels)


def build_dashboard_html(macros: Sequence[Mapping], *, generated_at: str | None = None) -> str:
    """Build a self-contained, two-level (macro → org → section) HTML document.

    ``macros`` is a list of ``{name, org_tabs}``; each macro is a dashboard family
    (e.g. "Contributors & governance") and each ``org_tab`` is
    ``{org, metrics, sections}``. A section is either a table (has ``columns``/
    ``rows``) or a chart gallery (has ``charts``; images expand in a lightbox on
    click). The macro bar always shows (so the family is labelled even with one);
    the org tab bar shows only with more than one org. The column glossary appears
    only inside macros that have a table section. Section ids are namespaced per
    macro+org so filter/sort/export stay independent. All values are HTML-escaped.
    """
    esc = html.escape
    stamp = f" · generated {esc(generated_at)}" if generated_at else ""
    header = (
        "<h1>Hiero — analytics dashboard</h1>"
        f"<p class='sub'>Generated locally{stamp} · open in any browser · type to filter tables, "
        "click a column header to sort, download any view as CSV, click a chart to enlarge.</p>"
    )

    macro_bar = ""
    if macros:  # macro bar always shows (even at one family), so the scope is labelled
        buttons = "".join(
            f"<button class='macro{' active' if i == 0 else ''}' id='macrobtn-{_slug(macro['name'])}' "
            f"onclick=\"switchMacro('{_slug(macro['name'])}')\">{esc(macro['name'])}</button>"
            for i, macro in enumerate(macros)
        )
        macro_bar = f"<div class='macrobar'>{buttons}</div>"

    macro_panels = []
    for i, macro in enumerate(macros):
        mslug = _slug(macro["name"])
        display = "" if i == 0 else "display:none"
        # The column glossary applies to tables only, so show it inside a macro
        # only when that macro actually has a table section (not chart-only macros).
        has_table = any("charts" not in section for tab in macro["org_tabs"] for section in tab["sections"])
        glossary = _GLOSSARY if has_table else ""
        macro_panels.append(
            f"<div class='macropanel' id='macro-{mslug}' style='{display}'>"
            f"{glossary}{_org_panels_html(mslug, macro['org_tabs'], esc)}</div>"
        )

    # Lightbox overlay (charts expand on click); macro bar is the top-level nav.
    lightbox = (
        "<div id='lightbox' class='lightbox' onclick='closeLightbox()'>"
        "<span class='hint'>click outside or press Esc to close</span>"
        "<img id='lightbox-img' alt='' onclick='event.stopPropagation()'>"
        "<div id='lightbox-note' class='lbcap' onclick='event.stopPropagation()'></div></div>"
    )
    footer = (
        "<footer class='wip'><span class='wipbadge'>Work in progress</span> "
        "This dashboard is under active development. Organisation affiliations are curated and still being "
        "verified — figures are directional and may change. Spotted something wrong? Use a table's "
        "&ldquo;Suggest a correction&rdquo; link.</footer>"
    )
    body = header + macro_bar + "".join(macro_panels) + footer + lightbox
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Hiero analytics dashboard</title><style>{_CSS}</style></head>"
        f"<body>{body}<script>{_JS}</script></body></html>"
    )
