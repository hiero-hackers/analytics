---
name: lfdt-report
description: Draft Hiero's LF Decentralized Trust TAC report (annual review or mid-year update) from this repo's published data API. Data-backed sections get real, cited numbers in the register of the filed reviews; judgment sections become marked maintainer slots pre-filled with the evidence and the prior report's goals; a Data notes and gaps appendix lists what the TAC asks for that the API cannot yet supply. Ships scripts to fetch and inventory the API, derive period figures, render figures, lint the draft and export PNG and PDF. Use whenever asked to write, draft, refresh, or prepare the LFDT / TAC annual review or mid-year report for hiero-ledger or any other org in the manifest.
---

# Drafting the LFDT TAC report

Hiero files two reports a year with the LFDT Technical Advisory Council (TAC):
an annual review and a mid-year update. Part of each is measurable (activity,
diversity, releases, security posture) and part is judgment (goals, help
needed, lifecycle recommendation). This skill fills the measurable part from
the data API with cited numbers, leaves the judgment part as marked slots that
already carry their evidence, and lists everything the TAC wants that the API
cannot supply.

The bar is **TAC-ready**: a maintainer fills the slots in under an hour and
opens the PR against `lf-decentralized-trust/governance` without rewriting
anything else. The reader is a TAC member with twenty minutes, not an analyst.
The gap list is as much the product as the draft: it is the input for
analytics issues (issue 439 calls the skill "the instrument that discovers
what the API layer is missing").

This skill is documentation plus small standard-library scripts under
`scripts/`. It never changes code, pipelines or the API contract. A gap is
reported, not fixed.

## 1. Settle the inputs

- **Report type:** `annual` or `mid-year`. If the request does not say, ask;
  the two have different questions, periods and templates
  (`references/report-structure.md`).
- **Org:** default `hiero-ledger`. Any org in the manifest works. Only LFDT
  projects file a TAC report; for any other org (e.g. `hiero-hackers`) the
  draft is a coverage exercise in the TAC's shape, and its header says it is
  not for filing.
- **Period:** annual covers the previous calendar year and is filed early in
  the new one; mid-year covers the six months since the annual. Write the
  period as months in the header. `YYYY` in the file name is the filing
  year. An org younger than the period starts at its first month. If the
  data stops before the period ends, every bucket in it is `partial`: the
  one-line header ends with "draft against data to <date>; re-run after
  <period end>", the hand-back opens with the same words, partial buckets
  are cited only as lower bounds, and whole-year comparisons use the two
  complete years before the period.
- **Prior report:** fetch it. Reports live at
  `https://raw.githubusercontent.com/lf-decentralized-trust/governance/main/tac/project-updates/<year>/<file>.md`
  (`YYYY-annual-Hiero.md`, `YYYY-MidYear-Hiero.md`; the prior annual is in
  `<filing year - 1>/`, the annual a mid-year answers to is in `<filing
  year>/`; list the directory with the GitHub contents API if unsure). Its
  forward-looking goals table feeds the goals slot. If there is none (first
  report, or a non-project org) say "no prior report"; never guess names or
  paraphrase goals from memory.

## 2. Read the TAC instructions again, every run

Fetch both pages; they define the questions and they change (mid-year
reports became mandatory in 2026):

- Annual: <https://lf-decentralized-trust.github.io/governance/project-updates/annual-review-instructions/>
- Mid-year: <https://lf-decentralized-trust.github.io/governance/project-updates/mid-year-update-instructions/>

`references/report-structure.md` holds a snapshot of both plus the templates.
If a live page differs, the live page wins and the appendix says what
changed. If the fetch fails, use the snapshot and say so in the appendix.

## 3. Fetch and inventory the data. Never assume it.

The API is static JSON on GitHub Pages: no auth, no queries. Work in a
scratch directory, never in the repo:

```bash
export WORK=${WORK:-$(mktemp -d)}
S=.claude/skills/lfdt-report/scripts
python3 $S/inventory.py fetch hiero-ledger            # manifest + every document; fails loudly
python3 $S/inventory.py show  hiero-ledger > "$WORK/inventory.md"
```

Read the inventory, not the raw manifest. It lists every macro (present or
absent, with the absence note), every section with its all-time and
per-period row counts, every chart card with variant → document id → kind,
frequency, window, partial buckets and comparison pair, the views, the
tiles and the entity counts. `references/api-section-map.md` says which of
them answers which TAC question and sets out the reading rules: ids live at
three levels and tiles have none; `row_count` is the all-time table and the
`7d`/`30d`/`365d` tables differ; variants are matched by `frequency`, not
label; zero rows is a measured "none" for finding-type sections and a gap
for population sections; absent-macro notes are global strings that can
contradict the org's own manifest; the entity index counts repos with
activity, the tables count every repo.

If the org is not in the manifest, stop and list the orgs that are. If
`fetch` fails, say so and do not draft from memory or a stale copy.

## 4. Read the definitions, then derive with `derive.py`

For every document you cite, read its `note`, `methodology`, `population`,
`window`, `stale` and `generated_at` first (a variant's note may sit on the
manifest card rather than in the document; read both). Those are the only
reliable statement of who was counted. If `stale` is true, say so beside the
number. `references/data-quirks.md` lists the traps (two meanings of
"adoption", unknown versus independent, the bot name rule) and the documents
that disagree with each other; check each one every run.

Do not recompute what a tile, section or chart already states. Where a
figure for the period must be derived, use the script and paste its
`Derived:` line into the Data notes appendix:

```bash
python3 $S/derive.py releases  "$WORK/hiero-ledger/charts/release_timeline.json" --from 2026-01 --to 2026-09
python3 $S/derive.py months    "$WORK/hiero-ledger/charts/maintainer_pipeline_monthly.json" --from 2026-01 --to 2026-09 --compare 2025-11,2025-12
python3 $S/derive.py period    "$WORK/hiero-ledger/understaffed.json" --period 365d
python3 $S/derive.py hips      "$WORK/hiero-ledger/hip-evidence.json" --funnel "$WORK/hiero-ledger/charts/hip_adoption_funnel.json" --board "$WORK/hiero-ledger/hip-board.json"
python3 $S/derive.py single-employer "$WORK/hiero-ledger/repodiversity.json"
```

Time series rules: a `partial` bucket is never compared with a complete one
and is cited only as a lower bound; the document's `comparison` pair is two
adjacent buckets, never "since the last report"; the six-month or
year-to-date view comes from `derive.py months`, naming the months; monthly
distinct counts are never summed to get people; a like-for-like month from
a trailing window (the 18-month release timeline) counts only if the whole
month lies inside the window, and `derive.py releases` warns when it does
not. Heatmaps hold every row
(`top_n` is a display cut) and cover the last six complete months. Role
counts add only in org-wide documents (tiles, affiliations, the
active-by-role series), never across per-repo or per-team rows.

## 5. Write the draft

Follow the template for the report type in `references/report-structure.md`
and the register of the filed reviews (`references/example.md`). Rules:

1. **Body prose, not a dashboard dump, and not a summary either.** Aim for
   the filed review's shape: about 2,500 words of body in 25 to 35
   paragraphs of three to five sentences, each data section carrying two or
   three paragraphs that say what happened and what it means for the TAC's
   question. No section, chart, tile or column identifiers, no field names,
   no "derived by this draft", no remarks about how the API is structured:
   all of that belongs in the appendices. Human dates in prose ("6 October
   2026"). The linter warns when the body falls under 70% of that length.
2. **Cite with inline links and numbered sources.** Link the number or
   phrase to the dashboard card
   (`https://hiero-hackers.github.io/analytics/#tab=<Macro>&org=<org>&widget=<card or section id>`,
   `&` in a macro name URL-encoded) and put the bracketed source number
   after the link, on first use. `python3 $S/inventory.py sources ORG
   ID...` emits the numbered entries for "Appendix: Sources"; a tile takes
   the manifest date; a derived figure cites the documents it came from and
   its `Derived:` line sits in the Data notes. No `Source:` lines in the
   body.
3. **At most six numbers in a paragraph and one short table per section.**
   Numbers are quantities: counts, percentages, scores. Years and dates are
   context and do not count, so write them in full rather than "this year".
   Longer tables go to "Appendix: Supporting tables"; the body says so in
   half a sentence. The goals table in the goals slot is exempt.
4. **A caveat only when it changes the reading, as one plain clause**, next
   to the first figure it limits: GitHub accounts not people, affiliation
   known share, absence of evidence for HIPs, GitHub Releases only.
5. **Two documents that disagree by more than about a tenth put no number
   in the body.** Say the published views differ and point to the Data
   notes, which carry both with ids. Smaller differences: headline the
   dashboard's figure, footnote the other.
6. **Never write a judgment section.** Progress against goals, next goals,
   help required, community calls, project composition and the lifecycle
   recommendation are `> [MAINTAINER INPUT]` slots that state the TAC's
   question and list the evidence in the draft by section and figure. The
   goals slot is a table (goal, one-line purpose, Result column for the
   maintainer, evidence column) built from the prior report's goals, with the
   prior table in the supporting-tables appendix as filed (stray empty
   cells normalised, and said so). The lifecycle
   slot states the current stage as the prior report gave it.
7. **Describe, don't editorialise.** "The maintainer bench spans fourteen
   employers" is a finding; "diversity is healthy" is the slot's to say.
8. **Two or three figures**, rendered with `render_figure.py` as
   `references/figures.md` describes, saved in `figures/` beside the draft,
   each with alt text, a one-sentence plain caption and a source number.
9. **The header is one line** (data as of, dashboard link, period, the
   re-run clause when the period is incomplete, pointer to the appendix).
   Provenance and `BASE` live in the appendix.
10. **First line of the file:** `[//]: # (SPDX-License-Identifier: CC-BY-4.0)`.

## 6. Appendices

In this order: Supporting tables (each with a `Source:` line), Sources
(numbered, from `inventory.py sources`), Data notes and gaps as
`references/gap-appendix.md` describes: provenance, data notes (both sides
of every disagreement, counting rules, data defects seen), gaps (what the
TAC wants, why the API cannot answer, the closest signal, the smallest
follow-up), coverage checklist. An empty gaps section almost certainly
means the checks were skipped.

## 7. Check, export, hand back

```bash
python3 $S/check_draft.py "$OUT/2027-annual-Hiero.md" --manifest "$WORK/manifest.json"
python3 $S/export_report.py png "$OUT/figures"
python3 $S/export_report.py pdf "$OUT/2027-annual-Hiero.md"
```

- Fix every failure the linter reports and judge each warning; it checks
  the rules in step 5 and prints the body's shape against the filed review.
- Then read the body once yourself as the TAC reviewer, and once as the
  maintainer who must fill each slot from the evidence listed under it.
- Trace three numbers back to their JSON documents: one tile, one table row,
  one chart bucket. Open each figure.
- `git status`: no tracked file may have changed. Write the draft where the
  maintainer asks, else in your scratch directory, and say it is untracked.
  Never under `outputs/`, which is gitignored and regenerated.
- Hand back in the shape of `references/handback.md`: re-run warning first,
  files (markdown is what gets filed; PNGs are for GitHub attachments; the
  PDF is a review copy), slots, filing steps, data defects for
  `/write-analytics-issue`, manifest `generated_at` and `git_sha`.
- Do not commit, push or open a PR. Maintainers file under
  `tac/project-updates/<year>/` and add the `mkdocs.yml` nav entry under
  "1H" (annual) or "2H" (mid-year).
