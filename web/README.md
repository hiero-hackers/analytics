# Hiero analytics — web dashboard

A static Vite + React + TypeScript app that renders the versioned JSON data API
(`outputs/data/api/v1/`). It is manifest-driven: it renders whatever orgs,
sections, chart sections, bespoke views, and metrics the API lists, so adding
analytics on the Python side rarely requires frontend changes.

Three kinds of content arrive from the API. _Sections_ are tables, rendered
generically from their column specs. _Chart sections_ are PNG galleries with
their notes and step-by-step methodology. _Views_ are the bespoke cases a table
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

- **Tailwind v4 utilities, composed from the semantic tokens** declared in
  `src/app.css` (`bg-surface`, `text-muted`, `border-edge`, `text-ink`,
  `bg-page`, `bg-raise`, `text-soft`, `bg-accent`, …). The tokens flip for
  dark mode automatically — never write per-component dark colors when a
  token exists.
- **No raw hex values in components.** If a design genuinely needs a new
  color, add a token to the palette in `src/app.css` and use it by name.
- **Border utilities need `border-solid`** — Tailwind's preflight reset is
  deliberately not imported (the layout predates it), so border-width
  utilities alone won't render.
- The `@layer components` classes in `src/app.css` are the pre-Tailwind
  vocabulary (`.card`, `.tsec`, `.lightbox`, …). They are being migrated to
  utilities opportunistically; don't add new ones.

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
documentation of the manifest contract), `app.test.tsx` covers the app shell
and table/chart behavior, `csv.test.ts` covers the provenance-stamped export.
Query by role and text, not by class name — styling refactors shouldn't break
tests.
