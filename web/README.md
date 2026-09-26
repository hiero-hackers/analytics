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

- **UI is built from [shadcn/ui](https://ui.shadcn.com) components** (Radix
  base, Mira style) in `src/components/ui/`, added with
  `npx shadcn@latest add <name>`. Reach for a component before writing
  markup: `Card` for any content card, `Button`, `Badge`, `ToggleGroup` for a
  2–7 option switch, `Collapsible`, `Dialog`, `Table`, `Alert`, `Empty`,
  `Skeleton`. Compose them fully (`CardHeader`/`CardTitle`/…), and use
  `className` for layout, not to restyle a component.
- **The components are our source now.** Edits to generated files are allowed
  but deliberate and marked `Local change` with the reason (e.g. `table.tsx`
  lets its container be the scroll box; `badge.tsx` has the status tones
  `ok`/`warn`/`neg`/`info`/`neutral`). Preview upstream changes with
  `npx shadcn@latest add <name> --diff` before overwriting one.
- **All colour comes from semantic tokens** in `src/app.css`. Components use
  shadcn's names — `bg-background`, `bg-card`, `text-foreground`,
  `text-muted-foreground`, `border-border`, `bg-primary`, `ring-ring` — plus
  our own where shadcn has no slot (`text-soft`, `text-link`, `text-ok-ink`,
  `bg-chart-ground`, …). Two names mean something different from what the
  old palette used them for: shadcn `muted` and `accent` are _backgrounds_
  (secondary text is `text-muted-foreground`, the active fill is
  `bg-primary`). No raw hex values in components; a genuinely new colour gets
  a token in `src/app.css`, with its dark value, and is used by name.
- **Dark mode is one token flip.** The OS preference is the default;
  `data-theme="light"|"dark"` on `<html>` forces one (the header's theme
  switch, persisted by `src/theme.ts`, applied before first paint by
  `public/theme-init.js`). The `dark:` variant matches exactly those cases,
  but a component should rarely need it — tokens already flip.
- **Tailwind's preflight is on**, so `border` utilities render without
  `border-solid` and every box is `border-box`.
- **Custom CSS is the exception**, allowed only for information design no
  component expresses — today the HIP coverage matrix (`.hipmx*`) and the
  governance board lanes (`.hipboard*`) in `src/app.css`, each commented with
  why it remains. Everything else is utilities on components.
- **Type:** one self-hosted family, Public Sans (the CSP allows fonts from
  `'self'` only, so it ships in the bundle via `@fontsource-variable`). Numbers
  that line up in columns use `tabular-nums`.

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
styling refactors shouldn't break tests. (Radix gives a single-select
`ToggleGroup` `radiogroup`/`radio` roles, and cards are labelled `region`s.)
