"""Generate a single self-contained HTML dashboard from the analytics tables.

No server required: open the produced file in any browser. The data is rendered
into static tables, and a small amount of dependency-free vanilla JS adds
per-section search and click-to-sort, so the file works fully offline.
"""

from __future__ import annotations

import html
import json
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
    download = ""
    if dl := section.get("download"):
        download = f'<a class=\'dl\' download="{esc(dl["name"])}" href="{dl["href"]}">Download CSV</a>'
    return (
        f"<section class='card'><h2>{esc(section['title'])}</h2>"
        f"<div class='shead'><p class='desc'>{esc(section['description'])}</p>{download}</div>"
        f"<div class='gallery'>{figures}</div></section>"
    )


# Per-column display formats a section spec may request via a third tuple
# element, e.g. ("hip", "HIP", "hip"). Plain text stays the default; every
# format keeps a stable text token in the cell, so the built-in filter, sort,
# and CSV export keep operating on what the reader sees.
def _format_cell(value: object, fmt: str, esc) -> str:
    text = _fmt(value)
    if not text:
        return "<td></td>"
    if fmt == "hip":
        return f"<td><span class='cell-hip'>HIP-{esc(text)}</span></td>"
    if fmt == "date":
        return f"<td>{esc(text[:10])}</td>"
    if fmt == "link":
        return f'<td><a class="cell-link" href="{esc(text)}" target="_blank" rel="noopener">open &#8599;</a></td>'
    if fmt == "status":
        return f"<td><span class='chip chip-spec'>{esc(text)}</span></td>"
    if fmt == "flag":
        return f"<td>{'&#10003;' if text == 'True' else '&mdash;'}</td>"
    return f"<td>{esc(text)}</td>"


def _table_view_html(
    section_id: str,
    columns: Sequence[Sequence[str]],
    rows: Sequence[Mapping],
    esc,
    *,
    title: str = "",
    data_as_of: str = "",
) -> str:
    """Render one filterable, sortable, exportable table view.

    ``title``/``data_as_of`` and the row total ride along as data attributes so
    the CSV export can stamp them into the downloaded file. The export takes the
    *visible* rows, so a filtered download is a subset — the total is what lets
    the file say so rather than passing itself off as the whole table.

    ``columns`` entries are ``(key, label)`` or ``(key, label, format)``; the
    optional third element selects a display format (see ``_format_cell``).
    """
    specs = [(column[0], column[1], column[2] if len(column) > 2 else "") for column in columns]
    head = "".join(
        f"<th onclick=\"sortTable('{section_id}',{i},this)\">{esc(label)}</th>"
        for i, (_key, label, _fmt_name) in enumerate(specs)
    )
    body = "".join(
        "<tr>" + "".join(_format_cell(row.get(key), fmt, esc) for key, _label, fmt in specs) + "</tr>" for row in rows
    )
    return (
        f"<button class='dl' onclick=\"exportCSV('{section_id}','{section_id}.csv')\">Download CSV</button>"
        f"<input class='search' id='{section_id}-q' placeholder='Filter…' "
        f"oninput=\"filterTable('{section_id}',this.value)\">"
        f"<div class='tablewrap'><table id='{section_id}' data-title=\"{esc(title)}\" "
        f"data-asof=\"{esc(data_as_of)}\" data-total='{len(rows)}'><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        f"<p class='count' id='{section_id}-count'>{len(rows)} rows</p>"
    )


def _asof_html(section: Mapping, esc) -> str:
    """The "data as of" stamp, flagged when older than the refresh cadence."""
    if not section.get("data_as_of"):
        return ""
    suffix = " — older than the scheduled refresh" if section.get("stale") else ""
    stale_cls = " stale" if section.get("stale") else ""
    return f"<span class='asof{stale_cls}'>data as of {esc(section['data_as_of'])}{suffix}</span>"


def _download_html(section: Mapping, esc) -> str:
    """A section's inlined CSV download link, when it declares one."""
    dl = section.get("download")
    if not dl:
        return ""
    return f'<a class=\'dl\' download="{esc(dl["name"])}" href="{dl["href"]}">Download CSV</a>'


