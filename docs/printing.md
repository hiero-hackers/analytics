# Printing dashboard tabs (issue #356)

## Design and impact

The document is for governance meetings: it must preserve the current organisation,
tab, period and role selections, show where its numbers came from, and never silently
omit data. The implementation reuses the live component tree with a transient print
context and a print stylesheet. This keeps local selection state and formatting in
one place rather than maintaining a second dashboard renderer or a second data API.

A CSS-only solution cannot restore virtualised rows, select chart slides or await
images. A separate route would need a new serialization contract for per-card
periods, roles, sorting and filters. A full PDF-generation library would add a
parallel rendering system. None is necessary for this scope.

The visible **Print tab** action prepares the current tab, waits for chart images
and fonts, and invokes the browser print dialog. Native browser printing also
switches the React tree synchronously through `beforeprint`; print-media changes
are handled for browser automation. Collapsed sections are opened temporarily and
restored after printing. Interactive controls and bespoke scrolling views stay
mounted while hidden, so keyboard focus, matrix/board scroll offsets and selections
survive print/cancel. Pending preparation is cancelled on tab/org navigation, and
image sources are rechecked before the dialog opens. If native printing is invoked
before resources are ready, the document identifies the missing content rather than presenting a blank gap.
The button waits for resources and reports failures without silently printing them.

Tables print the current sorted/filtered rows, without virtualisation. Filtered
output states its filter and full row count. A shared limit of 500 rows per table
bounds document size and rendering cost; larger tables explicitly state how many
rows were omitted and point to the existing CSV download for the complete data.
Selected period and role labels become plain text. Charts include every slideshow
figure in order, use the active variant, load eagerly within the active tab, and
print their selection labels. HIP board and matrix views keep their data when
interactive controls are removed.

Print rules use the existing light palette and 8.5-point table text, normal
page flow, wrapping cells, repeating table headings and bounded chart dimensions.
Generic tables use automatic column sizing with 8–40 mm cell bounds: equal-width
columns wrapped repository names into tall strips while wasting numeric space.
Numeric values stay on one line. The HIP matrix groups its 14 component columns
into labelled merged/open counts; every component remains present.
The stylesheet removes navigation, action controls, scrolling and screen-only overlays. Screen
styles remain scoped separately. No pipeline, CSV, chart or API contract changes
are introduced.

Current Chromium supports `@page` margin boxes with provenance and page counters.
The implementation detects that support rather than assuming every engine has it.
Other engines receive a repeated provenance footer; page numbering depends on their
native print header/footer option. A fixed element's CSS `counter(page)` is not a
valid fallback (it evaluates to zero). Browser differences are documented honestly.

## Local verification (20 September 2026)

- Component tests cover print state, selections, row completeness/capping and errors.
- Playwright runs the real built dashboard with the shared typed API fixtures,
  following the fixture/staging approach discussed in #332. Its suite remains
  separate from Vitest and does not introduce a duplicate CI workflow.
- Browser checks cover native printing, the visible action, print-media emulation,
  light output from dark mode, hidden controls, collapsed content, long employer
  lists, large tables, image failure and restoration after cancel/print.
- Chromium PDFs are inspected for clipping, readable type, every-page provenance,
  page numbering and explicit truncation. Firefox print-media checks exercise the
  engine in which the original blank-page problem was reproduced.
- Representative live-data PDFs and the source chart pixel dimensions are checked
  locally. Generated PDFs are review artifacts, not pipeline output or CI exports.

The checks use Node 24, matching the web CI jobs. The new browser harness has only
development dependencies; the production bundle adds no PDF library. Python,
pipeline definitions, CSV/PNG output paths and the data API remain unchanged.
The web suite passes 78 unit/component tests and 16 Playwright tests in each of
Chromium and Firefox. A clean `npm ci`, lint, Prettier and typecheck/build pass;
lint retains five existing warnings and introduces none. A fresh pre-push run
also passes the full Python suite (802 tests, 95.65% coverage), Ruff lint and Ruff
formatting. The output-contract, data-API and spec-consistency tests are included.

