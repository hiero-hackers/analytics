---
name: lfdt-report
description: Draft Hiero's LF Decentralized Trust TAC report (annual review or mid-year update) from this repo's published data API. Data-backed sections get real, cited numbers; judgment sections become marked maintainer slots pre-filled with the evidence and the prior report's goals; a Data Gaps appendix lists what the TAC asks for that the API cannot yet supply. Use whenever asked to write, draft, refresh, or prepare the LFDT / TAC annual review or mid-year report for hiero-ledger or any other org in the manifest.
---

# Drafting the LFDT TAC report

Hiero files two reports a year with the LFDT Technical Advisory Council (TAC):
an annual review and a mid-year update. Part of each is measurable (activity,
diversity, releases, security posture) and part is judgment (goals, help
needed, lifecycle recommendation). This skill fills the measurable part from
the data API with cited numbers, leaves the judgment part as marked slots that
already carry their evidence, and lists everything the TAC wants that the API
cannot supply.

The bar is **TAC-ready**: a maintainer should be able to fill the slots in
under an hour and open the PR against `lf-decentralized-trust/governance`
without rewriting anything else. The gap list is as much the product as the
draft: it is how we learn what the API layer is missing, and it is the input
for follow-up issues.

This skill is documentation only. It never changes code, pipelines, or the API
contract. A gap is reported, not fixed.

## 1. Settle the inputs

- **Report type:** `annual` or `mid-year`. If the request does not say, ask.
  Never guess; the two have different questions and different periods.
- **Org:** default `hiero-ledger`. Any org in the manifest works. Others
  (e.g. `hiero-hackers`) are sparse by design, and that is a case to handle,
  not an error (see section 3).
- **Period:** annual covers the previous calendar year and is filed early in
  the new one; mid-year covers the six months since the annual review. Write
  the period as explicit months in the draft header ("January to June 2026").
  `YYYY` in the file name is the filing year, not the data year. If the org
  is younger than the period (first bucket of `repo-growth` or the oldest
  `maintainer-pipeline` bucket is inside it), start the period at the org's
  first month and say so. If the data stops before the period ends (a draft
  run early, so every bucket in the period is `partial`), the header must
  say "draft against data to <date>; re-run after <period end>", the
  partial buckets are shown but compared with nothing. Year-over-year on
  whole years is then only possible between the two complete years before
  the period. Complete *months* inside the period may still be compared
  like-for-like with the same months a year earlier where a series covers
  both (release events do; the monthly pipeline holds twelve months and
  does not). Name the months. Never extrapolate.
- **Is a TAC report the right artefact?** Only LFDT projects file one. For
  any other org in the manifest (e.g. `hiero-hackers`) the draft is an
  API-coverage exercise in the TAC's shape, useful for finding gaps, and the
  header must say it is not for filing.
