# Mapping TAC questions to the data API

Base URL: `https://hiero-hackers.github.io/analytics/data/api/v1/`. Every
`path` in the manifest is relative to it (for example
`hiero-ledger/profiles.json`). Read `web/src/api.ts` for every document shape,
and `docs/architecture.md` ("Data flow and persistence") for what the API is.

Dashboard deep link for any section or chart card:
`https://hiero-hackers.github.io/analytics/#tab=<Macro>&org=<org>&widget=<id>`
(macro names as in `macro_order`, e.g. `Governance`, `Security & scorecards`;
URL-encode the ampersand).

## Manifest anatomy (as observed, API generated 2026-10-06)

Top level: `version`, `wip`, `generated_at`, `provenance` (`git_sha`,
`data_as_of`), `macro_order`, `macro_summaries`, `macro_glossaries`,
`macro_absent_notes`, `group_order`, `period_labels`, `orgs`.

Per org, `orgs[org]` holds:

| Key | What it is |
|---|---|
| `sections` | Table documents: `id`, `macro`, `title`, `row_count` (all-time rows), `path`, sometimes `absorbed_by`. The document may carry `periods`: `{"7d": rows, "30d": rows, "365d": rows}`, plain row lists with the same columns; their count is the list length |
| `chart_sections` | Cards of charts. Each chart has `variants[]`; a variant's `interactive` gives `kind` and `path`, plus its own `note` and `methodology` |
| `views` | Bespoke views (the HIPs board and coverage matrix) |
| `metrics` | `Record<macro, tile[]>`: a list of headline tiles per macro, each `label`, `value`, `note`, `methodology`; no id |
| `entities` | Repository and contributor indexes, with counts |

`macro_glossaries[macro]` defines every column and term for that tab. Use it
when explaining a figure; do not invent definitions.

Chart `kind`s: `timeseries` (buckets by year, month, week or day; rows carry
`partial`; `frequency` names the bucket; `comparison` is the last two complete
adjacent buckets), `categories`, `matrix`, `network`, `events`.

Variant labels are period words, not shapes; the document path and its `frequency` field tell you the bucket. Observed on `hiero-ledger`:

| Card | Variant label | Document path ends in | What the document is |
|---|---|---|---|
| `maintainer-pipeline` | `All time` | `maintainer_pipeline_yearly.json` | `frequency: year`, every year since 2018, current year partial |
| `maintainer-pipeline` | `1 year` | `maintainer_pipeline_monthly.json` | `frequency: month`, last 12 months, current month partial |
| `maintainer-pipeline` | `1 month` | `maintainer_pipeline_weekly.json` | `frequency: week` |
| `maintainer-pipeline` | `Week` | `maintainer_pipeline_daily.json` | `frequency: day` |
| `release-timeline` | `Last 18 months` / `1 year` / `1 month` / `Week` | varies | `events`, trailing window of 548 / 365 / 30 / 7 days |
| `activity-heatmap` | one per dimension | varies | `matrix`, last six complete months, top 25 rows |

## Reading rules

The inventory (`scripts/inventory.py show`) applies these for you; they are
spelled out so you can check it and so the appendix can explain a figure.

- **Provenance first.** `generated_at`, `provenance.git_sha`,
  `provenance.data_as_of` and `wip` go in the appendix. `data_as_of` is the
  oldest dataset watermark, so it is the honest "data as of" date for the
  whole report.
- **Ids live at three levels, and tiles have none.** `chart_sections[].id`
  names a *card* and is what the dashboard deep link's `widget=` takes (so
  do section ids and view ids; an absorbed section's id also resolves). The
  charts on a card have a `title` but no id; each variant has a `label`, an
  `interactive.path`, and the document at that path has its own `id`, equal
  to its file stem. Cite a chart as "card id, chart title, variant label
  (document id)". Tiles are `orgs[org].metrics[macro]`, a list per macro
  with `label` and `value`; cite them as "<Macro> tile '<label>'".
- **Variants are matched by shape, not label.** Labels are period words or
  descriptive titles. Read `frequency` (`year`, `month`, `week`, `day`, or
  `snapshot` for a series re-measured each run, which has no `comparison`)
  or `window`. For a young org several variants are identical; say so once
  and cite one.