Actual PDFs were generated for all six available macro tabs for both organisations
in Chromium 153 and Firefox 156: 24 distinct engine/tab/org documents. The public
snapshot's data watermark is 2026-09-16 09:05 UTC and its data/code revision is
420dac3. `Community` is an unused manifest ordering entry; it correctly falls back
to Contributors rather than representing a seventh available tab.

- No words outside the horizontal page margins, hidden final columns or blank-page
  runs were found. Table text remained 8.5 points in both engines.
- Chromium repeats data-as-of, git SHA and correct `Page n of N` on every page.
  Firefox repeats provenance on every page using the table-footer fallback. Its
  page numbers require the browser's headers/footers option; the screen explains
  this limitation. WebKit's lack of margin-box support was checked, but Safari's
  native printed output was not verified.
- The largest all-time Ledger reports contain 86 Governance / 91 HIP pages in
  Chromium, and 88 / 93 in Firefox. These are populated pages: the tables include
  500 rows where capped, long strings wrap, and repeated column headers remain
  readable. Page counts vary with browser, paper settings and filters.
- The capped Ledger tables explicitly disclose 258 omitted role rows, 2,149 omitted
  team/repository rows, 963 omitted contributor rows and 344 omitted HIP evidence
  rows in this snapshot. CSV remains available on screen for the complete data.
- Real chart sources provide approximately 212–569 effective DPI at the selected
  print width. Dense source charts still have small labels; scaling a full chart
  to paper cannot increase the label size independently. Their full images are
  preserved and no chart-generation change is required.
- The HIP PDFs retain hyperlinks to the underlying GitHub PRs; the ordinary issue
  link also remains clickable. `Copy link` and CSV buttons are hidden because PDF
  pages do not run the dashboard's click handlers.
- Desktop light mode (1440 px) and narrow dark mode (390 px), period/filter changes,
  native print, image failures/timeouts, print cancellation, keyboard focus and
  horizontal/vertical matrix scrolling were checked. The narrow Governance CSV
  action row has a pre-existing 13 px overflow; this print change does not modify
  those screen styles.

Eager loading is limited to selected chart variants in the active tab, including
hidden slideshow figures. In this snapshot the largest default chart group is
Governance: 10 images totalling 2.23 MiB. The 500-row cap bounds the additional DOM
work, and asset preparation has a 15-second timeout, including the final render
frame. The fallback presentation wrapper and print listeners are removed/cleaned
up with their owning components.

## State-restoration follow-up (21 September 2026)

Persistent scroll containers opt in with `data-scroll-restore` in their component.
The print controller queries that attribute, so adding a scrolling component does
not require adding its CSS class to a central list. Coverage includes tables,
matrices, boards, charts, period tabs, the jump bar and open explanation/evidence
panels. Open panels stay mounted while hidden; their Escape handlers pause during
printing. Methodology expansion, focus and scroll positions therefore survive
print/cancel.

Virtual tables detach their scroll observer during printing while retaining their
screen measurements and offset. This avoids restoring against the shorter printed
table when the reader was scrolled beyond row 500. The previous viewport's rows
beyond that cap stay mounted but hidden, preserving focused links without printing
extra rows or rendering a second table. The empty-filter clear button also stays
mounted while hidden.

Regression checks now cover those cases, including an actual Firefox period-tab
reset reproduced with the old selector. The suite passes 78 unit/component tests
and 20 Playwright tests in each of Chromium and Firefox. The browser suite uses
print-media emulation and dispatched lifecycle events; the button tests observe
`window.print` rather than automate the operating system's print dialog. Chromium
also generates a PDF. Native Firefox PDF evidence is recorded separately above.

Local Chromium timing checks used the real Governance data and ten chart images.
Preparation took 0.26 seconds with charts already loaded. With a fresh browser
context, 6x CPU slowdown, 150 ms network latency and approximately 1.6 Mbps download
throughput, it took 11.45 seconds. At 750 Kbps the 15-second timeout fired, restored
the screen and did not invoke printing. Once the remaining images loaded, a retry
succeeded in 0.57 seconds. These are simulated conditions on this machine, not
measurements from separate slow hardware. Timing starts at the Print tab click,
after the tab's data has loaded; it excludes the initial dashboard load.