- **Prior report:** the TAC compares against it, so fetch it by default. The
  governance repo publishes every report at
  `https://raw.githubusercontent.com/lf-decentralized-trust/governance/main/tac/project-updates/<year>/<file>.md`
  (names: `YYYY-annual-Hiero.md`, `YYYY-MidYear-Hiero.md`; list the directory
  with the GitHub contents API if unsure of the case). For an annual the
  prior report is last year's annual, in the `<filing year - 1>/`
  directory; for a mid-year it is this year's annual, in `<filing year>/`. The prior report has
  two goals tables; copy the *forward-looking* one (its "{YEAR-1} Year's
  Goals", or for a mid-year the annual's goals for this year) verbatim into
  the "Performance Against Prior Goals" slot so the maintainer answers
  against the real goals. If the fetch fails, list the
  year's directory and look for the project's file before giving up; if there
  is none (a first report, or a non-project org), say "no prior report" in
  the slot and the appendix. Do not guess file names for other orgs and do
  not paraphrase goals from memory.

## 2. Read the TAC instructions again, every run

Fetch both pages. They define the questions, and they change (mid-year
reports became mandatory in 2026):

- Annual: <https://lf-decentralized-trust.github.io/governance/project-updates/annual-review-instructions/>
- Mid-year: <https://lf-decentralized-trust.github.io/governance/project-updates/mid-year-update-instructions/>

`references/report-structure.md` holds a snapshot of both, plus the template.
If a live page differs from the snapshot, **the live page wins**: follow it, and
note in the appendix what changed. If the fetch fails, use the snapshot and say
so in the appendix.

## 3. Discover the data. Never assume it.

The API is static JSON, so no auth and no queries. Fetch the manifest first
into a scratch directory (not the repo, not a shared `/tmp` path):

```bash
BASE=https://hiero-hackers.github.io/analytics/data/api/v1
WORK=${WORK:-$(mktemp -d)}
curl -fsS "$BASE/manifest.json" -o "$WORK/manifest.json"
python3 - "$WORK/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(m['version'], 'wip=', m.get('wip'), m['generated_at'], m['provenance'])
print('orgs:', list(m['orgs']))
PY
```

`curl -fsS` fails loudly on an HTTP error. Without `-f` a 404 page is saved
as JSON and the first symptom is a confusing decode error.

If the dashboard was generated locally, the same files are under
`outputs/data/api/v1/`; use that only when the maintainer says to work offline.

Rules while reading the manifest:

- **Record provenance first:** `generated_at`, `provenance.git_sha`,
  `provenance.data_as_of`, and whether `wip` is true. All of it goes in the
  appendix. `data_as_of` is the oldest dataset watermark, so it is the honest
  "data as of" date for the whole report.
- **Org not in `orgs`:** stop and list the orgs that are. Do not draft.
- **Sections and chart sections:** read them from
  `orgs[org].sections`, `orgs[org].chart_sections`, `orgs[org].views` and
  `orgs[org].metrics`. Do not hard-code section ids; resolve them by `macro`
  and `id` from the manifest in front of you. `references/api-section-map.md`
  says which ones answer which TAC question.
- **Ids live at three levels, and tiles have none.** `chart_sections[].id`
  names a *card* (`maintainer-pipeline`, `scorecard`) and is what the
  dashboard deep link takes; the charts on a card have a `title` but no id;
  each variant has a `label`, an `interactive.path`, and the document at
  that path has its own `id` (`maintainer_pipeline_yearly`). Cite a chart as
  "card id, chart title, variant label (document id)". Metric tiles are
  `orgs[org].metrics[macro]`, a list per macro with a `label` and no id;
  cite them as "<Macro> tile '<label>'".
- **Notes live in two places.** A variant's `note` and `methodology` may be
  in the manifest's `chart_sections` entry rather than in the document (the
  release-timeline documents carry none). Read both before citing.
- **Chart variants are matched by shape, not label.** Labels are period
  words (`All time`, `1 year`, `Week`) or descriptive titles. Open the
  document and read `frequency` (`year`, `month`, `week`, `day`, or
  `snapshot` for a series that is re-measured each run and has no
  `comparison`) or `window` to know what you have. The yearly series of
  `maintainer-pipeline` is the `All time` variant; the `1 year` variant is
  twelve monthly buckets. For a young org several variants are identical
  (the `1 year` and `All time` windows both cover its whole life); say so
  once and cite one.
- **`row_count` is the all-time table.** Sections with `periods` carry
  separate `7d`, `30d` and `365d` tables (`periods` is a dict of row lists
  with the same columns; their row count is the list length) and they
  differ (on 2026-10-06 `understaffed` had 16 all-time rows, 4 in `365d`,
  26 in `7d`; `gonedark` 14 all-time and 81 in `365d`). For an annual report
  cite the `365d` table and its row count; for a mid-year cite `365d` and say
  the API has no six-month table. Name the period beside every count.
- **Zero rows means one of two things.** Read the section's
  `description` first. If each row is an *exception or finding* (understaffed
  repos, gone-dark permission holders, HIPs with no activity, HIPs citing an
  unknown number, single-employer repos), zero rows is a measured result:
  report "none", citing the section. If each row is a *member of a
  population* (contributors, repos, teams, affiliations, releases), zero rows
  is a gap ("no rows"), never a measured zero. When in doubt, say which
  reading you took.
- **`absorbed_by`:** the section is a role variant that another card now
  renders as a tab. Do not report it as a separate section; read its rows as
  variants of the absorbing section.
- **A macro missing for the org:** `macro_absent_notes[macro]` says why.
  Quote that note verbatim in the appendix, but the notes are global, not
  per org, so follow the quote with one sentence stating this org's actual
  state. Two failure modes seen: a note says "nothing generated for this org
  yet" for a macro the org does have (use the data, record the note as a
  data defect); and the Community note says Discord is "published once,
  under hiero-ledger" while hiero-ledger itself has no Community macro
  (quote it, then say the macro is absent for this org too). An ungoverned
  org has no role data; write "role data is not available for this org",
  never "no maintainers".
