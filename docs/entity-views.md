# Repository and contributor detail views

Every repository and every person with tracked activity in an organisation has
a detail view on the dashboard. It opens from their name in any table or chart.

## What is counted

Tracked activity is five kinds of GitHub event:

- pull requests opened;
- reviews submitted;
- pull requests merged, credited to the person who merged;
- issues opened;
- labels applied (label removals are not counted).

It does not measure commits, comments, reactions or anything else, and it is not
a measure of individual performance. Every view says so above its numbers.

The counts use the same events and definitions as the Contributors tab's
profiles (`analysis/contributor_activity_profile.combined_activity_events`).
Automation accounts are excluded by `domain/bots.is_bot_login`, the same filter
the rest of the dashboard uses.

## Data model

```
persisted datasets (contributor_activity_<org>_all, issue_label_events_<org>_all)
  → analysis/entity_activity.py          pure, per-window counts from the events
  → pipelines/entity_activity.py         writes 5 org-level CSVs (+ .meta.json)
  → export/entity_views.py (data_api)    indexes + one detail document per entity
```

**Windows.** Week, 1 month and 1 year are the 7, 30 and 365 days before the
pipeline ran, plus all time. Each window is computed from the events inside it,
not by summing or filtering the all-time profiles. So a repository's _active
contributors_ in a week is the number of distinct people with an action there
that week. The per-repository contributor profiles the dashboard had before were
all-time only; these tables add the windowed versions.

**Tables** (`dashboard_spec/entities.py` names them; each is long form, with one
row per entity and window that had activity):

| File                                                        | One row per                        | Columns                                                                                       |
| ----------------------------------------------------------- | ---------------------------------- | --------------------------------------------------------------------------------------------- |
| `entity_repo_activity.csv`                                  | repository × window                | the 5 counts, `total_actions`, `active_contributors`, first/last active                       |
| `entity_contributor_activity.csv`                           | contributor × window               | the 5 counts, `total_actions`, `repos_touched`, work-mix counts and shares, first/last active |
| `entity_repo_contributor_activity.csv`                      | (repository, contributor) × window | the 5 counts, `total_actions`, work-mix shares, first/last active                             |
| `entity_repo_monthly.csv`, `entity_contributor_monthly.csv` | entity × month (UTC)               | the 5 counts                                                                                  |

The three activity tables also carry:

- `window_end`, the moment every window ends;
- `data_through`, the latest tracked event in the organisation. A view warns
  when there is no event after the Week window's start, because a quiet week
  then can't be told apart from activity data that was not refreshed.

**Joined tables.** A repository's view also joins the optional per-repository
tables other pipelines write, declared in `dashboard_spec.entities.REPO_RELATED`:

| Section        | Tables                                                                                                                                                                                      |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Releases       | `release_repo_summary.csv`, `release_timeline.csv`                                                                                                                                          |
| Governance     | `repo_activity_overview.csv` (role counts, active permission-holders), `repo_affiliation_diversity.csv`, `review_load_share.csv`, `repo_wise_codeowner_status.csv`, `role_coverage_all.csv` |
| HIP engagement | `hip_repo_engagement.csv`                                                                                                                                                                   |
| Onboarding     | `difficulty_by_repo.csv` (including issues without a difficulty label)                                                                                                                      |
| Security       | `org_scorecard_checks.csv`                                                                                                                                                                  |

**Links back to sources.** Each section links to the dashboard sections its
tables feed (`links: [{macro, id, title}]`). `data_api` builds the map from what
it actually published for the org, so a link never leads to a section the org
lacks. Following one closes the detail view and jumps to that section, the same
way a shared section link does. While charts above the target load, the jump
holds the target in place for a few seconds, and stops as soon as the reader
scrolls. Shared section links benefit too.

Repositories match by bare or `owner/repo` name. A table this run did not
produce is listed as unavailable, for example when an offline run skips the
network-only pipelines. A table that was produced but has no row for the
repository shows as an empty section, which the view states.

## Data API (v1, additive)

Each org's manifest entry gains `entities`:

```json
"entities": {
  "repositories": {"path": "<org>/entities/repositories.json", "count": 40},
  "contributors": {"path": "<org>/entities/contributors.json", "count": 1457}
}
```

**Indexes.** Each index (`kind: repositories-index` / `contributors-index`,
`schema_version: 1`) lists every entity with its `id`, its names, all-time
`total_actions` and `last_active`. Its `detail_path` template locates each
entity's document, with `{id}` substituted.

**Ids.** Ids are lower-case and safe to use as file names. A repository name that
starts with a dot gets an underscore instead (`.github` → `_github`), so no
document is a hidden file. Clients find ids through the index, not by deriving
them from names.