- **`row_count` is the all-time table.** Sections with `periods` carry
  `7d`, `30d` and `365d` row lists with the same columns; their counts are
  the list lengths and they differ (on 2026-10-06 `understaffed` had 16
  all-time rows, 4 in `365d`, 26 in `7d`; `gonedark` 14 and 81). An annual
  cites the `365d` table; a mid-year cites `365d` and says there is no
  six-month table. Name the period beside every count.
- **Zero rows means one of two things.** Read the section's `description`.
  Where each row is an exception or finding (understaffed repos, gone-dark
  holders, HIPs with no activity or an unknown number, single-employer
  repos) zero rows is a measured "none"; where each row is a member of a
  population (contributors, repos, teams, affiliations, releases) zero rows
  is a gap. Say which reading you took when in doubt.
- **`absorbed_by`** marks a role variant that another card renders as a
  tab; read its rows as variants of the absorbing section, not as a
  separate section.
- **Absent-macro notes are global strings.** Quote
  `macro_absent_notes[macro]` for a macro the org truly lacks, then state
  the org's actual state in one sentence: a note can say "nothing generated
  for this org yet" for a macro the org has (use the data, record the note
  as a defect), and the Community note says Discord is published under
  hiero-ledger while hiero-ledger itself has no Community macro. An
  ungoverned org has no role data: write "role data is not available for
  this org", never "no maintainers".
- **No `maintainer-pipeline` (no governance config):** the activity trend
  falls back to `repo-growth`, the `profiles` period rows and the heatmap's
  monthly columns (a weighted score, not a count; counting non-zero cells
  per month is a derivation and must be called one).
- **Notes live in two places.** A variant's `note` and `methodology` may be
  on the manifest card, in the document, or both; the release-timeline
  `Last 18 months` document carries them, its sibling variants do not.
  When a note and the document's `population` or `window` disagree about
  the period, `window` and `population` win and the mismatch is a data note.
- **Two repo counts.** `entities.repositories.count` lists repos with
  tracked activity; the repo-level tables and `repo-growth` list every
  repo. Report the table count as the org size and the entity count as
  "repos with activity".