- **No `maintainer-pipeline` (no governance config):** the activity trend
  falls back to `repo-growth` (repos created per month), the `profiles`
  period rows (`7d`, `30d`, `365d` distinct contributors) and the heatmap's
  monthly columns. Counting non-zero heatmap cells per month gives "people
  with scored activity that month" for the rows present; it is a derivation,
  it is a weighted score not a count, and you must say both.
- **Chart documents** live at `charts[].variants[].interactive.path`. Their
  `kind` (`timeseries`, `categories`, `matrix`, `network`, `events`) decides
  how to read them. `web/src/api.ts` documents every shape; read it, do not
  guess field names.

## 4. Read what the API says about itself, then the numbers

For every document you cite, read its own `note`, `methodology`, `population`,
`window`, `stale` and `generated_at` before using a number. Those are the
definitions a TAC reader needs, and they are the only reliable statement of who
was counted. Quote or paraphrase them wherever a figure could be misread. If a
document says `stale: true`, say so next to the number.

Do not recompute what a section, chart document, or metric tile already
states. Simple derivations (a row count, the difference between two buckets,
a sum of complete monthly buckets) are fine, but say you derived it and from
which document.

Time series:

- A bucket marked `partial` (the current year, month, week or day) is never
  compared with a complete one. Name the partial bucket you excluded.
- **The document's `comparison` pair is always two adjacent buckets** (last
  complete year vs the one before; last complete month vs the one before). Use
  it only for that adjacent comparison, and name the two buckets. It is *not*
  "since the last report".
- **For "since the last report" or "the past six months"** derive it yourself
  from the monthly buckets of the `frequency: month` variant: name the months
  in the period, name the months you compared them with, and say the series
  counts distinct people per bucket so months must not be summed to get
  unique people.
- Heatmaps cover the last six complete calendar months. The document holds
  every row; `top_n: 25` is the dashboard's display cut, so say "top 25 shown
  on the dashboard, N rows in the document". They show who carries the work,
  not totals, and a `role` of "General User" on every row means the org has
  no role data, not that nobody holds a role.
- Table periods are `7d`, `30d`, `365d` plus the default rows (all-time).
  There is no 180-day or six-month table; for a mid-year view use the monthly
  chart buckets. For an org younger than a year the `365d` rows equal the
  default rows; say so rather than reporting the same figure twice.
- When a document's `note` and its `population` or `window` disagree about
  the period, `window` and `population` win; quote the note's claim as the
  note's and record the mismatch in the appendix.
- **Calendar-period deliverables are derived.** No published figure is "the
  period's" releases or HIP activity: the funnel is cohort-based, heatmaps
  cover six months, release windows are trailing. Count releases in the
  period from the `release-timeline` events document (`Last 18 months`
  variant; rows carry `repo`, `tag_name`, `time` and `type`, which is
  `release` or `prerelease`; filter on `time`, state whether prereleases are
  included) and say you derived it.
- **Org-wide concentration is not published.** HHI, largest-org share and
  single-employer flags exist per repo and per team only. Do not state an
  org-wide HHI; describe the employer shares from `org-diversity` and the
  known-share tiles instead.
- **Known disagreements** between documents are listed in
  `references/data-quirks.md`; check each one every run and report both
  sides with ids.

## 5. Write the draft

Follow the template in `references/report-structure.md`. Rules:

1. **Every number carries its source:** the section, chart or metric id, plus
   the data-as-of date. Put the JSON URL where a reader can follow it, and the
   dashboard deep link
   (`https://hiero-hackers.github.io/analytics/#tab=<Macro>&org=<org>&widget=<id>`).
   A short `Source:` line under each block beats inline clutter. Define
   `BASE` (the API root) and `DASH` (the dashboard root) once in the header
   and write paths relative to them; repeat the data-as-of date only where
   a document's own `generated_at` differs. Charts are
   drawn from JSON, so there are no image URLs; if the maintainer wants a
   figure, say which chart to print from the dashboard's print button.
2. **Never write a judgment section yourself.** Progress against goals, next
   goals, help required, the community-calls narrative, project composition
   and the lifecycle recommendation are `> [MAINTAINER INPUT]` slots. Each slot
   states the TAC's question, lists the evidence in the draft that bears on
   it, and (for goals) carries the prior report's goals verbatim. Pointing at
   evidence is fine; drawing the recommendation is not.