**Detail documents.** Each detail document (`kind: repository` / `contributor`,
`schema_version: 1`) is fetched only when a reader opens it. It carries:

- **Provenance:** `source` (the CSVs it was built from), `generated_at` and
  `stale` (from the CSV sidecar, with the same 132-hour rule as sections);
- **Explanation:** `scope`, `population`, `methodology` and `limits`;
- **Dates:** `window` (end, `data_through`, and each window's start),
  `first_active` and `last_active`;
- **Counts:** `summary` and `mix`, keyed by `all`, `365d`, `30d` and `7d`. A
  window with no activity is all zeros, never missing;
- **Trend:** a standard monthly timeseries chart document (the same format
  `chart_data` publishes);
- **Breakdown table:** `contributors` (repository) or `repositories`
  (contributor), shaped like a section with all-time `rows` and `periods`;
- **Repositories only:** `related` and `unavailable`.

The `entities/` tree is rewritten on every emit, so an entity that leaves the
data does not leave a stale document behind.

**Size.** hiero-ledger publishes about 1,500 detail documents (about 18 MB;
median 9 KB per contributor), which brings the API to about 24 MB across
about 1,660 files, or 1.3 MB gzipped. See `docs/snapshots.md`.

## Navigation

- **Opening a view.** `entity=repo:<id>` or `entity=contributor:<id>` in the hash
  opens a view over the current tab. The tab, org and focus keys are kept, so
  "Back to <tab>" and browser Back return exactly where the reader was. Links are
  real hash hrefs: a click adds a history entry, and Forward, "open in new tab"
  and copied links all reopen the view.
- **Which names link.** Once a kind's index has loaded (indexes are fetched once
  per org, after the manifest), every well-formed repository name or GitHub
  login of that kind links, so names behave the same everywhere. A name with no
  tracked activity opens a short view saying so, with a "View on GitHub" button.
  Only a loaded index can say that. While an index is loading, has failed, or
  isn't published, its names stay plain GitHub links. A detail URL opened then
  shows loading, a Retry for the failed index, or "not published for this org"
  instead of a false "no tracked activity".
- **Where names link.** Table cells (repositories and people), heatmap rows,
  ranking and release-timeline axis labels, chart Data views, and the network's
  focus panel all link. Each keeps a separate GitHub link: an icon beside the
  name, or the view's "View on GitHub".
- **Focus.** In a chart's Data view, the dashboard-focus toggle moves to a
  crosshair beside the name and keeps its label ("Focus on …"). Names without a
  detail view keep their old behaviour. A detail view's "Focus the dashboard on …"
  sets the focus and returns to the tab in one history entry.
- **Switching.** Choosing a tab closes an open view. Switching organisation
  clears both the focus and the open view, since both belong to one org.
- **Reuse.** A view is built from the dashboard's own pieces: section cards and
  groups (with the sidebar's "On this page"), the period-tabbed table with its
  filter and CSV export, the interactive chart with its Data view and CSV, the
  loading, error and retry states, and "Print page", which uses the tab print
  path.

## Limits of the source data

- **Capped reads.** At most 100 reviews per pull request and 100 label events
  per issue are read.
- **Merge credit.** A merge counts for the person who merged, who may not be
  the author.
- **Unattributable events.** Events whose author GitHub no longer reports, and
  label events without an actor, are dropped.
- **Window timing.** Windows end when the pipeline runs, not when the data was
  fetched. With stale datasets the recent windows undercount, and the view warns
  about it (see `data_through` above).
- **Bot filtering.** Automation accounts that `is_bot_login` does not recognise
  are counted as people. `stepsecurity-app` in hiero-ledger is one example.
- **Other orgs.** Only the organisation's own repositories are counted. A person's
  activity in other organisations is not.

## Tests

- **Calculations:** `tests/analysis/test_entity_activity.py` covers window
  boundaries, distinct active contributors, merge credit, work mix, bots and
  label removals.
- **Pipeline:** `tests/pipelines/test_entity_activity.py`.
- **Documents:** `tests/export/test_entity_views.py` covers ids, indexes,
  zero-filled windows, the trend document, joined and missing tables, freshness,
  the manifest entry and stale-document cleanup.
- **Contract:** `tests/contracts/test_output_contract.py` checks, in the full
  synthetic run, that every org's index resolves to documents and that every
  joined table is actually produced.
- **Frontend:** `web/src/test/entities.test.tsx` covers the URL, table and chart
  links, Back/Forward, the rendering, focus, org and tab switches, and the
  missing and failed cases. `web/e2e/entities.spec.ts` covers real browser
  history and printing, in Chromium and Firefox.
