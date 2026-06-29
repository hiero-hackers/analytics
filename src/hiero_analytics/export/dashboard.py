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

_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:0 auto;padding:24px;color:#1b1b1b;background:#fafafa}
h1{font-size:22px;font-weight:600;margin:0 0 4px}
.sub{color:#666;font-size:14px;margin:0 0 20px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}
.metric{background:#fff;border:1px solid #e6e6e6;border-radius:10px;padding:14px 16px}
.macrobar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.macro{padding:9px 18px;border:1px solid #ddd;background:#fff;border-radius:999px;cursor:pointer;font-size:14px;font-weight:600;color:#444}
.macro.active{background:#1b1b1b;color:#fff;border-color:#1b1b1b}
.macro:hover{border-color:#999}
.tabbar{display:flex;gap:6px;margin-bottom:18px;border-bottom:1px solid #e0e0e0;flex-wrap:wrap}
.tab{padding:8px 16px;border:none;background:none;cursor:pointer;font-size:14px;color:#666;border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.active{color:#1b1b1b;border-bottom-color:#555;font-weight:600}
.tab:hover{color:#1b1b1b}
.metric .label{color:#666;font-size:13px}
.metric .value{font-size:26px;font-weight:600;margin-top:2px}
.card{background:#fff;border:1px solid #e6e6e6;border-radius:12px;padding:16px 18px;margin-bottom:20px}
.card h2{font-size:16px;font-weight:600;margin:0 0 2px}
.shead{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
.dl{flex:none;font-size:12px;padding:5px 11px;border:1px solid #ccc;border-radius:6px;background:#fff;color:#333;cursor:pointer}
.dl:hover{background:#f3f3f3}
.desc{color:#666;font-size:13px;margin:0 0 12px}
.glossary{margin:0 0 18px;border:1px solid #e6e6e6;border-radius:10px;background:#fff;padding:0 14px}
.glossary summary{cursor:pointer;padding:12px 0;font-weight:600;font-size:14px}
.glossary dl{margin:0 0 10px;font-size:13px;display:grid;grid-template-columns:150px 1fr;gap:5px 14px}
.glossary dt{font-weight:600;color:#333}
.glossary dd{margin:0;color:#555}
.gnote{font-size:12px;color:#777;margin:6px 0 12px}
.search{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid #ddd;border-radius:8px;font-size:14px;margin-bottom:12px}
.tablewrap{overflow:auto;max-height:520px;border:1px solid #eee;border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{position:sticky;top:0;background:#f3f3f3;text-align:left;padding:8px 10px;cursor:pointer;white-space:nowrap;border-bottom:1px solid #e0e0e0;font-weight:600}
th:hover{background:#ececec}
td{padding:6px 10px;border-bottom:1px solid #f0f0f0;white-space:nowrap}
tr:hover td{background:#fbfbfb}
.count{color:#888;font-size:12px;margin:8px 0 0}
.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.chart{margin:0}
.chart img{width:100%;height:auto;border:1px solid #eee;border-radius:8px;background:#fff;cursor:zoom-in}
.chart img:hover{border-color:#bbb}
.chart figcaption{font-size:12px;color:#666;margin-top:6px;text-align:center}
.lightbox{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;align-items:center;justify-content:center;z-index:1000;cursor:zoom-out;padding:24px;box-sizing:border-box}
.lightbox img{max-width:96vw;max-height:92vh;border-radius:8px;box-shadow:0 10px 40px rgba(0,0,0,.5);background:#fff}
.lightbox .hint{position:fixed;top:16px;right:20px;color:#ccc;font-size:13px}
.slidenav{display:flex;align-items:center;gap:14px;margin-bottom:10px}
.snav{font-size:13px;padding:6px 14px;border:1px solid #ccc;border-radius:6px;background:#fff;color:#333;cursor:pointer}
.snav:hover{background:#f3f3f3}
.scount{font-size:13px;color:#666}
.slide img{width:100%;height:auto;border:1px solid #eee;border-radius:8px;background:#fff;cursor:zoom-in}
.slide figcaption{font-size:13px;color:#444;margin-top:8px;text-align:center;font-weight:600}
@media (prefers-color-scheme:dark){body{background:#0f0f0f;color:#e6e6e6}.metric,.card{background:#1a1a1a;border-color:#2a2a2a}.metric .label,.sub,.desc,.count{color:#999}th{background:#222;border-color:#333}td{border-color:#222}tr:hover td{background:#1d1d1d}.search{background:#1a1a1a;color:#e6e6e6;border-color:#333}.tablewrap{border-color:#2a2a2a}.dl{background:#1a1a1a;color:#e6e6e6;border-color:#333}.dl:hover{background:#262626}.snav{background:#1a1a1a;color:#e6e6e6;border-color:#333}.snav:hover{background:#262626}.scount,.slide figcaption{color:#bbb}.tabbar{border-color:#2a2a2a}.tab{color:#999}.tab.active{color:#e6e6e6;border-bottom-color:#888}.tab:hover{color:#e6e6e6}.macro{background:#1a1a1a;color:#ccc;border-color:#333}.macro.active{background:#e6e6e6;color:#0f0f0f;border-color:#e6e6e6}.macro:hover{border-color:#666}.glossary{background:#1a1a1a;border-color:#2a2a2a}.glossary dt{color:#ccc}.glossary dd,.gnote{color:#999}.chart img{border-color:#333}.chart figcaption{color:#999}}
"""

_JS = """
function filterTable(id,q){q=q.toLowerCase();var n=0,rows=document.querySelectorAll('#'+id+' tbody tr');rows.forEach(function(tr){var hit=tr.textContent.toLowerCase().indexOf(q)>-1;tr.style.display=hit?'':'none';if(hit)n++;});var c=document.getElementById(id+'-count');if(c)c.textContent=n+' rows';}
function sortTable(id,col,th){var tb=document.querySelector('#'+id+' tbody');var rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));var asc=th.getAttribute('data-dir')!=='asc';th.setAttribute('data-dir',asc?'asc':'desc');var num=/^-?\\d+(?:\\.\\d+)?$/;rows.sort(function(a,b){var x=a.children[col].textContent.trim(),y=b.children[col].textContent.trim();if(num.test(x)&&num.test(y))return asc?x-y:y-x;return asc?x.localeCompare(y):y.localeCompare(x);});rows.forEach(function(r){tb.appendChild(r);});}
function csvCell(s){s=(s==null?'':String(s)).trim();return /[",\\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
function exportCSV(id,name){var out=[];var ths=document.querySelectorAll('#'+id+' thead th');out.push([].map.call(ths,function(th){return csvCell(th.textContent);}).join(','));document.querySelectorAll('#'+id+' tbody tr').forEach(function(tr){if(tr.style.display==='none')return;out.push([].map.call(tr.children,function(td){return csvCell(td.textContent);}).join(','));});var blob=new Blob([out.join('\\n')],{type:'text/csv'});var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();document.body.removeChild(a);URL.revokeObjectURL(a.href);}
function switchMacro(m){document.querySelectorAll('.macropanel').forEach(function(p){p.style.display='none';});document.getElementById('macro-'+m).style.display='';document.querySelectorAll('.macro').forEach(function(b){b.classList.remove('active');});document.getElementById('macrobtn-'+m).classList.add('active');}
function switchTab(m,o){var panel=document.getElementById('macro-'+m);panel.querySelectorAll('.tabpanel').forEach(function(p){p.style.display='none';});document.getElementById('tab-'+m+'-'+o).style.display='';panel.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});document.getElementById('tabbtn-'+m+'-'+o).classList.add('active');}
function openLightbox(src){document.getElementById('lightbox-img').src=src;document.getElementById('lightbox').style.display='flex';}
function closeLightbox(){var lb=document.getElementById('lightbox');lb.style.display='none';document.getElementById('lightbox-img').src='';}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeLightbox();});
function slide(id,dir){var s=document.querySelectorAll('#'+id+'-show .slide');if(!s.length)return;var cur=0;s.forEach(function(f,i){if(f.style.display!=='none')cur=i;});s[cur].style.display='none';var n=(cur+dir+s.length)%s.length;s[n].style.display='';var c=document.getElementById(id+'-counter');if(c)c.textContent=(n+1)+' / '+s.length;}
"""


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


def _slideshow_section_html(section: Mapping, esc) -> str:
    """Render a chart slideshow: one image at a time with Prev/Next navigation."""
    section_id = section["id"]
    slides = "".join(
        f'<figure class="slide" style="{"" if i == 0 else "display:none"}">'
        f'<img src="{chart["src"]}" alt="{esc(chart["title"])}" loading="lazy" '
        f'onclick="openLightbox(this.src)">'
        f"<figcaption>{esc(chart['title'])}</figcaption></figure>"
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
        f"<figcaption>{esc(chart['title'])}</figcaption></figure>"
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
        f"<section class='card'>"
        f"<div class='shead'><h2>{esc(section['title'])}</h2>"
        f"<button class='dl' onclick=\"exportCSV('{section_id}','{section_id}.csv')\">Download CSV</button>"
        f"</div>"
        f"<p class='desc'>{esc(section['description'])}</p>"
        f"<input class='search' placeholder='Filter…' "
        f"oninput=\"filterTable('{section_id}',this.value)\">"
        f"<div class='tablewrap'><table id='{section_id}'><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        f"<p class='count' id='{section_id}-count'>{len(rows)} rows</p></section>"
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
        namespaced = [{**section, "id": f"{mslug}-{oslug}-{section['id']}"} for section in tab["sections"]]
        sections_html = "".join(_section_html(section, esc) for section in namespaced)
        display = "" if i == 0 else "display:none"
        panels.append(
            f"<div class='tabpanel' id='tab-{mslug}-{oslug}' style='{display}'>"
            f"<div class='metrics'>{_metric_cards(tab['metrics'], esc)}</div>"
            f"{sections_html}</div>"
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