The timeout is a bounded wait with an explicit retry path, not a guarantee that
every device or connection finishes within 15 seconds. Safari native printing
remains unverified, and Firefox page numbering still needs its native print setting.

## Port to the interactive dashboard (27 September 2026)

The shadcn/ui dashboard (#490) replaced the PNG galleries with interactive charts
drawn from each variant's JSON dataset, so the print feature was carried over
onto the new components rather than merged line by line. Its behaviour is
unchanged: the live tree is printed under the same transient print context, with
selections stated as text, every table row up to the 500-row cap, and provenance
on every page. What changed is how each piece is implemented:

- **Readiness.** Charts are SVG drawn from JSON, so preparation no longer decodes
  images. A chart still loading (its module or its dataset) carries
  `data-print-pending`; a chart whose dataset failed carries `data-print-error`
  and names itself ("Could not load chart data: <title> (<variant>)"). Print tab
  waits, within the same 15-second bound, until nothing is pending, then refuses
  to print if anything failed. Native printing before that point prints the named
  loading or error notice, never a silent gap.
- **Collapsed content.** Section groups, cards and the tab explainer are Radix
  collapsibles, which unmount closed content. Each holds its open state and is
  forced open while printing; the reader's own collapse returns afterwards. The
  native `<details>` that remain (chart methodology) are still opened and
  restored by the print controller. Group names print as headings.
- **Selections.** Variant, role and period switches are toggle groups. While
  printing they stay mounted but hidden, and a line such as "Time range: 1 month"
  or "Pipeline view: By month" states the choice.
- **Controls on paper.** `print.css` selects data attributes and shadcn
  `data-slot`s, never utility classes. It hides the header, sidebar, dialogs,
  tooltips, inputs and every button except those marked `data-print-keep`: a
  chart's legend doubles as its series switch, and some table rows name
  themselves with a focus button, so those print as text.
- **Slideshows** keep every slide mounted (each keeps its chosen variant) and
  print them all in order; an expanded chart prints in place of its dialog.
- **Light output.** Dark mode is one Tailwind `dark` variant, now scoped to
  `screen`, so paper always gets the light palette.

The component tests were ported to the new roles (toggle items are radios) and
now cover chart readiness through the pending and error markers instead of image
decoding. The Playwright suite was ported to the new DOM with real chart datasets
in its fixtures; avatar requests to GitHub, which the dashboard makes by design
(see `web/README.md`), are answered locally so the suite stays offline.

Two behaviours needed new handling. An open Radix dialog (an expanded chart or a
figure's explanation) ignores Escape and outside clicks while printing, so the
key that dismisses the browser's print dialog cannot also close it; the dialog is
a scroll box and opts in to scroll restore. An expanded chart prints in place
while its dialog keeps its own copy mounted, so its open explanation and scroll
position survive.

Local verification after the port: 167 Vitest tests, and 21 Playwright tests in
each of Chromium and Firefox. Lint, Prettier and the typecheck/build pass; lint
keeps its five existing warnings and adds none. Printed output from real data was
not re-reviewed in this pass.

## Printing one chart (30 September 2026)

Every interactive chart has a **Print** action beside Download CSV and Expand
(icon-only in a narrow card; its accessible name is "Print chart: <title>"). It
opens a print preview rather than the browser dialog, so the reader sees the page
before printing it.

**One renderer.** The preview does not redraw the chart from a copy of its state.
`ChartShell` hands its own view's switches, legend and `chart()` render function
to `ChartPrintDialog`, which lays them out as a sheet of paper. Every selection
already lives in the URL (variant, chart style, scale, span, hidden series,
cohort, search, focus, show-all) or in the view's closure (the network's zoom),
so the sheet shows exactly what the card shows. The views receive the sheet's
chart area as `sheet` and size themselves to it: bars over time take its height,
rankings and timelines fit their rows between a minimum and maximum row height,
heatmaps switch to a fixed-width grid with every column on the page, and the
network graph and adjacency matrix scale into the area.

**The sheet is the printout.** It is drawn at its printed size in millimetres and
only scaled down (CSS transform) on screen, so the measured layout, the chart's
pixel size and the page count in the preview are the ones printed. While the
preview is open, `<html data-print-scope="chart">` and a page rule
(`@page { size: A4|letter portrait|landscape; margin: 12mm }`) are in place, and
print.css prints the sheet alone: the dashboard, overlays and the dialog's own
controls are left out, and the tab's print mode (`PrintProvider`) is skipped. The
browser's own print command prints the same sheet while the preview is open.
Every tab-print rule is scoped to `:where(html:not([data-print-scope='chart']))`,
which adds no specificity, so tab printing cascades as before.

**On the page:** the chart title with its organisation and card, the unit line,
the selection as filters ("Chart style Line", "Hidden series Triage", "Showing
top 10 of 40 repositories", "Search …", "Focus …"), the date range (the buckets
shown for a timeseries; the window's dates otherwise), the legend (series drawn;
switched-off ones are listed among the filters), the chart, the population and
window notes. The source line (data date, code revision), the source's
generated time and the view's URL were dropped from the sheet as clutter; the printed date is optional and off by default.
Reading notes and methodology are optional and off by default, so they do not
take the chart's room. Paper cannot hover, so values are printed on the marks:
stack totals on bars, point values on short lines and areas, the latest value on
long series. Heatmaps keep their cell values; funnels and meters are labelled
already. The sheet always uses the light palette, including in dark mode.

**Paper.** A4 or Letter, remembered per browser (the default follows the
reader's region). Orientation is _Best fit_ unless chosen: each view states its
natural shape (`printAspect`), and the orientation that draws it largest wins.
Wide timeseries print landscape; long rankings, timelines, networks and tall
heatmaps print portrait. A selection that cannot fit one page even at the
minimum row height (every row of a very long ranking) runs onto further pages;
the preview marks the page breaks and says how many pages it needs.

**Download.** The preview also saves the page as a file, without the print
dialog: a PDF (one page per printed page, at the paper's exact size), or a PNG
or JPG of the whole sheet. `chartExport.ts` renders the sheet in the browser at
288 dpi with `modern-screenshot` (loaded only when a file is saved). It lays the
sheet on paper with the print margins, and writes the PDF itself: one
losslessly compressed image per page, using the browser's `CompressionStream`,
with no PDF library. GitHub avatars are left out, because the page's CSP
(`connect-src 'self'`) does not let a script read them; their initials stand in.
The PDF is an image of the page, so its text cannot be selected; Print keeps
the text.

**No browser header or footer.** The browser prints its own date, title and URL
in the page margin. The chart's page rule sets the margin to 0, and the sheet
pads itself by 12 mm instead (`box-decoration-break: clone`, so every printed
page gets it). The browser then has no margin to print them in. Checked in
Chromium with its header and footer option switched on.

**Nothing to print.** If the selection has no data (an empty period, a search
with no match), Print shows "Nothing to print for this selection" with the
chart's own empty-state reason, instead of opening an empty preview. The message
lasts until the selection changes.

The CSS minifier (Lightning CSS) folds `translate: none` into the `transform`
shorthand, which would leave the dialog's centring offset on paper; print.css
resets Tailwind's `--tw-translate-*` variables instead.

### Verification

- Vitest: 12 new tests. They cover paper geometry and orientation, the page
  rule, regional defaults and storage, filter naming, date ranges, the preview's
  filters, legend and notes, printing and restoring the page, and the empty
  message. Also that tab printing is skipped while a chart prints.
- Playwright (Chromium and Firefox): 5 new tests. In Chromium, PDFs are generated
  for A4 and Letter in both orientations and checked for page size and one page.
  The tests also cover the sheet-only print document, a 120-row ranking that
  prints portrait on two pages, the empty-selection message, dark mode, and focus
  and tab printing after the preview closes.
- Real data (hiero-ledger and hiero-hackers): every chart on every tab was
  previewed and printed to PDF in Chromium. That covers bars, stacked bars,
  lines, areas, horizontal rankings, funnel, meter, heatmaps (with and without
  avatars), network graph, adjacency matrix and release timeline. Each fits one
  page, with no content past the sheet's edges, and the preview's page count
  matched the PDF. Filter combinations were also printed: variant, chart style,
  hidden series, latest-24 span, show-all with share scale, network threshold
  and focus, hidden release types, dark mode, A4/Letter portrait/landscape.
  Safari's native print was not verified.
