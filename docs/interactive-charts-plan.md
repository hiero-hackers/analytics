# Interactive chart migration

## Recommendation

Use shadcn chart components with Recharts for bars, lines, areas, and small composition charts. Keep Python responsible for metric definitions and aggregation. Publish chart datasets through the existing static JSON API; React handles presentation and interaction. The dashboard can continue to deploy as a static site.

This document is the implementation plan and its progress record.

**Status:** Steps 1–4 are implemented. 37 chart variants per organisation have interactive versions (listed under steps 2 and 3). Each switches from PNG to interactive once its CSV exists in the output directory. Connected exploration (step 4) links them: a dashboard-wide focus, chart state in shareable URLs, and previous-period comparisons. What remains is the few charts listed under "Still PNG" and the event-level work described at the end of step 4.

## Reference direction

LFX Insights provides useful patterns: project/repository scope, time filters, focused metric pages, contributor and organization rankings, and explanations of what a metric measures.

Sources reviewed:

- [LFX Kubernetes overview](https://insights.linuxfoundation.org/project/k8s)
- [LFX contributor metrics](https://insights.linuxfoundation.org/docs/metrics/contributors/index.html)
- [LFX repository groups](https://insights.linuxfoundation.org/docs/features/repository-groups/index.html)
- [shadcn chart documentation](https://ui.shadcn.com/docs/components/radix/chart)

For Hiero, use compact headers, consistent chart heights, quiet gridlines, readable axes, and a stable color for each role or activity across pages. Put the period and scope beside the title. Show exact values on hover and keyboard focus. Keep methodology and freshness available in the card.

A proposed page structure:

1. Organization and supported period controls.
2. Headline metrics that explicitly state their scope.
3. A main trend chart with a companion ranking or composition chart.
4. Contributor ranking with avatars, sortable activity counts, and search.
5. Heatmap and network exploration deeper in the page.

Repository filters should only affect charts whose datasets support that dimension. Snapshot metrics must remain explicitly labelled as snapshots.

## What the repository has today

- `web/src/components/ChartSectionCard.tsx` renders a variant with `InteractiveChart` when it has an `interactive` reference, and as a PNG otherwise. `InteractiveChart` loads the document and picks a view in `components/charts/` (`SeriesView`, `MatrixView`, `NetworkView`, `EventsView`); all share `ChartShell` (Chart / Data, CSV, expanded dialog, footer). It is lazy-loaded; with Recharts it is a separate 120 kB (gzipped) chunk.
- `web/src/api.ts` describes image variants plus the `ChartDocument` type (`TimeseriesDocument` | `CategoriesDocument`). `web/src/chartData.ts` validates and caches documents.
- `src/hiero_analytics/export/chart_data.py` builds chart documents from CSVs. Dashboard specs declare them through `interactive_sources`, keyed by the PNG filename; shared series, colours and counting rules live in `dashboard_spec/interactive.py`. `_org_chart_sections` publishes a variant when either its PNG or its dataset exists.
- Recharts and `components/ui/chart.tsx` are installed. Role colours are the `--chart-general|triage|committer|maintainer` tokens in `app.css`; neutral series use `--chart-1`…`--chart-5`. All have dark-mode values. Domain palettes (difficulty, employers) reuse the PNGs' hex colours.
- Existing chart notes, methodology, share links, period tabs, CSV exports, and provenance remain part of the experience.

Local dataset inventory (`outputs/data/org/hiero-ledger`, generated 2026-09-07; its PNGs are newer, from 2026-09-26):

| Dataset | Local state | Presentation |
| --- | --- | --- |
| `maintainer_pipeline_{yearly,monthly,weekly,daily}.csv` | Present | Stacked bars per period (done) |
| `maintainer_pipeline_by_repo{,_365d,_30d,_7d}.csv` | Only the all-time file | Ranked horizontal stacked bars (done) |
| `affiliation_distribution{,_committers}.csv` | Maintainers only | Ranked employer bars (done) |
| `repo_affiliation_composition{,_committers}.csv`, `team_affiliation_composition.csv` | Committer file missing | 100% horizontal bars with a 50% line (done) |
| `hip_adoption_funnel.csv` | Present, 8 rows across cohorts | Stage bars with cohort selection (done) |
| `hip_repo_engagement.csv` | Present, 39 rows | Ranked horizontal bars (done) |
| `difficulty_by_repo{,_365d,_30d,_7d}.csv` | Missing (only stale `_30_days` names) | Ranked stacked bars (done) |
| `difficulty_over_time{_all,}_event_based_weekly.csv` | Labelled file only | Stacked area of point-in-time counts (done) |
| `repo_growth_timeline.csv` | Missing | Monthly bars and cumulative line (done) |
| `org_scorecard.csv` | Missing; the scorecard pipeline now saves it | Ranked score bars (done) |
| `{contributor,team,org,repo}_activity_heatmap.csv` | Present | Heatmap grid (done) |
| `{maintainer,committer,triage,all}_network_{nodes,edges}.csv` | Missing; the pipelines now save them | SVG network with the PNG's layout (done) |
| `release_timeline.csv` | Missing | Release scatter per window (done) |
| `org_scorecard_checks.csv` | Missing; the scorecard pipeline now saves it | Checks matrix (done) |

Missing files only mean the local output is stale. The contract test runs every pipeline on fixture data and checks that every declared interactive variant with data publishes. Re-run the pipelines before judging the dashboard from this directory.

## Data flow

Python analysis → persisted CSV → validated chart JSON → React chart component.

`export/chart_data.py` holds the dataset adapters. Chart sources are declared explicitly in the dashboard specifications (`interactive_sources`). Avoid guessing a CSV name from a PNG filename. Multiple charts can share a dataset; variants can use distinct datasets.

Per-chart documents are published under `data/api/v1/<org>/charts/`, named after the PNG they replace (two repo-growth charts share one CSV). Chart variants carry an optional `interactive` reference and keep their image field during migration. `image_available: false` marks a variant that has data but no PNG. v1 stays additive; a later version can remove the image requirement entirely.

The published reference:

```json
{
  "label": "1 year",
  "file": "charts/org/hiero-ledger/maintainer_pipeline_monthly.png",
  "interactive": {
    "kind": "timeseries",
    "path": "hiero-ledger/charts/maintainer_pipeline_monthly.json"
  },
  "image_available": true
}
```

Every document shares the metadata fields (`id`, `metric`, `unit`, `population`, `dimensions`, `window`, freshness). `kind` selects the shape:

- `timeseries`: rows are calendar buckets (`year`, `month`, ISO `week`, `day`), completed up to the source's generation time. Flow series fill empty buckets with zero; stock series (`"fill": "carry"`, e.g. a cumulative total) hold their level. `snapshot` frequency is for point-in-time counts on their own dates, which are never gap-filled.
- `categories`: rows are repositories, employers, stages and so on, in the analysis's order. An optional `group` (e.g. the funnel cohort) splits rows; the reader picks one value and values are never combined.
- `matrix`: a heatmap: rows × columns (months, checks) on an explicit linear `scale`, with an optional per-row `total` and `sublabel`. `missing` names what a null cell means (Scorecard's -1 and unreported checks become null, never zero).
- `network`: `nodes` (repository, active and total members, category, and the PNG layout's `x`/`y`) and `edges` (shared members), read from a nodes CSV plus `edges_file`.
- `events`: individual timestamped events (releases) in a trailing window, with a `type` (release / prerelease) and the row order (busiest first).

For the two series kinds, drawing is declared, not coded: `mark` (`bar` | `line` | `area`), `stacked`, `normalize` (draw shares of each row's visible total; the table keeps counts), `orientation`, `rank` (re-rank by the visible series), `top_n` (rows before "Show all"), `reference` (e.g. a 50% line), and `details` (values shown in the tooltip and table but not drawn). A source can supply its own `note` when the PNG's note does not describe the interactive view. Examples: the PNG pools small repositories and the interactive chart does not, and the pie shows the top 2 employers while the bars rank them all. The counting rule travels separately as `population`, so no chart note can replace it.

Implemented dataset fields: `schema_version`, `id`, `kind`, `org`, `source`, `metric`, `unit`, `population`, `dimensions`, `category`, `series` (with colours), `details`, `rows`, `window`, and the drawing fields above. Time series also carry `frequency`, `timezone`, and a per-row `partial` flag. `window.kind` is `calendar`, `trailing` (with `days`), `all`, or `snapshot`, so snapshot metrics are labelled as snapshots. `note`, `methodology`, `generated_at`, and `stale` are added when available. Still open from the list below: a separate `data_as_of` (how far the data reaches, as opposed to when it was generated) and declared filters beyond `dimensions`.

The full dataset contract includes:

- Stable ID, schema version, organization, metric, unit, and series definitions.
- Rows with numeric values and canonical dates.
- Explicit window start/end, timezone, bucket size, and partial-bucket status.
- `data_as_of`, source generation timestamp, source artifact, methodology, and population definition.
- Supported dimensions and filters, so the UI cannot imply unavailable filtering.

Use the existing chart aggregation and calendar helpers for parity. Extend them where needed to share transformation logic between PNG and JSON generation. Validate required columns, finite numbers, ordering, and supported series. Load chart data on demand and cache repeated requests.

## First implementation: role activity over time

Use `maintainer_pipeline_monthly.csv`, whose columns are:

```text
month, general_user, triage, committer, maintainer
```

Example actual source row, September 2026 (partial month):

```json
{"month":"2026-09","general_user":23,"triage":3,"committer":35,"maintainer":38}
```

Implemented first as `RoleActivityChart.tsx`, now folded into the generic `InteractiveChart.tsx`. It uses `ChartContainer` and a Recharts `ComposedChart` with `CartesianGrid`, both axes, and bar/line/area series sharing a stack ID when stacked. The tooltip is custom so it can show shares, totals and details together. Set an explicit responsive height. Use CSS variables compatible with the app's existing `data-theme` handling.

The card should provide:

- Existing period choices mapped to daily/weekly/monthly/yearly data.
- Exact per-role and total counts in the tooltip.
- Legend buttons to show or hide a role, with pressed state accessible to assistive technology.
- A Chart / Data toggle; both views and CSV export use the same selected dataset.
- An expanded interactive view in the existing dialog.
- Clear treatment of partial periods, missing data, zero activity, and loading failures.

These counts are unique people within each bucket, classified by their highest role. They cannot be summed across months or repositories to produce an organization-wide distinct-contributor total. Preserve the existing bot and activity-type rules.

## Delivery sequence

### 1. One complete chart — done

- Add shadcn chart primitives and Recharts; review generated changes against local tokens and utilities.
- Build the typed chart data contract, monthly/yearly/daily/weekly adapters, and optional manifest references.
- Render role activity end to end, including the data view, selected-data CSV, tooltip, legend, and expanded view.
- Publish interactive variants when their datasets exist, independently of image availability.
- Retain an explicit image fallback for older bundles and unmigrated charts.

### 2. Standard charts — done

Interactive now, all declared in the dashboard specs:

- Maintainer pipeline by repository: all four spans; top 10, re-ranked when roles are hidden.
- Role-holders by organisation (maintainers, committers): ranked employer bars in place of the top-2 pie.
- Organisation mix by repo (maintainers, committers) and by team: 100% bars in the analysis's concentration order, with the 50% majority line.
- HIP adoption funnel, with a cohort switch that defaults to the recent cohort and shows share of proposed as a detail; HIP repository engagement, with matched and total PRs as details.
- Issue difficulty by repo (all four spans) and over time (all issues, labelled).
- Repository growth: new repositories per month as bars, cumulative count as a line.
- OpenSSF scorecard: aggregate score per repository. The scorecard pipeline now saves `org_scorecard.csv`.

Still PNG:

- Single-employer teams/repos by org, and HIP activity by status: their plotted frames are computed in the pipeline and never saved. Each needs a CSV first.
- Code-owner and runner summaries, and the Contributors-tab overview charts, which were not inventoried in this step.

Prefer bars for discrete monthly additions and lines for cumulative totals. Keep funnel cohorts separate and denominators explicit. Avoid arbitrary smoothed curves that imply intermediate measurements.

### 3. Specialized charts — done

- Heatmaps (by contributor, team, organisation, repository; plus hiero-hackers): an ARIA grid in the coverage matrix's idiom. One tab stop with arrow-key movement, a live readout of the focused or hovered cell, row search, GitHub avatars and highest role, the top 25 with "Show all", and a legend giving each shade's range. The theme `--heat-*` ramp inverts in dark mode. The footer states that the value is a weighted score, gives the weights, and says the current month is excluded. The PNG notes' "greener/redder" wording, which the YlGnBu map never matched, now says "darker blue".
- Scorecard breakdown: now a repository × check matrix on a fixed 0–10 scale, with a "Not scored" state, instead of stacked bars that implied the checks add up to the aggregate score. The pipeline saves `org_scorecard_checks.csv`, leaving unreported checks blank rather than zero-filling them.
- Networks (maintainer, committer, triage, all contributors): `plotting/network.py` exposes `network_layout`, which the PNG renderer and `network_tables` both use, so the saved node positions are the PNG's. The largest graph is 42 nodes and 466 edges, so the renderer is plain SVG with no graph library. It offers search, selection that highlights neighbours, a neighbour list with shared counts, focusable nodes (Enter to select, Escape to clear), zoom buttons, Ctrl/⌘+wheel zoom and drag-to-pan. The data view and CSV list each repository with its links.
- Release timeline (18 months, 1 year, 1 month, week): a scatter of publication time against repository, busiest first with per-repository counts, and prereleases as diamonds that can be toggled. The data view lists releases newest first.

### 4. Connected exploration — done

**Scope filter and chart-to-table filtering: the dashboard focus.** One focus, held in the URL as `focus=<dimension>:<value>` (`repo`, `contributor`, `organisation` or `team`; `web/src/focus.ts`).

- Setting it: click a bar in a categories chart, use a row's focus button in a heatmap or a chart's data view, select a network node (selection *is* the focus), or click a release.
- Effect on tables: every section table with a column for that dimension filters to it. It says "Filtered to … n of m rows", its CSV preamble reports "n of m", and it offers Clear focus. Tables without the column are unchanged.
- Effect on charts: charts with that dimension highlight it. Other bars dim, the focused heatmap row is pinned first, the network selects the node, and release marks dim. A focused row beyond the top N is still drawn.
- Honest limits: a chart without the dimension (every time series, for instance) says it shows the whole organisation and that the focus does not apply. A chart that has the dimension but not the value says so too.
- A focus bar at the top of the tab states the focus and clears it. Changing organisation clears it.
- Values are normalised (repository `owner/` prefixes dropped, case ignored) so charts and tables agree. The exporter names dimensions in the same vocabulary (`contributor name` → `contributor`).

**Shareable URL state.** `web/src/urlState.ts` makes the hash a small store.

- Tab and org changes push history entries as before.
- View state rewrites the current entry, so typing a search does not flood Back: the card's variant tabs and slide, each chart's Chart / Data, hidden series, cohort, search and "Show all", and the focus.
- Values equal to their default are removed. "Copy link" therefore reproduces what is on screen, and a fresh page opened from it restores the same view.
- A link naming a cohort the document no longer has falls back to the default.

**Previous-period comparisons.** Only for calendar time series. The exporter adds `comparison: {current, previous}`, naming the last complete bucket and the one before it, and never the partial current bucket. The chart shows each visible series' value, absolute change, and percentage change when the earlier value is non-zero.

There is no comparison for:

- snapshot series (irregular point-in-time dates),
- trailing-window rankings (no earlier window is exported),
- matrices, networks and timelines.

A source can opt out with `"compare": False`.

**Not done, deliberately.** There is no arbitrary date-range filtering: distinct-contributor counts for an arbitrary range need event-level aggregation, and the exported fixed-window totals cannot be re-cut or summed to produce them. Two focus limits also remain:

- The focus does not narrow the time series, because a per-repository monthly breakdown is not exported.
- Section tables do not yet *set* the focus.

## Completion checks

- Assert source-to-JSON parity, including role classification, zero buckets, date order, partial buckets, and cohort selection.
- Verify changing a period updates chart, table, download, and explanatory text together.
- Verify keyboard tooltips, legend controls, focus restoration, and a readable data alternative.
- Check mobile widths, long labels, light/dark themes, and reduced motion.
- Keep stable section IDs and existing share links.
- Measure bundle size and lazy-load the chart renderer; virtualize large supporting tables.
- Check missing/failed datasets and compatibility with older image-only manifests.

The first deliverable should be the role-activity chart and its matching data view. This establishes the reusable data contract and interaction design before converting the remaining catalog.
