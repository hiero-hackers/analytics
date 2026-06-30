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
# means. Every table uses the same five raw contribution counts.
_GLOSSARY = (
    "<details class='glossary'><summary>How to read this — what each column means</summary>"
    "<dl>"
    "<dt>contributor / account / member / user</dt><dd>a GitHub login.</dd>"
    "<dt>PRs</dt><dd>pull requests this person opened (authored).</dd>"
    "<dt>reviews</dt><dd>pull-request reviews they submitted on any PR.</dd>"
    "<dt>merges</dt><dd>pull requests they merged (clicked &lsquo;merge&rsquo;).</dd>"
    "<dt>issues</dt><dd>issues they opened.</dd>"
    "<dt>labels</dt><dd>label add/remove actions they performed (triage).</dd>"
    "<dt>actions</dt><dd>PRs + reviews + merges + issues + labels, summed &mdash; one activity total. "
    "&ldquo;maint./comm. actions&rdquo; split it by the repo&rsquo;s maintainers / committers / triage.</dd>"
    "<dt>review+merge</dt><dd>reviews submitted + PRs merged, summed &mdash; the &ldquo;shepherding&rdquo; "
    "load. Both committers and maintainers can merge (triage cannot).</dd>"
    "<dt>mergers</dt><dd>how many people (committers + maintainers) reviewed or merged in the repo.</dd>"
    "<dt>top carrier / top % / top role</dt><dd>the person doing the most review+merge in a repo, their "
    "share of it (top-2 % = the top two combined), and whether they are a committer or maintainer.</dd>"
    "<dt>&hellip; 90d</dt><dd>the same count limited to the last 90 days; columns without "
    "&ldquo;90d&rdquo; (incl. &ldquo;all-time&rdquo;) are cumulative.</dd>"
    "<dt>repos</dt><dd>number of distinct repositories they were active in.</dd>"
    "<dt>last active</dt><dd>date of their most recent tracked activity (all-time).</dd>"
    "<dt>status</dt><dd>active = recent activity within the window; quiet = none in it.</dd>"
    "<dt>days since active</dt><dd>days since their most recent activity (all-time; blank = never active).</dd>"
    "<dt>role / role here</dt><dd>governance permission in that repo: triage, committer, or maintainer; "
    "<em>general</em> = holds no special role there.</dd>"
    "<dt>maintainers / committers / triage</dt><dd>as a count column (Repository activity), the number of "
    "people holding that role in the repo.</dd>"
    "<dt>members</dt><dd>the number of people on the team.</dd>"
    "<dt>active / members active</dt><dd>how many of the group (team members, role-holders) had activity in "
    "the window &mdash; vs. the total.</dd>"
    "<dt>highest role</dt><dd>the most senior role a person holds in any repo (maintainer &gt; committer "
    "&gt; triage).</dd>"
    "<dt>roles held</dt><dd>every distinct role the person holds across repos.</dd>"
    "<dt>how roles are set</dt><dd>a person&rsquo;s role in a repo comes from the governance "
    "config&rsquo;s team&rarr;permission grants: <em>triage</em> &rarr; triage, <em>write</em> &rarr; "
    "committer, <em>maintain</em> / <em>admin</em> &rarr; maintainer (<em>read</em> access isn&rsquo;t "
    "counted). Where someone holds more than one, the highest is shown.</dd>"
    "<dt>org-wide teams</dt><dd>a few teams (github-maintainers, security-maintainers, lf-staff, tsc, "
    "hiero-triage) are granted on nearly every repo. To keep each repo&rsquo;s domain maintainers "
    "visible, these are not counted on domain repos; they&rsquo;re credited only on org/meta repos "
    "(e.g. .github, governance) that have no domain maintainer team of their own. So members of those "
    "teams appear on just those few repos.</dd>"
    "</dl>"
    "<p class='gnote'>Contribution counts are all-time, except columns labelled &ldquo;90d&rdquo;, which "
    "cover the last 90 days. Recency thresholds: a repo role-holder shows as &ldquo;quiet&rdquo; after 90 "
    "days with no activity in that repo, and a role-holder or team shows as &ldquo;quiet&rdquo; after 180 "
    "days with no activity anywhere. Tracked activities are opening PRs/issues, reviewing, merging, and "
    "labeling &mdash; comments and reactions are not counted.</p>"
    "</details>"
)


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


def _chart_caption_html(chart: Mapping, esc) -> str:
    """A chart's caption plus, when present, its 'how to read it' note shown inline."""
    caption = f"<figcaption>{esc(chart['title'])}</figcaption>"
    note = chart.get("note")
    if not note:
        return caption
    return f"{caption}<p class='chartnote'>{esc(note)}</p>"


