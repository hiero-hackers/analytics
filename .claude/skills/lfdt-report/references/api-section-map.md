# Mapping TAC questions to the data API

Base URL: `https://hiero-hackers.github.io/analytics/data/api/v1/`. Every
`path` in the manifest is relative to it (for example
`hiero-ledger/profiles.json`). Read `web/src/api.ts` for every document shape,
and `docs/architecture.md` ("Data flow and persistence") for what the API is.

## Manifest anatomy (as observed, API generated 2026-10-06)

Top level: `version`, `wip`, `generated_at`, `provenance` (`git_sha`,
`data_as_of`), `macro_order`, `macro_summaries`, `macro_glossaries`,
`macro_absent_notes`, `group_order`, `period_labels`, `orgs`.

Per org, `orgs[org]` holds:

| Key | What it is |
|---|---|
| `sections` | Table documents: `id`, `macro`, `title`, `row_count`, `path`, sometimes `absorbed_by` |
| `chart_sections` | Cards of charts. Each chart has `variants[]`; a variant's `interactive` gives `kind` and `path`, plus its own `note` and `methodology` |
| `views` | Bespoke views (the HIPs board and coverage matrix) |
| `metrics` | Headline tiles per macro: `label`, `value`, `note`, `methodology` |
| `entities` | Repository and contributor indexes, with counts |

`macro_glossaries[macro]` defines every column and term for that tab. Use it
when explaining a figure; do not invent definitions.

Chart `kind`s: `timeseries` (buckets by year, month, week or day; rows carry
`partial`), `categories`, `matrix`, `network`, `events`.

## Which macro answers which question

The macros below existed for `hiero-ledger` on 2026-10-06. Resolve ids from the
manifest you fetched; treat the ids here as hints, not constants. "Gap?" means
check the appendix reference.

| TAC question or criterion | Look in | Notes |
|---|---|---|
| Size of the organisation | `entities.repositories.count`, chart `repo-growth` | Cross-check against `row_count` of repo-level sections; they have differed (42 repos vs 44 rows in `repoactivity`, `codeowners`, `release-staleness`). Report both and name the ids |
| Consistent or increasing contribution activity | Contributors metrics tiles; chart `maintainer-pipeline` (yearly, monthly variants); section `profiles` (period columns) | `maintainer-pipeline` counts distinct active people per role per bucket, so it is both an activity trend and the active-maintainer trend |
| Maintainer and contributor diversity (annual Q5, mid-year Q5) | Governance macro: chart `org-diversity` (donut, single-employer repos and teams, mix by repo and by team); sections `affiliations`, `repodiversity`, `teamdiversity`; metrics `maintainers`, `committers`, `triage`, `... affiliations known` | Always print the known-share tiles beside any employer chart. Glossary defines HHI, largest org %, distinct orgs, single employer |
| Did active maintainers rise or fall over the past year | Chart `maintainer-pipeline`, maintainer tier, yearly and monthly variants | Mind `partial` buckets. For "changes since the last report" use `comparison` or the last two complete buckets |
| Maintainer bench and risk | Sections `understaffed`, `gonedark`, `loadshare`; metrics `quiet permission-holders (180d+)`, `quiet teams` | The 180-day threshold is fixed, not the tab's period |
| Deliverables or outputs (annual Q2, mid-year Q2) | Releases macro: sections `release-staleness`; chart `release-timeline` (`events` kind, 7d / 30d / 365d / 18-month variants); metrics `repos with releases`, `released last 90d %`, `>3x their own typical gap` | GitHub Releases only; repos that tag without Releases show nothing. Prereleases are excluded from latest-release and pace |
| Standards and specification progress | HIPs macro: charts `hip-adoption-funnel`, `hip-activity-by-status`, `hip-repo-engagement`; views `hip-board`, `hip-matrix`; section `hip-no-activity` | Evidence, not completion. This is not "adoption" in the TAC sense |
| Security posture | Security & scorecards macro: charts `scorecard`, `ownership`; section `codeowners` | Declared configuration, not enforcement |
| Onboarding and new-contributor pipeline | Issues & onboarding macro: chart `issue-difficulty`; Contributors metric `completed a GFI %` | Describes the open queue, not throughput |
| Discord and community | Community macro | Manual export, published once under hiero-ledger. Not present in the 2026-10-06 manifest for hiero-ledger, so expect a gap |
| Activity concentration and who carries the work | Charts `activity-heatmap` (by contributor, team, organisation, repository), `contributor-network`, `role-networks` | Top-25 views, six months, bots excluded |
| Prior goals, next goals, help, lifecycle recommendation | No data | Maintainer slots |
| Adopters (ADOPTERS file) | No data | Gap |

## Mid-year specifics

- The API has no six-month period tab; use the monthly buckets of
  `maintainer-pipeline` and the six-month heatmaps, and say which months.
- "Are PRs and issues resolved promptly": the manifest has no time-to-close or
  time-to-merge. `issue-difficulty` describes the open queue only. Gap.
- "Are Discord questions answered promptly": gap even when the Community macro
  is present (it counts messages, not response times).

## Other orgs

`hiero-hackers` is the community org, not an LFDT project. On 2026-10-06 its
entry listed only three table sections (`profiles`, `codeowners`,
`release-staleness`) and chart cards for Contributors and Security &
scorecards; no Governance or HIPs sections appeared. Re-check against the
manifest you fetch: list the macros the org actually has and compare them with
`macro_order`. For every macro in `macro_order` that the org lacks, the
top-level `macro_absent_notes[macro]` gives the reason (for example that the org
publishes no governance config, or that the HIP process is specific to
hiero-ledger). A draft for such an org is legitimate. It must mark each missing
macro as a gap with that note quoted, and must not write role or diversity
findings it cannot support.