def _html_section_html(section: Mapping, esc) -> str:
    """A section whose body is a prebuilt HTML fragment (e.g. the HIP matrix).

    The fragment is produced by the dashboard pipeline from this run's own
    CSVs — trusted content, inlined verbatim inside the standard card chrome.
    """
    asof = _asof_html(section, esc)
    badge = f"<span class='sbadge'>{esc(section['badge'])}</span>" if section.get("badge") else ""
    download = ""
    if dl := section.get("download"):
        download = f'<a class=\'dl\' download="{esc(dl["name"])}" href="{dl["href"]}">Download CSV</a>'
    return (
        f"<details class='card tsec' open>"
        f"<summary class='tsum'><h2>{esc(section['title'])}</h2>{badge}</summary>"
        f"<div class='sbody'>"
        f"<div class='shead'><p class='desc'>{esc(section['description'])}</p>{asof}{download}</div>"
        f"{section['html']}"
        f"</div></details>"
    )


def _section_html(section: Mapping, esc) -> str:
    if "charts" in section:
        return _charts_section_html(section, esc)
    if "html" in section:
        return _html_section_html(section, esc)
    section_id = section["id"]
    variants = section.get("variants")
    row_count = max((len(variant["rows"]) for variant in variants), default=0) if variants else len(section["rows"])
    asof = _asof_html(section, esc)
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
            + _table_view_html(
                f"{section_id}-period-{i}",
                variant["columns"],
                variant["rows"],
                esc,
                # Each period is a different row set, so the export has to name
                # which one it is — "Contributors.csv" alone is ambiguous.
                title=f"{section['title']} — {variant['label']}",
                data_as_of=section.get("data_as_of", ""),
            )
            + "</div>"
            for i, variant in enumerate(variants)
        )
        content = f"<div class='periodtabs'>{tabs}</div>{tables}"
    else:
        content = _table_view_html(
            section_id,
            section["columns"],
            section["rows"],
            esc,
            title=section["title"],
            data_as_of=section.get("data_as_of", ""),
        )
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


def build_dashboard_html(
    macros: Sequence[Mapping],
    *,
    generated_at: str | None = None,
    git_sha: str | None = None,
) -> str:
    """Build a self-contained, two-level (macro → org → section) HTML document.

    ``macros`` is a list of ``{name, org_tabs}``; each macro is a dashboard family
    (e.g. "Contributors & governance") and each ``org_tab`` is
    ``{org, metrics, sections}``. A section is either a table (has ``columns``/
    ``rows``) or a chart gallery (has ``charts``; images expand in a lightbox on
    click). The macro bar always shows (so the family is labelled even with one);
    the org tab bar shows only with more than one org. The column glossary appears
    only inside macros that have a table section. Section ids are namespaced per
    macro+org so filter/sort/export stay independent. All values are HTML-escaped.

    ``git_sha`` stamps the revision that built the page. Each deploy overwrites
    the last and nothing is committed, so without it a reader comparing two
    dashboards cannot tell whether the data moved or the code did.
    """
    esc = html.escape
    stamp = f" · generated {esc(generated_at)}" if generated_at else ""
    stamp += f" · code {esc(git_sha)}" if git_sha else ""
    header = (
        "<h1>Hiero — analytics dashboard</h1>"
        f"<p class='sub'>Generated locally{stamp} · open in any browser · type to filter tables, "
        "click a column header to sort, download any view as CSV, click a chart to enlarge.</p>"
    )

    macro_bar = ""
    if macros:  # macro bar always shows (even at one family), so the scope is labelled
        buttons = "".join(
            f"<a class='macro{' active' if i == 0 else ''}' id='macrobtn-{_slug(macro['name'])}' "
            f"href='#{_slug(macro['name'])}'>{esc(macro['name'])}</a>"
            for i, macro in enumerate(macros)
        )
        macro_bar = f"<div class='macrobar'>{buttons}</div>"

    macro_panels = []
    for i, macro in enumerate(macros):
        mslug = _slug(macro["name"])
        display = "" if i == 0 else "display:none"
        # Each macro gets its own "how to read this" expander: a family may
        # supply tab-specific content (glossary_html); otherwise the shared
        # column glossary shows for macros that actually have a table section.
        has_table = any("charts" not in section for tab in macro["org_tabs"] for section in tab["sections"])
        glossary = macro.get("glossary_html") or (_GLOSSARY if has_table else "")
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
    # Page-level provenance for the CSV export. A downloaded file leaves the
    # dashboard behind entirely, so the stamp has to be written into the file —
    # `json.dumps` rather than string interpolation because these values end up
    # inside a <script> block.
    provenance_js = "var PROVENANCE=" + json.dumps({"generated": generated_at or "", "sha": git_sha or ""}) + ";"
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Hiero analytics dashboard</title><style>{_CSS}</style></head>"
        f"<body>{body}<script>{provenance_js}{_JS}</script></body></html>"
    )