3. **Describe, don't editorialise.** "The committer bench spans N employers" is
   a finding. "Diversity is healthy" is a judgment: attribute it to the TAC
   criterion or leave it to the slot.
4. **Print coverage caveats next to the figures they limit.** Affiliation known
   share, HIP absence-of-evidence, manual Discord exports and the like.
5. **When two documents disagree about the same thing, report both** with their
   ids. Do not pick one silently.
6. **Role counts add only where the document says they do.** The Governance
   tiles, the `affiliations` variants and the `maintainer-pipeline` series
   count each person once at their highest role anywhere, so maintainer and
   committer figures from those documents are disjoint and can be added or
   compared. Per-repository and per-team sections (`repo`, `repodiversity`,
   `teamrepo`, `maintainer-pipeline-by-repo`) resolve roles per repository,
   so one person appears in several rows; never sum them. Counts across time
   buckets are never summed either.
7. **Write it as a report, not a dashboard dump.** The real Hiero reviews are
   prose paragraphs with a few tables. In the body, each data section is one
   or two paragraphs that say what the numbers show, at most one short table
   of headline figures, and one `Source:` line. Everything longer (per-repo
   releases, HIP evidence rows, employer breakdowns beyond the top few) goes
   in "Appendix: Supporting tables", referenced from the body. The prior
   report's goals table inside the goals slot is exempt: it stays where the
   maintainer will edit it, and it is quoted, not written. Aim for the
   filed review's shape: around 2,500 words of body, about thirty
   paragraphs of three to five sentences, two or three tables. Plain prose,
   no emoji, no hype, no headings the template does not have.
8. **Start the file with the SPDX line** the governance repo requires:
   `[//]: # (SPDX-License-Identifier: CC-BY-4.0)`.
9. **Two or three figures, not more.** Render them from the chart documents
   with `scripts/render_figure.py` as described in `references/figures.md`
   (active contributors by role per year, maintainers by employer, and the
   repository count are the defaults), save them in `figures/` beside the
   draft, and embed each with alt text, an italic caption and a `Source:`
   line. Then run `scripts/export_report.py` to produce the PNG figures
   (GitHub attachments do not accept SVG) and a PDF review copy of the
   draft; both are companions, the markdown is what gets filed. Tell the
   maintainer in the hand-back how the images get hosted when the report is
   filed.

## 6. Data Gaps appendix

Every report ends with the appendix described in `references/gap-appendix.md`.
It is a first-class deliverable, not an apology. Each entry names what the TAC
wants, why the API cannot answer it, the closest signal available, and the
follow-up that would close the gap. An empty appendix almost certainly means
the checks were skipped.

## 7. Repo-specific traps

Read `references/data-quirks.md` before writing any number. It lists the
vocabulary collisions (two meanings of "adoption", unknown vs independent),
what is and is not counted, and the documents that disagree with each other.

## 8. Before handing it back

- Trace three numbers back to their JSON documents and confirm them. Pick
  one tile, one table row and one chart bucket.
- Re-read every `Source:` line: id, data-as-of date, JSON path, dashboard
  link. Deep links cannot be checked with curl (the dashboard is a
  single-page app and returns the shell for every hash); say they are
  unverified if you could not open one in a browser.
- Open each figure (or describe it from its SVG) and check the partial
  bucket is hollow, the series legend is right and the subtitle matches the
  document's population.
- Count the `[MAINTAINER INPUT]` slots and list them at the end of your reply,
  so the maintainer knows exactly what is theirs to write.
- Run `git status`: no tracked file may have changed.
- **Where to save.** Write the draft where the maintainer asks. If they did
  not say, write it to your scratch directory and give them the path; say
  plainly that it is untracked. Do not put it under `outputs/`, which is
  gitignored and regenerated by the pipelines, so a hand-finished report there
  can be lost without warning.
- List every file produced: the markdown, the `figures/` SVGs and PNGs,
  and the PDF, with the one-line reminder that only the markdown is filed.
- Report which manifest the draft ran against (`generated_at`, `git_sha`).
- Do not commit, push, or open a PR. Maintainers file the report with LFDT,
  which means adding it under `tac/project-updates/<year>/` and updating the
  `mkdocs.yml` nav under that year's "1H" or "2H", as the TAC instructions
  describe.
