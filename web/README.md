# Hiero analytics — web dashboard

A static Vite + React + TypeScript app that renders the versioned JSON data API
(`outputs/data/api/v1/`). It is manifest-driven: it renders whatever orgs,
sections, chart sections, bespoke views, and metrics the API lists, so adding
analytics on the Python side rarely requires frontend changes.

Three kinds of content arrive from the API. _Sections_ are tables, rendered
generically from their column specs. _Chart sections_ are galleries of
interactive charts, drawn from each variant's JSON dataset, with their notes
and step-by-step methodology. _Views_ are the bespoke cases a table
cannot express — today the HIP coverage matrix and governance board — which the
Python side ships as pure data (`export/hip_views.py`) so the component owns
only the rendering.

## Develop

```bash
uv run hiero-analytics data_api        # re-emit the API from existing outputs
python3 -m http.server 8642 -d outputs # serve data + charts (dev proxy target)
npm run dev                            # the app, on http://localhost:5173
```

`npm run lint` (oxlint), `npm test` (Vitest + Testing Library), and
`npm run build` (tsc + vite) are the CI gates — all three run on every PR.

## Styling conventions

- **UI is built from [shadcn/ui](https://ui.shadcn.com) components** (Radix
  base, Mira style) in `src/components/ui/`, added with
  `npx shadcn@latest add <name>`. Reach for a component before writing
  markup: `Card` for any content card, `Button`, `Badge`, `ToggleGroup` for a
  2–7 option switch, `Collapsible`, `Dialog`, `Table`, `Alert`, `Empty`,
  `Skeleton`. Compose them fully (`CardHeader`/`CardTitle`/…), and use
  `className` for layout, not to restyle a component.
- **Edits to generated components** are allowed but marked `Local change`
  with the reason (e.g. `badge.tsx` has the status tones
  `ok`/`warn`/`neg`/`info`/`neutral`). Preview upstream changes with
  `npx shadcn@latest add <name> --diff` before overwriting one.
- **All colour comes from semantic tokens** in `src/app.css`. Components use
  shadcn's names — `bg-background`, `bg-card`, `text-foreground`,
  `text-muted-foreground`, `border-border`, `bg-primary`, `ring-ring` — plus
  our own where shadcn has no slot (`text-soft`, `text-link`, `text-ok-ink`,
  `bg-chart-ground`, …). shadcn `muted` and `accent` are _backgrounds_
  (secondary text is `text-muted-foreground`). No raw hex values in
  components; a new colour gets a token in `src/app.css`, with its dark
  value.
- **Dark mode is one token flip.** The OS preference is the default;
  `data-theme="light"|"dark"` on `<html>` forces one (`src/theme.ts`, applied
  before first paint by `public/theme-init.js`). Components rarely need
  `dark:` — tokens already flip.
- **Custom CSS is the exception**, only for information design no component
  expresses: the HIP coverage matrix (`.hipmx*`) and governance board lanes
  (`.hipboard*`) in `src/app.css`.
- **Type:** one self-hosted family, Public Sans (the CSP allows fonts from
  `'self'` only, so it ships in the bundle via `@fontsource-variable`). Numbers
  that line up in columns use `tabular-nums`.

## Third-party requests

The CSP in `index.html` keeps everything on `'self'` except images from
`https://avatars.githubusercontent.com` (contributor avatars, `ContributorCell`)
and `https://github.com` (org avatars, `OrgSwitcher`, which redirect to the
avatar host). This is a deliberate trade-off: the pictures make long contributor
tables scannable, but GitHub sees the reader's IP address and which avatars,
and therefore which contributor lists, they load. To keep that exposure small, the
images load lazily (only rows scrolled into view) with
`referrerPolicy="no-referrer"`, so GitHub is not told which page asked. A
failed or blocked image falls back to initials, so a browser or extension that
blocks third-party images loses nothing but the pictures.

If that exposure is no longer acceptable, download the avatars in the pipeline,
serve them from `'self'`, and drop both origins from `img-src`. Don't add any
other origin without the same written reasoning here.

## Adding to the dashboard

- **A new table column** may declare a display format from the set in
  `dashboard_spec.COLUMN_FORMATS`; implement it in `components/FormattedCell`
  and add it there in the same change, or the column renders as plain text.
- **A new chart** needs both a `CHART_NOTES` entry (what it shows) and a
  `CHART_METHODOLOGY` entry (how it was derived) — a spec test enforces both,
  so a chart cannot ship with an empty lightbox.
- **A new bespoke view** returns pure data from a `build_views()` module and
  renders through `SectionCard`, so it inherits the shared card chrome.

## Tests

`src/test/` holds the Vitest suite: `fixtures.ts` is a miniature but
structurally complete data API served through a fetch stub (it doubles as
documentation of the manifest contract), `app.test.tsx` covers tabs, tables
and charts, `shell.test.tsx` the header, sidebar, theme switch and phone
layout, `theme.test.ts` the theme plumbing, `csv.test.ts` the
provenance-stamped export. Query by role and text, not by class name —
styling refactors shouldn't break tests. (A single-select `ToggleGroup` has
`radiogroup`/`radio` roles; cards are labelled `region`s.)
