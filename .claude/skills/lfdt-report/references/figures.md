# Figures

Hiero's filed reviews carry a few chart images (the 2026 annual review had
two, hosted as GitHub attachments). Of the other 2026 LFDT reviews none had
any, so figures are Hiero house style, not a TAC requirement. Two or three
well-chosen ones make the diversity and activity sections legible; more
turns the report back into a dashboard.

## Which charts

Default set, in this order of priority. Skip any whose document is absent
for the org.

| Figure | Document | Why |
|---|---|---|
| Active contributors by role, per year | `maintainer-pipeline`, `All time` variant (`maintainer_pipeline_yearly`) | The TAC's "did active maintainers rise or fall" question, and the activity trend, in one picture |
| Maintainers by employer | `org-diversity`, "Role-holders by organisation", Maintainers variant (`affiliation_donut`) | Annual Q5 / mid-year Q5. Caption must carry the known-share tile |
| Committers by employer | same card, Committers variant | Only if it tells a different story from the maintainers one |
| Cumulative repository count | `repo-growth`, "Cumulative repo count" | Org size over time; the only trend an ungoverned org has. Monthly since the org began, so the renderer thins the axis to years automatically; pass `--every 12` to force it |
| Repos created per month | `repo-growth`, "New repos per month" | Mid-year only, if the period had notable growth |

Heatmaps, networks, the HIP matrix and the release timeline stay on the
dashboard: they need interaction to read, and a static copy misleads.

## How to render

`scripts/render_figure.py` draws a `timeseries` or `categories` document as
an SVG with the standard library only. Partial buckets are drawn hollow and
starred; a `categories` document is cut at its `top_n` with the tail folded
into "Other (n)".

```bash
python3 .claude/skills/lfdt-report/scripts/render_figure.py \
  "$WORK/hiero-ledger/charts/maintainer_pipeline_yearly.json" \
  "$OUT/figures/active-by-role-yearly.svg" \
  --title "Unique active contributors by role, per year" \
  --subtitle "Each person counted once at their highest role anywhere; bots excluded. Data as of 6 October 2026."
```

Partial buckets are outlined with a dashed border, starred, and carry no
total label; the footer says "outlined, not final".

Open every figure before embedding it (the PNG, or the SVG in a browser).
The axis must be readable and the legend must match the series you kept.
Put the figures in a `figures/` directory beside the draft. Keep the
subtitle to what the document's `population` and `window` say, with a human
date ("Data as of 6 October 2026"); the caption and the source number in
the report carry everything else.

If the maintainer wants the picture to match the dashboard exactly, the
dashboard's print button on any chart card exports a PNG, JPG or PDF of
that chart. Say which card and variant to export.

## How to embed

In the body, directly under the paragraph the figure illustrates:

```markdown
![Active contributors by role, 2018 to 2026](figures/active-by-role-yearly.svg)

*Figure 1. People active each year, counted once at their highest role. The
2026 bar is outlined because the year is not complete.* [3]
```

The alt text says what the picture shows, the caption says how to read it
in one plain sentence, and the bracketed number points to the Sources
appendix like any other figure. No `Source:` line under a figure.

## PNG and PDF companions

The markdown file is what the TAC files. Two companions help it get there:

- **PNG figures**, because GitHub attachments do not accept SVG.
- **A PDF review copy**, for circulating the draft to the TSC and for the
  TAC meeting, where a rendered document with figures reads better than a
  diff.

`scripts/export_report.py` produces both with whatever the machine already
has and adds nothing to the project:

```bash
python3 .claude/skills/lfdt-report/scripts/export_report.py png "$OUT/figures"
python3 .claude/skills/lfdt-report/scripts/export_report.py pdf "$OUT/2027-annual-Hiero.md"
```

`png` uses the first of rsvg-convert, ImageMagick or Inkscape it finds.
`pdf` renders the markdown with the `markdown` package (fetched transiently
through `uv run --with markdown` when it is not installed), swaps the
figure references for the PNGs, and prints with headless Chrome or
Chromium. Each command says plainly which tool is missing when it cannot
run; then tell the maintainer to export the PNGs from the dashboard's
print button and to print the draft to PDF from a browser.

The PDF is a review copy. It is never what gets filed, and its page breaks
and fonts are not worth polishing.

## How the figures get filed

The governance site is MkDocs and the 2026 review embedded images through
GitHub's attachment URLs (`github.com/user-attachments/...`), which are
created by dragging the image into the PR description or a comment. Tell
the maintainer, in the hand-back note:

1. Export each SVG to PNG if GitHub's drag-and-drop does not accept SVG
   (any browser: open the SVG, print or save as image; or use the
   dashboard's PNG export of the same chart).
2. Drag each PNG into the governance PR, copy the `<img ... src=...>` GitHub
   inserts, and replace the `![...](figures/...)` line with it.
3. Alternatively commit the files under the governance repo's
   `tac/project-updates/<year>/` beside the report and keep the relative
   path; check the TAC's preference first.

Never leave a figure line pointing at your scratch directory in the version
that is filed.