- **Heatmaps** hold every row (`top_n: 25` is the dashboard's display cut)
  and cover the last six complete calendar months; a `role` of "General
  User" on every row means the org has no role data.
- **Table periods** are `7d`, `30d`, `365d` plus the default rows
  (all-time). There is no 180-day or six-month table. For an org younger
  than a year the `365d` rows equal the default rows; say so once.
- **Chart documents** live at `charts[].variants[].interactive.path`; their
  `kind` (`timeseries`, `categories`, `matrix`, `network`, `events`) decides
  how to read them. `web/src/api.ts` documents every shape.

## Which macro answers which question

The sections below existed for `hiero-ledger` on 2026-10-06. Resolve ids from
the manifest you fetched; treat the ids here as hints, not constants. "Gap?"
means check the appendix reference.

| TAC question or criterion | Look in | Notes |
|---|---|---|
| Size of the organisation | `entities.repositories.count`, chart `repo-growth` | Cross-check against `row_count` of repo-level sections; they have differed (42 repos vs 44 rows in `repoactivity`, `codeowners`, `release-staleness`; the Releases tile says "26 of 44"). Report both and name the ids |
| Consistent or increasing contribution activity | Contributors metrics tiles; chart `maintainer-pipeline` (`All time` for the yearly trend, `1 year` for the monthly trend); section `profiles` (period columns) | `maintainer-pipeline` counts distinct active people per role per bucket, so it is both an activity trend and the active-maintainer trend. Use `comparison` only for adjacent buckets |
| Maintainer and contributor diversity (annual Q5, mid-year Q5) | Governance macro: chart `org-diversity` (donut, single-employer repos and teams, mix by repo and by team); sections `affiliations` (with `committeraffiliations` as its tab), `repodiversity` (with `committerrepodiversity`), `teamdiversity`; metrics `maintainers`, `committers`, `triage`, `maintainer affiliations known`, `committer affiliations known` | Always print the known-share tiles beside any employer chart. Glossary defines HHI, largest org %, distinct orgs, single employer. Org-wide documents are disjoint by role; per-repo and per-team ones are not |
| Did active maintainers rise or fall over the past year | Chart `maintainer-pipeline`, Maintainers series, `All time` (yearly) and `1 year` (monthly) variants | Mind `partial` buckets. For "since the last report" compare the months yourself and name them; `comparison` is only month-over-month or year-over-year |
| Maintainer bench and risk | Sections `understaffed`, `gonedark`, `loadshare`, `repoactivity` (`365d` period tables for an annual); metrics `quiet permission-holders (180d+)`, `quiet teams` | The 180-day threshold is fixed, not the tab's period. Zero rows in a period table of `understaffed` or `gonedark` is a measured "none" for that period |
| Governance structure | Sections `repo` (role per person per repo), `teams`, `teamrepo`, `tscrepo` | `tscrepo` is the closest signal for TSC activity: which repos TSC members work in and their role, not dated reviews |
| Deliverables or outputs (annual Q2, mid-year Q2) | Releases macro: section `release-staleness`; chart `release-timeline` (`events`, 7d / 30d / 365d / 18-month windows); metrics `repos with releases`, `released last 90d %`, `>3x their own typical gap` | GitHub Releases only; repos that tag without Releases show nothing. Prereleases are plotted but excluded from latest-release and pace |
| Standards and specification progress | HIPs macro: charts `hip-adoption-funnel`, `hip-activity-by-status`, `hip-repo-engagement`; views `hip-board`, `hip-matrix`; sections `hip-evidence` (PR-level backing for every HIP figure), `hip-no-activity`, `hip-unknown` (PRs citing a HIP not in the spec list) | Evidence, not completion. This is not "adoption" in the TAC sense. Cite `hip-evidence` as the table behind any funnel or matrix number |
| Security posture | Security & scorecards macro: charts `scorecard`, `ownership` (code-owner coverage and runners); section `codeowners` | Declared configuration, not enforcement |
| Onboarding and new-contributor pipeline | Issues & onboarding macro: chart `issue-difficulty`; Contributors metric `completed a GFI %` | Describes the open queue, not throughput |
| Discord and community | Community macro | Manual export, published once under hiero-ledger. Not present in the 2026-10-06 manifest for hiero-ledger, so expect a gap |
| Activity concentration and who carries the work | Charts `activity-heatmap` (by contributor, team, organisation, repository), `contributor-network`, `role-networks` | Top-25 views, last six complete months, bots excluded |
| Prior goals, next goals, help, lifecycle recommendation | No data; the prior report's goals come from the governance repo (SKILL.md step 1) | Maintainer slots |
| Adopters (ADOPTERS file) | No data | Gap |

## Mid-year specifics

- The API has no six-month period tab; use the monthly buckets of
  `maintainer-pipeline` (`1 year` variant, `frequency: month`) and the
  six-month heatmaps, and say which months.
- "Are PRs and issues resolved promptly": the manifest has no time-to-close or
  time-to-merge. `issue-difficulty` describes the open queue only. Gap.
- "Are Discord questions answered promptly": gap even when the Community macro
  is present (it counts messages, not response times).

## Other orgs

`hiero-hackers` is the community org, not an LFDT project. On 2026-10-06 its
entry listed only three table sections (`profiles`, `codeowners`,
`release-staleness`), chart cards for Contributors (including an
`org-overview` card hiero-ledger does not have), Security & scorecards,
Issues & onboarding and Releases, no views, and tiles for Contributors and
Releases only. Re-check against the manifest you fetch: list the macros the
org actually has and compare them with `macro_order`. For every macro in
`macro_order` that the org lacks, the top-level `macro_absent_notes[macro]`
gives the reason (for example that the org publishes no governance config, or
that the HIP process is specific to hiero-ledger). Quote a note only for a macro the org truly lacks; on 2026-10-06 the notes
for Security & scorecards, Issues & onboarding and Releases said "nothing
generated for this org yet" while the org had data for all three, so treat a
contradicting note as a stale global string and record it as a data defect.
A draft for such an org is legitimate as a gap-finding exercise, not for
filing. It must mark each missing macro as a gap with that note quoted, and
must not write role or diversity findings it cannot support. Its repo count
differs too (28 in the tables, 24 in `entities`, which lists only repos with
tracked activity).