def _slideshow_section_html(section: Mapping, esc) -> str:
    """Render a chart slideshow: one image at a time with Prev/Next navigation."""
    section_id = section["id"]
    slides = "".join(
        f'<figure class="slide" style="{"" if i == 0 else "display:none"}">'
        f'<img src="{chart["src"]}" alt="{esc(chart["title"])}" loading="lazy" '
        f'onclick="openLightbox(this.src)">'
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


def _charts_section_html(section: Mapping, esc) -> str:
    """Render an image section: a slideshow if flagged, else a gallery grid."""
    if section.get("slideshow"):
        return _slideshow_section_html(section, esc)
    figures = "".join(
        f'<figure class="chart"><img src="{chart["src"]}" alt="{esc(chart["title"])}" loading="lazy" '
        f'onclick="openLightbox(this.src)">'
        f"{_chart_caption_html(chart, esc)}</figure>"
        for chart in section["charts"]
    )
    return (
        f"<section class='card'><h2>{esc(section['title'])}</h2>"
        f"<p class='desc'>{esc(section['description'])}</p>"
        f"<div class='gallery'>{figures}</div></section>"
    )


def _section_html(section: Mapping, esc) -> str:
    if "charts" in section:
        return _charts_section_html(section, esc)
    section_id = section["id"]
    columns: Sequence[tuple[str, str]] = section["columns"]
    rows: Sequence[Mapping] = section["rows"]

    head = "".join(
        f'<th onclick="sortTable(\'{section_id}\',{i},this)">{esc(label)}</th>'
        for i, (_key, label) in enumerate(columns)
    )
    body = "".join(
        "<tr>" + "".join(f"<td>{esc(_fmt(row.get(key)))}</td>" for key, _label in columns) + "</tr>"
        for row in rows
    )
    return (
        f"<details class='card tsec' open>"
        f"<summary class='tsum'><h2>{esc(section['title'])}</h2>"
        f"<span class='sbadge'>{len(rows)} rows</span></summary>"
        f"<div class='sbody'>"
        f"<div class='shead'><p class='desc'>{esc(section['description'])}</p>"
        f"<button class='dl' onclick=\"exportCSV('{section_id}','{section_id}.csv')\">Download CSV</button>"
        f"</div>"
        f"<input class='search' placeholder='Filter…' "
        f"oninput=\"filterTable('{section_id}',this.value)\">"
        f"<div class='tablewrap'><table id='{section_id}'><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        f"<p class='count' id='{section_id}-count'>{len(rows)} rows</p>"
        f"</div></details>"
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "org"


def _metric_cards(metrics: Sequence[tuple[str, object]], esc) -> str:
    return "".join(
        f"<div class='metric'><div class='label'>{esc(label)}</div>"
        f"<div class='value'>{esc(_fmt(value))}</div></div>"
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

        # Jump bar: a link per group, plus expand/collapse-all when there are tables.
        links = "".join(
            f"<a class='jbtn' href='#grp-{mslug}-{oslug}-{_slug(g)}'>{esc(g)}</a>" for g, _ in groups
        )
        has_tables = any("charts" not in s for s in namespaced)
        toggle = (
            f"<button class='jbtn jtoggle' onclick=\"toggleAll('{panel_id}')\">Collapse all</button>"
            if has_tables else ""
        )
        jumpbar = (
            f"<div class='jump'><span class='jlabel'>Jump to</span>{links}{toggle}</div>"
            if len(groups) > 1 else ""
        )

        # Each group: a heading anchor followed by its sections (tables collapsed).
        # With only one group (e.g. a chart-only macro) the heading is redundant.
        show_headers = len(groups) > 1
        blocks = "".join(
            (f"<h2 class='grouphdr' id='grp-{mslug}-{oslug}-{_slug(g)}'>{esc(g)}</h2>" if show_headers else "")
            + "".join(_section_html(s, esc) for s in secs)
            for g, secs in groups
        )

        display = "" if i == 0 else "display:none"
        panels.append(
            f"<div class='tabpanel' id='{panel_id}' style='{display}'>"
            f"<div class='metrics'>{_metric_cards(tab['metrics'], esc)}</div>"
            f"{jumpbar}{blocks}</div>"
        )
    return tab_bar + "".join(panels)


def build_dashboard_html(macros: Sequence[Mapping]) -> str:
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
    header = (
        "<h1>Hiero — analytics dashboard</h1>"
        "<p class='sub'>Generated locally · open in any browser · type to filter tables, "
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
        has_table = any(
            "charts" not in section for tab in macro["org_tabs"] for section in tab["sections"]
        )
        glossary = _GLOSSARY if has_table else ""
        macro_panels.append(
            f"<div class='macropanel' id='macro-{mslug}' style='{display}'>"
            f"{glossary}{_org_panels_html(mslug, macro['org_tabs'], esc)}</div>"
        )

    # Lightbox overlay (charts expand on click); macro bar is the top-level nav.
    lightbox = (
        "<div id='lightbox' class='lightbox' onclick='closeLightbox()'>"
        "<span class='hint'>click anywhere or press Esc to close</span>"
        "<img id='lightbox-img' alt=''></div>"
    )
    body = header + macro_bar + "".join(macro_panels) + lightbox
    return (
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Hiero analytics dashboard</title><style>{_CSS}</style></head>"
        f"<body>{body}<script>{_JS}</script></body></html>"
    )
